"""Provider adapters. Preview is offline; real calls require explicit local settings."""
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
import json
import os
import re

from dotenv import dotenv_values
import httpx
from pydantic import ValidationError

from app.baseline import ROOT
from app.generation_contract import prepare_model_input, validate_model_output


MODELS = {'openai': 'gpt-6-luna', 'gemini': 'gemini-3.1-flash-lite'}
KEY_NAMES = {'openai': 'OPENAI_API_KEY', 'gemini': 'GEMINI_API_KEY'}


class ModelError(Exception):
    """Safe public error; never includes provider response bodies or credentials."""
    def __init__(self, code, message, usage=None):
        super().__init__(message)
        self.code = code
        self.usage = usage


@dataclass(frozen=True)
class ModelSettings:
    provider: str = 'openai'
    model: str = 'gpt-6-luna'
    api_key: str = field(default='', repr=False)
    enabled: bool = False
    call_limit: int = 0
    batch: str = 'sd001-first'
    output_language: str = 'en'
    max_output_tokens: int = 1200
    budget_usd: float = 0.5

    def validate(self):
        if self.provider not in MODELS or self.model != MODELS[self.provider]:
            raise ModelError('configuration', 'Unsupported provider or model; check the local configuration.')
        if not 0 <= self.call_limit <= 100 or not 128 <= self.max_output_tokens <= 1200:
            raise ModelError('configuration', 'The call limit must be 0–100 and the output limit 128–1200.')
        if not 0 <= self.budget_usd <= 0.5:
            raise ModelError('configuration', 'The batch budget must be between $0 and $0.50.')
        if self.output_language not in ('zh', 'en') or not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', self.batch):
            raise ModelError('configuration', 'Invalid reply language or batch name.')
        if '\n' in self.api_key or '\r' in self.api_key:
            raise ModelError('configuration', 'Invalid API key format; check the local configuration.')

    def require_enabled(self):
        self.validate()
        if not self.enabled or self.call_limit == 0:
            raise ModelError('disabled', 'Model calls are disabled; no request was sent.')
        if not self.api_key.strip() or self.api_key == 'PASTE_YOUR_KEY_HERE':
            raise ModelError('missing_key', 'No model API key is configured; no request was sent.')


def model_profiles():
    profiles = json.loads((ROOT / 'config/model_profiles.json').read_text(encoding='utf-8'))
    for name, profile in profiles.items():
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', name):
            raise ModelError('configuration', 'Invalid model profile name.')
        ModelSettings(provider=profile['provider'], model=profile['model'],
                      max_output_tokens=profile['max_output_tokens']).validate()
    return profiles


def load_settings(path: Path | None = None, profile=None, output_language=None):
    # Only known model settings are consumed. No secrets are printed or put into plans.
    names = ('MODEL_PROVIDER', 'MODEL_NAME', 'MODEL_API_KEY', 'ENABLE_PAID_CALLS',
             'MODEL_CALL_LIMIT', 'MODEL_CALL_BATCH', 'OUTPUT_LANGUAGE', 'MODEL_MAX_OUTPUT_TOKENS',
             'OPENAI_API_KEY', 'GEMINI_API_KEY', 'MODEL_BUDGET_USD')
    values = dotenv_values(path or ROOT / '.env', interpolate=False)
    config = {name: os.environ.get(name, values.get(name)) for name in names}
    default_provider = config['MODEL_PROVIDER'] or 'openai'
    selected = None
    if profile is not None:
        selected = model_profiles().get(profile)
        if selected is None:
            raise ModelError('configuration', 'Unknown model profile.')
    provider = selected['provider'] if selected else default_provider
    # Legacy key only belongs to the configured default provider, never to another service.
    key = config.get(KEY_NAMES.get(provider, '')) or (config['MODEL_API_KEY'] if provider == default_provider else '')
    try:
        settings = ModelSettings(provider=provider,
            model=selected['model'] if selected else config['MODEL_NAME'] or MODELS.get(provider, ''),
            api_key=key or '',
            enabled=(config['ENABLE_PAID_CALLS'] or '').lower() == 'true',
            call_limit=int(config['MODEL_CALL_LIMIT'] or '0'),
            batch=config['MODEL_CALL_BATCH'] or 'sd001-first',
            budget_usd=float(config['MODEL_BUDGET_USD'] or '0.5'),
            output_language=output_language or config['OUTPUT_LANGUAGE'] or 'en',
            max_output_tokens=(selected['max_output_tokens'] if selected
                               else int(config['MODEL_MAX_OUTPUT_TOKENS'] or '1200')))
    except (TypeError, ValueError):
        raise ModelError('configuration', 'Call and output limits must be integers.') from None
    settings.validate()
    return settings


