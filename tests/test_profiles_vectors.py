"""Offline configuration and embedding adapter tests, all credentials/vectors are fixtures."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import os
import unittest
import httpx
from app.model_gateway import load_settings, ModelSettings, ModelError
from app.vector_search import embed_texts, vector_literal

class ProfilesVectors(unittest.TestCase):
    def test_cli_profiles_choose_correct_keys_without_rewriting_env(self):
        with TemporaryDirectory() as folder, patch.dict(os.environ, {}, clear=True):
            env = Path(folder) / '.env'
            body = 'MODEL_PROVIDER=openai\nMODEL_API_KEY=FIXTURE-LEGACY\nGEMINI_API_KEY=FIXTURE-GEMINI\n'
            env.write_text(body, encoding='utf-8')
            self.assertEqual(load_settings(env, profile='openai_luna').api_key, 'FIXTURE-LEGACY')
            gemini = load_settings(env, profile='gemini_lite', output_language='en')
            self.assertEqual((gemini.provider, gemini.api_key, gemini.output_language),
                             ('gemini', 'FIXTURE-GEMINI', 'en'))
            self.assertNotIn('FIXTURE-GEMINI', repr(gemini))
            self.assertEqual(env.read_text(encoding='utf-8'), body)
            env.write_text('MODEL_PROVIDER=openai\nMODEL_API_KEY=FIXTURE-OPENAI\n', encoding='utf-8')
            self.assertEqual(load_settings(env, profile='gemini_lite').api_key, '')

    def test_vector_validation_rejects_malformed_and_zero(self):
        for values in ([1.0], [0.0]*256, [float('nan')]+[0.0]*255, [True]+[0.0]*255):
            with self.assertRaises(ModelError):
                vector_literal(values)

    def test_embedding_http_uses_dimensions_and_restores_response_order(self):
        requests, finished = [], []
        def fixture(request):
            requests.append(json.loads(request.content))
            return httpx.Response(200, json={'model':'text-embedding-3-small','data':[
                {'index':1,'embedding':[0.0,1.0]+[0.0]*254},
                {'index':0,'embedding':[1.0]+[0.0]*255}],
                'usage':{'prompt_tokens':5,'total_tokens':5}})
        # No database or network. Reservation/update/finish are isolated mocks.
        from contextlib import ExitStack
        with ExitStack() as stack:
            stack.enter_context(patch('app.vector_search.load_settings', return_value=ModelSettings(
                api_key='FIXTURE', enabled=True, call_limit=1)))
            stack.enter_context(patch('app.vector_search.database.reserve_model_call', return_value='fixture-id'))
            stack.enter_context(patch('app.vector_search.database.connect'))
            stack.enter_context(patch('app.vector_search.database.finish_model_call', side_effect=lambda *a:finished.append(a)))
            result = embed_texts(['alpha','beta'], transport=httpx.MockTransport(fixture))
        self.assertTrue(result[0].startswith('[1.0,0.0'))
        self.assertEqual(requests[0]['dimensions'], 256)
        self.assertEqual(finished[0][1], 'success')
        self.assertEqual(finished[0][2]['total_tokens'], 5)

if __name__ == '__main__':
    unittest.main()
