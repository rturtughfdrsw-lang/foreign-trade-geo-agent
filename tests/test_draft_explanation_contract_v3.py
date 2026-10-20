"""Isolated v3 procurement relations, never production admission."""
from dataclasses import replace
import json
import unittest

from tests.draft_explanation_v3_fixtures import fixture_v3, parse, rebind
from foreign_trade_geo_agent.core.draft_explanation_contract_v3 import (
    inspect_explanations_v3, decode_sidecar_v3, encode_sidecar_v3, render_parts,
)


class ExplanationV3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.value, cls.selection, cls.raw, cls.sidecar = fixture_v3()

    def check(self, sidecar=None, raw=None, spec=None):
        raw = self.raw if raw is None else raw
        return inspect_explanations_v3(self.sidecar if sidecar is None else sidecar, self.selection, raw,
            spec or parse(self.value, raw), self.value,
            current_snapshot_sha256=self.value.customer_evidence.snapshot_sha256)

    def change(self, **updates):
        a = replace(self.sidecar.explanations[0], **updates)
        return replace(self.sidecar, explanations=(a, *self.sidecar.explanations[1:]))

    def test_complete_procurement_chain_pass_pending_only(self):
        result = self.check()
        self.assertEqual(result.status, 'PASS')
        self.assertEqual(result.state, 'PENDING_SEMANTIC_REVIEW')
        self.assertFalse(result.production_authorized)
        self.assertFalse(result.semantic_approved)
        self.assertEqual(result.errors, ())

    def test_multiple_facts_support_one_explanation(self):
        self.assertGreater(len(self.sidecar.explanations[0].evidence_reference), 1)
        self.assertEqual(self.check().status, 'PASS')

    def test_unknown_boundary_is_unresolved_not_failure(self):
        a = self.sidecar.explanations[0]
        self.assertEqual(a.boundary_type, 'unknown')
        self.assertIn('unresolved', a.non_applicability)
        self.assertEqual(self.check().status, 'PASS')

    def test_limitation_action_without_decision_rejected(self):
        result = self.check(self.change(buyer_implication='Check the limits and request records.'))
        self.assertIn('V3_DECISION_REALIZATION', result.errors)

    def test_keyword_bag_does_not_supply_relations(self):
        a = self.sidecar.explanations[0]
        result = self.check(self.change(buyer_implication=
            'machine_shortlist buyer supplier fixture_layout unknown verify evidence because'))
        self.assertEqual(result.status, 'FAIL')
        self.assertIn('V3_DECISION_REALIZATION', result.errors)
        result = self.check(self.change(decision=replace(a.decision, rationale='')))
        self.assertIn('V3_RELATION_TEXT', result.errors)

    def test_verification_without_owner_rejected(self):
        self.assertIn('V3_VERIFICATION_ROLE', self.check(self.change(verification_owner='')).errors)

    def test_unknown_declared_as_failure_rejected(self):
        a = self.sidecar.explanations[0]
        self.assertIn('V3_BOUNDARY_TYPE', self.check(self.change(boundary_type='observed_failure')).errors)
        changed = replace(a, boundary_condition='The untested fixture failed clearance.')
        changed = replace(changed, **render_parts(changed, self.selection.sections[0]))
        raw, sidecar = rebind(self.raw, self.sidecar, changed)
        self.assertIn('V3_UNKNOWN_FALSE_DIAGNOSTIC', self.check(sidecar, raw).errors)

    def test_unselected_fact_rejected(self):
        self.assertIn('V3_FACT_NOT_SELECTED', self.check(self.change(selected_fact_refs=('E2.F02',))).errors)

    def test_candidate_hash_mismatch_rejected(self):
        self.assertIn('V3_HASH_BINDING', self.check(replace(self.sidecar, candidate_hash='0'*64)).errors)

    def test_all_context_hashes_bound(self):
        for key in ('selection_sha256', 'evidence_snapshot_sha256', 'plan_sha256'):
            with self.subTest(key=key):
                self.assertIn('V3_HASH_BINDING', self.check(replace(self.sidecar, **{key:'0'*64})).errors)

    def test_claim_section_and_body_hash_bound(self):
        for updates, code in (({'claim_id':'CL1'}, 'V3_CLAIM_BINDING'),
            ({'section_id':'S2'}, 'V3_CLAIM_BINDING'), ({'text_sha256':'0'*64}, 'V3_BODY_BINDING')):
            with self.subTest(updates=updates):
                self.assertIn(code, self.check(self.change(**updates)).errors)

    def test_source_quotes_and_complete_premises_bound(self):
        a = self.sidecar.explanations[0]
        refs = (replace(a.evidence_reference[0], source_quote='Invented evidence.'), *a.evidence_reference[1:])
        self.assertIn('V3_EVIDENCE_BINDING', self.check(self.change(evidence_reference=refs)).errors)
        self.assertIn('V3_PREMISE_BINDING', self.check(self.change(evidence_reference=a.evidence_reference[:1])).errors)

    def test_coverage_duplicates_and_extra_annotations_rejected(self):
        for annotations in (self.sidecar.explanations[1:], (*self.sidecar.explanations, self.sidecar.explanations[0])):
            with self.subTest(count=len(annotations)):
                self.assertEqual(self.check(replace(self.sidecar, explanations=annotations)).status, 'FAIL')

    def test_owner_artifact_purpose_must_be_visible(self):
        a = self.sidecar.explanations[0]
        for updates in ({'verification_artifact':'other record'}, {'verification_owner':'buyer'},
            {'verification':replace(a.verification, purpose='a different decision')}):
            with self.subTest(updates=updates):
                self.assertIn('V3_VERIFICATION_REALIZATION', self.check(self.change(**updates)).errors)

    def test_parsed_specification_cannot_be_swapped(self):
        body = json.loads(self.raw)
        body['draft']['sections'][0]['blocks'][0]['claims'][0]['text'] += ' Changed.'
        other = json.dumps(body)
        self.assertIn('V3_SPEC_BINDING', self.check(spec=parse(self.value, other)).errors)

    def test_native_rules_and_section_reservations_remain_prerequisites(self):
        body = json.loads(self.raw)
        body['draft']['sections'][0]['blocks'].pop()
        from foreign_trade_geo_agent.core.draft_selection_contract import canonical_json, text_digest
        raw = canonical_json(body)
        sidecar = replace(self.sidecar, candidate_hash=text_digest(raw))
        self.assertIn('V3_SECTION_RESERVATION', self.check(sidecar, raw).errors)

    def test_strict_codec_roundtrip(self):
        self.assertEqual(decode_sidecar_v3(encode_sidecar_v3(self.sidecar)), self.sidecar)

    def test_codec_rejects_unknown_fields_duplicates_nan_and_oversize(self):
        body = json.loads(encode_sidecar_v3(self.sidecar))
        body['semantic_approved'] = True
        bad = [json.dumps(body), '{}', '[]', '{"a":1,"a":2}', '{"a":NaN}', ' '*300001]
        for raw in bad:
            with self.subTest(raw=raw[:30]), self.assertRaisesRegex(ValueError, 'V3_'):
                decode_sidecar_v3(raw)

    def test_malformed_inputs_fail_closed_sanitized(self):
        for bad in (None, {}, [], 'secret-provider-response'):
            with self.subTest(bad=bad):
                result = self.check(bad if bad is not None else {})
                self.assertEqual(result.status, 'FAIL')
                self.assertNotIn('secret', str(result.errors))

    def test_replay_original_v2_remains_rejected(self):
        from tests.draft_explanation_v3_fixtures import replay_original
        result = replay_original()
        self.assertEqual(result['state'], 'REJECTED')
        self.assertEqual(result['original_parser_error'], 'PREFLIGHT_RESPONSE_INVALID')
        self.assertEqual(result['source_sha256_before'], result['source_sha256_after'])


if __name__ == '__main__':
    unittest.main()
