"""Evidence-grounded content draft models, budgets, and deterministic finalization."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import json
import math
import re
from types import MappingProxyType
from typing import Callable
import unicodedata

from .change_plan import (
    CHANGE_PLAN_LIMITATIONS,
    ContentPoint,
    ChangeOperation,
    ChangeOperationType,
    ChangePlanReport,
    comparison_operation_error,
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
from .first_party_planning import FirstPartyPlanningScope
from .draft_customer_evidence import DraftCustomerEvidence, InterpretationProposal, MAX_INTERPRETATION_CHARS


# --- Budgets -------------------------------------------------------------
MAX_DRAFTS = 8
MAX_PROVIDER_CALLS = 8
MAX_BLOCKS_PER_DRAFT = 24
MAX_CLAIMS_PER_BLOCK = 4
MAX_CLAIMS_PER_DRAFT = 48
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
MAX_RAW_OUTPUT_CHARS = 64_000
MAX_RAW_OUTPUT_BYTES = 128 * 1024
MAX_SYSTEM_PROMPT_CHARS = 8_000
MAX_SYSTEM_PROMPT_BYTES = 16 * 1024
# Reviewed full-article interpretations must survive native replay losslessly.
MAX_USER_MATERIAL_CHARS = 52_000
MAX_USER_MATERIAL_BYTES = 112 * 1024
MAX_INPUT_ENVELOPE_CHARS = 64_000
MAX_INPUT_ENVELOPE_BYTES = 144 * 1024
MAX_PROVIDER_TOKENS = 16_384
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
    CANDIDATE_TEXT_NOT_CANONICAL = "CANDIDATE_TEXT_NOT_CANONICAL"
    INTERPRETATION_PENDING_REVIEW = "INTERPRETATION_PENDING_REVIEW"
    ARTICLE_QUALITY_GAP = 'ARTICLE_QUALITY_GAP'
    INTAKE_EXECUTION_BLOCKED = "INTAKE_EXECUTION_BLOCKED"
    CUSTOMER_EVIDENCE_INVALID = "CUSTOMER_EVIDENCE_INVALID"
    UNKNOWN_CUSTOMER_REFERENCE = "UNKNOWN_CUSTOMER_REFERENCE"
    CUSTOMER_QUOTE_MISMATCH = "CUSTOMER_QUOTE_MISMATCH"
    CUSTOMER_EVIDENCE_COVERAGE = "CUSTOMER_EVIDENCE_COVERAGE"
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
    NUMERIC_CONTEXT_NOT_PRESERVED = "NUMERIC_CONTEXT_NOT_PRESERVED"
    NUMERIC_NOT_GROUNDED = "NUMERIC_NOT_GROUNDED"
    UNSUPPORTED_PROMOTIONAL_CLAIM = "UNSUPPORTED_PROMOTIONAL_CLAIM"
    UNSUPPORTED_ABSENCE_CLAIM = "UNSUPPORTED_ABSENCE_CLAIM"
    COMPETITOR_MENTION = "COMPETITOR_MENTION"
    HEADING_MISMATCH = "HEADING_MISMATCH"
    TABLE_SCHEMA_MISMATCH = "TABLE_SCHEMA_MISMATCH"
    COMPARISON_UNAVAILABLE = "COMPARISON_UNAVAILABLE"
    INTERNAL_LINK_INVALID = "INTERNAL_LINK_INVALID"
    NEW_RESOURCE_INVALID = "NEW_RESOURCE_INVALID"
    BLOCK_BUDGET = "BLOCK_BUDGET"
    CLAIM_BUDGET = "CLAIM_BUDGET"
    DUPLICATE_CLAIM = "DUPLICATE_CLAIM"
    DUPLICATE_DRAFT = "DUPLICATE_DRAFT"


CONTENT_DRAFT_REPAIR_CATEGORIES = frozenset(
    {
        ContentDraftValidationCategory.CLAIM_BUDGET,
        ContentDraftValidationCategory.NUMERIC_NOT_GROUNDED,
        ContentDraftValidationCategory.UNKNOWN_CHANGE_REFERENCE,
    }
)

_CONTENT_DRAFT_REPAIR_ACTIONS = MappingProxyType(
    {
        ContentDraftValidationCategory.CLAIM_BUDGET: (
            "Regenerate the complete response within the declared draft "
            f"budgets. Use no more than {MAX_BLOCKS_PER_DRAFT} blocks and {MAX_CLAIMS_PER_DRAFT} claims or items "
            f"total, with no more than {MAX_CLAIMS_PER_BLOCK} claims per paragraph and {MAX_BULLET_ITEMS} items "
            "per bullet list."
        ),
        ContentDraftValidationCategory.NUMERIC_NOT_GROUNDED: (
            "Regenerate the complete response under the system NUMERIC RULE. "
            "Never emit a bare number. Replace unsafe numeric claims or cell "
            "text with accurate, conservative non-numeric wording supported "
            "by current evidence; do not invent replacement facts. Preserve "
            "required table cells, cell_ref coordinates, schema, and row/column "
            "coverage."
        ),
        ContentDraftValidationCategory.UNKNOWN_CHANGE_REFERENCE: (
            "Regenerate the complete response for exactly the supplied change. "
            "Set draft.change_ref to the supplied change_ref verbatim and do not "
            "use any other C identifier."
        ),
    }
)


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
    EVIDENCE_BASED_INTERPRETATION = "EVIDENCE_BASED_INTERPRETATION"
    GENERAL_TECHNICAL_CONTEXT = "GENERAL_TECHNICAL_CONTEXT"
    COMPARATIVE_CONTEXT = "COMPARATIVE_CONTEXT"
    EDITORIAL_TRANSITION = "EDITORIAL_TRANSITION"
    CALL_TO_ACTION = "CALL_TO_ACTION"


class DraftClaimSupportKind(str, Enum):
    FIRST_PARTY_OBSERVED = "FIRST_PARTY_OBSERVED"
    CUSTOMER_REVIEWED_QUOTE = "CUSTOMER_REVIEWED_QUOTE"
    CUSTOMER_REVIEWED_INTERPRETATION = "CUSTOMER_REVIEWED_INTERPRETATION"
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
        DraftClaimType.EVIDENCE_BASED_INTERPRETATION,
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
class ArticleWritingBrief:
    """Bounded writing intent, never evidence or an execution credential."""
    snapshot_sha256: str
    goal: str
    search_intent: str
    instructions: tuple[str, ...]
    article_type: str | None = None
    reader_problem: str | None = None

    def __post_init__(self):
        if any(v is not None and (type(v) is not str or not v.strip() or len(v) > 1000)
               for v in (self.article_type, self.reader_problem)):
            raise ValueError('ARTICLE_BRIEF_INVALID')
        if any(v is not None and any(ord(c) < 32 and c not in '\n\r\t' for c in v)
               for v in (self.article_type, self.reader_problem)):
            raise ValueError('ARTICLE_BRIEF_INVALID')
        if (type(self.snapshot_sha256) is not str or len(self.snapshot_sha256) != 64
                or any(c not in '0123456789abcdef' for c in self.snapshot_sha256)
                or any(type(v) is not str or not v.strip() or len(v) > 1000
                       or any(ord(c) < 32 and c not in '\n\r\t' for c in v)
                       for v in (self.goal, self.search_intent))
                or type(self.instructions) is not tuple or not 1 <= len(self.instructions) <= 8
                or any(type(v) is not str or not v.strip() or len(v) > 1000
                       or any(ord(c) < 32 and c not in '\n\r\t' for c in v) for v in self.instructions)):
            raise ValueError('ARTICLE_BRIEF_INVALID')


@dataclass(frozen=True, slots=True)
class ContentDraftInput:
    site_content: SiteContentPacket
    opportunity_report: ContentOpportunityReport
    change_plan_report: ChangePlanReport
    target_language: str = "en"
    customer_evidence: DraftCustomerEvidence | None = None
    writing_brief: ArticleWritingBrief | None = None
    propose_interpretations: bool = False

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


def stable_content_draft_input_error(
    value: ContentDraftInput, *, first_party_scope: FirstPartyPlanningScope | None = None,
    task_id: str | None = None,
) -> str | None:
    """Reuse upstream stable validation rather than re-implementing C# rules."""

    if not isinstance(value, ContentDraftInput):
        return 'FIELD_CONTRACT'
    if type(value.propose_interpretations) is not bool or (value.propose_interpretations and value.customer_evidence is None):
        return 'FIELD_CONTRACT'
    if value.writing_brief is not None:
        if (type(value.writing_brief) is not ArticleWritingBrief or value.customer_evidence is None
                or value.writing_brief.snapshot_sha256 != value.customer_evidence.snapshot_sha256):
            return 'CUSTOMER_EVIDENCE_INVALID'

    try:
        change_input = ChangePlanInput(value.site_content, value.opportunity_report, first_party_scope, task_id)
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

    if value.customer_evidence is not None:
        bundle = value.customer_evidence
        if (type(bundle) is not DraftCustomerEvidence or len(report.operations) != 1
            or not bundle.matches_native(value.site_content, value.opportunity_report, report.operations[0])):
            return ContentDraftValidationCategory.CUSTOMER_EVIDENCE_INVALID.value

    page_ids = {page.evidence_id for page in value.site_content.pages}
    source_ids = {material.source_id for material in value.opportunity_report.source_materials}
    opportunity_by_id = {
        item.recommendation_id: item for item in value.opportunity_report.opportunities
    }
    for operation in report.operations:
        if not isinstance(operation, ChangeOperation):
            return ContentDraftValidationCategory.FIELD_CONTRACT.value
        capability_error = comparison_operation_error(operation)
        if capability_error is not None:
            return capability_error
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
        if operation.audit_refs != opportunity.audit_refs:
            return ContentDraftValidationCategory.EVIDENCE_OUTSIDE_CHANGE_SCOPE.value
    return None


