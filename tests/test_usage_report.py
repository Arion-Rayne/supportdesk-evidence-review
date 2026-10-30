"""Cost accounting fixtures: buckets must not be charged twice; not account bills."""
import unittest
from scripts.usage_report import estimate


class UsageEstimateTests(unittest.TestCase):
    def test_cache_buckets_replace_regular_input_instead_of_adding_to_it(self):
        row={'requested_model':'gpt-6-luna','usage':{'input_tokens':100,'output_tokens':20,
             'input_tokens_details':{'cached_tokens':30,'cache_write_tokens':40}}}
        # 30 regular + 30 cached + 40 writes + 20 output, rates per million.
        self.assertAlmostEqual(estimate(row),0.0000183,places=12)

    def test_embedding_prompt_tokens_and_generation_without_cache_details(self):
        self.assertAlmostEqual(estimate({'requested_model':'text-embedding-3-small',
            'usage':{'prompt_tokens':1200,'total_tokens':1200}}),0.000024,places=12)
        self.assertAlmostEqual(estimate({'requested_model':'gpt-6-luna',
            'usage':{'input_tokens':100,'output_tokens':20}}),0.00002,places=12)

    def test_unknown_or_invalid_usage_is_not_reported_as_zero_cost(self):
        usages=[None,{'input_tokens':True,'output_tokens':1},
                {'input_tokens':10,'output_tokens':1,'input_tokens_details':{'cached_tokens':11}},
                {'input_tokens':10,'output_tokens':1,'input_tokens_details':{'cache_write_tokens':-1}}]
        for usage in usages:
            with self.subTest(usage=usage):
                self.assertIsNone(estimate({'requested_model':'gpt-6-luna','usage':usage}))


if __name__=='__main__':
    unittest.main()
