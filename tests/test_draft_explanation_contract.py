from dataclasses import replace
import json
import unittest

from foreign_trade_geo_agent.core.draft_selection_contract import text_digest, selection_digest
from foreign_trade_geo_agent.workflows.draft_contract_v2 import inspect_offline_candidate
from tests.draft_v2_fixtures import fixture, explanation_fixture


class ExplanationContractTests(unittest.TestCase):
    def setUp(self):
        self.value, self.contract = fixture()
        self.raw, self.sidecar = explanation_fixture(self.contract)

    def check(self, sidecar=None, raw=None, contract=None):
        return inspect_offline_candidate(self.value, self.raw if raw is None else raw,
            contract or self.contract, sidecar or self.sidecar,
            current_snapshot_sha256=self.value.customer_evidence.snapshot_sha256)

    def test_twelve_structured_explanations_pending_only(self):
        check = self.check()
        self.assertEqual(check.errors, ())
        self.assertTrue(check.explanation_structure_valid)
        self.assertEqual(check.state, 'PENDING_SEMANTIC_REVIEW')
        self.assertFalse(check.production_authorized)
        self.assertFalse(check.semantic_approved)

    def test_versioned_sidecar_round_trip_and_strict_decode(self):
        from foreign_trade_geo_agent.storage.draft_selection_contract import encode_explanation_contract, decode_explanation_contract
        raw = encode_explanation_contract(self.sidecar)
        self.assertEqual(decode_explanation_contract(raw), self.sidecar)
        body = json.loads(raw)
        body['explanations'][0]['semantic_approved'] = True
        with self.assertRaises(ValueError):
            decode_explanation_contract(json.dumps(body))
        for raw in ('{}', '[]', '{"contract_version":1,"contract_version":2}', ' ' * 300000):
            with self.subTest(raw=raw[:30]), self.assertRaises(ValueError):
                decode_explanation_contract(raw)

    def test_each_part_required(self):
        for key in ('buyer_implication', 'non_applicability', 'verification_action'):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'EXPLANATION'):
                replace(self.sidecar.explanations[0], **{key: ' '})

    def test_unselected_premise(self):
        a = replace(self.sidecar.explanations[0], selected_fact_refs=('E2.F02',))
        check = self.check(replace(self.sidecar, explanations=(a, *self.sidecar.explanations[1:])))
        self.assertIn('EXPLANATION_FACT_NOT_SELECTED', check.errors)

    def test_claim_and_section_ids_are_bound(self):
        for key, value in (('explanation_claim_id', 'CL1'), ('section_id', 'S2')):
            a = replace(self.sidecar.explanations[0], **{key: value})
            check = self.check(replace(self.sidecar, explanations=(a, *self.sidecar.explanations[1:])))
            self.assertEqual(check.state, 'DETERMINISTICALLY_REJECTED')
            self.assertIn('EXPLANATION_CLAIM_BINDING', check.errors)

    def test_all_claim_premises_must_match_sidecar(self):
        a = replace(self.sidecar.explanations[0], selected_fact_refs=('E2.F01',))
        check = self.check(replace(self.sidecar, explanations=(a, *self.sidecar.explanations[1:])))
        self.assertIn('EXPLANATION_PREMISE_BINDING', check.errors)

    def test_all_hash_bindings(self):
        for key in ('candidate_sha256', 'selection_sha256', 'evidence_snapshot_sha256', 'plan_sha256'):
            with self.subTest(key=key):
                self.assertIn('EXPLANATION_HASH_BINDING', self.check(replace(self.sidecar, **{key: '0'*64})).errors)

    def test_missing_extra_duplicate_annotations(self):
        self.assertIn('EXPLANATION_COVERAGE', self.check(replace(self.sidecar,
            explanations=self.sidecar.explanations[1:])).errors)
        with self.assertRaisesRegex(ValueError, 'EXPLANATION'):
            replace(self.sidecar, explanations=(*self.sidecar.explanations, self.sidecar.explanations[0]))

    def test_text_hash_and_visible_body_binding(self):
        for update in ({'text_sha256': '0'*64}, {'buyer_implication': self.sidecar.explanations[0].buyer_implication + ' Different.'}):
            a = replace(self.sidecar.explanations[0], **update)
            self.assertIn('EXPLANATION_BODY_BINDING', self.check(replace(self.sidecar,
                explanations=(a, *self.sidecar.explanations[1:]))).errors)

    def test_keyword_labels_cannot_replace_structured_parts(self):
        with self.assertRaisesRegex(ValueError, 'EXPLANATION'):
            replace(self.sidecar.explanations[0], buyer_implication='buyer implication',
                non_applicability='non applicability', verification_action='verification action')

    def test_fixed_boundary_in_wrong_part_is_rejected(self):
        # Preserve text concatenation, native proposal and hashes; move the entire
        # non-applicability segment into implication. Boundary check must catch it.
        a = self.sidecar.explanations[0]
        words = a.verification_action.split()
        a = replace(a, buyer_implication=a.buyer_implication + ' ' + a.non_applicability,
                    non_applicability=' '.join(words[:12]), verification_action=' '.join(words[12:]))
        self.assertIn('EXPLANATION_BOUNDARY_PLACEMENT', self.check(replace(self.sidecar,
            explanations=(a, *self.sidecar.explanations[1:]))).errors)