# --- Specification models (provider output) ------------------------------


@dataclass(frozen=True, slots=True)
class DraftClaimSpecification:
    text: str
    claim_type: DraftClaimType
    page_refs: tuple[str, ...] = ()
    source_refs: tuple[str, ...] = ()
    customer_refs: tuple[str, ...] = ()
    proposal: InterpretationProposal | None = None


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


@dataclass(frozen=True, slots=True)
class CompetitorMentionViolation:
    """Text-free transient location of an existing heuristic rejection.

    The stable index refers to the title-case match within the rejected field;
    it does not imply that an authoritative competitor catalog exists.
    """

    change_ref: str
    operation_type: ChangeOperationType
    draft_item_index: int
    section_index: int | None
    field_path: str
    match_kind: str
    competitor_index: int
    mention_count: int
    source_origin: str

    def __post_init__(self) -> None:
        if (
            type(self.change_ref) is not str
            or re.fullmatch(r"C[1-9][0-9]{0,2}", self.change_ref) is None
            or not isinstance(self.operation_type, ChangeOperationType)
            or type(self.draft_item_index) is not int
            or not 0 <= self.draft_item_index < MAX_DRAFTS
            or self.section_index is not None
            and (type(self.section_index) is not int or not 0 <= self.section_index < MAX_BLOCKS_PER_DRAFT)
            or type(self.field_path) is not str
            or re.fullmatch(
                r"draft\.(?:(?:sections\[[0-7]\]\.)?blocks\[[0-7]\]\."
                r"(?:claims\[[0-3]\]|items\[[0-5]\])|insertion_claims\[[0-9]{1,5}\])\.text",
                self.field_path,
            ) is None
            or self.match_kind != "TITLE_CASE_HEURISTIC"
            or type(self.competitor_index) is not int
            or not 0 <= self.competitor_index <= MAX_CLAIM_CHARS
            or type(self.mention_count) is not int
            or not 1 <= self.mention_count <= MAX_CLAIM_CHARS
            or self.source_origin not in {
                "SITE_CONTENT", "INDUSTRY_RESEARCH", "CHANGE_PLAN", "CONTENT_OPPORTUNITY",
                "DRAFT_INSTRUCTION", "MODEL_HALLUCINATION", "MULTIPLE", "UNKNOWN",
            }
        ):
            raise ValueError("Competitor mention diagnostic is invalid.")


@dataclass(frozen=True, slots=True)
class ClaimTypeViolation:
    """Text-free, process-local location of a rejected editorial/CTA claim."""

    change_ref: str
    operation_type: ChangeOperationType
    draft_item_index: int
    field_path: str
    rule_id: str
    actual_claim_type: DraftClaimType
    expected_claim_types: tuple[DraftClaimType, ...]
    prior_category: ContentDraftValidationCategory | None
    has_page_refs: bool
    has_source_refs: bool
    has_numeric_expression: bool
    has_first_party_expression: bool
    has_promotional_term: bool

    def __post_init__(self) -> None:
        if (
            re.fullmatch(r"C[1-9][0-9]{0,2}", self.change_ref) is None
            or not isinstance(self.operation_type, ChangeOperationType)
            or type(self.draft_item_index) is not int
            or not 0 <= self.draft_item_index < MAX_DRAFTS
            or re.fullmatch(
                r"draft\.(?:(?:sections\[[0-7]\]\.)?blocks\[[0-7]\]\."
                r"(?:claims\[[0-3]\]|items\[[0-5]\])|insertion_claims\[[0-9]{1,5}\])\.claim_type",
                self.field_path,
            ) is None
            or self.rule_id not in {"EDITORIAL_CTA_WITH_REFS", "EDITORIAL_CTA_FACTUAL_CONTENT"}
            or self.actual_claim_type not in {
                DraftClaimType.EDITORIAL_TRANSITION, DraftClaimType.CALL_TO_ACTION,
            }
            or self.expected_claim_types != ()
            or self.prior_category is not None
            and self.prior_category not in CONTENT_DRAFT_REPAIR_CATEGORIES
            or any(type(value) is not bool for value in (
                self.has_page_refs, self.has_source_refs, self.has_numeric_expression,
                self.has_first_party_expression, self.has_promotional_term,
            ))
        ):
            raise ValueError("Claim type diagnostic is invalid.")


