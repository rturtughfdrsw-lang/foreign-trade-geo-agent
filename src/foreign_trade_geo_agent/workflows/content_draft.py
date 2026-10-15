"""Strict parsing, evidence validation, and finalization for content drafts."""

from __future__ import annotations

import asyncio
from dataclasses import replace
import json
import math

from foreign_trade_geo_agent.core.draft_customer_evidence import InterpretationProposal
from foreign_trade_geo_agent.core.change_plan import (
    ChangeOperation,
    ChangeOperationType,
)
from foreign_trade_geo_agent.core.content_draft import (
    CONTENT_DRAFT_LIMITATIONS,
    CONTENT_DRAFT_REPAIR_CATEGORIES,
    MAX_CONTENT_DRAFT_TIMEOUT_SECONDS,
    MAX_PROVIDER_CALLS,
    MAX_TABLE_COLUMNS,
    MAX_TABLE_ROWS,
    MAX_RAW_OUTPUT_BYTES,
    MAX_RAW_OUTPUT_CHARS,
    MAX_USER_MATERIAL_BYTES,
    MAX_USER_MATERIAL_CHARS,
    BulletListSpecification,
    ClaimTypeViolation,
    CompetitorMentionViolation,
    NumericGroundingViolation,
    ContentDraftGeneration,
    ContentDraftGenerationFailureKind,
    ContentDraftGenerationStatus,
    ContentDraftInput,
    ContentDraftPrompt,
    ContentDraftReport,
    ContentDraftSpecification,
    ContentDraftStatus,
    ContentDraftType,
    ContentDraftValidationCategory,
    DraftBlockKind,
    DraftBlockBudgetViolation,
    DraftClaimSpecification,
    DraftClaimType,
    NewResourceSectionSpecification,
    ParagraphSpecification,
    TableCellSpecification,
    build_content_draft_prompt,
    content_draft_requires_provider,
    describe_competitor_mention,
    describe_claim_type_violation,
    describe_numeric_grounding_violation,
    describe_draft_block_budget_violation,
    finalize_draft_item,
    stable_content_draft_input_error,
    table_coordinate_catalog,
)
from foreign_trade_geo_agent.core.ports import ContentDraftWriter, ContentDraftAdmission
from foreign_trade_geo_agent.core.p_only_draft import (
    POnlyDraftConsumer, POnlyDraftGenerator, POnlyDraftRequestV1, POnlyDraftResultV1,
    coverage_proof, final_coverage_error, material_for, render_body, specification_coverage_error,
    verify_coverage_proof,
)


def _strict_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _string_tuple(value: object) -> tuple[str, ...] | None:
    if type(value) is not list or any(type(item) is not str for item in value):
        return None
    return tuple(value)


def _exact_keys(raw: object, expected: set[str]) -> bool:
    return type(raw) is dict and set(raw) == expected


def _parse_claim(raw: object) -> DraftClaimSpecification:
    proposal = None
    if type(raw) is dict and "proposal" in raw:
        raw = dict(raw)
        value = raw.pop("proposal")
        keys = {"procurement_question", "reasoning", "assumptions", "limitation", "procurement_action"}
        if not _exact_keys(value, keys):
            raise ValueError("FIELD_CONTRACT")
        try:
            proposal = InterpretationProposal(**value)
        except (ValueError, TypeError):
            raise ValueError("FIELD_CONTRACT") from None
    if not (_exact_keys(raw, {"text", "claim_type", "page_refs", "source_refs"})
            or _exact_keys(raw, {"text", "claim_type", "page_refs", "source_refs", "customer_refs"})):
        raise ValueError(ContentDraftValidationCategory.FIELD_CONTRACT.value)
    assert isinstance(raw, dict)
    text = raw["text"]
    if type(text) is not str:
        raise ValueError(ContentDraftValidationCategory.FIELD_CONTRACT.value)
    try:
        claim_type = DraftClaimType(raw["claim_type"])
    except (TypeError, ValueError):
        raise ValueError(ContentDraftValidationCategory.FIELD_CONTRACT.value) from None
    page_refs = _string_tuple(raw["page_refs"])
    source_refs = _string_tuple(raw["source_refs"])
    customer_refs = _string_tuple(raw.get("customer_refs", []))
    if page_refs is None or source_refs is None or customer_refs is None:
        raise ValueError(ContentDraftValidationCategory.FIELD_CONTRACT.value)
    return DraftClaimSpecification(text, claim_type, page_refs, source_refs, customer_refs, proposal)


