import asyncio
import unittest

from foreign_trade_geo_agent.core.change_plan import (
    ChangeOperationType,
    ChangePlanReport,
    ChangePlanStatus,
)
from foreign_trade_geo_agent.core.content_draft import (
    CONTENT_DRAFT_LIMITATIONS,
    MAX_DRAFTS,
    BulletListSpecification,
    ContentDraftInput,
    ContentDraftSpecification,
    ContentDraftStatus,
    ContentDraftType,
    DraftBlockKind,
    DraftClaimSpecification,
    DraftClaimSupportKind,
    DraftClaimType,
    DraftItem,
    NewResourceSectionSpecification,
    ParagraphSpecification,
    TableCellSpecification,
    finalize_draft_item,
    stable_content_draft_input_error,
)
from foreign_trade_geo_agent.core.content_opportunity import (
    ContentOpportunityActionCode,
    ContentOpportunityType,
)
from tests.test_change_plan_workflow import (
    common,
    expand,
    opportunity,
    opportunity_report,
    packet,
    page,
    point,
    run_one,
)


def _plan(raw, *, site=None, report=None):
    result, _ = asyncio.run(run_one(raw, site=site, report=report))
    return result


def _expand_site():
    return packet(
        page(
            "P1",
            body=(
                "Chemical compatibility, material selection, port size 3 inch, "
                "application, maintenance considerations, and AODD pump maintenance "
                "are observed topics. Maximum flow is 120 GPM."
            ),
        )
    )


def _expand_report():
    return opportunity_report(
        opportunity(action_codes=(ContentOpportunityActionCode.EXPAND_PAGE_SECTION,))
    )


def _claim(text, claim_type="GENERAL_TECHNICAL_CONTEXT", *, page_refs=(), source_refs=()):
    return DraftClaimSpecification(
        text, DraftClaimType(claim_type), tuple(page_refs), tuple(source_refs)
    )


def _paragraph(*claims):
    return ParagraphSpecification(DraftBlockKind.PARAGRAPH, tuple(claims))


def _finalize_expand(specification, *, site=None, report=None):
    site = site or _expand_site()
    report = report or _expand_report()
    plan = _plan(expand(), site=site, report=report)
    operation = plan.operations[0]
    opportunity = next(
        item
        for item in report.opportunities
        if item.recommendation_id == operation.opportunity_ref
    )
    return finalize_draft_item(1, specification, operation, opportunity, site, report)