@dataclass(frozen=True, slots=True)
class NumericGroundingViolation:
    """Text-free process-local metadata for one rejected numeric occurrence."""

    change_ref: str
    operation_type: ChangeOperationType
    draft_item_index: int
    field_path: str
    numeric_kind: str
    numeric_occurrence_index: int
    numeric_literal_count: int
    grounded_count: int
    ungrounded_count: int
    cited_ref_ids: tuple[str, ...]
    grounding_mode: str
    source_namespace: str
    rule_id: str
    bare_number_count: int
    evidence_mismatch_count: int
    has_source_refs: bool
    attempt: int = 1
    table_row_index: int | None = None
    table_column_index: int | None = None

    def __post_init__(self) -> None:
        if (
            type(self.change_ref) is not str
            or re.fullmatch(r"C[1-9][0-9]{0,2}", self.change_ref) is None
            or not isinstance(self.operation_type, ChangeOperationType)
            or type(self.draft_item_index) is not int
            or not 0 <= self.draft_item_index < MAX_DRAFTS
            or type(self.field_path) is not str
            or re.fullmatch(
                r"draft\.(?:(?:sections\[[0-9]{1,5}\]\.)?blocks\[[0-7]\]\."
                r"(?:claims\[[0-3]\]|items\[[0-5]\])\.text|"
                r"cells\[[0-9]{1,2}\]\.text|anchor_text|insertion_claims\[[0-9]{1,5}\]\.text)",
                self.field_path,
            ) is None
            or self.numeric_kind not in {
                "BARE_INTEGER", "BARE_DECIMAL", "BARE_NUMBER", "PERCENTAGE",
                "RANGE", "CURRENCY", "NUMBER_WITH_UNIT", "OTHER_EXPRESSION",
            }
            or any(type(count) is not int or not 0 <= count <= MAX_RAW_OUTPUT_CHARS
                   for count in (self.numeric_occurrence_index, self.numeric_literal_count,
                                 self.grounded_count, self.ungrounded_count,
                                 self.bare_number_count, self.evidence_mismatch_count))
            or not self.numeric_occurrence_index < self.numeric_literal_count
            or not self.ungrounded_count
            or self.grounded_count + self.ungrounded_count != self.numeric_literal_count
            or self.bare_number_count + self.evidence_mismatch_count != self.ungrounded_count
            or self.rule_id not in {
                "BARE_NUMBER_FORBIDDEN", "NUMERIC_EXPRESSION_NOT_IN_CITED_PAGE",
                "NUMERIC_EXPRESSION_NOT_IN_CITED_FIRST_PARTY",
            }
            or self.is_bare_number != self.numeric_kind.startswith("BARE_")
            or self.is_bare_number and not self.bare_number_count
            or self.evidence_match_failed and not self.evidence_mismatch_count
            or type(self.has_source_refs) is not bool
            or type(self.attempt) is not int or self.attempt not in {1, 2}
            or type(self.cited_ref_ids) is not tuple
            or not self.cited_ref_ids
            or len(self.cited_ref_ids) > MAX_RAW_OUTPUT_CHARS
            or any(type(ref) is not str or re.fullmatch(r"(?:P[1-9][0-9]{0,2}|E[1-9][0-9]{0,2}(?:\.F[0-9]{2})?)", ref) is None
                   for ref in self.cited_ref_ids)
            or self.grounding_mode != "NORMALIZED_EXACT_NON_BARE"
            or self.source_namespace not in {"PAGE_EVIDENCE", "TARGET_PAGE_EVIDENCE", "CUSTOMER_EVIDENCE", "MIXED_FIRST_PARTY_EVIDENCE"}
            or (self.table_row_index is None) != (self.table_column_index is None)
            or self.field_path.startswith("draft.cells[") != (self.table_row_index is not None)
            or self.table_row_index is not None
            and (type(self.table_row_index) is not int or not 0 <= self.table_row_index < MAX_TABLE_ROWS
                 or type(self.table_column_index) is not int
                 or not 0 <= self.table_column_index < MAX_TABLE_COLUMNS)
        ):
            raise ValueError("Numeric grounding diagnostic is invalid.")

    @property
    def has_page_refs(self) -> bool:
        return any(ref.startswith("P") for ref in self.cited_ref_ids)

    @property
    def is_bare_number(self) -> bool:
        return self.rule_id == "BARE_NUMBER_FORBIDDEN"

    @property
    def evidence_match_failed(self) -> bool:
        """Whether the first rejection reached and failed the evidence check."""

        return self.rule_id in {"NUMERIC_EXPRESSION_NOT_IN_CITED_PAGE", "NUMERIC_EXPRESSION_NOT_IN_CITED_FIRST_PARTY"}


# --- Final models --------------------------------------------------------


class DraftBlockBudgetRule(str, Enum):
    BLOCK_COUNT = "BLOCK_COUNT"
    PARAGRAPH_COUNT = "PARAGRAPH_COUNT"
    BULLET_ITEM_COUNT = "BULLET_ITEM_COUNT"
    TABLE_CELL_COUNT = "TABLE_CELL_COUNT"
    RESOURCE_TOTAL_BLOCK_COUNT = "RESOURCE_TOTAL_BLOCK_COUNT"


@dataclass(frozen=True, slots=True)
class DraftBlockBudgetViolation:
    """Process-local structural counts; never carries generated or evidence text."""

    change_ref: str
    operation_type: ChangeOperationType
    field_path: str
    rule_id: DraftBlockBudgetRule
    expected_min: int
    expected_max: int
    actual_count: int
    paragraph_count: int
    bullet_list_count: int

    def __post_init__(self) -> None:
        if (
            type(self.change_ref) is not str
            or re.fullmatch(r"C[1-9][0-9]{0,2}", self.change_ref) is None
            or not isinstance(self.operation_type, ChangeOperationType)
            or not isinstance(self.rule_id, DraftBlockBudgetRule)
            or type(self.field_path) is not str
            or re.fullmatch(
                r"draft\.(?:cells|sections\[\*\]\.blocks|"
                r"(?:sections\[[0-5]\]\.)?blocks(?:\[[0-7]\]\.items)?)",
                self.field_path,
            ) is None
            or any(type(count) is not int or not 0 <= count <= MAX_RAW_OUTPUT_CHARS
                   for count in (self.expected_min, self.expected_max, self.actual_count,
                                 self.paragraph_count, self.bullet_list_count))
            or self.expected_min > self.expected_max
            or self.expected_min <= self.actual_count <= self.expected_max
        ):
            raise ValueError("Draft block budget diagnostic is invalid.")


def describe_draft_block_budget_violation(
    specification: ContentDraftSpecification,
    operation: ChangeOperation,
) -> DraftBlockBudgetViolation | None:
    """Locate a structural rejection after final validation selected BLOCK_BUDGET.

    Mirrors only the existing structural checks, in their existing order. The
    caller must gate this observer on the final category; it does not validate
    claims, authorize refs, or replace the complete validator.
    """

    def descriptor(path, rule, minimum, maximum, actual, blocks=()):
        return DraftBlockBudgetViolation(
            operation.change_id, operation.operation_type, path, rule,
            minimum, maximum, actual,
            sum(block.kind is DraftBlockKind.PARAGRAPH for block in blocks),
            sum(block.kind is DraftBlockKind.BULLET_LIST for block in blocks),
        )

    def section_violation(blocks, prefix):
        if not blocks or len(blocks) > MAX_BLOCKS_PER_DRAFT:
            return descriptor(prefix, DraftBlockBudgetRule.BLOCK_COUNT,
                              1, MAX_BLOCKS_PER_DRAFT, len(blocks), blocks)
        paragraphs = sum(block.kind is DraftBlockKind.PARAGRAPH for block in blocks)
        if paragraphs > MAX_PARAGRAPHS_PER_DRAFT:
            return descriptor(prefix, DraftBlockBudgetRule.PARAGRAPH_COUNT,
                              0, MAX_PARAGRAPHS_PER_DRAFT, paragraphs, blocks)
        for index, block in enumerate(blocks):
            if block.kind is DraftBlockKind.BULLET_LIST and (
                not block.items or len(block.items) > MAX_BULLET_ITEMS
            ):
                return descriptor(f"{prefix}[{index}].items", DraftBlockBudgetRule.BULLET_ITEM_COUNT,
                                  1, MAX_BULLET_ITEMS, len(block.items), blocks)
        return None

    if specification.draft_type is ContentDraftType.SECTION_DRAFT:
        return section_violation(specification.blocks, "draft.blocks")
    if specification.draft_type is ContentDraftType.COMPARISON_TABLE_DRAFT:
        if len(specification.cells) > MAX_TABLE_ROWS * MAX_TABLE_COLUMNS:
            return descriptor("draft.cells", DraftBlockBudgetRule.TABLE_CELL_COUNT,
                              0, MAX_TABLE_ROWS * MAX_TABLE_COLUMNS, len(specification.cells))
    if specification.draft_type is ContentDraftType.NEW_RESOURCE_DRAFT:
        for index, section in enumerate(specification.sections):
            violation = section_violation(section.blocks, f"draft.sections[{index}].blocks")
            if violation is not None:
                return violation
        blocks = tuple(block for section in specification.sections for block in section.blocks)
        if len(blocks) > MAX_BLOCKS_PER_DRAFT:
            return descriptor("draft.sections[*].blocks", DraftBlockBudgetRule.RESOURCE_TOTAL_BLOCK_COUNT,
                              0, MAX_BLOCKS_PER_DRAFT, len(blocks), blocks)
    return None


