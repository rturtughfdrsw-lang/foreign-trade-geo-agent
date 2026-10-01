"""Evidence-grounded content draft models, budgets, and deterministic finalization."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
import math
import re
from types import MappingProxyType
import unicodedata

from .change_plan import (
    CHANGE_PLAN_LIMITATIONS,
    ChangeOperation,
    ChangeOperationType,
    ChangePlanReport,
    ChangePlanStatus,
    ChangeTargetKind,
    SectionLocator,
    SectionLocatorKind,
    build_change_plan_prompt,
    validate_change_plan_input,
)
from .change_plan import ChangePlanInput
from .content_opportunity import (
    CONTENT_OPPORTUNITY_ABSENCE_TERMS,
    ContentOpportunity,
    ContentOpportunityReport,
    ContentOpportunitySourceMaterial,
    ContentOpportunityStatus,
)
from .extraction import StructuredContentBlock, StructuredContentKind
from .site_content import SiteContentEvidence, SiteContentPacket


# --- Budgets -------------------------------------------------------------
MAX_DRAFTS = 8
MAX_PROVIDER_CALLS = 8
MAX_BLOCKS_PER_DRAFT = 8
MAX_CLAIMS_PER_BLOCK = 4
MAX_CLAIMS_PER_DRAFT = 16
MAX_CLAIM_CHARS = 300
MAX_PARAGRAPHS_PER_DRAFT = 4
MAX_BULLET_ITEMS = 6
MAX_BULLET_ITEM_CHARS = 220
MAX_TABLE_ROWS = 6
MAX_TABLE_COLUMNS = 5
MAX_TABLE_CELL_CHARS = 200
MAX_ANCHOR_TEXT_CHARS = 120
MAX_INSERTION_SENTENCE_CHARS = 300
MAX_TITLE_CHARS = 120
MAX_HEADING_CHARS = 120
MAX_TARGET_LANGUAGE_CHARS = 12
MAX_RAW_OUTPUT_CHARS = 16_000
MAX_RAW_OUTPUT_BYTES = 32 * 1024
MAX_SYSTEM_PROMPT_CHARS = 8_000
MAX_SYSTEM_PROMPT_BYTES = 16 * 1024
MAX_USER_MATERIAL_CHARS = 26_000
MAX_USER_MATERIAL_BYTES = 56 * 1024
MAX_INPUT_ENVELOPE_CHARS = 36_000
MAX_INPUT_ENVELOPE_BYTES = 76 * 1024
MAX_PROVIDER_TOKENS = 3_000
MAX_CONTENT_DRAFT_TIMEOUT_SECONDS = 120.0


CONTENT_DRAFT_LIMITATIONS = (
    "Draft content is based only on bounded, observed evidence.",
    "External S evidence is unverified context, not an authoritative citation.",
    "Factual claims remain subject to human review before any CMS use.",
    "Semantic locators are review targets, not CMS execution selectors.",
    "SUCCESS means generated and validated, never approved or published.",
    "Current CMS state must be revalidated before any WordPress write.",
)


# --- Enums ---------------------------------------------------------------


class ContentDraftStatus(str, Enum):
    SUCCESS = "success"
    INVALID_INPUT = "invalid_input"
    INPUT_TOO_LARGE = "input_too_large"
    GENERATION_FAILED = "generation_failed"
    INVALID_OUTPUT = "invalid_output"
    WORKFLOW_TIMEOUT = "workflow_timeout"


class ContentDraftGenerationStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"


class ContentDraftGenerationFailureKind(str, Enum):
    PROVIDER_FAILURE = "provider_failure"
    INPUT_TOO_LARGE = "input_too_large"


class ContentDraftValidationCategory(str, Enum):
    JSON_FORMAT = "JSON_FORMAT"
    FIELD_CONTRACT = "FIELD_CONTRACT"
    OUTPUT_TOO_LARGE = "OUTPUT_TOO_LARGE"
    INPUT_TOO_LARGE = "INPUT_TOO_LARGE"
    LANGUAGE_INVALID = "LANGUAGE_INVALID"
    UNKNOWN_CHANGE_REFERENCE = "UNKNOWN_CHANGE_REFERENCE"
    UNKNOWN_PAGE_REFERENCE = "UNKNOWN_PAGE_REFERENCE"
    UNKNOWN_SOURCE_REFERENCE = "UNKNOWN_SOURCE_REFERENCE"
    EVIDENCE_OUTSIDE_CHANGE_SCOPE = "EVIDENCE_OUTSIDE_CHANGE_SCOPE"
    CLAIM_TYPE_CONTRACT = "CLAIM_TYPE_CONTRACT"
    SUPPORT_KIND_CONTRACT = "SUPPORT_KIND_CONTRACT"
    FIRST_PARTY_FACT_WITHOUT_PAGE = "FIRST_PARTY_FACT_WITHOUT_PAGE"
    NUMERIC_NOT_GROUNDED = "NUMERIC_NOT_GROUNDED"
    UNSUPPORTED_PROMOTIONAL_CLAIM = "UNSUPPORTED_PROMOTIONAL_CLAIM"
    UNSUPPORTED_ABSENCE_CLAIM = "UNSUPPORTED_ABSENCE_CLAIM"
    COMPETITOR_MENTION = "COMPETITOR_MENTION"
    HEADING_MISMATCH = "HEADING_MISMATCH"
    TABLE_SCHEMA_MISMATCH = "TABLE_SCHEMA_MISMATCH"
    INTERNAL_LINK_INVALID = "INTERNAL_LINK_INVALID"
    NEW_RESOURCE_INVALID = "NEW_RESOURCE_INVALID"
    BLOCK_BUDGET = "BLOCK_BUDGET"
    CLAIM_BUDGET = "CLAIM_BUDGET"
    DUPLICATE_CLAIM = "DUPLICATE_CLAIM"
    DUPLICATE_DRAFT = "DUPLICATE_DRAFT"


class ContentDraftType(str, Enum):
    SECTION_DRAFT = "SECTION_DRAFT"
    COMPARISON_TABLE_DRAFT = "COMPARISON_TABLE_DRAFT"
    INTERNAL_LINK_DRAFT = "INTERNAL_LINK_DRAFT"
    NEW_RESOURCE_DRAFT = "NEW_RESOURCE_DRAFT"
    STRUCTURE_ONLY = "STRUCTURE_ONLY"


class DraftBlockKind(str, Enum):
    PARAGRAPH = "PARAGRAPH"
    BULLET_LIST = "BULLET_LIST"
    COMPARISON_TABLE = "COMPARISON_TABLE"
    INTERNAL_LINK = "INTERNAL_LINK"


class DraftClaimType(str, Enum):
    OBSERVED_PRODUCT_FACT = "OBSERVED_PRODUCT_FACT"
    GENERAL_TECHNICAL_CONTEXT = "GENERAL_TECHNICAL_CONTEXT"
    COMPARATIVE_CONTEXT = "COMPARATIVE_CONTEXT"
    EDITORIAL_TRANSITION = "EDITORIAL_TRANSITION"
    CALL_TO_ACTION = "CALL_TO_ACTION"


class DraftClaimSupportKind(str, Enum):
    FIRST_PARTY_OBSERVED = "FIRST_PARTY_OBSERVED"
    EXTERNAL_CONTEXT = "EXTERNAL_CONTEXT"
    MIXED_CONTEXT = "MIXED_CONTEXT"


CONTENT_DRAFT_TYPE_BY_OPERATION = MappingProxyType(
    {
        ChangeOperationType.EXPAND_SECTION: ContentDraftType.SECTION_DRAFT,
        ChangeOperationType.ADD_SECTION: ContentDraftType.SECTION_DRAFT,
        ChangeOperationType.ADD_COMPARISON_TABLE: ContentDraftType.COMPARISON_TABLE_DRAFT,
        ChangeOperationType.ADD_INTERNAL_LINK: ContentDraftType.INTERNAL_LINK_DRAFT,
        ChangeOperationType.CREATE_NEW_RESOURCE: ContentDraftType.NEW_RESOURCE_DRAFT,
        ChangeOperationType.PROPOSE_SECTION_REORDER: ContentDraftType.STRUCTURE_ONLY,
    }
)


def content_draft_type_for(operation_type: ChangeOperationType) -> ContentDraftType:
    return CONTENT_DRAFT_TYPE_BY_OPERATION[operation_type]


def content_draft_requires_provider(operation_type: ChangeOperationType) -> bool:
    return operation_type is not ChangeOperationType.PROPOSE_SECTION_REORDER


_FACTUAL_CLAIM_TYPES = frozenset(
    {
        DraftClaimType.OBSERVED_PRODUCT_FACT,
        DraftClaimType.GENERAL_TECHNICAL_CONTEXT,
        DraftClaimType.COMPARATIVE_CONTEXT,
    }
)


# --- Provider-independent generation ------------------------------------


@dataclass(frozen=True, slots=True)
class ContentDraftGeneration:
    provider: str
    model: str
    status: ContentDraftGenerationStatus
    text: str | None
    error: str | None
    failure_kind: ContentDraftGenerationFailureKind | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.status, ContentDraftGenerationStatus)
            or type(self.provider) is not str
            or not self.provider.strip()
            or type(self.model) is not str
            or not self.model.strip()
        ):
            raise ValueError("Content draft generation requires provider metadata.")
        if self.status is ContentDraftGenerationStatus.SUCCESS:
            if (
                self.text is None
                or not self.text.strip()
                or self.error is not None
                or self.failure_kind is not None
            ):
                raise ValueError("Successful content draft generation is invalid.")
        elif (
            self.text is not None
            or not self.error
            or self.failure_kind is not None
            and not isinstance(
                self.failure_kind, ContentDraftGenerationFailureKind
            )
        ):
            raise ValueError("Failed content draft generation is invalid.")


# --- Stable input --------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ContentDraftInput:
    site_content: SiteContentPacket
    opportunity_report: ContentOpportunityReport
    change_plan_report: ChangePlanReport
    target_language: str = "en"

    def __post_init__(self) -> None:
        if not isinstance(self.site_content, SiteContentPacket):
            raise TypeError("Content draft input requires SiteContentPacket.")
        if not isinstance(self.opportunity_report, ContentOpportunityReport):
            raise TypeError("Content draft input requires ContentOpportunityReport.")
        if not isinstance(self.change_plan_report, ChangePlanReport):
            raise TypeError("Content draft input requires ChangePlanReport.")
        if validate_target_language(self.target_language) is not None:
            raise ValueError("Content draft target language is invalid.")


_TARGET_LANGUAGE_RE = re.compile(r"[A-Za-z]{2,3}(?:[-_][A-Za-z0-9]{2,8})*")


def validate_target_language(value: object) -> str | None:
    if type(value) is not str or not value:
        return "LANGUAGE_INVALID"
    normalized = value.strip()
    if (
        len(normalized) > MAX_TARGET_LANGUAGE_CHARS
        or _TARGET_LANGUAGE_RE.fullmatch(normalized) is None
    ):
        return "LANGUAGE_INVALID"
    return None


def stable_content_draft_input_error(value: ContentDraftInput) -> str | None:
    """Reuse upstream stable validation rather than re-implementing C# rules."""

    try:
        change_input = ChangePlanInput(value.site_content, value.opportunity_report)
    except (AttributeError, TypeError, ValueError):
        return ContentDraftValidationCategory.FIELD_CONTRACT.value
    upstream_error = validate_change_plan_input(change_input)
    if upstream_error is not None:
        return upstream_error
    report = value.change_plan_report
    if (
        not isinstance(report, ChangePlanReport)
        or report.status is not ChangePlanStatus.SUCCESS
        or not report.requires_human_review
        or report.error is not None
        or report.limitations != CHANGE_PLAN_LIMITATIONS
        or not isinstance(report.operations, tuple)
        or len(report.operations) > MAX_DRAFTS
    ):
        return ContentDraftValidationCategory.FIELD_CONTRACT.value

    page_ids = {page.evidence_id for page in value.site_content.pages}
    source_ids = {material.source_id for material in value.opportunity_report.source_materials}
    opportunity_by_id = {
        item.recommendation_id: item for item in value.opportunity_report.opportunities
    }
    for operation in report.operations:
        if not isinstance(operation, ChangeOperation):
            return ContentDraftValidationCategory.FIELD_CONTRACT.value
        opportunity = opportunity_by_id.get(operation.opportunity_ref)
        if opportunity is None:
            return ContentDraftValidationCategory.UNKNOWN_CHANGE_REFERENCE.value
        if any(ref not in page_ids for ref in operation.page_refs):
            return ContentDraftValidationCategory.UNKNOWN_PAGE_REFERENCE.value
        if any(ref not in source_ids for ref in operation.source_refs):
            return ContentDraftValidationCategory.UNKNOWN_SOURCE_REFERENCE.value
        if any(ref not in opportunity.page_refs for ref in operation.page_refs):
            return ContentDraftValidationCategory.EVIDENCE_OUTSIDE_CHANGE_SCOPE.value
        if any(ref not in opportunity.source_refs for ref in operation.source_refs):
            return ContentDraftValidationCategory.EVIDENCE_OUTSIDE_CHANGE_SCOPE.value
    return None


