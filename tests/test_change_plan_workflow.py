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
    ContentPointCandidate,
    ContentPointIntent,
    NewResourcePurpose,
    ObservedHeadingKind,
    OpportunityContentPointCandidates,
    SectionLocatorKind,
    SectionPurpose,
    TargetLocatorRepairRule,
    build_change_plan_prompt,
    diagnose_grounding_violation,
    derive_section_locator,
    _validate_table,
    operation_evidence_texts,
    stable_change_plan_input_shape_error,
    validate_and_finalize_specification,
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


def _current_transient_operation(operation: dict[str, object]) -> dict[str, object]:
    provider_operation = dict(operation)
    if (
        provider_operation.get("operation_type") == "ADD_SECTION"
        and provider_operation.get("proposed_heading")
        == "Chemical Compatibility Guide"
    ):
        locator_ref = provider_operation.get("locator_ref", "P1.LOC_00")
        page_ref = (
            locator_ref.split(".", 1)[0]
            if isinstance(locator_ref, str)
            else "P1"
        )
        provider_operation.pop("proposed_heading")
        provider_operation["proposed_heading_ref"] = f"{page_ref}.PH_01"
    if (
        provider_operation.get("operation_type") == "CREATE_NEW_RESOURCE"
        and provider_operation.get("outline_headings")
        == ["Material Selection", "Application"]
    ):
        provider_operation.pop("outline_headings")
    return provider_operation


def generated(operations: list[dict[str, object]]) -> ChangePlanGeneration:
    opportunity_operations: dict[str, dict[str, object]] = {}
    for operation in operations:
        provider_operation = _current_transient_operation(operation)
        opportunity_ref = provider_operation.pop("opportunity_ref", "R1")
        if not isinstance(opportunity_ref, str):
            opportunity_ref = str(opportunity_ref)
        if provider_operation.get("operation_type") == "CREATE_NEW_RESOURCE":
            page_refs = provider_operation.pop("page_refs", None)
            suggestions = provider_operation.pop("suggested_source_page_refs", None)
            if (
                isinstance(page_refs, list)
                and all(isinstance(item, str) for item in page_refs)
                and isinstance(suggestions, list)
                and all(isinstance(item, str) for item in suggestions)
                and set(suggestions).issubset(page_refs)
            ):
                provider_operation["page_bindings"] = [
                    {
                        "page_ref": page_ref,
                        "suggested_source": page_ref in suggestions,
                    }
                    for page_ref in page_refs
                ]
        slots = opportunity_operations.setdefault(opportunity_ref, {})
        if "primary_operation" not in slots:
            slots["primary_operation"] = provider_operation
        elif "secondary_operation" not in slots:
            slots["secondary_operation"] = provider_operation
        else:
            slots["tertiary_operation"] = provider_operation
    return ChangePlanGeneration(
        provider="fake",
        model="fake",
        status=ChangePlanGenerationStatus.SUCCESS,
        text=json.dumps(
            {"opportunity_operations": opportunity_operations},
            ensure_ascii=False,
        ),
        error=None,
    )


def generated_slots(
    primary: dict[str, object] | None = None,
    secondary: dict[str, object] | None = None,
    *,
    opportunity_ref: str = "R1",
    extra_slots: dict[str, object] | None = None,
) -> ChangePlanGeneration:
    slots: dict[str, object] = {}
    if primary is not None:
        primary = _current_transient_operation(primary)
        primary.pop("opportunity_ref", None)
        slots["primary_operation"] = primary
    if secondary is not None:
        secondary = _current_transient_operation(secondary)
        secondary.pop("opportunity_ref", None)
        slots["secondary_operation"] = secondary
    if extra_slots:
        slots.update(extra_slots)
    return ChangePlanGeneration(
        provider="fake",
        model="fake",
        status=ChangePlanGenerationStatus.SUCCESS,
        text=json.dumps(
            {"opportunity_operations": {opportunity_ref: slots}},
            ensure_ascii=False,
        ),
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
    locator_ref: str | None = None,
) -> dict[str, object]:
    result: dict[str, object] = {
        "opportunity_ref": "R1",
        "source_action_code": action,
        "operation_type": operation_type,
        "page_refs": ["P1"] if page_refs is None else page_refs,
        "source_refs": ["S1"] if source_refs is None else source_refs,
    }
    if operation_type in {
        "EXPAND_SECTION",
        "ADD_SECTION",
        "ADD_COMPARISON_TABLE",
    }:
        if locator_ref is None:
            heading_indexes = {
                "Industrial Pumps": 1,
                "Chemical Compatibility": 2,
                "Specifications": 2,
                "Maintenance": 3,
                "Installation Notes": 4,
            }
            if (
                locator_kind == "PAGE_LEVEL"
                and target_page_ref is not None
                and target_heading is None
            ):
                locator_ref = f"{target_page_ref}.LOC_00"
            elif (
                locator_kind == "EXACT_OBSERVED_HEADING"
                and target_page_ref is not None
                and target_heading in heading_indexes
            ):
                locator_ref = (
                    f"{target_page_ref}.LOC_{heading_indexes[target_heading]:02d}"
                )
            else:
                locator_ref = f"{target_page_ref or 'P1'}.LOC_99"
        result["locator_ref"] = locator_ref
    elif operation_type == "ADD_INTERNAL_LINK":
        result["target_page_ref"] = target_page_ref
    return result


def point(subject: str = "chemical compatibility", intent: str = "EXPLAIN") -> dict[str, str]:
    candidate_refs = {
        "chemical compatibility": "P1.CP_02",
        "material selection": "P1.CP_04",
        "port size": "P1.CP_05",
        "application": "P1.CP_06",
        "maintenance considerations": "P1.CP_07",
        "pump performance are observed topics.": "P1.CP_08",
    }
    return {"intent": intent, "subject_ref": candidate_refs.get(subject, subject)}


def expand(**overrides: object) -> dict[str, object]:
    locator_options = {
        name: overrides.pop(name)
        for name in (
            "target_page_ref",
            "locator_kind",
            "target_heading",
            "locator_ref",
        )
        if name in overrides
    }
    result = {
        **common(
            "EXPAND_SECTION",
            action="EXPAND_PAGE_SECTION",
            **locator_options,
        ),
        "content_points": [point()],
    }
    result.update(overrides)
    return result


def transient_common(
    operation_type: str,
    *,
    action: str,
    page_refs: list[str] | None = None,
    source_refs: list[str] | None = None,
    locator_ref: str = "P1.LOC_00",
) -> dict[str, object]:
    result: dict[str, object] = {
        "opportunity_ref": "R1",
        "source_action_code": action,
        "operation_type": operation_type,
        "source_refs": ["S1"] if source_refs is None else source_refs,
    }
    if operation_type != "CREATE_NEW_RESOURCE":
        result["page_refs"] = ["P1"] if page_refs is None else page_refs
    if operation_type in {
        "EXPAND_SECTION",
        "ADD_SECTION",
        "ADD_COMPARISON_TABLE",
    }:
        result["locator_ref"] = locator_ref
    return result