def wire_schema(plan):
    # Keep stricter length/True checks server-side, use a conservative schema subset on wire.
    schema = deepcopy(plan['output_schema'])
    def simplify(value):
        if isinstance(value, dict):
            for key in ('title', 'maxLength', 'const'):
                value.pop(key, None)
            for child in value.values():
                simplify(child)
        elif isinstance(value, list):
            for child in value:
                simplify(child)
    simplify(schema)
    identifiers = [entry['segment_id'] for entry in json.loads(plan['input'])['evidence']]
    if identifiers:
        schema['properties']['citation_ids']['items']['enum'] = identifiers
    return schema


def build_request(settings, plan):
    """Build public payload only. Credentials are added solely in the send function."""
    settings.validate()
    schema = wire_schema(plan)
    if settings.provider == 'openai':
        url = 'https://api.openai.com/v1/responses'
        payload = {'model': settings.model, 'instructions': plan['instructions'],
            'input': plan['input'], 'max_output_tokens': settings.max_output_tokens,
            'reasoning': {'effort': 'none'}, 'store': False,
            'text': {'format': {'type': 'json_schema', 'name': 'supportdesk_draft',
                                'strict': True, 'schema': schema}}}
    else:
        url = f'https://generativelanguage.googleapis.com/v1beta/models/{settings.model}:generateContent'
        payload = {'systemInstruction': {'parts': [{'text': plan['instructions']}]},
            'contents': [{'role': 'user', 'parts': [{'text': plan['input']}]}],
            'generationConfig': {'candidateCount': 1, 'maxOutputTokens': settings.max_output_tokens,
                                 'responseMimeType': 'application/json', 'responseJsonSchema': schema}}
    return url, payload


def preview(question, citations, settings):
    plan = prepare_model_input(question, citations, output_language=settings.output_language)
    url, payload = build_request(settings, plan)
    return {'status': 'prepared_only', 'model_called': False,
        'provider': settings.provider, 'model': settings.model,
        'key_configured': bool(settings.api_key.strip()) and settings.api_key != 'PASTE_YOUR_KEY_HERE',
        'calls_enabled': settings.enabled and settings.call_limit > 0,
        'call_limit': settings.call_limit, 'batch': settings.batch,
        'max_output_tokens': settings.max_output_tokens, 'output_language': settings.output_language,
        'has_retrieved_evidence': plan['has_retrieved_evidence'],
        'request_url': url, 'request_body': payload,
        'serialized_request_bytes': len(json.dumps(payload, ensure_ascii=False).encode('utf-8')),
        'input_token_count': None, 'cost_usd': None}