# --- Specification models (provider output) ------------------------------


@dataclass(frozen=True, slots=True)
class DraftClaimSpecification:
    text: str
    claim_type: DraftClaimType
    page_refs: tuple[str, ...] = ()
    source_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ParagraphSpecification:
    kind: DraftBlockKind
    claims: tuple[DraftClaimSpecification, ...]


@dataclass(frozen=True, slots=True)
class BulletListSpecification:
    kind: DraftBlockKind
    items: tuple[DraftClaimSpecification, ...]


@dataclass(frozen=True, slots=True)
class TableCellSpecification:
    row_dimension: str
    column: str
    text: str
    page_refs: tuple[str, ...] = ()
    source_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class NewResourceSectionSpecification:
    outline_heading: str
    blocks: tuple[ParagraphSpecification | BulletListSpecification, ...]


@dataclass(frozen=True, slots=True)
class ContentDraftSpecification:
    change_ref: str
    draft_type: ContentDraftType
    blocks: tuple[ParagraphSpecification | BulletListSpecification, ...] = ()
    cells: tuple[TableCellSpecification, ...] = ()
    anchor_text: str | None = None
    insertion_claims: tuple[DraftClaimSpecification, ...] = ()
    sections: tuple[NewResourceSectionSpecification, ...] = ()


