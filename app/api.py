"""Local SupportDesk API: retrieval, opt-in model generation and human review."""
from time import perf_counter
from uuid import UUID
from typing import Literal
from urllib.parse import urlsplit
import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field, field_validator
import psycopg

from app import database
from app.baseline import ROOT, search
from app.model_gateway import ModelError, load_settings, model_profiles
from app.workflow import generate_ticket, preview_ticket

app = FastAPI(title='SupportDesk', version='0.2.0')
logger = logging.getLogger('supportdesk')


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    synthetic: bool = True
    retrieval: Literal['keyword', 'vector', 'hybrid'] = 'keyword'

    @field_validator('question')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('The question must not be blank')
        return value.strip()


class GenerateRequest(BaseModel):
    profile: str = Field(default='openai_luna', max_length=64)
    language: Literal['zh', 'en'] = 'en'


class ReviewRequest(BaseModel):
    run_id: UUID
    draft: str = Field(min_length=1, max_length=10000)
    decision: Literal['draft', 'approved', 'needs_information', 'rejected'] = 'draft'
    notes: str = Field(default='', max_length=2000)

    @field_validator('draft')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('The review must not be blank')
        return value.strip()


@app.middleware('http')
async def request_log(request: Request, call_next):
    started = perf_counter()
    # Apply the same browser-origin check to every state-changing route.
    # Origin-less requests remain available to local command-line clients.
    if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'}:
        origin = request.headers.get('origin')
        try:
            parsed = urlsplit(origin) if origin else None
        except ValueError:
            return JSONResponse(status_code=403, content={
                'detail': 'Requests from another web origin are not accepted.'})
        expected = request.url
        if (request.headers.get('sec-fetch-site') == 'cross-site' or
                (parsed and (parsed.scheme != expected.scheme or
                             parsed.netloc.lower() != expected.netloc.lower() or
                             parsed.path or parsed.query or parsed.fragment))):
            return JSONResponse(status_code=403, content={
                'detail': 'Requests from another web origin are not accepted.'})
    response = await call_next(request)
    # Log route templates only; never request bodies or connection strings.
    route = request.scope.get('route')
    logger.info('%s %s status=%s duration_ms=%.2f', request.method,
                getattr(route, 'path', '/unknown'), response.status_code,
                (perf_counter() - started) * 1000)
    return response


@app.exception_handler(psycopg.Error)
async def database_failure(request: Request, exception: psycopg.Error):
    logger.error('PostgreSQL operation failed: %s', type(exception).__name__)
    return JSONResponse(status_code=503, content={
        'detail': 'The database is unavailable. The operation was not confirmed as saved; start the database and try again.'})


@app.exception_handler(ModelError)
async def model_failure(request: Request, exception: ModelError):
    codes = {'disabled': 403, 'missing_key': 503, 'call_limit': 429, 'timeout': 504,
             'ticket_missing': 404, 'configuration': 422, 'source_changed': 409, 'scope': 422}
    return JSONResponse(status_code=codes.get(exception.code, 502),
                        content={'detail': str(exception), 'code': exception.code})


@app.get('/', include_in_schema=False)
def demo():
    return FileResponse(ROOT / 'app/stage1.html')


@app.get('/assets/stage1.css', include_in_schema=False)
def workspace_styles():
    return FileResponse(ROOT / 'app/stage1.css', media_type='text/css')


@app.get('/assets/stage1.js', include_in_schema=False)
def workspace_script():
    return FileResponse(ROOT / 'app/stage1.js', media_type='text/javascript')


@app.get('/demo', include_in_schema=False)
def static_demo():
    return FileResponse(ROOT / 'demo/index.html')


@app.get('/docs/EVALUATION.md', include_in_schema=False)
def evaluation_notes():
    return FileResponse(ROOT / 'docs/EVALUATION.md', media_type='text/plain; charset=utf-8')


@app.get('/health')
def health():
    with database.connect() as connection:
        stats = database.counts(connection)
    return {'status': 'ok', 'project': 'supportdesk-english-v1', 'database': 'postgresql', 'counts': stats,
            'model_calls_enabled': load_settings().enabled}


@app.get('/models')
def available_models():
    result = []
    for name, profile in model_profiles().items():
        settings = load_settings(profile=name)
        result.append({'profile': name, **profile, 'key_configured': bool(settings.api_key.strip()),
                       'calls_enabled': settings.enabled and settings.call_limit > 0})
    return result


@app.get('/tickets')
def tickets():
    return database.list_tickets()


@app.post('/imports')
def import_documents():
    try:
        return {'status': 'imported', 'counts': database.import_sources()}
    except ValueError:
        raise HTTPException(422, 'Source snapshot verification failed; no documents were imported.')


@app.post('/tickets', status_code=201)
def submit_question(body: Question):
    started = perf_counter()
    segments = database.current_segments()
    if not segments:
        raise HTTPException(503, 'No source documents have been imported.')
    if body.retrieval == 'keyword':
        result = search(segments, body.question, limit=3)
    else:
        from app.vector_search import retrieve
        result = retrieve(segments, body.question, body.retrieval, limit=3)
    result.update(topic=None, missing_information=[])
    return database.save_ticket(body.question, result,
                                (perf_counter() - started) * 1000, body.synthetic)


@app.get('/tickets/{ticket_id}')
def ticket_detail(ticket_id: UUID):
    result = database.read_ticket(ticket_id)
    if result is None:
        raise HTTPException(404, 'The ticket was not found.')
    return result


@app.get('/tickets/{ticket_id}/model-input')
def model_input(ticket_id: UUID, profile: str = 'openai_luna', language: Literal['zh', 'en'] = 'en'):
    return preview_ticket(ticket_id, profile, language)


@app.post('/tickets/{ticket_id}/generate', status_code=201)
def generate(ticket_id: UUID, body: GenerateRequest):
    return generate_ticket(ticket_id, body.profile, body.language)


@app.post('/tickets/{ticket_id}/reviews', status_code=201)
def review(ticket_id: UUID, body: ReviewRequest):
    saved = database.save_review(ticket_id, body.run_id, body.draft, body.decision, body.notes)
    if saved is None:
        raise HTTPException(404, 'The run does not belong to this ticket or was not found.')
    return saved


@app.get('/vector/status')
def vector_status():
    from app.vector_search import index_status
    return index_status()