@dataclass(frozen=True, slots=True)
class DraftClaim:
    claim_id: str
    text: str
    claim_type: DraftClaimType
    support_kind: DraftClaimSupportKind | None
    page_refs: tuple[str, ...]
    source_refs: tuple[str, ...]
    customer_refs: tuple[str, ...] = ()
    proposal: InterpretationProposal | None = None


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
    # Empty for historical artifacts whose section boundaries were not saved.
    section_block_counts: tuple[int, ...] = ()
    customer_evidence: DraftCustomerEvidence | None = None

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
        claims = tuple(claim for block in self.blocks for claim in
            (block.claims if isinstance(block, ParagraphBlock) else
             block.items if isinstance(block, BulletListBlock) else
             block.insertion_claims if isinstance(block, InternalLinkBlock) else ()))
        e_claims = tuple(c for c in claims if c.customer_refs)
        if self.customer_evidence is None:
            if e_claims:
                raise ValueError("Customer draft binding is missing.")
        else:
            bundle = self.customer_evidence
            if (type(bundle) is not DraftCustomerEvidence
                or self.draft_type is not ContentDraftType.NEW_RESOURCE_DRAFT
                or self.change_ref != bundle.change_ref):
                raise ValueError("Customer draft binding is invalid.")
            if (not bundle.reference_selection_valid(r for c in e_claims for r in c.customer_refs)
                or any(bundle.claim_error(c.text, c.claim_type.value, c.customer_refs, c.page_refs, c.source_refs, c.proposal)
                       or c.support_kind is not (DraftClaimSupportKind.CUSTOMER_REVIEWED_INTERPRETATION
                           if c.claim_type is DraftClaimType.EVIDENCE_BASED_INTERPRETATION else DraftClaimSupportKind.CUSTOMER_REVIEWED_QUOTE)
                       for c in e_claims)):
                raise ValueError("Customer draft quotations are invalid.")
        if (type(self.section_block_counts) is not tuple
            or self.section_block_counts and (
                self.draft_type is not ContentDraftType.NEW_RESOURCE_DRAFT
                or len(self.section_block_counts) != len(self.ordered_headings)
                or any(type(n) is not int or not 1 <= n <= MAX_BLOCKS_PER_DRAFT
                       for n in self.section_block_counts)
                or sum(self.section_block_counts) != len(self.blocks)
                or len(self.blocks) > MAX_BLOCKS_PER_DRAFT)):
            raise ValueError("Draft section boundaries are invalid.")


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


def content_draft_block_budget_contract(operation_type: ChangeOperationType) -> dict[str, object]:
    """Project the existing structural validator limits for one operation.

    This transient generation contract neither mutates the Change Plan nor
    changes which provider outputs the complete validator accepts.
    """

    if operation_type in {ChangeOperationType.EXPAND_SECTION, ChangeOperationType.ADD_SECTION}:
        return {
            "blocks": {"min": 1, "max": MAX_BLOCKS_PER_DRAFT},
            "paragraph_blocks": {"min": 0, "max": MAX_PARAGRAPHS_PER_DRAFT},
            "items_per_bullet_list": {"min": 1, "max": MAX_BULLET_ITEMS},
        }
    if operation_type is ChangeOperationType.CREATE_NEW_RESOURCE:
        return {
            "blocks_per_section": {"min": 1, "max": MAX_BLOCKS_PER_DRAFT},
            "paragraph_blocks_per_section": {"min": 0, "max": MAX_PARAGRAPHS_PER_DRAFT},
            "items_per_bullet_list": {"min": 1, "max": MAX_BULLET_ITEMS},
            "total_blocks_across_sections": {"max": MAX_BLOCKS_PER_DRAFT},
        }
    if operation_type is ChangeOperationType.ADD_COMPARISON_TABLE:
        return {"cells": {"min": 0, "max": MAX_TABLE_ROWS * MAX_TABLE_COLUMNS}}
    return {}


def table_coordinate_catalog(
    operation: ChangeOperation,
) -> tuple[tuple[str, str, str], ...]:
    """Assign transient, change-scoped refs to approved table coordinates."""

    schema = operation.comparison_table_spec
    if schema is None:
        raise ValueError("Comparison table schema is required.")
    columns = schema.column_headers
    rows = schema.row_dimensions
    if (
        not columns or not rows
        or len(columns) > MAX_TABLE_COLUMNS
        or len(rows) > MAX_TABLE_ROWS
        or len(columns) != len(set(columns))
        or len(rows) != len(set(rows))
        or len(columns) * len(rows) > MAX_TABLE_ROWS * MAX_TABLE_COLUMNS
    ):
        raise ValueError("Comparison table schema exceeds the coordinate contract.")
    return tuple(
        (f"{operation.change_id}_CELL_{number:03d}", row, column)
        for number, (row, column) in enumerate(
            ((row, column) for row in rows for column in columns), start=1
        )
    )