# --- Final models --------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DraftClaim:
    claim_id: str
    text: str
    claim_type: DraftClaimType
    support_kind: DraftClaimSupportKind | None
    page_refs: tuple[str, ...]
    source_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ParagraphBlock:
    kind: DraftBlockKind
    claims: tuple[DraftClaim, ...]


@dataclass(frozen=True, slots=True)
class BulletListBlock:
    kind: DraftBlockKind
    items: tuple[DraftClaim, ...]


@dataclass(frozen=True, slots=True)
class TableCell:
    row_dimension: str
    column: str
    text: str
    page_refs: tuple[str, ...]
    source_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ComparisonTableBlock:
    kind: DraftBlockKind
    cells: tuple[TableCell, ...]


@dataclass(frozen=True, slots=True)
class InternalLinkBlock:
    kind: DraftBlockKind
    anchor_text: str
    target_page_ref: str
    target_url: str
    insertion_claims: tuple[DraftClaim, ...]


DraftBlock = ParagraphBlock | BulletListBlock | ComparisonTableBlock | InternalLinkBlock


@dataclass(frozen=True, slots=True)
class DraftItem:
    draft_id: str
    change_ref: str
    opportunity_ref: str
    draft_type: ContentDraftType
    target_kind: ChangeTargetKind
    target_page_ref: str | None
    locator: SectionLocator
    heading: str | None
    ordered_headings: tuple[str, ...]
    blocks: tuple[DraftBlock, ...]
    page_refs: tuple[str, ...]
    source_refs: tuple[str, ...]
    requires_human_review: bool = True

    def __post_init__(self) -> None:
        if re.fullmatch(r"D[1-9][0-9]*", self.draft_id) is None:
            raise ValueError("Draft ID must be assigned by Python.")
        if not self.requires_human_review:
            raise ValueError("Content drafts require human review.")
        if not isinstance(self.blocks, tuple) or not all(
            isinstance(block, (ParagraphBlock, BulletListBlock, ComparisonTableBlock, InternalLinkBlock))
            for block in self.blocks
        ):
            raise ValueError("Draft blocks are invalid.")
        if not isinstance(self.ordered_headings, tuple):
            raise ValueError("Draft ordered headings are invalid.")


@dataclass(frozen=True, slots=True)
class ContentDraftReport:
    status: ContentDraftStatus
    drafts: tuple[DraftItem, ...]
    limitations: tuple[str, ...]
    error: str | None
    requires_human_review: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.status, ContentDraftStatus) or not self.requires_human_review:
            raise ValueError("Content draft reports require human review.")
        if not isinstance(self.drafts, tuple) or not all(
            isinstance(item, DraftItem) for item in self.drafts
        ):
            raise ValueError("Content draft report items are invalid.")
        if self.status is ContentDraftStatus.SUCCESS:
            if self.error is not None or self.limitations != CONTENT_DRAFT_LIMITATIONS:
                raise ValueError("Successful content draft report is invalid.")
            expected_ids = tuple(f"D{number}" for number in range(1, len(self.drafts) + 1))
            if tuple(item.draft_id for item in self.drafts) != expected_ids:
                raise ValueError("Content draft IDs are inconsistent.")
            if len(self.drafts) > MAX_DRAFTS:
                raise ValueError("Content draft report exceeds draft budget.")
        elif self.drafts or self.limitations:
            raise ValueError("Failed content draft reports cannot carry payloads.")
        if self.error is not None and self.error not in {
            item.value for item in ContentDraftValidationCategory
        }:
            raise ValueError("Content draft error must be an allowlisted category.")
        validation_failure = self.status in {
            ContentDraftStatus.INVALID_INPUT,
            ContentDraftStatus.INPUT_TOO_LARGE,
            ContentDraftStatus.INVALID_OUTPUT,
        }
        if validation_failure != (self.error is not None):
            raise ValueError("Content draft status and error are inconsistent.")


