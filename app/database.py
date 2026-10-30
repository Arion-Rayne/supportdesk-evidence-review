"""Real PostgreSQL persistence. All user values use bound parameters."""
from pathlib import Path
from uuid import uuid4
import hashlib
import json
import os

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.baseline import ROOT, verified_sources, segments_for


def connect():
    url = os.environ.get('DATABASE_URL')
    if url:
        return psycopg.connect(url, connect_timeout=3, row_factory=dict_row)
    config_path = ROOT / '.local/database.json'
    if not config_path.exists():
        raise psycopg.OperationalError('Local database configuration is missing')
    config = json.loads(config_path.read_text(encoding='utf-8'))
    return psycopg.connect(**config, connect_timeout=3, row_factory=dict_row)


def migrate():
    with connect() as connection:
        connection.execute('SELECT pg_advisory_xact_lock(8765001)')
        connection.execute('''CREATE TABLE IF NOT EXISTS schema_migrations (
            name text PRIMARY KEY, sha256 text NOT NULL,
            applied_at timestamptz NOT NULL DEFAULT now())''')
        for file in sorted((ROOT / 'migrations').glob('*.sql')):
            sql = file.read_text(encoding='utf-8')
            digest = hashlib.sha256(sql.encode()).hexdigest()
            applied = connection.execute(
                'SELECT sha256 FROM schema_migrations WHERE name = %s', (file.name,)).fetchone()
            if applied:
                if applied['sha256'] != digest:
                    raise ValueError('Applied migration was modified: ' + file.name)
                continue
            connection.execute(sql)
            connection.execute('INSERT INTO schema_migrations(name, sha256) VALUES (%s, %s)',
                               (file.name, digest))


def import_sources():
    # Verification and splitting finish before the transaction starts.
    sources = verified_sources()
    partials = {Path(source['local_file']).name: source for source in sources[5:]}
    segments = [segment for source in sources[:5] for segment in segments_for(source, partials)]
    by_source = {source['source_id']: source for source in sources}
    with connect() as connection:
        connection.execute('SELECT pg_advisory_xact_lock(8765002)')
        ids = {}
        for source in sources:
            connection.execute('UPDATE documents SET is_current = false '
                'WHERE source_id = %s AND sha256 <> %s AND is_current',
                (source['source_id'], source['sha256']))
            row = connection.execute('''INSERT INTO documents(id, source_id, sha256, metadata)
                VALUES (%s, %s, %s, %s) ON CONFLICT (source_id, sha256)
                DO UPDATE SET is_current = true RETURNING id''',
                (uuid4(), source['source_id'], source['sha256'], Jsonb(source))).fetchone()
            ids[source['source_id']] = row['id']
        for segment in segments:
            if segment['sha256'] != by_source[segment['source_id']]['sha256']:
                raise ValueError('Segment origin hash does not match verified snapshot')
            connection.execute('''INSERT INTO segments
                (id, document_id, origin_document_id, segment_id, payload)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (document_id, origin_document_id, segment_id) DO NOTHING''',
                (uuid4(), ids[segment['document_id']], ids[segment['source_id']],
                 segment['segment_id'], Jsonb(segment)))
        return counts(connection)


def counts(connection):
    return {table: connection.execute('SELECT count(*) AS n FROM ' + table).fetchone()['n']
            for table in ('documents', 'segments', 'tickets', 'runs', 'reviews')}


def current_segments():
    with connect() as connection:
        rows = connection.execute('''SELECT s.payload FROM segments s
            JOIN documents parent ON parent.id = s.document_id
            JOIN documents origin ON origin.id = s.origin_document_id
            WHERE parent.is_current AND origin.is_current
            ORDER BY s.segment_id''').fetchall()
        return [row['payload'] for row in rows]