class ContentDraftCoreModelTests(unittest.TestCase):
    def test_statuses_and_limits(self) -> None:
        self.assertEqual(MAX_DRAFTS, 8)
        self.assertEqual(ContentDraftStatus.INVALID_INPUT.value, "invalid_input")
        self.assertIn("never approved or published", CONTENT_DRAFT_LIMITATIONS[4])

    def test_finalize_expand_success(self) -> None:
        spec = ContentDraftSpecification(
            "C1",
            ContentDraftType.SECTION_DRAFT,
            blocks=(
                _paragraph(
                    _claim(
                        "Material selection and port size are observed topics.",
                        "OBSERVED_PRODUCT_FACT",
                        page_refs=("P1",),
                    )
                ),
            ),
        )
        draft, error = _finalize_expand(spec)
        self.assertIsNone(error)
        self.assertIsInstance(draft, DraftItem)
        self.assertEqual(draft.draft_id, "D1")
        self.assertEqual(
            draft.blocks[0].claims[0].support_kind,
            DraftClaimSupportKind.FIRST_PARTY_OBSERVED,
        )

    def test_observed_product_fact_requires_page(self) -> None:
        spec = ContentDraftSpecification(
            "C1",
            ContentDraftType.SECTION_DRAFT,
            blocks=(
                _paragraph(
                    _claim(
                        "Our pump uses stainless steel.",
                        "OBSERVED_PRODUCT_FACT",
                        source_refs=("S1",),
                    )
                ),
            ),
        )
        draft, error = _finalize_expand(spec)
        self.assertIsNone(draft)
        self.assertEqual(error, "FIRST_PARTY_FACT_WITHOUT_PAGE")

    def test_external_context_with_source_is_accepted(self) -> None:
        spec = ContentDraftSpecification(
            "C1",
            ContentDraftType.SECTION_DRAFT,
            blocks=(
                _paragraph(
                    _claim(
                        "Chemical compatibility is a common selection criterion.",
                        "GENERAL_TECHNICAL_CONTEXT",
                        source_refs=("S1",),
                    )
                ),
            ),
        )
        draft, error = _finalize_expand(spec)
        self.assertIsNone(error)
        self.assertEqual(
            draft.blocks[0].claims[0].support_kind,
            DraftClaimSupportKind.EXTERNAL_CONTEXT,
        )

    def test_mixed_context_requires_both_refs(self) -> None:
        spec = ContentDraftSpecification(
            "C1",
            ContentDraftType.SECTION_DRAFT,
            blocks=(
                _paragraph(
                    _claim(
                        "Port size and application guidance are documented.",
                        "COMPARATIVE_CONTEXT",
                        page_refs=("P1",),
                        source_refs=("S1",),
                    )
                ),
            ),
        )
        draft, error = _finalize_expand(spec)
        self.assertIsNone(error)
        self.assertEqual(
            draft.blocks[0].claims[0].support_kind,
            DraftClaimSupportKind.MIXED_CONTEXT,
        )

    def test_first_party_numeric_requires_exact_page_grounding(self) -> None:
        good = ContentDraftSpecification(
            "C1",
            ContentDraftType.SECTION_DRAFT,
            blocks=(
                _paragraph(
                    _claim(
                        "Maximum flow is 120 GPM.",
                        "OBSERVED_PRODUCT_FACT",
                        page_refs=("P1",),
                    )
                ),
            ),
        )
        draft, error = _finalize_expand(good)
        self.assertIsNone(error)

        unsupported = ContentDraftSpecification(
            "C1",
            ContentDraftType.SECTION_DRAFT,
            blocks=(
                _paragraph(
                    _claim(
                        "Maximum flow is 999 GPM.",
                        "OBSERVED_PRODUCT_FACT",
                        page_refs=("P1",),
                    )
                ),
            ),
        )
        _, error = _finalize_expand(unsupported)
        self.assertEqual(error, "NUMERIC_NOT_GROUNDED")

    def test_absence_and_promotional_claims_are_rejected(self) -> None:
        for text, category in (
            ("This page lacks technical documentation.", "UNSUPPORTED_ABSENCE_CLAIM"),
            ("We are the best pump supplier.", "UNSUPPORTED_PROMOTIONAL_CLAIM"),
        ):
            spec = ContentDraftSpecification(
                "C1",
                ContentDraftType.SECTION_DRAFT,
                blocks=(
                    _paragraph(
                        _claim(text, "OBSERVED_PRODUCT_FACT", page_refs=("P1",))
                    ),
                ),
            )
            draft, error = _finalize_expand(spec)
            self.assertIsNone(draft)
            self.assertEqual(error, category)

    def test_competitor_brand_mention_is_rejected(self) -> None:
        spec = ContentDraftSpecification(
            "C1",
            ContentDraftType.SECTION_DRAFT,
            blocks=(
                _paragraph(
                    _claim(
                        "Compared with Rival Pumps, this unit is compact.",
                        "COMPARATIVE_CONTEXT",
                        source_refs=("S1",),
                    )
                ),
            ),
        )
        draft, error = _finalize_expand(spec)
        self.assertIsNone(draft)
        self.assertEqual(error, "COMPETITOR_MENTION")

    def test_editorial_transition_with_fact_is_rejected(self) -> None:
        spec = ContentDraftSpecification(
            "C1",
            ContentDraftType.SECTION_DRAFT,
            blocks=(
                _paragraph(
                    _claim(
                        "Our maximum flow is 120 GPM.",
                        "EDITORIAL_TRANSITION",
                    )
                ),
            ),
        )
        draft, error = _finalize_expand(spec)
        self.assertIsNone(draft)
        self.assertEqual(error, "CLAIM_TYPE_CONTRACT")

    def test_evidence_outside_change_scope_rejected(self) -> None:
        site = packet(page("P1"), page("P2"))
        report = opportunity_report(
            opportunity(
                action_codes=(ContentOpportunityActionCode.EXPAND_PAGE_SECTION,),
                page_refs=("P1",),
            )
        )
        plan = _plan(expand(), site=site, report=report)
        operation = plan.operations[0]
        opp = next(item for item in report.opportunities)
        spec = ContentDraftSpecification(
            "C1",
            ContentDraftType.SECTION_DRAFT,
            blocks=(
                _paragraph(
                    _claim(
                        "Installation is documented.",
                        "OBSERVED_PRODUCT_FACT",
                        page_refs=("P2",),
                    )
                ),
            ),
        )
        draft, error = finalize_draft_item(1, spec, operation, opp, site, report)
        self.assertIsNone(draft)
        self.assertEqual(error, "EVIDENCE_OUTSIDE_CHANGE_SCOPE")

    def test_stable_input_rejects_forged_change(self) -> None:
        site = _expand_site()
        report = _expand_report()
        plan = _plan(expand(), site=site, report=report)
        valid = ContentDraftInput(site, report, plan)
        self.assertIsNone(stable_content_draft_input_error(valid))
        bad_report = ChangePlanReport(
            status=ChangePlanStatus.GENERATION_FAILED,
            operations=(),
            limitations=(),
            error=None,
        )
        bad = ContentDraftInput(site, report, bad_report)
        self.assertEqual(stable_content_draft_input_error(bad), "FIELD_CONTRACT")

    def test_structure_only_mapping(self) -> None:
        from foreign_trade_geo_agent.core.content_draft import (
            content_draft_requires_provider,
            content_draft_type_for,
        )

        self.assertEqual(
            content_draft_type_for(ChangeOperationType.EXPAND_SECTION),
            ContentDraftType.SECTION_DRAFT,
        )
        self.assertFalse(
            content_draft_requires_provider(ChangeOperationType.PROPOSE_SECTION_REORDER)
        )
        self.assertTrue(
            content_draft_requires_provider(ChangeOperationType.ADD_SECTION)
        )

    def _finalize_claim_with_page(self, body, text, **claim_kwargs):
        site = packet(page("P1", body=body))
        report = _expand_report()
        plan = _plan(expand(), site=site, report=report)
        op = plan.operations[0]
        opp = next(item for item in report.opportunities)
        spec = ContentDraftSpecification(
            "C1",
            ContentDraftType.SECTION_DRAFT,
            blocks=(_paragraph(_claim(text, **claim_kwargs)),),
        )
        return finalize_draft_item(1, spec, op, opp, site, report)

    def test_numeric_requires_unit_bound_grounding(self) -> None:
        draft, error = self._finalize_claim_with_page(
            "Maximum pressure is 10 bar.",
            "Maximum pressure is 10 bar.",
            claim_type="OBSERVED_PRODUCT_FACT",
            page_refs=("P1",),
        )
        self.assertIsNone(error)
        self.assertIsNotNone(draft)

        _, error = self._finalize_claim_with_page(
            "Maximum pressure is 10 mm.",
            "Maximum pressure is 10 bar.",
            claim_type="OBSERVED_PRODUCT_FACT",
            page_refs=("P1",),
        )
        self.assertEqual(error, "NUMERIC_NOT_GROUNDED")

    def test_numeric_flow_rate_unit_binding(self) -> None:
        _, error = self._finalize_claim_with_page(
            "Flow rate is 100 L/min.",
            "Flow rate is 100 L/min.",
            claim_type="OBSERVED_PRODUCT_FACT",
            page_refs=("P1",),
        )
        self.assertIsNone(error)

        _, error = self._finalize_claim_with_page(
            "Flow rate is 100 L/min.",
            "Flow rate is 100 mm.",
            claim_type="OBSERVED_PRODUCT_FACT",
            page_refs=("P1",),
        )
        self.assertEqual(error, "NUMERIC_NOT_GROUNDED")

    def test_numeric_percentage_decimal_fraction_hyphen(self) -> None:
        cases = (
            ("Efficiency is 50%.", "Efficiency is 50%."),
            ("Clearance is 3.5 mm.", "Clearance is 3.5 mm."),
            ('Port size is 1/2".', 'Port size is 1/2".'),
            ("Port size is 1-1/2.", "Port size is 1-1/2."),
        )
        for claim, body in cases:
            with self.subTest(claim=claim):
                _, error = self._finalize_claim_with_page(
                    body, claim, claim_type="OBSERVED_PRODUCT_FACT", page_refs=("P1",)
                )
                self.assertIsNone(error)

    def test_numeric_leading_digit_collision_rejected(self) -> None:
        accepts = (
            ("Maximum pressure is 10 bar.", "Maximum pressure is 10 bar."),
            ("Efficiency is 50%.", "Efficiency is 50%."),
            ('Port size is 1/2".', 'Port size is 1/2".'),
        )
        for claim, body in accepts:
            with self.subTest(claim=claim):
                _, error = self._finalize_claim_with_page(
                    body, claim, claim_type="OBSERVED_PRODUCT_FACT", page_refs=("P1",)
                )
                self.assertIsNone(error)

        rejects = (
            ("Maximum pressure is 10 bar.", "Maximum pressure is 110 bar."),
            ("Maximum pressure is 10 bar.", "Maximum pressure is 210 bar."),
            ("Efficiency is 50%.", "Efficiency is 150%."),
            ('Port size is 1/2".', 'Port size is 11/2".'),
            ("Flow rate is 100 L/min.", "Flow rate is 1100 L/min."),
        )
        for claim, body in rejects:
            with self.subTest(claim=claim, body=body):
                _, error = self._finalize_claim_with_page(
                    body, claim, claim_type="OBSERVED_PRODUCT_FACT", page_refs=("P1",)
                )
                self.assertEqual(error, "NUMERIC_NOT_GROUNDED")

    def test_bare_number_fails_closed(self) -> None:
        _, error = self._finalize_claim_with_page(
            "Maximum pressure is 10.",
            "Maximum pressure is 10.",
            claim_type="OBSERVED_PRODUCT_FACT",
            page_refs=("P1",),
        )
        self.assertEqual(error, "NUMERIC_NOT_GROUNDED")

    def test_numeric_decimal_adjacency_rejected(self) -> None:
        rejects = (
            ("Maximum pressure is 5 bar.", "Maximum pressure is 0.5 bar."),
            ("Maximum pressure is 5 bar.", "Maximum pressure is 1.5 bar."),
            ("Maximum pressure is 5 bar.", "Maximum pressure is 5.5 bar."),
            ("Efficiency is 5%.", "Efficiency is 0.5%."),
            ("Clearance is 2 inch.", "Clearance is 0.2 inch."),
            ("Port size is 1/2.", "Port size is 0.1/2."),
            ("Port size is 1/2.", "Port size is 1/2.5."),
        )
        for claim, body in rejects:
            with self.subTest(claim=claim, body=body):
                _, error = self._finalize_claim_with_page(
                    body, claim, claim_type="OBSERVED_PRODUCT_FACT", page_refs=("P1",)
                )
                self.assertEqual(error, "NUMERIC_NOT_GROUNDED")

        accepts = (
            ("Maximum pressure is 10 bar.", "Maximum pressure is 10 bar."),
            ("Port size is 1/2.", "Port size is 1/2."),
        )
        for claim, body in accepts:
            with self.subTest(claim=claim, body=body):
                _, error = self._finalize_claim_with_page(
                    body, claim, claim_type="OBSERVED_PRODUCT_FACT", page_refs=("P1",)
                )
                self.assertIsNone(error)

    def test_dj02_first_party_entity_requires_page(self) -> None:
        _, error = self._finalize_claim_with_page(
            "The DJ02 pump uses stainless steel.",
            "The DJ02 pump uses stainless steel.",
            claim_type="GENERAL_TECHNICAL_CONTEXT",
            source_refs=("S1",),
        )
        self.assertEqual(error, "FIRST_PARTY_FACT_WITHOUT_PAGE")

    def test_s_only_technical_number_general_context_allowed(self) -> None:
        _, error = self._finalize_claim_with_page(
            "Typical AODD pumps operate near 7 bar.",
            "Typical AODD pumps operate near 7 bar.",
            claim_type="GENERAL_TECHNICAL_CONTEXT",
            source_refs=("S1",),
        )
        self.assertIsNone(error)

    def test_competitor_brand_in_source_title_not_allowlisted(self) -> None:
        _, error = self._finalize_claim_with_page(
            "This unit is compact and reliable.",
            "Compared with Acme Pumps, this unit is compact.",
            claim_type="COMPARATIVE_CONTEXT",
            source_refs=("S1",),
        )
        self.assertEqual(error, "COMPETITOR_MENTION")

    def test_generic_technical_phrase_not_competitor(self) -> None:
        _, error = self._finalize_claim_with_page(
            "Chemical Compatibility is addressed on this page.",
            "Chemical Compatibility is addressed on this page.",
            claim_type="OBSERVED_PRODUCT_FACT",
            page_refs=("P1",),
        )
        self.assertIsNone(error)

    def test_canonical_duplicate_claim_rejected(self) -> None:
        spec = ContentDraftSpecification(
            "C1",
            ContentDraftType.SECTION_DRAFT,
            blocks=(
                _paragraph(
                    _claim(
                        "Chemical compatibility matters.",
                        "GENERAL_TECHNICAL_CONTEXT",
                        source_refs=("S1",),
                    ),
                    _claim(
                        "CHEMICAL COMPATIBILITY matters.",
                        "GENERAL_TECHNICAL_CONTEXT",
                        source_refs=("S1",),
                    ),
                ),
            ),
        )
        draft, error = _finalize_expand(spec)
        self.assertIsNone(draft)
        self.assertEqual(error, "DUPLICATE_CLAIM")

    def test_table_cell_numeric_wrong_unit_rejected(self) -> None:
        site = packet(
            page(
                "P1",
                body=(
                    "Material selection, port size 3 inch, thread 1/2 inch, "
                    "application, maintenance considerations."
                ),
            )
        )
        report = opportunity_report(
            opportunity(action_codes=(ContentOpportunityActionCode.ADD_COMPARISON_TABLE,))
        )
        raw = {
            **common("ADD_COMPARISON_TABLE", action="ADD_COMPARISON_TABLE"),
            "proposed_heading": "Pump Comparison",
            "column_headers": ["material selection", "port size"],
            "row_dimensions": ["application", "maintenance considerations"],
        }
        plan = _plan(raw, site=site, report=report)
        op = plan.operations[0]
        opp = next(item for item in report.opportunities)

        def cells(port_text):
            return (
                TableCellSpecification(
                    "application", "material selection", "chemical compatibility", ("P1",), ()
                ),
                TableCellSpecification(
                    "application", "port size", port_text, ("P1",), ()
                ),
                TableCellSpecification(
                    "maintenance considerations",
                    "material selection",
                    "material selection guidance",
                    ("P1",),
                    (),
                ),
                TableCellSpecification(
                    "maintenance considerations",
                    "port size",
                    "1/2 inch",
                    ("P1",),
                    (),
                ),
            )

        good = ContentDraftSpecification(
            "C1", ContentDraftType.COMPARISON_TABLE_DRAFT, cells=cells("3 inch")
        )
        _, error = finalize_draft_item(1, good, op, opp, site, report)
        self.assertIsNone(error)

        bad = ContentDraftSpecification(
            "C1", ContentDraftType.COMPARISON_TABLE_DRAFT, cells=cells("10 mm")
        )
        _, error = finalize_draft_item(1, bad, op, opp, site, report)
        self.assertEqual(error, "NUMERIC_NOT_GROUNDED")

    def test_new_resource_aggregate_claim_cap(self) -> None:
        site = packet(
            page(
                "P1",
                body="Chemical compatibility material selection port size application.",
            )
        )
        report = opportunity_report(
            opportunity(
                action_codes=(ContentOpportunityActionCode.CREATE_SUPPORTING_RESOURCE,),
                opportunity_type=ContentOpportunityType.NEW_SUPPORTING_CONTENT,
            )
        )
        raw = {
            **common(
                "CREATE_NEW_RESOURCE",
                action="CREATE_SUPPORTING_RESOURCE",
                target_page_ref=None,
                locator_kind="NEW_PAGE",
            ),
            "resource_purpose": "SUPPORTING_RESOURCE",
            "proposed_title": "Chemical Compatibility Guide",
            "outline_headings": ["Material Selection", "Application"],
            "content_points": [point("chemical compatibility")],
            "suggested_source_page_refs": ["P1"],
            "comparison_table_brief": None,
        }
        plan = _plan(raw, site=site, report=report)
        op = plan.operations[0]
        opp = next(item for item in report.opportunities)

        def general_claims(start, count):
            return tuple(
                DraftClaimSpecification(
                    f"Context item {number} is documented.",
                    DraftClaimType.GENERAL_TECHNICAL_CONTEXT,
                    (),
                    ("S1",),
                )
                for number in range(start, start + count)
            )

        def section(heading, start):
            claims = general_claims(start, 9)
            blocks = (
                ParagraphSpecification(DraftBlockKind.PARAGRAPH, claims[0:3]),
                ParagraphSpecification(DraftBlockKind.PARAGRAPH, claims[3:6]),
                ParagraphSpecification(DraftBlockKind.PARAGRAPH, claims[6:9]),
            )
            return NewResourceSectionSpecification(heading, blocks)

        spec = ContentDraftSpecification(
            "C1",
            ContentDraftType.NEW_RESOURCE_DRAFT,
            sections=(
                section("Material Selection", 1),
                section("Application", 10),
            ),
        )
        _, error = finalize_draft_item(1, spec, op, opp, site, report)
        self.assertEqual(error, "CLAIM_BUDGET")


if __name__ == "__main__":
    unittest.main()
