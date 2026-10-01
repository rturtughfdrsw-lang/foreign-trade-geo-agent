"""Strict parsing, evidence validation, and finalization for change plans."""

import asyncio
import json
import math
from dataclasses import replace

from foreign_trade_geo_agent.core.change_plan import (
    CHANGE_PLAN_LIMITATIONS,
    MAX_CHANGE_PLAN_TIMEOUT_SECONDS,
    MAX_OPERATIONS,
    MAX_OPERATIONS_PER_OPPORTUNITY,
    MAX_RAW_OUTPUT_BYTES,
    MAX_RAW_OUTPUT_CHARS,
    MAX_USER_MATERIAL_BYTES,
    MAX_USER_MATERIAL_CHARS,
    AddComparisonTableSpecification,
    AddInternalLinkSpecification,
    AddSectionSpecification,
    ChangeOperation,
    ChangeOperationType,
    ChangePlanGeneration,
    ChangePlanGenerationFailureKind,
    ChangePlanGenerationStatus,
    ChangePlanInput,
    ChangePlanPrompt,
    ChangePlanReport,
    ChangePlanSpecification,
    ChangePlanStatus,
    ChangePlanValidationCategory,
    ComparisonTableSpecification,
    ContentPointIntent,
    ContentPointSpecification,
    CreateNewResourceSpecification,
    ExpandSectionSpecification,
    InternalLinkSpecification,
    NewResourceSpecification,
    NewResourcePurpose,
    ProposeSectionReorderSpecification,
    SectionLocatorKind,
    SectionLocatorSpecification,
    SectionPurpose,
    build_change_plan_prompt,
    canonical_change_operation_identity,
    stable_change_plan_input_shape_error,
    validate_change_plan_input,
    validate_and_finalize_specification,
)
from foreign_trade_geo_agent.core.content_opportunity import (
    ContentOpportunityActionCode,
    ContentOpportunityReport,
)
from foreign_trade_geo_agent.core.ports import ChangePlanWriter
from foreign_trade_geo_agent.core.site_content import SiteContentPacket


_COMMON_FIELDS = {
    "opportunity_ref",
    "source_action_code",
    "operation_type",
    "page_refs",
    "source_refs",
    "target_page_ref",
    "locator_kind",
    "target_heading",
}

_OPERATION_FIELDS = {
    ChangeOperationType.EXPAND_SECTION: {"content_points"},
    ChangeOperationType.PROPOSE_SECTION_REORDER: {"ordered_headings"},
    ChangeOperationType.ADD_SECTION: {
        "section_purpose",
        "proposed_heading",
        "content_points",
    },
    ChangeOperationType.ADD_COMPARISON_TABLE: {
        "proposed_heading",
        "column_headers",
        "row_dimensions",
    },
    ChangeOperationType.ADD_INTERNAL_LINK: {
        "source_page_ref",
        "anchor_intent",
    },
    ChangeOperationType.CREATE_NEW_RESOURCE: {
        "resource_purpose",
        "proposed_title",
        "outline_headings",
        "content_points",
        "suggested_source_page_refs",
        "comparison_table_brief",
    },
}


def _strict_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