def save_ticket(question, result, latency_ms, synthetic):
    ticket_id, run_id = uuid4(), uuid4()
    with connect() as connection:
        connection.execute('INSERT INTO tickets(id, question, synthetic) VALUES (%s, %s, %s)',
                           (ticket_id, question, synthetic))
        connection.execute('''INSERT INTO runs
            (id, ticket_id, method, result, latency_ms, status)
            VALUES (%s, %s, %s, %s, %s, 'success')''',
            (run_id, ticket_id, result['method'], Jsonb(result), latency_ms))
    return {'ticket_id': str(ticket_id), 'run_id': str(run_id), **result}


def read_ticket(ticket_id):
    with connect() as connection:
        ticket = connection.execute('SELECT * FROM tickets WHERE id = %s', (ticket_id,)).fetchone()
        if ticket is None:
            return None
        runs = connection.execute('SELECT * FROM runs WHERE ticket_id = %s ORDER BY created_at, id',
                                  (ticket_id,)).fetchall()
        reviews = connection.execute('SELECT * FROM reviews WHERE ticket_id = %s ORDER BY created_at, id',
                                     (ticket_id,)).fetchall()
        return {'ticket': ticket, 'runs': runs, 'reviews': reviews}


def reserve_model_call(settings):
    from app.model_gateway import ModelError
    settings.require_enabled()
    call_id = uuid4()
    with connect() as connection:
        connection.execute('SELECT pg_advisory_xact_lock(8765003)')
        used = connection.execute('SELECT count(*) AS n FROM model_call_attempts WHERE batch = %s',
                                  (settings.batch,)).fetchone()['n']
        if used >= settings.call_limit:
            raise ModelError('call_limit', 'The batch call limit has been reached; no request was sent.')
        # Reserve $0.01 per attempt, including failures and unknown responses. No release.
        # Only the authorized low-cost OpenAI models are executed in this batch.
        from decimal import Decimal
        if (used + 1) * Decimal('0.01') > Decimal(str(settings.budget_usd)):
            raise ModelError('budget_limit', 'The batch reservation limit has been reached; no request was sent.')
        connection.execute('''INSERT INTO model_call_attempts
            (id, batch, provider, requested_model, status) VALUES (%s, %s, %s, %s, 'reserved')''',
            (call_id, settings.batch, settings.provider, settings.model))
    return call_id


def finish_model_call(call_id, status, usage, latency_ms, error_code, actual_model):
    with connect() as connection:
        connection.execute('''UPDATE model_call_attempts SET
            status = %s, usage = %s, latency_ms = %s, error_code = %s, actual_model = %s
            WHERE id = %s AND status = 'reserved' ''',
            (status, Jsonb(usage) if usage is not None else None, latency_ms,
             error_code, actual_model, call_id))


def save_generated_run(ticket_id, question, generation):
    # Persist validated draft as a new run; prior retrieval stays available for comparison.
    run_id = uuid4()
    result = {**generation, 'question': question,
              'method': generation.get('retrieval_method', 'keyword') + '+model'}
    with connect() as connection:
        connection.execute('''INSERT INTO runs
            (id, ticket_id, method, result, latency_ms, model_name, usage, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'success')''',
            (run_id, ticket_id, result['method'], Jsonb(result), generation['latency_ms'],
             generation['model_name'], Jsonb(generation['usage']) if generation['usage'] is not None else None))
    return {'ticket_id': str(ticket_id), 'run_id': str(run_id), **result}


def list_tickets(limit=40):
    with connect() as connection:
        return connection.execute('''SELECT t.id, t.question, t.synthetic, t.created_at,
            (SELECT count(*) FROM reviews r WHERE r.ticket_id = t.id) AS review_count
            FROM tickets t ORDER BY t.created_at DESC, t.id DESC LIMIT %s''', (limit,)).fetchall()


def save_review(ticket_id, run_id, draft, decision, notes):
    with connect() as connection:
        run = connection.execute('SELECT id FROM runs WHERE id = %s AND ticket_id = %s',
                                 (run_id, ticket_id)).fetchone()
        if run is None:
            return None
        return connection.execute('''INSERT INTO reviews(id, ticket_id, run_id, draft, decision, notes)
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING *''',
            (uuid4(), ticket_id, run_id, draft, decision, notes)).fetchone()
