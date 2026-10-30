"""Real OpenAI embeddings and exact pgvector cosine retrieval over fixed snapshots."""
from hashlib import sha256
from time import perf_counter
import json
import math

import httpx

from app import database
from app.evidence_context import with_context
from app.baseline import ROOT, search, verified_sources
from app.model_gateway import ModelError, load_settings

MODEL = 'text-embedding-3-small'
DIMENSIONS = 256


def ensure_schema():
    with database.connect() as connection:
        connection.execute((ROOT / 'migrations/vector/001_vector_index.sql').read_text(encoding='utf-8'))


def index_text(segment):
    return segment['section'] + '\n' + segment['text']


def digest(text):
    return sha256(text.encode('utf-8')).hexdigest()


def vector_literal(values):
    if len(values) != DIMENSIONS or any(isinstance(value, bool) or not isinstance(value, (int, float))
                                      or not math.isfinite(value) for value in values):
        raise ModelError('invalid_embedding', 'The embedding service returned an invalid vector.')
    if not any(value != 0 for value in values):
        raise ModelError('invalid_embedding', 'The embedding service returned a zero vector.')
    return '[' + ','.join(str(float(value)) for value in values) + ']'


def embed_texts(texts, transport=None):
    if not texts or len(texts) > 64 or any(not text.strip() for text in texts):
        raise ModelError('configuration', 'Each embedding batch must contain 1–64 nonempty texts.')
    if sum(len(text.encode('utf-8')) for text in texts) > 400000:
        raise ModelError('budget_limit', 'The embedding input exceeds the batch limit; no request was sent.')
    settings = load_settings(profile='openai_luna')
    settings.require_enabled()
    # Reserve under the same shared authorized batch, with the actual embedding model recorded.
    call_id = database.reserve_model_call(settings)
    with database.connect() as connection:
        connection.execute('UPDATE model_call_attempts SET requested_model = %s WHERE id = %s', (MODEL, call_id))
    started, usage = perf_counter(), None
    try:
        with httpx.Client(timeout=60, follow_redirects=False, transport=transport) as client:
            response = client.post('https://api.openai.com/v1/embeddings',
                headers={'Authorization': 'Bearer ' + settings.api_key},
                json={'model': MODEL, 'input': texts, 'dimensions': DIMENSIONS, 'encoding_format': 'float'})
        if response.status_code != 200:
            raise ModelError('provider_http', f'Embedding service returned HTTP {response.status_code}; the index was not built.')
        data = response.json()
        usage = data.get('usage')
        if data.get('model') != MODEL:
            raise ModelError('invalid_embedding', 'The returned embedding model does not match the requested model.')
        rows = data['data']
        if len(rows) != len(texts) or {row['index'] for row in rows} != set(range(len(texts))):
            raise ModelError('invalid_embedding', 'The embedding response does not match the input count or indexes.')
        vectors = [vector_literal(row['embedding']) for row in sorted(rows, key=lambda row: row['index'])]
    except httpx.TimeoutException:
        error = ModelError('timeout', 'The embedding request timed out and may have been billed; it will not be retried automatically.')
    except httpx.HTTPError:
        error = ModelError('network', 'The embedding service connection failed; it will not be retried automatically.')
    except ModelError as exception:
        error = exception
    except (ValueError, TypeError, KeyError, AttributeError):
        error = ModelError('invalid_embedding', 'The embedding response format is invalid.')
    else:
        database.finish_model_call(call_id, 'success', usage, (perf_counter() - started) * 1000, None, MODEL)
        return vectors
    database.finish_model_call(call_id, 'failed', usage, (perf_counter() - started) * 1000, error.code, MODEL)
    raise error


def index_status():
    segments = database.current_segments()
    with database.connect() as connection:
        present = connection.execute("SELECT to_regclass('public.segment_vectors') AS name").fetchone()['name']
        if present:
            rows = connection.execute('SELECT segment_id, text_sha256 FROM segment_vectors WHERE model = %s',
                                      (MODEL,)).fetchall()
        else:
            rows = []
    found = {(row['segment_id'], row['text_sha256']) for row in rows}
    count = sum((segment['segment_id'], digest(index_text(segment))) in found for segment in segments)
    return {'model': MODEL, 'dimensions': DIMENSIONS, 'indexed_segments': count,
            'current_segments': len(segments), 'ready': bool(segments) and count == len(segments)}


