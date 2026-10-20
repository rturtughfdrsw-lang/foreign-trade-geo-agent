"""Prompt assertions and authored expectations, not generated-model evidence.

No semantic classifier, output filter or replacement validator is introduced.
"""
import json
import unittest

import phase7a6_prompt as candidate

e = candidate.previous
CASES = (
    dict(case=1, evidence_items=['ACURA', 'TILTENTA'],
         forbidden=['two configurations'],
         allowed='ACURA and TILTENTA are described separately'),
    dict(case=2, evidence_items=['document A', 'document B', 'document C'],
         forbidden=['three documents show'],
         allowed='The ACURA configuration includes a rotating and swivelling table for five-axis machining.'),
    dict(case=3, evidence_items=['product A', 'product B'],
         forbidden=['all products'], allowed='The documented product is described individually.'),
    dict(case=4, admitted_claim='The synthetic ACURA configuration includes a rotating and swivelling table for five-axis machining.',
         forbidden=[], allowed='The synthetic ACURA configuration includes a rotating and swivelling table for five-axis machining.'),
)


class CompositionPromptTests(unittest.TestCase):
    def assert_authored_expectation(self, case):
        # These strings are hand-authored expectations, never simulated LLM output.
        for phrase in case['forbidden']:
            self.assertNotIn(phrase, case['allowed'].casefold())
        encoded = json.dumps({'article': case['allowed']})
        self.assertEqual(e.phase2.strict(encoded)['article'], case['allowed'])

    def test_case1_items_must_not_be_counted(self):
        self.assertEqual(CASES[0]['evidence_items'], ['ACURA', 'TILTENTA'])
        self.assertIn('Do not calculate, count, aggregate, summarize or infer quantities from evidence items.', candidate.SYSTEM)
        self.assertIn('- counts', candidate.SYSTEM)
        self.assertIn('- multiple configurations', candidate.SYSTEM)
        self.assertIn('Describe each supported item individually when needed.', candidate.SYSTEM)
        self.assert_authored_expectation(CASES[0])
        self.assertEqual(CASES[0]['forbidden'], ['two configurations'])
        self.assertEqual(CASES[0]['allowed'], 'ACURA and TILTENTA are described separately')

    def test_case2_document_count_must_not_become_assertion(self):
        self.assertEqual(len(CASES[1]['evidence_items']), 3)
        self.assertIn('- numbers\n- spelled-out quantities\n- totals\n- counts\n- collection claims', candidate.SYSTEM)
        self.assertIn('unless the exact quantity is explicitly supported by an admitted claim.', candidate.SYSTEM)
        self.assert_authored_expectation(CASES[1])
        self.assertEqual(CASES[1]['forbidden'], ['three documents show'])

    def test_case3_product_items_do_not_imply_complete_coverage(self):
        self.assertIn('Multiple evidence records do not imply:\n- multiple products\n- multiple configurations\n- all products\n- complete coverage\n- every case', candidate.SYSTEM)
        self.assert_authored_expectation(CASES[2])
        self.assertEqual(CASES[2]['forbidden'], ['all products'])

    def test_case4_explicit_admitted_quantity_retained(self):
        self.assertIn('unless the exact quantity is explicitly supported by an admitted claim.', candidate.SYSTEM)
        material = e.phase2.strict(candidate.messages()[1]['content'])
        claim = next(c for c in material['admitted_claims'] if c['claim_id'] == 'acura')
        self.assertEqual(claim['claim_text'], CASES[3]['admitted_claim'])
        self.assertIn('five-axis', claim['claim_text'])
        self.assertEqual(CASES[3]['allowed'], claim['claim_text'])
        self.assert_authored_expectation(CASES[3])

    def test_only_composition_rule_appended_to_frozen_a5(self):
        original = e.phase2.strict((candidate.A5 / 'prompt.json').read_bytes())
        updated = candidate.messages()
        self.assertEqual(updated, [dict(role='system', content=original[0]['content'] + candidate.COMPOSITION), original[1]])

    def test_a3_internal_boundary_and_a5_json_escaping_preserved(self):
        self.assertTrue(candidate.SYSTEM.startswith(candidate.base.SYSTEM))
        self.assertIn(candidate.base.base.BOUNDARY, candidate.SYSTEM)
        self.assertIn(candidate.base.JSON_ESCAPING, candidate.SYSTEM)
        self.assertIn(r'Escape all newline characters inside the article string as \n.', candidate.SYSTEM)
        self.assertEqual(candidate.messages()[1], candidate.base.messages()[1])

    def test_model_parameters_frozen(self):
        self.assertEqual(e.PARAMETERS, dict(model='deepseek-flash', temperature=0,
            thinking={'type': 'disabled'}, response_format={'type': 'json_object'}, max_tokens=3000))

    def test_historical_failure_and_ready_envelope_preserved(self):
        saved = e.phase2.strict((candidate.A5 / 'live-verification.json').read_bytes())
        self.assertEqual(saved['failure_code'], 'P7A5_EVIDENCE_UNSUPPORTED_NUMERIC')
        self.assertEqual(saved['first_failed_layer'], 3)
        self.assertEqual(saved['findings'][0]['excerpt'], 'Two synthetic configurations are documented.')
        value, ready = e.load_admitted()
        self.assertEqual(e.admission.require_ready(value, ready), ready)
        self.assertFalse(value.semantic_approved or value.production_authorized)


if __name__ == '__main__':
    unittest.main()