def transient_expand(**overrides: object) -> dict[str, object]:
    result = {
        **transient_common("EXPAND_SECTION", action="EXPAND_PAGE_SECTION"),
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


class ScriptedWriter:
    def __init__(self, *responses: ChangePlanGeneration) -> None:
        self.responses = list(responses)
        self.prompts = []

    async def write_change_plan(self, prompt):
        self.prompts.append(prompt)
        if not self.responses:
            raise AssertionError("Change plan writer exceeded its script.")
        return self.responses.pop(0)


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


def supporting_resource(**overrides):
    raw = {
        **common("CREATE_NEW_RESOURCE", action="CREATE_SUPPORTING_RESOURCE"),
        "resource_purpose": "SUPPORTING_RESOURCE",
        "proposed_title": "Chemical Compatibility Guide",
        "outline_headings": ["Material Selection", "Application"],
        "content_points": [point()],
        "suggested_source_page_refs": ["P1"],
        "comparison_table_brief": None,
    }
    raw.update(overrides)
    return raw


async def run_one(raw: dict[str, object], *, site=None, report=None):
    writer = FakeWriter(generated([raw]))
    result = await ChangePlanWorkflow(writer).run(site or packet(), report or opportunity_report())
    return result, writer


class ChangePlanWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_grounding_failures_expose_exact_transient_safe_descriptors(self) -> None:
        add_section_report = opportunity_report(
            opportunity(action_codes=(ContentOpportunityActionCode.ADD_BUYER_GUIDANCE,))
        )
        table_report = opportunity_report(
            opportunity(action_codes=(ContentOpportunityActionCode.ADD_COMPARISON_TABLE,))
        )
        link_report = opportunity_report(
            opportunity(
                action_codes=(ContentOpportunityActionCode.ADD_INTERNAL_LINK,),
                page_refs=("P1", "P2"),
            )
        )
        resource_report = opportunity_report(
            opportunity(
                action_codes=(ContentOpportunityActionCode.CREATE_SUPPORTING_RESOURCE,),
                opportunity_type=ContentOpportunityType.NEW_SUPPORTING_CONTENT,
            )
        )
        base_add_section = {
            **common("ADD_SECTION", action="ADD_BUYER_GUIDANCE"),
            "section_purpose": "BUYER_GUIDANCE",
            "proposed_heading": "Chemical Compatibility Guide",
            "content_points": [point()],
        }
        base_table = {
            **common("ADD_COMPARISON_TABLE", action="ADD_COMPARISON_TABLE"),
            "proposed_heading": "Pump Comparison",
            "column_headers": ["material selection", "port size"],
            "row_dimensions": ["application", "maintenance considerations"],
        }
        base_link = {
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
        base_resource = {
            **common(
                "CREATE_NEW_RESOURCE",
                action="CREATE_SUPPORTING_RESOURCE",
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
        cases = (
            (
                "expand subject",
                expand(content_points=[point("P1.CP_99")]),
                opportunity_report(),
                packet(),
                "R1.primary_operation.content_points[0].subject",
                "VERBATIM_CONTIGUOUS",
                "P1.CP_99",
            ),
            (
                "add section subject",
                {**base_add_section, "content_points": [point("P1.CP_99")]},
                add_section_report,
                packet(),
                "R1.primary_operation.content_points[0].subject",
                "VERBATIM_CONTIGUOUS",
                "P1.CP_99",
            ),
            (
                "table column",
                {**base_table, "column_headers": ["quantum flux", "port size"]},
                table_report,
                packet(),
                "R1.primary_operation.column_headers[0]",
                "VERBATIM_CONTIGUOUS",
                None,
            ),
            (
                "table proposed heading",
                {**base_table, "proposed_heading": "Quantum Flux Comparison"},
                table_report,
                packet(),
                "R1.primary_operation.proposed_heading",
                "TOKEN_RECOMBINATION",
                None,
            ),
            (
                "table row",
                {**base_table, "row_dimensions": ["application", "quantum flux"]},
                table_report,
                packet(),
                "R1.primary_operation.row_dimensions[1]",
                "VERBATIM_CONTIGUOUS",
                None,
            ),
            (
                "internal link anchor",
                {**base_link, "anchor_intent": "quantum flux"},
                link_report,
                packet(page(), page("P2", h1=("Pump Selection",))),
                "R1.primary_operation.anchor_intent",
                "VERBATIM_CONTIGUOUS",
                None,
            ),
            (
                "new resource title",
                {**base_resource, "proposed_title": "Quantum Flux Guide"},
                resource_report,
                packet(),
                "R1.primary_operation.proposed_title",
                "TOKEN_RECOMBINATION",
                None,
            ),
            (
                "new resource subject",
                {**base_resource, "content_points": [point("P1.CP_99")]},
                resource_report,
                packet(),
                "R1.primary_operation.content_points[0].subject",
                "VERBATIM_CONTIGUOUS",
                "P1.CP_99",
            ),
            (
                "nested table row",
                {
                    **base_resource,
                    "comparison_table_brief": {
                        "column_headers": ["material selection", "port size"],
                        "row_dimensions": ["quantum flux"],
                    },
                },
                resource_report,
                packet(),
                "R1.primary_operation.comparison_table_brief.row_dimensions[0]",
                "VERBATIM_CONTIGUOUS",
                None,
            ),
        )

        for name, raw, report, site, field_path, mode, candidate_id in cases:
            with self.subTest(name=name):
                prompt = build_change_plan_prompt(ChangePlanInput(site, report))
                if candidate_id is not None:
                    candidate_set = prompt.content_point_candidate_sets[0]
                    origin_ref = candidate_id.split(".", 1)[0]
                    prompt = replace(
                        prompt,
                        content_point_candidate_sets=(
                            OpportunityContentPointCandidates(
                                candidate_set.opportunity_ref,
                                (*candidate_set.candidates, ContentPointCandidate(
                                    candidate_id,
                                    "quantum flux",
                                    origin_ref,
                                )),
                            ),
                        ),
                    )
                invalid = generated([raw])
                writer = ScriptedWriter(invalid, invalid)
                workflow = ChangePlanWorkflow(writer)
                legacy_comparison = raw["operation_type"] == "ADD_COMPARISON_TABLE" or raw.get("comparison_table_brief") is not None
                if legacy_comparison:
                    # V1 lexical diagnostics remain inspectable; execution is unavailable.
                    provider_raw = json.loads(invalid.text)["opportunity_operations"]["R1"]["primary_operation"]
                    specification, failure = workflow._parse_specification(
                        provider_raw, opportunity_ref="R1",
                        field_path="R1.primary_operation", prompt=prompt,
                    )
                    self.assertIsNone(failure)
                    violation = diagnose_grounding_violation(
                        specification, prompt.catalog, field_path="R1.primary_operation",
                    )
                else:
                    with patch(
                        "foreign_trade_geo_agent.workflows.change_plan.build_change_plan_prompt",
                        return_value=prompt,
                    ):
                        result = await workflow.run(site, report)

                    self.assertEqual(result.error, "CONTENT_NOT_GROUNDED")
                    self.assertEqual(result.writer_attempt_count, 2)
                    self.assertEqual(len(writer.prompts), 2)
                    violation = workflow.last_grounding_violation
                    self.assertIs(workflow.run_diagnostics.grounding_violation, violation)
                self.assertIsNotNone(violation)
                self.assertEqual(violation.opportunity_ref, "R1")
                self.assertEqual(violation.slot, "primary_operation")
                self.assertEqual(violation.operation_type.value, raw["operation_type"])
                self.assertEqual(violation.field_path, field_path)
                self.assertEqual(violation.grounding_mode.value, mode)
                source_only = raw["operation_type"] in {
                    "ADD_SECTION",
                    "CREATE_NEW_RESOURCE",
                } and field_path.endswith(("proposed_heading", "proposed_title"))
                expected_refs = tuple(
                    raw["source_refs"]
                    if source_only
                    else raw["page_refs"] + raw["source_refs"]
                )
                self.assertEqual(violation.cited_ref_ids, expected_refs)
                self.assertNotIn("quantum flux", repr(violation).casefold())
                self.assertNotIn("chemical compatibility pump guide", repr(violation).casefold())
                if mode == "VERBATIM_CONTIGUOUS":
                    self.assertFalse(violation.contiguous_match)
                    self.assertIsNone(violation.token_coverage_pass)
                else:
                    self.assertIsNone(violation.contiguous_match)
                    self.assertFalse(violation.token_coverage_pass)
                    self.assertGreater(violation.normalized_token_count, 0)
                    self.assertLess(
                        violation.matched_token_count,
                        violation.normalized_token_count,
                    )

    async def test_success_and_non_grounding_final_failure_clear_grounding_descriptor(self) -> None:
        valid_workflow = ChangePlanWorkflow(FakeWriter(generated([expand()])))
        valid = await valid_workflow.run(packet(), opportunity_report())
        self.assertEqual(valid.status, ChangePlanStatus.SUCCESS)
        self.assertIsNone(valid_workflow.last_grounding_violation)

        report = opportunity_report(
            opportunity(action_codes=(ContentOpportunityActionCode.CREATE_SUPPORTING_RESOURCE,))
        )
        invalid_heading = supporting_resource(proposed_title="Quantum Flux Guide")
        malformed = ChangePlanGeneration(
            "fake", "fake", ChangePlanGenerationStatus.SUCCESS, "{", None
        )
        workflow = ChangePlanWorkflow(
            ScriptedWriter(generated([invalid_heading]), malformed)
        )
        result = await workflow.run(packet(), report)
        self.assertEqual(result.error, "JSON_FORMAT")
        self.assertEqual(result.writer_attempt_count, 2)
        self.assertIsNone(workflow.last_grounding_violation)
        self.assertFalse(hasattr(result, "grounding_violation"))

    def test_locator_candidates_are_deterministic_bounded_and_keep_every_page_level(self) -> None:
        pages = tuple(
            page(
                f"P{page_number}",
                h1=(),
                h2=tuple(
                    f"P{page_number} heading {heading_number}"
                    for heading_number in range(1, 13)
                ),
            )
            for page_number in range(1, 6)
        )
        report = opportunity_report(
            opportunity(page_refs=("P1", "P2", "P3", "P4", "P5"))
        )

        first = json.loads(
            build_change_plan_prompt(ChangePlanInput(packet(*pages), report)).material_json()
        )["opportunities"][0]["locator_candidates"]
        second = json.loads(
            build_change_plan_prompt(ChangePlanInput(packet(*pages), report)).material_json()
        )["opportunities"][0]["locator_candidates"]

        self.assertEqual(first, second)
        self.assertEqual(len(first), 24)
        self.assertEqual(
            [item["id"] for item in first[:5]],
            [f"P{page_number}.LOC_00" for page_number in range(1, 6)],
        )
        for page_number in range(1, 6):
            page_candidates = [
                item for item in first if item["page_ref"] == f"P{page_number}"
            ]
            self.assertEqual(page_candidates[0]["locator_kind"], "PAGE_LEVEL")
            self.assertIsNone(page_candidates[0]["target_heading"])
            self.assertLessEqual(
                sum(
                    item["locator_kind"] == "EXACT_OBSERVED_HEADING"
                    for item in page_candidates
                ),
                8,
            )

    def test_page_level_candidate_exists_when_page_has_no_visible_heading(self) -> None:
        empty_heading_page = page("P1", h1=(), h2=(), structured=())

        material = json.loads(
            build_change_plan_prompt(
                ChangePlanInput(packet(empty_heading_page), opportunity_report())
            ).material_json()
        )

        self.assertEqual(
            material["opportunities"][0]["locator_candidates"],
            [
                {
                    "id": "P1.LOC_00",
                    "locator_kind": "PAGE_LEVEL",
                    "page_ref": "P1",
                    "target_heading": None,
                }
            ],
        )

    async def test_insert_operations_materialize_bounded_locator_refs(self) -> None:
        site = packet(page("P4"))
        cases = (
            (
                {
                    **transient_common(
                        "EXPAND_SECTION",
                        action="EXPAND_PAGE_SECTION",
                        page_refs=["P4"],
                        locator_ref="P4.LOC_00",
                    ),
                    "content_points": [point("P4.CP_02")],
                },
                (SectionLocatorKind.PAGE_LEVEL, "P4", None),
            ),
            (
                {
                    **transient_common(
                        "EXPAND_SECTION",
                        action="EXPAND_PAGE_SECTION",
                        page_refs=["P4"],
                        locator_ref="P4.LOC_02",
                    ),
                    "content_points": [point("P4.CP_02")],
                },
                (
                    SectionLocatorKind.EXACT_OBSERVED_HEADING,
                    "P4",
                    "Chemical Compatibility",
                ),
            ),
            (
                {
                    **transient_common(
                        "ADD_SECTION",
                        action="ADD_BUYER_GUIDANCE",
                        page_refs=["P4"],
                        locator_ref="P4.LOC_02",
                    ),
                    "section_purpose": "BUYER_GUIDANCE",
                    "proposed_heading": "Chemical Compatibility Guide",
                    "content_points": [point("P4.CP_02")],
                },
                (
                    SectionLocatorKind.EXACT_OBSERVED_HEADING,
                    "P4",
                    "Chemical Compatibility",
                ),
            ),
            (
                {
                    **transient_common(
                        "ADD_COMPARISON_TABLE",
                        action="ADD_COMPARISON_TABLE",
                        page_refs=["P4"],
                        locator_ref="P4.LOC_02",
                    ),
                    "proposed_heading": "Pump Comparison",
                    "column_headers": ["material selection", "port size"],
                    "row_dimensions": ["application"],
                },
                (
                    SectionLocatorKind.EXACT_OBSERVED_HEADING,
                    "P4",
                    "Chemical Compatibility",
                ),
            ),
        )
        reports = (
            opportunity_report(opportunity(page_refs=("P4",))),
            opportunity_report(opportunity(page_refs=("P4",))),
            opportunity_report(
                opportunity(
                    action_codes=(ContentOpportunityActionCode.ADD_BUYER_GUIDANCE,),
                    page_refs=("P4",),
                )
            ),
            opportunity_report(
                opportunity(
                    action_codes=(ContentOpportunityActionCode.ADD_COMPARISON_TABLE,),
                    page_refs=("P4",),
                )
            ),
        )

        for (raw, expected), report in zip(cases, reports):
            with self.subTest(operation_type=raw["operation_type"]):
                result, _ = await run_one(raw, site=site, report=report)
                if raw["operation_type"] == "ADD_COMPARISON_TABLE":
                    self.assertEqual(result.error, "COMPARISON_UNAVAILABLE")
                    prompt = build_change_plan_prompt(ChangePlanInput(site, report))
                    provider_raw = json.loads(generated([raw]).text)["opportunity_operations"]["R1"]["primary_operation"]
                    specification, failure = ChangePlanWorkflow(FakeWriter(None))._parse_specification(
                        provider_raw, opportunity_ref="R1", field_path="R1.primary_operation", prompt=prompt,
                    )
                    self.assertIsNone(failure)
                    locator, error = derive_section_locator(specification, prompt.catalog)
                    self.assertIsNone(error)
                    self.assertEqual((locator.locator_kind, locator.page_ref, locator.observed_heading), expected)
                    self.assertEqual(locator.observed_heading_kind, ObservedHeadingKind.H2)
                    self.assertTrue(locator.observed_context)
                    continue
                self.assertEqual(result.status, ChangePlanStatus.SUCCESS)
                locator = result.operations[0].locator
                self.assertEqual(
                    (locator.locator_kind, locator.page_ref, locator.observed_heading),
                    expected,
                )
                if locator.locator_kind is SectionLocatorKind.EXACT_OBSERVED_HEADING:
                    self.assertEqual(locator.observed_heading_kind, ObservedHeadingKind.H2)
                    self.assertTrue(locator.observed_context)
                if raw["operation_type"] == "ADD_SECTION":
                    self.assertEqual(
                        result.operations[0].proposed_heading,
                        "Chemical Compatibility Guide",
                    )

    async def test_locator_ref_failures_are_fail_closed_without_retry(self) -> None:
        unknown = transient_expand(locator_ref="P1.LOC_99")
        writer = ScriptedWriter(generated([unknown]), generated([transient_expand()]))

        result = await ChangePlanWorkflow(writer).run(packet(), opportunity_report())

        self.assertEqual(result.error, "TARGET_LOCATOR_INVALID")
        self.assertEqual(result.writer_attempt_count, 1)
        self.assertEqual(len(writer.prompts), 1)

        site = packet(page("P1"), page("P2"))
        cross_report = opportunity_report(
            opportunity("R1", page_refs=("P1",)),
            opportunity("R2", page_refs=("P2",)),
        )
        cross_r = transient_expand(locator_ref="P2.LOC_00")
        cross_r_result, _ = await run_one(cross_r, site=site, report=cross_report)
        self.assertEqual(cross_r_result.error, "EVIDENCE_USE_NOT_ALLOWED")

        same_r_report = opportunity_report(opportunity(page_refs=("P1", "P2")))
        omitted_page = transient_expand(page_refs=["P1"], locator_ref="P2.LOC_00")
        omitted_result, _ = await run_one(
            omitted_page,
            site=site,
            report=same_r_report,
        )
        self.assertEqual(omitted_result.error, "EVIDENCE_USE_NOT_ALLOWED")

    async def test_fixed_locators_are_derived_and_provider_locator_fields_are_rejected(self) -> None:
        reorder = {
            **transient_common(
                "PROPOSE_SECTION_REORDER",
                action="REORGANIZE_PAGE_SECTIONS",
            ),
            "ordered_headings": ["Chemical Compatibility", "Maintenance"],
        }
        reorder_report = opportunity_report(
            opportunity(
                action_codes=(ContentOpportunityActionCode.REORGANIZE_PAGE_SECTIONS,)
            )
        )
        reorder_result, _ = await run_one(reorder, report=reorder_report)
        self.assertEqual(reorder_result.status, ChangePlanStatus.SUCCESS)
        self.assertEqual(
            (
                reorder_result.operations[0].locator.locator_kind,
                reorder_result.operations[0].locator.page_ref,
                reorder_result.operations[0].locator.observed_heading,
            ),
            (SectionLocatorKind.PAGE_LEVEL, "P1", None),
        )

        internal_link = {
            **transient_common(
                "ADD_INTERNAL_LINK",
                action="ADD_INTERNAL_LINK",
                page_refs=["P1", "P2"],
            ),
            "source_page_ref": "P1",
            "target_page_ref": "P2",
            "anchor_intent": "chemical compatibility",
        }
        link_report = opportunity_report(
            opportunity(
                action_codes=(ContentOpportunityActionCode.ADD_INTERNAL_LINK,),
                page_refs=("P1", "P2"),
            )
        )
        link_result, _ = await run_one(internal_link, report=link_report)
        self.assertEqual(link_result.status, ChangePlanStatus.SUCCESS)
        self.assertEqual(link_result.operations[0].locator.page_ref, "P1")
        self.assertEqual(
            link_result.operations[0].locator.locator_kind,
            SectionLocatorKind.PAGE_LEVEL,
        )

        new_resource = {
            **transient_common(
                "CREATE_NEW_RESOURCE",
                action="CREATE_SUPPORTING_RESOURCE",
            ),
            "page_refs": [],
            "resource_purpose": "SUPPORTING_RESOURCE",
            "proposed_title": "Chemical Compatibility Guide",
            "outline_headings": ["Material Selection", "Application"],
            "content_points": [point("S1.CP_02")],
            "suggested_source_page_refs": [],
            "comparison_table_brief": None,
        }
        resource_report = opportunity_report(
            opportunity(
                action_codes=(ContentOpportunityActionCode.CREATE_SUPPORTING_RESOURCE,),
                page_refs=(),
                opportunity_type=ContentOpportunityType.NEW_SUPPORTING_CONTENT,
            )
        )
        resource_result, _ = await run_one(new_resource, report=resource_report)
        self.assertEqual(resource_result.status, ChangePlanStatus.SUCCESS)
        self.assertEqual(
            (
                resource_result.operations[0].locator.locator_kind,
                resource_result.operations[0].locator.page_ref,
                resource_result.operations[0].locator.observed_heading,
            ),
            (SectionLocatorKind.NEW_PAGE, None, None),
        )

        legacy_fields = {
            "locator_kind": "PAGE_LEVEL",
            "target_page_ref": "P1",
            "target_heading": None,
        }
        for base in (transient_expand(), reorder, internal_link, new_resource):
            with self.subTest(operation_type=base["operation_type"]):
                rejected, _ = await run_one(
                    {**base, **legacy_fields},
                    report={
                        "PROPOSE_SECTION_REORDER": reorder_report,
                        "ADD_INTERNAL_LINK": link_report,
                        "CREATE_NEW_RESOURCE": resource_report,
                    }.get(base["operation_type"], opportunity_report()),
                )
                self.assertEqual(rejected.error, "FIELD_CONTRACT")

    async def test_retry_is_narrowed_to_provider_fixable_locator_semantics(self) -> None:
        reorder_report = opportunity_report(
            opportunity(
                action_codes=(ContentOpportunityActionCode.REORGANIZE_PAGE_SECTIONS,)
            )
        )
        bad_reorder = {
            **transient_common(
                "PROPOSE_SECTION_REORDER",
                action="REORGANIZE_PAGE_SECTIONS",
            ),
            "ordered_headings": ["Chemical Compatibility", "Invented"],
        }
        good_reorder = {
            **bad_reorder,
            "ordered_headings": ["Chemical Compatibility", "Maintenance"],
        }
        reorder_writer = ScriptedWriter(
            generated([bad_reorder]), generated([good_reorder])
        )
        reorder_result = await ChangePlanWorkflow(reorder_writer).run(
            packet(), reorder_report
        )
        self.assertEqual(reorder_result.status, ChangePlanStatus.SUCCESS)
        self.assertEqual(len(reorder_writer.prompts), 2)
        self.assertEqual(
            json.loads(reorder_writer.prompts[1].material_json())["contract"][
                "retry_feedback"
            ]["locator_rule"],
            "REORDER_HEADING_NOT_OBSERVED_ON_TARGET_PAGE",
        )

    def test_content_point_candidate_catalog_is_deterministic_bounded_and_filtered(self) -> None:
        structured = StructuredContentBlock(
            StructuredContentKind.LIST,
            items=(
                "Material Selection",
                "material   selection",
                "x" * 121,
                "<b>unsafe</b>",
                "https://example.com/unsafe",
                "No FAQ available",
            ),
        )
        site = packet(
            page(
                h1=("Industrial Pumps",),
                h2=("Industrial Pumps", "Chemical Compatibility"),
                structured=(structured,),
            )
        )
        change_input = ChangePlanInput(site, opportunity_report())

        first = build_change_plan_prompt(change_input)
        second = build_change_plan_prompt(change_input)
        first_candidates = first.content_point_candidates_for("R1")
        second_candidates = second.content_point_candidates_for("R1")

        self.assertEqual(first_candidates, second_candidates)
        self.assertEqual(
            tuple(item.candidate_id for item in first_candidates),
            tuple(item.candidate_id for item in second_candidates),
        )
        normalized = tuple(" ".join(item.text.casefold().split()) for item in first_candidates)
        self.assertEqual(len(normalized), len(set(normalized)))
        self.assertEqual(normalized.count("industrial pumps"), 1)
        self.assertIn("material selection", normalized)
        self.assertNotIn("x" * 121, normalized)
        self.assertFalse(any("<b>" in item.text for item in first_candidates))
        self.assertFalse(any("https://" in item.text for item in first_candidates))
        self.assertFalse(any("no faq" in item.text.casefold() for item in first_candidates))

    async def test_s_candidate_materializes_before_final_validation(self) -> None:
        raw = expand(
            content_points=[{"intent": "EXPLAIN", "subject_ref": "S1.CP_02"}]
        )
        writer = FakeWriter(generated([raw]))
        expected = build_change_plan_prompt(
            ChangePlanInput(packet(), opportunity_report())
        ).content_point_candidate("R1", "S1.CP_02")
        self.assertIsNotNone(expected)

        with patch(
            "foreign_trade_geo_agent.workflows.change_plan.validate_and_finalize_specification",
            wraps=validate_and_finalize_specification,
        ) as validator:
            result = await ChangePlanWorkflow(writer).run(packet(), opportunity_report())

        self.assertEqual(result.status, ChangePlanStatus.SUCCESS)
        self.assertEqual(
            result.operations[0].content_points[0].subject,
            expected.text,
        )
        validator.assert_called_once()

    async def test_p_candidate_materializes_exact_observed_text(self) -> None:
        raw = expand(
            content_points=[{"intent": "DESCRIBE", "subject_ref": "P1.CP_02"}]
        )

        result, _ = await run_one(raw)

        self.assertEqual(result.status, ChangePlanStatus.SUCCESS)
        self.assertEqual(
            result.operations[0].content_points[0].subject,
            "Chemical Compatibility",
        )

    async def test_unknown_candidate_id_fails_closed(self) -> None:
        raw = expand(
            content_points=[{"intent": "EXPLAIN", "subject_ref": "S1.CP_99"}]
        )

        result, _ = await run_one(raw)

        self.assertEqual(result.status, ChangePlanStatus.INVALID_OUTPUT)
        self.assertEqual(result.error, "FIELD_CONTRACT")

    async def test_candidate_origin_must_be_in_operation_references(self) -> None:
        raw = expand(
            source_refs=[],
            content_points=[{"intent": "EXPLAIN", "subject_ref": "S1.CP_02"}],
        )

        result, _ = await run_one(raw)

        self.assertEqual(result.status, ChangePlanStatus.INVALID_OUTPUT)
        self.assertEqual(result.error, "EVIDENCE_USE_NOT_ALLOWED")

    async def test_candidate_from_another_opportunity_fails_closed(self) -> None:
        report = opportunity_report(
            opportunity("R1", page_refs=("P1",), source_refs=("S1",)),
            opportunity("R2", page_refs=("P2",), source_refs=("S2",)),
        )
        raw = expand(
            content_points=[{"intent": "EXPLAIN", "subject_ref": "S2.CP_02"}]
        )

        result, _ = await run_one(raw, report=report)

        self.assertEqual(result.status, ChangePlanStatus.INVALID_OUTPUT)
        self.assertEqual(result.error, "EVIDENCE_USE_NOT_ALLOWED")

    async def test_provider_content_point_rejects_legacy_subject_field(self) -> None:
        result, _ = await run_one(
            expand(
                content_points=[
                    {"intent": "EXPLAIN", "subject": "chemical compatibility"}
                ]
            )
        )

        self.assertEqual(result.status, ChangePlanStatus.INVALID_OUTPUT)
        self.assertEqual(result.error, "FIELD_CONTRACT")

    def test_material_exposes_compact_candidates_per_opportunity(self) -> None:
        prompt = build_change_plan_prompt(ChangePlanInput(packet(), opportunity_report()))
        material = json.loads(prompt.material_json())
        candidates = material["opportunities"][0]["content_point_candidates"]

        selected = next(item for item in candidates if item["id"] == "S1.CP_02")
        self.assertEqual(selected["origin"], "S1")
        self.assertLessEqual(len(selected["text"]), 120)
        self.assertLessEqual(len(candidates), 12)

    async def test_provider_slots_normalize_primary_and_secondary_operations(self) -> None:
        writer = FakeWriter(
            generated_slots(
                expand(),
                expand(content_points=[point("material selection")]),
            )
        )

        result = await ChangePlanWorkflow(writer).run(packet(), opportunity_report())

        self.assertEqual(result.status, ChangePlanStatus.SUCCESS)
        self.assertEqual(len(result.operations), 2)
        self.assertEqual(tuple(item.change_id for item in result.operations), ("C1", "C2"))
        self.assertTrue(all(item.opportunity_ref == "R1" for item in result.operations))

    async def test_provider_slots_allow_primary_without_secondary(self) -> None:
        writer = FakeWriter(generated_slots(expand()))

        result = await ChangePlanWorkflow(writer).run(packet(), opportunity_report())

        self.assertEqual(result.status, ChangePlanStatus.SUCCESS)
        self.assertEqual(len(result.operations), 1)

    async def test_provider_slots_reject_a_third_slot_without_truncation(self) -> None:
        third = dict(expand())
        third.pop("opportunity_ref", None)
        writer = FakeWriter(
            generated_slots(
                expand(),
                expand(),
                extra_slots={"tertiary_operation": third},
            )
        )

        result = await ChangePlanWorkflow(writer).run(packet(), opportunity_report())

        self.assertEqual(result.status, ChangePlanStatus.INVALID_OUTPUT)
        self.assertEqual(result.error, "FIELD_CONTRACT")
        self.assertEqual(result.operations, ())

    async def test_new_resource_page_bindings_derive_both_domain_ref_sets(self) -> None:
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
            "content_points": [point()],
            "page_bindings": [
                {"page_ref": "P1", "suggested_source": True},
                {"page_ref": "P2", "suggested_source": False},
            ],
            "comparison_table_brief": None,
        }
        raw.pop("page_refs")
        report = opportunity_report(
            opportunity(
                action_codes=(ContentOpportunityActionCode.CREATE_SUPPORTING_RESOURCE,),
                page_refs=("P1", "P2"),
                opportunity_type=ContentOpportunityType.NEW_SUPPORTING_CONTENT,
            )
        )
        writer = FakeWriter(generated_slots(raw))

        result = await ChangePlanWorkflow(writer).run(
            packet(page("P1"), page("P2")), report
        )

        self.assertEqual(result.status, ChangePlanStatus.SUCCESS)
        operation = result.operations[0]
        self.assertEqual(operation.page_refs, ("P1", "P2"))
        self.assertEqual(
            operation.new_resource_spec.suggested_source_page_refs,
            ("P1",),
        )

    async def test_new_resource_page_bindings_reject_duplicate_unknown_and_unauthorized_pages(self) -> None:
        base = {
            **common(
                "CREATE_NEW_RESOURCE",
                action="CREATE_SUPPORTING_RESOURCE",
                target_page_ref=None,
                locator_kind="NEW_PAGE",
            ),
            "resource_purpose": "SUPPORTING_RESOURCE",
            "proposed_title": "Chemical Compatibility Guide",
            "outline_headings": ["Material Selection", "Application"],
            "content_points": [point()],
            "comparison_table_brief": None,
        }
        base.pop("page_refs")
        report = opportunity_report(
            opportunity(
                action_codes=(ContentOpportunityActionCode.CREATE_SUPPORTING_RESOURCE,),
                page_refs=("P1",),
                opportunity_type=ContentOpportunityType.NEW_SUPPORTING_CONTENT,
            )
        )
        site = packet(page("P1"), page("P2"))
        cases = (
            (
                [
                    {"page_ref": "P1", "suggested_source": True},
                    {"page_ref": "P1", "suggested_source": False},
                ],
                "FIELD_CONTRACT",
            ),
            ([{"page_ref": "P999", "suggested_source": True}], "UNKNOWN_PAGE_REFERENCE"),
            ([{"page_ref": "P2", "suggested_source": True}], "EVIDENCE_USE_NOT_ALLOWED"),
        )
        for bindings, expected in cases:
            with self.subTest(expected=expected):
                raw = {**base, "page_bindings": bindings}
                result = await ChangePlanWorkflow(
                    FakeWriter(generated_slots(raw))
                ).run(site, report)
                self.assertEqual(result.status, ChangePlanStatus.INVALID_OUTPUT)
                self.assertEqual(result.error, expected)

    async def test_new_resource_zero_page_bindings_preserve_no_page_semantics(self) -> None:
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
            "content_points": [point("S1.CP_02")],
            "page_bindings": [],
            "comparison_table_brief": None,
        }
        raw.pop("page_refs")
        report = opportunity_report(
            opportunity(
                action_codes=(ContentOpportunityActionCode.CREATE_SUPPORTING_RESOURCE,),
                page_refs=(),
                opportunity_type=ContentOpportunityType.NEW_SUPPORTING_CONTENT,
            )
        )

        result = await ChangePlanWorkflow(
            FakeWriter(generated_slots(raw))
        ).run(packet(), report)

        self.assertEqual(result.status, ChangePlanStatus.SUCCESS)
        self.assertEqual(result.operations[0].page_refs, ())
        self.assertEqual(
            result.operations[0].new_resource_spec.suggested_source_page_refs,
            (),
        )

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

    async def test_exact_heading_context_truncation_is_whitespace_normalized(self) -> None:
        section = StructuredContentBlock(
            StructuredContentKind.SECTION,
            heading="Specifications",
            text="x" * 239 + " " + "y" * 100,
        )
        source_page = page(
            h2=("Specifications",),
            structured=(section,),
        )
        raw = expand(
            locator_kind="EXACT_OBSERVED_HEADING",
            target_heading="Specifications",
            content_points=[point("P1.CP_02")],
        )
        writer = FakeWriter(generated([raw]))

        result = await ChangePlanWorkflow(writer).run(
            packet(source_page),
            opportunity_report(),
        )

        self.assertEqual(result.status, ChangePlanStatus.SUCCESS)
        observed = result.operations[0].locator.observed_context
        self.assertEqual(observed, "x" * 239)
        self.assertEqual(observed, " ".join(observed.split()))

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
            (expand(page_refs=[], target_page_ref=None), "TARGET_LOCATOR_INVALID"),
            (expand(source_refs=[]), "UNKNOWN_SOURCE_REFERENCE"),
            (expand(source_action_code="ADD_INTERNAL_LINK"), "OPERATION_NOT_ALLOWED"),
            (expand(content_points=[point("quantum flux")]), "FIELD_CONTRACT"),
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
            "content_points": [point("S1.CP_02")],
        }
        rejected, _ = await run_one(bad, report=base_report)
        self.assertEqual(rejected.error, "FIELD_CONTRACT")

    async def test_add_section_heading_must_be_new_to_target_page(self) -> None:
        report = opportunity_report(
            opportunity(action_codes=(ContentOpportunityActionCode.ADD_BUYER_GUIDANCE,))
        )
        prompt = build_change_plan_prompt(ChangePlanInput(packet(), report))
        self.assertNotIn(
            "chemical compatibility",
            {
                " ".join(candidate.text.casefold().split())
                for candidate in prompt.proposed_heading_candidates_for("R1")
            },
        )
        candidate = prompt.proposed_heading_candidates_for("R1")[0]
        raw = {
            **common("ADD_SECTION", action="ADD_BUYER_GUIDANCE"),
            "section_purpose": "BUYER_GUIDANCE",
            "proposed_heading_ref": candidate.candidate_id,
            "content_points": [point("chemical compatibility")],
        }
        result, _ = await run_one(raw, report=report)
        self.assertEqual(result.status, ChangePlanStatus.SUCCESS)
        self.assertEqual(result.operations[0].proposed_heading, candidate.text)

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

    async def test_legacy_comparison_brief_is_grounded_but_unavailable(self) -> None:
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
        self.assertEqual(result.status, ChangePlanStatus.INVALID_INPUT)
        self.assertEqual(result.error, "COMPARISON_UNAVAILABLE")
        self.assertEqual(result.operations, ())
        prompt = build_change_plan_prompt(ChangePlanInput(packet(), report))
        provider_raw = json.loads(generated([raw]).text)["opportunity_operations"]["R1"]["primary_operation"]
        spec, failure = ChangePlanWorkflow(FakeWriter(None))._parse_specification(
            provider_raw, opportunity_ref="R1", field_path="R1.primary_operation", prompt=prompt,
        )
        self.assertIsNone(failure)
        table = spec.comparison_table_specification
        self.assertEqual(table.column_headers, ("material selection", "port size"))
        self.assertEqual(table.row_dimensions, ("application", "maintenance considerations"))
        self.assertIsNone(_validate_table(table, operation_evidence_texts(spec, prompt.catalog)))
        invalids = (
            {**raw, "column_headers": ["a", "b", "c", "d", "e", "f"]},
            {**raw, "row_dimensions": ["application"] * 7},
            {**raw, "cell_values": [["42 PSI"]]},
            {**raw, "row_dimensions": ["quantum flux"]},
        )
        for changed in invalids:
            provider_raw = json.loads(generated([changed]).text)["opportunity_operations"]["R1"]["primary_operation"]
            parsed, failure = ChangePlanWorkflow(FakeWriter(None))._parse_specification(
                provider_raw, opportunity_ref="R1", field_path="R1.primary_operation", prompt=prompt,
            )
            if parsed is None:
                self.assertEqual(failure.category.value, "FIELD_CONTRACT")
            else:
                self.assertEqual(_validate_table(
                    parsed.comparison_table_specification,
                    operation_evidence_texts(parsed, prompt.catalog),
                ), "CONTENT_NOT_GROUNDED")

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

    async def test_new_resource_can_omit_pages_but_rejects_nested_table(self) -> None:
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
            "content_points": [point("S1.CP_02")],
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
        self.assertEqual(result.status, ChangePlanStatus.INVALID_OUTPUT)
        self.assertEqual(result.error, "COMPARISON_UNAVAILABLE")
        self.assertEqual(result.operations, ())
        result, _ = await run_one({**raw, "comparison_table_brief": None}, report=report)
        self.assertEqual(result.status, ChangePlanStatus.SUCCESS)
        operation = result.operations[0]
        self.assertEqual(operation.locator.locator_kind, SectionLocatorKind.NEW_PAGE)
        self.assertIsNone(operation.new_resource_spec.comparison_table_spec)
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
                if action is ContentOpportunityActionCode.ADD_COMPARISON_TABLE:
                    self.assertEqual(result.status, ChangePlanStatus.INVALID_INPUT)
                    self.assertEqual(result.error, "COMPARISON_UNAVAILABLE")
                else:
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
        self.assertEqual(result.error, "COMPARISON_UNAVAILABLE")

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
            opportunity(action_codes=(ContentOpportunityActionCode.ADD_COMPARISON_TABLE, ContentOpportunityActionCode.EXPAND_PAGE_SECTION)),
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
        text = '{"opportunity_operations":{},"opportunity_operations":{}}'
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
            (expand(page_refs=["P9"]), "EVIDENCE_USE_NOT_ALLOWED"),
            (expand(source_refs=["S9"]), "UNKNOWN_SOURCE_REFERENCE"),
            (expand(page_refs=["P2"], target_page_ref="P2"), "TARGET_LOCATOR_INVALID"),
        )
        for raw, category in cases:
            with self.subTest(raw=raw):
                result, _ = await run_one(raw, site=site, report=report)
                self.assertEqual(result.error, category)

    async def test_action_code_must_belong_to_r_and_compatibility_matrix(self) -> None:
        not_on_r = expand(source_action_code="ADD_COMPARISON_TABLE")
        result, _ = await run_one(not_on_r)
        self.assertEqual(result.error, "OPERATION_NOT_ALLOWED")

        report = opportunity_report(
            opportunity(action_codes=(ContentOpportunityActionCode.ADD_COMPARISON_TABLE, ContentOpportunityActionCode.EXPAND_PAGE_SECTION))
        )
        incompatible = expand(source_action_code="ADD_COMPARISON_TABLE")
        result, _ = await run_one(incompatible, report=report)
        self.assertEqual(result.error, "OPERATION_NOT_ALLOWED")

    def test_absence_claims_never_enter_content_point_candidates(self) -> None:
        for subject in ("missing FAQ", "lacks links", "absent comparison table", "no FAQ"):
            with self.subTest(subject=subject):
                prompt = build_change_plan_prompt(
                    ChangePlanInput(
                        packet(page(body=subject)),
                        opportunity_report(source_text=subject),
                    )
                )
                self.assertFalse(
                    any(
                        item.text == subject
                        for item in prompt.content_point_candidates_for("R1")
                    )
                )

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
            self.assertEqual(result.writer_attempt_count, 1)
            self.assertEqual(len(writer.prompts), 1)

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
                action_codes=(ContentOpportunityActionCode.ADD_BUYER_GUIDANCE,)
            )
        )
        section = {
            **common("ADD_SECTION", action="ADD_BUYER_GUIDANCE"),
            "section_purpose": "BUYER_GUIDANCE",
            "proposed_heading": "Chemical Compatibility Guide",
            "content_points": [point()],
        }
        resource = {**supporting_resource(), "source_action_code": "ADD_BUYER_GUIDANCE",
                    "resource_purpose": "BUYER_GUIDANCE"}

        result = await ChangePlanWorkflow(
            FakeWriter(generated([section, resource]))
        ).run(packet(), report)

        self.assertEqual(result.status, ChangePlanStatus.SUCCESS)
        self.assertEqual(
            tuple(item.operation_type for item in result.operations),
            (
                ChangeOperationType.ADD_SECTION,
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
            # Keep the workflow budget clear of validation/scheduler overhead;
            # this case is specifically about the inner generation deadline.
            SlowWriter(), generation_timeout=0.01, total_timeout=2.0
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
        self.assertEqual(result.error, "FIELD_CONTRACT")

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

    async def test_content_grounding_failure_retries_once_with_fixed_feedback(self) -> None:
        invalid_heading = "Quantum Flux Guide"
        report = opportunity_report(
            opportunity(action_codes=(ContentOpportunityActionCode.CREATE_SUPPORTING_RESOURCE,))
        )
        invalid = supporting_resource(proposed_title=invalid_heading)
        valid = {**invalid, "proposed_title": "Chemical Compatibility Guide"}
        writer = ScriptedWriter(
            generated([invalid]),
            generated([valid]),
        )

        result = await ChangePlanWorkflow(writer).run(packet(), report)

        self.assertEqual(result.status, ChangePlanStatus.SUCCESS)
        self.assertEqual(len(writer.prompts), 2)
        first = json.loads(writer.prompts[0].material_json())
        retry = json.loads(writer.prompts[1].material_json())
        for key in ("opportunities", "pages", "sources"):
            self.assertEqual(retry[key], first[key])
        self.assertIsNone(first["contract"]["retry_feedback"])
        self.assertEqual(
            retry["contract"]["retry_feedback"],
            {
                "validator": "CONTENT_NOT_GROUNDED",
                "required_action": (
                    "Regenerate the complete response. Copy every grounded free phrase "
                    "as one verbatim contiguous substring from the field's allowed cited "
                    "P/S evidence; do not paraphrase, combine fragments, or guess. Omit "
                    "an operation when no legal phrase exists."
                ),
            },
        )
        self.assertNotIn(invalid_heading, writer.prompts[1].material_json())

    async def test_string_length_field_contract_retries_with_exact_safe_feedback(self) -> None:
        oversized_heading = "x" * 121
        report = opportunity_report(
            opportunity(action_codes=(ContentOpportunityActionCode.CREATE_SUPPORTING_RESOURCE,)),
            source_text="Chemical Compatibility Guide",
        )
        invalid = supporting_resource(proposed_title=oversized_heading)
        valid = {**invalid, "proposed_title": "Chemical Compatibility Guide"}
        first_generation = generated([invalid])
        writer = ScriptedWriter(first_generation, generated([valid]))

        result = await ChangePlanWorkflow(writer).run(packet(), report)

        self.assertEqual(result.status, ChangePlanStatus.SUCCESS)
        self.assertEqual(len(writer.prompts), 2)
        retry_material = writer.prompts[1].material_json()
        feedback = json.loads(retry_material)["contract"]["retry_feedback"]
        self.assertEqual(
            feedback,
            {
                "validator": "FIELD_CONTRACT",
                "field_path": "R1.primary_operation.proposed_title",
                "rule_id": "STRING_LENGTH_EXCEEDED",
                "expected": {"max_chars": 120},
                "actual": {"actual_chars": 121},
                "required_action": (
                    "Previous generation violated a bounded field contract. "
                    "Regenerate the complete response and preserve all valid "
                    "references and grounding."
                ),
            },
        )
        self.assertNotIn(oversized_heading, retry_material)
        self.assertNotIn(first_generation.text or "", retry_material)

    async def test_provider_outline_field_is_rejected_without_semantic_retry(self) -> None:
        headings = [f"Heading {index}" for index in range(1, 8)]
        report = opportunity_report(
            opportunity(
                action_codes=(ContentOpportunityActionCode.CREATE_SUPPORTING_RESOURCE,),
                opportunity_type=ContentOpportunityType.NEW_SUPPORTING_CONTENT,
            ),
            source_text=" ".join([*headings, "Chemical Compatibility Guide"]),
        )
        invalid = {
            **common(
                "CREATE_NEW_RESOURCE",
                action="CREATE_SUPPORTING_RESOURCE",
                target_page_ref=None,
                locator_kind="NEW_PAGE",
            ),
            "resource_purpose": "SUPPORTING_RESOURCE",
            "proposed_title": "Chemical Compatibility Guide",
            "outline_headings": headings,
            "content_points": [point()],
            "suggested_source_page_refs": ["P1"],
            "comparison_table_brief": None,
        }
        writer = ScriptedWriter(generated([invalid]))
        workflow = ChangePlanWorkflow(writer)

        result = await workflow.run(packet(), report)

        self.assertEqual(result.status, ChangePlanStatus.INVALID_OUTPUT)
        self.assertEqual(result.error, "FIELD_CONTRACT")
        self.assertEqual(result.writer_attempt_count, 1)
        self.assertEqual(len(writer.prompts), 1)
        self.assertIsNotNone(workflow.last_field_contract_violation)
        self.assertEqual(
            workflow.last_field_contract_violation.rule_id.value,
            "OPERATION_KEYS_INVALID",
        )

    async def test_empty_content_points_is_type_b_and_retries_once(self) -> None:
        invalid = generated([expand(content_points=[])])
        writer = ScriptedWriter(invalid, generated([expand()]))

        result = await ChangePlanWorkflow(writer).run(packet(), opportunity_report())

        self.assertEqual(result.status, ChangePlanStatus.SUCCESS)
        self.assertEqual(len(writer.prompts), 2)
        self.assertEqual(
            json.loads(writer.prompts[1].material_json())["contract"]["retry_feedback"],
            {
                "validator": "FIELD_CONTRACT",
                "field_path": "R1.primary_operation.content_points",
                "rule_id": "LIST_COUNT_BELOW_MIN",
                "expected": {"min_count": 1},
                "actual": {"actual_count": 0},
                "required_action": (
                    "Previous generation violated a bounded field contract. "
                    "Regenerate the complete response and preserve all valid "
                    "references and grounding."
                ),
            },
        )

    async def test_type_c_field_contracts_fail_once_with_sanitized_descriptors(self) -> None:
        third = dict(expand())
        third.pop("opportunity_ref", None)
        wrong_root = ChangePlanGeneration(
            "fake",
            "fake",
            ChangePlanGenerationStatus.SUCCESS,
            json.dumps({"operations": []}),
            None,
        )
        cases = (
            (
                generated([{**expand(), "html": "<p>provider text</p>"}]),
                "OPERATION_KEYS_INVALID",
                "R1.primary_operation",
            ),
            (
                generated(
                    [
                        expand(
                            content_points=[
                                {"intent": "EXPLAIN", "subject": "provider text"}
                            ]
                        )
                    ]
                ),
                "CONTENT_POINT_SHAPE_INVALID",
                "R1.primary_operation.content_points[0]",
            ),
            (
                generated([expand(operation_type="WRITE_ARTICLE")]),
                "ENUM_INVALID",
                "R1.primary_operation.operation_type",
            ),
            (
                generated_slots(
                    expand(),
                    expand(content_points=[point("material selection")]),
                    extra_slots={"tertiary_operation": third},
                ),
                "SLOT_KEYS_INVALID",
                "R1",
            ),
            (wrong_root, "TOP_LEVEL_KEYS_INVALID", "$"),
        )
        for first_generation, rule_id, field_path in cases:
            with self.subTest(rule_id=rule_id):
                writer = ScriptedWriter(first_generation, generated([]))
                workflow = ChangePlanWorkflow(writer)

                result = await workflow.run(packet(), opportunity_report())

                self.assertEqual(result.status, ChangePlanStatus.INVALID_OUTPUT)
                self.assertEqual(result.error, "FIELD_CONTRACT")
                self.assertEqual(result.writer_attempt_count, 1)
                self.assertEqual(len(writer.prompts), 1)
                violation = getattr(workflow, "last_field_contract_violation", None)
                self.assertIsNotNone(violation)
                self.assertIs(
                    workflow.run_diagnostics.field_contract_violation,
                    violation,
                )
                self.assertEqual(violation.rule_id.value, rule_id)
                self.assertEqual(violation.field_path, field_path)
                self.assertEqual(violation.repair_class.value, "TYPE_C")
                self.assertNotIn("provider text", repr(violation))

    async def test_type_a_unknown_subject_candidate_fails_once(self) -> None:
        writer = ScriptedWriter(
            generated([expand(content_points=[point("P1.CP_99")])]),
            generated([expand()]),
        )
        workflow = ChangePlanWorkflow(writer)

        result = await workflow.run(packet(), opportunity_report())

        self.assertEqual(result.status, ChangePlanStatus.INVALID_OUTPUT)
        self.assertEqual(result.error, "FIELD_CONTRACT")
        self.assertEqual(result.writer_attempt_count, 1)
        self.assertEqual(len(writer.prompts), 1)
        violation = workflow.last_field_contract_violation
        self.assertIsNotNone(violation)
        self.assertEqual(violation.rule_id.value, "SUBJECT_REF_INVALID")
        self.assertEqual(violation.repair_class.value, "TYPE_A")
        self.assertEqual(
            violation.field_path,
            "R1.primary_operation.content_points[0].subject_ref",
        )

    async def test_second_type_b_failure_stops_after_one_retry_with_second_descriptor(self) -> None:
        first = generated([expand(content_points=[])])
        second = generated([expand(content_points=[point()] * 6)])
        writer = ScriptedWriter(first, second)
        workflow = ChangePlanWorkflow(writer)

        result = await workflow.run(packet(), opportunity_report())

        self.assertEqual(result.status, ChangePlanStatus.INVALID_OUTPUT)
        self.assertEqual(result.error, "FIELD_CONTRACT")
        self.assertEqual(result.writer_attempt_count, 2)
        self.assertEqual(len(writer.prompts), 2)
        violation = getattr(workflow, "last_field_contract_violation", None)
        self.assertIsNotNone(violation)
        self.assertEqual(violation.rule_id.value, "LIST_COUNT_EXCEEDED")
        self.assertEqual(violation.field_path, "R1.primary_operation.content_points")
        self.assertEqual(violation.actual, (("actual_count", 6),))

    async def test_second_attempt_returns_its_real_non_field_category(self) -> None:
        malformed = ChangePlanGeneration(
            "fake", "fake", ChangePlanGenerationStatus.SUCCESS, "{", None
        )
        writer = ScriptedWriter(generated([expand(content_points=[])]), malformed)
        workflow = ChangePlanWorkflow(writer)

        result = await workflow.run(packet(), opportunity_report())

        self.assertEqual(result.status, ChangePlanStatus.INVALID_OUTPUT)
        self.assertEqual(result.error, "JSON_FORMAT")
        self.assertEqual(result.final_validation_category, "JSON_FORMAT")
        self.assertEqual(result.writer_attempt_count, 2)
        self.assertEqual(len(writer.prompts), 2)
        self.assertIsNone(
            getattr(workflow, "last_field_contract_violation", None)
        )

    async def test_unknown_locator_ref_is_not_retried(self) -> None:
        invalid_heading = "Unobserved heading"
        first_generation = generated(
            [
                expand(
                    locator_kind="EXACT_OBSERVED_HEADING",
                    target_heading=invalid_heading,
                )
            ]
        )
        writer = ScriptedWriter(first_generation, generated([expand()]))
        workflow = ChangePlanWorkflow(writer)

        result = await workflow.run(packet(), opportunity_report())

        self.assertEqual(result.status, ChangePlanStatus.INVALID_OUTPUT)
        self.assertEqual(result.error, "TARGET_LOCATOR_INVALID")
        self.assertEqual(result.writer_attempt_count, 1)
        self.assertEqual(len(writer.prompts), 1)
        violation = workflow.last_target_locator_violation
        self.assertIsNotNone(violation)
        self.assertEqual(violation.field_path, "R1.primary_operation.locator_ref")
        self.assertIsNone(violation.repair_rule)

    async def test_final_repairable_locator_failure_exposes_exact_field(self) -> None:
        report = opportunity_report(
            opportunity(
                action_codes=(ContentOpportunityActionCode.REORGANIZE_PAGE_SECTIONS,)
            )
        )
        invalid = generated(
            [
                {
                    **transient_common(
                        "PROPOSE_SECTION_REORDER",
                        action="REORGANIZE_PAGE_SECTIONS",
                    ),
                    "ordered_headings": ["Chemical Compatibility", "Invented"],
                }
            ]
        )
        workflow = ChangePlanWorkflow(ScriptedWriter(invalid, invalid))

        result = await workflow.run(packet(), report)

        self.assertEqual(result.error, "TARGET_LOCATOR_INVALID")
        violation = workflow.last_target_locator_violation
        self.assertIsNotNone(violation)
        self.assertEqual(
            violation.field_path,
            "R1.primary_operation.ordered_headings",
        )
        self.assertIs(
            violation.repair_rule,
            TargetLocatorRepairRule.REORDER_HEADING_NOT_OBSERVED_ON_TARGET_PAGE,
        )

    async def test_second_content_grounding_failure_remains_failed(self) -> None:
        report = opportunity_report(
            opportunity(action_codes=(ContentOpportunityActionCode.CREATE_SUPPORTING_RESOURCE,))
        )
        raw = supporting_resource(proposed_title="Quantum Flux Guide")
        invalid = generated([raw])
        writer = ScriptedWriter(invalid, invalid)

        result = await ChangePlanWorkflow(writer).run(packet(), report)

        self.assertEqual(result.status, ChangePlanStatus.INVALID_OUTPUT)
        self.assertEqual(result.error, "CONTENT_NOT_GROUNDED")
        self.assertEqual(len(writer.prompts), 2)

    async def test_non_allowlisted_invalid_generation_is_not_retried(self) -> None:
        unknown_source = expand(source_refs=["S9"])
        writer = ScriptedWriter(generated([unknown_source]))
        result = await ChangePlanWorkflow(writer).run(packet(), opportunity_report())

        self.assertEqual(result.status, ChangePlanStatus.INVALID_OUTPUT)
        self.assertEqual(result.error, "UNKNOWN_SOURCE_REFERENCE")
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

    async def test_add_section_requires_heading_ref_and_materializes_candidate(self) -> None:
        report = opportunity_report(
            opportunity(action_codes=(ContentOpportunityActionCode.ADD_BUYER_GUIDANCE,))
        )
        prompt = build_change_plan_prompt(ChangePlanInput(packet(), report))
        candidate = prompt.proposed_heading_candidates_for("R1")[0]
        raw = {
            **common("ADD_SECTION", action="ADD_BUYER_GUIDANCE"),
            "section_purpose": "BUYER_GUIDANCE",
            "proposed_heading_ref": candidate.candidate_id,
            "content_points": [point()],
        }

        result = await ChangePlanWorkflow(FakeWriter(generated([raw]))).run(packet(), report)

        self.assertEqual(result.status, ChangePlanStatus.SUCCESS)
        self.assertEqual(result.operations[0].proposed_heading, candidate.text)
        self.assertFalse(hasattr(result.operations[0], "proposed_heading_ref"))

    async def test_add_section_rejects_raw_heading_and_unknown_or_wrong_r_refs(self) -> None:
        report = opportunity_report(
            opportunity(
                "R1",
                action_codes=(ContentOpportunityActionCode.ADD_BUYER_GUIDANCE,),
                page_refs=("P1",),
            ),
            opportunity(
                "R2",
                action_codes=(ContentOpportunityActionCode.ADD_BUYER_GUIDANCE,),
                page_refs=("P2",),
            ),
        )
        base = {
            **common("ADD_SECTION", action="ADD_BUYER_GUIDANCE"),
            "section_purpose": "BUYER_GUIDANCE",
            "content_points": [point()],
        }
        invalid_payloads = (
            {**base, "proposed_heading": "Chemical Compatibility Guide"},
            {**base, "proposed_heading_ref": "P1.PH_99"},
            {**base, "proposed_heading_ref": "P2.PH_01"},
        )

        for raw in invalid_payloads:
            with self.subTest(raw=raw):
                provider_raw = dict(raw)
                provider_raw.pop("opportunity_ref", None)
                generation = ChangePlanGeneration(
                    "fake",
                    "fake",
                    ChangePlanGenerationStatus.SUCCESS,
                    json.dumps(
                        {
                            "opportunity_operations": {
                                "R1": {"primary_operation": provider_raw}
                            }
                        }
                    ),
                    None,
                )
                result = await ChangePlanWorkflow(FakeWriter(generation)).run(
                    packet(), report
                )
                self.assertEqual(result.status, ChangePlanStatus.INVALID_OUTPUT)

    async def test_add_section_candidate_page_must_match_operation_and_locator(self) -> None:
        report = opportunity_report(
            opportunity(
                action_codes=(ContentOpportunityActionCode.ADD_BUYER_GUIDANCE,),
                page_refs=("P1", "P2"),
            )
        )
        prompt = build_change_plan_prompt(ChangePlanInput(packet(), report))
        candidate = next(
            item
            for item in prompt.proposed_heading_candidates_for("R1")
            if item.page_ref == "P2"
        )
        raw = {
            **common(
                "ADD_SECTION",
                action="ADD_BUYER_GUIDANCE",
                page_refs=["P1"],
                locator_ref="P1.LOC_00",
            ),
            "section_purpose": "BUYER_GUIDANCE",
            "proposed_heading_ref": candidate.candidate_id,
            "content_points": [point()],
        }

        result = await ChangePlanWorkflow(FakeWriter(generated([raw]))).run(packet(), report)

        self.assertEqual(result.status, ChangePlanStatus.INVALID_OUTPUT)
        self.assertEqual(result.error, "EVIDENCE_USE_NOT_ALLOWED")

    def test_proposed_heading_catalog_is_bounded_deterministic_and_excludes_collisions(self) -> None:
        target = page(h2=("Chemical Compatibility Guide", "Maintenance"))
        report = opportunity_report(
            opportunity(action_codes=(ContentOpportunityActionCode.ADD_BUYER_GUIDANCE,))
        )

        first = build_change_plan_prompt(ChangePlanInput(packet(target), report))
        second = build_change_plan_prompt(ChangePlanInput(packet(target), report))
        candidates = first.proposed_heading_candidates_for("R1")

        self.assertEqual(candidates, second.proposed_heading_candidates_for("R1"))
        self.assertLessEqual(len(candidates), 16)
        self.assertTrue(all(item.page_ref == "P1" for item in candidates))
        self.assertNotIn(
            "chemical compatibility guide",
            {" ".join(item.text.casefold().split()) for item in candidates},
        )

    async def test_new_resource_outline_is_materialized_as_exactly_two_stable_headings(self) -> None:
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
            "content_points": [point()],
            "suggested_source_page_refs": ["P1"],
            "comparison_table_brief": None,
        }
        generation = generated([raw])

        first = await ChangePlanWorkflow(FakeWriter(generation)).run(packet(), report)
        second = await ChangePlanWorkflow(FakeWriter(generation)).run(packet(), report)

        self.assertEqual(first.status, ChangePlanStatus.SUCCESS)
        self.assertEqual(second.status, ChangePlanStatus.SUCCESS)
        first_outline = first.operations[0].new_resource_spec.outline_headings
        second_outline = second.operations[0].new_resource_spec.outline_headings
        self.assertEqual(len(first_outline), 2)
        self.assertEqual(first_outline, second_outline)
        self.assertFalse(hasattr(first.operations[0].new_resource_spec, "outline_heading_refs"))

    async def test_new_resource_rejects_provider_outline_headings(self) -> None:
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
            "content_points": [point()],
            "suggested_source_page_refs": ["P1"],
            "comparison_table_brief": None,
        }

        provider_raw = dict(raw)
        provider_raw.pop("opportunity_ref", None)
        page_refs = provider_raw.pop("page_refs")
        suggestions = provider_raw.pop("suggested_source_page_refs")
        provider_raw["page_bindings"] = [
            {
                "page_ref": page_ref,
                "suggested_source": page_ref in suggestions,
            }
            for page_ref in page_refs
        ]
        generation = ChangePlanGeneration(
            "fake",
            "fake",
            ChangePlanGenerationStatus.SUCCESS,
            json.dumps(
                {
                    "opportunity_operations": {
                        "R1": {"primary_operation": provider_raw}
                    }
                }
            ),
            None,
        )
        result = await ChangePlanWorkflow(FakeWriter(generation)).run(packet(), report)

        self.assertEqual(result.status, ChangePlanStatus.INVALID_OUTPUT)
        self.assertEqual(result.error, "FIELD_CONTRACT")

    def test_create_new_resource_availability_requires_two_outline_candidates(self) -> None:
        base = opportunity_report(
            opportunity(
                action_codes=(ContentOpportunityActionCode.CREATE_SUPPORTING_RESOURCE,),
                opportunity_type=ContentOpportunityType.NEW_SUPPORTING_CONTENT,
            )
        )
        for text, expected_count in (("Material Selection", 1), ("x" * 101, 0)):
            with self.subTest(expected_count=expected_count):
                source = replace(base.sources[0], title=text)
                material = replace(base.source_materials[0], title=text, content=text)
                report = replace(base, sources=(source,), source_materials=(material,))
                prompt = build_change_plan_prompt(ChangePlanInput(packet(), report))
                material_payload = json.loads(prompt.material_json())
                opportunity_payload = material_payload["opportunities"][0]

                self.assertEqual(
                    len(prompt.outline_heading_candidates_for("R1")), expected_count
                )
                self.assertNotIn(
                    "CREATE_NEW_RESOURCE",
                    opportunity_payload["allowed_operation_types"],
                )

    def test_add_section_availability_requires_a_legal_heading_candidate(self) -> None:
        base = opportunity_report(
            opportunity(action_codes=(ContentOpportunityActionCode.ADD_BUYER_GUIDANCE,))
        )
        ungrounded = "x" * 121
        source = replace(base.sources[0], title=ungrounded)
        material = replace(
            base.source_materials[0],
            title=ungrounded,
            content=ungrounded,
        )
        report = replace(base, sources=(source,), source_materials=(material,))

        prompt = build_change_plan_prompt(ChangePlanInput(packet(), report))
        opportunity_payload = json.loads(prompt.material_json())["opportunities"][0]

        self.assertEqual(prompt.proposed_heading_candidates_for("R1"), ())
        self.assertNotIn(
            "ADD_SECTION",
            opportunity_payload["allowed_operation_types"],
        )


if __name__ == "__main__":
    unittest.main()