def build_index():
    verified_sources()
    ensure_schema()
    segments = database.current_segments()
    with database.connect() as connection:
        existing = {(row['segment_id'], row['text_sha256']) for row in connection.execute(
            'SELECT segment_id, text_sha256 FROM segment_vectors WHERE model = %s', (MODEL,)).fetchall()}
    missing = [segment for segment in segments if (segment['segment_id'], digest(index_text(segment))) not in existing]
    for offset in range(0, len(missing), 64):
        batch = missing[offset:offset + 64]
        vectors = embed_texts([index_text(segment) for segment in batch])
        with database.connect() as connection:
            for segment, vector in zip(batch, vectors):
                connection.execute('''INSERT INTO segment_vectors(segment_id, model, dimensions, text_sha256, embedding)
                    VALUES (%s, %s, %s, %s, %s::vector) ON CONFLICT DO NOTHING''',
                    (segment['segment_id'], MODEL, DIMENSIONS, digest(index_text(segment)), vector))
    return index_status()


def prepare_queries(questions):
    # Queries cached by exact text and embedding model; repeat retrieval incurs no new call.
    ensure_schema()
    unique = list(dict.fromkeys(questions))
    with database.connect() as connection:
        existing = {row['query_sha256'] for row in connection.execute(
            'SELECT query_sha256 FROM query_vectors WHERE model = %s', (MODEL,)).fetchall()}
    missing = [question for question in unique if digest(question) not in existing]
    for offset in range(0, len(missing), 64):
        batch = missing[offset:offset + 64]
        vectors = embed_texts(batch)
        with database.connect() as connection:
            for question, vector in zip(batch, vectors):
                connection.execute('''INSERT INTO query_vectors(query_sha256, model, dimensions, embedding)
                    VALUES (%s, %s, %s, %s::vector) ON CONFLICT DO NOTHING''',
                    (digest(question), MODEL, DIMENSIONS, vector))


def retrieve(segments, question, method='vector', limit=3):
    if method not in ('vector', 'hybrid') or not 1 <= limit <= 30:
        raise ModelError('configuration', 'Invalid vector retrieval method or result limit.')
    if not index_status()['ready']:
        raise ModelError('index_missing', 'The vector index is not ready. Build the index first.')
    prepare_queries([question])
    with database.connect() as connection:
        query = connection.execute('SELECT embedding::text AS vector FROM query_vectors WHERE query_sha256 = %s AND model = %s',
                                   (digest(question), MODEL)).fetchone()['vector']
        rows = connection.execute('''SELECT segment_id, text_sha256,
            embedding <=> %s::vector AS distance FROM segment_vectors WHERE model = %s
            ORDER BY distance, segment_id''', (query, MODEL)).fetchall()
    current = {segment['segment_id']: segment for segment in segments}
    ranked = [row for row in rows if row['segment_id'] in current
              and row['text_sha256'] == digest(index_text(current[row['segment_id']]))]
    if method == 'hybrid':
        keyword = search(segments, question, limit=30)['citations']
        scores = {}
        for ranking in ([row['segment_id'] for row in ranked[:30]], [c['segment_id'] for c in keyword]):
            for rank, identifier in enumerate(ranking, 1):
                scores[identifier] = scores.get(identifier, 0) + 1 / (60 + rank)
        chosen = sorted(scores, key=lambda identifier: (-scores[identifier], identifier))[:limit]
        citations = [dict(current[identifier], score=scores[identifier]) for identifier in chosen]
    else:
        citations = [dict(current[row['segment_id']], score=1 - float(row['distance'])) for row in ranked[:limit]]
    return {'question': question, 'method': method, 'draft': None, 'citations': with_context(citations, segments),
            'needs_review': True, 'review_reason': 'Vector similarity identifies candidate evidence; it does not establish the root cause.',
            'embedding_model': MODEL, 'dimensions': DIMENSIONS}
