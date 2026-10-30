"""Integration checks for actual snapshots and citation integrity; no model calls."""
from pathlib import Path
from unittest.mock import patch
import re
import unittest

from app import baseline as b


class SnapshotRetrievalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = b.verified_sources()
        cls.partials = {Path(s["local_file"]).name: s for s in cls.sources[5:]}
        cls.segments = [x for s in cls.sources[:5] for x in b.segments_for(s, cls.partials)]

    def test_corrupt_metadata_stops_import(self):
        original = b.load_json
        def changed(path):
            data = original(path)
            if path == "data/download_status.json":
                data[0]["sha256"] = "0" * 64
            return data
        with patch.object(b, "load_json", side_effect=changed):
            with self.assertRaisesRegex(ValueError, "Unverified snapshot"):
                b.verified_sources()

    def test_english_empty_array_question_finds_the_grant_rls_distinction(self):
        result=b.search(self.segments,'Could a permissions issue explain an empty array from a browser query?',limit=3)
        first=result['citations'][0]
        self.assertEqual((first['source_id'],first['line_start']),('keys',90))
        self.assertIn('a policy that matches no rows returns an empty result',first['text'])

    def test_auth_methods_and_standalone_paraphrases_reach_actual_source(self):
        questions = [
            ('有哪些认证方式，可以用邮箱链接登录吗？', 11, 'magic link'),
            ('What authentication methods are available?', 11, 'single sign-on'),
            ('我能使用独立的认证服务吗？', 24, 'standalone product'),
            ('Can I use Supabase Auth independently?', 24, 'standalone product'),
        ]
        for question, line, fact in questions:
            with self.subTest(question=question):
                first = b.search(self.segments, question, limit=3)['citations'][0]
                self.assertEqual((first['source_id'], first['line_start']), ('auth', line))
                self.assertIn(fact, first['text'])

    def test_every_code_block_is_preserved_and_traceable(self):
        count = 0
        for source in self.sources[:5]:
            lines = (b.ROOT / source["local_file"]).read_text(encoding="utf-8").splitlines()
            start = None
            for number, line in enumerate(lines, 1):
                if re.match(r"^\s*```", line):
                    if start is None:
                        start = number
                    else:
                        expected = "\n".join(lines[start - 1:number]).strip()
                        found = [s for s in self.segments if s["source_id"] == source["source_id"]
                                 and s["line_start"] == start and s["line_end"] == number]
                        self.assertEqual(len(found), 1, (source["source_id"], start))
                        self.assertEqual(found[0]["text"], expected)
                        count += 1
                        start = None
            self.assertIsNone(start)
        self.assertGreater(count, 30)

    def test_comparing_tables_retrieves_per_table_grants_and_policies(self):
        for question in (
            '为什么两个表使用相同的凭证，访问结果却不一样？',
            'Why do two tables behave differently with the same credentials?',
        ):
            with self.subTest(question=question):
                result = b.search(self.segments, question, limit=3)
                evidence = '\n'.join(c['context']['text'] for c in result['citations'])
                self.assertIn('Grants decide whether a role can run an operation on the table at all.', evidence)
                self.assertIn('Policies decide which rows that operation applies to.', evidence)
                self.assertIsNone(result['draft'])

    def test_secret_key_questions_include_token_qualification(self):
        for question in ('我可以把secret key放进前端环境变量吗？',
                         'Can I put my secret key in frontend code?',
                         'secret key 会绕过 RLS 吗？'):
            with self.subTest(question=question):
                result = b.search(self.segments, question, limit=3)
                self.assertLessEqual(len(result['citations']), 3)
                contexts = '\n'.join(c['context']['text'] for c in result['citations'])
                self.assertIn('A secret key bypasses RLS only when the request carries no user access token.', contexts)
                self.assertIn('If the request carries one, it runs under the RLS policies', contexts)
                self.assertTrue(any(c['source_id'] == 'keys' for c in result['citations']))
                self.assertIsNone(result['draft'])

    def test_condition_rule_does_not_invent_missing_source(self):
        without_qualifier = [s for s in self.segments if b.SECRET_KEY_CONDITION not in s['text'].lower()]
        result = b.search(without_qualifier, '我可以把secret key放进前端环境变量吗？', limit=3)
        self.assertTrue(result['citations'])
        self.assertFalse(any(b.SECRET_KEY_CONDITION in c['context']['text'].lower() for c in result['citations']))
        self.assertTrue(all(c['segment_id'] in {s['segment_id'] for s in without_qualifier} for c in result['citations']))

    def test_partial_provenance_and_site_relative_links(self):
        children = [s for s in self.segments if s["included_by"]]
        self.assertEqual({s["source_id"] for s in children}, {s["source_id"] for s in self.sources[5:]})
        for segment in children:
            self.assertTrue(segment["sha256"])
            self.assertNotIn("https://github.com/docs/", segment["text"])
        text = "\n".join(s["text"] for s in children)
        self.assertIn("https://supabase.com/docs/guides/getting-started/api-keys#find-your-keys", text)
        self.assertIn("https://supabase.com/dashboard/project/_?", text)

    def test_no_executable_component_scaffolding_in_prose(self):
        for segment in self.segments:
            if not segment["text"].lstrip().startswith("```"):
                self.assertNotRegex(segment["text"], r"<\$?/?(?:Admonition|NavData|GlassPanel|Tabs|TabPanel|ContentListings|AuthProviders)")
                self.assertNotIn("data.items?.map", segment["text"])
                self.assertNotRegex(segment["text"], r"\]\((?:/|#)")
        self.assertTrue(any("<https://en.wikipedia.org/" in s["text"] for s in self.segments))

    def test_three_development_questions_return_actual_citations(self):
        for case in b.load_json("data/cases_dev.json")[:3]:
            result = b.search(self.segments, case["question"])
            self.assertTrue(result["citations"])
            self.assertIsNone(result["draft"])
            for citation in result["citations"]:
                source = next(s for s in self.sources if s["source_id"] == citation["source_id"])
                raw = (b.ROOT / source["local_file"]).read_text(encoding="utf-8").splitlines()
                self.assertLessEqual(citation["line_end"], len(raw))
                self.assertEqual(citation["sha256"], source["sha256"])
                self.assertTrue(citation["url"].startswith(source["url"]))

    def test_repeat_import_has_identical_unique_segment_ids(self):
        again = [x for s in self.sources[:5] for x in b.segments_for(s, self.partials)]
        self.assertEqual(again, self.segments)
        ids = [s["segment_id"] for s in again]
        self.assertEqual(len(ids), len(set(ids)))

    def test_empty_and_uncovered_questions(self):
        with self.assertRaises(ValueError):
            b.search(self.segments, " ")
        with self.assertRaises(ValueError):
            b.search(self.segments, "x" * 2001)
        result = b.search(self.segments, "这个月能给我多少美元折扣？")
        self.assertEqual(result["citations"], [])
        self.assertIn("No keyword evidence", result["review_reason"])


if __name__ == "__main__":
    unittest.main()
