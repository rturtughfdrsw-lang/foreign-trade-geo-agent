"""Strict parsing, evidence validation, and finalization for change plans."""

import asyncio
import json
from foreign_trade_geo_agent.core.first_party_planning import FirstPartyPlanningScope, MAX_FIRST_PARTY_EXCERPTS
import math
from dataclasses import dataclass, replace

from foreign_trade_geo_agent.core.change_plan import (
    CHANGE_PLAN_LIMITATIONS,
    CHANGE_PLAN_REPAIR_CATEGORIES,
    MAX_ANCHOR_INTENT_CHARS,
    MAX_CHANGE_PLAN_TIMEOUT_SECONDS,
    MAX_CONTENT_POINTS_PER_OPERATION,
    MAX_OUTLINE_HEADING_CHARS,
    MAX_OUTLINE_HEADINGS,
    MAX_OPERATIONS,
    MAX_OPERATIONS_PER_OPPORTUNITY,
    MAX_PAGE_REFS_PER_OPERATION,
    MAX_PROPOSED_HEADING_CHARS,
    MAX_RAW_OUTPUT_BYTES,
    MAX_RAW_OUTPUT_CHARS,
    MAX_REORDER_HEADINGS,
    MAX_SOURCE_REFS_PER_OPERATION,
    MAX_TABLE_COLUMNS,
    MAX_TABLE_DIMENSIONS,
    MAX_TABLE_LABEL_CHARS,
    MAX_USER_MATERIAL_BYTES,
    MAX_USER_MATERIAL_CHARS,
    MIN_CONTENT_POINTS_PER_OPERATION,
    MIN_OUTLINE_HEADINGS,
    MIN_REORDER_HEADINGS,
    MIN_TABLE_COLUMNS,
    MIN_TABLE_DIMENSIONS,
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
    FieldContractRepairClass,
    FieldContractRule,
    FieldContractViolation,
    GroundingViolation,
    InternalLinkSpecification,
    NewResourceSpecification,
    NewResourcePurpose,
    ProposeSectionReorderSpecification,
    SectionLocatorKind,
    SectionLocatorSpecification,
    SectionPurpose,
    TargetLocatorRepairRule,
    TargetLocatorViolation,
    build_change_plan_prompt,
    canonical_change_operation_identity,
    diagnose_grounding_violation,
    has_forbidden_prose_syntax,
    stable_change_plan_input_shape_error,
    validate_change_plan_input,
    validate_provider_generation_material,
    validate_and_finalize_specification,
)
from foreign_trade_geo_agent.core.content_opportunity import (
    ContentOpportunityActionCode,
    ContentOpportunityReport,
)
from foreign_trade_geo_agent.core.ports import ChangePlanWriter
from foreign_trade_geo_agent.core.history import PlanningValidationCategory
from foreign_trade_geo_agent.core.site_content import SiteContentPacket
from foreign_trade_geo_agent.core.evidence_intake import CustomerPlanningContext, native_plan_error, rebind_preserves_task
from foreign_trade_geo_agent.workflows.run_diagnostics import RunDiagnosticContext


_COMMON_FIELDS = {
    "source_action_code",
    "operation_type",
    "source_refs",
}

_LOCATOR_REF_OPERATIONS = frozenset(
    {
        ChangeOperationType.EXPAND_SECTION,
        ChangeOperationType.ADD_SECTION,
        ChangeOperationType.ADD_COMPARISON_TABLE,
    }
)

_OPERATION_FIELDS = {
    ChangeOperationType.EXPAND_SECTION: {"page_refs", "content_points"},
    ChangeOperationType.PROPOSE_SECTION_REORDER: {"page_refs", "ordered_headings"},
    ChangeOperationType.ADD_SECTION: {
        "page_refs",
        "section_purpose",
        "proposed_heading_ref",
        "content_points",
    },
    ChangeOperationType.ADD_COMPARISON_TABLE: {
        "page_refs",
        "proposed_heading",
        "column_headers",
        "row_dimensions",
    },
    ChangeOperationType.ADD_INTERNAL_LINK: {
        "page_refs",
        "source_page_ref",
        "target_page_ref",
        "anchor_intent",
    },
    ChangeOperationType.CREATE_NEW_RESOURCE: {
        "page_bindings",
        "resource_purpose",
        "proposed_title",
        "content_points",
        "comparison_table_brief",
    },
}

_OPPORTUNITY_SLOT_FIELDS = frozenset(
    {"primary_operation", "secondary_operation"}
)


@dataclass(frozen=True, slots=True)
class _ValidationFailure:
    category: ChangePlanValidationCategory
    violation: FieldContractViolation | None = None
    locator_repair_rule: TargetLocatorRepairRule | None = None
    grounding_violation: GroundingViolation | None = None
    target_locator_violation: TargetLocatorViolation | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.category, ChangePlanValidationCategory):
            raise TypeError("Change plan validation failure category is invalid.")
        if self.violation is not None and (
            self.category is not ChangePlanValidationCategory.FIELD_CONTRACT
            or not isinstance(self.violation, FieldContractViolation)
        ):
            raise ValueError("Change plan field violation is inconsistent.")
        if self.locator_repair_rule is not None and (
            self.category is not ChangePlanValidationCategory.TARGET_LOCATOR_INVALID
            or not isinstance(
                self.locator_repair_rule,
                TargetLocatorRepairRule,
            )
        ):
            raise ValueError("Change plan locator repair rule is inconsistent.")
        if self.grounding_violation is not None and (
            self.category is not ChangePlanValidationCategory.CONTENT_NOT_GROUNDED
            or not isinstance(self.grounding_violation, GroundingViolation)
        ):
            raise ValueError("Change plan grounding violation is inconsistent.")
        if self.target_locator_violation is not None and (
            self.category is not ChangePlanValidationCategory.TARGET_LOCATOR_INVALID
            or not isinstance(
                self.target_locator_violation,
                TargetLocatorViolation,
            )
        ):
            raise ValueError("Change plan locator violation is inconsistent.")