@dataclass(frozen=True, slots=True)
class ContentDraftPrompt:
    input: ContentDraftInput
    change_ref: str
    operation: ChangeOperation
    opportunity: ContentOpportunity
    pages: tuple[SiteContentEvidence, ...]
    sources: tuple[ContentOpportunitySourceMaterial, ...]
    repair_category: ContentDraftValidationCategory | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.input, ContentDraftInput)
            or self.repair_category is not None
            and self.repair_category not in CONTENT_DRAFT_REPAIR_CATEGORIES
        ):
            raise ValueError("Content draft prompt input is invalid.")
        capability_error = comparison_operation_error(self.operation)
        if capability_error is None:
            capability_error = next((
                error for operation in self.input.change_plan_report.operations
                if (error := comparison_operation_error(operation)) is not None
            ), None)
        if capability_error is not None:
            raise ValueError(capability_error)

    def material_json(self) -> str:
        payload = {
            "contract": {
                "evidence_scope": "observed_present_only",
                "supports_absence_claims": False,
                "requires_human_review": True,
                "target_language": self.input.target_language,
                "untrusted_data": True,
                "block_budget": content_draft_block_budget_contract(self.operation.operation_type),
                "retry_feedback": (
                    {
                        "validator": self.repair_category.value,
                        "required_action": _CONTENT_DRAFT_REPAIR_ACTIONS[
                            self.repair_category
                        ],
                    }
                    if self.repair_category is not None
                    else None
                ),
            },
            "change": _operation_payload(
                self.operation,
                pages=self.pages,
                sources=self.sources,
            ),
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
        if self.input.writing_brief is not None:
            from dataclasses import asdict
            payload['writing_brief'] = asdict(self.input.writing_brief)
        if self.input.customer_evidence is not None:
            from dataclasses import asdict
            bundle = self.input.customer_evidence
            payload["customer_evidence"] = {
                "review_status": bundle.review_status,
                "rule": "TEST-only: exact direct facts or explicitly reviewed multi-fact interpretations. Evidence is not a sentence checklist. No self-certification or execution permission.",
                "sources": [{"customer_ref": s.evidence_id, "evidence_version": s.evidence_version,
                    "requirement_ids": s.requirement_ids, "source_locator": s.source_locator,
                    "quote": s.quote, "facts": [{"fact_ref": f.fact_ref, "start": f.start, "end": f.end, "quote": f.quote,
                        "requirement_ids": f.requirement_ids}
                        for f in s.facts]} for s in bundle.sources],
                "interpretations": [dict(text=i.text, fact_refs=i.fact_refs, limitation=i.limitation,
                    procurement_action=i.procurement_action,
                    **({'proposal': asdict(i.proposal)} if i.proposal is not None else {}))
                    for i in bundle.interpretations],
            }
            payload["contract"]["customer_refs"] = tuple(bundle.quote_map())
            payload['contract']['customer_coverage_rule'] = (
                'Select only facts needed to answer the reader questions; the fact bank is not an all-ref quota. '
                'Use exact direct facts or genuine interpretation premises, never irrelevant refs for coverage. '
                'Preserve each section supporting_evidence and requirement_ids coverage.'
                if all(s.facts for s in bundle.sources) else
                'Native coverage requires all customer_refs across exact direct facts or relevant interpretation premises. '
                'Select which facts to display; do not enumerate every quote or attach irrelevant premises. '
                'Preserve section evidence and requirement coverage.')
            # Explicit intake requirement mapping supersedes lexical P/S subject hints for E.
            payload["contract"]["customer_claim_rule"] = "OBSERVED_PRODUCT_FACT: exact fact quote with one ref. EVIDENCE_BASED_INTERPRETATION: exact reviewed interpretation with all its fact_refs. No P/S substitution. Unsupported inference rejected."
            if any(s.facts for s in bundle.sources):
                payload['contract']['page_source_role'] = (
                    'PLANNING_CONTEXT_ONLY: pages, sources and content_points P/S reference/type hints '
                    'describe the planning graph, not E article claim permissions. Use the E contract and section map.')
                # Structured E prose needs its distinct length budget. Legacy
                # short tasks already receive common totals in the system
                # prompt; repeating this metadata can exhaust their 16KB cap.
                payload['contract']['claim_budget'] = {"total": MAX_CLAIMS_PER_DRAFT,
                    "per_paragraph": MAX_CLAIMS_PER_BLOCK, "text_chars": MAX_CLAIM_CHARS,
                    "customer_interpretation_chars": MAX_INTERPRETATION_CHARS}
                payload['contract']['customer_claim_rule'] += ' Structured articles contain only reviewed E facts/interpretations and nonfactual editorial/CTA; P/S remains planning context.'
        if self.input.propose_interpretations:
            payload['contract']['customer_claim_rule'] = (
                'Propose NEW evidence-based analysis; never copy preapproved interpretations. '
                'OBSERVED_PRODUCT_FACT must be an exact quote with one ref. '
                'All claims use text, claim_type, page_refs, source_refs, customer_refs. E refs cannot be replaced by P/S. '
                'EVIDENCE_BASED_INTERPRETATION must add proposal metadata: procurement_question, reasoning, '
                'assumptions, limitation, procurement_action. Python attaches exact premise quotes, conditions and source versions. '
                'Keep limitation and procurement_action verbatim in text; use the section question. '
                'Candidates are PENDING_REVIEW, never delivery eligible. No approval fields. '
                'Preserve subjects, numbers, units, conditions and scope. Editorial/CTA contains no facts.')
            payload['customer_evidence']['interpretations'] = []
            payload['customer_evidence']['rule'] = 'Reviewed facts only. New inferences require independent semantic review.'
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _operation_payload(
    operation: ChangeOperation,
    *,
    pages: tuple[SiteContentEvidence, ...],
    sources: tuple[ContentOpportunitySourceMaterial, ...],
) -> dict[str, object]:
    payload: dict[str, object] = {
        "change_ref": operation.change_id,
        "operation_type": operation.operation_type.value,
        "target_kind": operation.target_kind.value,
        "locator_kind": operation.locator.locator_kind.value,
        "target_page_ref": operation.locator.page_ref,
        "target_heading": operation.locator.observed_heading,
        "content_points": [
            _content_point_payload(point, pages=pages, sources=sources)
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
            "cell_catalog": [
                {"cell_ref": ref, "row_dimension": row, "column": column}
                for ref, row, column in table_coordinate_catalog(operation)
            ],
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
        if operation.new_resource_spec.section_briefs:
            from dataclasses import asdict
            payload['new_resource']['section_briefs'] = [asdict(b) for b in operation.new_resource_spec.section_briefs]
    if operation.ordered_headings:
        payload["ordered_headings"] = operation.ordered_headings
    return payload


def _content_point_payload(
    point: ContentPoint,
    *,
    pages: tuple[SiteContentEvidence, ...],
    sources: tuple[ContentOpportunitySourceMaterial, ...],
) -> dict[str, object]:
    normalized_subject = _normalized_text(point.subject)
    page_refs = tuple(
        page.evidence_id
        for page in pages
        if normalized_subject in _evidence_text(page)
    )
    source_refs = tuple(
        source.source_id
        for source in sources
        if normalized_subject
        in _normalized_text(f"{source.title} {source.content}")
    )
    allowed_claim_types: tuple[str, ...]
    if page_refs and source_refs:
        allowed_claim_types = (
            DraftClaimType.OBSERVED_PRODUCT_FACT.value,
            DraftClaimType.GENERAL_TECHNICAL_CONTEXT.value,
            DraftClaimType.COMPARATIVE_CONTEXT.value,
        )
    elif page_refs:
        allowed_claim_types = (DraftClaimType.OBSERVED_PRODUCT_FACT.value,)
    else:
        allowed_claim_types = (
            DraftClaimType.GENERAL_TECHNICAL_CONTEXT.value,
            DraftClaimType.COMPARATIVE_CONTEXT.value,
        )
    return {
        "intent": point.intent.value,
        "subject": point.subject,
        "observed_in_page_refs": page_refs,
        "observed_in_source_refs": source_refs,
        "allowed_claim_types": allowed_claim_types,
        "required_page_refs": page_refs,
        "required_source_refs": source_refs,
    }


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
    input_error = stable_content_draft_input_error(value)
    if input_error is not None:
        raise ValueError(input_error)
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


_NUMERIC_SPAN_RE = re.compile(
    r"(?<![\w])(?:"
    r"(?P<identifier>[a-z](?=[a-z0-9_-]*\d)[a-z0-9]*(?:[-_][a-z0-9]+)*"
    # Digit-leading compound codes must stay whole too (e.g. alloy/temper).
    # Requiring a letter keeps numeric ranges, fractions and dates on the
    # quantity path; identifiers still undergo exact cited-token grounding.
    r"|\d+(?=[a-z0-9_-]*[a-z])(?:[-_][a-z0-9]+)+)"
    r"|\d[\d.,%°\"'\-/]*)"
)
_NUMERIC_DATE_RE = re.compile(r"\d{4}([-/])\d{2}\1\d{2}")
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
_FIRST_PARTY_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(marker.strip()) for marker in _FIRST_PARTY_MARKERS) + r")\b"
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
    return _FIRST_PARTY_RE.search(folded) is not None


def extract_numeric_expressions(text: str) -> tuple[str, ...]:
    """Return whole identifiers, dates and number+unit expressions for grounding."""

    normalized = _normalized_text(text)
    expressions: list[str] = []
    for match in _NUMERIC_SPAN_RE.finditer(normalized):
        token = match.group(0)
        expression = token.rstrip(".,")
        # Identifier suffixes are not independent quantities. Dates and
        # sentence punctuation end a token; prose after them is not a unit.
        if (match.group("identifier") is not None
            or _NUMERIC_DATE_RE.fullmatch(expression)
            or expression != token):
            expressions.append(expression)
            continue
        tail = _NUMERIC_TAIL_RE.match(normalized, match.end())
        if tail is not None and tail.group(0).strip():
            # Preserve observed adjacency: adding a space to 10bar or 20°C
            # creates a different expression from identical cited evidence.
            expression = normalized[match.start():tail.end()]
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
    if before.isalnum() or before == "_":
        return True
    if before in ".,":
        return index >= 2 and evidence_text[index - 2].isdigit()
    if before in "-/":
        return index >= 2 and evidence_text[index - 2].isalnum()
    return False


def _embedded_in_number_after(evidence_text: str, after_index: int) -> bool:
    """True when the token ends inside a larger numeric/decimal token."""

    length = len(evidence_text)
    if after_index >= length:
        return False
    after = evidence_text[after_index]
    if after.isalnum() or after == "_":
        return True
    if after in ".,":
        return after_index + 1 < length and evidence_text[after_index + 1].isdigit()
    if after in "-/":
        return after_index + 1 < length and evidence_text[after_index + 1].isalnum()
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


def describe_competitor_mention(
    number: int,
    specification: ContentDraftSpecification,
    prompt: ContentDraftPrompt,
) -> CompetitorMentionViolation | None:
    """Locate the first claim rejection after final validation selected its category.

    This observer reuses the unchanged claim validator. It has no effect on
    authorization, matching, validation order, or final report shape.
    """

    evidence = _build_evidence_context(
        prompt.operation, prompt.input.site_content, prompt.input.opportunity_report
    )
    candidates = []
    block_groups = [(None, "draft", specification.blocks)]
    block_groups.extend(
        (index, f"draft.sections[{index}]", section.blocks)
        for index, section in enumerate(specification.sections)
    )
    for section_index, prefix, blocks in block_groups:
        for block_index, block in enumerate(blocks):
            name = "claims" if isinstance(block, ParagraphSpecification) else "items"
            claims = block.claims if name == "claims" else block.items
            candidates.extend(
                (section_index, f"{prefix}.blocks[{block_index}].{name}[{index}].text", claim)
                for index, claim in enumerate(claims)
            )
    candidates.extend(
        (None, f"draft.insertion_claims[{index}].text", claim)
        for index, claim in enumerate(specification.insertion_claims)
    )
    for section_index, path, claim in candidates:
        error = _validate_claim_evidence(
            claim, page_ids=evidence.page_ids, source_ids=evidence.source_ids,
            allowed_pages=evidence.allowed_pages, allowed_sources=evidence.allowed_sources,
            page_text_by_id=evidence.page_text_by_id, first_party_text=evidence.first_party_text,
            first_party_entities=evidence.first_party_entities,
        )
        if error is None:
            continue
        if error != ContentDraftValidationCategory.COMPETITOR_MENTION.value:
            return None
        text = " ".join(claim.text.split())
        literal = _has_competitor_mention(text, first_party_text=evidence.first_party_text)
        assert literal is not None
        runs = _TITLE_CASE_RUN_RE.findall(text)
        folded = literal.casefold()
        material = json.loads(prompt.material_json())

        def contains(value: object) -> bool:
            if isinstance(value, str):
                return folded in _normalized_text(value)
            if isinstance(value, dict):
                return any(contains(item) for item in value.values())
            if isinstance(value, (list, tuple)):
                return any(contains(item) for item in value)
            return False

        origins = {
            origin for field, origin in (
                ("pages", "SITE_CONTENT"), ("sources", "INDUSTRY_RESEARCH"),
                ("change", "CHANGE_PLAN"), ("opportunity", "CONTENT_OPPORTUNITY"),
                ("contract", "DRAFT_INSTRUCTION"),
            ) if contains(material[field])
        }
        # Arbitrary writers may have private system instructions; absence from
        # this projection alone cannot prove a model hallucination.
        origin = "MULTIPLE" if len(origins) > 1 else next(iter(origins), "UNKNOWN")
        return CompetitorMentionViolation(
            prompt.change_ref, prompt.operation.operation_type, number - 1,
            section_index, path, "TITLE_CASE_HEURISTIC", runs.index(literal),
            sum(run.casefold() == folded for run in runs), origin,
        )
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
    customer_quote_by_id: dict[str, str] | None = None,
    customer_binding: DraftCustomerEvidence | None = None,
    proposal_only: bool = False,
    numeric_failure_observer: Callable[[object, str, str, tuple[str, ...]], None] | None = None,
    claim_type_failure_observer: Callable[[DraftClaimSpecification, str, bool, bool, bool], None] | None = None,
) -> str | None:
    text = claim.text
    if claim.proposal is not None and (type(claim.proposal) is not InterpretationProposal
            or claim.claim_type is not DraftClaimType.EVIDENCE_BASED_INTERPRETATION):
        return "FIELD_CONTRACT"
    if type(text) is not str or not text.strip():
        return ContentDraftValidationCategory.FIELD_CONTRACT.value
    normalized = " ".join(text.split())
    if claim.proposal is not None and text != normalized:
        return "CANDIDATE_TEXT_NOT_CANONICAL"
    maximum = (MAX_INTERPRETATION_CHARS if customer_binding is not None
        and claim.claim_type is DraftClaimType.EVIDENCE_BASED_INTERPRETATION else MAX_CLAIM_CHARS)
    if not normalized or len(normalized) > maximum:
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

    quotes = customer_quote_by_id or {}
    if (type(claim.customer_refs) is not tuple or len(claim.customer_refs) > 20
        or any(type(ref) is not str for ref in claim.customer_refs)
        or len(set(claim.customer_refs)) != len(claim.customer_refs)):
        return ContentDraftValidationCategory.FIELD_CONTRACT.value
    for ref in claim.customer_refs:
        if ref not in quotes:
            return ContentDraftValidationCategory.UNKNOWN_CUSTOMER_REFERENCE.value
    if (customer_binding is not None and any(s.facts for s in customer_binding.sources)
            and not claim.customer_refs and claim.claim_type not in {DraftClaimType.CALL_TO_ACTION, DraftClaimType.EDITORIAL_TRANSITION}):
        # A new assumption cannot escape the interpretation boundary by being
        # relabelled as general context or an editorial sentence.
        return ContentDraftValidationCategory.CLAIM_TYPE_CONTRACT.value
    if customer_binding is not None and any(s.facts for s in customer_binding.sources):
        if claim.claim_type is DraftClaimType.EDITORIAL_TRANSITION and text not in {
                'The next section considers the purchasing decision.',
                'Consider the following questions before proceeding.'}:
            return 'CLAIM_TYPE_CONTRACT'
        if claim.claim_type is DraftClaimType.CALL_TO_ACTION and re.search(
                r'\b(?:handles|delivers|guarantees|provides|ensures|achieves|will|certified|capable)\b', text, re.I):
            return 'CLAIM_TYPE_CONTRACT'
    if claim.customer_refs and claim.claim_type not in {DraftClaimType.OBSERVED_PRODUCT_FACT, DraftClaimType.EVIDENCE_BASED_INTERPRETATION}:
        return ContentDraftValidationCategory.CLAIM_TYPE_CONTRACT.value
    if claim.claim_type is DraftClaimType.EVIDENCE_BASED_INTERPRETATION and not claim.customer_refs:
        return ContentDraftValidationCategory.CLAIM_TYPE_CONTRACT.value
    support_kind = (DraftClaimSupportKind.CUSTOMER_REVIEWED_QUOTE if claim.customer_refs else
                    _derived_support_kind(claim.claim_type, claim.page_refs, claim.source_refs))
    is_first_party_expression = (
        claim.claim_type in {DraftClaimType.OBSERVED_PRODUCT_FACT, DraftClaimType.EVIDENCE_BASED_INTERPRETATION}
        or _has_first_party_expression(normalized)
        or _contains_first_party_entity(normalized, first_party_entities)
    )

    if claim.claim_type is DraftClaimType.OBSERVED_PRODUCT_FACT:
        if not (claim.page_refs or claim.customer_refs):
            return ContentDraftValidationCategory.FIRST_PARTY_FACT_WITHOUT_PAGE.value
    if claim.claim_type in _FACTUAL_CLAIM_TYPES and support_kind is None:
        return ContentDraftValidationCategory.SUPPORT_KIND_CONTRACT.value
    if (
        claim.claim_type in _FACTUAL_CLAIM_TYPES
        and is_first_party_expression
        and not (claim.page_refs or claim.customer_refs)
    ):
        return ContentDraftValidationCategory.FIRST_PARTY_FACT_WITHOUT_PAGE.value
    if (
        claim.claim_type
        in (DraftClaimType.EDITORIAL_TRANSITION, DraftClaimType.CALL_TO_ACTION)
        and (claim.page_refs or claim.source_refs or claim.customer_refs)
    ):
        if claim_type_failure_observer is not None:
            claim_type_failure_observer(claim, "EDITORIAL_CTA_WITH_REFS", False,
                                        is_first_party_expression, False)
        return ContentDraftValidationCategory.CLAIM_TYPE_CONTRACT.value

    if claim.claim_type in _FACTUAL_CLAIM_TYPES and is_first_party_expression:
        combined_page_text = "\n".join((
            *(page_text_by_id[ref] for ref in claim.page_refs),
            *(_normalized_text(quotes[ref]) for ref in claim.customer_refs),
        ))
        numeric_error = _validate_numeric_grounding(normalized, combined_page_text)
        if numeric_error is not None:
            if numeric_failure_observer is not None:
                numeric_failure_observer(claim, normalized, combined_page_text, claim.page_refs + claim.customer_refs)
            return numeric_error
    if claim.customer_refs:
        if claim.proposal is not None:
            p = claim.proposal
            if (p.limitation not in text or p.procurement_action not in text):
                return 'CUSTOMER_QUOTE_MISMATCH'
            # Conservative numeric-context rule for NEW inference: quantities
            # belong in exact source sentences, with their subject and qualifiers.
            # Identifier-only prose can reason about a model without a quantity.
            for candidate_text in (text, p.reasoning, p.assumptions, p.limitation, p.procurement_action):
                for sentence in re.split(r'(?<=[.!?])\s+', candidate_text):
                    quantities = tuple(e for e in extract_numeric_expressions(sentence)
                        if not re.fullmatch(r'[a-z][a-z0-9_-]*', e))
                    if quantities and not any(sentence in quotes[r] for r in claim.customer_refs):
                        return 'NUMERIC_CONTEXT_NOT_PRESERVED'
            # Metadata is untrusted too; numbers cannot be hidden in reasoning.
            for extra in (p.reasoning, p.assumptions, p.limitation, p.procurement_action):
                if _validate_numeric_grounding(extra, combined_page_text):
                    return 'NUMERIC_NOT_GROUNDED'
                if _has_promotional_term(extra):
                    return 'UNSUPPORTED_PROMOTIONAL_CLAIM'
        error = (customer_binding.claim_error(text, claim.claim_type.value, claim.customer_refs,
                    claim.page_refs, claim.source_refs, claim.proposal) if customer_binding is not None else
                 (None if len(claim.customer_refs) == 1 and text == quotes[claim.customer_refs[0]] else
                  ContentDraftValidationCategory.CUSTOMER_QUOTE_MISMATCH.value))
        if error and not (proposal_only and claim.proposal is not None
                          and not claim.page_refs and not claim.source_refs):
            return ('INTERPRETATION_PENDING_REVIEW' if claim.proposal is not None else error)
    if claim.claim_type in (
        DraftClaimType.EDITORIAL_TRANSITION,
        DraftClaimType.CALL_TO_ACTION,
    ):
        has_numeric = bool(extract_numeric_expressions(normalized))
        has_promotional = _has_promotional_term(normalized) is not None
        if has_numeric or is_first_party_expression or has_promotional:
            if claim_type_failure_observer is not None:
                claim_type_failure_observer(claim, "EDITORIAL_CTA_FACTUAL_CONTENT",
                                            has_numeric, is_first_party_expression,
                                            has_promotional)
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
        if term in _normalized_text(normalized) and not (claim.page_refs or claim.customer_refs):
            return ContentDraftValidationCategory.FIRST_PARTY_FACT_WITHOUT_PAGE.value
    return None


# --- Deterministic finalization -----------------------------------------


def article_quality_findings(operation, blocks, section_block_counts, bundle):
    """Small structural preflight, never a semantic score or human approval."""
    resource = operation.new_resource_spec
    if resource is None or not resource.section_briefs:
        return ('ARTICLE_SCOPE_NOT_STRUCTURED',)
    if bundle is None or len(section_block_counts) != len(resource.section_briefs):
        return ('ARTICLE_EVIDENCE_MAP_MISSING',)
    findings, offset, all_claims = [], 0, []
    for brief, count in zip(resource.section_briefs, section_block_counts):
        claims = tuple(c for b in blocks[offset:offset + count] for c in
                       (b.claims if isinstance(b, ParagraphBlock) else b.items if isinstance(b, BulletListBlock) else ()))
        offset += count
        all_claims.extend(claims)
        if not any(c.claim_type is DraftClaimType.OBSERVED_PRODUCT_FACT for c in claims):
            findings.append('SECTION_DIRECT_FACT_MISSING: ' + brief.heading)
        explanations = tuple(c for c in claims if c.claim_type is DraftClaimType.EVIDENCE_BASED_INTERPRETATION)
        if not explanations:
            findings.append('SECTION_EXPLANATION_ACTION_LIMIT_MISSING: ' + brief.heading)
        elif not any(brief.limitations in c.text and brief.procurement_action in c.text for c in explanations):
            findings.append('SECTION_QUESTION_BOUNDARIES_MISSING: ' + brief.heading)
        assigned = {s.evidence_id for s in bundle.sources if set(s.requirement_ids) & set(brief.requirement_ids)}
        allowed_facts = {f.fact_ref for s in bundle.sources for f in s.facts
                         if set(f.requirement_ids) & set(brief.requirement_ids)}
        for c in claims:
            if any(r.split('.')[0] not in assigned for r in c.customer_refs):
                findings.append('SECTION_EVIDENCE_OUTSIDE_QUESTION: ' + brief.heading)
            if allowed_facts and any(r not in allowed_facts for r in c.customer_refs):
                findings.append('SECTION_FACT_OUTSIDE_QUESTION: ' + brief.heading)
        covered_requirements = {rid for s in bundle.sources for f in s.facts
                                if any(f.fact_ref in c.customer_refs for c in claims) for rid in f.requirement_ids}
        if not set(brief.requirement_ids) <= covered_requirements:
            findings.append('SECTION_REQUIREMENT_UNANSWERED: ' + brief.heading)
        if {r.split('.')[0] for c in claims for r in c.customer_refs} != set(brief.supporting_evidence):
            findings.append('SECTION_QUESTION_EVIDENCE_INCOMPLETE: ' + brief.heading)
    if not all_claims or all_claims[-1].claim_type is not DraftClaimType.CALL_TO_ACTION:
        findings.append('PROCUREMENT_CTA_MISSING')
    if sum(bool(c.source_refs) for c in all_claims) > sum(bool(c.customer_refs) for c in all_claims):
        findings.append('BACKGROUND_DOMINATES')
    return tuple(dict.fromkeys(findings))


@dataclass(frozen=True, slots=True)
class _DraftEvidence:
    page_ids: set[str]
    source_ids: set[str]
    allowed_pages: set[str]
    allowed_sources: set[str]
    page_text_by_id: dict[str, str]
    first_party_text: str
    first_party_entities: frozenset[str]
    numeric_failure_observer: Callable[[object, str, str, tuple[str, ...]], None] | None = None
    claim_type_failure_observer: Callable[[DraftClaimSpecification, str, bool, bool, bool], None] | None = None
    customer_quote_by_id: dict[str, str] | None = None
    customer_binding: DraftCustomerEvidence | None = None


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
        numeric_failure_observer=evidence.numeric_failure_observer,
        claim_type_failure_observer=evidence.claim_type_failure_observer,
        customer_quote_by_id=evidence.customer_quote_by_id,
        customer_binding=evidence.customer_binding,
    )
    if error is not None:
        return None, error
    support_kind = (DraftClaimSupportKind.CUSTOMER_REVIEWED_QUOTE if claim.customer_refs else
                    _derived_support_kind(claim.claim_type, claim.page_refs, claim.source_refs))
    if claim.claim_type is DraftClaimType.EVIDENCE_BASED_INTERPRETATION:
        support_kind = DraftClaimSupportKind.CUSTOMER_REVIEWED_INTERPRETATION
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
        customer_refs=claim.customer_refs,
        proposal=claim.proposal,
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
                if evidence.numeric_failure_observer is not None:
                    evidence.numeric_failure_observer(cell, cell.text, combined, cell.page_refs)
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
            if evidence.numeric_failure_observer is not None:
                evidence.numeric_failure_observer(specification, anchor, target_text, (target_page_ref,))
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
    *,
    customer_evidence: DraftCustomerEvidence | None = None,
    _numeric_failure_observer: Callable[[object, str, str, tuple[str, ...]], None] | None = None,
    _claim_type_failure_observer: Callable[[DraftClaimSpecification, str, bool, bool, bool], None] | None = None,
) -> tuple[DraftItem | None, str | None]:
    capability_error = comparison_operation_error(operation)
    if capability_error is not None:
        return None, capability_error
    expected_type = content_draft_type_for(operation.operation_type)
    if specification.draft_type is not expected_type:
        return None, ContentDraftValidationCategory.FIELD_CONTRACT.value
    if specification.change_ref != operation.change_id:
        return None, ContentDraftValidationCategory.UNKNOWN_CHANGE_REFERENCE.value

    evidence = _build_evidence_context(operation, site_content, opportunity_report)
    if _numeric_failure_observer is not None or _claim_type_failure_observer is not None:
        evidence = _DraftEvidence(
            evidence.page_ids, evidence.source_ids, evidence.allowed_pages, evidence.allowed_sources,
            evidence.page_text_by_id, evidence.first_party_text, evidence.first_party_entities,
            _numeric_failure_observer, _claim_type_failure_observer,
        )
    if customer_evidence is not None:
        if (type(customer_evidence) is not DraftCustomerEvidence
            or not customer_evidence.matches_native(site_content, opportunity_report, operation)):
            return None, ContentDraftValidationCategory.CUSTOMER_EVIDENCE_INVALID.value
        evidence = replace(evidence,
            customer_quote_by_id=customer_evidence.quote_map(), customer_binding=customer_evidence,
            first_party_text=evidence.first_party_text + " " + " ".join(s.quote for s in customer_evidence.sources),
            first_party_entities=evidence.first_party_entities | frozenset(
                token.casefold() for source in customer_evidence.sources for token in _MODEL_TOKEN_RE.findall(source.quote)))
    state = _ClaimState()

    heading: str | None = None
    ordered_headings: tuple[str, ...] = ()
    blocks: tuple[DraftBlock, ...] = ()
    section_block_counts: tuple[int, ...] = ()

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
        ordered_headings = expected_outline
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
        section_block_counts = tuple(len(section.blocks) for section in specification.sections)

    if customer_evidence is not None:
        used_refs = {ref for block in blocks for claim in
            (block.claims if isinstance(block, ParagraphBlock) else block.items)
            for ref in claim.customer_refs}
        if not customer_evidence.reference_selection_valid(used_refs):
            return None, ContentDraftValidationCategory.CUSTOMER_EVIDENCE_COVERAGE.value
        if (operation.new_resource_spec is not None and operation.new_resource_spec.section_briefs
                and article_quality_findings(operation, blocks, section_block_counts, customer_evidence)):
            return None, ContentDraftValidationCategory.ARTICLE_QUALITY_GAP.value
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
            section_block_counts=section_block_counts,
            customer_evidence=customer_evidence,
        ),
        None,
    )