def generate_draft(question, citations, settings, reserve_call, finish_call, transport=None):
    """At most one HTTP attempt. Persistent reservation precedes sending; failures consume it."""
    plan = prepare_model_input(question, citations, output_language=settings.output_language)
    if not plan['has_retrieved_evidence']:
        return {'status': 'skipped_no_evidence', 'model_called': False, 'draft': None,
                'citations': [], 'needs_review': True, 'review_reason': plan['blocked_reason']}
    settings.require_enabled()
    url, payload = build_request(settings, plan)
    if len(json.dumps(payload, ensure_ascii=False).encode('utf-8')) > 24000:
        raise ModelError('budget_limit', 'The input exceeds the batch limit; no request was sent.')
    call_id = reserve_call(settings)
    started = perf_counter()
    usage = None
    actual_model = None
    try:
        headers = ({'Authorization': 'Bearer ' + settings.api_key} if settings.provider == 'openai'
                   else {'x-goog-api-key': settings.api_key})
        # No retry/fallback. Redirects must not forward credentials to another host.
        with httpx.Client(timeout=httpx.Timeout(90, connect=10, write=30, pool=5),
                          follow_redirects=False, transport=transport) as client:
            response = client.post(url, json=payload, headers=headers)
        if response.status_code != 200:
            raise ModelError('provider_http', f'Model service returned HTTP {response.status_code}; no usable draft was produced.')
        data = response.json()
        usage = data.get('usage') if settings.provider == 'openai' else data.get('usageMetadata')
        actual_model = data.get('model') or data.get('modelVersion')
        if settings.provider == 'openai':
            if data.get('status') != 'completed':
                raise ModelError('incomplete', 'The model did not finish its response; no successful draft was saved.', usage)
            parts = [part for entry in data.get('output', []) if entry.get('type') == 'message'
                     for part in entry.get('content', [])]
            if any(part.get('type') == 'refusal' for part in parts):
                raise ModelError('refusal', 'The model refused the request; human review is required.', usage)
            text = ''.join(part.get('text', '') for part in parts if part.get('type') == 'output_text')
        else:
            candidates = data.get('candidates', [])
            if not candidates or candidates[0].get('finishReason') != 'STOP':
                raise ModelError('incomplete', 'The model response was incomplete or blocked; no successful draft was saved.', usage)
            text = ''.join(part.get('text', '') for part in candidates[0].get('content', {}).get('parts', [])
                           if not part.get('thought'))
        validated = validate_model_output(text, citations)
        if not isinstance(actual_model, str) or not actual_model.strip():
            raise ModelError('invalid_output', 'The response did not identify the actual model; no verified draft was saved.', usage)
    except httpx.TimeoutException:
        error = ModelError('timeout', 'The model request timed out and may have been billed; it will not be retried automatically.')
    except httpx.HTTPError:
        error = ModelError('network', 'The model connection failed; it will not be retried automatically.')
    except ModelError as exception:
        error = exception
    except ValidationError as exception:
        # Report only fixed schema error types and known field names; never echo
        # provider input or output into logs or user-facing error messages.
        allowed = {'topic', 'draft', 'citation_ids', 'missing_information', 'needs_review', 'review_reason'}
        problems = []
        for item in exception.errors(include_input=False, include_url=False):
            field = str(item['loc'][0]) if item.get('loc') and item['loc'][0] in allowed else 'root'
            kind = item.get('type', 'unknown')
            if not isinstance(kind, str) or not re.fullmatch(r'[a-z0-9_]{1,64}', kind):
                kind = 'unknown'
            problems.append(field + ':' + kind)
        error = ModelError('invalid_schema',
            'The model response failed schema validation: ' + ', '.join(sorted(set(problems))) + '.', usage)
    except ValueError as exception:
        # Only expose our own fixed validation messages, never provider output.
        if str(exception) in ('Secret key answer requires the user-token condition and its citation',
                              'Secret key bypass requires the user-token condition and its citation'):
            error = ModelError('missing_token_condition',
                'The draft omitted or failed to cite the user-token condition; human review is required.', usage)
        elif str(exception) == 'Model cited a segment outside this retrieval':
            error = ModelError('invalid_citation', 'The model cited an unavailable source segment.', usage)
        elif str(exception) == 'Duplicate model citation IDs':
            error = ModelError('duplicate_citation', 'The model repeated a citation ID.', usage)
        elif str(exception) == 'A draft requires at least one retrieved citation':
            error = ModelError('missing_citation', 'The model returned a draft without a citation.', usage)
        else:
            error = ModelError('invalid_output', 'The model output or citations failed validation; human review is required.', usage)
    except (TypeError, KeyError, AttributeError):
        error = ModelError('invalid_output', 'The model output or citations failed validation; human review is required.', usage)
    else:
        duration = (perf_counter() - started) * 1000
        finish_call(call_id, 'success', usage, duration, None, actual_model)
        return {**validated, 'status': 'success', 'model_called': True,
                'provider': settings.provider, 'requested_model': settings.model,
                'model_name': actual_model, 'usage': usage, 'latency_ms': duration,
                'output_language': settings.output_language, 'call_id': str(call_id)}
    finish_call(call_id, 'failed', usage, (perf_counter() - started) * 1000, error.code, actual_model)
    raise error