def _validation_failure(
    category: ChangePlanValidationCategory,
    locator_repair_rule: TargetLocatorRepairRule | None = None,
    *,
    grounding_violation: GroundingViolation | None = None,
    target_locator_violation: TargetLocatorViolation | None = None,
) -> _ValidationFailure:
    return _ValidationFailure(
        category,
        locator_repair_rule=locator_repair_rule,
        grounding_violation=grounding_violation,
        target_locator_violation=target_locator_violation,
    )


def _field_failure(
    rule_id: FieldContractRule,
    field_path: str,
    *,
    expected: tuple[tuple[str, object], ...] = (),
    actual: tuple[tuple[str, object], ...] = (),
) -> _ValidationFailure:
    return _ValidationFailure(
        ChangePlanValidationCategory.FIELD_CONTRACT,
        FieldContractViolation(rule_id, field_path, expected, actual),
    )


def _safe_actual_type(value: object) -> str:
    if value is None:
        return "null"
    if type(value) is dict:
        return "object"
    if type(value) is list:
        return "array"
    if type(value) is str:
        return "string"
    if type(value) is bool:
        return "boolean"
    if type(value) in {int, float}:
        return "number"
    return "unknown"


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
        run_diagnostics: RunDiagnosticContext | None = None,
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
        self._run_diagnostics = run_diagnostics or RunDiagnosticContext()

    @property
    def run_diagnostics(self) -> RunDiagnosticContext:
        """Return the process-local diagnostic context used by this workflow."""

        return self._run_diagnostics

    @property
    def last_field_contract_violation(self) -> FieldContractViolation | None:
        """Return only the current run's sanitized, non-persisted final violation."""

        return self._run_diagnostics.field_contract_violation

    @property
    def last_grounding_violation(self) -> GroundingViolation | None:
        """Return only the current run's sanitized, non-persisted final violation."""

        return self._run_diagnostics.grounding_violation

    @property
    def last_target_locator_violation(self) -> TargetLocatorViolation | None:
        """Return only the current run's sanitized locator violation."""

        return self._run_diagnostics.target_locator_violation

    async def run(
        self,
        site_content: SiteContentPacket,
        opportunity_report: ContentOpportunityReport,
        *,
        first_party_scope: FirstPartyPlanningScope | None = None,
        task_id: str | None = None,
        customer_context: CustomerPlanningContext | None = None,
    ) -> ChangePlanReport:
        self._run_diagnostics.clear()
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
                self._run(site_content, opportunity_report, first_party_scope, task_id, customer_context),
                timeout=self._total_timeout,
            )
        except (TimeoutError, asyncio.TimeoutError):
            return self._failure(ChangePlanStatus.WORKFLOW_TIMEOUT)

    async def _run(
        self,
        site_content: SiteContentPacket,
        opportunity_report: ContentOpportunityReport,
        first_party_scope: FirstPartyPlanningScope | None = None,
        task_id: str | None = None,
        customer_context: CustomerPlanningContext | None = None,
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
            change_input = ChangePlanInput(site_content, opportunity_report, first_party_scope, task_id, customer_context)
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
        material_error = validate_provider_generation_material(prompt, material)
        if material_error is not None:
            return self._failure(
                ChangePlanStatus.INVALID_INPUT,
                ChangePlanValidationCategory(material_error),
            )
        writer_attempt_count = 1
        try:
            generation = await asyncio.wait_for(
                self._writer.write_change_plan(prompt),
                timeout=self._generation_timeout,
            )
        except (TimeoutError, asyncio.TimeoutError):
            return self._failure(
                ChangePlanStatus.GENERATION_FAILED,
                writer_attempt_count=writer_attempt_count,
            )
        except Exception:
            return self._failure(
                ChangePlanStatus.GENERATION_FAILED,
                writer_attempt_count=writer_attempt_count,
            )
        if not isinstance(generation, ChangePlanGeneration):
            return self._failure(
                ChangePlanStatus.GENERATION_FAILED,
                writer_attempt_count=writer_attempt_count,
            )
        if generation.status is ChangePlanGenerationStatus.FAILED:
            if (
                generation.failure_kind
                is ChangePlanGenerationFailureKind.INPUT_TOO_LARGE
            ):
                return self._failure(
                    ChangePlanStatus.INPUT_TOO_LARGE,
                    ChangePlanValidationCategory.INPUT_TOO_LARGE,
                    writer_attempt_count=writer_attempt_count,
                )
            return self._failure(
                ChangePlanStatus.GENERATION_FAILED,
                writer_attempt_count=writer_attempt_count,
            )

        operations, failure = self._parse_validate_finalize_detailed(
            generation.text,
            prompt,
        )
        repair_category = None if failure is None else failure.category
        repairable = repair_category in CHANGE_PLAN_REPAIR_CATEGORIES and (
            repair_category is ChangePlanValidationCategory.CONTENT_NOT_GROUNDED
            or repair_category is ChangePlanValidationCategory.FIELD_CONTRACT
            and failure is not None
            and failure.violation is not None
            and failure.violation.repair_class is FieldContractRepairClass.TYPE_B
            or repair_category
            is ChangePlanValidationCategory.TARGET_LOCATOR_INVALID
            and failure is not None
            and failure.locator_repair_rule is not None
        )
        if repairable:
            retry_prompt = replace(
                prompt,
                repair_category=repair_category,
                field_contract_violation=(
                    failure.violation
                    if repair_category is ChangePlanValidationCategory.FIELD_CONTRACT
                    else None
                ),
                locator_repair_rule=(
                    failure.locator_repair_rule
                    if repair_category
                    is ChangePlanValidationCategory.TARGET_LOCATOR_INVALID
                    else None
                ),
            )
            retry_material = retry_prompt.material_json()
            if (
                len(retry_material) > MAX_USER_MATERIAL_CHARS
                or len(retry_material.encode("utf-8")) > MAX_USER_MATERIAL_BYTES
            ):
                return self._failure(
                    ChangePlanStatus.INPUT_TOO_LARGE,
                    ChangePlanValidationCategory.INPUT_TOO_LARGE,
                    writer_attempt_count=writer_attempt_count,
                )
            material_error = validate_provider_generation_material(retry_prompt, retry_material)
            if material_error is not None:
                return self._failure(
                    ChangePlanStatus.INVALID_INPUT,
                    ChangePlanValidationCategory(material_error),
                    writer_attempt_count=writer_attempt_count,
                )
            writer_attempt_count = 2
            try:
                generation = await asyncio.wait_for(
                    self._writer.write_change_plan(retry_prompt),
                    timeout=self._generation_timeout,
                )
            except (TimeoutError, asyncio.TimeoutError):
                return self._failure(
                    ChangePlanStatus.GENERATION_FAILED,
                    writer_attempt_count=writer_attempt_count,
                )
            except Exception:
                return self._failure(
                    ChangePlanStatus.GENERATION_FAILED,
                    writer_attempt_count=writer_attempt_count,
                )
            if not isinstance(generation, ChangePlanGeneration):
                return self._failure(
                    ChangePlanStatus.GENERATION_FAILED,
                    writer_attempt_count=writer_attempt_count,
                )
            if generation.status is ChangePlanGenerationStatus.FAILED:
                if (
                    generation.failure_kind
                    is ChangePlanGenerationFailureKind.INPUT_TOO_LARGE
                ):
                    return self._failure(
                        ChangePlanStatus.INPUT_TOO_LARGE,
                        ChangePlanValidationCategory.INPUT_TOO_LARGE,
                        writer_attempt_count=writer_attempt_count,
                    )
                return self._failure(
                    ChangePlanStatus.GENERATION_FAILED,
                    writer_attempt_count=writer_attempt_count,
                )
            operations, failure = self._parse_validate_finalize_detailed(
                generation.text,
                retry_prompt,
            )
        if operations is None:
            assert failure is not None
            self._run_diagnostics.capture_change_plan_violation(
                field_contract_violation=(
                    failure.violation
                    if failure.category
                    is ChangePlanValidationCategory.FIELD_CONTRACT
                    else None
                ),
                grounding_violation=(
                    failure.grounding_violation
                    if failure.category
                    is ChangePlanValidationCategory.CONTENT_NOT_GROUNDED
                    else None
                ),
                target_locator_violation=(
                    failure.target_locator_violation
                    if failure.category
                    is ChangePlanValidationCategory.TARGET_LOCATOR_INVALID
                    else None
                ),
            )
            return self._failure(
                ChangePlanStatus.INVALID_OUTPUT,
                failure.category,
                final_validation_category=PlanningValidationCategory(
                    ChangePlanValidationCategory.OPERATION_NOT_ALLOWED.value
                    if failure.category is ChangePlanValidationCategory.COMPARISON_UNAVAILABLE
                    else failure.category.value
                ),
                writer_attempt_count=writer_attempt_count,
            )
        self._run_diagnostics.clear()
        report = ChangePlanReport(
            status=ChangePlanStatus.SUCCESS,
            operations=operations,
            limitations=self.limitations,
            error=None,
        )
        if customer_context is not None:
            current = customer_context.snapshot
            candidate_input = replace(current.planning_input, change_plan_report=report)
            if (native_plan_error(candidate_input, current.point_subjects) is not None
                    or not rebind_preserves_task(current, candidate_input)):
                return self._failure(ChangePlanStatus.INVALID_OUTPUT, ChangePlanValidationCategory.FIELD_CONTRACT,
                    final_validation_category=PlanningValidationCategory.FIELD_CONTRACT,
                    writer_attempt_count=writer_attempt_count)
        return report

    def _parse_validate_finalize(
        self,
        text: str | None,
        prompt: ChangePlanPrompt,
    ) -> tuple[tuple[ChangeOperation, ...] | None, str | None]:
        """Preserve the legacy private helper result for focused callers."""
        operations, failure = self._parse_validate_finalize_detailed(text, prompt)
        return operations, None if failure is None else failure.category.value

    def _parse_validate_finalize_detailed(
        self,
        text: str | None,
        prompt: ChangePlanPrompt,
    ) -> tuple[tuple[ChangeOperation, ...] | None, _ValidationFailure | None]:
        if text is None:
            return None, _validation_failure(ChangePlanValidationCategory.JSON_FORMAT)
        if (
            len(text) > MAX_RAW_OUTPUT_CHARS
            or len(text.encode("utf-8")) > MAX_RAW_OUTPUT_BYTES
        ):
            return None, _validation_failure(ChangePlanValidationCategory.OUTPUT_TOO_LARGE)
        try:
            payload = json.loads(text, object_pairs_hook=_strict_json_object)
        except (json.JSONDecodeError, TypeError, ValueError):
            return None, _validation_failure(ChangePlanValidationCategory.JSON_FORMAT)
        if type(payload) is not dict:
            return None, _field_failure(
                FieldContractRule.ROOT_TYPE_INVALID,
                "$",
                expected=(("expected_type", "object"),),
                actual=(("actual_type", _safe_actual_type(payload)),),
            )
        if set(payload) != {"opportunity_operations"}:
            return None, _field_failure(
                FieldContractRule.TOP_LEVEL_KEYS_INVALID,
                "$",
                expected=(("expected_keys", ("opportunity_operations",)),),
                actual=(("actual_count", len(payload)),),
            )
        raw_opportunities = payload["opportunity_operations"]
        if type(raw_opportunities) is not dict:
            return None, _field_failure(
                FieldContractRule.OPPORTUNITY_OPERATIONS_TYPE_INVALID,
                "$",
                expected=(("expected_type", "object"),),
                actual=(("actual_type", _safe_actual_type(raw_opportunities)),),
            )
        if len(raw_opportunities) > MAX_OPERATIONS // MAX_OPERATIONS_PER_OPPORTUNITY:
            return None, _field_failure(
                FieldContractRule.OPPORTUNITY_COUNT_EXCEEDED,
                "$",
                expected=(("max_count", MAX_OPERATIONS // MAX_OPERATIONS_PER_OPPORTUNITY),),
                actual=(("actual_count", len(raw_opportunities)),),
            )

        specifications: list[ChangePlanSpecification] = []
        specification_paths: list[str] = []
        for opportunity_ref, raw_slots in raw_opportunities.items():
            if type(opportunity_ref) is not str:
                return None, _field_failure(
                    FieldContractRule.STRING_TYPE_INVALID,
                    "$",
                    expected=(("expected_type", "string"),),
                    actual=(("actual_type", _safe_actual_type(opportunity_ref)),),
                )
            if opportunity_ref not in prompt.catalog.opportunity_by_id():
                return None, _validation_failure(
                    ChangePlanValidationCategory.UNKNOWN_OPPORTUNITY_REFERENCE
                )
            if type(raw_slots) is not dict:
                return None, _field_failure(
                    FieldContractRule.SLOT_TYPE_INVALID,
                    opportunity_ref,
                    expected=(("expected_type", "object"),),
                    actual=(("actual_type", _safe_actual_type(raw_slots)),),
                )
            if "primary_operation" not in raw_slots:
                return None, _field_failure(
                    FieldContractRule.PRIMARY_REQUIRED,
                    opportunity_ref,
                    expected=(("required", True),),
                    actual=(("actual_count", len(raw_slots)),),
                )
            if not set(raw_slots).issubset(_OPPORTUNITY_SLOT_FIELDS):
                return None, _field_failure(
                    FieldContractRule.SLOT_KEYS_INVALID,
                    opportunity_ref,
                    expected=(("expected_keys", tuple(sorted(_OPPORTUNITY_SLOT_FIELDS))),),
                    actual=(("actual_count", len(raw_slots)),),
                )
            if type(raw_slots["primary_operation"]) is not dict:
                return None, _field_failure(
                    FieldContractRule.SLOT_TYPE_INVALID,
                    f"{opportunity_ref}.primary_operation",
                    expected=(("expected_type", "object"),),
                    actual=(("actual_type", _safe_actual_type(raw_slots["primary_operation"])),),
                )
            if (
                "secondary_operation" in raw_slots
                and raw_slots["secondary_operation"] is not None
                and type(raw_slots["secondary_operation"]) is not dict
            ):
                return None, _field_failure(
                    FieldContractRule.SLOT_TYPE_INVALID,
                    f"{opportunity_ref}.secondary_operation",
                    expected=(("expected_type", "object"),),
                    actual=(("actual_type", _safe_actual_type(raw_slots["secondary_operation"])),),
                )
            raw_slot_operations = [
                ("primary_operation", raw_slots["primary_operation"])
            ]
            if raw_slots.get("secondary_operation") is not None:
                raw_slot_operations.append(
                    ("secondary_operation", raw_slots["secondary_operation"])
                )
            for slot_name, raw in raw_slot_operations:
                field_path = f"{opportunity_ref}.{slot_name}"
                specification, failure = self._parse_specification(
                    raw,
                    opportunity_ref=opportunity_ref,
                    field_path=field_path,
                    prompt=prompt,
                )
                if specification is None:
                    return None, failure
                specifications.append(specification)
                specification_paths.append(field_path)
        if len(specifications) > MAX_OPERATIONS:
            return None, _field_failure(
                FieldContractRule.OPERATION_COUNT_EXCEEDED,
                "$",
                expected=(("max_count", MAX_OPERATIONS),),
                actual=(("actual_count", len(specifications)),),
            )
        if prompt.input.first_party_scope is not None and len(specifications) != 1:
            return None, _field_failure(
                FieldContractRule.OPERATION_COUNT_EXCEEDED,
                "$",
                expected=(("max_count", 1),),
                actual=(("actual_count", len(specifications)),),
            )

        # No result is exposed until every operation has passed every validator.
        provisional: list[ChangeOperation] = []
        identities: set[tuple[object, ...]] = set()
        for specification, field_path in zip(specifications, specification_paths):
            operation, error = validate_and_finalize_specification(
                1, specification, prompt.catalog,
                first_party_scope=prompt.input.first_party_scope,
                task_id=prompt.input.task_id,
            )
            if operation is None:
                assert error is not None
                category = ChangePlanValidationCategory(error)
                if category is ChangePlanValidationCategory.FIELD_CONTRACT:
                    return None, _field_failure(
                        FieldContractRule.INTERNAL_INVARIANT,
                        field_path,
                    )
                locator_repair_rule = None
                target_locator_violation = None
                if category is ChangePlanValidationCategory.TARGET_LOCATOR_INVALID:
                    if isinstance(specification, ProposeSectionReorderSpecification):
                        locator_repair_rule = (
                            TargetLocatorRepairRule.REORDER_HEADING_NOT_OBSERVED_ON_TARGET_PAGE
                        )
                        locator_field = "ordered_headings"
                    elif isinstance(specification, AddSectionSpecification):
                        locator_repair_rule = (
                            TargetLocatorRepairRule.ADD_SECTION_PROPOSED_HEADING_COLLIDES
                        )
                        locator_field = "proposed_heading"
                    else:
                        locator_field = "locator_ref"
                    target_locator_violation = TargetLocatorViolation(
                        f"{field_path}.{locator_field}",
                        locator_repair_rule,
                    )
                return None, _validation_failure(
                    category,
                    locator_repair_rule,
                    grounding_violation=(
                        diagnose_grounding_violation(
                            specification,
                            prompt.catalog,
                            field_path=field_path,
                        )
                        if category
                        is ChangePlanValidationCategory.CONTENT_NOT_GROUNDED
                        else None
                    ),
                    target_locator_violation=target_locator_violation,
                )
            identity = canonical_change_operation_identity(operation)
            if identity in identities:
                return None, _field_failure(
                    FieldContractRule.CANONICAL_OPERATION_DUPLICATE,
                    field_path,
                )
            identities.add(identity)
            provisional.append(operation)
        return tuple(
            replace(operation, change_id=f"C{number}")
            for number, operation in enumerate(provisional, start=1)
        ), None

    def _parse_specification(
        self,
        raw: object,
        *,
        opportunity_ref: str,
        field_path: str,
        prompt: ChangePlanPrompt,
    ) -> tuple[ChangePlanSpecification | None, _ValidationFailure | None]:
        if type(raw) is not dict:
            return None, _field_failure(
                FieldContractRule.SLOT_TYPE_INVALID,
                field_path,
                expected=(("expected_type", "object"),),
                actual=(("actual_type", _safe_actual_type(raw)),),
            )
        if opportunity_ref not in prompt.catalog.opportunity_by_id():
            return None, _validation_failure(
                ChangePlanValidationCategory.UNKNOWN_OPPORTUNITY_REFERENCE
            )
        try:
            operation_type = ChangeOperationType(raw.get("operation_type"))
        except (TypeError, ValueError):
            return None, _field_failure(
                FieldContractRule.ENUM_INVALID,
                f"{field_path}.operation_type",
                expected=(("expected_type", "string"),),
                actual=(("actual_type", _safe_actual_type(raw.get("operation_type"))),),
            )
        # Generation availability is a preflight contract. Keep parsing and
        # domain validation authoritative for response errors (including the
        # existing exact locator/field/grounding categories).
        expected_fields = _COMMON_FIELDS | _OPERATION_FIELDS[operation_type]
        if operation_type in _LOCATOR_REF_OPERATIONS:
            expected_fields = expected_fields | {"locator_ref"}
        if set(raw) != expected_fields:
            return None, _field_failure(
                FieldContractRule.OPERATION_KEYS_INVALID,
                field_path,
                expected=(("expected_keys", tuple(sorted(expected_fields))),),
                actual=(("actual_count", len(raw)),),
            )
        page_refs: tuple[str, ...] | None = None
        suggested_source_page_refs: tuple[str, ...] = ()
        if operation_type is ChangeOperationType.CREATE_NEW_RESOURCE:
            bindings, failure = self._parse_page_bindings(
                raw["page_bindings"],
                field_path=f"{field_path}.page_bindings",
            )
            if bindings is None:
                return None, failure
            page_refs, suggested_source_page_refs = bindings
        else:
            page_refs, failure = self._parse_string_tuple(
                raw["page_refs"],
                field_path=f"{field_path}.page_refs",
                maximum=MAX_PAGE_REFS_PER_OPERATION,
            )
            if page_refs is None:
                return None, failure
        common, failure = self._parse_common(
            raw,
            operation_type,
            opportunity_ref=opportunity_ref,
            field_path=field_path,
            page_refs=page_refs,
            prompt=prompt,
        )
        if common is None:
            return None, failure
        if operation_type is ChangeOperationType.EXPAND_SECTION:
            points, failure = self._parse_content_points(
                raw["content_points"],
                opportunity_ref=opportunity_ref,
                field_path=f"{field_path}.content_points",
                source_refs=common["source_refs"],
                prompt=prompt,
                maximum=(MAX_FIRST_PARTY_EXCERPTS if prompt.input.first_party_scope is not None
                         else MAX_CONTENT_POINTS_PER_OPERATION),
            )
            if points is None:
                return None, failure
            return ExpandSectionSpecification(**common, content_points=points), None
        if operation_type is ChangeOperationType.PROPOSE_SECTION_REORDER:
            headings, failure = self._parse_string_tuple(
                raw["ordered_headings"],
                field_path=f"{field_path}.ordered_headings",
                minimum=MIN_REORDER_HEADINGS,
                maximum=MAX_REORDER_HEADINGS,
                maximum_chars=MAX_PROPOSED_HEADING_CHARS,
            )
            if headings is None:
                return None, failure
            return ProposeSectionReorderSpecification(
                **common, ordered_headings=headings
            ), None
        if operation_type is ChangeOperationType.ADD_SECTION:
            points, failure = self._parse_content_points(
                raw["content_points"],
                opportunity_ref=opportunity_ref,
                field_path=f"{field_path}.content_points",
                source_refs=common["source_refs"],
                prompt=prompt,
            )
            try:
                purpose = SectionPurpose(raw["section_purpose"])
            except (TypeError, ValueError):
                return None, _field_failure(
                    FieldContractRule.ENUM_INVALID,
                    f"{field_path}.section_purpose",
                    expected=(("expected_type", "string"),),
                    actual=(("actual_type", _safe_actual_type(raw["section_purpose"])),),
                )
            if points is None:
                return None, failure
            proposed_heading_ref = raw["proposed_heading_ref"]
            if type(proposed_heading_ref) is not str:
                return None, _field_failure(
                    FieldContractRule.STRING_TYPE_INVALID,
                    f"{field_path}.proposed_heading_ref",
                    expected=(("expected_type", "string"),),
                    actual=(("actual_type", _safe_actual_type(proposed_heading_ref)),),
                )
            candidate = prompt.proposed_heading_candidate(
                opportunity_ref,
                proposed_heading_ref,
            )
            if candidate is None:
                if prompt.has_proposed_heading_candidate_id(proposed_heading_ref):
                    return None, _validation_failure(
                        ChangePlanValidationCategory.EVIDENCE_USE_NOT_ALLOWED
                    )
                return None, _field_failure(
                    FieldContractRule.PROPOSED_HEADING_REF_INVALID,
                    f"{field_path}.proposed_heading_ref",
                    expected=(("expected_type", "string"),),
                    actual=(("actual_type", "string"),),
                )
            locator = common["locator"]
            source_refs = common["source_refs"]
            if (
                not isinstance(locator, SectionLocatorSpecification)
                or not isinstance(source_refs, tuple)
                or candidate.page_ref not in common["page_refs"]
                or candidate.page_ref != locator.page_ref
                or candidate.source_ref not in source_refs
            ):
                return None, _validation_failure(
                    ChangePlanValidationCategory.EVIDENCE_USE_NOT_ALLOWED
                )
            return AddSectionSpecification(
                **common,
                section_purpose=purpose,
                proposed_heading=candidate.text,
                content_points=points,
            ), None
        if operation_type is ChangeOperationType.ADD_COMPARISON_TABLE:
            failure = self._validate_bounded_string(
                raw["proposed_heading"],
                field_path=f"{field_path}.proposed_heading",
                maximum=MAX_PROPOSED_HEADING_CHARS,
            )
            if failure is not None:
                return None, failure
            table, failure = self._parse_table(
                raw["column_headers"],
                raw["row_dimensions"],
                field_path=field_path,
            )
            if table is None:
                return None, failure
            return AddComparisonTableSpecification(
                **common,
                proposed_heading=raw["proposed_heading"],
                comparison_table_specification=table,
            ), None
        if operation_type is ChangeOperationType.ADD_INTERNAL_LINK:
            for name in ("source_page_ref", "target_page_ref"):
                if type(raw[name]) is not str:
                    return None, _field_failure(
                        FieldContractRule.STRING_TYPE_INVALID,
                        f"{field_path}.{name}",
                        expected=(("expected_type", "string"),),
                        actual=(("actual_type", _safe_actual_type(raw[name])),),
                    )
            failure = self._validate_bounded_string(
                raw["anchor_intent"],
                field_path=f"{field_path}.anchor_intent",
                maximum=MAX_ANCHOR_INTENT_CHARS,
            )
            if failure is not None:
                return None, failure
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
        resource = self._parse_new_resource(
            raw,
            suggested_source_page_refs=suggested_source_page_refs,
            opportunity_ref=opportunity_ref,
            field_path=field_path,
            page_refs=page_refs,
            source_refs=common["source_refs"],
            prompt=prompt,
        )
        if resource[0] is None:
            return None, resource[1]
        return CreateNewResourceSpecification(
            **common, new_resource_specification=resource[0]
        ), None

    def _parse_common(
        self,
        raw: dict[str, object],
        operation_type: ChangeOperationType,
        *,
        opportunity_ref: str,
        field_path: str,
        page_refs: tuple[str, ...] | None,
        prompt: ChangePlanPrompt,
    ) -> tuple[dict[str, object] | None, _ValidationFailure | None]:
        try:
            action = ContentOpportunityActionCode(raw["source_action_code"])
        except (TypeError, ValueError):
            return None, _field_failure(
                FieldContractRule.ENUM_INVALID,
                f"{field_path}.source_action_code",
                expected=(("expected_type", "string"),),
                actual=(("actual_type", _safe_actual_type(raw["source_action_code"])),),
            )
        source_refs, failure = self._parse_string_tuple(
            raw["source_refs"],
            field_path=f"{field_path}.source_refs",
            maximum=MAX_SOURCE_REFS_PER_OPERATION,
        )
        if source_refs is None:
            return None, failure
        if page_refs is None:
            return None, _field_failure(
                FieldContractRule.INTERNAL_INVARIANT,
                field_path,
            )
        if operation_type in _LOCATOR_REF_OPERATIONS:
            locator_ref = raw["locator_ref"]
            if type(locator_ref) is not str:
                return None, _field_failure(
                    FieldContractRule.STRING_TYPE_INVALID,
                    f"{field_path}.locator_ref",
                    expected=(("expected_type", "string"),),
                    actual=(("actual_type", _safe_actual_type(locator_ref)),),
                )
            candidate = prompt.locator_candidate(opportunity_ref, locator_ref)
            if candidate is None:
                if prompt.has_locator_candidate_id(locator_ref):
                    return None, _validation_failure(
                        ChangePlanValidationCategory.EVIDENCE_USE_NOT_ALLOWED
                    )
                return None, _validation_failure(
                    ChangePlanValidationCategory.TARGET_LOCATOR_INVALID,
                    target_locator_violation=TargetLocatorViolation(
                        f"{field_path}.locator_ref"
                    ),
                )
            if candidate.page_ref not in page_refs:
                return None, _validation_failure(
                    ChangePlanValidationCategory.EVIDENCE_USE_NOT_ALLOWED
                )
            locator = SectionLocatorSpecification(
                candidate.locator_kind,
                candidate.page_ref,
                candidate.target_heading,
            )
        elif operation_type is ChangeOperationType.PROPOSE_SECTION_REORDER:
            if len(page_refs) != 1:
                return None, _validation_failure(
                    ChangePlanValidationCategory.EVIDENCE_USE_NOT_ALLOWED
                )
            locator = SectionLocatorSpecification(
                SectionLocatorKind.PAGE_LEVEL,
                page_refs[0],
                None,
            )
        elif operation_type is ChangeOperationType.CREATE_NEW_RESOURCE:
            locator = SectionLocatorSpecification(
                SectionLocatorKind.NEW_PAGE,
                None,
                None,
            )
        else:
            locator = SectionLocatorSpecification(
                SectionLocatorKind.PAGE_LEVEL,
                None,
                None,
            )
        return {
            "opportunity_ref": opportunity_ref,
            "source_action_code": action,
            "operation_type": operation_type,
            "page_refs": page_refs,
            "source_refs": source_refs,
            "locator": locator,
        }, None

    @staticmethod
    def _parse_string_tuple(
        value: object,
        *,
        field_path: str,
        minimum: int | None = None,
        maximum: int | None = None,
        maximum_chars: int | None = None,
        reject_prose_syntax: bool = False,
    ) -> tuple[tuple[str, ...] | None, _ValidationFailure | None]:
        if type(value) is not list:
            return None, _field_failure(
                FieldContractRule.LIST_TYPE_INVALID,
                field_path,
                expected=(("expected_type", "array"),),
                actual=(("actual_type", _safe_actual_type(value)),),
            )
        if minimum is not None and len(value) < minimum:
            return None, _field_failure(
                FieldContractRule.LIST_COUNT_BELOW_MIN,
                field_path,
                expected=(("min_count", minimum),),
                actual=(("actual_count", len(value)),),
            )
        if maximum is not None and len(value) > maximum:
            return None, _field_failure(
                FieldContractRule.LIST_COUNT_EXCEEDED,
                field_path,
                expected=(("max_count", maximum),),
                actual=(("actual_count", len(value)),),
            )
        parsed: list[str] = []
        for index, item in enumerate(value):
            item_path = f"{field_path}[{index}]"
            if type(item) is not str:
                return None, _field_failure(
                    FieldContractRule.STRING_TYPE_INVALID,
                    item_path,
                    expected=(("expected_type", "string"),),
                    actual=(("actual_type", _safe_actual_type(item)),),
                )
            if maximum_chars is not None:
                failure = ChangePlanWorkflow._validate_bounded_string(
                    item,
                    field_path=item_path,
                    maximum=maximum_chars,
                    reject_prose_syntax=reject_prose_syntax,
                )
                if failure is not None:
                    return None, failure
            parsed.append(item)
        if len(parsed) != len(set(parsed)):
            return None, _field_failure(
                FieldContractRule.LIST_DUPLICATE,
                field_path,
                actual=(("actual_count", len(parsed)),),
            )
        return tuple(parsed), None

    @staticmethod
    def _validate_bounded_string(
        value: object,
        *,
        field_path: str,
        maximum: int,
        reject_prose_syntax: bool = True,
    ) -> _ValidationFailure | None:
        if type(value) is not str:
            return _field_failure(
                FieldContractRule.STRING_TYPE_INVALID,
                field_path,
                expected=(("expected_type", "string"),),
                actual=(("actual_type", _safe_actual_type(value)),),
            )
        if not value:
            return _field_failure(FieldContractRule.STRING_EMPTY, field_path)
        if len(value) > maximum:
            return _field_failure(
                FieldContractRule.STRING_LENGTH_EXCEEDED,
                field_path,
                expected=(("max_chars", maximum),),
                actual=(("actual_chars", len(value)),),
            )
        if (
            value != " ".join(value.split())
            or "\n" in value
            or "\r" in value
            or reject_prose_syntax
            and has_forbidden_prose_syntax(value)
        ):
            return _field_failure(FieldContractRule.STRING_FORMAT_INVALID, field_path)
        return None

    def _parse_content_points(
        self,
        value: object,
        *,
        opportunity_ref: str,
        field_path: str,
        source_refs: object,
        prompt: ChangePlanPrompt,
        maximum: int = MAX_CONTENT_POINTS_PER_OPERATION,
    ) -> tuple[tuple[ContentPointSpecification, ...] | None, _ValidationFailure | None]:
        if type(value) is not list:
            return None, _field_failure(
                FieldContractRule.LIST_TYPE_INVALID,
                field_path,
                expected=(("expected_type", "array"),),
                actual=(("actual_type", _safe_actual_type(value)),),
            )
        if len(value) < MIN_CONTENT_POINTS_PER_OPERATION:
            return None, _field_failure(
                FieldContractRule.LIST_COUNT_BELOW_MIN,
                field_path,
                expected=(("min_count", MIN_CONTENT_POINTS_PER_OPERATION),),
                actual=(("actual_count", len(value)),),
            )
        if len(value) > maximum:
            return None, _field_failure(
                FieldContractRule.LIST_COUNT_EXCEEDED,
                field_path,
                expected=(("max_count", maximum),),
                actual=(("actual_count", len(value)),),
            )
        if not isinstance(source_refs, tuple):
            return None, _field_failure(
                FieldContractRule.INTERNAL_INVARIANT,
                field_path,
            )
        points: list[ContentPointSpecification] = []
        for index, item in enumerate(value):
            item_path = f"{field_path}[{index}]"
            if type(item) is not dict or set(item) != {"intent", "subject_ref"}:
                return None, _field_failure(
                    FieldContractRule.CONTENT_POINT_SHAPE_INVALID,
                    item_path,
                    expected=(("expected_keys", ("intent", "subject_ref")),),
                    actual=(
                        ("actual_type", _safe_actual_type(item)),
                        ("actual_count", len(item) if type(item) is dict else 0),
                    ),
                )
            try:
                intent = ContentPointIntent(item["intent"])
            except (TypeError, ValueError):
                return None, _field_failure(
                    FieldContractRule.ENUM_INVALID,
                    f"{item_path}.intent",
                    expected=(("expected_type", "string"),),
                    actual=(("actual_type", _safe_actual_type(item["intent"])),),
                )
            subject_ref = item["subject_ref"]
            if type(subject_ref) is not str:
                return None, _field_failure(
                    FieldContractRule.STRING_TYPE_INVALID,
                    f"{item_path}.subject_ref",
                    expected=(("expected_type", "string"),),
                    actual=(("actual_type", _safe_actual_type(subject_ref)),),
                )
            candidate = prompt.content_point_candidate(opportunity_ref, subject_ref)
            if candidate is None:
                if prompt.has_content_point_candidate_id(subject_ref):
                    return None, _validation_failure(
                        ChangePlanValidationCategory.EVIDENCE_USE_NOT_ALLOWED
                    )
                return None, _field_failure(
                    FieldContractRule.SUBJECT_REF_INVALID,
                    f"{item_path}.subject_ref",
                    expected=(("expected_type", "string"),),
                    actual=(("actual_type", "string"),),
                )
            points.append(
                ContentPointSpecification(intent, candidate.text, candidate.origin_ref)
            )
        return tuple(points), None

    def _parse_table(
        self,
        columns: object,
        dimensions: object,
        *,
        field_path: str,
    ) -> tuple[ComparisonTableSpecification | None, _ValidationFailure | None]:
        parsed_columns, failure = self._parse_string_tuple(
            columns,
            field_path=f"{field_path}.column_headers",
            minimum=MIN_TABLE_COLUMNS,
            maximum=MAX_TABLE_COLUMNS,
            maximum_chars=MAX_TABLE_LABEL_CHARS,
            reject_prose_syntax=True,
        )
        if parsed_columns is None:
            return None, failure
        parsed_dimensions, failure = self._parse_string_tuple(
            dimensions,
            field_path=f"{field_path}.row_dimensions",
            minimum=MIN_TABLE_DIMENSIONS,
            maximum=MAX_TABLE_DIMENSIONS,
            maximum_chars=MAX_TABLE_LABEL_CHARS,
            reject_prose_syntax=True,
        )
        if parsed_dimensions is None:
            return None, failure
        return ComparisonTableSpecification(parsed_columns, parsed_dimensions), None

    def _parse_new_resource(
        self,
        raw: dict[str, object],
        *,
        suggested_source_page_refs: tuple[str, ...],
        opportunity_ref: str,
        field_path: str,
        page_refs: tuple[str, ...],
        source_refs: object,
        prompt: ChangePlanPrompt,
    ) -> tuple[NewResourceSpecification | None, _ValidationFailure | None]:
        outlines = prompt.deterministic_outline_headings_for(opportunity_ref)
        if not MIN_OUTLINE_HEADINGS <= len(outlines) <= MAX_OUTLINE_HEADINGS:
            return None, _validation_failure(
                ChangePlanValidationCategory.OPERATION_NOT_ALLOWED
            )
        points, failure = self._parse_content_points(
            raw["content_points"],
            opportunity_ref=opportunity_ref,
            field_path=f"{field_path}.content_points",
            source_refs=source_refs,
            prompt=prompt,
        )
        if points is None:
            return None, failure
        failure = self._validate_bounded_string(
            raw["proposed_title"],
            field_path=f"{field_path}.proposed_title",
            maximum=MAX_PROPOSED_HEADING_CHARS,
        )
        if failure is not None:
            return None, failure
        try:
            purpose = NewResourcePurpose(raw["resource_purpose"])
        except (TypeError, ValueError):
            return None, _field_failure(
                FieldContractRule.ENUM_INVALID,
                f"{field_path}.resource_purpose",
                expected=(("expected_type", "string"),),
                actual=(("actual_type", _safe_actual_type(raw["resource_purpose"])),),
            )
        nested_raw = raw["comparison_table_brief"]
        nested = None
        if nested_raw is not None:
            if type(nested_raw) is not dict or set(nested_raw) != {
                "column_headers",
                "row_dimensions",
            }:
                return None, _field_failure(
                    FieldContractRule.COMPARISON_TABLE_SHAPE_INVALID,
                    f"{field_path}.comparison_table_brief",
                    expected=(("expected_keys", ("column_headers", "row_dimensions")),),
                    actual=(
                        ("actual_type", _safe_actual_type(nested_raw)),
                        ("actual_count", len(nested_raw) if type(nested_raw) is dict else 0),
                    ),
                )
            nested, failure = self._parse_table(
                nested_raw["column_headers"],
                nested_raw["row_dimensions"],
                field_path=f"{field_path}.comparison_table_brief",
            )
            if nested is None:
                return None, failure
        return (
            NewResourceSpecification(
                purpose,
                raw["proposed_title"],
                outlines,
                points,
                suggested_source_page_refs,
                nested,
                prompt.input.customer_context.section_briefs() if prompt.input.customer_context else (),
            ),
            None,
        )

    @staticmethod
    def _parse_page_bindings(
        value: object,
        *,
        field_path: str,
    ) -> tuple[
        tuple[tuple[str, ...], tuple[str, ...]] | None,
        _ValidationFailure | None,
    ]:
        if type(value) is not list:
            return None, _field_failure(
                FieldContractRule.LIST_TYPE_INVALID,
                field_path,
                expected=(("expected_type", "array"),),
                actual=(("actual_type", _safe_actual_type(value)),),
            )
        if len(value) > MAX_PAGE_REFS_PER_OPERATION:
            return None, _field_failure(
                FieldContractRule.LIST_COUNT_EXCEEDED,
                field_path,
                expected=(("max_count", MAX_PAGE_REFS_PER_OPERATION),),
                actual=(("actual_count", len(value)),),
            )
        page_refs: list[str] = []
        suggestions: list[str] = []
        for index, binding in enumerate(value):
            binding_path = f"{field_path}[{index}]"
            if type(binding) is not dict or set(binding) != {
                "page_ref",
                "suggested_source",
            }:
                return None, _field_failure(
                    FieldContractRule.PAGE_BINDING_SHAPE_INVALID,
                    binding_path,
                    expected=(("expected_keys", ("page_ref", "suggested_source")),),
                    actual=(
                        ("actual_type", _safe_actual_type(binding)),
                        ("actual_count", len(binding) if type(binding) is dict else 0),
                    ),
                )
            if type(binding["page_ref"]) is not str:
                return None, _field_failure(
                    FieldContractRule.STRING_TYPE_INVALID,
                    f"{binding_path}.page_ref",
                    expected=(("expected_type", "string"),),
                    actual=(("actual_type", _safe_actual_type(binding["page_ref"])),),
                )
            if type(binding["suggested_source"]) is not bool:
                return None, _field_failure(
                    FieldContractRule.PAGE_BINDING_SHAPE_INVALID,
                    f"{binding_path}.suggested_source",
                    expected=(("expected_type", "boolean"),),
                    actual=(("actual_type", _safe_actual_type(binding["suggested_source"])),),
                )
            if binding["page_ref"] in page_refs:
                return None, _field_failure(
                    FieldContractRule.PAGE_BINDING_DUPLICATE,
                    field_path,
                    actual=(("actual_count", len(value)),),
                )
            page_refs.append(binding["page_ref"])
            if binding["suggested_source"]:
                suggestions.append(binding["page_ref"])
        return (tuple(page_refs), tuple(suggestions)), None

    @staticmethod
    def _failure(
        status: ChangePlanStatus,
        category: ChangePlanValidationCategory | None = None,
        *,
        final_validation_category: PlanningValidationCategory | None = None,
        writer_attempt_count: int | None = None,
    ) -> ChangePlanReport:
        return ChangePlanReport(
            status=status,
            operations=(),
            limitations=(),
            error=None if category is None else category.value,
            final_validation_category=final_validation_category,
            writer_attempt_count=writer_attempt_count,
        )