def describe_claim_type_violation(
    number: int,
    specification: ContentDraftSpecification,
    prompt: ContentDraftPrompt,
) -> ClaimTypeViolation | None:
    """Replay finalization to locate its first claim-type rejection, without text output."""

    paths: dict[int, str] = {}
    groups = [("draft", specification.blocks)]
    groups.extend((f"draft.sections[{index}]", section.blocks)
                  for index, section in enumerate(specification.sections))
    for prefix, blocks in groups:
        for block_index, block in enumerate(blocks):
            name = "claims" if isinstance(block, ParagraphSpecification) else "items"
            for index, claim in enumerate(block.claims if name == "claims" else block.items):
                paths[id(claim)] = f"{prefix}.blocks[{block_index}].{name}[{index}].claim_type"
    for index, claim in enumerate(specification.insertion_claims):
        paths[id(claim)] = f"draft.insertion_claims[{index}].claim_type"

    captured: list[ClaimTypeViolation] = []

    def observe(claim, rule_id, has_numeric, has_first_party, has_promotional):
        captured.append(ClaimTypeViolation(
            prompt.change_ref, prompt.operation.operation_type, number - 1,
            paths[id(claim)], rule_id, claim.claim_type, (), prompt.repair_category,
            bool(claim.page_refs), bool(claim.source_refs), has_numeric,
            has_first_party, has_promotional,
        ))

    _, error = finalize_draft_item(
        number, specification, prompt.operation, prompt.opportunity,
        prompt.input.site_content, prompt.input.opportunity_report,
        customer_evidence=prompt.input.customer_evidence,
        _claim_type_failure_observer=observe,
    )
    return captured[0] if error == ContentDraftValidationCategory.CLAIM_TYPE_CONTRACT.value and captured else None