# --- Prompt --------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ContentDraftPrompt:
    input: ContentDraftInput
    change_ref: str
    operation: ChangeOperation
    opportunity: ContentOpportunity
    pages: tuple[SiteContentEvidence, ...]
    sources: tuple[ContentOpportunitySourceMaterial, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.input, ContentDraftInput):
            raise ValueError("Content draft prompt input is invalid.")

    def material_json(self) -> str:
        payload = {
            "contract": {
                "evidence_scope": "observed_present_only",
                "supports_absence_claims": False,
                "requires_human_review": True,
                "target_language": self.input.target_language,
                "untrusted_data": True,
            },
            "change": _operation_payload(self.operation),
            "opportunity": {
                "opportunity_ref": self.opportunity.recommendation_id,
                "topic": self.opportunity.topic,
                "action_codes": tuple(
                    action.value for action in self.opportunity.action_codes
                ),
            },
            "pages": [_page_payload(page) for page in self.pages],
            "sources": [
                {
                    "source_ref": source.source_id,
                    "title": source.title,
                    "content": source.content,
                    "content_truncated": source.content_truncated,
                }
                for source in self.sources
            ],
        }
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _operation_payload(operation: ChangeOperation) -> dict[str, object]:
    payload: dict[str, object] = {
        "change_ref": operation.change_id,
        "operation_type": operation.operation_type.value,
        "target_kind": operation.target_kind.value,
        "locator_kind": operation.locator.locator_kind.value,
        "target_page_ref": operation.locator.page_ref,
        "target_heading": operation.locator.observed_heading,
        "content_points": [
            {"intent": point.intent.value, "subject": point.subject}
            for point in operation.content_points
        ],
        "page_refs": operation.page_refs,
        "source_refs": operation.source_refs,
    }
    if operation.proposed_heading is not None:
        payload["proposed_heading"] = operation.proposed_heading
    if operation.section_purpose is not None:
        payload["section_purpose"] = operation.section_purpose.value
    if operation.comparison_table_spec is not None:
        payload["comparison_table"] = {
            "column_headers": operation.comparison_table_spec.column_headers,
            "row_dimensions": operation.comparison_table_spec.row_dimensions,
        }
    if operation.internal_link_spec is not None:
        payload["internal_link"] = {
            "source_page_ref": operation.internal_link_spec.source_page_ref,
            "target_page_ref": operation.internal_link_spec.target_page_ref,
            "anchor_intent": operation.internal_link_spec.anchor_intent,
        }
    if operation.new_resource_spec is not None:
        payload["new_resource"] = {
            "resource_purpose": operation.new_resource_spec.resource_purpose.value,
            "proposed_title": operation.new_resource_spec.proposed_title,
            "outline_headings": operation.new_resource_spec.outline_headings,
            "suggested_source_page_refs": operation.new_resource_spec.suggested_source_page_refs,
        }
    if operation.ordered_headings:
        payload["ordered_headings"] = operation.ordered_headings
    return payload


def _page_payload(page: SiteContentEvidence) -> dict[str, object]:
    return {
        "page_ref": page.evidence_id,
        "title": page.title,
        "description": page.description,
        "h1": page.h1,
        "h2": page.h2,
        "body_text": page.body_text,
        "structured_content": [
            {
                "kind": block.kind.value,
                "heading": block.heading,
                "rows": block.rows,
                "pairs": block.pairs,
                "items": block.items,
                "text": block.text,
            }
            for block in page.structured_content
            if block.kind is not StructuredContentKind.IMAGE_ALT
        ],
    }


def build_content_draft_prompt(value: ContentDraftInput, change_ref: str) -> ContentDraftPrompt:
    operation = next(
        (item for item in value.change_plan_report.operations if item.change_id == change_ref),
        None,
    )
    if operation is None:
        raise ValueError(f"Unknown change reference: {change_ref}")
    opportunity = next(
        (
            item
            for item in value.opportunity_report.opportunities
            if item.recommendation_id == operation.opportunity_ref
        ),
        None,
    )
    if opportunity is None:
        raise ValueError("Change operation references an unknown opportunity.")
    page_by_id = {page.evidence_id: page for page in value.site_content.pages}
    source_by_id = {
        source.source_id: source for source in value.opportunity_report.source_materials
    }
    pages = tuple(page_by_id[ref] for ref in operation.page_refs)
    sources = tuple(source_by_id[ref] for ref in operation.source_refs)
    return ContentDraftPrompt(
        input=value,
        change_ref=change_ref,
        operation=operation,
        opportunity=opportunity,
        pages=pages,
        sources=sources,
    )


# --- Deterministic evidence text ----------------------------------------


def _normalized_text(value: str | None) -> str:
    if value is None:
        return ""
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _evidence_text(page: SiteContentEvidence) -> str:
    parts = [
        _normalized_text(page.title),
        _normalized_text(page.description),
        *(_normalized_text(item) for item in page.h1),
        *(_normalized_text(item) for item in page.h2),
        _normalized_text(page.body_text),
    ]
    for block in page.structured_content:
        parts.append(_normalized_text(block.heading))
        parts.append(_normalized_text(block.text))
        for row in block.rows:
            parts.extend(_normalized_text(cell) for cell in row)
        for pair in block.pairs:
            parts.extend((_normalized_text(pair[0]), _normalized_text(pair[1])))
        parts.extend(_normalized_text(item) for item in block.items)
    return "\n".join(part for part in parts if part)


_NUMERIC_SPAN_RE = re.compile(r"(?<![\w])\d[\d.,%°\"'\-/]*")
_NUMERIC_TAIL_RE = re.compile(r"\s*(?:°[cf]?|%|\"|'|[a-zµ]+(?:/[a-zµ]+)?)")
_MODEL_TOKEN_RE = re.compile(r"\b[A-Za-z]{1,6}\d{1,6}\b")
_TITLE_CASE_RUN_RE = re.compile(r"\b[A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*)+\b")

_FIRST_PARTY_MARKERS = (
    "our company",
    "our factory",
    "our product",
    "our pump",
    "our ",
    " we ",
    "certification",
    "certified",
    "warranty",
    "maximum",
    "material code",
    "port size",
    "patented",
    "model ",
)