class ChangePlanWorkflow:
    """Create one all-or-nothing, human-reviewed change plan offline."""

    limitations = CHANGE_PLAN_LIMITATIONS

    def __init__(
        self,
        writer: ChangePlanWriter,
        *,
        generation_timeout: float = 40.0,
        total_timeout: float = 45.0,
    ) -> None:
        for name, value in (
            ("generation_timeout", generation_timeout),
            ("total_timeout", total_timeout),
        ):
            if (
                type(value) not in {int, float}
                or not math.isfinite(value)
                or not 0 < value <= MAX_CHANGE_PLAN_TIMEOUT_SECONDS
            ):
                raise ValueError(f"{name} must be finite, positive, and bounded.")
        self._writer = writer
        self._generation_timeout = float(generation_timeout)
        self._total_timeout = float(total_timeout)

    async def run(
        self,
        site_content: SiteContentPacket,
        opportunity_report: ContentOpportunityReport,
    ) -> ChangePlanReport:
        if not isinstance(site_content, SiteContentPacket) or not isinstance(
            opportunity_report,
            ContentOpportunityReport,
        ):
            return self._failure(
                ChangePlanStatus.INVALID_INPUT,
                ChangePlanValidationCategory.FIELD_CONTRACT,
            )
        try:
            return await asyncio.wait_for(
                self._run(site_content, opportunity_report),
                timeout=self._total_timeout,
            )
        except (TimeoutError, asyncio.TimeoutError):
            return self._failure(ChangePlanStatus.WORKFLOW_TIMEOUT)

    async def _run(
        self,
        site_content: SiteContentPacket,
        opportunity_report: ContentOpportunityReport,
    ) -> ChangePlanReport:
        try:
            shape_error = stable_change_plan_input_shape_error(
                site_content,
                opportunity_report,
            )
        except (AttributeError, TypeError, ValueError):
            shape_error = ChangePlanValidationCategory.FIELD_CONTRACT.value
        if shape_error is not None:
            return self._failure(
                ChangePlanStatus.INVALID_INPUT,
                ChangePlanValidationCategory(shape_error),
            )
        try:
            change_input = ChangePlanInput(site_content, opportunity_report)
        except (AttributeError, TypeError, ValueError):
            return self._failure(
                ChangePlanStatus.INVALID_INPUT,
                ChangePlanValidationCategory.FIELD_CONTRACT,
            )
        try:
            input_error = validate_change_plan_input(change_input)
        except (AttributeError, TypeError, ValueError):
            input_error = ChangePlanValidationCategory.FIELD_CONTRACT.value
        if input_error is not None:
            return self._failure(
                ChangePlanStatus.INVALID_INPUT,
                ChangePlanValidationCategory(input_error),
            )
        if not opportunity_report.opportunities:
            return ChangePlanReport(
                status=ChangePlanStatus.SUCCESS,
                operations=(),
                limitations=self.limitations,
                error=None,
            )

        try:
            prompt = build_change_plan_prompt(change_input)
        except (AttributeError, TypeError, ValueError):
            return self._failure(
                ChangePlanStatus.INVALID_INPUT,
                ChangePlanValidationCategory.FIELD_CONTRACT,
            )
        material = prompt.material_json()
        if (
            len(material) > MAX_USER_MATERIAL_CHARS
            or len(material.encode("utf-8")) > MAX_USER_MATERIAL_BYTES
        ):
            return self._failure(
                ChangePlanStatus.INPUT_TOO_LARGE,
                ChangePlanValidationCategory.INPUT_TOO_LARGE,
            )
        try:
            generation = await asyncio.wait_for(
                self._writer.write_change_plan(prompt),
                timeout=self._generation_timeout,
            )
        except (TimeoutError, asyncio.TimeoutError):
            return self._failure(ChangePlanStatus.GENERATION_FAILED)
        except Exception:
            return self._failure(ChangePlanStatus.GENERATION_FAILED)
        if not isinstance(generation, ChangePlanGeneration):
            return self._failure(ChangePlanStatus.GENERATION_FAILED)
        if generation.status is ChangePlanGenerationStatus.FAILED:
            if (
                generation.failure_kind
                is ChangePlanGenerationFailureKind.INPUT_TOO_LARGE
            ):
                return self._failure(
                    ChangePlanStatus.INPUT_TOO_LARGE,
                    ChangePlanValidationCategory.INPUT_TOO_LARGE,
                )
            return self._failure(ChangePlanStatus.GENERATION_FAILED)

        operations, error = self._parse_validate_finalize(generation.text, prompt)
        if operations is None:
            assert error is not None
            return self._failure(
                ChangePlanStatus.INVALID_OUTPUT,
                ChangePlanValidationCategory(error),
            )
        return ChangePlanReport(
            status=ChangePlanStatus.SUCCESS,
            operations=operations,
            limitations=self.limitations,
            error=None,
        )

    def _parse_validate_finalize(
        self,
        text: str | None,
        prompt: ChangePlanPrompt,
    ) -> tuple[tuple[ChangeOperation, ...] | None, str | None]:
        if text is None:
            return None, ChangePlanValidationCategory.JSON_FORMAT.value
        if (
            len(text) > MAX_RAW_OUTPUT_CHARS
            or len(text.encode("utf-8")) > MAX_RAW_OUTPUT_BYTES
        ):
            return None, ChangePlanValidationCategory.OUTPUT_TOO_LARGE.value
        try:
            payload = json.loads(text, object_pairs_hook=_strict_json_object)
        except (json.JSONDecodeError, TypeError, ValueError):
            return None, ChangePlanValidationCategory.JSON_FORMAT.value
        if type(payload) is not dict or set(payload) != {"operations"}:
            return None, ChangePlanValidationCategory.FIELD_CONTRACT.value
        raw_operations = payload["operations"]
        if type(raw_operations) is not list or len(raw_operations) > MAX_OPERATIONS:
            return None, ChangePlanValidationCategory.FIELD_CONTRACT.value

        specifications: list[ChangePlanSpecification] = []
        counts: dict[str, int] = {}
        for raw in raw_operations:
            specification, error = self._parse_specification(raw)
            if specification is None:
                return None, error
            counts[specification.opportunity_ref] = counts.get(
                specification.opportunity_ref, 0
            ) + 1
            if counts[specification.opportunity_ref] > MAX_OPERATIONS_PER_OPPORTUNITY:
                return None, ChangePlanValidationCategory.OPERATION_NOT_ALLOWED.value
            specifications.append(specification)

        # No result is exposed until every operation has passed every validator.
        provisional: list[ChangeOperation] = []
        identities: set[tuple[object, ...]] = set()
        for specification in specifications:
            operation, error = validate_and_finalize_specification(
                1, specification, prompt.catalog
            )
            if operation is None:
                return None, error
            identity = canonical_change_operation_identity(operation)
            if identity in identities:
                return None, ChangePlanValidationCategory.FIELD_CONTRACT.value
            identities.add(identity)
            provisional.append(operation)
        return tuple(
            replace(operation, change_id=f"C{number}")
            for number, operation in enumerate(provisional, start=1)
        ), None

    def _parse_specification(
        self,
        raw: object,
    ) -> tuple[ChangePlanSpecification | None, str | None]:
        if type(raw) is not dict:
            return None, ChangePlanValidationCategory.FIELD_CONTRACT.value
        try:
            operation_type = ChangeOperationType(raw.get("operation_type"))
        except (TypeError, ValueError):
            return None, ChangePlanValidationCategory.FIELD_CONTRACT.value
        if set(raw) != _COMMON_FIELDS | _OPERATION_FIELDS[operation_type]:
            return None, ChangePlanValidationCategory.FIELD_CONTRACT.value
        common, error = self._parse_common(raw, operation_type)
        if common is None:
            return None, error
        if operation_type is ChangeOperationType.EXPAND_SECTION:
            points = self._parse_content_points(raw["content_points"])
            if points is None:
                return None, ChangePlanValidationCategory.FIELD_CONTRACT.value
            return ExpandSectionSpecification(**common, content_points=points), None
        if operation_type is ChangeOperationType.PROPOSE_SECTION_REORDER:
            headings = self._parse_string_tuple(raw["ordered_headings"])
            if headings is None:
                return None, ChangePlanValidationCategory.FIELD_CONTRACT.value
            return ProposeSectionReorderSpecification(
                **common, ordered_headings=headings
            ), None
        if operation_type is ChangeOperationType.ADD_SECTION:
            points = self._parse_content_points(raw["content_points"])
            try:
                purpose = SectionPurpose(raw["section_purpose"])
            except (TypeError, ValueError):
                return None, ChangePlanValidationCategory.FIELD_CONTRACT.value
            if points is None or type(raw["proposed_heading"]) is not str:
                return None, ChangePlanValidationCategory.FIELD_CONTRACT.value
            return AddSectionSpecification(
                **common,
                section_purpose=purpose,
                proposed_heading=raw["proposed_heading"],
                content_points=points,
            ), None
        if operation_type is ChangeOperationType.ADD_COMPARISON_TABLE:
            table = self._parse_table(raw["column_headers"], raw["row_dimensions"])
            if table is None or type(raw["proposed_heading"]) is not str:
                return None, ChangePlanValidationCategory.FIELD_CONTRACT.value
            return AddComparisonTableSpecification(
                **common,
                proposed_heading=raw["proposed_heading"],
                comparison_table_specification=table,
            ), None
        if operation_type is ChangeOperationType.ADD_INTERNAL_LINK:
            if (
                type(raw["source_page_ref"]) is not str
                or type(raw["target_page_ref"]) is not str
                or type(raw["anchor_intent"]) is not str
            ):
                return None, ChangePlanValidationCategory.FIELD_CONTRACT.value
            # For links the operation target is the linked-to page; insertion is
            # page-level on source_page_ref and remains a semantic locator.
            common["locator"] = SectionLocatorSpecification(
                common["locator"].locator_kind,
                raw["source_page_ref"],
                common["locator"].target_heading,
            )
            return AddInternalLinkSpecification(
                **common,
                internal_link_specification=InternalLinkSpecification(
                    raw["source_page_ref"],
                    raw["target_page_ref"],
                    raw["anchor_intent"],
                ),
            ), None
        resource = self._parse_new_resource(raw)
        if resource is None:
            return None, ChangePlanValidationCategory.FIELD_CONTRACT.value
        return CreateNewResourceSpecification(
            **common, new_resource_specification=resource
        ), None

    def _parse_common(
        self,
        raw: dict[str, object],
        operation_type: ChangeOperationType,
    ) -> tuple[dict[str, object] | None, str | None]:
        try:
            action = ContentOpportunityActionCode(raw["source_action_code"])
            locator_kind = SectionLocatorKind(raw["locator_kind"])
        except (TypeError, ValueError):
            return None, ChangePlanValidationCategory.FIELD_CONTRACT.value
        page_refs = self._parse_string_tuple(raw["page_refs"])
        source_refs = self._parse_string_tuple(raw["source_refs"])
        if (
            type(raw["opportunity_ref"]) is not str
            or page_refs is None
            or source_refs is None
            or raw["target_page_ref"] is not None
            and type(raw["target_page_ref"]) is not str
            or raw["target_heading"] is not None
            and type(raw["target_heading"]) is not str
        ):
            return None, ChangePlanValidationCategory.FIELD_CONTRACT.value
        return {
            "opportunity_ref": raw["opportunity_ref"],
            "source_action_code": action,
            "operation_type": operation_type,
            "page_refs": page_refs,
            "source_refs": source_refs,
            "locator": SectionLocatorSpecification(
                locator_kind,
                raw["target_page_ref"],
                raw["target_heading"],
            ),
        }, None

    @staticmethod
    def _parse_string_tuple(value: object) -> tuple[str, ...] | None:
        if type(value) is not list or any(type(item) is not str for item in value):
            return None
        return tuple(value)

    def _parse_content_points(
        self, value: object
    ) -> tuple[ContentPointSpecification, ...] | None:
        if type(value) is not list:
            return None
        points: list[ContentPointSpecification] = []
        for item in value:
            if type(item) is not dict or set(item) != {"intent", "subject"}:
                return None
            try:
                intent = ContentPointIntent(item["intent"])
            except (TypeError, ValueError):
                return None
            if type(item["subject"]) is not str:
                return None
            points.append(ContentPointSpecification(intent, item["subject"]))
        return tuple(points)

    def _parse_table(
        self, columns: object, dimensions: object
    ) -> ComparisonTableSpecification | None:
        parsed_columns = self._parse_string_tuple(columns)
        parsed_dimensions = self._parse_string_tuple(dimensions)
        if parsed_columns is None or parsed_dimensions is None:
            return None
        return ComparisonTableSpecification(parsed_columns, parsed_dimensions)

    def _parse_new_resource(
        self, raw: dict[str, object]
    ) -> NewResourceSpecification | None:
        outlines = self._parse_string_tuple(raw["outline_headings"])
        points = self._parse_content_points(raw["content_points"])
        suggestions = self._parse_string_tuple(raw["suggested_source_page_refs"])
        if (
            type(raw["proposed_title"]) is not str
            or outlines is None
            or points is None
            or suggestions is None
        ):
            return None
        try:
            purpose = NewResourcePurpose(raw["resource_purpose"])
        except (TypeError, ValueError):
            return None
        nested_raw = raw["comparison_table_brief"]
        nested = None
        if nested_raw is not None:
            if type(nested_raw) is not dict or set(nested_raw) != {
                "column_headers",
                "row_dimensions",
            }:
                return None
            nested = self._parse_table(
                nested_raw["column_headers"], nested_raw["row_dimensions"]
            )
            if nested is None:
                return None
        return NewResourceSpecification(
            purpose,
            raw["proposed_title"],
            outlines,
            points,
            suggestions,
            nested,
        )

    @staticmethod
    def _failure(
        status: ChangePlanStatus,
        category: ChangePlanValidationCategory | None = None,
    ) -> ChangePlanReport:
        return ChangePlanReport(
            status=status,
            operations=(),
            limitations=(),
            error=None if category is None else category.value,
        )
