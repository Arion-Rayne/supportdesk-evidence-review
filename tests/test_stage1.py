"""Integration tests against a disposable, real PostgreSQL database."""
from uuid import uuid4
import json
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from fastapi.testclient import TestClient

from app import database
from app.api import app
from app.baseline import ROOT, search


@unittest.skipUnless(os.environ.get('SUPPORTDESK_TEST_POSTGRES') == '1',
                     'Set SUPPORTDESK_TEST_POSTGRES=1 to run real PostgreSQL integration tests')
class PostgreSQLIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config = json.loads((ROOT / '.local/database.json').read_text(encoding='utf-8'))
        cls.admin_config = dict(config, dbname='postgres')
        cls.test_db = 'supportdesk_test_' + uuid4().hex
        with psycopg.connect(**cls.admin_config, autocommit=True) as connection:
            connection.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(cls.test_db)))
        cls.environment = patch.dict(os.environ, {
            'DATABASE_URL': make_conninfo(**dict(config, dbname=cls.test_db))})
        cls.environment.start()
        database.migrate()
        database.import_sources()
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        cls.environment.stop()
        # Only the generated disposable database is dropped, never the project database.
        if not cls.test_db.startswith('supportdesk_test_'):
            raise ValueError('Unexpected integration-test database name')
        with psycopg.connect(**cls.admin_config, autocommit=True) as connection:
            connection.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(cls.test_db)))

    def stats(self):
        with database.connect() as connection:
            return database.counts(connection)

    def test_workspace_serves_its_separate_assets(self):
        page = self.client.get('/')
        css = self.client.get('/assets/stage1.css')
        script = self.client.get('/assets/stage1.js')
        self.assertEqual((page.status_code, css.status_code, script.status_code), (200, 200, 200))
        self.assertIn('/assets/stage1.css', page.text)
        self.assertIn('/assets/stage1.js', page.text)
        self.assertIn('text/css', css.headers['content-type'])
        self.assertIn('javascript', script.headers['content-type'])

    def test_import_and_migration_repeat_without_duplicates(self):
        before = self.stats()
        database.migrate()
        for _ in range(2):
            response = self.client.post('/imports')
            self.assertEqual(response.status_code, 200)
        self.assertEqual(self.stats(), before)
        self.assertEqual(before['documents'], 7)
        self.assertEqual(before['segments'], 314)

    def test_submit_read_and_provenance(self):
        response = self.client.post('/tickets', json={
            'question': '我在浏览器里查询表，返回空数组。可能是权限问题吗？'})
        self.assertEqual(response.status_code, 201)
        created = response.json()
        citation = created['citations'][0]
        self.assertEqual((citation['source_id'], citation['line_start']), ('keys', 90))
        read = self.client.get('/tickets/' + created['ticket_id']).json()
        self.assertEqual(read['runs'][0]['result']['citations'], created['citations'])
        self.assertIsNone(read['runs'][0]['model_name'])
        self.assertIsNone(read['runs'][0]['usage'])
        self.assertIsNone(created['draft'])
        self.assertTrue(read['ticket']['synthetic'])
        with database.connect() as connection:
            payload = connection.execute('SELECT payload FROM segments WHERE segment_id = %s',
                                         (citation['segment_id'],)).fetchone()['payload']
        self.assertEqual(citation['text'], payload['text'])
        self.assertEqual(citation['sha256'], payload['sha256'])

    def test_invalid_and_unknown_input_does_not_create_records(self):
        before = self.stats()
        for question in ('', '   ', 'x' * 2001):
            self.assertEqual(self.client.post('/tickets', json={'question': question}).status_code, 422)
        self.assertEqual(self.client.get('/tickets/' + str(uuid4())).status_code, 404)
        self.assertEqual(self.client.get('/tickets/not-a-uuid').status_code, 422)
        self.assertEqual(self.stats(), before)

    def test_uncovered_question_is_saved_without_invented_answer(self):
        created = self.client.post('/tickets', json={'question': '明天天气怎么样？'}).json()
        self.assertEqual(created['citations'], [])
        self.assertIsNone(created['draft'])
        self.assertTrue(created['needs_review'])
        self.assertIn('No keyword evidence', created['review_reason'])

    def test_failed_run_insert_rolls_back_ticket(self):
        before = self.stats()
        result = search(database.current_segments(), '查询返回空数组')
        result['cannot_serialize'] = object()
        with self.assertRaises(TypeError):
            database.save_ticket('事务回滚测试', result, 1, True)
        self.assertEqual(self.stats(), before)

    def test_corrupt_package_is_rejected_without_writes(self):
        before = self.stats()
        with patch('app.database.verified_sources', side_effect=ValueError('snapshot mismatch')):
            self.assertEqual(self.client.post('/imports').status_code, 422)
        self.assertEqual(self.stats(), before)

    def test_all_writes_reject_cross_origin_including_imports(self):
        before = self.stats()
        for origin in ('https://other.example', 'https://testserver', 'http://[invalid'):
            self.assertEqual(self.client.post('/imports', headers={'Origin': origin}).status_code, 403)
            self.assertEqual(self.client.post('/tickets', json={'question': 'Test question'},
                                              headers={'Origin': origin}).status_code, 403)
        self.assertEqual(self.client.post('/imports', headers={'Sec-Fetch-Site': 'cross-site'}).status_code, 403)
        self.assertEqual(self.client.post('/imports', headers={'Origin': 'http://testserver'}).status_code, 200)
        self.assertEqual(self.stats(), before)

    def test_generation_checks_database_and_saved_citations_against_source_files(self):
        from copy import deepcopy
        from app.model_gateway import ModelError
        from app.workflow import ticket_inputs

        created = self.client.post('/tickets', json={'question': 'Can I put my secret key in frontend environment variables?'}).json()
        ticket_id = created['ticket_id']
        question, citations = ticket_inputs(ticket_id)
        self.assertEqual(question, created['question'])
        self.assertEqual(citations[0]['segment_id'], created['citations'][0]['segment_id'])

        record = deepcopy(database.read_ticket(ticket_id))
        segments = deepcopy(database.current_segments())
        identifier = record['runs'][0]['result']['citations'][0]['segment_id']
        # Matching tampered copies in the ticket and database must not count as proof.
        record['runs'][0]['result']['citations'][0]['text'] = 'tampered text'
        next(item for item in segments if item['segment_id'] == identifier)['text'] = 'tampered text'
        with patch('app.workflow.database.read_ticket', return_value=record), \
             patch('app.workflow.database.current_segments', return_value=segments):
            with self.assertRaises(ModelError) as error:
                ticket_inputs(ticket_id)
        self.assertEqual(error.exception.code, 'source_changed')

        record = deepcopy(database.read_ticket(ticket_id))
        record['runs'][0]['result']['citations'][0]['url'] = 'https://example.invalid/tampered'
        with patch('app.workflow.database.read_ticket', return_value=record):
            with self.assertRaises(ModelError):
                ticket_inputs(ticket_id)
        with patch('app.workflow.verified_sources', side_effect=ValueError('fixture')):
            response = self.client.get('/tickets/' + ticket_id + '/model-input')
            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.json()['code'], 'source_changed')

    def test_model_reservation_is_atomic_and_survives_new_connection(self):
        from app.model_gateway import ModelError, ModelSettings
        settings = ModelSettings(api_key='TEST-FIXTURE-KEY', enabled=True, call_limit=1,
                                 batch='fixture-' + uuid4().hex)
        def reserve():
            try:
                return database.reserve_model_call(settings)
            except ModelError:
                return None
        with ThreadPoolExecutor(max_workers=2) as executor:
            ids = list(executor.map(lambda _: reserve(), range(2)))
        valid = [value for value in ids if value is not None]
        self.assertEqual(len(valid), 1)
        database.finish_model_call(valid[0], 'failed', None, 1, 'fixture_timeout', settings.model)
        with self.assertRaises(ModelError):
            database.reserve_model_call(settings)
        with database.connect() as connection:
            row = connection.execute('SELECT * FROM model_call_attempts WHERE id = %s', (valid[0],)).fetchone()
        self.assertEqual(row['status'], 'failed')
        self.assertIsNone(row['usage'])

    def test_budget_reservation_stops_before_sending_even_if_call_limit_remains(self):
        from app.model_gateway import ModelError, ModelSettings
        settings=ModelSettings(api_key='TEST-FIXTURE',enabled=True,call_limit=60,
            budget_usd=0.01,batch='budget-fixture-'+uuid4().hex)
        call_id=database.reserve_model_call(settings)
        database.finish_model_call(call_id,'failed',None,1,'fixture_timeout',None)
        with self.assertRaises(ModelError) as context:
            database.reserve_model_call(settings)
        self.assertEqual(context.exception.code,'budget_limit')

    def test_validated_fixture_draft_persists_as_separate_run(self):
        created = self.client.post('/tickets', json={'question': '查询返回空数组'}).json()
        fixture = {'draft': 'TEST FIXTURE DRAFT, NOT MODEL OUTPUT', 'citations': created['citations'][:1],
            'topic': 'TEST FIXTURE', 'missing_information': [], 'needs_review': True,
            'review_reason': 'TEST FIXTURE REVIEW', 'latency_ms': 1, 'model_name': 'fixture-model',
            'usage': {'fixture_only': True}, 'model_called': True, 'status': 'success'}
        saved = database.save_generated_run(created['ticket_id'], created['question'], fixture)
        read = database.read_ticket(created['ticket_id'])
        self.assertEqual(len(read['runs']), 2)
        self.assertIsNone(read['runs'][0]['result']['draft'])
        stored = next(run for run in read['runs'] if str(run['id']) == saved['run_id'])
        self.assertEqual(stored['model_name'], 'fixture-model')
        self.assertEqual(stored['usage'], {'fixture_only': True})
        self.assertEqual(stored['result']['draft'], fixture['draft'])

    def test_review_is_append_only_and_survives_readback(self):
        created = self.client.post('/tickets', json={'question': '人工审核集成验证'}).json()
        endpoint = '/tickets/' + created['ticket_id'] + '/reviews'
        body = {'run_id': created['run_id'], 'draft': '人工草稿，不是模型输出',
                'decision': 'needs_information', 'notes': '请补充错误码'}
        first = self.client.post(endpoint, json=body)
        self.assertEqual(first.status_code, 201)
        second = self.client.post(endpoint, json={**body, 'draft': '第二次人工修改'})
        self.assertEqual(second.status_code, 201)
        read = self.client.get('/tickets/' + created['ticket_id']).json()
        self.assertEqual([r['draft'] for r in read['reviews']], [body['draft'], '第二次人工修改'])
        self.assertEqual(read['reviews'][0]['decision'], 'needs_information')
        self.assertIsNone(read['runs'][0]['result']['draft'])
        self.assertEqual(self.client.post(endpoint, json={**body, 'run_id': str(uuid4())}).status_code, 404)
        self.assertEqual(self.client.post(endpoint, json={**body, 'draft': '  '}).status_code, 422)
        self.assertEqual(self.client.post(endpoint, json=body,
            headers={'Origin': 'https://other.example'}).status_code, 403)

    def test_disabled_generation_never_creates_an_attempt_or_run(self):
        created = self.client.post('/tickets', json={'question': '查询返回空数组'}).json()
        with database.connect() as connection:
            before = connection.execute('SELECT count(*) AS n FROM model_call_attempts').fetchone()['n']
        with patch.dict(os.environ, {'ENABLE_PAID_CALLS': 'false'}):
            response = self.client.post('/tickets/' + created['ticket_id'] + '/generate',
                                       json={'profile': 'openai_luna', 'language': 'en'})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(len(database.read_ticket(created['ticket_id'])['runs']), 1)
        with database.connect() as connection:
            after = connection.execute('SELECT count(*) AS n FROM model_call_attempts').fetchone()['n']
        self.assertEqual(after, before)

    def test_pgvector_extension_and_cosine_fixture(self):
        # Synthetic basis vectors verify SQL distance only, never real embedding quality.
        from app.vector_search import ensure_schema, vector_literal
        ensure_schema()
        a = vector_literal([1.0] + [0.0] * 255)
        b = vector_literal([0.0, 1.0] + [0.0] * 254)
        with database.connect() as connection:
            version = connection.execute("SELECT extversion FROM pg_extension WHERE extname='vector'").fetchone()
            distances = connection.execute('SELECT %s::vector <=> %s::vector AS same, '
                '%s::vector <=> %s::vector AS different', (a, a, a, b)).fetchone()
        self.assertIsNotNone(version)
        self.assertAlmostEqual(distances['same'], 0)
        self.assertAlmostEqual(distances['different'], 1)


if __name__ == '__main__':
    unittest.main()
