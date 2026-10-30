"""Offline regressions against the actual context-loss failure, not model grades."""
import copy
import json
import unittest
from pathlib import Path
from app.baseline import verified_sources, segments_for, search
from app.evidence_context import with_context
from app.generation_contract import prepare_model_input


class EvidenceContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sources = verified_sources()
        partials = {Path(s['local_file']).name: s for s in sources[5:]}
        cls.segments = [segment for source in sources[:5]
                        for segment in segments_for(source, partials)]

    def test_actual_sql_fragment_has_its_subject_and_authentication_condition(self):
        hit = next(s for s in self.segments if s['source_id'] == 'rls' and s['line_start'] == 587)
        unchanged = copy.deepcopy(hit)
        citation = with_context([hit], list(reversed(self.segments)))[0]
        self.assertEqual(hit, unchanged)
        self.assertEqual(citation['segment_id'], hit['segment_id'])
        self.assertEqual(citation['text'], 'is always false in SQL.')
        context = citation['context']
        self.assertIn('without an authenticated user', context['text'])
        self.assertIn('returns `null`', context['text'])
        self.assertIn('```sql\nnull = user_id\n```', context['text'])
        self.assertNotIn('auth.jwt()', context['text'])
        current = {s['segment_id']: s for s in self.segments}
        for reference in context['segments']:
            self.assertEqual(reference['source_id'], hit['source_id'])
            self.assertEqual(reference['sha256'], hit['sha256'])
            self.assertEqual(current[reference['segment_id']]['section'], hit['section'])
        prepared = json.loads(prepare_model_input('Test question', [citation])['input'])
        self.assertEqual(prepared['evidence'][0]['context'], context)

    def test_bypass_rls_excerpt_includes_user_token_exception(self):
        hit = next(s for s in self.segments if s['source_id'] == 'rls' and s['line_start'] == 752)
        context = with_context([hit], self.segments)[0]['context']
        self.assertIn('access token', context['text'])
        self.assertGreaterEqual(context['line_end'], 758)

    def test_bounded_context_does_not_split_code_or_change_rank(self):
        hit = next(s for s in self.segments if s['source_id'] == 'rls' and s['line_start'] == 587)
        short = with_context([hit], self.segments, max_chars=len(hit['text']))[0]
        self.assertEqual(short['context']['text'], hit['text'])
        result = search(self.segments, 'Could permissions explain an empty array from a browser query?', limit=3)
        self.assertEqual((result['citations'][0]['source_id'], result['citations'][0]['line_start']), ('keys', 90))
        self.assertEqual(len(result['citations']), 3)

    def test_unknown_or_changed_excerpt_cannot_gain_verified_context(self):
        hit = copy.deepcopy(self.segments[0])
        hit['text'] = 'Changed source text'
        with self.assertRaises(ValueError):
            with_context([hit], self.segments)
        hit['segment_id'] = 'unknown'
        with self.assertRaises(ValueError):
            with_context([hit], self.segments)


if __name__ == '__main__':
    unittest.main()
