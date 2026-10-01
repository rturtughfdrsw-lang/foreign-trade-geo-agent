"""Strict parsing, evidence validation, and finalization for content drafts."""

from __future__ import annotations

import asyncio
import json
import math

from foreign_trade_geo_agent.core.change_plan import (
    ChangeOperationType,
)
from foreign_trade_geo_agent.core.content_draft import (
    CONTENT_DRAFT_LIMITATIONS,
    MAX_CONTENT_DRAFT_TIMEOUT_SECONDS,
    MAX_PROVIDER_CALLS,
    MAX_RAW_OUTPUT_BYTES,
    MAX_RAW_OUTPUT_CHARS,
    MAX_USER_MATERIAL_BYTES,
    MAX_USER_MATERIAL_CHARS,
    BulletListSpecification,
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
    DraftClaimSpecification,
    DraftClaimType,
    NewResourceSectionSpecification,
    ParagraphSpecification,
    TableCellSpecification,
    build_content_draft_prompt,
    content_draft_requires_provider,
    finalize_draft_item,
    stable_content_draft_input_error,
)
from foreign_trade_geo_agent.core.ports import ContentDraftWriter


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
    if not _exact_keys(raw, {"text", "claim_type", "page_refs", "source_refs"}):
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
    if page_refs is None or source_refs is None:
        raise ValueError(ContentDraftValidationCategory.FIELD_CONTRACT.value)
    return DraftClaimSpecification(text, claim_type, page_refs, source_refs)


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


def _parse_cell(raw: object) -> TableCellSpecification:
    if not _exact_keys(raw, {"row_dimension", "column", "text", "page_refs", "source_refs"}):
        raise ValueError(ContentDraftValidationCategory.FIELD_CONTRACT.value)
    assert isinstance(raw, dict)
    if (
        type(raw["row_dimension"]) is not str
        or type(raw["column"]) is not str
        or type(raw["text"]) is not str
    ):
        raise ValueError(ContentDraftValidationCategory.FIELD_CONTRACT.value)
    page_refs = _string_tuple(raw["page_refs"])
    source_refs = _string_tuple(raw["source_refs"])
    if page_refs is None or source_refs is None:
        raise ValueError(ContentDraftValidationCategory.FIELD_CONTRACT.value)
    return TableCellSpecification(
        raw["row_dimension"],
        raw["column"],
        raw["text"],
        page_refs,
        source_refs,
    )


def _parse_specification(
    text: str,
    *,
    expected_change_ref: str,
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
        cells = tuple(_parse_cell(item) for item in draft["cells"])
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


class ContentDraftWorkflow:
    """Create bounded, human-reviewed content drafts one C# at a time."""

    limitations = CONTENT_DRAFT_LIMITATIONS

    def __init__(
        self,
        writer: ContentDraftWriter,
        *,
        generation_timeout: float = 40.0,
        total_timeout: float | None = None,
    ) -> None:
        if (
            type(generation_timeout) not in {int, float}
            or not math.isfinite(generation_timeout)
            or not 0 < generation_timeout <= MAX_CONTENT_DRAFT_TIMEOUT_SECONDS
        ):
            raise ValueError("generation_timeout must be finite, positive, and bounded.")
        self._writer = writer
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

    async def run(self, value: ContentDraftInput) -> ContentDraftReport:
        if not isinstance(value, ContentDraftInput):
            return self._failure(ContentDraftStatus.INVALID_INPUT, ContentDraftValidationCategory.FIELD_CONTRACT)
        try:
            return await asyncio.wait_for(self._run(value), timeout=self._total_timeout)
        except (TimeoutError, asyncio.TimeoutError):
            return self._failure(ContentDraftStatus.WORKFLOW_TIMEOUT)

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
                material = prompt.material_json()
                if (
                    len(material) > MAX_USER_MATERIAL_CHARS
                    or len(material.encode("utf-8")) > MAX_USER_MATERIAL_BYTES
                ):
                    return self._failure(
                        ContentDraftStatus.INPUT_TOO_LARGE,
                        ContentDraftValidationCategory.INPUT_TOO_LARGE,
                    )
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
                    )
                except ValueError as exc:
                    return self._failure(
                        ContentDraftStatus.INVALID_OUTPUT,
                        ContentDraftValidationCategory(str(exc)),
                    )
                draft, error = self._finalize(
                    number, specification, operation, value
                )
            if error is not None:
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