_ALWAYS_FORBIDDEN_PROMOTIONAL = (
    "best",
    "leading",
    "#1",
    "number one",
    "guaranteed",
    "safest",
    "superior",
)

_EVIDENCE_REQUIRED_PROMOTIONAL = ("certified", "patented")

_DRAFT_ABSENCE_TERMS = CONTENT_OPPORTUNITY_ABSENCE_TERMS + (
    "page lacks",
    "site lacks",
    "no faq",
    "previous page did not",
    "currently missing",
    "unlike competitors",
)


def _has_first_party_expression(text: str) -> bool:
    folded = _normalized_text(text)
    return any(marker in folded for marker in _FIRST_PARTY_MARKERS)


def extract_numeric_expressions(text: str) -> tuple[str, ...]:
    """Return normalized number+unit expressions for deterministic grounding."""

    normalized = _normalized_text(text)
    expressions: list[str] = []
    for match in _NUMERIC_SPAN_RE.finditer(normalized):
        expression = match.group(0)
        tail = _NUMERIC_TAIL_RE.match(normalized, match.end())
        if tail is not None and tail.group(0).strip():
            expression = expression + " " + tail.group(0).strip()
        expressions.append(expression.strip())
    return tuple(expressions)


def _is_bare_number(expression: str) -> bool:
    return re.search(r"[a-zµ%°\"'/-]", expression) is None


def _validate_numeric_grounding(text: str, evidence_text: str) -> str | None:
    """Require every number+unit expression to appear verbatim in the evidence."""

    for expression in extract_numeric_expressions(text):
        if _is_bare_number(expression):
            return ContentDraftValidationCategory.NUMERIC_NOT_GROUNDED.value
        if not _numeric_expression_is_present(expression, evidence_text):
            return ContentDraftValidationCategory.NUMERIC_NOT_GROUNDED.value
    return None


def _numeric_expression_is_present(expression: str, evidence_text: str) -> bool:
    """Return True only when ``expression`` is a whole numeric token occurrence."""

    length = len(expression)
    start = 0
    while True:
        index = evidence_text.find(expression, start)
        if index < 0:
            return False
        if not _embedded_in_number_before(evidence_text, index) and not _embedded_in_number_after(
            evidence_text, index + length
        ):
            return True
        start = index + 1


def _embedded_in_number_before(evidence_text: str, index: int) -> bool:
    """True when the token starts inside a larger numeric/decimal token."""

    if index <= 0:
        return False
    before = evidence_text[index - 1]
    if before.isdigit():
        return True
    if before in ".,":
        return index >= 2 and evidence_text[index - 2].isdigit()
    return False


def _embedded_in_number_after(evidence_text: str, after_index: int) -> bool:
    """True when the token ends inside a larger numeric/decimal token."""

    length = len(evidence_text)
    if after_index >= length:
        return False
    after = evidence_text[after_index]
    if after.isdigit():
        return True
    if after in ".,":
        return after_index + 1 < length and evidence_text[after_index + 1].isdigit()
    return False


def derive_first_party_entities(
    pages: tuple[SiteContentEvidence, ...] | list[SiteContentEvidence],
) -> frozenset[str]:
    """Derive model-like first-party identifiers observed in cited pages."""

    tokens: set[str] = set()
    for page in pages:
        for value in (
            page.title,
            page.description,
            *page.h1,
            *page.h2,
            page.body_text,
        ):
            if not value:
                continue
            for token in _MODEL_TOKEN_RE.findall(value):
                tokens.add(token.casefold())
    return frozenset(tokens)


def _contains_first_party_entity(text: str, entities: frozenset[str]) -> bool:
    folded = _normalized_text(text)
    return any(entity in folded for entity in entities)


def _has_promotional_term(text: str) -> str | None:
    folded = _normalized_text(text)
    for term in _ALWAYS_FORBIDDEN_PROMOTIONAL:
        if term in folded:
            return term
    return None


def _has_absence_term(text: str) -> str | None:
    folded = _normalized_text(text)
    for term in _DRAFT_ABSENCE_TERMS:
        if term in folded:
            return term
    return None


def _has_competitor_mention(
    text: str,
    *,
    first_party_text: str,
) -> str | None:
    """Flag title-case runs that are not observed first-party entities."""

    folded_first = first_party_text.casefold()
    for run in _TITLE_CASE_RUN_RE.findall(text):
        folded = run.casefold()
        if folded not in folded_first:
            return run
    return None


def _derived_support_kind(
    claim_type: DraftClaimType,
    page_refs: tuple[str, ...],
    source_refs: tuple[str, ...],
) -> DraftClaimSupportKind | None:
    if claim_type not in _FACTUAL_CLAIM_TYPES:
        return None
    has_page = bool(page_refs)
    has_source = bool(source_refs)
    if has_page and has_source:
        return DraftClaimSupportKind.MIXED_CONTEXT
    if has_page:
        return DraftClaimSupportKind.FIRST_PARTY_OBSERVED
    if has_source:
        return DraftClaimSupportKind.EXTERNAL_CONTEXT
    return None