def describe_numeric_grounding_violation(
    number: int,
    specification: ContentDraftSpecification,
    prompt: ContentDraftPrompt,
    *,
    attempt: int = 1,
) -> NumericGroundingViolation | None:
    """Observe the same finalizer after it selected NUMERIC_NOT_GROUNDED.

    Only the original failing numeric check triggers the observer. Replaying
    the complete finalizer preserves structural, reference, and claim order;
    no separate validator selects a rejected field. Literal text is local to
    this function and never enters the descriptor.
    """

    paths: dict[int, tuple[str, int | None, int | None]] = {
        id(specification): ("draft.anchor_text", None, None),
    }
    groups = [("draft", specification.blocks)]
    groups.extend((f"draft.sections[{index}]", section.blocks)
                  for index, section in enumerate(specification.sections))
    for prefix, blocks in groups:
        for block_index, block in enumerate(blocks):
            name = "claims" if isinstance(block, ParagraphSpecification) else "items"
            for index, claim in enumerate(block.claims if name == "claims" else block.items):
                paths.setdefault(id(claim), (f"{prefix}.blocks[{block_index}].{name}[{index}].text", None, None))
    for index, claim in enumerate(specification.insertion_claims):
        paths.setdefault(id(claim), (f"draft.insertion_claims[{index}].text", None, None))
    schema = prompt.operation.comparison_table_spec
    for index, cell in enumerate(specification.cells):
        paths.setdefault(id(cell), (
            f"draft.cells[{index}].text",
            schema.row_dimensions.index(cell.row_dimension) if schema else None,
            schema.column_headers.index(cell.column) if schema else None,
        ))
    captured: list[NumericGroundingViolation] = []

    def observe(subject, text, evidence_text, refs):
        expressions = extract_numeric_expressions(text)
        bare = tuple(_is_bare_number(expression) for expression in expressions)
        # These disjoint reasons follow validator precedence. Bare expressions
        # never reach evidence matching, even when present in cited P text.
        mismatched = tuple(not is_bare and not _numeric_expression_is_present(expression, evidence_text)
                           for expression, is_bare in zip(expressions, bare))
        grounded = tuple(not is_bare and not mismatch
                         for is_bare, mismatch in zip(bare, mismatched))
        index = grounded.index(False)
        expression = expressions[index]
        if _is_bare_number(expression):
            kind = ("BARE_INTEGER" if expression.isdigit() else
                    "BARE_DECIMAL" if re.fullmatch(r"\d+\.\d+", expression) else "BARE_NUMBER")
        elif "%" in expression:
            kind = "PERCENTAGE"
        elif re.search(r"\d-\d", expression):
            kind = "RANGE"
        elif re.search(r"\b(?:usd|eur|gbp|cny)\b", expression):
            kind = "CURRENCY"
        elif re.search(r"[a-zµ°\"'/]", expression):
            kind = "NUMBER_WITH_UNIT"
        else:
            kind = "OTHER_EXPRESSION"
        path, row, column = paths[id(subject)]
        captured.append(NumericGroundingViolation(
            prompt.change_ref, prompt.operation.operation_type, number - 1, path, kind,
            index, len(expressions), sum(grounded), len(expressions) - sum(grounded), refs,
            "NORMALIZED_EXACT_NON_BARE",
            ("MIXED_FIRST_PARTY_EVIDENCE" if any(r.startswith("P") for r in refs) else "CUSTOMER_EVIDENCE")
                if any(r.startswith("E") for r in refs) else
                ("TARGET_PAGE_EVIDENCE" if subject is specification else "PAGE_EVIDENCE"),
            "BARE_NUMBER_FORBIDDEN" if bare[index] else
                ("NUMERIC_EXPRESSION_NOT_IN_CITED_FIRST_PARTY" if any(r.startswith("E") for r in refs)
                 else "NUMERIC_EXPRESSION_NOT_IN_CITED_PAGE"),
            sum(bare), sum(mismatched), bool(getattr(subject, "source_refs", ())),
            attempt, row, column,
        ))

    _, error = finalize_draft_item(
        number, specification, prompt.operation, prompt.opportunity,
        prompt.input.site_content, prompt.input.opportunity_report,
        customer_evidence=prompt.input.customer_evidence,
        _numeric_failure_observer=observe,
    )
    return captured[0] if error == ContentDraftValidationCategory.NUMERIC_NOT_GROUNDED.value and captured else None
