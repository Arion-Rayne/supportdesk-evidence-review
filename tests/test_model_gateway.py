"""Offline adapter tests. HTTP responses and credentials are explicit fixtures."""
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch
import json
import os
import unittest

import httpx

from app.model_gateway import ModelError, ModelSettings, generate_draft, load_settings, preview


class ModelGatewayTests(unittest.TestCase):
    def setUp(self):
        self.settings = ModelSettings(api_key='TEST-FIXTURE-KEY', enabled=True, call_limit=1)
        self.citations = [{'segment_id': 'fixture-segment', 'source_id': 'fixture-document',
            'text': 'TEST FIXTURE ONLY', 'section': 'fixture', 'url': 'https://example.invalid/fixture'}]
        self.draft = {'topic': 'TEST FIXTURE', 'draft': 'TEST FIXTURE DRAFT, NOT REAL MODEL OUTPUT',
            'citation_ids': ['fixture-segment'], 'missing_information': [], 'needs_review': True,
            'review_reason': 'TEST FIXTURE REVIEW'}
        self.reserve = Mock(return_value='fixture-call-id')
        self.finish = Mock()
        self.requests = []

    def transport(self, body=None, status=200, timeout=False):
        if body is None:
            body = {'status': 'completed', 'model': 'gpt-6-luna-fixture',
                    'usage': {'input_tokens': 100, 'output_tokens': 50},
                    'output': [{'type': 'message', 'content': [
                        {'type': 'output_text', 'text': json.dumps(self.draft)}]}]}
        def handler(request):
            self.requests.append(request)
            if timeout:
                raise httpx.ReadTimeout('TEST-FIXTURE-KEY MUST NOT LEAK', request=request)
            return httpx.Response(status, json=body)
        return httpx.MockTransport(handler)

    def run_fixture(self, **kwargs):
        return generate_draft('TEST FIXTURE QUESTION', self.citations, self.settings,
                              self.reserve, self.finish, transport=self.transport(**kwargs))

    def test_preview_has_no_key_and_cannot_send(self):
        prepared = preview('TEST FIXTURE QUESTION', self.citations, self.settings)
        self.assertNotIn(self.settings.api_key, json.dumps(prepared))
        self.assertNotIn(self.settings.api_key, repr(self.settings))
        self.assertFalse(prepared['model_called'])
        self.assertIsNone(prepared['input_token_count'])
        self.assertIsNone(prepared['cost_usd'])

    def test_disabled_or_missing_key_never_reserves_or_sends(self):
        for settings in (replace(self.settings, enabled=False), replace(self.settings, call_limit=0),
                         replace(self.settings, api_key='')):
            with self.assertRaises(ModelError):
                generate_draft('TEST FIXTURE', self.citations, settings,
                               self.reserve, self.finish, self.transport())
        self.reserve.assert_not_called()
        self.finish.assert_not_called()
        self.assertEqual(self.requests, [])

    def test_no_evidence_skips_even_when_calls_enabled(self):
        result = generate_draft('TEST FIXTURE', [], self.settings,
                                self.reserve, self.finish, self.transport())
        self.assertFalse(result['model_called'])
        self.assertIsNone(result['draft'])
        self.reserve.assert_not_called()
        self.assertEqual(self.requests, [])

    def test_openai_request_and_validated_result_with_actual_usage(self):
        result = self.run_fixture()
        self.assertEqual(result['citations'], self.citations)
        self.assertEqual(result['model_name'], 'gpt-6-luna-fixture')
        self.assertEqual(result['usage']['input_tokens'], 100)
        self.assertEqual(len(self.requests), 1)
        payload = json.loads(self.requests[0].content)
        self.assertFalse(payload['store'])
        self.assertEqual(payload['max_output_tokens'], 1200)
        self.assertEqual(payload['reasoning']['effort'], 'none')
        self.assertNotIn('tools', payload)
        self.assertTrue(payload['text']['format']['strict'])
        self.assertEqual(payload['text']['format']['schema']['properties']['citation_ids']['items']['enum'],
                         ['fixture-segment'])
        self.assertEqual(self.finish.call_args.args[1], 'success')

    def test_invalid_citation_fails_and_consumes_one_attempt(self):
        self.draft['citation_ids'] = ['invented-id']
        with self.assertRaises(ModelError) as context:
            self.run_fixture()
        self.assertEqual(context.exception.code, 'invalid_citation')
        self.reserve.assert_called_once()
        self.assertEqual(self.finish.call_args.args[1], 'failed')
        self.assertEqual(len(self.requests), 1)

    def test_missing_secret_key_qualification_is_explained_without_leaking_output(self):
        self.citations = [{'segment_id': 'condition', 'source_id': 'fixture-document',
                           'section': 'fixture',
                           'text': 'A secret key bypasses RLS only when the request carries no user access token.'}]
        self.draft.update(draft='The secret key bypasses RLS.', citation_ids=['condition'])
        with self.assertRaises(ModelError) as context:
            self.run_fixture()
        self.assertEqual(context.exception.code, 'missing_token_condition')
        self.assertNotIn('The secret key bypasses RLS.', str(context.exception))
        self.assertEqual(self.finish.call_args.args[1], 'failed')
        self.assertEqual(len(self.requests), 1)

    def test_invalid_schema_reports_field_without_provider_text(self):
        self.draft['needs_review'] = False
        with self.assertRaises(ModelError) as context:
            self.run_fixture()
        self.assertEqual(context.exception.code, 'invalid_schema')
        self.assertIn('needs_review', str(context.exception))
        self.assertNotIn('TEST FIXTURE DRAFT', str(context.exception))
        self.assertEqual(self.finish.call_args.args[1], 'failed')

    def test_timeout_is_not_retried_or_leaked(self):
        with self.assertRaises(ModelError) as context:
            self.run_fixture(timeout=True)
        self.assertEqual(context.exception.code, 'timeout')
        self.assertNotIn(self.settings.api_key, str(context.exception))
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.finish.call_args.args[1], 'failed')

    def test_http_errors_and_redirect_are_not_retried_or_leaked(self):
        for code in (401, 429, 500, 302):
            with self.subTest(code=code), self.assertRaises(ModelError) as context:
                self.run_fixture(body={'error': self.settings.api_key}, status=code)
            self.assertNotIn(self.settings.api_key, str(context.exception))
        self.assertEqual(len(self.requests), 4)
        self.assertEqual(self.finish.call_count, 4)

    def test_incomplete_keeps_usage_but_does_not_return_draft(self):
        body = {'status': 'incomplete', 'usage': {'output_tokens': 1200}, 'output': []}
        with self.assertRaises(ModelError) as context:
            self.run_fixture(body=body)
        self.assertEqual(context.exception.code, 'incomplete')
        self.assertEqual(self.finish.call_args.args[2], body['usage'])

    def test_refusal_is_explicit_failure(self):
        with self.assertRaises(ModelError) as context:
            self.run_fixture(body={'status': 'completed', 'output': [{'type': 'message',
                'content': [{'type': 'refusal', 'refusal': 'TEST FIXTURE'}]}]})
        self.assertEqual(context.exception.code, 'refusal')

    def test_gemini_uses_header_and_validates_same_contract(self):
        self.settings = replace(self.settings, provider='gemini', model='gemini-3.1-flash-lite')
        body = {'modelVersion': 'gemini-fixture', 'usageMetadata': {'promptTokenCount': 100},
            'candidates': [{'finishReason': 'STOP', 'content': {'parts': [
                {'thought': True, 'text': 'TEST FIXTURE THOUGHT'}, {'text': json.dumps(self.draft)}]}}]}
        result = self.run_fixture(body=body)
        request = self.requests[0]
        self.assertEqual(request.headers['x-goog-api-key'], self.settings.api_key)
        self.assertNotIn(self.settings.api_key, str(request.url))
        self.assertEqual(result['citations'], self.citations)
        self.assertEqual(result['usage'], body['usageMetadata'])

    def test_reservation_limit_stops_before_http(self):
        self.reserve.side_effect = ModelError('call_limit', 'TEST FIXTURE LIMIT')
        with self.assertRaises(ModelError):
            self.run_fixture()
        self.finish.assert_not_called()
        self.assertEqual(self.requests, [])

    def test_env_loading_and_invalid_config_do_not_expose_key(self):
        with TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            path = Path(directory) / '.env'
            path.write_text('MODEL_API_KEY=TEST-FIXTURE-KEY\nENABLE_PAID_CALLS=false\n', encoding='utf-8')
            settings = load_settings(path)
            self.assertEqual(settings.api_key, 'TEST-FIXTURE-KEY')
            self.assertFalse(settings.enabled)
            path.write_text('MODEL_API_KEY=TEST-FIXTURE-KEY\nMODEL_CALL_LIMIT=bad\n', encoding='utf-8')
            with self.assertRaises(ModelError) as context:
                load_settings(path)
            self.assertNotIn('TEST-FIXTURE-KEY', str(context.exception))


if __name__ == '__main__':
    unittest.main()