def _validate_claim_evidence(
    claim: DraftClaimSpecification,
    *,
    page_ids: set[str],
    source_ids: set[str],
    allowed_pages: set[str],
    allowed_sources: set[str],
    page_text_by_id: dict[str, str],
    first_party_text: str,
    first_party_entities: frozenset[str],
) -> str | None:
    text = claim.text
    if type(text) is not str or not text.strip():
        return ContentDraftValidationCategory.FIELD_CONTRACT.value
    normalized = " ".join(text.split())
    if not normalized or len(normalized) > MAX_CLAIM_CHARS:
        return ContentDraftValidationCategory.CLAIM_BUDGET.value
    if any(unicodedata.category(char).startswith("C") for char in normalized):
        return ContentDraftValidationCategory.FIELD_CONTRACT.value
    if not isinstance(claim.claim_type, DraftClaimType):
        return ContentDraftValidationCategory.FIELD_CONTRACT.value
    if not isinstance(claim.page_refs, tuple) or not isinstance(claim.source_refs, tuple):
        return ContentDraftValidationCategory.FIELD_CONTRACT.value

    for ref in claim.page_refs:
        if ref not in page_ids:
            return ContentDraftValidationCategory.UNKNOWN_PAGE_REFERENCE.value
        if ref not in allowed_pages:
            return ContentDraftValidationCategory.EVIDENCE_OUTSIDE_CHANGE_SCOPE.value
    for ref in claim.source_refs:
        if ref not in source_ids:
            return ContentDraftValidationCategory.UNKNOWN_SOURCE_REFERENCE.value
        if ref not in allowed_sources:
            return ContentDraftValidationCategory.EVIDENCE_OUTSIDE_CHANGE_SCOPE.value

    support_kind = _derived_support_kind(claim.claim_type, claim.page_refs, claim.source_refs)
    is_first_party_expression = (
        claim.claim_type is DraftClaimType.OBSERVED_PRODUCT_FACT
        or _has_first_party_expression(normalized)
        or _contains_first_party_entity(normalized, first_party_entities)
    )

    if claim.claim_type is DraftClaimType.OBSERVED_PRODUCT_FACT:
        if not claim.page_refs:
            return ContentDraftValidationCategory.FIRST_PARTY_FACT_WITHOUT_PAGE.value
    if claim.claim_type in _FACTUAL_CLAIM_TYPES and support_kind is None:
        return ContentDraftValidationCategory.SUPPORT_KIND_CONTRACT.value
    if (
        claim.claim_type in _FACTUAL_CLAIM_TYPES
        and is_first_party_expression
        and not claim.page_refs
    ):
        return ContentDraftValidationCategory.FIRST_PARTY_FACT_WITHOUT_PAGE.value
    if (
        claim.claim_type
        in (DraftClaimType.EDITORIAL_TRANSITION, DraftClaimType.CALL_TO_ACTION)
        and (claim.page_refs or claim.source_refs)
    ):
        return ContentDraftValidationCategory.CLAIM_TYPE_CONTRACT.value

    if claim.claim_type in _FACTUAL_CLAIM_TYPES and is_first_party_expression:
        combined_page_text = "\n".join(
            page_text_by_id[ref] for ref in claim.page_refs
        )
        numeric_error = _validate_numeric_grounding(normalized, combined_page_text)
        if numeric_error is not None:
            return numeric_error
    if claim.claim_type in (
        DraftClaimType.EDITORIAL_TRANSITION,
        DraftClaimType.CALL_TO_ACTION,
    ):
        if (
            extract_numeric_expressions(normalized)
            or is_first_party_expression
            or _has_promotional_term(normalized)
        ):
            return ContentDraftValidationCategory.CLAIM_TYPE_CONTRACT.value

    if _has_absence_term(normalized):
        return ContentDraftValidationCategory.UNSUPPORTED_ABSENCE_CLAIM.value
    if _has_competitor_mention(
        normalized,
        first_party_text=first_party_text,
    ):
        return ContentDraftValidationCategory.COMPETITOR_MENTION.value
    if _has_promotional_term(normalized):
        return ContentDraftValidationCategory.UNSUPPORTED_PROMOTIONAL_CLAIM.value
    for term in _EVIDENCE_REQUIRED_PROMOTIONAL:
        if term in _normalized_text(normalized) and not claim.page_refs:
            return ContentDraftValidationCategory.FIRST_PARTY_FACT_WITHOUT_PAGE.value
    return None


# --- Deterministic finalization -----------------------------------------


@dataclass(frozen=True, slots=True)
class _DraftEvidence:
    page_ids: set[str]
    source_ids: set[str]
    allowed_pages: set[str]
    allowed_sources: set[str]
    page_text_by_id: dict[str, str]
    first_party_text: str
    first_party_entities: frozenset[str]


def _build_evidence_context(
    operation: ChangeOperation,
    site_content: SiteContentPacket,
    opportunity_report: ContentOpportunityReport,
) -> _DraftEvidence:
    page_ids = {page.evidence_id for page in site_content.pages}
    source_ids = {source.source_id for source in opportunity_report.source_materials}
    page_text_by_id = {page.evidence_id: _evidence_text(page) for page in site_content.pages}
    allowed_pages = set(operation.page_refs)
    allowed_sources = set(operation.source_refs)
    first_party_text = " ".join(page_text_by_id[ref] for ref in operation.page_refs)
    cited_pages = tuple(
        page for page in site_content.pages if page.evidence_id in allowed_pages
    )
    first_party_entities = derive_first_party_entities(cited_pages)
    return _DraftEvidence(
        page_ids=page_ids,
        source_ids=source_ids,
        allowed_pages=allowed_pages,
        allowed_sources=allowed_sources,
        page_text_by_id=page_text_by_id,
        first_party_text=first_party_text,
        first_party_entities=first_party_entities,
    )


class _ClaimState:
    """Shared, deterministic claim numbering and canonical duplicate tracking."""

    def __init__(self) -> None:
        self.counter = 0
        self.seen: set[tuple[object, ...]] = set()


def _factual_identity(
    text: str,
    page_refs: tuple[str, ...],
    source_refs: tuple[str, ...],
) -> tuple[object, ...]:
    return (_normalized_text(text), tuple(page_refs), tuple(source_refs))


def _finalize_claim(
    state: _ClaimState,
    claim: DraftClaimSpecification,
    evidence: _DraftEvidence,
) -> tuple[DraftClaim | None, str | None]:
    error = _validate_claim_evidence(
        claim,
        page_ids=evidence.page_ids,
        source_ids=evidence.source_ids,
        allowed_pages=evidence.allowed_pages,
        allowed_sources=evidence.allowed_sources,
        page_text_by_id=evidence.page_text_by_id,
        first_party_text=evidence.first_party_text,
        first_party_entities=evidence.first_party_entities,
    )
    if error is not None:
        return None, error
    support_kind = _derived_support_kind(claim.claim_type, claim.page_refs, claim.source_refs)
    state.counter += 1
    identity = _factual_identity(claim.text, claim.page_refs, claim.source_refs)
    if identity in state.seen:
        return None, ContentDraftValidationCategory.DUPLICATE_CLAIM.value
    state.seen.add(identity)
    return DraftClaim(
        claim_id=f"CL{state.counter}",
        text=" ".join(claim.text.split()),
        claim_type=claim.claim_type,
        support_kind=support_kind,
        page_refs=claim.page_refs,
        source_refs=claim.source_refs,
    ), None


