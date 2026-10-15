"""Focused read-only checks of this case's token/cost and frozen binding evidence."""
import hashlib
import json
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
BUNDLE = HERE / 'frozen-v1'


def read(name):
    return json.loads((BUNDLE / name).read_bytes())


class PreflightEvidenceTests(unittest.TestCase):
    def test_measured_messages_and_complete_json_are_current_bytes(self):
        raw = (BUNDLE / 'request.FROZEN-NOT-AUTHORIZED.json').read_bytes()
        request = json.loads(raw)
        token = read('token-budget.json')
        for message, name in zip(request['messages'], ['system', 'user']):
            text = message['content']
            self.assertEqual(token[name]['characters'], len(text))
            self.assertEqual(token[name]['utf8_bytes'], len(text.encode()))
        self.assertEqual(token['complete_request_json']['utf8_bytes'], len(raw))
        self.assertEqual(raw, (BUNDLE / 'native/B-rich-evidence/web-experiment/request.json').read_bytes())
        self.assertEqual(hashlib.sha256(raw).hexdigest(), read('readiness.json')['request_sha256'])

    def test_public_parameters_match_current_request(self):
        req = read('request.FROZEN-NOT-AUTHORIZED.json')
        self.assertEqual(req['model'], 'deepseek-flash')
        self.assertEqual(req['temperature'], 0)
        self.assertEqual(req['thinking'], {'type': 'disabled'})
        self.assertEqual(req['response_format'], {'type': 'json_object'})
        self.assertTrue(1 <= req['max_tokens'] <= 393216)
        items = read('official-verification.json')['items']
        required = {'model_id', 'context', 'max_output', 'max_tokens', 'json_response_format', 'temperature', 'thinking', 'request_shape', 'usd_prices_per_million', 'cache_rules'}
        self.assertEqual({i['item'] for i in items if i['item'] in required and i['status'] == 'VERIFIED'}, required)

    def test_estimates_are_not_relabelled_as_usage_or_exact_bounds(self):
        token = read('token-budget.json')
        self.assertEqual(token['historical_observed_usage']['prompt_tokens'], 7610)
        self.assertEqual(token['input']['characters'], 30622)
        self.assertAlmostEqual(token['input']['official_english_ratio_estimate'], 30622 * .3)
        self.assertIsNone(token['actual_current_request_usage'])
        self.assertFalse(token['exact_token_bound_verified'])
        self.assertFalse(token['owner_risk_acceptance'])
        self.assertEqual(token['status'], 'ESTIMATED_TOKEN_FEASIBILITY')
        self.assertEqual(token['planning_total_context_tokens'], token['planning_input_tokens'] + token['max_output_tokens'])
        self.assertEqual(token['estimated_remaining_context_tokens'], token['conservative_context_for_arithmetic'] - token['planning_total_context_tokens'])

    def test_peak_cache_miss_cost_and_budget_risk_are_explicit(self):
        cost = read('cost-budget.json')
        expected = (cost['input_scenario_tokens'] * cost['input_cache_miss_per_million']['peak'] + cost['max_output_tokens'] * cost['output_per_million']['peak']) / 1e6
        self.assertAlmostEqual(cost['conservative_peak_scenario_usd'], expected)
        self.assertAlmostEqual(expected, .0393216)
        self.assertLessEqual(expected, cost['proposed_limit_usd'])
        self.assertEqual(cost['assumed_cache_hit_tokens'], 0)
        self.assertFalse(cost['provider_bill_cap_enforced'])
        self.assertFalse(cost['strict_cost_upper_bound_verified'])
        self.assertEqual(cost['actual_spending_authorized_usd'], 0)

    def test_mock_pending_history_rejected_and_no_authority_created(self):
        drill = read('mock-only-result.json')
        self.assertEqual(drill['candidate_state'], 'PENDING_SEMANTIC_REVIEW')
        self.assertEqual(drill['formal_draft_error'], 'INTERPRETATION_PENDING_REVIEW')
        self.assertEqual(drill['old_response_state'], 'DETERMINISTICALLY_REJECTED')
        self.assertEqual((drill['real_requests'], drill['wordpress_requests'], drill['live_permits'], drill['formal_drafts']), (0, 0, 0, 0))
        self.assertFalse(read('readiness.json')['live_permit_issued'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
