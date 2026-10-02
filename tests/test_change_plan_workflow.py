import asyncio
import json
import unittest
from dataclasses import replace
from unittest.mock import patch

from foreign_trade_geo_agent.core.change_plan import (
    MAX_OPERATIONS,
    MAX_CHANGE_PLAN_TIMEOUT_SECONDS,
    ChangeOperationType,
    ChangePlanGeneration,
    ChangePlanGenerationStatus,
    ChangePlanInput,
    ChangePlanStatus,
    ContentPointIntent,
    NewResourcePurpose,
    ObservedHeadingKind,
    SectionLocatorKind,
    SectionPurpose,
    build_change_plan_prompt,
    stable_change_plan_input_shape_error,
    validate_change_plan_input,
)
from foreign_trade_geo_agent.core.content_opportunity import (
    CONTENT_OPPORTUNITY_LIMITATIONS,
    ContentOpportunity,
    ContentOpportunityActionCode,
    ContentOpportunityPage,
    ContentOpportunityPriority,
    ContentOpportunityReport,
    ContentOpportunitySource,
    ContentOpportunitySourceMaterial,
    ContentOpportunityStatus,
    ContentOpportunityType,
    ContentOpportunitySpecification,
    finalize_content_opportunity,
)
from foreign_trade_geo_agent.core.crawling import CrawlStopReason
from foreign_trade_geo_agent.core.audit import (
    AuditEvidence,
    AuditEvidenceCategory,
    AuditEvidenceOutcome,
)
from foreign_trade_geo_agent.core.optimization import NumberedAuditEvidence
from foreign_trade_geo_agent.core.extraction import (
    PageExtractionStatus,
    StructuredContentBlock,
    StructuredContentKind,
)
from foreign_trade_geo_agent.core.research import ResearchEvidenceClassification
from foreign_trade_geo_agent.core.site_content import SiteContentEvidence, SiteContentPacket
from foreign_trade_geo_agent.workflows.change_plan import ChangePlanWorkflow


CLASSIFICATIONS = (
    ResearchEvidenceClassification.EXTERNAL_RESEARCH_CONTEXT,
    ResearchEvidenceClassification.UNVERIFIED_SEARCH_RESULT,
)


def page(
    evidence_id: str = "P1",
    *,
    url: str | None = None,
    h1: tuple[str, ...] = ("Industrial Pumps",),
    h2: tuple[str, ...] = ("Chemical Compatibility", "Maintenance"),
    structured: tuple[StructuredContentBlock, ...] = (),
    body: str = (
        "Chemical compatibility, material selection, port size, application, "
        "maintenance considerations, and pump performance are observed topics."
    ),
) -> SiteContentEvidence:
    return SiteContentEvidence(
        evidence_id=evidence_id,
        final_url=url or f"https://example.com/{evidence_id.casefold()}",
        title="Industrial Pumps",
        description="Pump application guide",
        h1=h1,
        h2=h2,
        body_text=body,
        structured_content=structured,
        extraction_status=PageExtractionStatus.SUCCESS,
        extraction_failure_kind=None,
        structured_content_truncated=False,
        content_truncated=False,
    )


def packet(*pages: SiteContentEvidence) -> SiteContentPacket:
    selected = pages or (page(), page("P2", h1=("Pump Selection",)))
    return SiteContentPacket(
        pages=selected,
        source_page_count=len(selected),
        crawl_stop_reason=CrawlStopReason.COMPLETED,
        crawl_budget_exhausted=False,
        truncated=False,
    )


def opportunity(
    recommendation_id: str = "R1",
    *,
    action_codes: tuple[ContentOpportunityActionCode, ...] = (
        ContentOpportunityActionCode.EXPAND_PAGE_SECTION,
    ),
    page_refs: tuple[str, ...] = ("P1",),
    source_refs: tuple[str, ...] = ("S1",),
    opportunity_type: ContentOpportunityType | None = None,
    audit_refs: tuple[str, ...] = (),
) -> ContentOpportunity:
    if opportunity_type is None:
        if ContentOpportunityActionCode.REORGANIZE_PAGE_SECTIONS in action_codes:
            opportunity_type = ContentOpportunityType.REORGANIZE_OBSERVED_CONTENT
        elif any(
            action in action_codes
            for action in (
                ContentOpportunityActionCode.CREATE_SUPPORTING_RESOURCE,
                ContentOpportunityActionCode.ADD_BUYER_GUIDANCE,
                ContentOpportunityActionCode.ADD_TECHNICAL_DOCUMENTATION,
            )
        ):
            opportunity_type = ContentOpportunityType.NEW_SUPPORTING_CONTENT
        else:
            opportunity_type = ContentOpportunityType.EXPAND_OBSERVED_CONTENT
    number = int(recommendation_id[1:]) if recommendation_id.startswith("R") and recommendation_id[1:].isdigit() else 1
    finalized = finalize_content_opportunity(
        number,
        ContentOpportunitySpecification(
            opportunity_type=opportunity_type,
            priority=ContentOpportunityPriority.HIGH,
            topic="chemical compatibility",
            action_codes=action_codes,
            page_refs=page_refs,
            source_refs=source_refs,
        ),
    )
    return replace(
        finalized,
        recommendation_id=recommendation_id,
        audit_refs=audit_refs,
    )


def opportunity_report(
    *opportunities: ContentOpportunity,
    source_text: str = (
        "Chemical compatibility material selection port size application maintenance "
        "considerations pump comparison buyer guidance technical documentation."
    ),
    audit_evidence: tuple[NumberedAuditEvidence, ...] = (),
) -> ContentOpportunityReport:
    items = opportunities or (opportunity(),)
    source_ids = tuple(dict.fromkeys(ref for item in items for ref in item.source_refs)) or ("S1",)
    materials = tuple(
        ContentOpportunitySourceMaterial(
            source_id=source_id,
            title="Chemical compatibility pump guide",
            content=" ".join(source_text.split()),
            content_truncated=False,
        )
        for source_id in source_ids
    )
    sources = tuple(
        ContentOpportunitySource(
            source_id=source_id,
            title="Chemical compatibility pump guide",
            url=f"https://source.example/{source_id.casefold()}",
            classifications=CLASSIFICATIONS,
        )
        for source_id in source_ids
    )
    page_ids = tuple(dict.fromkeys(ref for item in items for ref in item.page_refs))
    return ContentOpportunityReport(
        status=ContentOpportunityStatus.SUCCESS,
        opportunities=items,
        pages=tuple(
            ContentOpportunityPage(ref, f"https://example.com/{ref.casefold()}", "Pump")
            for ref in page_ids
        ),
        sources=sources,
        limitations=CONTENT_OPPORTUNITY_LIMITATIONS,
        error=None,
        source_materials=materials,
        audit_evidence=audit_evidence,
    )


def generated(operations: list[dict[str, object]]) -> ChangePlanGeneration:
    return ChangePlanGeneration(
        provider="fake",
        model="fake",
        status=ChangePlanGenerationStatus.SUCCESS,
        text=json.dumps({"operations": operations}, ensure_ascii=False),
        error=None,
    )


def common(
    operation_type: str,
    *,
    action: str,
    page_refs: list[str] | None = None,
    source_refs: list[str] | None = None,
    target_page_ref: str | None = "P1",
    locator_kind: str = "PAGE_LEVEL",
    target_heading: str | None = None,
) -> dict[str, object]:
    return {
        "opportunity_ref": "R1",
        "source_action_code": action,
        "operation_type": operation_type,
        "page_refs": ["P1"] if page_refs is None else page_refs,
        "source_refs": ["S1"] if source_refs is None else source_refs,
        "target_page_ref": target_page_ref,
        "locator_kind": locator_kind,
        "target_heading": target_heading,
    }


def point(subject: str = "chemical compatibility", intent: str = "EXPLAIN") -> dict[str, str]:
    return {"intent": intent, "subject": subject}


def expand(**overrides: object) -> dict[str, object]:
    result = {
        **common("EXPAND_SECTION", action="EXPAND_PAGE_SECTION"),
        "content_points": [point()],
    }
    result.update(overrides)
    return result