def _finalize_blocks(
    specification: ContentDraftSpecification,
    evidence: _DraftEvidence,
    state: _ClaimState,
) -> tuple[tuple[DraftBlock, ...] | None, str | None, int]:
    if specification.draft_type is not ContentDraftType.SECTION_DRAFT:
        return (), None, 0
    if not specification.blocks or len(specification.blocks) > MAX_BLOCKS_PER_DRAFT:
        return None, ContentDraftValidationCategory.BLOCK_BUDGET.value, 0
    if sum(1 for block in specification.blocks if block.kind is DraftBlockKind.PARAGRAPH) > MAX_PARAGRAPHS_PER_DRAFT:
        return None, ContentDraftValidationCategory.BLOCK_BUDGET.value, 0
    finalized: list[DraftBlock] = []
    added = 0
    for block in specification.blocks:
        if block.kind is DraftBlockKind.PARAGRAPH:
            claims: list[DraftClaim] = []
            if not block.claims or len(block.claims) > MAX_CLAIMS_PER_BLOCK:
                return None, ContentDraftValidationCategory.CLAIM_BUDGET.value, 0
            for claim in block.claims:
                finalized_claim, error = _finalize_claim(state, claim, evidence)
                if error is not None:
                    return None, error, 0
                assert finalized_claim is not None
                added += 1
                claims.append(finalized_claim)
            finalized.append(ParagraphBlock(DraftBlockKind.PARAGRAPH, tuple(claims)))
        elif block.kind is DraftBlockKind.BULLET_LIST:
            if not block.items or len(block.items) > MAX_BULLET_ITEMS:
                return None, ContentDraftValidationCategory.BLOCK_BUDGET.value, 0
            items: list[DraftClaim] = []
            for claim in block.items:
                if len(claim.text) > MAX_BULLET_ITEM_CHARS:
                    return None, ContentDraftValidationCategory.CLAIM_BUDGET.value, 0
                finalized_claim, error = _finalize_claim(state, claim, evidence)
                if error is not None:
                    return None, error, 0
                assert finalized_claim is not None
                added += 1
                items.append(finalized_claim)
            finalized.append(BulletListBlock(DraftBlockKind.BULLET_LIST, tuple(items)))
        else:
            return None, ContentDraftValidationCategory.FIELD_CONTRACT.value, 0
    return tuple(finalized), None, added


def _finalize_table(
    specification: ContentDraftSpecification,
    operation: ChangeOperation,
    evidence: _DraftEvidence,
    state: _ClaimState,
) -> tuple[DraftBlock | None, str | None]:
    if specification.draft_type is not ContentDraftType.COMPARISON_TABLE_DRAFT:
        return None, None
    if operation.comparison_table_spec is None:
        return None, ContentDraftValidationCategory.TABLE_SCHEMA_MISMATCH.value
    expected_columns = tuple(operation.comparison_table_spec.column_headers)
    expected_rows = tuple(operation.comparison_table_spec.row_dimensions)
    if len(specification.cells) > MAX_TABLE_ROWS * MAX_TABLE_COLUMNS:
        return None, ContentDraftValidationCategory.BLOCK_BUDGET.value
    columns = tuple(dict.fromkeys(cell.column for cell in specification.cells))
    rows = tuple(dict.fromkeys(cell.row_dimension for cell in specification.cells))
    if columns != expected_columns or rows != expected_rows:
        return None, ContentDraftValidationCategory.TABLE_SCHEMA_MISMATCH.value
    cells: list[TableCell] = []
    for cell in specification.cells:
        if len(cell.text) > MAX_TABLE_CELL_CHARS:
            return None, ContentDraftValidationCategory.CLAIM_BUDGET.value
        if any(ref not in evidence.allowed_pages for ref in cell.page_refs):
            return None, ContentDraftValidationCategory.EVIDENCE_OUTSIDE_CHANGE_SCOPE.value
        if any(ref not in evidence.allowed_sources for ref in cell.source_refs):
            return None, ContentDraftValidationCategory.EVIDENCE_OUTSIDE_CHANGE_SCOPE.value
        if any(ref not in evidence.page_ids for ref in cell.page_refs):
            return None, ContentDraftValidationCategory.UNKNOWN_PAGE_REFERENCE.value
        if any(ref not in evidence.source_ids for ref in cell.source_refs):
            return None, ContentDraftValidationCategory.UNKNOWN_SOURCE_REFERENCE.value
        is_first_party_cell = (
            _has_first_party_expression(cell.text)
            or _contains_first_party_entity(cell.text, evidence.first_party_entities)
            or bool(cell.page_refs)
        )
        if is_first_party_cell:
            if not cell.page_refs:
                return None, ContentDraftValidationCategory.FIRST_PARTY_FACT_WITHOUT_PAGE.value
            combined = "\n".join(
                evidence.page_text_by_id[ref] for ref in cell.page_refs
            )
            numeric_error = _validate_numeric_grounding(cell.text, combined)
            if numeric_error is not None:
                return None, numeric_error
        if _has_promotional_term(cell.text):
            return None, ContentDraftValidationCategory.UNSUPPORTED_PROMOTIONAL_CLAIM.value
        if _has_absence_term(cell.text):
            return None, ContentDraftValidationCategory.UNSUPPORTED_ABSENCE_CLAIM.value
        identity = _factual_identity(cell.text, cell.page_refs, cell.source_refs)
        if identity in state.seen:
            return None, ContentDraftValidationCategory.DUPLICATE_CLAIM.value
        state.seen.add(identity)
        cells.append(
            TableCell(
                row_dimension=cell.row_dimension,
                column=cell.column,
                text=" ".join(cell.text.split()),
                page_refs=cell.page_refs,
                source_refs=cell.source_refs,
            )
        )
    return ComparisonTableBlock(DraftBlockKind.COMPARISON_TABLE, tuple(cells)), None