def _parse_block(raw: object):
    if not type(raw) is dict:
        raise ValueError(ContentDraftValidationCategory.FIELD_CONTRACT.value)
    kind_value = raw.get("kind")
    try:
        kind = DraftBlockKind(kind_value)
    except (TypeError, ValueError):
        raise ValueError(ContentDraftValidationCategory.FIELD_CONTRACT.value) from None
    if kind is DraftBlockKind.PARAGRAPH:
        if not _exact_keys(raw, {"kind", "claims"}):
            raise ValueError(ContentDraftValidationCategory.FIELD_CONTRACT.value)
        claims = tuple(_parse_claim(item) for item in raw["claims"])
        return ParagraphSpecification(kind, claims)
    if kind is DraftBlockKind.BULLET_LIST:
        if not _exact_keys(raw, {"kind", "items"}):
            raise ValueError(ContentDraftValidationCategory.FIELD_CONTRACT.value)
        items = tuple(_parse_claim(item) for item in raw["items"])
        return BulletListSpecification(kind, items)
    raise ValueError(ContentDraftValidationCategory.FIELD_CONTRACT.value)


def _parse_cell(raw: object) -> tuple[str, str, tuple[str, ...], tuple[str, ...]]:
    if not _exact_keys(raw, {"cell_ref", "text", "page_refs", "source_refs"}):
        raise ValueError(ContentDraftValidationCategory.FIELD_CONTRACT.value)
    assert isinstance(raw, dict)
    if type(raw["cell_ref"]) is not str or type(raw["text"]) is not str:
        raise ValueError(ContentDraftValidationCategory.FIELD_CONTRACT.value)
    page_refs = _string_tuple(raw["page_refs"])
    source_refs = _string_tuple(raw["source_refs"])
    if page_refs is None or source_refs is None:
        raise ValueError(ContentDraftValidationCategory.FIELD_CONTRACT.value)
    return raw["cell_ref"], raw["text"], page_refs, source_refs


def _materialize_table_cells(
    raw_cells: object, operation: ChangeOperation | None,
) -> tuple[TableCellSpecification, ...]:
    if type(raw_cells) is not list:
        raise ValueError(ContentDraftValidationCategory.FIELD_CONTRACT.value)
    if len(raw_cells) > MAX_TABLE_ROWS * MAX_TABLE_COLUMNS:
        raise ValueError(ContentDraftValidationCategory.BLOCK_BUDGET.value)
    if operation is None or operation.comparison_table_spec is None:
        raise ValueError(ContentDraftValidationCategory.TABLE_SCHEMA_MISMATCH.value)
    catalog = table_coordinate_catalog(operation)
    by_ref = {ref: (row, column) for ref, row, column in catalog}
    specified: dict[str, TableCellSpecification] = {}
    for raw in raw_cells:
        ref, text, page_refs, source_refs = _parse_cell(raw)
        if ref not in by_ref or ref in specified:
            raise ValueError(ContentDraftValidationCategory.TABLE_SCHEMA_MISMATCH.value)
        row, column = by_ref[ref]
        specified[ref] = TableCellSpecification(row, column, text, page_refs, source_refs)

    schema = operation.comparison_table_spec
    if (
        {cell.column for cell in specified.values()} != set(schema.column_headers)
        or {cell.row_dimension for cell in specified.values()} != set(schema.row_dimensions)
    ):
        raise ValueError(ContentDraftValidationCategory.TABLE_SCHEMA_MISMATCH.value)

    # Choose the earliest approved coordinate that does not skip an as-yet
    # unseen row or column. This preserves the original validator's ordered
    # first-occurrence rule without requiring a full Cartesian grid.
    row_index = {row: index for index, row in enumerate(schema.row_dimensions)}
    column_index = {column: index for index, column in enumerate(schema.column_headers)}
    remaining = set(specified)
    ordered: list[TableCellSpecification] = []
    seen_rows: set[str] = set()
    seen_columns: set[str] = set()
    while remaining:
        next_ref = next((
            ref for ref, row, column in catalog
            if ref in remaining
            and row_index[row] <= len(seen_rows)
            and column_index[column] <= len(seen_columns)
        ), None)
        if next_ref is None:
            raise ValueError(ContentDraftValidationCategory.TABLE_SCHEMA_MISMATCH.value)
        cell = specified[next_ref]
        ordered.append(cell)
        seen_rows.add(cell.row_dimension)
        seen_columns.add(cell.column)
        remaining.remove(next_ref)
    return tuple(ordered)


