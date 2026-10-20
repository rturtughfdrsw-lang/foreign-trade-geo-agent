"""Characterize current gaps, without granting Draft authority or adding a route.

Low-level finalizer successes below are gap witnesses, not approved executions.
All material and authorization doubles are synthetic and confined to tests.
"""
import asyncio
from dataclasses import fields, replace
import unittest

from foreign_trade_geo_agent.adapters.evidence_review import (
    AuthenticatedEvidenceReviewLoader, draft_input_digest, freeze_excerpt_target,
    load_excerpt_target,
)
from foreign_trade_geo_agent.core import change_plan as cp, content_draft as cd
from foreign_trade_geo_agent.core import content_opportunity as co, evidence_sufficiency as es
from foreign_trade_geo_agent.evidence_review_composition import production_preflight
from foreign_trade_geo_agent.workflows.content_draft import ContentDraftWorkflow
from foreign_trade_geo_agent.workflows.evidence_sufficiency import EvidenceSufficiencyPreflight
from tests.evidence_review_fixtures import (
    NOW, SyntheticAuthority, record_for, review_bytes, synthetic_target,
)
from tests.test_evidence_sufficiency_preflight import NoWriter
from tests.test_first_party_excerpt_capacity import native_planning


class POnlyDraftGapAuditTests(unittest.TestCase):
    def setUp(self):
        self.target = synthetic_target(es)
        self.value = self.target.draft_input
        self.operation = self.value.change_plan_report.operations[0]
        self.opportunity = self.value.opportunity_report.opportunities[0]

    def finalize(self, texts, *, page_refs=None):
        refs = (self.target.scope.page_ref,) if page_refs is None else page_refs
        claims = tuple(cd.DraftClaimSpecification(
            text, cd.DraftClaimType.OBSERVED_PRODUCT_FACT, refs, (),
        ) for text in texts)
        specification = cd.ContentDraftSpecification(
            self.operation.change_id, cd.ContentDraftType.SECTION_DRAFT,
            blocks=tuple(cd.ParagraphSpecification(cd.DraftBlockKind.PARAGRAPH,
                         claims[n:n + 4]) for n in range(0, len(claims), 4)),
        )
        return cd.finalize_draft_item(1, specification, self.operation,
            self.opportunity, self.value.site_content, self.value.opportunity_report)

    def gate(self):
        authority = SyntheticAuthority(es, self.target)
        record = record_for(self.target, freeze_excerpt_target(self.target),
                            draft_input_digest(self.value))
        raw = review_bytes(record)
        result = EvidenceSufficiencyPreflight(
            review_loader=AuthenticatedEvidenceReviewLoader(authority),
            allow_synthetic=True,
        ).check(self.target, raw, authority.sign(raw), now=NOW)
        return result

    def test_exact_root_cause_is_missing_scope_then_source_required(self):
        self.assertIsNone(cp.validate_change_plan_input(cp.ChangePlanInput(
            self.value.site_content, self.value.opportunity_report,
            self.target.scope, self.target.task_id)))
        catalog = co.build_content_opportunity_evidence_catalog(self.value.site_content, ())
        self.assertEqual(co.finalized_content_opportunity_error(
            self.opportunity, 1, catalog, ()), "SOURCE_REFERENCE_REQUIRED")
        self.assertEqual(cp.validate_change_plan_input(cp.ChangePlanInput(
            self.value.site_content, self.value.opportunity_report)), "FIELD_CONTRACT")
        self.assertEqual(cd.stable_content_draft_input_error(self.value), "FIELD_CONTRACT")
        with self.assertRaisesRegex(ValueError, "FIELD_CONTRACT"):
            cd.build_content_draft_prompt(self.value, self.operation.change_id)

    def test_synthetic_green_is_offline_only_and_native_writer_zero(self):
        self.assertEqual(self.gate().status, es.EvidenceGateStatus.SYNTHETIC_GREEN)
        self.assertIn("no Draft generation", " ".join(self.target.output_constraints))
        writer = NoWriter()
        result = asyncio.run(ContentDraftWorkflow(writer).run(self.value))
        self.assertEqual((result.status, result.error, writer.calls),
                         (cd.ContentDraftStatus.INVALID_INPUT, "FIELD_CONTRACT", 0))
        self.assertEqual(result.drafts, ())

    def test_frozen_target_expresses_six_obligations_seven_spans_and_adjacent_o1(self):
        self.assertIsNone(es.excerpt_target_error(self.target))
        self.assertEqual(len(self.target.obligations), 6)
        self.assertEqual(len(self.target.scope.excerpts), 7)
        self.assertEqual(self.target.obligations[0].excerpt_indexes, (0, 1))
        first, second = self.target.scope.excerpts[:2]
        self.assertEqual((first.field, first.structured_index, first.end),
                         (second.field, second.structured_index, second.start))
        self.assertEqual(first.quote + second.quote, self.target.obligations[0].statement)
        raw = freeze_excerpt_target(self.target)
        reloaded = load_excerpt_target(raw)
        self.assertEqual(reloaded, self.target)
        self.assertEqual(freeze_excerpt_target(reloaded), raw)
        self.assertEqual(draft_input_digest(reloaded.draft_input), draft_input_digest(self.value))

    def test_complete_low_level_payload_has_no_obligation_span_or_context_proof(self):
        draft, error = self.finalize(tuple(o.statement for o in self.target.obligations))
        self.assertIsNone(error)
        claims = tuple(c for b in draft.blocks for c in b.claims)
        self.assertEqual(tuple(c.text for c in claims), tuple(o.statement for o in self.target.obligations))
        self.assertEqual({c.page_refs for c in claims}, {(self.target.scope.page_ref,)})
        self.assertFalse({"obligation_id", "span", "excerpt_indexes"} &
                         {f.name for f in fields(cd.DraftClaim)})
        self.assertNotIn(self.target.context, tuple(c.text for c in claims))
        self.assertNotIn(self.target.attribution, tuple(c.text for c in claims))
        self.assertTrue(draft.requires_human_review)

    def test_missing_five_obligations_is_accepted_by_generic_finalizer(self):
        draft, error = self.finalize((self.target.obligations[0].statement,))
        self.assertIsNone(error)
        self.assertEqual(len(draft.blocks[0].claims), 1)

    def test_o1_first_fragment_only_is_accepted_by_generic_finalizer(self):
        fragment = self.target.scope.excerpts[0].quote
        self.assertNotEqual(fragment, self.target.obligations[0].statement)
        draft, error = self.finalize((fragment,))
        self.assertIsNone(error)
        self.assertEqual(draft.blocks[0].claims[0].text, fragment)

    def test_reordered_obligations_are_accepted_by_generic_finalizer(self):
        texts = tuple(o.statement for o in reversed(self.target.obligations))
        draft, error = self.finalize(texts)
        self.assertIsNone(error)
        self.assertEqual(tuple(c.text for b in draft.blocks for c in b.claims), texts)

    def test_complete_quotes_plus_new_non_numeric_fact_are_accepted(self):
        extra = "Packing orientation determines weather protection."
        self.assertNotIn(extra, self.value.site_content.pages[0].body_text)
        texts = (*tuple(o.statement for o in self.target.obligations), extra)
        draft, error = self.finalize(texts)
        self.assertIsNone(error)
        self.assertEqual(tuple(c.text for b in draft.blocks for c in b.claims), texts)

    def test_duplicate_and_wrong_page_still_reject(self):
        text = self.target.obligations[0].statement
        for texts, refs, expected in (
            ((text, text), None, "DUPLICATE_CLAIM"),
            ((text,), ("P99",), "UNKNOWN_PAGE_REFERENCE"),
        ):
            with self.subTest(expected=expected):
                draft, error = self.finalize(texts, page_refs=refs)
                self.assertIsNone(draft)
                self.assertEqual(error, expected)

    def test_finalizer_normalizes_text_instead_of_preserving_verbatim_bytes(self):
        original = self.target.obligations[0].statement
        changed = original.replace(" ", "  ", 1)
        self.assertNotEqual(changed, original)
        draft, error = self.finalize((changed,))
        self.assertIsNone(error)
        self.assertEqual(draft.blocks[0].claims[0].text, original)

    def test_summarize_intent_can_pass_target_validation_but_not_native_draft(self):
        operation = replace(self.operation, content_points=tuple(
            replace(point, intent=cp.ContentPointIntent.SUMMARIZE)
            for point in self.operation.content_points))
        value = replace(self.value, change_plan_report=replace(
            self.value.change_plan_report, operations=(operation,)))
        self.assertIsNone(es.excerpt_target_error(replace(self.target, draft_input=value)))
        self.assertEqual(cd.stable_content_draft_input_error(value), "FIELD_CONTRACT")

    def test_explain_and_compare_remain_denied_by_scoped_native_planning(self):
        for intent in ("EXPLAIN", "COMPARE"):
            with self.subTest(intent=intent):
                def mutate(raw):
                    raw["opportunity_operations"]["R1"]["primary_operation"]["content_points"][0]["intent"] = intent
                _, plan, _, _ = native_planning(self.value.site_content, self.target.scope, mutate)
                self.assertEqual(plan.status, cp.ChangePlanStatus.INVALID_OUTPUT)
                self.assertEqual(plan.operations, ())
                if intent == "COMPARE":
                    self.assertEqual(plan.error, "COMPARISON_UNAVAILABLE")

    def test_input_replacement_changes_binding_and_rejects_existing_review(self):
        authority = SyntheticAuthority(es, self.target)
        raw = review_bytes(record_for(self.target, freeze_excerpt_target(self.target),
                                     draft_input_digest(self.value)))
        changed = replace(self.target, draft_input=replace(self.value, target_language="zh"))
        self.assertNotEqual(draft_input_digest(changed.draft_input), draft_input_digest(self.value))
        result = EvidenceSufficiencyPreflight(
            review_loader=AuthenticatedEvidenceReviewLoader(authority), allow_synthetic=True,
        ).check(changed, raw, authority.sign(raw), now=NOW)
        self.assertEqual(result.status, es.EvidenceGateStatus.REJECTED)

    def test_production_without_root_rejects_even_synthetic_green(self):
        result = self.gate()
        self.assertEqual(result.status, es.EvidenceGateStatus.SYNTHETIC_GREEN)
        self.assertEqual(production_preflight().check(self.target, result.review_id).status,
                         es.EvidenceGateStatus.REJECTED)