def _finalize_internal_link(
    specification: ContentDraftSpecification,
    operation: ChangeOperation,
    site_content: SiteContentPacket,
    evidence: _DraftEvidence,
    state: _ClaimState,
) -> tuple[DraftBlock | None, str | None]:
    if specification.draft_type is not ContentDraftType.INTERNAL_LINK_DRAFT:
        return None, None
    if operation.internal_link_spec is None:
        return None, ContentDraftValidationCategory.INTERNAL_LINK_INVALID.value
    anchor_text = specification.anchor_text
    if type(anchor_text) is not str or not anchor_text.strip():
        return None, ContentDraftValidationCategory.FIELD_CONTRACT.value
    anchor = " ".join(anchor_text.split())
    if len(anchor) > MAX_ANCHOR_TEXT_CHARS:
        return None, ContentDraftValidationCategory.CLAIM_BUDGET.value
    target_page_ref = operation.internal_link_spec.target_page_ref
    target_page = next(
        (page for page in site_content.pages if page.evidence_id == target_page_ref),
        None,
    )
    if target_page is None:
        return None, ContentDraftValidationCategory.UNKNOWN_PAGE_REFERENCE.value
    target_text = evidence.page_text_by_id[target_page_ref]
    anchor_norm = _normalized_text(anchor)
    if _has_first_party_expression(anchor) or _contains_first_party_entity(
        anchor_norm, evidence.first_party_entities
    ):
        anchor_error = _validate_numeric_grounding(anchor, target_text)
        if anchor_error is not None:
            return None, anchor_error
    claims: list[DraftClaim] = []
    for claim in specification.insertion_claims:
        finalized_claim, error = _finalize_claim(state, claim, evidence)
        if error is not None:
            return None, error
        assert finalized_claim is not None
        claims.append(finalized_claim)
    return (
        InternalLinkBlock(
            DraftBlockKind.INTERNAL_LINK,
            anchor,
            target_page_ref,
            target_page.final_url,
            tuple(claims),
        ),
        None,
    )


def finalize_draft_item(
    number: int,
    specification: ContentDraftSpecification,
    operation: ChangeOperation,
    opportunity: ContentOpportunity,
    site_content: SiteContentPacket,
    opportunity_report: ContentOpportunityReport,
) -> tuple[DraftItem | None, str | None]:
    expected_type = content_draft_type_for(operation.operation_type)
    if specification.draft_type is not expected_type:
        return None, ContentDraftValidationCategory.FIELD_CONTRACT.value
    if specification.change_ref != operation.change_id:
        return None, ContentDraftValidationCategory.UNKNOWN_CHANGE_REFERENCE.value

    evidence = _build_evidence_context(operation, site_content, opportunity_report)
    state = _ClaimState()

    heading: str | None = None
    ordered_headings: tuple[str, ...] = ()
    blocks: tuple[DraftBlock, ...] = ()

    if expected_type is ContentDraftType.STRUCTURE_ONLY:
        ordered_headings = operation.ordered_headings
    elif expected_type is ContentDraftType.SECTION_DRAFT:
        finalized_blocks, error, used = _finalize_blocks(specification, evidence, state)
        if error is not None:
            return None, error
        assert finalized_blocks is not None
        if used > MAX_CLAIMS_PER_DRAFT:
            return None, ContentDraftValidationCategory.CLAIM_BUDGET.value
        blocks = finalized_blocks
        if operation.operation_type is ChangeOperationType.ADD_SECTION:
            heading = operation.proposed_heading
    elif expected_type is ContentDraftType.COMPARISON_TABLE_DRAFT:
        table_block, error = _finalize_table(specification, operation, evidence, state)
        if error is not None:
            return None, error
        assert table_block is not None
        blocks = (table_block,)
    elif expected_type is ContentDraftType.INTERNAL_LINK_DRAFT:
        link_block, error = _finalize_internal_link(
            specification, operation, site_content, evidence, state
        )
        if error is not None:
            return None, error
        assert link_block is not None
        if state.counter > MAX_CLAIMS_PER_DRAFT:
            return None, ContentDraftValidationCategory.CLAIM_BUDGET.value
        blocks = (link_block,)
    else:  # NEW_RESOURCE_DRAFT
        if operation.new_resource_spec is None:
            return None, ContentDraftValidationCategory.NEW_RESOURCE_INVALID.value
        heading = operation.new_resource_spec.proposed_title
        expected_outline = operation.new_resource_spec.outline_headings
        provided_outline = tuple(section.outline_heading for section in specification.sections)
        if provided_outline != expected_outline:
            return None, ContentDraftValidationCategory.NEW_RESOURCE_INVALID.value
        resource_blocks: list[DraftBlock] = []
        total_claims = 0
        for section in specification.sections:
            section_spec = ContentDraftSpecification(
                change_ref=specification.change_ref,
                draft_type=ContentDraftType.SECTION_DRAFT,
                blocks=section.blocks,
            )
            section_blocks, error, used = _finalize_blocks(section_spec, evidence, state)
            if error is not None:
                return None, error
            assert section_blocks is not None
            total_claims += used
            resource_blocks.extend(section_blocks)
        if len(resource_blocks) > MAX_BLOCKS_PER_DRAFT:
            return None, ContentDraftValidationCategory.BLOCK_BUDGET.value
        if total_claims > MAX_CLAIMS_PER_DRAFT:
            return None, ContentDraftValidationCategory.CLAIM_BUDGET.value
        blocks = tuple(resource_blocks)

    target_page_ref = (
        operation.locator.page_ref
        if operation.locator.locator_kind is not SectionLocatorKind.NEW_PAGE
        else None
    )
    return (
        DraftItem(
            draft_id=f"D{number}",
            change_ref=operation.change_id,
            opportunity_ref=operation.opportunity_ref,
            draft_type=expected_type,
            target_kind=operation.target_kind,
            target_page_ref=target_page_ref,
            locator=operation.locator,
            heading=heading,
            ordered_headings=ordered_headings,
            blocks=blocks,
            page_refs=operation.page_refs,
            source_refs=operation.source_refs,
            requires_human_review=True,
        ),
        None,
    )
