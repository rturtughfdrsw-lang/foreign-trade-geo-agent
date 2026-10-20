from dataclasses import replace
import unittest

from foreign_trade_geo_agent.core.draft_selection_contract import (
    validate_selection, budget_diagnostics, plan_digest, evidence_digest,
)
from tests.draft_v2_fixtures import fixture, change_section


class SelectionContractTests(unittest.TestCase):
    def setUp(self):
        self.value, self.contract = fixture()

    def validate(self, contract=None, value=None, snapshot=None):
        return validate_selection(contract or self.contract, value or self.value,
            current_snapshot_sha256=snapshot or self.value.customer_evidence.snapshot_sha256)

    def test_valid_selection(self):
        self.assertEqual(self.validate(), ('SOFT_DIRECT_FACTS_OVER_30',))

    def test_unknown_selected_fact(self):
        with self.assertRaisesRegex(ValueError, 'SELECTION'):
            self.validate(change_section(self.contract, selected_facts=self.contract.sections[0].selected_facts + ('E9.F99',)))

    def test_unknown_fact_even_if_added_to_optional(self):
        with self.assertRaisesRegex(ValueError, 'FACT_ROUTING'):
            self.validate(change_section(self.contract, optional_facts=('E9.F99',),
                selected_facts=self.contract.sections[0].selected_facts + ('E9.F99',)))

    def test_required_fact_missing(self):
        with self.assertRaisesRegex(ValueError, 'SELECTION'):
            self.validate(change_section(self.contract, selected_facts=self.contract.sections[0].selected_facts[1:]))

    def test_required_direct_must_be_selected(self):
        with self.assertRaisesRegex(ValueError, 'SELECTION'):
            self.validate(change_section(self.contract, required_direct_facts=('E2.F02',)))

    def test_cross_section_source(self):
        s = self.contract.sections[1]
        with self.assertRaisesRegex(ValueError, 'FACT_ROUTING'):
            self.validate(change_section(self.contract, 1, optional_facts=s.optional_facts + ('E5.F03',),
                selected_facts=s.selected_facts + ('E5.F03',)))

    def test_same_source_wrong_requirement(self):
        s = self.contract.sections[1]
        with self.assertRaisesRegex(ValueError, 'FACT_ROUTING'):
            self.validate(change_section(self.contract, 1, optional_facts=s.optional_facts + ('E3.F05',)))

    def test_section_source_equality(self):
        with self.assertRaisesRegex(ValueError, 'SECTION_BINDING'):
            self.validate(change_section(self.contract, required_sources=('E2',)))

    def test_requirement_coverage(self):
        s = self.contract.sections[5]
        refs = tuple(r for r in s.selected_facts if not r.startswith('E7.'))
        with self.assertRaisesRegex(ValueError, 'COVERAGE'):
            self.validate(change_section(self.contract, 5, required_facts=refs,
                selected_facts=refs, required_direct_facts=refs))

    def test_snapshot_binding(self):
        with self.assertRaisesRegex(ValueError, 'SNAPSHOT'):
            self.validate(snapshot='0' * 64)

    def test_plan_hash_binding(self):
        with self.assertRaisesRegex(ValueError, 'PLAN_HASH'):
            self.validate(replace(self.contract, plan_sha256='0' * 64))

    def test_actual_plan_is_hashed(self):
        value = replace(self.value, writing_brief=replace(self.value.writing_brief, goal='Changed goal'))
        self.assertNotEqual(plan_digest(value), plan_digest(self.value))
        with self.assertRaisesRegex(ValueError, 'PLAN_HASH'):
            self.validate(value=value)

    def test_evidence_bytes_cannot_reuse_snapshot(self):
        bundle = replace(self.value.customer_evidence, sources=(
            replace(self.value.customer_evidence.sources[0], source_locator='changed-location'),
            *self.value.customer_evidence.sources[1:]))
        self.assertNotEqual(evidence_digest(bundle), self.contract.evidence_sha256)
        with self.assertRaisesRegex(ValueError, 'EVIDENCE_HASH'):
            self.validate(value=replace(self.value, customer_evidence=bundle))

    def test_heading_question_order_bound(self):
        for updates in ({'heading': 'Different'}, {'question': 'Different?'}, {'section_id': 'S9'}):
            with self.subTest(updates=updates), self.assertRaisesRegex(ValueError, 'SECTION_BINDING'):
                self.validate(change_section(self.contract, **updates))

    def test_invalid_types_duplicates_and_versions_fail_closed(self):
        for updates in ({'claim_budget': True}, {'block_budget': 0}, {'explanation_budget': -1},
                        {'selected_facts': ['E2.F01']}, {'required_sources': ('E2', 'E2')}):
            with self.subTest(updates=updates), self.assertRaises(ValueError):
                self.validate(change_section(self.contract, **updates))
        with self.assertRaises(ValueError):
            replace(self.contract, contract_version='v1')

    def test_global_49_claim_budget_rejected(self):
        with self.assertRaisesRegex(ValueError, 'CLAIM_BUDGET'):
            self.validate(change_section(self.contract, claim_budget=12, direct_fact_budget=10))

    def test_global_25_block_budget_rejected(self):
        with self.assertRaisesRegex(ValueError, 'BLOCK_BUDGET'):
            self.validate(change_section(self.contract, block_budget=9))

    def test_reservations_cannot_exceed_claim_budget(self):
        with self.assertRaisesRegex(ValueError, 'RESERVATION'):
            change_section(self.contract, claim_budget=6)

    def test_required_claims_must_fit_block_capacity(self):
        with self.assertRaisesRegex(ValueError, 'RESERVATION'):
            change_section(self.contract, block_budget=1)

    def test_duplicate_required_direct_quote_across_sections_is_infeasible(self):
        s = self.contract.sections[3]
        with self.assertRaisesRegex(ValueError, 'DIRECT_DUPLICATE'):
            self.validate(change_section(self.contract, 3, required_direct_facts=s.required_facts))

    def test_soft_targets_are_only_diagnostics(self):
        self.assertEqual(budget_diagnostics(31, 11, 0), (
            'SOFT_DIRECT_FACTS_OVER_30', 'SOFT_EXPLANATIONS_UNDER_12', 'SOFT_CTA_NOT_ONE'))
        sections = tuple(replace(s, explanation_budget=1, cta_budget=0) for s in self.contract.sections)
        notes = self.validate(replace(self.contract, sections=sections))
        self.assertIn('SOFT_EXPLANATIONS_UNDER_12', notes)
        self.assertIn('SOFT_CTA_NOT_ONE', notes)

    def test_missing_or_incorrect_audit_reasons_rejected(self):
        with self.assertRaisesRegex(ValueError, 'AUDIT'):
            self.validate(replace(self.contract, fact_reasons=self.contract.fact_reasons[:-1]))
        reasons = (replace(self.contract.fact_reasons[0], selected_sections=()), *self.contract.fact_reasons[1:])
        with self.assertRaisesRegex(ValueError, 'AUDIT'):
            self.validate(replace(self.contract, fact_reasons=reasons))