class FakeWriter:
    def __init__(self, response: ChangePlanGeneration) -> None:
        self.response = response
        self.prompts = []

    async def write_change_plan(self, prompt):
        self.prompts.append(prompt)
        return self.response


class RaisingWriter:
    def __init__(self) -> None:
        self.calls = 0

    async def write_change_plan(self, prompt):
        self.calls += 1
        raise RuntimeError("secret provider output")


class SlowWriter:
    async def write_change_plan(self, prompt):
        await asyncio.sleep(0.1)
        return generated([])


class TimeoutRaisingWriter:
    def __init__(self) -> None:
        self.calls = 0

    async def write_change_plan(self, prompt):
        self.calls += 1
        raise TimeoutError("provider-internal timeout")


async def run_one(raw: dict[str, object], *, site=None, report=None):
    writer = FakeWriter(generated([raw]))
    result = await ChangePlanWorkflow(writer).run(site or packet(), report or opportunity_report())
    return result, writer


class ChangePlanWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_operation_deterministically_inherits_audit_provenance_from_r(self) -> None:
        evidence = NumberedAuditEvidence(
            "A1",
            AuditEvidence(
                AuditEvidenceCategory.META,
                "meta.title.present",
                False,
                AuditEvidenceOutcome.ABSENT,
                "meta.title.present",
            ),
        )
        report = opportunity_report(
            opportunity(audit_refs=("A1",)), audit_evidence=(evidence,)
        )

        result, writer = await run_one(expand(), report=report)

        self.assertEqual(result.status, ChangePlanStatus.SUCCESS)
        self.assertEqual(result.operations[0].audit_refs, ("A1",))
        material = json.loads(writer.prompts[0].material_json())
        self.assertEqual(material["opportunities"][0]["audit_refs"], ["A1"])

    async def test_success_report_has_fixed_limitations_and_no_approval_state(self) -> None:
        from foreign_trade_geo_agent.core.change_plan import CHANGE_PLAN_LIMITATIONS

        result, _ = await run_one(expand())
        self.assertEqual(result.limitations, CHANGE_PLAN_LIMITATIONS)
        self.assertTrue(result.requires_human_review)
        for forbidden in ("approved", "reviewed", "applied", "approved_for_publish"):
            self.assertFalse(hasattr(result, forbidden))

    async def test_minimal_expand_success_and_deterministic_fields(self) -> None:
        result, writer = await run_one(expand())
        self.assertEqual(result.status, ChangePlanStatus.SUCCESS)
        self.assertEqual(len(writer.prompts), 1)
        operation = result.operations[0]
        self.assertEqual(operation.change_id, "C1")
        self.assertEqual(operation.operation_type, ChangeOperationType.EXPAND_SECTION)
        self.assertEqual(operation.locator.locator_kind, SectionLocatorKind.PAGE_LEVEL)
        self.assertTrue(operation.requires_human_review)
        self.assertEqual(operation.content_points[0].intent, ContentPointIntent.EXPLAIN)

    async def test_exact_observed_h1_h2_and_structured_heading_are_derived(self) -> None:
        structured = StructuredContentBlock(
            StructuredContentKind.SECTION,
            heading="Installation Notes",
            text="Installation notes describe chemical compatibility.",
        )
        site = packet(page(structured=(structured,)))
        cases = (
            ("Industrial Pumps", ObservedHeadingKind.H1),
            ("Chemical Compatibility", ObservedHeadingKind.H2),
            ("Installation Notes", ObservedHeadingKind.STRUCTURED_HEADING),
        )
        for heading, expected in cases:
            with self.subTest(heading=heading):
                raw = expand(
                    locator_kind="EXACT_OBSERVED_HEADING",
                    target_heading=heading,
                )
                result, _ = await run_one(raw, site=site)
                self.assertEqual(result.status, ChangePlanStatus.SUCCESS)
                self.assertEqual(result.operations[0].locator.observed_heading_kind, expected)
                self.assertTrue(result.operations[0].locator.observed_context)

    async def test_invented_heading_and_provider_locator_metadata_are_rejected(self) -> None:
        invented = expand(
            locator_kind="EXACT_OBSERVED_HEADING", target_heading="Invented"
        )
        self_reported = {
            **expand(),
            "observed_heading_kind": "H2",
            "observed_context": "provider text",
        }
        occurrence = {**expand(), "occurrence_index": 1}
        for raw, category in (
            (invented, "TARGET_LOCATOR_INVALID"),
            (self_reported, "FIELD_CONTRACT"),
            (occurrence, "FIELD_CONTRACT"),
        ):
            with self.subTest(raw=raw):
                result, _ = await run_one(raw)
                self.assertEqual(result.status, ChangePlanStatus.INVALID_OUTPUT)
                self.assertEqual(result.error, category)

    async def test_ambiguous_heading_namespace_becomes_semantic_only(self) -> None:
        structured = StructuredContentBlock(
            StructuredContentKind.SECTION,
            heading="Chemical Compatibility",
            text="Chemical compatibility context.",
        )
        raw = expand(
            locator_kind="EXACT_OBSERVED_HEADING",
            target_heading="Chemical Compatibility",
        )
        result, _ = await run_one(raw, site=packet(page(structured=(structured,))))
        self.assertEqual(result.status, ChangePlanStatus.SUCCESS)
        self.assertEqual(
            result.operations[0].locator.observed_heading_kind,
            ObservedHeadingKind.SEMANTIC_ONLY,
        )

    async def test_expand_requires_p_s_compatible_action_and_grounded_points(self) -> None:
        cases = (
            (expand(page_refs=[], target_page_ref=None), "UNKNOWN_PAGE_REFERENCE"),
            (expand(source_refs=[]), "UNKNOWN_SOURCE_REFERENCE"),
            (expand(source_action_code="ADD_INTERNAL_LINK"), "OPERATION_NOT_ALLOWED"),
            (expand(content_points=[point("quantum flux")]), "CONTENT_NOT_GROUNDED"),
        )
        for raw, category in cases:
            with self.subTest(category=category):
                result, _ = await run_one(raw)
                self.assertEqual(result.status, ChangePlanStatus.INVALID_OUTPUT)
                self.assertEqual(result.error, category)

    async def test_reorder_validates_same_page_observed_headings(self) -> None:
        raw = {
            **common("PROPOSE_SECTION_REORDER", action="REORGANIZE_PAGE_SECTIONS"),
            "ordered_headings": ["Chemical Compatibility", "Maintenance"],
        }
        report = opportunity_report(
            opportunity(action_codes=(ContentOpportunityActionCode.REORGANIZE_PAGE_SECTIONS,))
        )
        result, _ = await run_one(raw, report=report)
        self.assertEqual(result.status, ChangePlanStatus.SUCCESS)
        self.assertEqual(result.operations[0].ordered_headings, ("Chemical Compatibility", "Maintenance"))
        self.assertFalse(result.operations[0].complete_page_order)

        for changed in (
            {**raw, "ordered_headings": ["Chemical Compatibility", "Invented"]},
            {**raw, "ordered_headings": ["Chemical Compatibility"]},
            {**raw, "complete_page_order": True},
        ):
            rejected, _ = await run_one(changed, report=report)
            self.assertEqual(rejected.status, ChangePlanStatus.INVALID_OUTPUT)

    async def test_reorder_rejects_heading_observed_only_on_another_page(self) -> None:
        site = packet(
            page("P1", h2=("Chemical Compatibility", "Maintenance")),
            page("P2", h2=("Installation",)),
        )
        report = opportunity_report(
            opportunity(
                action_codes=(ContentOpportunityActionCode.REORGANIZE_PAGE_SECTIONS,),
                page_refs=("P1", "P2"),
            )
        )
        raw = {
            **common("PROPOSE_SECTION_REORDER", action="REORGANIZE_PAGE_SECTIONS"),
            "ordered_headings": ["Chemical Compatibility", "Installation"],
        }
        result, _ = await run_one(raw, site=site, report=report)
        self.assertEqual(result.error, "TARGET_LOCATOR_INVALID")

    async def test_add_section_supports_only_two_purposes_on_existing_page(self) -> None:
        base_report = opportunity_report(
            opportunity(action_codes=(ContentOpportunityActionCode.ADD_BUYER_GUIDANCE,))
        )
        for purpose, action in (
            ("BUYER_GUIDANCE", ContentOpportunityActionCode.ADD_BUYER_GUIDANCE),
            ("TECHNICAL_DOCUMENTATION", ContentOpportunityActionCode.ADD_TECHNICAL_DOCUMENTATION),
        ):
            report = opportunity_report(opportunity(action_codes=(action,)))
            raw = {
                **common("ADD_SECTION", action=action.value),
                "section_purpose": purpose,
                "proposed_heading": "Chemical Compatibility Guide",
                "content_points": [point("chemical compatibility")],
            }
            result, _ = await run_one(raw, report=report)
            self.assertEqual(result.status, ChangePlanStatus.SUCCESS)
            self.assertEqual(result.operations[0].section_purpose, SectionPurpose(purpose))
            self.assertEqual(result.operations[0].proposed_heading, "Chemical Compatibility Guide")

        bad = {
            **common("ADD_SECTION", action="ADD_BUYER_GUIDANCE"),
            "section_purpose": "BUYER_GUIDANCE",
            "proposed_heading": "Quantum Flux Guide",
            "content_points": [point()],
        }
        rejected, _ = await run_one(bad, report=base_report)
        self.assertEqual(rejected.error, "CONTENT_NOT_GROUNDED")

    async def test_add_section_heading_must_be_new_to_target_page(self) -> None:
        report = opportunity_report(
            opportunity(action_codes=(ContentOpportunityActionCode.ADD_BUYER_GUIDANCE,))
        )
        base = {
            **common("ADD_SECTION", action="ADD_BUYER_GUIDANCE"),
            "section_purpose": "BUYER_GUIDANCE",
            "content_points": [point("chemical compatibility")],
        }
        collision, _ = await run_one(
            {**base, "proposed_heading": "chemical compatibility"},
            report=report,
        )
        novel, _ = await run_one(
            {**base, "proposed_heading": "Chemical Compatibility Guide"},
            report=report,
        )
        self.assertEqual(collision.error, "TARGET_LOCATOR_INVALID")
        self.assertEqual(novel.status, ChangePlanStatus.SUCCESS)

    async def test_image_alt_heading_is_hidden_from_locator_and_reorder(self) -> None:
        hidden = StructuredContentBlock(
            StructuredContentKind.IMAGE_ALT,
            heading="Hidden Pump Diagram",
            text="chemical compatibility",
        )
        site = packet(page(h2=("Chemical Compatibility", "Maintenance"), structured=(hidden,)))
        expand_hidden = expand(
            locator_kind="EXACT_OBSERVED_HEADING",
            target_heading="Hidden Pump Diagram",
        )
        hidden_result, hidden_writer = await run_one(expand_hidden, site=site)
        self.assertEqual(hidden_result.error, "TARGET_LOCATOR_INVALID")
        material = hidden_writer.prompts[0].material_json()
        self.assertNotIn("Hidden Pump Diagram", material)
        self.assertIn("Chemical Compatibility", material)

        report = opportunity_report(
            opportunity(action_codes=(ContentOpportunityActionCode.REORGANIZE_PAGE_SECTIONS,))
        )
        reorder = {
            **common("PROPOSE_SECTION_REORDER", action="REORGANIZE_PAGE_SECTIONS"),
            "ordered_headings": ["Chemical Compatibility", "Hidden Pump Diagram"],
        }
        reorder_result, _ = await run_one(reorder, site=site, report=report)
        self.assertEqual(reorder_result.error, "TARGET_LOCATOR_INVALID")

        visible = {
            **reorder,
            "ordered_headings": ["Chemical Compatibility", "Maintenance"],
        }
        visible_result, _ = await run_one(visible, site=site, report=report)
        self.assertEqual(visible_result.status, ChangePlanStatus.SUCCESS)

    async def test_comparison_table_contains_only_grounded_brief(self) -> None:
        raw = {
            **common("ADD_COMPARISON_TABLE", action="ADD_COMPARISON_TABLE"),
            "proposed_heading": "Pump Comparison",
            "column_headers": ["material selection", "port size"],
            "row_dimensions": ["application", "maintenance considerations"],
        }
        report = opportunity_report(
            opportunity(action_codes=(ContentOpportunityActionCode.ADD_COMPARISON_TABLE,))
        )
        result, _ = await run_one(raw, report=report)
        self.assertEqual(result.status, ChangePlanStatus.SUCCESS)
        table = result.operations[0].comparison_table_spec
        self.assertEqual(table.column_headers, ("material selection", "port size"))
        self.assertEqual(table.row_dimensions, ("application", "maintenance considerations"))

        invalids = (
            {**raw, "column_headers": ["a", "b", "c", "d", "e", "f"]},
            {**raw, "row_dimensions": ["application"] * 7},
            {**raw, "cell_values": [["42 PSI"]]},
            {**raw, "row_dimensions": ["quantum flux"]},
        )
        for changed in invalids:
            rejected, _ = await run_one(changed, report=report)
            self.assertEqual(rejected.status, ChangePlanStatus.INVALID_OUTPUT)

    async def test_internal_link_is_observed_to_observed_and_urls_are_derived(self) -> None:
        raw = {
            **common(
                "ADD_INTERNAL_LINK",
                action="ADD_INTERNAL_LINK",
                page_refs=["P1", "P2"],
                target_page_ref="P1",
            ),
            "source_page_ref": "P1",
            "target_page_ref": "P2",
            "anchor_intent": "chemical compatibility",
        }
        report = opportunity_report(
            opportunity(
                action_codes=(ContentOpportunityActionCode.ADD_INTERNAL_LINK,),
                page_refs=("P1", "P2"),
            )
        )
        site = packet(
            page("P1", url="https://example.com/source"),
            page("P2", url="https://example.com/target"),
        )
        result, _ = await run_one(raw, site=site, report=report)
        self.assertEqual(result.status, ChangePlanStatus.SUCCESS)
        link = result.operations[0].internal_link_spec
        self.assertEqual(link.source_url, "https://example.com/source")
        self.assertEqual(link.target_url, "https://example.com/target")

        invalids = (
            {**raw, "target_page_ref": "P1"},
            {**raw, "source_page_ref": "P9"},
            {**raw, "target_page_ref": "P9"},
            {**raw, "source_url": "https://evil.example"},
            {**raw, "anchor_text": "final anchor"},
        )
        for changed in invalids:
            rejected, _ = await run_one(changed, site=site, report=report)
            self.assertEqual(rejected.status, ChangePlanStatus.INVALID_OUTPUT)
        same_page, _ = await run_one(
            {**raw, "target_page_ref": "P1"}, site=site, report=report
        )
        self.assertEqual(same_page.error, "INTERNAL_LINK_INVALID")

    async def test_cross_origin_site_packet_fails_closed_before_internal_link_generation(self) -> None:
        raw = {
            **common(
                "ADD_INTERNAL_LINK",
                action="ADD_INTERNAL_LINK",
                page_refs=["P1", "P2"],
                target_page_ref="P1",
            ),
            "source_page_ref": "P1",
            "target_page_ref": "P2",
            "anchor_intent": "chemical compatibility",
        }
        report = opportunity_report(
            opportunity(
                action_codes=(ContentOpportunityActionCode.ADD_INTERNAL_LINK,),
                page_refs=("P1", "P2"),
            )
        )
        for target_url in (
            "https://evil.example/target",
            "http://example.com/target",
            "https://example.com:444/target",
        ):
            with self.subTest(target_url=target_url):
                writer = FakeWriter(generated([raw]))
                result = await ChangePlanWorkflow(writer).run(
                    packet(
                        page("P1", url="https://example.com/source"),
                        page("P2", url=target_url),
                    ),
                    report,
                )
                self.assertEqual(result.status, ChangePlanStatus.INVALID_INPUT)
                self.assertEqual(result.error, "FIELD_CONTRACT")
                self.assertEqual(writer.prompts, [])

    def test_cross_origin_internal_link_core_validator_uses_internal_link_category(self) -> None:
        raw = {
            **common(
                "ADD_INTERNAL_LINK",
                action="ADD_INTERNAL_LINK",
                page_refs=["P1", "P2"],
                target_page_ref="P1",
            ),
            "source_page_ref": "P1",
            "target_page_ref": "P2",
            "anchor_intent": "chemical compatibility",
        }
        report = opportunity_report(
            opportunity(
                action_codes=(ContentOpportunityActionCode.ADD_INTERNAL_LINK,),
                page_refs=("P1", "P2"),
            )
        )
        prompt = build_change_plan_prompt(
            ChangePlanInput(
                packet(
                    page("P1", url="https://example.com/source"),
                    page("P2", url="https://evil.example/target"),
                ),
                report,
            )
        )
        workflow = ChangePlanWorkflow(FakeWriter(generated([])))
        operations, error = workflow._parse_validate_finalize(
            generated([raw]).text,
            prompt,
        )
        self.assertIsNone(operations)
        self.assertEqual(error, "INTERNAL_LINK_INVALID")

    async def test_default_and_explicit_effective_ports_share_origin(self) -> None:
        raw = {
            **common(
                "ADD_INTERNAL_LINK",
                action="ADD_INTERNAL_LINK",
                page_refs=["P1", "P2"],
                target_page_ref="P1",
            ),
            "source_page_ref": "P1",
            "target_page_ref": "P2",
            "anchor_intent": "chemical compatibility",
        }
        report = opportunity_report(
            opportunity(
                action_codes=(ContentOpportunityActionCode.ADD_INTERNAL_LINK,),
                page_refs=("P1", "P2"),
            )
        )
        result, _ = await run_one(
            raw,
            site=packet(
                page("P1", url="https://EXAMPLE.com/source"),
                page("P2", url="https://example.com:443/target"),
            ),
            report=report,
        )
        self.assertEqual(result.status, ChangePlanStatus.SUCCESS)

    async def test_new_resource_can_omit_pages_and_support_nested_table(self) -> None:
        raw = {
            **common(
                "CREATE_NEW_RESOURCE",
                action="CREATE_SUPPORTING_RESOURCE",
                page_refs=[],
                target_page_ref=None,
                locator_kind="NEW_PAGE",
            ),
            "resource_purpose": "SUPPORTING_RESOURCE",
            "proposed_title": "Chemical Compatibility Guide",
            "outline_headings": ["Material Selection", "Application"],
            "content_points": [point()],
            "suggested_source_page_refs": [],
            "comparison_table_brief": {
                "column_headers": ["material selection", "port size"],
                "row_dimensions": ["application"],
            },
        }
        report = opportunity_report(
            opportunity(
                action_codes=(ContentOpportunityActionCode.CREATE_SUPPORTING_RESOURCE,),
                page_refs=(),
                opportunity_type=ContentOpportunityType.NEW_SUPPORTING_CONTENT,
            )
        )
        result, _ = await run_one(raw, report=report)
        self.assertEqual(result.status, ChangePlanStatus.SUCCESS)
        operation = result.operations[0]
        self.assertEqual(operation.locator.locator_kind, SectionLocatorKind.NEW_PAGE)
        self.assertIsNotNone(operation.new_resource_spec.comparison_table_spec)
        self.assertFalse(hasattr(operation.new_resource_spec, "slug"))
        self.assertFalse(hasattr(operation.new_resource_spec, "final_url"))

    async def test_new_resource_requires_sources_bounds_and_observed_suggestions(self) -> None:
        base = {
            **common(
                "CREATE_NEW_RESOURCE",
                action="CREATE_SUPPORTING_RESOURCE",
                page_refs=["P1"],
                target_page_ref=None,
                locator_kind="NEW_PAGE",
            ),
            "resource_purpose": "SUPPORTING_RESOURCE",
            "proposed_title": "Chemical Compatibility Guide",
            "outline_headings": ["Material Selection", "Application"],
            "content_points": [point()],
            "suggested_source_page_refs": ["P1"],
            "comparison_table_brief": None,
        }
        report = opportunity_report(
            opportunity(
                action_codes=(ContentOpportunityActionCode.CREATE_SUPPORTING_RESOURCE,),
                opportunity_type=ContentOpportunityType.NEW_SUPPORTING_CONTENT,
            )
        )
        valid, _ = await run_one(base, report=report)
        self.assertEqual(valid.status, ChangePlanStatus.SUCCESS)
        invalids = (
            {**base, "source_refs": []},
            {**base, "outline_headings": ["Application"]},
            {**base, "suggested_source_page_refs": ["P9"]},
            {**base, "slug": "guide"},
            {**base, "final_url": "https://example.com/guide"},
            {**base, "risk": "LOW"},
        )
        for changed in invalids:
            rejected, _ = await run_one(changed, report=report)
            self.assertEqual(rejected.status, ChangePlanStatus.INVALID_OUTPUT)

    async def test_new_resource_compatibility_for_buyer_technical_and_table_actions(self) -> None:
        for action in (
            ContentOpportunityActionCode.ADD_BUYER_GUIDANCE,
            ContentOpportunityActionCode.ADD_TECHNICAL_DOCUMENTATION,
            ContentOpportunityActionCode.ADD_COMPARISON_TABLE,
        ):
            with self.subTest(action=action.value):
                report = opportunity_report(
                    opportunity(
                        action_codes=(action,),
                        opportunity_type=ContentOpportunityType.NEW_SUPPORTING_CONTENT,
                    )
                )
                raw = {
                    **common(
                        "CREATE_NEW_RESOURCE",
                        action=action.value,
                        target_page_ref=None,
                        locator_kind="NEW_PAGE",
                    ),
                    "resource_purpose": {
                        ContentOpportunityActionCode.ADD_BUYER_GUIDANCE: "BUYER_GUIDANCE",
                        ContentOpportunityActionCode.ADD_TECHNICAL_DOCUMENTATION: "TECHNICAL_DOCUMENTATION",
                        ContentOpportunityActionCode.ADD_COMPARISON_TABLE: "COMPARISON_RESOURCE",
                    }[action],
                    "proposed_title": "Chemical Compatibility Guide",
                    "outline_headings": ["Material Selection", "Application"],
                    "content_points": [point()],
                    "suggested_source_page_refs": ["P1"],
                    "comparison_table_brief": (
                        {
                            "column_headers": ["material selection", "port size"],
                            "row_dimensions": ["application"],
                        }
                        if action is ContentOpportunityActionCode.ADD_COMPARISON_TABLE
                        else None
                    ),
                }
                result, _ = await run_one(raw, report=report)
                self.assertEqual(result.status, ChangePlanStatus.SUCCESS)

    async def test_table_action_new_resource_requires_nested_table_brief(self) -> None:
        report = opportunity_report(
            opportunity(
                action_codes=(ContentOpportunityActionCode.ADD_COMPARISON_TABLE,),
                opportunity_type=ContentOpportunityType.NEW_SUPPORTING_CONTENT,
            )
        )
        raw = {
            **common(
                "CREATE_NEW_RESOURCE",
                action="ADD_COMPARISON_TABLE",
                target_page_ref=None,
                locator_kind="NEW_PAGE",
            ),
            "resource_purpose": "COMPARISON_RESOURCE",
            "proposed_title": "Chemical Compatibility Comparison",
            "outline_headings": ["Material Selection", "Application"],
            "content_points": [point()],
            "suggested_source_page_refs": ["P1"],
            "comparison_table_brief": None,
        }
        result, _ = await run_one(raw, report=report)
        self.assertEqual(result.error, "OPERATION_NOT_ALLOWED")

    async def test_new_resource_purpose_must_match_source_action(self) -> None:
        cases = (
            (
                ContentOpportunityActionCode.ADD_TECHNICAL_DOCUMENTATION,
                "BUYER_GUIDANCE",
            ),
            (
                ContentOpportunityActionCode.ADD_BUYER_GUIDANCE,
                "TECHNICAL_DOCUMENTATION",
            ),
        )
        for action, purpose in cases:
            report = opportunity_report(
                opportunity(
                    action_codes=(action,),
                    opportunity_type=ContentOpportunityType.NEW_SUPPORTING_CONTENT,
                )
            )
            raw = {
                **common(
                    "CREATE_NEW_RESOURCE",
                    action=action.value,
                    target_page_ref=None,
                    locator_kind="NEW_PAGE",
                ),
                "resource_purpose": purpose,
                "proposed_title": "Chemical Compatibility Guide",
                "outline_headings": ["Material Selection", "Application"],
                "content_points": [point()],
                "suggested_source_page_refs": ["P1"],
                "comparison_table_brief": None,
            }
            result, _ = await run_one(raw, report=report)
            self.assertEqual(result.error, "OPERATION_NOT_ALLOWED")

    async def test_old_free_text_page_purpose_field_is_rejected(self) -> None:
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
            "page_purpose": "chemical compatibility guide",
            "proposed_title": "Chemical Compatibility Guide",
            "outline_headings": ["Material Selection", "Application"],
            "content_points": [point()],
            "suggested_source_page_refs": ["P1"],
            "comparison_table_brief": None,
        }
        result, _ = await run_one(raw, report=report)
        self.assertEqual(result.error, "FIELD_CONTRACT")

    async def test_refs_outside_r_are_rejected_even_when_globally_known(self) -> None:
        second = opportunity(
            "R2",
            page_refs=("P2",),
            source_refs=("S2",),
        )
        report = opportunity_report(opportunity(), second)
        site = packet(page("P1"), page("P2"))
        page_outside, _ = await run_one(
            expand(page_refs=["P2"], target_page_ref="P2"), site=site, report=report
        )
        source_outside, _ = await run_one(
            expand(source_refs=["S2"]), site=site, report=report
        )
        self.assertEqual(page_outside.error, "EVIDENCE_USE_NOT_ALLOWED")
        self.assertEqual(source_outside.error, "EVIDENCE_USE_NOT_ALLOWED")

    async def test_page_and_source_ref_count_and_duplicates_are_bounded(self) -> None:
        cases = (
            expand(page_refs=["P1", "P1"]),
            expand(source_refs=["S1", "S1"]),
            expand(page_refs=["P1", "P2", "P3", "P4"]),
            expand(source_refs=["S1", "S2", "S3", "S4", "S5"]),
        )
        for raw in cases:
            with self.subTest(raw=raw):
                result, _ = await run_one(raw)
                self.assertEqual(result.error, "FIELD_CONTRACT")

    async def test_content_point_count_and_subject_length_are_bounded(self) -> None:
        cases = (
            expand(content_points=[]),
            expand(content_points=[point()] * 6),
            expand(content_points=[point("x" * 121)]),
        )
        for raw in cases:
            result, _ = await run_one(raw)
            self.assertEqual(result.status, ChangePlanStatus.INVALID_OUTPUT)

    async def test_proposed_heading_outline_and_table_label_lengths_are_bounded(self) -> None:
        report = opportunity_report(
            opportunity(action_codes=(ContentOpportunityActionCode.ADD_COMPARISON_TABLE,)),
            source_text="x " * 300,
        )
        table = {
            **common("ADD_COMPARISON_TABLE", action="ADD_COMPARISON_TABLE"),
            "proposed_heading": "x" * 121,
            "column_headers": ["x", "x x"],
            "row_dimensions": ["x"],
        }
        result, _ = await run_one(table, report=report)
        self.assertEqual(result.status, ChangePlanStatus.INVALID_OUTPUT)

        resource_report = opportunity_report(
            opportunity(
                action_codes=(ContentOpportunityActionCode.CREATE_SUPPORTING_RESOURCE,),
                opportunity_type=ContentOpportunityType.NEW_SUPPORTING_CONTENT,
            ),
            source_text="chemical compatibility application material selection " + "x " * 300,
        )
        resource = {
            **common(
                "CREATE_NEW_RESOURCE",
                action="CREATE_SUPPORTING_RESOURCE",
                target_page_ref=None,
                locator_kind="NEW_PAGE",
            ),
            "resource_purpose": "SUPPORTING_RESOURCE",
            "proposed_title": "Chemical Compatibility Guide",
            "outline_headings": ["x" * 101, "Application"],
            "content_points": [point()],
            "suggested_source_page_refs": ["P1"],
            "comparison_table_brief": None,
        }
        result, _ = await run_one(resource, report=resource_report)
        self.assertEqual(result.status, ChangePlanStatus.INVALID_OUTPUT)

    async def test_content_point_intent_is_strict_enum(self) -> None:
        result, _ = await run_one(expand(content_points=[point(intent="WRITE")]))
        self.assertEqual(result.error, "FIELD_CONTRACT")

    async def test_provider_cannot_output_urls_slug_risk_prose_or_approval_fields(self) -> None:
        forbidden = {
            "source_url": "https://example.com",
            "target_url": "https://example.com",
            "final_url": "https://example.com",
            "slug": "guide",
            "risk": "LOW",
            "rationale": "final rationale",
            "summary": "final summary",
            "html": "<p>draft</p>",
            "approved": True,
            "reviewed": True,
            "applied": True,
            "approved_for_publish": True,
        }
        for name, value in forbidden.items():
            with self.subTest(field=name):
                result, _ = await run_one({**expand(), name: value})
                self.assertEqual(result.error, "FIELD_CONTRACT")

    async def test_duplicate_json_keys_are_rejected(self) -> None:
        text = '{"operations":[],"operations":[]}'
        generation = ChangePlanGeneration(
            "fake", "fake", ChangePlanGenerationStatus.SUCCESS, text, None
        )
        result = await ChangePlanWorkflow(FakeWriter(generation)).run(
            packet(), opportunity_report()
        )
        self.assertEqual(result.error, "JSON_FORMAT")

    async def test_prompt_contains_only_bounded_evidence_not_display_or_diagnostics(self) -> None:
        writer = FakeWriter(generated([]))
        result = await ChangePlanWorkflow(writer).run(packet(), opportunity_report())
        material = writer.prompts[0].material_json()
        self.assertEqual(result.status, ChangePlanStatus.SUCCESS)
        self.assertNotIn("final_url", material)
        self.assertNotIn("rationale", material)
        self.assertNotIn("Research draft", material)
        self.assertNotIn("crawl_stop_reason", material)
        self.assertNotIn("timeout", material.casefold())
        self.assertIn('"evidence_scope":"observed_present_only"', material)
        self.assertIn('"supports_absence_claims":false', material)

    async def test_oversized_prompt_fails_before_provider(self) -> None:
        huge = page(body="chemical compatibility " * 2_000)
        writer = FakeWriter(generated([]))
        result = await ChangePlanWorkflow(writer).run(
            packet(huge), opportunity_report()
        )
        self.assertEqual(result.status, ChangePlanStatus.INVALID_INPUT)
        self.assertEqual(result.error, "FIELD_CONTRACT")
        self.assertEqual(writer.prompts, [])

    async def test_legal_worst_case_prompt_fits_user_budget(self) -> None:
        from foreign_trade_geo_agent.core.change_plan import (
            MAX_USER_MATERIAL_BYTES,
            MAX_USER_MATERIAL_CHARS,
        )

        pages = tuple(
            page(
                f"P{index}",
                body="chemical compatibility material selection application " + "x" * 500,
                structured=(
                    StructuredContentBlock(
                        StructuredContentKind.SECTION,
                        heading=f"Technical Evidence {index}",
                        text="chemical compatibility " + "t" * 1_100,
                    ),
                    StructuredContentBlock(
                        StructuredContentKind.SECTION,
                        heading=f"Buyer Evidence {index}",
                        text="material selection " + "b" * 300,
                    ),
                ),
            )
            for index in range(1, 6)
        )
        opportunities = tuple(
            opportunity(
                f"R{index}",
                page_refs=tuple(f"P{page_index}" for page_index in range(1, 6)),
                source_refs=tuple(f"S{source_index}" for source_index in range(1, 5)),
            )
            for index in range(1, 5)
        )
        report = opportunity_report(
            *opportunities,
            source_text="chemical compatibility material selection application " + "s" * 690,
        )
        writer = FakeWriter(generated([]))
        result = await ChangePlanWorkflow(writer).run(packet(*pages), report)
        material = writer.prompts[0].material_json()
        self.assertEqual(result.status, ChangePlanStatus.SUCCESS)
        self.assertLessEqual(len(material), MAX_USER_MATERIAL_CHARS)
        self.assertLessEqual(len(material.encode("utf-8")), MAX_USER_MATERIAL_BYTES)

    async def test_invalid_writer_result_is_generation_failure(self) -> None:
        class InvalidWriter:
            async def write_change_plan(self, prompt):
                return object()

        result = await ChangePlanWorkflow(InvalidWriter()).run(packet(), opportunity_report())
        self.assertEqual(result.status, ChangePlanStatus.GENERATION_FAILED)
        self.assertEqual(result.operations, ())

    async def test_empty_operations_from_provider_is_success(self) -> None:
        result = await ChangePlanWorkflow(FakeWriter(generated([]))).run(
            packet(), opportunity_report()
        )
        self.assertEqual(result.status, ChangePlanStatus.SUCCESS)
        self.assertEqual(result.operations, ())

    async def test_unknown_and_out_of_opportunity_refs_fail_closed(self) -> None:
        report = opportunity_report(
            opportunity(page_refs=("P1",), source_refs=("S1",)),
            source_text="chemical compatibility",
        )
        site = packet(page("P1"), page("P2"))
        cases = (
            (expand(opportunity_ref="R9"), "UNKNOWN_OPPORTUNITY_REFERENCE"),
            (expand(page_refs=["P9"]), "UNKNOWN_PAGE_REFERENCE"),
            (expand(source_refs=["S9"]), "UNKNOWN_SOURCE_REFERENCE"),
            (expand(page_refs=["P2"], target_page_ref="P2"), "EVIDENCE_USE_NOT_ALLOWED"),
        )
        for raw, category in cases:
            result, _ = await run_one(raw, site=site, report=report)
            self.assertEqual(result.error, category)

    async def test_action_code_must_belong_to_r_and_compatibility_matrix(self) -> None:
        not_on_r = expand(source_action_code="ADD_COMPARISON_TABLE")
        result, _ = await run_one(not_on_r)
        self.assertEqual(result.error, "OPERATION_NOT_ALLOWED")

        report = opportunity_report(
            opportunity(action_codes=(ContentOpportunityActionCode.ADD_COMPARISON_TABLE,))
        )
        incompatible = expand(source_action_code="ADD_COMPARISON_TABLE")
        result, _ = await run_one(incompatible, report=report)
        self.assertEqual(result.error, "OPERATION_NOT_ALLOWED")

    async def test_absence_claims_are_rejected_in_every_free_phrase(self) -> None:
        for subject in ("missing FAQ", "lacks links", "absent comparison table", "no FAQ"):
            with self.subTest(subject=subject):
                result, _ = await run_one(expand(content_points=[point(subject)]))
                self.assertEqual(result.error, "UNSUPPORTED_ABSENCE_CLAIM")

    async def test_strict_json_and_exact_discriminated_fields(self) -> None:
        malformed = ChangePlanGeneration(
            "fake", "fake", ChangePlanGenerationStatus.SUCCESS, "{", None
        )
        cases = (
            (malformed, "JSON_FORMAT"),
            (ChangePlanGeneration("fake", "fake", ChangePlanGenerationStatus.SUCCESS, "[]", None), "FIELD_CONTRACT"),
            (generated([{**expand(), "html": "<p>draft</p>"}]), "FIELD_CONTRACT"),
            (generated([{**expand(), "change_id": "C1"}]), "FIELD_CONTRACT"),
            (generated([{**expand(), "risk": "LOW"}]), "FIELD_CONTRACT"),
            (generated([{**expand(), "proposed_heading": "wrong discriminator"}]), "FIELD_CONTRACT"),
        )
        for generation, category in cases:
            writer = FakeWriter(generation)
            result = await ChangePlanWorkflow(writer).run(packet(), opportunity_report())
            self.assertEqual(result.status, ChangePlanStatus.INVALID_OUTPUT)
            self.assertEqual(result.error, category)

    async def test_any_invalid_operation_rejects_entire_report(self) -> None:
        writer = FakeWriter(generated([expand(), expand(content_points=[point("ungrounded")])]))
        result = await ChangePlanWorkflow(writer).run(packet(), opportunity_report())
        self.assertEqual(result.status, ChangePlanStatus.INVALID_OUTPUT)
        self.assertEqual(result.operations, ())

    async def test_multiple_operations_keep_order_and_assign_ids_after_validation(self) -> None:
        second = expand(content_points=[point("material selection", "DESCRIBE")])
        writer = FakeWriter(generated([expand(), second]))
        result = await ChangePlanWorkflow(writer).run(packet(), opportunity_report())
        self.assertEqual(result.status, ChangePlanStatus.SUCCESS)
        self.assertEqual(tuple(item.change_id for item in result.operations), ("C1", "C2"))
        self.assertEqual(result.operations[1].content_points[0].subject, "material selection")

    async def test_identical_duplicate_operations_reject_entire_output(self) -> None:
        writer = FakeWriter(generated([expand(), dict(expand())]))
        result = await ChangePlanWorkflow(writer).run(packet(), opportunity_report())
        self.assertEqual(result.status, ChangePlanStatus.INVALID_OUTPUT)
        self.assertEqual(result.error, "FIELD_CONTRACT")
        self.assertEqual(result.operations, ())

    async def test_normalization_equivalent_duplicate_operations_reject_entire_output(self) -> None:
        equivalents = (
            "CHEMICAL COMPATIBILITY",
            "ｃｈｅｍｉｃａｌ ｃｏｍｐａｔｉｂｉｌｉｔｙ",
            "chemical   compatibility",
            " ＣＨＥＭＩＣＡＬ   ＣＯＭＰＡＴＩＢＩＴＹ ",
        )
        for equivalent in equivalents:
            with self.subTest(equivalent=equivalent):
                writer = FakeWriter(
                    generated(
                        [
                            expand(content_points=[point("chemical compatibility")]),
                            expand(content_points=[point(equivalent)]),
                        ]
                    )
                )

                result = await ChangePlanWorkflow(writer).run(
                    packet(), opportunity_report()
                )

                self.assertEqual(result.status, ChangePlanStatus.INVALID_OUTPUT)
                self.assertEqual(result.error, "FIELD_CONTRACT")
                self.assertEqual(result.operations, ())

    async def test_same_text_on_different_target_pages_is_not_duplicate(self) -> None:
        site = packet(page("P1"), page("P2"))
        report = opportunity_report(opportunity(page_refs=("P1", "P2")))
        first = expand(page_refs=["P1", "P2"], target_page_ref="P1")
        second = expand(page_refs=["P1", "P2"], target_page_ref="P2")

        result = await ChangePlanWorkflow(
            FakeWriter(generated([first, second]))
        ).run(site, report)

        self.assertEqual(result.status, ChangePlanStatus.SUCCESS)
        self.assertEqual(tuple(item.change_id for item in result.operations), ("C1", "C2"))

    async def test_meaningful_reorder_sequence_is_not_collapsed_as_duplicate(self) -> None:
        report = opportunity_report(
            opportunity(
                action_codes=(ContentOpportunityActionCode.REORGANIZE_PAGE_SECTIONS,)
            )
        )
        first = {
            **common("PROPOSE_SECTION_REORDER", action="REORGANIZE_PAGE_SECTIONS"),
            "ordered_headings": ["Chemical Compatibility", "Maintenance"],
        }
        second = {
            **common("PROPOSE_SECTION_REORDER", action="REORGANIZE_PAGE_SECTIONS"),
            "ordered_headings": ["Maintenance", "Chemical Compatibility"],
        }

        result = await ChangePlanWorkflow(
            FakeWriter(generated([first, second]))
        ).run(packet(), report)

        self.assertEqual(result.status, ChangePlanStatus.SUCCESS)
        self.assertEqual(tuple(item.change_id for item in result.operations), ("C1", "C2"))

    async def test_same_opportunity_allows_distinct_compatible_operation_types(self) -> None:
        report = opportunity_report(
            opportunity(
                action_codes=(ContentOpportunityActionCode.ADD_COMPARISON_TABLE,)
            )
        )
        table = {
            **common("ADD_COMPARISON_TABLE", action="ADD_COMPARISON_TABLE"),
            "proposed_heading": "Pump Comparison",
            "column_headers": ["material selection", "port size"],
            "row_dimensions": ["application"],
        }
        resource = {
            **common(
                "CREATE_NEW_RESOURCE",
                action="ADD_COMPARISON_TABLE",
                target_page_ref=None,
                locator_kind="NEW_PAGE",
            ),
            "resource_purpose": "COMPARISON_RESOURCE",
            "proposed_title": "Pump Comparison Guide",
            "outline_headings": ["Material Selection", "Application"],
            "content_points": [point()],
            "suggested_source_page_refs": ["P1"],
            "comparison_table_brief": {
                "column_headers": ["material selection", "port size"],
                "row_dimensions": ["application"],
            },
        }

        result = await ChangePlanWorkflow(
            FakeWriter(generated([table, resource]))
        ).run(packet(), report)

        self.assertEqual(result.status, ChangePlanStatus.SUCCESS)
        self.assertEqual(
            tuple(item.operation_type for item in result.operations),
            (
                ChangeOperationType.ADD_COMPARISON_TABLE,
                ChangeOperationType.CREATE_NEW_RESOURCE,
            ),
        )

    async def test_zero_opportunities_is_success_without_provider_call(self) -> None:
        empty = opportunity_report(opportunity())
        empty = replace(empty, opportunities=())
        writer = FakeWriter(generated([expand()]))
        result = await ChangePlanWorkflow(writer).run(packet(), empty)
        self.assertEqual(result.status, ChangePlanStatus.SUCCESS)
        self.assertEqual(result.operations, ())
        self.assertEqual(writer.prompts, [])
        self.assertTrue(result.requires_human_review)

    async def test_none_opportunities_is_invalid_input_without_provider_call(self) -> None:
        report = replace(opportunity_report(), opportunities=None)
        writer = FakeWriter(generated([]))

        result = await ChangePlanWorkflow(writer).run(packet(), report)

        self.assertEqual(result.status, ChangePlanStatus.INVALID_INPUT)
        self.assertEqual(result.error, "FIELD_CONTRACT")
        self.assertEqual(result.operations, ())
        self.assertEqual(writer.prompts, [])

    async def test_wrong_top_level_input_types_return_invalid_input(self) -> None:
        writer = FakeWriter(generated([]))
        cases = (
            (object(), opportunity_report()),
            (packet(), object()),
        )
        for site, report in cases:
            with self.subTest(site=type(site), report=type(report)):
                result = await ChangePlanWorkflow(writer).run(  # type: ignore[arg-type]
                    site,
                    report,
                )
                self.assertEqual(result.status, ChangePlanStatus.INVALID_INPUT)
                self.assertEqual(result.error, "FIELD_CONTRACT")
                self.assertEqual(result.operations, ())
        self.assertEqual(writer.prompts, [])

    async def test_missing_stable_collection_is_invalid_input_without_exception(self) -> None:
        report = opportunity_report()
        object.__delattr__(report, "opportunities")
        writer = FakeWriter(generated([]))

        result = await ChangePlanWorkflow(writer).run(packet(), report)

        self.assertEqual(result.status, ChangePlanStatus.INVALID_INPUT)
        self.assertEqual(result.error, "FIELD_CONTRACT")
        self.assertEqual(result.operations, ())
        self.assertEqual(writer.prompts, [])

    async def test_list_opportunities_is_invalid_input_without_provider_call(self) -> None:
        report = replace(
            opportunity_report(),
            opportunities=[opportunity()],
        )
        writer = FakeWriter(generated([]))

        result = await ChangePlanWorkflow(writer).run(packet(), report)

        self.assertEqual(result.status, ChangePlanStatus.INVALID_INPUT)
        self.assertEqual(result.error, "FIELD_CONTRACT")
        self.assertEqual(result.operations, ())
        self.assertEqual(writer.prompts, [])

    async def test_list_page_collection_is_invalid_input_without_provider_call(self) -> None:
        site = packet()
        object.__setattr__(site, "pages", list(site.pages))
        writer = FakeWriter(generated([]))

        result = await ChangePlanWorkflow(writer).run(site, opportunity_report())

        self.assertEqual(result.status, ChangePlanStatus.INVALID_INPUT)
        self.assertEqual(result.error, "FIELD_CONTRACT")
        self.assertEqual(result.operations, ())
        self.assertEqual(writer.prompts, [])

    async def test_list_source_materials_is_invalid_input_without_provider_call(self) -> None:
        report = opportunity_report()
        object.__setattr__(report, "source_materials", list(report.source_materials))
        writer = FakeWriter(generated([]))

        result = await ChangePlanWorkflow(writer).run(packet(), report)

        self.assertEqual(result.status, ChangePlanStatus.INVALID_INPUT)
        self.assertEqual(result.error, "FIELD_CONTRACT")
        self.assertEqual(result.operations, ())
        self.assertEqual(writer.prompts, [])

    def test_runtime_shape_preflight_rejects_malformed_structured_collections(self) -> None:
        block = StructuredContentBlock(
            StructuredContentKind.TABLE,
            rows=(("material", "selection"),),
        )
        object.__setattr__(block, "rows", [["material", "selection"]])
        site = packet(page(structured=(block,)))

        error = stable_change_plan_input_shape_error(site, opportunity_report())

        self.assertEqual(error, "FIELD_CONTRACT")

    async def test_forged_structured_kind_is_invalid_input_without_exception(self) -> None:
        block = StructuredContentBlock(
            StructuredContentKind.SECTION,
            heading="Chemical Compatibility",
            text="chemical compatibility",
        )
        object.__setattr__(block, "kind", "bogus")
        site = packet(page(structured=(block,)))
        writer = FakeWriter(generated([]))

        result = await ChangePlanWorkflow(writer).run(site, opportunity_report())

        self.assertEqual(result.status, ChangePlanStatus.INVALID_INPUT)
        self.assertEqual(result.error, "FIELD_CONTRACT")
        self.assertEqual(result.operations, ())
        self.assertEqual(writer.prompts, [])

    def test_core_input_validator_runs_shape_preflight_before_cardinality(self) -> None:
        report = replace(opportunity_report(), opportunities=None)

        error = validate_change_plan_input(ChangePlanInput(packet(), report))

        self.assertEqual(error, "FIELD_CONTRACT")

    async def test_invalid_stable_r_identifier_fails_before_provider(self) -> None:
        malformed = replace(opportunity(), recommendation_id="provider-R1")
        writer = FakeWriter(generated([]))
        result = await ChangePlanWorkflow(writer).run(
            packet(), opportunity_report(malformed)
        )
        self.assertEqual(result.status, ChangePlanStatus.INVALID_INPUT)
        self.assertEqual(result.error, "FIELD_CONTRACT")
        self.assertEqual(writer.prompts, [])

    async def test_stable_r_unknown_page_fails_before_provider(self) -> None:
        malformed = opportunity(page_refs=("P9",))
        writer = FakeWriter(generated([]))
        result = await ChangePlanWorkflow(writer).run(
            packet(), opportunity_report(malformed)
        )
        self.assertEqual(result.error, "UNKNOWN_PAGE_REFERENCE")
        self.assertEqual(writer.prompts, [])

    async def test_stable_r_unknown_source_fails_before_provider(self) -> None:
        report = opportunity_report(opportunity())
        malformed = replace(
            report,
            opportunities=(replace(opportunity(), source_refs=("S9",)),),
        )
        writer = FakeWriter(generated([]))
        result = await ChangePlanWorkflow(writer).run(packet(), malformed)
        self.assertEqual(result.error, "UNKNOWN_SOURCE_REFERENCE")
        self.assertEqual(writer.prompts, [])

    async def test_forged_stable_opportunity_semantics_fail_before_provider(self) -> None:
        valid = opportunity()
        for forged in (
            replace(
                valid,
                action_codes=(ContentOpportunityActionCode.CREATE_SUPPORTING_RESOURCE,),
            ),
            replace(valid, title="Forged title"),
            replace(valid, rationale="Forged rationale"),
            replace(valid, actions=("Forged action",)),
            replace(valid, topic="quantum flux"),
        ):
            with self.subTest(forged=forged):
                writer = FakeWriter(generated([]))
                result = await ChangePlanWorkflow(writer).run(
                    packet(), opportunity_report(forged)
                )
                self.assertEqual(result.status, ChangePlanStatus.INVALID_INPUT)
                self.assertEqual(result.error, "FIELD_CONTRACT")
                self.assertEqual(writer.prompts, [])

    async def test_forged_expand_with_supporting_resource_action_fails_before_provider(self) -> None:
        forged = replace(
            opportunity(),
            action_codes=(ContentOpportunityActionCode.CREATE_SUPPORTING_RESOURCE,),
        )
        writer = FakeWriter(generated([]))
        result = await ChangePlanWorkflow(writer).run(
            packet(), opportunity_report(forged)
        )
        self.assertEqual(result.status, ChangePlanStatus.INVALID_INPUT)
        self.assertEqual(writer.prompts, [])

    async def test_duplicate_and_oversized_stable_page_catalogs_fail_closed(self) -> None:
        duplicate_packet = packet(page("P1"), page("P1", url="https://example.com/other"))
        oversized_packet = packet(*(page(f"P{index}") for index in range(1, 7)))
        for site in (duplicate_packet, oversized_packet):
            writer = FakeWriter(generated([]))
            result = await ChangePlanWorkflow(writer).run(site, opportunity_report())
            self.assertEqual(result.status, ChangePlanStatus.INVALID_INPUT)
            self.assertEqual(result.error, "FIELD_CONTRACT")
            self.assertEqual(writer.prompts, [])

    async def test_duplicate_and_oversized_stable_source_catalogs_fail_closed(self) -> None:
        base = opportunity_report()
        duplicate = replace(
            base,
            source_materials=(base.source_materials[0], base.source_materials[0]),
        )
        materials = tuple(
            ContentOpportunitySourceMaterial(
                f"S{index}",
                "Chemical compatibility pump guide",
                "chemical compatibility",
                False,
            )
            for index in range(1, 6)
        )
        sources = tuple(
            ContentOpportunitySource(
                f"S{index}",
                "Chemical compatibility pump guide",
                f"https://source.example/s{index}",
                CLASSIFICATIONS,
            )
            for index in range(1, 6)
        )
        oversized = replace(base, source_materials=materials, sources=sources)
        for report in (duplicate, oversized):
            writer = FakeWriter(generated([]))
            result = await ChangePlanWorkflow(writer).run(packet(), report)
            self.assertEqual(result.status, ChangePlanStatus.INVALID_INPUT)
            self.assertEqual(result.error, "FIELD_CONTRACT")
            self.assertEqual(writer.prompts, [])

    async def test_provider_failure_exception_timeout_and_no_retry(self) -> None:
        failed = ChangePlanGeneration(
            "fake", "fake", ChangePlanGenerationStatus.FAILED, None, "secret"
        )
        fake = FakeWriter(failed)
        first = await ChangePlanWorkflow(fake).run(packet(), opportunity_report())
        raising = RaisingWriter()
        second = await ChangePlanWorkflow(raising).run(packet(), opportunity_report())
        generation_deadline = await ChangePlanWorkflow(
            SlowWriter(), generation_timeout=0.01, total_timeout=0.05
        ).run(packet(), opportunity_report())
        internal_timeout_writer = TimeoutRaisingWriter()
        internal_timeout = await ChangePlanWorkflow(internal_timeout_writer).run(
            packet(), opportunity_report()
        )
        outer_deadline = await ChangePlanWorkflow(
            SlowWriter(), generation_timeout=0.2, total_timeout=0.01
        ).run(packet(), opportunity_report())
        self.assertEqual(first.status, ChangePlanStatus.GENERATION_FAILED)
        self.assertEqual(second.status, ChangePlanStatus.GENERATION_FAILED)
        self.assertEqual(generation_deadline.status, ChangePlanStatus.GENERATION_FAILED)
        self.assertEqual(internal_timeout.status, ChangePlanStatus.GENERATION_FAILED)
        self.assertEqual(outer_deadline.status, ChangePlanStatus.WORKFLOW_TIMEOUT)
        self.assertEqual(len(fake.prompts), 1)
        self.assertEqual(raising.calls, 1)
        self.assertEqual(internal_timeout_writer.calls, 1)
        self.assertIsNone(first.error)

    async def test_output_operation_and_per_opportunity_budgets(self) -> None:
        too_many = [expand() for _ in range(MAX_OPERATIONS + 1)]
        result = await ChangePlanWorkflow(FakeWriter(generated(too_many))).run(
            packet(), opportunity_report()
        )
        self.assertEqual(result.error, "FIELD_CONTRACT")

        three = [expand(), expand(), expand()]
        result = await ChangePlanWorkflow(FakeWriter(generated(three))).run(
            packet(), opportunity_report()
        )
        self.assertEqual(result.error, "OPERATION_NOT_ALLOWED")

    async def test_forged_upstream_opportunity_cardinality_is_invalid_input(self) -> None:
        opportunities = tuple(opportunity(f"R{index}") for index in range(1, 6))
        writer = FakeWriter(generated([]))
        result = await ChangePlanWorkflow(writer).run(
            packet(), opportunity_report(*opportunities)
        )
        self.assertEqual(result.status, ChangePlanStatus.INVALID_INPUT)
        self.assertEqual(result.error, "FIELD_CONTRACT")
        self.assertEqual(writer.prompts, [])

    async def test_valid_input_over_change_plan_material_budget_is_input_too_large(self) -> None:
        writer = FakeWriter(generated([]))
        with patch(
            "foreign_trade_geo_agent.workflows.change_plan.MAX_USER_MATERIAL_CHARS",
            1,
        ):
            result = await ChangePlanWorkflow(writer).run(packet(), opportunity_report())

        self.assertEqual(result.status, ChangePlanStatus.INPUT_TOO_LARGE)
        self.assertEqual(result.error, "INPUT_TOO_LARGE")
        self.assertEqual(result.operations, ())
        self.assertEqual(writer.prompts, [])

    async def test_invalid_generation_is_not_retried(self) -> None:
        writer = FakeWriter(generated([expand(content_points=[point("quantum flux")])]))
        result = await ChangePlanWorkflow(writer).run(packet(), opportunity_report())
        self.assertEqual(result.status, ChangePlanStatus.INVALID_OUTPUT)
        self.assertEqual(len(writer.prompts), 1)

    def test_workflow_timeouts_must_be_positive(self) -> None:
        for kwargs in (
            {"generation_timeout": 0},
            {"total_timeout": -1},
            {"generation_timeout": "40"},
            {"generation_timeout": float("nan")},
            {"total_timeout": float("inf")},
            {"generation_timeout": MAX_CHANGE_PLAN_TIMEOUT_SECONDS + 1},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    ChangePlanWorkflow(FakeWriter(generated([])), **kwargs)

    async def test_raw_provider_character_and_byte_bounds(self) -> None:
        from foreign_trade_geo_agent.core.change_plan import (
            MAX_RAW_OUTPUT_BYTES,
            MAX_RAW_OUTPUT_CHARS,
        )
        for text in ("x" * (MAX_RAW_OUTPUT_CHARS + 1), "泵" * (MAX_RAW_OUTPUT_BYTES // 3 + 1)):
            generation = ChangePlanGeneration(
                "fake", "fake", ChangePlanGenerationStatus.SUCCESS, text, None
            )
            result = await ChangePlanWorkflow(FakeWriter(generation)).run(
                packet(), opportunity_report()
            )
            self.assertEqual(result.error, "OUTPUT_TOO_LARGE")

    async def test_same_input_and_generation_produce_same_report(self) -> None:
        generation = generated([expand()])
        first = await ChangePlanWorkflow(FakeWriter(generation)).run(packet(), opportunity_report())
        second = await ChangePlanWorkflow(FakeWriter(generation)).run(packet(), opportunity_report())
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