def _parse_specification(
    text: str,
    *,
    expected_change_ref: str,
    operation: ChangeOperation | None = None,
) -> ContentDraftSpecification:
    if len(text) > MAX_RAW_OUTPUT_CHARS or len(text.encode("utf-8")) > MAX_RAW_OUTPUT_BYTES:
        raise ValueError(ContentDraftValidationCategory.OUTPUT_TOO_LARGE.value)
    try:
        payload = json.loads(text, object_pairs_hook=_strict_json_object)
    except (json.JSONDecodeError, TypeError, ValueError):
        raise ValueError(ContentDraftValidationCategory.JSON_FORMAT.value) from None
    if not _exact_keys(payload, {"draft"}):
        raise ValueError(ContentDraftValidationCategory.FIELD_CONTRACT.value)
    draft = payload["draft"]
    if not type(draft) is dict:
        raise ValueError(ContentDraftValidationCategory.FIELD_CONTRACT.value)
    if draft.get("change_ref") != expected_change_ref:
        raise ValueError(ContentDraftValidationCategory.UNKNOWN_CHANGE_REFERENCE.value)
    try:
        draft_type = ContentDraftType(draft.get("draft_type"))
    except (TypeError, ValueError):
        raise ValueError(ContentDraftValidationCategory.FIELD_CONTRACT.value) from None

    if draft_type is ContentDraftType.SECTION_DRAFT:
        if not _exact_keys(draft, {"change_ref", "draft_type", "blocks"}):
            raise ValueError(ContentDraftValidationCategory.FIELD_CONTRACT.value)
        blocks = tuple(_parse_block(item) for item in draft["blocks"])
        return ContentDraftSpecification(expected_change_ref, draft_type, blocks=blocks)
    if draft_type is ContentDraftType.COMPARISON_TABLE_DRAFT:
        if not _exact_keys(draft, {"change_ref", "draft_type", "cells"}):
            raise ValueError(ContentDraftValidationCategory.FIELD_CONTRACT.value)
        cells = _materialize_table_cells(draft["cells"], operation)
        return ContentDraftSpecification(expected_change_ref, draft_type, cells=cells)
    if draft_type is ContentDraftType.INTERNAL_LINK_DRAFT:
        if not _exact_keys(
            draft, {"change_ref", "draft_type", "anchor_text", "insertion_claims"}
        ):
            raise ValueError(ContentDraftValidationCategory.FIELD_CONTRACT.value)
        anchor_text = draft["anchor_text"]
        if type(anchor_text) is not str:
            raise ValueError(ContentDraftValidationCategory.FIELD_CONTRACT.value)
        claims = tuple(_parse_claim(item) for item in draft["insertion_claims"])
        return ContentDraftSpecification(
            expected_change_ref,
            draft_type,
            anchor_text=anchor_text,
            insertion_claims=claims,
        )
    if draft_type is ContentDraftType.NEW_RESOURCE_DRAFT:
        if not _exact_keys(draft, {"change_ref", "draft_type", "sections"}):
            raise ValueError(ContentDraftValidationCategory.FIELD_CONTRACT.value)
        sections = []
        for raw_section in draft["sections"]:
            if not _exact_keys(raw_section, {"outline_heading", "blocks"}):
                raise ValueError(ContentDraftValidationCategory.FIELD_CONTRACT.value)
            if type(raw_section["outline_heading"]) is not str:
                raise ValueError(ContentDraftValidationCategory.FIELD_CONTRACT.value)
            sections.append(
                NewResourceSectionSpecification(
                    raw_section["outline_heading"],
                    tuple(_parse_block(item) for item in raw_section["blocks"]),
                )
            )
        return ContentDraftSpecification(
            expected_change_ref, draft_type, sections=tuple(sections)
        )
    raise ValueError(ContentDraftValidationCategory.FIELD_CONTRACT.value)


def inspect_candidate_output(value, raw, *, current_snapshot_sha256):
    """Parse through the native parser, then produce a non-admitted Review view."""
    from foreign_trade_geo_agent.core.draft_candidate_review import inspect_specification
    operation = value.change_plan_report.operations[0]
    spec = _parse_specification(raw, expected_change_ref=operation.change_id, operation=operation)
    return inspect_specification(value, raw, spec, current_snapshot_sha256=current_snapshot_sha256)


class ContentDraftWorkflow:
    """Create bounded, human-reviewed content drafts one C# at a time."""

    limitations = CONTENT_DRAFT_LIMITATIONS

    def __init__(
        self,
        writer: ContentDraftWriter,
        *,
        generation_timeout: float = 40.0,
        total_timeout: float | None = None,
        p_only_consumer: POnlyDraftConsumer | None = None,
        p_only_generator: POnlyDraftGenerator | None = None,
        intake_admission: ContentDraftAdmission | None = None,
        max_repair_attempts: int = 1,
    ) -> None:
        if (
            type(generation_timeout) not in {int, float}
            or not math.isfinite(generation_timeout)
            or not 0 < generation_timeout <= MAX_CONTENT_DRAFT_TIMEOUT_SECONDS
        ):
            raise ValueError("generation_timeout must be finite, positive, and bounded.")
        if type(max_repair_attempts) is not int or max_repair_attempts not in {0, 1}:
            raise ValueError("Only zero or one repair attempt is supported.")
        self._max_repair_attempts = max_repair_attempts
        self._writer = writer
        self._intake_admission = intake_admission
        self.last_intake_rejection: str | None = None
        self._p_only_consumer, self._p_only_generator = p_only_consumer, p_only_generator
        self._generation_timeout = float(generation_timeout)
        if total_timeout is None:
            total_timeout = MAX_PROVIDER_CALLS * self._generation_timeout + 10.0
        if (
            type(total_timeout) not in {int, float}
            or not math.isfinite(total_timeout)
            or not 0 < total_timeout
        ):
            raise ValueError("total_timeout must be finite and positive.")
        self._total_timeout = float(total_timeout)
        self._last_competitor_mention_violation: CompetitorMentionViolation | None = None
        self._last_block_budget_violation: DraftBlockBudgetViolation | None = None
        self._last_numeric_grounding_violation: NumericGroundingViolation | None = None
        self._last_claim_type_violation: ClaimTypeViolation | None = None

    @property
    def last_claim_type_violation(self) -> ClaimTypeViolation | None:
        """Return text-free metadata for the terminal claim-type rejection."""

        return self._last_claim_type_violation

    @property
    def last_numeric_grounding_violation(self) -> NumericGroundingViolation | None:
        """Return only terminal, process-local numeric failure metadata."""

        return self._last_numeric_grounding_violation

    @property
    def last_block_budget_violation(self) -> DraftBlockBudgetViolation | None:
        """Return terminal, text-free structural diagnostics in this process."""

        return self._last_block_budget_violation

    @property
    def last_competitor_mention_violation(self) -> CompetitorMentionViolation | None:
        """Return text-free process-local diagnostics for the terminal failure."""

        return self._last_competitor_mention_violation

    async def run(self, value: ContentDraftInput) -> ContentDraftReport:
        self.last_intake_rejection = None
        self._last_competitor_mention_violation = None
        self._last_block_budget_violation = None
        self._last_numeric_grounding_violation = None
        self._last_claim_type_violation = None
        if not isinstance(value, ContentDraftInput):
            return self._failure(ContentDraftStatus.INVALID_INPUT, ContentDraftValidationCategory.FIELD_CONTRACT)
        if self._intake_admission is not None:
            try:
                reason = self._intake_admission.rejection_reason(value)
                # This legacy port checks a binding, not an executable purpose.
                # It cannot freeze inputs or guarantee current authority across
                # an awaited writer call. Refuse even a permissive old adapter.
                if reason is None:
                    reason = "DRAFT_EXECUTION_AUTHORIZATION_REQUIRED"
                # Boundary details stay transient; never persist adapter errors.
                self.last_intake_rejection = reason if type(reason) is str and reason in {
                    "INTAKE_BINDING_REQUIRED", "STALE_INTAKE_BINDING", "INTAKE_PLAN_BINDING_INVALID",
                    "INTAKE_TASK_BINDING_INVALID", "CUSTOMER_EVIDENCE_DRAFT_AUTHORIZATION_REQUIRED",
                    "DRAFT_EXECUTION_AUTHORIZATION_REQUIRED",
                    "ARTICLE_SCOPE_REVIEW_REQUIRED", "ARTICLE_SCOPE_MISMATCH",
                } else "INTAKE_EXECUTION_BLOCKED"
                return self._failure(ContentDraftStatus.INVALID_INPUT,
                                     ContentDraftValidationCategory.INTAKE_EXECUTION_BLOCKED)
            except Exception:
                self.last_intake_rejection = "INTAKE_STATE_UNAVAILABLE"
                return self._failure(ContentDraftStatus.INVALID_INPUT,
                                     ContentDraftValidationCategory.INTAKE_EXECUTION_BLOCKED)
        try:
            return await asyncio.wait_for(self._run(value), timeout=self._total_timeout)
        except (TimeoutError, asyncio.TimeoutError):
            return self._failure(ContentDraftStatus.WORKFLOW_TIMEOUT)

    async def run_p_only(self, request: POnlyDraftRequestV1) -> POnlyDraftResultV1:
        """Explicit V1 opt-in on the SAME workflow; ordinary run remains strict.

        No provider or retry. Failed candidates never leave this method. The
        generator receives copy material, not the authorized input graph.
        """
        def rejected(reason, status=ContentDraftStatus.INVALID_INPUT):
            return POnlyDraftResultV1(self._failure(status, ContentDraftValidationCategory.FIELD_CONTRACT),
                                     None, None, reason)
        if self._intake_admission is not None:
            # A legacy excerpt purpose cannot bypass an application-bound
            # customer EXPLAIN task. Ordinary P-only composition is unchanged.
            return rejected("INTAKE_TASK_PROFILE_REQUIRED")
        if self._p_only_consumer is None or self._p_only_generator is None:
            return rejected("DRAFT_AUTHORIZATION_REQUIRED")
        try:
            execution = self._p_only_consumer.prepare(request)
            self._p_only_consumer.revalidate(execution)
        except Exception:
            return rejected("DRAFT_AUTHORIZATION_REQUIRED")
        try:
            generation = self._p_only_generator.generate(material_for(execution.target))
            if specification_coverage_error(execution.target, generation):
                return rejected("VERBATIM_COVERAGE_INVALID", ContentDraftStatus.INVALID_OUTPUT)
            value = execution.target.draft_input
            draft, error = self._finalize(1, generation.specification, value.change_plan_report.operations[0], value)
            if error is not None:
                return POnlyDraftResultV1(self._failure(ContentDraftStatus.INVALID_OUTPUT,
                    ContentDraftValidationCategory(error)), None, None, "BASE_DRAFT_VALIDATION_FAILED")
            report = ContentDraftReport(ContentDraftStatus.SUCCESS, (draft,), self.limitations, None)
            body = render_body(execution.target, draft)
            if final_coverage_error(execution.target, report, body):
                return rejected("VERBATIM_COVERAGE_INVALID", ContentDraftStatus.INVALID_OUTPUT)
        except Exception:
            return rejected("VERBATIM_COVERAGE_INVALID", ContentDraftStatus.INVALID_OUTPUT)
        try:
            # Recheck current receipt/key/grants/registration and BOTH digests
            # after generation/finalization, discarding revoked/expired outputs.
            if request != execution.request:
                raise ValueError()
            review = self._p_only_consumer.revalidate(execution)
            proof = coverage_proof(execution, review, report, body)
            if not verify_coverage_proof(execution, review, report, body, proof):
                raise ValueError()
            return POnlyDraftResultV1(report, body, proof, None)
        except Exception:
            return rejected("DRAFT_AUTHORIZATION_REQUIRED")

    async def _run(self, value: ContentDraftInput) -> ContentDraftReport:
        input_error = stable_content_draft_input_error(value)
        if input_error is not None:
            return self._failure(
                ContentDraftStatus.INVALID_INPUT,
                ContentDraftValidationCategory(input_error),
            )

        operations = value.change_plan_report.operations
        if not operations:
            return ContentDraftReport(
                status=ContentDraftStatus.SUCCESS,
                drafts=(),
                limitations=self.limitations,
                error=None,
            )

        drafts = []
        provider_calls = 0
        for number, operation in enumerate(operations, start=1):
            if not content_draft_requires_provider(operation.operation_type):
                specification = ContentDraftSpecification(
                    change_ref=operation.change_id,
                    draft_type=ContentDraftType.STRUCTURE_ONLY,
                )
                draft, error = self._finalize(
                    number, specification, operation, value
                )
            else:
                prompt = build_content_draft_prompt(value, operation.change_id)
                remaining_provider_operations = sum(
                    content_draft_requires_provider(item.operation_type)
                    for item in operations[number:]
                )
                for attempt in range(1 + self._max_repair_attempts):
                    material = prompt.material_json()
                    if (
                        len(material) > MAX_USER_MATERIAL_CHARS
                        or len(material.encode("utf-8")) > MAX_USER_MATERIAL_BYTES
                    ):
                        return self._failure(
                            ContentDraftStatus.INPUT_TOO_LARGE,
                            ContentDraftValidationCategory.INPUT_TOO_LARGE,
                        )
                    if provider_calls >= MAX_PROVIDER_CALLS:
                        return self._failure(ContentDraftStatus.GENERATION_FAILED)
                    provider_calls += 1
                    generation = await self._generate(prompt)
                    if generation.status is ContentDraftGenerationStatus.FAILED:
                        if (
                            generation.failure_kind
                            is ContentDraftGenerationFailureKind.INPUT_TOO_LARGE
                        ):
                            return self._failure(
                                ContentDraftStatus.INPUT_TOO_LARGE,
                                ContentDraftValidationCategory.INPUT_TOO_LARGE,
                            )
                        return self._failure(ContentDraftStatus.GENERATION_FAILED)
                    try:
                        specification = _parse_specification(
                            generation.text or "",
                            expected_change_ref=operation.change_id,
                            operation=operation,
                        )
                    except ValueError as exc:
                        draft = None
                        error = str(exc)
                    else:
                        draft, error = self._finalize(
                            number, specification, operation, value
                        )
                    repair_category = (
                        None
                        if error is None
                        else ContentDraftValidationCategory(error)
                    )
                    retry_fits_call_budget = (
                        provider_calls + 1 + remaining_provider_operations
                        <= MAX_PROVIDER_CALLS
                    )
                    if (
                        attempt == 0
                        and self._max_repair_attempts == 1
                        and repair_category in CONTENT_DRAFT_REPAIR_CATEGORIES
                        and retry_fits_call_budget
                    ):
                        prompt = replace(
                            prompt,
                            repair_category=repair_category,
                        )
                        continue
                    break
            if error is not None:
                if error == ContentDraftValidationCategory.CLAIM_TYPE_CONTRACT.value:
                    self._last_claim_type_violation = describe_claim_type_violation(
                        number, specification, prompt
                    )
                if error == ContentDraftValidationCategory.NUMERIC_NOT_GROUNDED.value:
                    self._last_numeric_grounding_violation = describe_numeric_grounding_violation(
                        number, specification, prompt, attempt=attempt + 1
                    )
                if error == ContentDraftValidationCategory.BLOCK_BUDGET.value:
                    self._last_block_budget_violation = describe_draft_block_budget_violation(
                        specification, operation
                    )
                if error == ContentDraftValidationCategory.COMPETITOR_MENTION.value:
                    self._last_competitor_mention_violation = describe_competitor_mention(
                        number, specification, prompt
                    )
                return self._failure(
                    ContentDraftStatus.INVALID_OUTPUT,
                    ContentDraftValidationCategory(error),
                )
            assert draft is not None
            drafts.append(draft)

        return ContentDraftReport(
            status=ContentDraftStatus.SUCCESS,
            drafts=tuple(drafts),
            limitations=self.limitations,
            error=None,
        )

    async def _generate(self, prompt: ContentDraftPrompt) -> ContentDraftGeneration:
        try:
            return await asyncio.wait_for(
                self._writer.write_content_draft(prompt),
                timeout=self._generation_timeout,
            )
        except (TimeoutError, asyncio.TimeoutError):
            return ContentDraftGeneration(
                provider="deepseek",
                model="deepseek-flash",
                status=ContentDraftGenerationStatus.FAILED,
                text=None,
                error="Content draft generation timed out.",
            )
        except Exception:
            return ContentDraftGeneration(
                provider="deepseek",
                model="deepseek-flash",
                status=ContentDraftGenerationStatus.FAILED,
                text=None,
                error="Content draft generation failed.",
            )

    @staticmethod
    def _finalize(number, specification, operation, value):
        opportunity = next(
            item
            for item in value.opportunity_report.opportunities
            if item.recommendation_id == operation.opportunity_ref
        )
        return finalize_draft_item(
            number,
            specification,
            operation,
            opportunity,
            value.site_content,
            value.opportunity_report,
            customer_evidence=value.customer_evidence,
        )

    @staticmethod
    def _failure(
        status: ContentDraftStatus,
        category: ContentDraftValidationCategory | None = None,
    ) -> ContentDraftReport:
        return ContentDraftReport(
            status=status,
            drafts=(),
            limitations=(),
            error=None if category is None else category.value,
        )
