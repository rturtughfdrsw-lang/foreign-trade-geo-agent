"""Provider-independent, evidence-grounded change-plan contracts."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import json
from foreign_trade_geo_agent.core.first_party_planning import (
    FirstPartyPlanningScope, MAX_FIRST_PARTY_EXCERPT_CHARS, MAX_FIRST_PARTY_EXCERPTS,
)
import re
from types import MappingProxyType
import unicodedata
from typing import Protocol

from .content_opportunity import (
    CONTENT_OPPORTUNITY_ABSENCE_TERMS,
    CONTENT_OPPORTUNITY_LIMITATIONS,
    MAX_CONTENT_OPPORTUNITY_SOURCE_URL_CHARS,
    MAX_OPPORTUNITIES,
    MAX_RESEARCH_SOURCES,
    MAX_SITE_PACKET_BYTES,
    MAX_SITE_PACKET_CHARS,
    MAX_SITE_PAGES,
    MAX_SOURCE_CONTENT_CHARS,
    MAX_SOURCE_PACKET_BYTES,
    MAX_SOURCE_PACKET_CHARS,
    MAX_SOURCE_TITLE_CHARS,
    MAX_TOTAL_SOURCE_CONTENT_CHARS,
    ContentOpportunity,
    ContentOpportunityActionCode,
    ContentOpportunityReport,
    ContentOpportunityPage,
    ContentOpportunitySource,
    ContentOpportunitySourceMaterial,
    ContentOpportunityStatus,
    ContentOpportunityType,
    build_content_opportunity_evidence_catalog,
    finalized_content_opportunity_error,
    parse_safe_http_url,
)
from .fetching import UrlOrigin
from .history import PlanningValidationCategory
from .optimization import NumberedAuditEvidence
from .extraction import StructuredContentBlock, StructuredContentKind
from .research import ResearchEvidenceClassification
from .site_content import (
    SiteContentEvidence,
    SiteContentEvidenceScope,
    SiteContentPacket,
    SiteContentPacketLimits,
)


MAX_INPUT_OPPORTUNITIES = MAX_OPPORTUNITIES
MAX_OPERATIONS = 8
MAX_OPERATIONS_PER_OPPORTUNITY = 2
MIN_PAGE_REFS_PER_OPERATION = 0
MAX_PAGE_REFS_PER_OPERATION = 3
MIN_SOURCE_REFS_PER_OPERATION = 1
MAX_SOURCE_REFS_PER_OPERATION = 4
MIN_EXISTING_PAGE_REFS_PER_OPERATION = 1
MIN_INTERNAL_LINK_PAGE_REFS = 2
REORDER_PAGE_REFS = 1
MAX_PROPOSED_HEADING_CHARS = 120
MIN_CONTENT_POINTS_PER_OPERATION = 1
MAX_CONTENT_POINTS_PER_OPERATION = 5
MAX_CONTENT_POINT_SUBJECT_CHARS = MAX_FIRST_PARTY_EXCERPT_CHARS
MAX_CONTENT_POINT_CANDIDATES_PER_EVIDENCE = 8
MAX_CONTENT_POINT_CANDIDATES_PER_OPPORTUNITY = 12
MAX_CONTENT_POINT_CANDIDATES_GLOBAL = 48
CONTENT_POINT_CANDIDATE_REPAIR_RESERVE_CHARS = 512
CONTENT_POINT_CANDIDATE_REPAIR_RESERVE_BYTES = 1_024
MAX_EXACT_LOCATOR_CANDIDATES_PER_PAGE = 8
MAX_LOCATOR_CANDIDATES_PER_OPPORTUNITY = 24
MAX_PROPOSED_HEADING_CANDIDATES_PER_PAGE = 8
MAX_PROPOSED_HEADING_CANDIDATES_PER_OPPORTUNITY = 16
MAX_OUTLINE_HEADING_CANDIDATES_PER_OPPORTUNITY = 8
MIN_REORDER_HEADINGS = 2
MAX_REORDER_HEADINGS = 6
MIN_OUTLINE_HEADINGS = 2
MAX_OUTLINE_HEADINGS = 6
MAX_OUTLINE_HEADING_CHARS = 100
MIN_TABLE_COLUMNS = 2
MAX_TABLE_COLUMNS = 5
MIN_TABLE_DIMENSIONS = 1
MAX_TABLE_DIMENSIONS = 6
MAX_TABLE_LABEL_CHARS = 80
MAX_ANCHOR_INTENT_CHARS = 120
MAX_OBSERVED_CONTEXT_CHARS = 240
MAX_RAW_OUTPUT_CHARS = 10_000
MAX_RAW_OUTPUT_BYTES = 20 * 1024
MAX_SYSTEM_PROMPT_CHARS = 8_000
MAX_SYSTEM_PROMPT_BYTES = 16 * 1024
MAX_USER_MATERIAL_CHARS = 26_000
MAX_USER_MATERIAL_BYTES = 56 * 1024
MAX_INPUT_ENVELOPE_CHARS = 52_000
MAX_INPUT_ENVELOPE_BYTES = 56 * 1024
MAX_PROVIDER_TOKENS = 1_800
MAX_CHANGE_PLAN_TIMEOUT_SECONDS = 120.0


CHANGE_PLAN_LIMITATIONS = (
    "Semantic locators are review targets, not CMS selectors.",
    "The plan is based only on bounded, observed evidence.",
    "External S evidence is unverified and requires human review.",
    "Change Plan SUCCESS means generated and validated, not approved.",
    "Current CMS content and locator matches must be revalidated before execution.",
)


class ChangePlanStatus(str, Enum):
    SUCCESS = "success"
    INVALID_INPUT = "invalid_input"
    INPUT_TOO_LARGE = "input_too_large"
    GENERATION_FAILED = "generation_failed"
    INVALID_OUTPUT = "invalid_output"
    WORKFLOW_TIMEOUT = "workflow_timeout"


class ChangePlanGenerationStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"


class ChangePlanGenerationFailureKind(str, Enum):
    PROVIDER_FAILURE = "provider_failure"
    INPUT_TOO_LARGE = "input_too_large"


class ChangeTargetKind(str, Enum):
    MODIFY_EXISTING_PAGE = "MODIFY_EXISTING_PAGE"
    CREATE_NEW_PAGE = "CREATE_NEW_PAGE"


class ChangeOperationType(str, Enum):
    EXPAND_SECTION = "EXPAND_SECTION"
    PROPOSE_SECTION_REORDER = "PROPOSE_SECTION_REORDER"
    ADD_SECTION = "ADD_SECTION"
    ADD_COMPARISON_TABLE = "ADD_COMPARISON_TABLE"
    ADD_INTERNAL_LINK = "ADD_INTERNAL_LINK"
    CREATE_NEW_RESOURCE = "CREATE_NEW_RESOURCE"


class SectionLocatorKind(str, Enum):
    PAGE_LEVEL = "PAGE_LEVEL"
    EXACT_OBSERVED_HEADING = "EXACT_OBSERVED_HEADING"
    NEW_PAGE = "NEW_PAGE"


class ObservedHeadingKind(str, Enum):
    H1 = "H1"
    H2 = "H2"
    STRUCTURED_HEADING = "STRUCTURED_HEADING"
    SEMANTIC_ONLY = "SEMANTIC_ONLY"


class SectionPurpose(str, Enum):
    BUYER_GUIDANCE = "BUYER_GUIDANCE"
    TECHNICAL_DOCUMENTATION = "TECHNICAL_DOCUMENTATION"


class NewResourcePurpose(str, Enum):
    SUPPORTING_RESOURCE = "SUPPORTING_RESOURCE"
    BUYER_GUIDANCE = "BUYER_GUIDANCE"
    TECHNICAL_DOCUMENTATION = "TECHNICAL_DOCUMENTATION"
    COMPARISON_RESOURCE = "COMPARISON_RESOURCE"


class ContentPointIntent(str, Enum):
    EXPLAIN = "EXPLAIN"
    COMPARE = "COMPARE"
    DESCRIBE = "DESCRIBE"
    SUMMARIZE = "SUMMARIZE"


class ChangePlanValidationCategory(str, Enum):
    JSON_FORMAT = "JSON_FORMAT"
    FIELD_CONTRACT = "FIELD_CONTRACT"
    OUTPUT_TOO_LARGE = "OUTPUT_TOO_LARGE"
    UNKNOWN_OPPORTUNITY_REFERENCE = "UNKNOWN_OPPORTUNITY_REFERENCE"
    UNKNOWN_PAGE_REFERENCE = "UNKNOWN_PAGE_REFERENCE"
    UNKNOWN_SOURCE_REFERENCE = "UNKNOWN_SOURCE_REFERENCE"
    OPERATION_NOT_ALLOWED = "OPERATION_NOT_ALLOWED"
    COMPARISON_UNAVAILABLE = "COMPARISON_UNAVAILABLE"
    TARGET_LOCATOR_INVALID = "TARGET_LOCATOR_INVALID"
    EVIDENCE_USE_NOT_ALLOWED = "EVIDENCE_USE_NOT_ALLOWED"
    CONTENT_NOT_GROUNDED = "CONTENT_NOT_GROUNDED"
    INTERNAL_LINK_INVALID = "INTERNAL_LINK_INVALID"
    UNSUPPORTED_ABSENCE_CLAIM = "UNSUPPORTED_ABSENCE_CLAIM"
    INPUT_TOO_LARGE = "INPUT_TOO_LARGE"


class GroundingMode(str, Enum):
    """Stable names for the grounding checks already enforced by Core."""

    VERBATIM_CONTIGUOUS = "VERBATIM_CONTIGUOUS"
    TOKEN_RECOMBINATION = "TOKEN_RECOMBINATION"


class TargetLocatorRepairRule(str, Enum):
    """Provider-fixable TARGET_LOCATOR_INVALID subrules."""

    REORDER_HEADING_NOT_OBSERVED_ON_TARGET_PAGE = (
        "REORDER_HEADING_NOT_OBSERVED_ON_TARGET_PAGE"
    )
    ADD_SECTION_PROPOSED_HEADING_COLLIDES = (
        "ADD_SECTION_PROPOSED_HEADING_COLLIDES"
    )


@dataclass(frozen=True, slots=True)
class TargetLocatorViolation:
    """Sanitized transient metadata for one exact locator failure."""

    field_path: str
    repair_rule: TargetLocatorRepairRule | None = None

    def __post_init__(self) -> None:
        if self.repair_rule is not None and not isinstance(
            self.repair_rule,
            TargetLocatorRepairRule,
        ):
            raise ValueError("Target locator violation metadata is invalid.")
        expected_suffix = {
            None: "locator_ref",
            TargetLocatorRepairRule.REORDER_HEADING_NOT_OBSERVED_ON_TARGET_PAGE: (
                "ordered_headings"
            ),
            TargetLocatorRepairRule.ADD_SECTION_PROPOSED_HEADING_COLLIDES: (
                "proposed_heading"
            ),
        }.get(self.repair_rule)
        if (
            expected_suffix is None
            or type(self.field_path) is not str
            or re.fullmatch(
                rf"R[1-9][0-9]*\.(?:primary_operation|secondary_operation)\.{expected_suffix}",
                self.field_path,
            )
            is None
        ):
            raise ValueError("Target locator violation metadata is invalid.")


class FieldContractRepairClass(str, Enum):
    """Internal handling class for one sanitized field-contract violation."""

    TYPE_A = "TYPE_A"
    TYPE_B = "TYPE_B"
    TYPE_C = "TYPE_C"


class FieldContractRule(str, Enum):
    """Stable internal rule identifiers; values never contain provider text."""

    ROOT_TYPE_INVALID = "ROOT_TYPE_INVALID"
    TOP_LEVEL_KEYS_INVALID = "TOP_LEVEL_KEYS_INVALID"
    OPPORTUNITY_OPERATIONS_TYPE_INVALID = "OPPORTUNITY_OPERATIONS_TYPE_INVALID"
    OPPORTUNITY_COUNT_EXCEEDED = "OPPORTUNITY_COUNT_EXCEEDED"
    SLOT_TYPE_INVALID = "SLOT_TYPE_INVALID"
    PRIMARY_REQUIRED = "PRIMARY_REQUIRED"
    SLOT_KEYS_INVALID = "SLOT_KEYS_INVALID"
    OPERATION_KEYS_INVALID = "OPERATION_KEYS_INVALID"
    OPERATION_COUNT_EXCEEDED = "OPERATION_COUNT_EXCEEDED"
    ENUM_INVALID = "ENUM_INVALID"
    LIST_TYPE_INVALID = "LIST_TYPE_INVALID"
    LIST_COUNT_EXCEEDED = "LIST_COUNT_EXCEEDED"
    LIST_COUNT_BELOW_MIN = "LIST_COUNT_BELOW_MIN"
    LIST_DUPLICATE = "LIST_DUPLICATE"
    STRING_TYPE_INVALID = "STRING_TYPE_INVALID"
    STRING_EMPTY = "STRING_EMPTY"
    STRING_LENGTH_EXCEEDED = "STRING_LENGTH_EXCEEDED"
    STRING_FORMAT_INVALID = "STRING_FORMAT_INVALID"
    CONTENT_POINT_SHAPE_INVALID = "CONTENT_POINT_SHAPE_INVALID"
    SUBJECT_REF_INVALID = "SUBJECT_REF_INVALID"
    PROPOSED_HEADING_REF_INVALID = "PROPOSED_HEADING_REF_INVALID"
    PAGE_BINDING_SHAPE_INVALID = "PAGE_BINDING_SHAPE_INVALID"
    PAGE_BINDING_DUPLICATE = "PAGE_BINDING_DUPLICATE"
    COMPARISON_TABLE_SHAPE_INVALID = "COMPARISON_TABLE_SHAPE_INVALID"
    CANONICAL_OPERATION_DUPLICATE = "CANONICAL_OPERATION_DUPLICATE"
    INTERNAL_INVARIANT = "INTERNAL_INVARIANT"


_FIELD_CONTRACT_TYPE_A_RULES = frozenset(
    {
        FieldContractRule.SUBJECT_REF_INVALID,
        FieldContractRule.PROPOSED_HEADING_REF_INVALID,
        FieldContractRule.PAGE_BINDING_DUPLICATE,
    }
)
_FIELD_CONTRACT_TYPE_B_RULES = frozenset(
    {
        FieldContractRule.STRING_LENGTH_EXCEEDED,
        FieldContractRule.LIST_COUNT_EXCEEDED,
        FieldContractRule.LIST_COUNT_BELOW_MIN,
    }
)
_FIELD_CONTRACT_EXPECTED_KEYS = frozenset(
    {
        "expected_type",
        "expected_keys",
        "required",
        "max_count",
        "min_count",
        "max_chars",
    }
)
_FIELD_CONTRACT_ACTUAL_KEYS = frozenset(
    {"actual_type", "actual_count", "actual_chars"}
)
_FIELD_CONTRACT_SAFE_TYPES = frozenset(
    {"array", "boolean", "null", "number", "object", "string", "unknown"}
)
_BOUNDED_FIELD_REPAIR_ACTION = (
    "Previous generation violated a bounded field contract. Regenerate the "
    "complete response and preserve all valid references and grounding."
)


@dataclass(frozen=True, slots=True)
class FieldContractViolation:
    """Sanitized transient metadata for one exact FIELD_CONTRACT failure."""

    rule_id: FieldContractRule
    field_path: str
    expected: tuple[tuple[str, object], ...] = ()
    actual: tuple[tuple[str, object], ...] = ()

    def __post_init__(self) -> None:
        if (
            not isinstance(self.rule_id, FieldContractRule)
            or type(self.field_path) is not str
            or re.fullmatch(
                r"(?:\$|R[1-9][0-9]*(?:\.(?:primary_operation|secondary_operation)(?:\.[A-Za-z_][A-Za-z0-9_]*(?:\[[0-9]+\])?)*)?)",
                self.field_path,
            )
            is None
            or not _safe_violation_metadata(
                self.expected,
                allowed_keys=_FIELD_CONTRACT_EXPECTED_KEYS,
            )
            or not _safe_violation_metadata(
                self.actual,
                allowed_keys=_FIELD_CONTRACT_ACTUAL_KEYS,
            )
        ):
            raise ValueError("Field contract violation metadata is invalid.")

    @property
    def repair_class(self) -> FieldContractRepairClass:
        if self.rule_id in _FIELD_CONTRACT_TYPE_B_RULES:
            return FieldContractRepairClass.TYPE_B
        if self.rule_id in _FIELD_CONTRACT_TYPE_A_RULES:
            return FieldContractRepairClass.TYPE_A
        return FieldContractRepairClass.TYPE_C

    def retry_feedback(self) -> dict[str, object]:
        if self.repair_class is not FieldContractRepairClass.TYPE_B:
            raise ValueError("Only TYPE_B field violations may produce repair feedback.")
        return {
            "validator": ChangePlanValidationCategory.FIELD_CONTRACT.value,
            "field_path": self.field_path,
            "rule_id": self.rule_id.value,
            "expected": dict(self.expected),
            "actual": dict(self.actual),
            "required_action": _BOUNDED_FIELD_REPAIR_ACTION,
        }


@dataclass(frozen=True, slots=True)
class GroundingViolation:
    """Sanitized transient metadata for one exact grounding failure."""

    opportunity_ref: str
    slot: str
    operation_type: ChangeOperationType
    field_path: str
    grounding_mode: GroundingMode
    cited_ref_ids: tuple[str, ...]
    normalized_length: int
    contiguous_match: bool | None = None
    token_coverage_pass: bool | None = None
    normalized_token_count: int | None = None
    matched_token_count: int | None = None

    def __post_init__(self) -> None:
        path_pattern = (
            rf"{re.escape(self.opportunity_ref)}\."
            rf"{re.escape(self.slot)}\."
            r"[A-Za-z_][A-Za-z0-9_]*(?:\[[0-9]+\])?"
            r"(?:\.[A-Za-z_][A-Za-z0-9_]*(?:\[[0-9]+\])?)*"
        )
        refs_are_safe = (
            isinstance(self.cited_ref_ids, tuple)
            and len(self.cited_ref_ids)
            <= MAX_PAGE_REFS_PER_OPERATION + MAX_SOURCE_REFS_PER_OPERATION
            and len(self.cited_ref_ids) == len(set(self.cited_ref_ids))
            and all(
                type(reference) is str
                and re.fullmatch(r"[PS][1-9][0-9]*", reference) is not None
                for reference in self.cited_ref_ids
            )
        )
        common_is_safe = (
            re.fullmatch(r"R[1-9][0-9]*", self.opportunity_ref) is not None
            and self.slot in {"primary_operation", "secondary_operation"}
            and isinstance(self.operation_type, ChangeOperationType)
            and type(self.field_path) is str
            and re.fullmatch(path_pattern, self.field_path) is not None
            and isinstance(self.grounding_mode, GroundingMode)
            and refs_are_safe
            and type(self.normalized_length) is int
            and 0 <= self.normalized_length <= MAX_RAW_OUTPUT_CHARS
        )
        if self.grounding_mode is GroundingMode.VERBATIM_CONTIGUOUS:
            mode_is_safe = (
                type(self.contiguous_match) is bool
                and self.token_coverage_pass is None
                and self.normalized_token_count is None
                and self.matched_token_count is None
            )
        else:
            mode_is_safe = (
                self.contiguous_match is None
                and type(self.token_coverage_pass) is bool
                and type(self.normalized_token_count) is int
                and type(self.matched_token_count) is int
                and 0 <= self.matched_token_count <= self.normalized_token_count
                and self.normalized_token_count >= 0
            )
        if not common_is_safe or not mode_is_safe:
            raise ValueError("Grounding violation metadata is invalid.")


def _safe_violation_metadata(
    values: object,
    *,
    allowed_keys: frozenset[str],
) -> bool:
    if not isinstance(values, tuple):
        return False
    keys: list[str] = []
    for item in values:
        if not isinstance(item, tuple) or len(item) != 2:
            return False
        key, value = item
        if type(key) is not str or key not in allowed_keys:
            return False
        keys.append(key)
        if type(value) is int:
            if value < 0:
                return False
        elif type(value) is bool:
            continue
        elif type(value) is str:
            if key not in {"expected_type", "actual_type"} or value not in _FIELD_CONTRACT_SAFE_TYPES:
                return False
        elif isinstance(value, tuple):
            if key != "expected_keys" or not all(
                type(name) is str
                and re.fullmatch(r"[a-z][a-z0-9_]*", name) is not None
                for name in value
            ):
                return False
        else:
            return False
    return len(keys) == len(set(keys))


CHANGE_PLAN_REPAIR_CATEGORIES = frozenset(
    {
        ChangePlanValidationCategory.CONTENT_NOT_GROUNDED,
        ChangePlanValidationCategory.FIELD_CONTRACT,
        ChangePlanValidationCategory.TARGET_LOCATOR_INVALID,
    }
)

_CHANGE_PLAN_REPAIR_ACTIONS = MappingProxyType(
    {
        ChangePlanValidationCategory.CONTENT_NOT_GROUNDED: (
            "Regenerate the complete response. Copy every grounded free phrase "
            "as one verbatim contiguous substring from the field's allowed cited "
            "P/S evidence; do not paraphrase, combine fragments, or guess. Omit "
            "an operation when no legal phrase exists."
        ),
        ChangePlanValidationCategory.FIELD_CONTRACT: (
            "Previous generation violated the output field contract. "
            "Regenerate the complete valid response. All bounded fields "
            "must respect their declared maximum lengths and counts. "
            "Preserve valid evidence grounding and references."
        ),
    }
)

_TARGET_LOCATOR_REPAIR_ACTIONS = MappingProxyType(
    {
        TargetLocatorRepairRule.REORDER_HEADING_NOT_OBSERVED_ON_TARGET_PAGE: (
            "Regenerate the complete response. For PROPOSE_SECTION_REORDER, "
            "copy every ordered_headings value exactly from the sole page_refs "
            "page's provider_visible_headings. Python derives its page-level locator."
        ),
        TargetLocatorRepairRule.ADD_SECTION_PROPOSED_HEADING_COLLIDES: (
            "Regenerate the complete response. For ADD_SECTION, proposed_heading "
            "must describe the new section and must not equal any "
            "provider_visible_heading on the selected locator page. Keep "
            "locator_ref as the existing insertion context."
        ),
    }
)


CHANGE_OPERATION_COMPATIBILITY = MappingProxyType(
    {
        ContentOpportunityActionCode.EXPAND_PAGE_SECTION: frozenset(
            {ChangeOperationType.EXPAND_SECTION}
        ),
        ContentOpportunityActionCode.REORGANIZE_PAGE_SECTIONS: frozenset(
            {ChangeOperationType.PROPOSE_SECTION_REORDER}
        ),
        ContentOpportunityActionCode.CREATE_SUPPORTING_RESOURCE: frozenset(
            {ChangeOperationType.CREATE_NEW_RESOURCE}
        ),
        ContentOpportunityActionCode.ADD_BUYER_GUIDANCE: frozenset(
            {ChangeOperationType.ADD_SECTION, ChangeOperationType.CREATE_NEW_RESOURCE}
        ),
        ContentOpportunityActionCode.ADD_TECHNICAL_DOCUMENTATION: frozenset(
            {ChangeOperationType.ADD_SECTION, ChangeOperationType.CREATE_NEW_RESOURCE}
        ),
        ContentOpportunityActionCode.ADD_COMPARISON_TABLE: frozenset(
            {
                ChangeOperationType.ADD_COMPARISON_TABLE,
                ChangeOperationType.CREATE_NEW_RESOURCE,
            }
        ),
        ContentOpportunityActionCode.ADD_INTERNAL_LINK: frozenset(
            {ChangeOperationType.ADD_INTERNAL_LINK}
        ),
    }
)

NEW_RESOURCE_PURPOSE_BY_ACTION = MappingProxyType(
    {
        ContentOpportunityActionCode.CREATE_SUPPORTING_RESOURCE: NewResourcePurpose.SUPPORTING_RESOURCE,
        ContentOpportunityActionCode.ADD_BUYER_GUIDANCE: NewResourcePurpose.BUYER_GUIDANCE,
        ContentOpportunityActionCode.ADD_TECHNICAL_DOCUMENTATION: NewResourcePurpose.TECHNICAL_DOCUMENTATION,
        ContentOpportunityActionCode.ADD_COMPARISON_TABLE: NewResourcePurpose.COMPARISON_RESOURCE,
    }
)


def render_change_operation_compatibility() -> str:
    """Render the single shared action-to-operation compatibility contract."""

    lines = ["Allowed operation_type values by source_action_code:"]
    for action in ContentOpportunityActionCode:
        lines.append(f"{action.value}:")
        allowed = CHANGE_OPERATION_COMPATIBILITY[action]
        lines.extend(
            f"- {operation.value}"
            for operation in ChangeOperationType
            if operation in allowed
        )
    lines.extend(
        (
            "ADD_COMPARISON_TABLE may use CREATE_NEW_RESOURCE only with a nested comparison_table_brief.",
            "Do not select any combination outside this contract.",
        )
    )
    return "\n".join(lines)


def render_new_resource_purpose_compatibility() -> str:
    """Render the shared action-to-purpose contract for provider instructions."""

    lines = ["Required resource_purpose by source_action_code:"]
    lines.extend(
        f"{action.value}: {purpose.value}"
        for action, purpose in NEW_RESOURCE_PURPOSE_BY_ACTION.items()
    )
    return "\n".join(lines)


def render_change_plan_bounds() -> str:
    """Render provider-visible bounds from the authoritative Core constants."""

    return "\n".join(
        (
            "Shared bounded field contract:",
            f"- page_refs: {MIN_PAGE_REFS_PER_OPERATION} to {MAX_PAGE_REFS_PER_OPERATION}; "
            f"existing-page operations require at least {MIN_EXISTING_PAGE_REFS_PER_OPERATION} page_ref; "
            f"internal links require at least {MIN_INTERNAL_LINK_PAGE_REFS} page_refs.",
            f"- source_refs: {MIN_SOURCE_REFS_PER_OPERATION} to {MAX_SOURCE_REFS_PER_OPERATION}.",
            f"- content_points: {MIN_CONTENT_POINTS_PER_OPERATION} to {MAX_CONTENT_POINTS_PER_OPERATION}; "
            f"content point subject candidate: at most {MAX_CONTENT_POINT_SUBJECT_CHARS} characters; "
            f"at most {MAX_CONTENT_POINT_CANDIDATES_PER_EVIDENCE} candidates per evidence, "
            f"{MAX_CONTENT_POINT_CANDIDATES_PER_OPPORTUNITY} per opportunity, and "
            f"{MAX_CONTENT_POINT_CANDIDATES_GLOBAL} globally.",
            f"- proposed heading or title: at most {MAX_PROPOSED_HEADING_CHARS} characters.",
            f"- ordered_headings: {MIN_REORDER_HEADINGS} to {MAX_REORDER_HEADINGS}; "
            f"ordered heading: at most {MAX_PROPOSED_HEADING_CHARS} characters.",
            f"- outline_headings: {MIN_OUTLINE_HEADINGS} to {MAX_OUTLINE_HEADINGS}; "
            f"outline heading: at most {MAX_OUTLINE_HEADING_CHARS} characters.",
            f"- table columns: {MIN_TABLE_COLUMNS} to {MAX_TABLE_COLUMNS}; "
            f"table dimensions: {MIN_TABLE_DIMENSIONS} to {MAX_TABLE_DIMENSIONS}; "
            f"table label: at most {MAX_TABLE_LABEL_CHARS} characters.",
            f"- anchor_intent: at most {MAX_ANCHOR_INTENT_CHARS} characters.",
            f"- CREATE_NEW_RESOURCE page_bindings: {MIN_PAGE_REFS_PER_OPERATION} to "
            f"{MAX_PAGE_REFS_PER_OPERATION}; each page_ref is unique and "
            "suggested_source is boolean.",
            f"- locator candidates: at most {MAX_EXACT_LOCATOR_CANDIDATES_PER_PAGE} "
            "exact-heading candidates per page and "
            f"{MAX_LOCATOR_CANDIDATES_PER_OPPORTUNITY} total per opportunity; "
            "every authorized page retains its PAGE_LEVEL candidate.",
            f"- PROPOSE_SECTION_REORDER requires exactly {REORDER_PAGE_REFS} page_ref.",
        )
    )


class CustomerPlanningEvidence(Protocol):
    """Read-only attributed context; concrete shape is validated at admission."""
    def validate_input(self, packet: SiteContentPacket, opportunities: ContentOpportunityReport,
                       task_id: str | None) -> None: ...
    def payload(self) -> dict[str, object]: ...


@dataclass(frozen=True, slots=True)
class ChangePlanInput:
    site_content: SiteContentPacket
    opportunities: ContentOpportunityReport
    first_party_scope: FirstPartyPlanningScope | None = None
    task_id: str | None = None
    customer_context: CustomerPlanningEvidence | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.site_content, SiteContentPacket):
            raise TypeError("Change plan input requires SiteContentPacket.")
        if not isinstance(self.opportunities, ContentOpportunityReport):
            raise TypeError("Change plan input requires ContentOpportunityReport.")
        if self.opportunities.status is not ContentOpportunityStatus.SUCCESS:
            raise ValueError("Change plan input requires a successful opportunity report.")
        if self.customer_context is not None:
            from .evidence_intake import CustomerPlanningContext
            if (type(self.customer_context) is not CustomerPlanningContext
                    or self.first_party_scope is not None):
                raise ValueError("Customer planning context is invalid.")
            self.customer_context.validate_input(self.site_content, self.opportunities, self.task_id)


@dataclass(frozen=True, slots=True)
class ChangePlanPageEvidence:
    page: SiteContentEvidence

    @property
    def evidence_id(self) -> str:
        return self.page.evidence_id


@dataclass(frozen=True, slots=True)
class ChangePlanSourceEvidence:
    material: ContentOpportunitySourceMaterial

    @property
    def evidence_id(self) -> str:
        return self.material.source_id


@dataclass(frozen=True, slots=True)
class ChangePlanOpportunityEvidence:
    opportunity: ContentOpportunity

    @property
    def evidence_id(self) -> str:
        return self.opportunity.recommendation_id


@dataclass(frozen=True, slots=True)
class ContentPointCandidate:
    candidate_id: str
    text: str
    origin_ref: str

    def __post_init__(self) -> None:
        if (
            re.fullmatch(r"[PS][1-9][0-9]*\.CP_[0-9]{2}", self.candidate_id) is None
            or re.fullmatch(r"[PS][1-9][0-9]*", self.origin_ref) is None
            or not self.candidate_id.startswith(f"{self.origin_ref}.CP_")
            or not _is_bounded_text(self.text, MAX_CONTENT_POINT_SUBJECT_CHARS)
        ):
            raise ValueError("Content point candidate is invalid.")


@dataclass(frozen=True, slots=True)
class OpportunityContentPointCandidates:
    opportunity_ref: str
    candidates: tuple[ContentPointCandidate, ...]

    def __post_init__(self) -> None:
        if (
            re.fullmatch(r"R[1-9][0-9]*", self.opportunity_ref) is None
            or not isinstance(self.candidates, tuple)
            or len(self.candidates) > MAX_CONTENT_POINT_CANDIDATES_PER_OPPORTUNITY
            or not all(isinstance(item, ContentPointCandidate) for item in self.candidates)
            or len({item.candidate_id for item in self.candidates}) != len(self.candidates)
        ):
            raise ValueError("Opportunity content point candidates are invalid.")


@dataclass(frozen=True, slots=True)
class LocatorCandidate:
    candidate_id: str
    locator_kind: SectionLocatorKind
    page_ref: str
    target_heading: str | None

    def __post_init__(self) -> None:
        match = re.fullmatch(r"(P[1-9][0-9]*)\.LOC_([0-9]{2})", self.candidate_id)
        if (
            match is None
            or match.group(1) != self.page_ref
            or not isinstance(self.locator_kind, SectionLocatorKind)
            or self.locator_kind is SectionLocatorKind.NEW_PAGE
            or self.locator_kind is SectionLocatorKind.PAGE_LEVEL
            and (match.group(2) != "00" or self.target_heading is not None)
            or self.locator_kind is SectionLocatorKind.EXACT_OBSERVED_HEADING
            and (
                match.group(2) == "00"
                or not _is_bounded_text(
                    self.target_heading,
                    MAX_PROPOSED_HEADING_CHARS,
                )
            )
        ):
            raise ValueError("Locator candidate is invalid.")


@dataclass(frozen=True, slots=True)
class OpportunityLocatorCandidates:
    opportunity_ref: str
    candidates: tuple[LocatorCandidate, ...]

    def __post_init__(self) -> None:
        if (
            re.fullmatch(r"R[1-9][0-9]*", self.opportunity_ref) is None
            or not isinstance(self.candidates, tuple)
            or len(self.candidates) > MAX_LOCATOR_CANDIDATES_PER_OPPORTUNITY
            or not all(isinstance(item, LocatorCandidate) for item in self.candidates)
            or len({item.candidate_id for item in self.candidates})
            != len(self.candidates)
        ):
            raise ValueError("Opportunity locator candidates are invalid.")


@dataclass(frozen=True, slots=True)
class ProposedHeadingCandidate:
    candidate_id: str
    text: str
    page_ref: str
    source_ref: str

    def __post_init__(self) -> None:
        match = re.fullmatch(r"(P[1-9][0-9]*)\.PH_([0-9]{2})", self.candidate_id)
        if (
            match is None
            or match.group(1) != self.page_ref
            or re.fullmatch(r"S[1-9][0-9]*", self.source_ref) is None
            or not _is_bounded_text(self.text, MAX_PROPOSED_HEADING_CHARS)
        ):
            raise ValueError("Proposed heading candidate is invalid.")


@dataclass(frozen=True, slots=True)
class OpportunityProposedHeadingCandidates:
    opportunity_ref: str
    candidates: tuple[ProposedHeadingCandidate, ...]

    def __post_init__(self) -> None:
        page_counts: dict[str, int] = {}
        for candidate in self.candidates:
            if not isinstance(candidate, ProposedHeadingCandidate):
                raise ValueError("Opportunity proposed heading candidates are invalid.")
            page_counts[candidate.page_ref] = page_counts.get(candidate.page_ref, 0) + 1
        if (
            re.fullmatch(r"R[1-9][0-9]*", self.opportunity_ref) is None
            or not isinstance(self.candidates, tuple)
            or len(self.candidates) > MAX_PROPOSED_HEADING_CANDIDATES_PER_OPPORTUNITY
            or any(
                count > MAX_PROPOSED_HEADING_CANDIDATES_PER_PAGE
                for count in page_counts.values()
            )
            or len({item.candidate_id for item in self.candidates})
            != len(self.candidates)
        ):
            raise ValueError("Opportunity proposed heading candidates are invalid.")


@dataclass(frozen=True, slots=True)
class OutlineHeadingCandidate:
    candidate_id: str
    text: str
    source_ref: str

    def __post_init__(self) -> None:
        match = re.fullmatch(r"(S[1-9][0-9]*)\.OH_([0-9]{2})", self.candidate_id)
        if (
            match is None
            or match.group(1) != self.source_ref
            or not _is_bounded_text(self.text, MAX_OUTLINE_HEADING_CHARS)
        ):
            raise ValueError("Outline heading candidate is invalid.")


@dataclass(frozen=True, slots=True)
class OpportunityOutlineHeadingCandidates:
    opportunity_ref: str
    candidates: tuple[OutlineHeadingCandidate, ...]

    def __post_init__(self) -> None:
        if (
            re.fullmatch(r"R[1-9][0-9]*", self.opportunity_ref) is None
            or not isinstance(self.candidates, tuple)
            or len(self.candidates) > MAX_OUTLINE_HEADING_CANDIDATES_PER_OPPORTUNITY
            or not all(isinstance(item, OutlineHeadingCandidate) for item in self.candidates)
            or len({item.candidate_id for item in self.candidates})
            != len(self.candidates)
        ):
            raise ValueError("Opportunity outline heading candidates are invalid.")


@dataclass(frozen=True, slots=True)
class ChangePlanEvidenceCatalog:
    opportunities: tuple[ChangePlanOpportunityEvidence, ...]
    pages: tuple[ChangePlanPageEvidence, ...]
    sources: tuple[ChangePlanSourceEvidence, ...]
    site_content: SiteContentPacket | None = None

    def __post_init__(self) -> None:
        groups = (
            (self.opportunities, ChangePlanOpportunityEvidence),
            (self.pages, ChangePlanPageEvidence),
            (self.sources, ChangePlanSourceEvidence),
        )
        for values, expected in groups:
            if not isinstance(values, tuple) or not all(
                isinstance(item, expected) for item in values
            ):
                raise ValueError("Change plan evidence catalog is invalid.")
            identifiers = tuple(item.evidence_id for item in values)
            if len(identifiers) != len(set(identifiers)):
                raise ValueError("Change plan evidence identifiers must be unique.")

    def opportunity_by_id(self) -> dict[str, ContentOpportunity]:
        return {item.evidence_id: item.opportunity for item in self.opportunities}

    def page_by_id(self) -> dict[str, SiteContentEvidence]:
        return {item.evidence_id: item.page for item in self.pages}

    def source_by_id(self) -> dict[str, ContentOpportunitySourceMaterial]:
        return {item.evidence_id: item.material for item in self.sources}


@dataclass(frozen=True, slots=True)
class ChangePlanPrompt:
    input: ChangePlanInput
    catalog: ChangePlanEvidenceCatalog
    content_point_candidate_sets: tuple[OpportunityContentPointCandidates, ...]
    locator_candidate_sets: tuple[OpportunityLocatorCandidates, ...]
    proposed_heading_candidate_sets: tuple[OpportunityProposedHeadingCandidates, ...]
    outline_heading_candidate_sets: tuple[OpportunityOutlineHeadingCandidates, ...]
    repair_category: ChangePlanValidationCategory | None = None
    field_contract_violation: FieldContractViolation | None = None
    locator_repair_rule: TargetLocatorRepairRule | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.input, ChangePlanInput)
            or not isinstance(self.catalog, ChangePlanEvidenceCatalog)
            or not isinstance(self.content_point_candidate_sets, tuple)
            or not all(
                isinstance(item, OpportunityContentPointCandidates)
                for item in self.content_point_candidate_sets
            )
            or tuple(
                item.opportunity_ref for item in self.content_point_candidate_sets
            )
            != tuple(item.evidence_id for item in self.catalog.opportunities)
            or not isinstance(self.locator_candidate_sets, tuple)
            or not all(
                isinstance(item, OpportunityLocatorCandidates)
                for item in self.locator_candidate_sets
            )
            or tuple(item.opportunity_ref for item in self.locator_candidate_sets)
            != tuple(item.evidence_id for item in self.catalog.opportunities)
            or not isinstance(self.proposed_heading_candidate_sets, tuple)
            or not all(
                isinstance(item, OpportunityProposedHeadingCandidates)
                for item in self.proposed_heading_candidate_sets
            )
            or tuple(
                item.opportunity_ref for item in self.proposed_heading_candidate_sets
            )
            != tuple(item.evidence_id for item in self.catalog.opportunities)
            or not isinstance(self.outline_heading_candidate_sets, tuple)
            or not all(
                isinstance(item, OpportunityOutlineHeadingCandidates)
                for item in self.outline_heading_candidate_sets
            )
            or tuple(
                item.opportunity_ref for item in self.outline_heading_candidate_sets
            )
            != tuple(item.evidence_id for item in self.catalog.opportunities)
            or sum(
                len(item.candidates) for item in self.content_point_candidate_sets
            )
            > MAX_CONTENT_POINT_CANDIDATES_GLOBAL
            or self.repair_category is not None
            and self.repair_category not in CHANGE_PLAN_REPAIR_CATEGORIES
            or self.field_contract_violation is not None
            and (
                self.repair_category is not ChangePlanValidationCategory.FIELD_CONTRACT
                or not isinstance(
                    self.field_contract_violation,
                    FieldContractViolation,
                )
                or self.field_contract_violation.repair_class
                is not FieldContractRepairClass.TYPE_B
            )
            or self.repair_category is ChangePlanValidationCategory.FIELD_CONTRACT
            and self.field_contract_violation is None
            or self.locator_repair_rule is not None
            and (
                self.repair_category
                is not ChangePlanValidationCategory.TARGET_LOCATOR_INVALID
                or not isinstance(
                    self.locator_repair_rule,
                    TargetLocatorRepairRule,
                )
            )
            or self.repair_category
            is ChangePlanValidationCategory.TARGET_LOCATOR_INVALID
            and self.locator_repair_rule is None
        ):
            raise ValueError("Change plan prompt is invalid.")

    def content_point_candidates_for(
        self, opportunity_ref: str
    ) -> tuple[ContentPointCandidate, ...]:
        return next(
            (
                item.candidates
                for item in self.content_point_candidate_sets
                if item.opportunity_ref == opportunity_ref
            ),
            (),
        )

    def content_point_candidate(
        self, opportunity_ref: str, candidate_id: str
    ) -> ContentPointCandidate | None:
        return next(
            (
                item
                for item in self.content_point_candidates_for(opportunity_ref)
                if item.candidate_id == candidate_id
            ),
            None,
        )

    def has_content_point_candidate_id(self, candidate_id: str) -> bool:
        return any(
            item.candidate_id == candidate_id
            for candidate_set in self.content_point_candidate_sets
            for item in candidate_set.candidates
        )

    def locator_candidates_for(
        self, opportunity_ref: str
    ) -> tuple[LocatorCandidate, ...]:
        return next(
            (
                item.candidates
                for item in self.locator_candidate_sets
                if item.opportunity_ref == opportunity_ref
            ),
            (),
        )

    def locator_candidate(
        self, opportunity_ref: str, candidate_id: str
    ) -> LocatorCandidate | None:
        return next(
            (
                item
                for item in self.locator_candidates_for(opportunity_ref)
                if item.candidate_id == candidate_id
            ),
            None,
        )

    def has_locator_candidate_id(self, candidate_id: str) -> bool:
        return any(
            item.candidate_id == candidate_id
            for candidate_set in self.locator_candidate_sets
            for item in candidate_set.candidates
        )

    def proposed_heading_candidates_for(
        self, opportunity_ref: str
    ) -> tuple[ProposedHeadingCandidate, ...]:
        return next(
            (
                item.candidates
                for item in self.proposed_heading_candidate_sets
                if item.opportunity_ref == opportunity_ref
            ),
            (),
        )

    def proposed_heading_candidate(
        self, opportunity_ref: str, candidate_id: str
    ) -> ProposedHeadingCandidate | None:
        return next(
            (
                item
                for item in self.proposed_heading_candidates_for(opportunity_ref)
                if item.candidate_id == candidate_id
            ),
            None,
        )

    def has_proposed_heading_candidate_id(self, candidate_id: str) -> bool:
        return any(
            item.candidate_id == candidate_id
            for candidate_set in self.proposed_heading_candidate_sets
            for item in candidate_set.candidates
        )

    def outline_heading_candidates_for(
        self, opportunity_ref: str
    ) -> tuple[OutlineHeadingCandidate, ...]:
        return next(
            (
                item.candidates
                for item in self.outline_heading_candidate_sets
                if item.opportunity_ref == opportunity_ref
            ),
            (),
        )

    def deterministic_outline_headings_for(
        self, opportunity_ref: str
    ) -> tuple[str, ...]:
        return tuple(
            item.text
            for item in self.outline_heading_candidates_for(opportunity_ref)[
                :MIN_OUTLINE_HEADINGS
            ]
        )

    def allowed_operation_types_for(
        self, opportunity_ref: str
    ) -> tuple[ChangeOperationType, ...]:
        return _derive_allowed_operation_types(self, opportunity_ref)

    def material_json(self) -> str:
        """Serialize only bounded P/S/R evidence and the evidence-use contract."""

        return json.dumps(
            self._material_payload(), ensure_ascii=False, separators=(",", ":"),
            sort_keys=True,
        )

    def _material_payload(self) -> dict[str, object]:
        payload = {
            "contract": {
                "first_party_planning": (
                    {"mode": "PLANNING_ONLY", "task_id": self.input.task_id,
                     "task_kind": "ATTRIBUTED_EXCERPT", "draft_admission": False,
                     "max_content_points": MAX_FIRST_PARTY_EXCERPTS,
                     "max_operations": 1,
                     "required_quotes": self.input.first_party_scope.quotes,
                     "allowed_intents": ["DESCRIBE", "SUMMARIZE"], "source_refs": []}
                    if self.input.first_party_scope is not None else None
                ),
                "evidence_scope": SiteContentEvidenceScope.OBSERVED_PRESENT_ONLY.value,
                "supports_absence_claims": False,
                "requires_human_review": True,
                "semantic_locators_only": True,
                "grounded_fields": {
                    "content_points[].subject_ref": {
                        "allowed_values": "enclosing_R_content_point_candidates",
                        "origin_must_be_cited_by_operation": True,
                        "materialized_field": "subject",
                        "free_text_subject_allowed": False,
                    },
                    "column_headers[]": {
                        "allowed_evidence": "operation_cited_P_or_S",
                        "match": "verbatim_contiguous_substring",
                        "paraphrase_allowed": False,
                        "omit_item_if_unavailable": True,
                    },
                    "row_dimensions[]": {
                        "allowed_evidence": "operation_cited_P_or_S",
                        "match": "verbatim_contiguous_substring",
                        "paraphrase_allowed": False,
                        "omit_item_if_unavailable": True,
                    },
                    "anchor_intent": {
                        "allowed_evidence": "operation_cited_P_or_S",
                        "match": "verbatim_contiguous_substring",
                        "paraphrase_allowed": False,
                        "omit_item_if_unavailable": True,
                    },
                    "proposed_heading_ref": {
                        "allowed_values": "enclosing_R_proposed_heading_candidates",
                        "candidate_page_must_match_locator_page": True,
                        "candidate_source_must_be_cited_by_operation": True,
                        "materialized_field": "proposed_heading",
                        "free_text_proposed_heading_allowed_for_add_section": False,
                    },
                    "proposed_title": {
                        "allowed_evidence": "cited_S_title_or_content",
                        "match": "verbatim_contiguous_substring",
                        "paraphrase_allowed": False,
                        "omit_item_if_unavailable": True,
                    },
                },
                "retry_feedback": (
                    self.field_contract_violation.retry_feedback()
                    if self.field_contract_violation is not None
                    else {
                        "validator": self.repair_category.value,
                        "locator_rule": self.locator_repair_rule.value,
                        "required_action": _TARGET_LOCATOR_REPAIR_ACTIONS[
                            self.locator_repair_rule
                        ],
                    }
                    if self.locator_repair_rule is not None
                    else {
                        "validator": self.repair_category.value,
                        "required_action": _CHANGE_PLAN_REPAIR_ACTIONS[
                            self.repair_category
                        ],
                    }
                    if self.repair_category is not None
                    else None
                ),
            },
            "opportunities": [
                {
                    "opportunity_ref": item.opportunity.recommendation_id,
                    "topic": item.opportunity.topic,
                    "action_codes": tuple(
                        action.value for action in item.opportunity.action_codes
                    ),
                    "page_refs": item.opportunity.page_refs,
                    "source_refs": item.opportunity.source_refs,
                    "audit_refs": item.opportunity.audit_refs,
                    "allowed_operation_types": tuple(
                        operation_type.value
                        for operation_type in self.allowed_operation_types_for(
                            item.opportunity.recommendation_id
                        )
                    ),
                    "content_point_candidates": [
                        {
                            "id": candidate.candidate_id,
                            "text": candidate.text,
                            "origin": candidate.origin_ref,
                        }
                        for candidate in self.content_point_candidates_for(
                            item.opportunity.recommendation_id
                        )
                    ],
                    "locator_candidates": [
                        {
                            "id": candidate.candidate_id,
                            "locator_kind": candidate.locator_kind.value,
                            "page_ref": candidate.page_ref,
                            "target_heading": candidate.target_heading,
                        }
                        for candidate in self.locator_candidates_for(
                            item.opportunity.recommendation_id
                        )
                    ],
                    "proposed_heading_candidates": [
                        {
                            "id": candidate.candidate_id,
                            "text": candidate.text,
                            "page_ref": candidate.page_ref,
                            "source_ref": candidate.source_ref,
                        }
                        for candidate in self.proposed_heading_candidates_for(
                            item.opportunity.recommendation_id
                        )
                    ],
                }
                for item in self.catalog.opportunities
                if not _comparison_only_opportunity(item.opportunity)
            ],
            "unavailable_opportunities": [
                {
                    "opportunity_ref": item.opportunity.recommendation_id,
                    "reason": ChangePlanValidationCategory.COMPARISON_UNAVAILABLE.value,
                }
                for item in self.catalog.opportunities
                if _comparison_only_opportunity(item.opportunity)
            ],
            "pages": [_page_prompt_payload(item.page) for item in self.catalog.pages],
            "sources": [
                {
                    "source_ref": item.material.source_id,
                    "title": item.material.title,
                    "content": item.material.content,
                    "content_truncated": item.material.content_truncated,
                }
                for item in self.catalog.sources
            ],
        }
        if self.input.customer_context is not None:
            payload["customer_evidence_intake"] = self.input.customer_context.payload()
        return payload


@dataclass(frozen=True, slots=True)
class _OperationPrerequisites:
    content_points: int = 0
    proposed_headings: int = 0
    outline_headings: int = 0
    locators: int = 0
    pages: int = MIN_EXISTING_PAGE_REFS_PER_OPERATION
    sources: int = MIN_SOURCE_REFS_PER_OPERATION


# Transient references and structural minima from the operation contracts.
# Free-text grounding remains the responsibility of the existing validators.
_OPERATION_PREREQUISITES = MappingProxyType({
    ChangeOperationType.EXPAND_SECTION: _OperationPrerequisites(
        content_points=MIN_CONTENT_POINTS_PER_OPERATION, locators=1,
    ),
    ChangeOperationType.PROPOSE_SECTION_REORDER: _OperationPrerequisites(),
    ChangeOperationType.ADD_SECTION: _OperationPrerequisites(
        content_points=MIN_CONTENT_POINTS_PER_OPERATION, proposed_headings=1, locators=1,
    ),
    ChangeOperationType.ADD_COMPARISON_TABLE: _OperationPrerequisites(locators=1),
    ChangeOperationType.ADD_INTERNAL_LINK: _OperationPrerequisites(pages=MIN_INTERNAL_LINK_PAGE_REFS),
    ChangeOperationType.CREATE_NEW_RESOURCE: _OperationPrerequisites(
        content_points=MIN_CONTENT_POINTS_PER_OPERATION,
        outline_headings=MIN_OUTLINE_HEADINGS, pages=MIN_PAGE_REFS_PER_OPERATION,
    ),
})


def _derive_allowed_operation_types(
    prompt: ChangePlanPrompt, opportunity_ref: str,
) -> tuple[ChangeOperationType, ...]:
    """Derive availability only from the final catalogs serialized for Python/provider use."""

    opportunity = prompt.catalog.opportunity_by_id().get(opportunity_ref)
    if opportunity is None:
        return ()
    pages = prompt.catalog.page_by_id()
    sources = prompt.catalog.source_by_id()
    page_refs = tuple(ref for ref in opportunity.page_refs if ref in pages)
    source_refs = tuple(ref for ref in opportunity.source_refs if ref in sources)
    points = tuple(
        item for item in prompt.content_point_candidates_for(opportunity_ref)
        if item.origin_ref in (*page_refs, *source_refs)
    )
    locators = tuple(
        item for item in prompt.locator_candidates_for(opportunity_ref)
        if item.page_ref in page_refs
        and (item.locator_kind is SectionLocatorKind.PAGE_LEVEL
             or item.target_heading in provider_visible_headings(pages[item.page_ref]))
    )
    headings = tuple(
        item for item in prompt.proposed_heading_candidates_for(opportunity_ref)
        if item.source_ref in source_refs
        and any(locator.page_ref == item.page_ref for locator in locators)
    )
    # Python always selects the first two outlines, so do not substitute later ones.
    outlines = prompt.outline_heading_candidates_for(opportunity_ref)[:MIN_OUTLINE_HEADINGS]
    compatible = {
        operation for action in opportunity.action_codes
        if action is not ContentOpportunityActionCode.ADD_COMPARISON_TABLE
        for operation in CHANGE_OPERATION_COMPATIBILITY[action]
    }
    result = []
    for operation in ChangeOperationType:
        if operation not in compatible:
            continue
        required = _OPERATION_PREREQUISITES[operation]
        p_only = (
            operation is ChangeOperationType.EXPAND_SECTION
            and _first_party_plan_scope_matches(prompt.input, opportunity)
        )
        if p_only and (
            tuple(point.text for point in points) != prompt.input.first_party_scope.quotes
            or not any(locator.locator_kind is SectionLocatorKind.EXACT_OBSERVED_HEADING
                       and locator.target_heading == prompt.input.first_party_scope.heading
                       and locator.page_ref == prompt.input.first_party_scope.page_ref for locator in locators)
        ):
            continue
        if (
            len(points) < required.content_points
            or len(headings) < required.proposed_headings
            or len(outlines) < required.outline_headings
            or required.outline_headings and any(item.source_ref not in source_refs for item in outlines)
            or len(locators) < required.locators
            or len(page_refs) < required.pages
            or len(source_refs) < (0 if p_only else required.sources)
        ):
            continue
        if operation is ChangeOperationType.PROPOSE_SECTION_REORDER and not any(
            sum(_is_bounded_text(heading, MAX_PROPOSED_HEADING_CHARS)
                for heading in provider_visible_headings(pages[ref])) >= MIN_REORDER_HEADINGS
            for ref in page_refs
        ):
            continue
        if operation is ChangeOperationType.ADD_INTERNAL_LINK and not any(
            canonical_url_origin(pages[left].final_url) is not None
            and canonical_url_origin(pages[left].final_url) == canonical_url_origin(pages[right].final_url)
            for index, left in enumerate(page_refs) for right in page_refs[index + 1:]
        ):
            continue
        result.append(operation)
    return tuple(result)


def _comparison_only_opportunity(opportunity: ContentOpportunity) -> bool:
    """V1 has no trusted comparison proof; defer only comparison-only R inputs."""

    return opportunity.action_codes == (ContentOpportunityActionCode.ADD_COMPARISON_TABLE,)


def validate_provider_generation_material(
    prompt: ChangePlanPrompt, material_json: str,
) -> str | None:
    """Fail closed on empty generation sets or a rendered contract/catalog mismatch."""

    try:
        material = json.loads(material_json)
        # Check the actual HTTP material, including catalogs and evidence, against
        # the authoritative final state; never trust a stale rendered allowlist.
        if material != json.loads(json.dumps(prompt._material_payload())):
            return ChangePlanValidationCategory.FIELD_CONTRACT.value
        opportunities = material["opportunities"]
        if not opportunities and prompt.catalog.opportunities:
            return ChangePlanValidationCategory.COMPARISON_UNAVAILABLE.value
        for item in opportunities:
            allowed = _derive_allowed_operation_types(prompt, item["opportunity_ref"])
            if not allowed or item["allowed_operation_types"] != [op.value for op in allowed]:
                return ChangePlanValidationCategory.FIELD_CONTRACT.value
    except (AttributeError, KeyError, TypeError, ValueError):
        return ChangePlanValidationCategory.FIELD_CONTRACT.value
    return None


def _page_prompt_payload(page: SiteContentEvidence) -> dict[str, object]:
    visible_headings = provider_visible_headings(page)
    return {
        "page_ref": page.evidence_id,
        "title": page.title,
        "description": page.description,
        "h1": page.h1,
        "h2": page.h2,
        "provider_visible_headings": visible_headings,
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


def build_change_plan_prompt(value: ChangePlanInput) -> ChangePlanPrompt:
    """Cross-reference the stable inputs and build the shared R/P/S catalog."""

    opportunity_items = value.opportunities.opportunities
    pages = tuple(
        ChangePlanPageEvidence(page)
        for page in value.site_content.pages
    )
    sources = tuple(
        ChangePlanSourceEvidence(material)
        for material in value.opportunities.source_materials
    )
    catalog = ChangePlanEvidenceCatalog(
        site_content=value.site_content,
        opportunities=tuple(
            ChangePlanOpportunityEvidence(item) for item in opportunity_items
        ),
        pages=pages,
        sources=sources,
    )
    prompt = ChangePlanPrompt(
        input=value,
        catalog=catalog,
        content_point_candidate_sets=_build_content_point_candidate_sets(catalog),
        locator_candidate_sets=_build_locator_candidate_sets(catalog),
        proposed_heading_candidate_sets=_build_proposed_heading_candidate_sets(catalog),
        outline_heading_candidate_sets=_build_outline_heading_candidate_sets(catalog),
    )
    scope = value.first_party_scope
    if scope is not None:
        if validate_change_plan_input(value) is not None:
            raise ValueError("First-party planning input binding is invalid.")
        # An excerpt scope cannot silently become a broader topic brief. Keep
        # the exact task excerpts in the final provider-visible candidate pool.
        prompt = replace(prompt, content_point_candidate_sets=(
            OpportunityContentPointCandidates("R1", tuple(
                ContentPointCandidate(f"{scope.page_ref}.CP_{index:02d}", quote, scope.page_ref)
                for index, quote in enumerate(scope.quotes, 1)
            )),
        ), locator_candidate_sets=(
            OpportunityLocatorCandidates("R1", tuple(
                candidate for candidate in prompt.locator_candidates_for("R1")
                if candidate.locator_kind is SectionLocatorKind.EXACT_OBSERVED_HEADING
                and candidate.page_ref == scope.page_ref and candidate.target_heading == scope.heading
            )),
        ))
    target_chars = MAX_USER_MATERIAL_CHARS - CONTENT_POINT_CANDIDATE_REPAIR_RESERVE_CHARS
    target_bytes = MAX_USER_MATERIAL_BYTES - CONTENT_POINT_CANDIDATE_REPAIR_RESERVE_BYTES
    initial_allowed = {
        item.evidence_id: prompt.allowed_operation_types_for(item.evidence_id)
        for item in catalog.opportunities
    }
    # Preserve each executable operation's minimum before sacrificing coverage.
    # Page-level locators and Python's deterministic outline pool are retained.
    stages = (
        ("content_point_candidate_sets", "content_points", True),
        ("locator_candidate_sets", "locators", False),
        ("proposed_heading_candidate_sets", "proposed_headings", True),
        ("content_point_candidate_sets", "content_points", False),
        ("proposed_heading_candidate_sets", "proposed_headings", False),
    )
    for field, prerequisite, preserve_minimum in stages:
        while True:
            material = prompt.material_json()
            if len(material) <= target_chars and len(material.encode("utf-8")) <= target_bytes:
                return prompt
            reduced = list(getattr(prompt, field))
            removable: list[tuple[int, int, int]] = []
            for index, item in enumerate(reduced):
                floor = max((
                    getattr(_OPERATION_PREREQUISITES[operation], prerequisite)
                    for operation in initial_allowed[item.opportunity_ref]
                ), default=0) if preserve_minimum else 0
                indexes = tuple(
                    candidate_index for candidate_index, candidate in enumerate(item.candidates)
                    if field != "locator_candidate_sets"
                    or candidate.locator_kind is SectionLocatorKind.EXACT_OBSERVED_HEADING
                )
                if len(indexes) > floor:
                    removable.append((len(indexes) - floor, index, indexes[-1]))
            if not removable:
                break
            _, index, remove_index = max(removable)
            item = reduced[index]
            reduced[index] = replace(item, candidates=(
                item.candidates[:remove_index] + item.candidates[remove_index + 1:]
            ))
            prompt = replace(prompt, **{field: tuple(reduced)})
    return prompt


def stable_change_plan_input_shape_error(
    site_content: SiteContentPacket,
    opportunity_report: ContentOpportunityReport,
) -> str | None:
    """Check runtime container shapes before any stable input is consumed."""

    pages = site_content.pages
    opportunities = opportunity_report.opportunities
    report_pages = opportunity_report.pages
    sources = opportunity_report.sources
    materials = opportunity_report.source_materials
    audit_evidence = opportunity_report.audit_evidence
    limitations = opportunity_report.limitations
    if (
        not isinstance(pages, tuple)
        or not all(isinstance(page, SiteContentEvidence) for page in pages)
        or not isinstance(opportunities, tuple)
        or not all(isinstance(item, ContentOpportunity) for item in opportunities)
        or not isinstance(report_pages, tuple)
        or not all(isinstance(page, ContentOpportunityPage) for page in report_pages)
        or not isinstance(sources, tuple)
        or not all(isinstance(source, ContentOpportunitySource) for source in sources)
        or not isinstance(materials, tuple)
        or not all(
            isinstance(material, ContentOpportunitySourceMaterial)
            for material in materials
        )
        or not isinstance(audit_evidence, tuple)
        or not all(
            isinstance(item, NumberedAuditEvidence) for item in audit_evidence
        )
        or not isinstance(limitations, tuple)
        or not all(type(item) is str for item in limitations)
    ):
        return ChangePlanValidationCategory.FIELD_CONTRACT.value
    if any(
        not isinstance(page.h1, tuple)
        or not all(type(heading) is str for heading in page.h1)
        or not isinstance(page.h2, tuple)
        or not all(type(heading) is str for heading in page.h2)
        or not isinstance(page.structured_content, tuple)
        or not all(
            isinstance(block, StructuredContentBlock)
            for block in page.structured_content
        )
        for page in pages
    ):
        return ChangePlanValidationCategory.FIELD_CONTRACT.value
    if any(
        not isinstance(block.kind, StructuredContentKind)
        or block.heading is not None
        and type(block.heading) is not str
        or block.text is not None
        and type(block.text) is not str
        or not isinstance(block.rows, tuple)
        or not all(
            isinstance(row, tuple) and all(type(cell) is str for cell in row)
            for row in block.rows
        )
        or not isinstance(block.pairs, tuple)
        or not all(
            isinstance(pair, tuple)
            and len(pair) == 2
            and all(type(value) is str for value in pair)
            for pair in block.pairs
        )
        or not isinstance(block.items, tuple)
        or not all(type(item) is str for item in block.items)
        for page in pages
        for block in page.structured_content
    ):
        return ChangePlanValidationCategory.FIELD_CONTRACT.value
    if any(
        not isinstance(item.actions, tuple)
        or not all(type(action) is str for action in item.actions)
        or not isinstance(item.action_codes, tuple)
        or not all(
            isinstance(action, ContentOpportunityActionCode)
            for action in item.action_codes
        )
        or not isinstance(item.page_refs, tuple)
        or not all(type(reference) is str for reference in item.page_refs)
        or not isinstance(item.source_refs, tuple)
        or not all(type(reference) is str for reference in item.source_refs)
        or not isinstance(item.audit_refs, tuple)
        or not all(type(reference) is str for reference in item.audit_refs)
        for item in opportunities
    ):
        return ChangePlanValidationCategory.FIELD_CONTRACT.value
    if any(
        not isinstance(source.classifications, tuple)
        or not all(
            isinstance(item, ResearchEvidenceClassification)
            for item in source.classifications
        )
        for source in sources
    ):
        return ChangePlanValidationCategory.FIELD_CONTRACT.value
    return None


def validate_change_plan_input(value: ChangePlanInput) -> str | None:
    """Revalidate stable R/P/S semantics before any provider call."""

    packet = value.site_content
    report = value.opportunities
    if value.customer_context is not None:
        from .evidence_intake import CustomerPlanningContext
        try:
            if type(value.customer_context) is not CustomerPlanningContext or value.first_party_scope is not None:
                return ChangePlanValidationCategory.FIELD_CONTRACT.value
            value.customer_context.validate_input(packet, report, value.task_id)
        except (AttributeError, TypeError, ValueError):
            return ChangePlanValidationCategory.FIELD_CONTRACT.value
    if value.first_party_scope is not None and (
        not isinstance(value.first_party_scope, FirstPartyPlanningScope)
        or not value.first_party_scope.matches_task(value.task_id)
        or not value.first_party_scope.matches_packet(packet)
        or len(report.opportunities) != 1
    ):
        return ChangePlanValidationCategory.EVIDENCE_USE_NOT_ALLOWED.value
    shape_error = stable_change_plan_input_shape_error(packet, report)
    if shape_error is not None:
        return shape_error
    limits = SiteContentPacketLimits()
    pages = packet.pages
    if (
        len(pages) > min(MAX_SITE_PAGES, limits.max_pages)
        or len(report.opportunities) > MAX_INPUT_OPPORTUNITIES
        or packet.evidence_scope is not SiteContentEvidenceScope.OBSERVED_PRESENT_ONLY
        or packet.supports_absence_claims is not False
        or type(packet.source_page_count) is not int
        or packet.source_page_count < len(pages)
        or type(packet.crawl_budget_exhausted) is not bool
        or type(packet.truncated) is not bool
        or report.limitations != CONTENT_OPPORTUNITY_LIMITATIONS
        or report.error is not None
        or not report.requires_human_review
    ):
        return ChangePlanValidationCategory.FIELD_CONTRACT.value
    page_ids_sequence = tuple(page.evidence_id for page in pages)
    if (
        len(page_ids_sequence) != len(set(page_ids_sequence))
        or any(not _is_page_ref(identifier) for identifier in page_ids_sequence)
    ):
        return ChangePlanValidationCategory.FIELD_CONTRACT.value
    origins: list[UrlOrigin] = []
    for page in pages:
        origin = canonical_url_origin(page.final_url)
        if origin is None or not _page_within_stable_limits(page, limits):
            return ChangePlanValidationCategory.FIELD_CONTRACT.value
        origins.append(origin)
    if origins and any(origin != origins[0] for origin in origins[1:]):
        return ChangePlanValidationCategory.FIELD_CONTRACT.value
    total_site_content = sum(
        len(page.body_text or "")
        + sum(_structured_block_chars(block) for block in page.structured_content)
        for page in pages
    )
    total_table_content = sum(
        sum(len(cell) for row in block.rows for cell in row)
        for page in pages
        for block in page.structured_content
        if block.kind is StructuredContentKind.TABLE
    )
    if (
        total_site_content > limits.max_site_content_chars
        or total_table_content > limits.max_site_table_chars
    ):
        return ChangePlanValidationCategory.FIELD_CONTRACT.value
    try:
        serialized_packet = packet.to_json()
    except (AttributeError, TypeError, ValueError):
        return ChangePlanValidationCategory.FIELD_CONTRACT.value
    if (
        len(serialized_packet) > min(MAX_SITE_PACKET_CHARS, limits.max_serialized_chars)
        or len(serialized_packet.encode("utf-8"))
        > min(MAX_SITE_PACKET_BYTES, limits.max_serialized_bytes)
    ):
        return ChangePlanValidationCategory.FIELD_CONTRACT.value

    materials = report.source_materials
    if not isinstance(materials, tuple) or len(materials) > MAX_RESEARCH_SOURCES:
        return ChangePlanValidationCategory.FIELD_CONTRACT.value
    source_ids_sequence = tuple(material.source_id for material in materials)
    if (
        len(source_ids_sequence) != len(set(source_ids_sequence))
        or any(re.fullmatch(r"S[1-9][0-9]*", identifier) is None for identifier in source_ids_sequence)
        or sum(len(material.content) for material in materials)
        > MAX_TOTAL_SOURCE_CONTENT_CHARS
        or any(
            not _stable_source_material_is_valid(material)
            for material in materials
        )
        or not _stable_display_sources_match(report, materials)
    ):
        return ChangePlanValidationCategory.FIELD_CONTRACT.value
    source_packet = json.dumps(
        {
            "classifications": (
                ResearchEvidenceClassification.EXTERNAL_RESEARCH_CONTEXT.value,
                ResearchEvidenceClassification.UNVERIFIED_SEARCH_RESULT.value,
            ),
            "sources": [
                {
                    "source_id": material.source_id,
                    "title": material.title,
                    "content": material.content,
                    "content_truncated": material.content_truncated,
                }
                for material in materials
            ],
            "selection_truncated": report.research_sources_truncated,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    if (
        len(source_packet) > MAX_SOURCE_PACKET_CHARS
        or len(source_packet.encode("utf-8")) > MAX_SOURCE_PACKET_BYTES
    ):
        return ChangePlanValidationCategory.FIELD_CONTRACT.value

    page_ids = set(page_ids_sequence)
    source_ids = set(source_ids_sequence)
    catalog = build_content_opportunity_evidence_catalog(
        packet, materials, report.audit_evidence
    )
    if not isinstance(report.opportunities, tuple) or not all(
        isinstance(item, ContentOpportunity) for item in report.opportunities
    ):
        return ChangePlanValidationCategory.FIELD_CONTRACT.value
    seen: set[str] = set()
    for expected_number, item in enumerate(
        report.opportunities, start=1
    ):
        if (
            item.recommendation_id != f"R{expected_number}"
            or item.recommendation_id in seen
        ):
            return ChangePlanValidationCategory.FIELD_CONTRACT.value
        seen.add(item.recommendation_id)
        if not item.action_codes:
            return ChangePlanValidationCategory.OPERATION_NOT_ALLOWED.value
        if any(reference not in page_ids for reference in item.page_refs):
            return ChangePlanValidationCategory.UNKNOWN_PAGE_REFERENCE.value
        if any(reference not in source_ids for reference in item.source_refs):
            return ChangePlanValidationCategory.UNKNOWN_SOURCE_REFERENCE.value
        audit_ids = {evidence.evidence_id for evidence in report.audit_evidence}
        if any(reference not in audit_ids for reference in item.audit_refs):
            return ChangePlanValidationCategory.FIELD_CONTRACT.value
        if finalized_content_opportunity_error(
            item,
            expected_number,
            catalog,
            materials,
            first_party_scope=value.first_party_scope,
            task_id=value.task_id,
        ) is not None:
            return ChangePlanValidationCategory.FIELD_CONTRACT.value
    return None


def _first_party_plan_scope_matches(value: ChangePlanInput, opportunity: ContentOpportunity) -> bool:
    scope = value.first_party_scope
    return (
        isinstance(scope, FirstPartyPlanningScope)
        and scope.matches_task(value.task_id) and scope.matches_packet(value.site_content)
        and opportunity.recommendation_id == "R1"
        and opportunity.opportunity_type is ContentOpportunityType.EXPAND_OBSERVED_CONTENT
        and opportunity.action_codes == (ContentOpportunityActionCode.EXPAND_PAGE_SECTION,)
        and opportunity.topic == scope.heading and opportunity.page_refs == (scope.page_ref,)
        and not opportunity.source_refs and not opportunity.audit_refs
    )


def canonical_url_origin(url: object) -> UrlOrigin | None:
    """Return a normalized HTTP(S) origin using the shared safe URL parser."""

    parsed = parse_safe_http_url(
        url,
        max_chars=MAX_CONTENT_OPPORTUNITY_SOURCE_URL_CHARS,
    )
    if parsed is None:
        return None
    port = parsed.port
    if port is None:
        port = 80 if parsed.scheme.casefold() == "http" else 443
    try:
        return UrlOrigin(parsed.scheme, parsed.hostname or "", port)
    except ValueError:
        return None


def _page_within_stable_limits(
    page: SiteContentEvidence,
    limits: SiteContentPacketLimits,
) -> bool:
    return (
        isinstance(page, SiteContentEvidence)
        and (
            page.title is None
            or type(page.title) is str
            and page.title == " ".join(page.title.split())
            and bool(page.title)
            and len(page.title) <= limits.max_title_chars
        )
        and (
            page.description is None
            or type(page.description) is str
            and page.description == " ".join(page.description.split())
            and bool(page.description)
            and len(page.description) <= limits.max_description_chars
        )
        and len(page.h1) <= limits.max_headings_per_level
        and len(page.h2) <= limits.max_headings_per_level
        and all(
            type(heading) is str and 0 < len(heading) <= limits.max_heading_chars
            and heading == " ".join(heading.split())
            for heading in (*page.h1, *page.h2)
        )
        and (
            page.body_text is None
            or type(page.body_text) is str
            and page.body_text == " ".join(page.body_text.split())
            and bool(page.body_text)
            and len(page.body_text) <= limits.max_body_chars_per_page
        )
        and len(page.structured_content) <= limits.max_structured_blocks_per_page
        and _structured_content_within_stable_limits(page, limits)
    )


def _structured_content_within_stable_limits(
    page: SiteContentEvidence,
    limits: SiteContentPacketLimits,
) -> bool:
    counts = {kind: 0 for kind in StructuredContentKind}
    for block in page.structured_content:
        counts[block.kind] += 1
        fields = [
            *(cell for row in block.rows for cell in row),
            *(value for pair in block.pairs for value in pair),
            *block.items,
        ]
        if (
            block.heading is not None
            and (
                block.heading != " ".join(block.heading.split())
                or len(block.heading) > limits.max_heading_chars
            )
            or any(
                value != " ".join(value.split())
                or len(value) > limits.max_field_chars
                for value in fields
            )
            or len(block.rows) > limits.max_rows_per_table
            or any(len(row) > limits.max_cells_per_row for row in block.rows)
            or len(block.pairs) > limits.max_pairs_per_block
            or len(block.items) > limits.max_items_per_list
            or block.text is not None
            and (
                block.text != " ".join(block.text.split())
                or len(block.text)
                > (
                    limits.max_section_chars
                    if block.kind is StructuredContentKind.SECTION
                    else limits.max_field_chars
                )
            )
            or block.kind is StructuredContentKind.TABLE
            and sum(len(cell) for row in block.rows for cell in row)
            > limits.max_chars_per_table
        ):
            return False
    return (
        counts[StructuredContentKind.TABLE] <= limits.max_tables_per_page
        and counts[StructuredContentKind.DEFINITION_LIST]
        <= limits.max_definition_lists_per_page
        and counts[StructuredContentKind.KEY_VALUE]
        <= limits.max_key_value_blocks_per_page
        and counts[StructuredContentKind.SECTION] <= limits.max_sections_per_page
        and counts[StructuredContentKind.LIST] <= limits.max_lists_per_page
        and counts[StructuredContentKind.IMAGE_ALT] <= limits.max_image_alts_per_page
        and sum(
            _structured_block_chars(block) for block in page.structured_content
        )
        <= limits.max_structured_chars_per_page
    )


def _structured_block_chars(block: object) -> int:
    if not hasattr(block, "kind"):
        return MAX_SITE_PACKET_CHARS + 1
    return (
        len(block.heading or "")
        + sum(len(cell) for row in block.rows for cell in row)
        + sum(len(value) for pair in block.pairs for value in pair)
        + sum(len(item) for item in block.items)
        + len(block.text or "")
    )


def _stable_source_material_is_valid(
    material: ContentOpportunitySourceMaterial,
) -> bool:
    return (
        isinstance(material, ContentOpportunitySourceMaterial)
        and type(material.title) is str
        and 0 < len(material.title) <= MAX_SOURCE_TITLE_CHARS
        and material.title == " ".join(material.title.split())
        and type(material.content) is str
        and 0 < len(material.content) <= MAX_SOURCE_CONTENT_CHARS
        and material.content == " ".join(material.content.split())
        and type(material.content_truncated) is bool
    )


def _stable_display_sources_match(
    report: ContentOpportunityReport,
    materials: tuple[ContentOpportunitySourceMaterial, ...],
) -> bool:
    if not isinstance(report.sources, tuple) or len(report.sources) != len(materials):
        return False
    for source, material in zip(report.sources, materials, strict=True):
        if (
            not isinstance(source, ContentOpportunitySource)
            or source.source_id != material.source_id
            or source.title != material.title
            or canonical_url_origin(source.url) is None
            or source.classifications
            != (
                ResearchEvidenceClassification.EXTERNAL_RESEARCH_CONTEXT,
                ResearchEvidenceClassification.UNVERIFIED_SEARCH_RESULT,
            )
        ):
            return False
    return True


@dataclass(frozen=True, slots=True)
class ChangePlanGeneration:
    provider: str
    model: str
    status: ChangePlanGenerationStatus
    text: str | None
    error: str | None
    failure_kind: ChangePlanGenerationFailureKind | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.status, ChangePlanGenerationStatus)
            or type(self.provider) is not str
            or type(self.model) is not str
            or not self.provider.strip()
            or not self.model.strip()
        ):
            raise ValueError("Change plan generation requires provider metadata.")
        if self.status is ChangePlanGenerationStatus.SUCCESS:
            if (
                self.text is None
                or not self.text.strip()
                or self.error is not None
                or self.failure_kind is not None
            ):
                raise ValueError("Successful change plan generation is invalid.")
        elif (
            self.text is not None
            or not self.error
            or self.failure_kind is not None
            and not isinstance(
                self.failure_kind,
                ChangePlanGenerationFailureKind,
            )
        ):
            raise ValueError("Failed change plan generation is invalid.")


@dataclass(frozen=True, slots=True)
class SectionLocatorSpecification:
    locator_kind: SectionLocatorKind
    page_ref: str | None
    target_heading: str | None


@dataclass(frozen=True, slots=True)
class ContentPointSpecification:
    intent: ContentPointIntent
    subject: str
    origin_ref: str


@dataclass(frozen=True, slots=True)
class ComparisonTableSpecification:
    column_headers: tuple[str, ...]
    row_dimensions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class InternalLinkSpecification:
    source_page_ref: str
    target_page_ref: str
    anchor_intent: str


@dataclass(frozen=True, slots=True)
class NewResourceSpecification:
    resource_purpose: NewResourcePurpose
    proposed_title: str
    outline_headings: tuple[str, ...]
    content_points: tuple[ContentPointSpecification, ...]
    suggested_source_page_refs: tuple[str, ...]
    comparison_table_specification: ComparisonTableSpecification | None


@dataclass(frozen=True, slots=True)
class BaseChangePlanSpecification:
    opportunity_ref: str
    source_action_code: ContentOpportunityActionCode
    operation_type: ChangeOperationType
    page_refs: tuple[str, ...]
    source_refs: tuple[str, ...]
    locator: SectionLocatorSpecification


@dataclass(frozen=True, slots=True)
class ExpandSectionSpecification(BaseChangePlanSpecification):
    content_points: tuple[ContentPointSpecification, ...]


@dataclass(frozen=True, slots=True)
class ProposeSectionReorderSpecification(BaseChangePlanSpecification):
    ordered_headings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AddSectionSpecification(BaseChangePlanSpecification):
    section_purpose: SectionPurpose
    proposed_heading: str
    content_points: tuple[ContentPointSpecification, ...]


@dataclass(frozen=True, slots=True)
class AddComparisonTableSpecification(BaseChangePlanSpecification):
    proposed_heading: str
    comparison_table_specification: ComparisonTableSpecification


@dataclass(frozen=True, slots=True)
class AddInternalLinkSpecification(BaseChangePlanSpecification):
    internal_link_specification: InternalLinkSpecification


@dataclass(frozen=True, slots=True)
class CreateNewResourceSpecification(BaseChangePlanSpecification):
    new_resource_specification: NewResourceSpecification


ChangePlanSpecification = (
    ExpandSectionSpecification
    | ProposeSectionReorderSpecification
    | AddSectionSpecification
    | AddComparisonTableSpecification
    | AddInternalLinkSpecification
    | CreateNewResourceSpecification
)


@dataclass(frozen=True, slots=True)
class SectionLocator:
    locator_kind: SectionLocatorKind
    page_ref: str | None
    observed_heading: str | None
    observed_heading_kind: ObservedHeadingKind | None
    observed_context: str | None

    def __post_init__(self) -> None:
        if self.locator_kind is SectionLocatorKind.PAGE_LEVEL:
            valid = (
                _is_page_ref(self.page_ref)
                and self.observed_heading is None
                and self.observed_heading_kind is None
                and self.observed_context is None
            )
        elif self.locator_kind is SectionLocatorKind.EXACT_OBSERVED_HEADING:
            valid = (
                _is_page_ref(self.page_ref)
                and _is_bounded_text(self.observed_heading, MAX_PROPOSED_HEADING_CHARS)
                and isinstance(self.observed_heading_kind, ObservedHeadingKind)
                and _is_bounded_text(self.observed_context, MAX_OBSERVED_CONTEXT_CHARS)
            )
        else:
            valid = (
                self.page_ref is None
                and self.observed_heading is None
                and self.observed_heading_kind is None
                and self.observed_context is None
            )
        if not valid:
            raise ValueError("Section locator shape is invalid.")


@dataclass(frozen=True, slots=True)
class ContentPoint:
    intent: ContentPointIntent
    subject: str

    def __post_init__(self) -> None:
        if not isinstance(self.intent, ContentPointIntent) or not _is_bounded_text(
            self.subject, MAX_CONTENT_POINT_SUBJECT_CHARS
        ):
            raise ValueError("Content point is invalid.")


@dataclass(frozen=True, slots=True)
class ComparisonTableSpec:
    column_headers: tuple[str, ...]
    row_dimensions: tuple[str, ...]

    def __post_init__(self) -> None:
        if not _valid_string_tuple(
            self.column_headers,
            MIN_TABLE_COLUMNS,
            MAX_TABLE_COLUMNS,
            MAX_TABLE_LABEL_CHARS,
        ) or not _valid_string_tuple(
            self.row_dimensions,
            MIN_TABLE_DIMENSIONS,
            MAX_TABLE_DIMENSIONS,
            MAX_TABLE_LABEL_CHARS,
        ):
            raise ValueError("Comparison table brief is invalid.")


@dataclass(frozen=True, slots=True)
class InternalLinkSpec:
    source_page_ref: str
    target_page_ref: str
    source_url: str
    target_url: str
    anchor_intent: str

    def __post_init__(self) -> None:
        if (
            not _is_page_ref(self.source_page_ref)
            or not _is_page_ref(self.target_page_ref)
            or self.source_page_ref == self.target_page_ref
            or type(self.source_url) is not str
            or not self.source_url
            or type(self.target_url) is not str
            or not self.target_url
            or not _is_bounded_text(self.anchor_intent, MAX_ANCHOR_INTENT_CHARS)
        ):
            raise ValueError("Internal link brief is invalid.")


@dataclass(frozen=True, slots=True)
class NewResourceSpec:
    resource_purpose: NewResourcePurpose
    proposed_title: str
    outline_headings: tuple[str, ...]
    content_points: tuple[ContentPoint, ...]
    suggested_source_page_refs: tuple[str, ...]
    comparison_table_spec: ComparisonTableSpec | None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.resource_purpose, NewResourcePurpose)
            or not _is_bounded_text(self.proposed_title, MAX_PROPOSED_HEADING_CHARS)
            or not _valid_string_tuple(
                self.outline_headings,
                MIN_OUTLINE_HEADINGS,
                MAX_OUTLINE_HEADINGS,
                MAX_OUTLINE_HEADING_CHARS,
            )
            or not isinstance(self.content_points, tuple)
            or not MIN_CONTENT_POINTS_PER_OPERATION
            <= len(self.content_points)
            <= MAX_CONTENT_POINTS_PER_OPERATION
            or not all(isinstance(item, ContentPoint) for item in self.content_points)
            or not isinstance(self.suggested_source_page_refs, tuple)
            or len(self.suggested_source_page_refs)
            != len(set(self.suggested_source_page_refs))
            or not all(_is_page_ref(item) for item in self.suggested_source_page_refs)
            or self.comparison_table_spec is not None
            and not isinstance(self.comparison_table_spec, ComparisonTableSpec)
        ):
            raise ValueError("New resource brief is invalid.")


@dataclass(frozen=True, slots=True)
class ChangeOperation:
    change_id: str
    opportunity_ref: str
    source_action_code: ContentOpportunityActionCode
    operation_type: ChangeOperationType
    target_kind: ChangeTargetKind
    locator: SectionLocator
    proposed_heading: str | None
    content_points: tuple[ContentPoint, ...]
    comparison_table_spec: ComparisonTableSpec | None
    internal_link_spec: InternalLinkSpec | None
    new_resource_spec: NewResourceSpec | None
    page_refs: tuple[str, ...]
    source_refs: tuple[str, ...]
    ordered_headings: tuple[str, ...]
    section_purpose: SectionPurpose | None
    requires_human_review: bool = True
    complete_page_order: bool = False
    audit_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if re.fullmatch(r"C[1-9][0-9]*", self.change_id) is None:
            raise ValueError("Change ID must be assigned by Python.")
        if not self.requires_human_review:
            raise ValueError("Change operations require human review.")
        if self.complete_page_order:
            raise ValueError("V1 never claims a complete page order.")
        if (
            not re.fullmatch(r"R[1-9][0-9]*", self.opportunity_ref)
            or not isinstance(self.source_action_code, ContentOpportunityActionCode)
            or not isinstance(self.operation_type, ChangeOperationType)
            or not isinstance(self.target_kind, ChangeTargetKind)
            or not isinstance(self.locator, SectionLocator)
            or not isinstance(self.page_refs, tuple)
            or len(self.page_refs) > MAX_PAGE_REFS_PER_OPERATION
            or len(self.page_refs) != len(set(self.page_refs))
            or not all(_is_page_ref(item) for item in self.page_refs)
            or not isinstance(self.source_refs, tuple)
            or len(self.source_refs) > MAX_SOURCE_REFS_PER_OPERATION
            or len(self.source_refs) != len(set(self.source_refs))
            or not all(
                type(item) is str
                and re.fullmatch(r"S[1-9][0-9]*", item) is not None
                for item in self.source_refs
            )
            or not isinstance(self.audit_refs, tuple)
            or len(self.audit_refs) != len(set(self.audit_refs))
            or not all(
                type(item) is str
                and re.fullmatch(r"A[1-9][0-9]*", item) is not None
                for item in self.audit_refs
            )
            or not isinstance(self.content_points, tuple)
            or not all(isinstance(item, ContentPoint) for item in self.content_points)
            or not isinstance(self.ordered_headings, tuple)
            or self.section_purpose is not None
            and not isinstance(self.section_purpose, SectionPurpose)
        ):
            raise ValueError("Finalized change operation is invalid.")
        if self.operation_type not in CHANGE_OPERATION_COMPATIBILITY[
            self.source_action_code
        ]:
            raise ValueError("Change operation is incompatible with its source action.")
        if self.proposed_heading is not None and not _is_bounded_text(
            self.proposed_heading, MAX_PROPOSED_HEADING_CHARS
        ):
            raise ValueError("Proposed heading is invalid.")
        if self.comparison_table_spec is not None and not isinstance(
            self.comparison_table_spec, ComparisonTableSpec
        ):
            raise ValueError("Comparison table brief is invalid.")
        if self.internal_link_spec is not None and not isinstance(
            self.internal_link_spec, InternalLinkSpec
        ):
            raise ValueError("Internal link brief is invalid.")
        if self.new_resource_spec is not None and not isinstance(
            self.new_resource_spec, NewResourceSpec
        ):
            raise ValueError("New resource brief is invalid.")

        existing_target = (
            self.target_kind is ChangeTargetKind.MODIFY_EXISTING_PAGE
            and self.locator.locator_kind is not SectionLocatorKind.NEW_PAGE
        )
        no_auxiliary = (
            self.comparison_table_spec is None
            and self.internal_link_spec is None
            and self.new_resource_spec is None
            and not self.ordered_headings
            and self.section_purpose is None
        )
        valid = False
        if self.operation_type is ChangeOperationType.EXPAND_SECTION:
            # This is a structural capacity check, never planning authority.
            # The finalizer separately requires an explicit task/packet scope
            # and complete ordered equality; default Planning/Draft stay shut.
            literal_shape = (
                len(self.page_refs) == 1 and not self.source_refs and not self.audit_refs
                and self.locator.locator_kind is SectionLocatorKind.EXACT_OBSERVED_HEADING
                and self.locator.page_ref == self.page_refs[0]
                and all(point.intent in {ContentPointIntent.DESCRIBE, ContentPointIntent.SUMMARIZE}
                        for point in self.content_points)
            )
            valid = (
                existing_target
                and self.proposed_heading is None
                and MIN_CONTENT_POINTS_PER_OPERATION
                <= len(self.content_points)
                <= (MAX_FIRST_PARTY_EXCERPTS if literal_shape else MAX_CONTENT_POINTS_PER_OPERATION)
                and no_auxiliary
            )
        elif self.operation_type is ChangeOperationType.PROPOSE_SECTION_REORDER:
            valid = (
                existing_target
                and self.locator.locator_kind is SectionLocatorKind.PAGE_LEVEL
                and self.proposed_heading is None
                and not self.content_points
                and self.comparison_table_spec is None
                and self.internal_link_spec is None
                and self.new_resource_spec is None
                and _valid_string_tuple(
                    self.ordered_headings,
                    MIN_REORDER_HEADINGS,
                    MAX_REORDER_HEADINGS,
                    MAX_PROPOSED_HEADING_CHARS,
                )
                and self.section_purpose is None
            )
        elif self.operation_type is ChangeOperationType.ADD_SECTION:
            expected_purpose = {
                ContentOpportunityActionCode.ADD_BUYER_GUIDANCE: SectionPurpose.BUYER_GUIDANCE,
                ContentOpportunityActionCode.ADD_TECHNICAL_DOCUMENTATION: SectionPurpose.TECHNICAL_DOCUMENTATION,
            }.get(self.source_action_code)
            valid = (
                existing_target
                and self.proposed_heading is not None
                and MIN_CONTENT_POINTS_PER_OPERATION
                <= len(self.content_points)
                <= MAX_CONTENT_POINTS_PER_OPERATION
                and self.comparison_table_spec is None
                and self.internal_link_spec is None
                and self.new_resource_spec is None
                and not self.ordered_headings
                and self.section_purpose is expected_purpose
            )
        elif self.operation_type is ChangeOperationType.ADD_COMPARISON_TABLE:
            valid = (
                existing_target
                and self.proposed_heading is not None
                and not self.content_points
                and self.comparison_table_spec is not None
                and self.internal_link_spec is None
                and self.new_resource_spec is None
                and not self.ordered_headings
                and self.section_purpose is None
            )
        elif self.operation_type is ChangeOperationType.ADD_INTERNAL_LINK:
            valid = (
                existing_target
                and self.locator.locator_kind is SectionLocatorKind.PAGE_LEVEL
                and self.proposed_heading is None
                and not self.content_points
                and self.comparison_table_spec is None
                and self.internal_link_spec is not None
                and self.new_resource_spec is None
                and not self.ordered_headings
                and self.section_purpose is None
                and self.locator.page_ref == self.internal_link_spec.source_page_ref
            )
        else:
            nested_table_required = (
                self.source_action_code
                is ContentOpportunityActionCode.ADD_COMPARISON_TABLE
            )
            valid = (
                self.target_kind is ChangeTargetKind.CREATE_NEW_PAGE
                and self.locator.locator_kind is SectionLocatorKind.NEW_PAGE
                and self.new_resource_spec is not None
                and self.new_resource_spec.resource_purpose
                is NEW_RESOURCE_PURPOSE_BY_ACTION.get(self.source_action_code)
                and self.proposed_heading == self.new_resource_spec.proposed_title
                and self.content_points == self.new_resource_spec.content_points
                and self.comparison_table_spec
                == self.new_resource_spec.comparison_table_spec
                and self.internal_link_spec is None
                and not self.ordered_headings
                and self.section_purpose is None
                and (
                    not nested_table_required
                    or self.comparison_table_spec is not None
                )
            )
        if not valid:
            raise ValueError("Change operation fields do not match its discriminator.")


def comparison_operation_error(
    operation: ChangeOperation | ChangePlanSpecification,
) -> str | None:
    """Execution eligibility, separate from V1 structural/read compatibility.

    No trusted subject/attribute/fact admission exists yet. All comparison
    capabilities are unavailable, including tables nested in other resources.
    Provider claims and lexical grounding cannot grant execution eligibility.
    """

    if (
        operation.operation_type is ChangeOperationType.ADD_COMPARISON_TABLE
        or operation.source_action_code is ContentOpportunityActionCode.ADD_COMPARISON_TABLE
    ):
        return ChangePlanValidationCategory.COMPARISON_UNAVAILABLE.value
    if isinstance(operation, ChangeOperation):
        if operation.comparison_table_spec is not None:
            return ChangePlanValidationCategory.COMPARISON_UNAVAILABLE.value
        resource = operation.new_resource_spec
        nested = None if resource is None else resource.comparison_table_spec
    elif isinstance(operation, CreateNewResourceSpecification):
        resource = operation.new_resource_specification
        nested = resource.comparison_table_specification
    else:
        return None
    if resource is not None and (
        resource.resource_purpose is NewResourcePurpose.COMPARISON_RESOURCE
        or nested is not None
    ):
        return ChangePlanValidationCategory.COMPARISON_UNAVAILABLE.value
    return None


@dataclass(frozen=True, slots=True)
class ChangePlanReport:
    status: ChangePlanStatus
    operations: tuple[ChangeOperation, ...]
    limitations: tuple[str, ...]
    error: str | None
    requires_human_review: bool = True
    final_validation_category: PlanningValidationCategory | None = None
    writer_attempt_count: int | None = None

    def __post_init__(self) -> None:
        if self.final_validation_category is not None and not isinstance(
            self.final_validation_category, PlanningValidationCategory
        ):
            raise TypeError("Change plan validation category is invalid.")
        if self.writer_attempt_count is not None and (
            type(self.writer_attempt_count) is not int
            or self.writer_attempt_count not in {1, 2}
        ):
            raise ValueError("Change plan writer attempt count is invalid.")
        if self.final_validation_category is not None and (
            self.status is not ChangePlanStatus.INVALID_OUTPUT
            or self.writer_attempt_count is None
        ):
            raise ValueError("Change plan validation diagnostics are inconsistent.")
        if not isinstance(self.status, ChangePlanStatus) or not self.requires_human_review:
            raise ValueError("Change plan reports require human review.")
        if not isinstance(self.operations, tuple) or not all(
            isinstance(item, ChangeOperation) for item in self.operations
        ):
            raise ValueError("Change plan operations are invalid.")
        if self.status is ChangePlanStatus.SUCCESS:
            if (
                self.error is not None
                or self.limitations != CHANGE_PLAN_LIMITATIONS
                or self.final_validation_category is not None
                or self.writer_attempt_count is not None
            ):
                raise ValueError("Successful change plan report is invalid.")
            expected_ids = tuple(
                f"C{number}" for number in range(1, len(self.operations) + 1)
            )
            actual_ids = tuple(item.change_id for item in self.operations)
            opportunity_counts: dict[str, int] = {}
            identities: set[tuple[object, ...]] = set()
            for operation in self.operations:
                opportunity_counts[operation.opportunity_ref] = (
                    opportunity_counts.get(operation.opportunity_ref, 0) + 1
                )
                identities.add(canonical_change_operation_identity(operation))
            if (
                len(self.operations) > MAX_OPERATIONS
                or actual_ids != expected_ids
                or any(
                    count > MAX_OPERATIONS_PER_OPPORTUNITY
                    for count in opportunity_counts.values()
                )
                or len(identities) != len(self.operations)
            ):
                raise ValueError("Successful change plan operations are inconsistent.")
        elif self.operations or self.limitations:
            raise ValueError("Failed change plan reports cannot carry payloads.")
        if self.error is not None and self.error not in {
            item.value for item in ChangePlanValidationCategory
        }:
            raise ValueError("Change plan error must be an allowlisted category.")
        validation_failure = self.status in {
            ChangePlanStatus.INVALID_INPUT,
            ChangePlanStatus.INPUT_TOO_LARGE,
            ChangePlanStatus.INVALID_OUTPUT,
        }
        if validation_failure != (self.error is not None):
            raise ValueError("Change plan status and error category are inconsistent.")


def _canonical_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    return normalized_evidence_text(value)


def _canonical_content_points(
    points: tuple[ContentPoint, ...],
) -> tuple[tuple[ContentPointIntent, str], ...]:
    return tuple(
        (point.intent, normalized_evidence_text(point.subject)) for point in points
    )


def _canonical_table(
    table: ComparisonTableSpec | None,
) -> tuple[tuple[str, ...], tuple[str, ...]] | None:
    if table is None:
        return None
    return (
        tuple(normalized_evidence_text(item) for item in table.column_headers),
        tuple(normalized_evidence_text(item) for item in table.row_dimensions),
    )


def _canonical_internal_link(
    link: InternalLinkSpec | None,
) -> tuple[object, ...] | None:
    if link is None:
        return None
    return (
        link.source_page_ref,
        link.target_page_ref,
        link.source_url,
        link.target_url,
        normalized_evidence_text(link.anchor_intent),
    )


def _canonical_new_resource(
    resource: NewResourceSpec | None,
) -> tuple[object, ...] | None:
    if resource is None:
        return None
    return (
        resource.resource_purpose,
        normalized_evidence_text(resource.proposed_title),
        tuple(
            normalized_evidence_text(heading)
            for heading in resource.outline_headings
        ),
        _canonical_content_points(resource.content_points),
        resource.suggested_source_page_refs,
        _canonical_table(resource.comparison_table_spec),
    )


def canonical_change_operation_identity(
    operation: ChangeOperation,
) -> tuple[object, ...]:
    """Return deterministic structured identity, excluding the assigned C#."""

    locator = operation.locator
    return (
        operation.opportunity_ref,
        operation.source_action_code,
        operation.operation_type,
        operation.target_kind,
        (
            locator.locator_kind,
            locator.page_ref,
            _canonical_optional_text(locator.observed_heading),
            locator.observed_heading_kind,
            _canonical_optional_text(locator.observed_context),
        ),
        _canonical_optional_text(operation.proposed_heading),
        _canonical_content_points(operation.content_points),
        _canonical_table(operation.comparison_table_spec),
        _canonical_internal_link(operation.internal_link_spec),
        _canonical_new_resource(operation.new_resource_spec),
        operation.page_refs,
        operation.source_refs,
        operation.audit_refs,
        tuple(
            normalized_evidence_text(heading)
            for heading in operation.ordered_headings
        ),
        operation.section_purpose,
        operation.requires_human_review,
        operation.complete_page_order,
    )


def _is_page_ref(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"P[1-9][0-9]*", value) is not None


def _is_bounded_text(value: object, maximum: int) -> bool:
    return (
        type(value) is str
        and value == " ".join(value.split())
        and bool(value)
        and len(value) <= maximum
        and "\n" not in value
        and "\r" not in value
    )


def _valid_string_tuple(
    values: object, minimum: int, maximum: int, maximum_chars: int
) -> bool:
    return (
        isinstance(values, tuple)
        and minimum <= len(values) <= maximum
        and len(values) == len(set(values))
        and all(_is_bounded_text(value, maximum_chars) for value in values)
    )


def normalized_evidence_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def contains_absence_claim(value: str) -> bool:
    """Share the opportunity-stage terms and cover the approved V1 no-X forms."""

    normalized = normalized_evidence_text(value)
    return any(
        term in normalized for term in CONTENT_OPPORTUNITY_ABSENCE_TERMS
    ) or re.search(
        r"\bno\s+(?:faq|comparison\s+table|internal\s+links?)\b", normalized
    ) is not None


def has_forbidden_prose_syntax(value: str) -> bool:
    return (
        re.search(r"<[^>]+>", value) is not None
        or re.search(r"(?:[a-z][a-z0-9+.-]*://|www\.)", value, re.IGNORECASE)
        is not None
    )


def phrase_is_grounded(value: str, evidence: tuple[str, ...]) -> bool:
    needle = normalized_evidence_text(value)
    return any(needle in normalized_evidence_text(text) for text in evidence if text)


_PROPOSAL_WORDS = frozenset(
    {"guide", "overview", "comparison", "buyer", "technical", "resource", "and", "for", "the", "of"}
)


def proposed_label_is_grounded(value: str, evidence: tuple[str, ...]) -> bool:
    """Ground proposed labels by all non-structural topic tokens."""

    tokens = tuple(
        token
        for token in re.findall(r"[^\W_]+", normalized_evidence_text(value))
        if token not in _PROPOSAL_WORDS
    )
    if not tokens:
        return False
    evidence_tokens = {
        token
        for text in evidence
        for token in re.findall(r"[^\W_]+", normalized_evidence_text(text))
    }
    return all(token in evidence_tokens for token in tokens)


def provider_visible_headings(page: SiteContentEvidence) -> tuple[str, ...]:
    """Return the single heading universe exposed to and accepted from providers."""

    headings = [*page.h1, *page.h2]
    headings.extend(
        block.heading
        for block in page.structured_content
        if block.kind is not StructuredContentKind.IMAGE_ALT and block.heading
    )
    return tuple(dict.fromkeys(headings))


def _build_locator_candidate_sets(
    catalog: ChangePlanEvidenceCatalog,
) -> tuple[OpportunityLocatorCandidates, ...]:
    pages = catalog.page_by_id()
    result: list[OpportunityLocatorCandidates] = []
    for opportunity_item in catalog.opportunities:
        opportunity = opportunity_item.opportunity
        allowed_pages = tuple(
            pages[page_ref]
            for page_ref in opportunity.page_refs
            if page_ref in pages
        )
        candidates = [
            LocatorCandidate(
                f"{page.evidence_id}.LOC_00",
                SectionLocatorKind.PAGE_LEVEL,
                page.evidence_id,
                None,
            )
            for page in allowed_pages
        ]
        visible_by_page = {
            page.evidence_id: provider_visible_headings(page)[
                :MAX_EXACT_LOCATOR_CANDIDATES_PER_PAGE
            ]
            for page in allowed_pages
        }
        for heading_index in range(MAX_EXACT_LOCATOR_CANDIDATES_PER_PAGE):
            for page in allowed_pages:
                if len(candidates) >= MAX_LOCATOR_CANDIDATES_PER_OPPORTUNITY:
                    break
                headings = visible_by_page[page.evidence_id]
                if heading_index >= len(headings):
                    continue
                candidates.append(
                    LocatorCandidate(
                        f"{page.evidence_id}.LOC_{heading_index + 1:02d}",
                        SectionLocatorKind.EXACT_OBSERVED_HEADING,
                        page.evidence_id,
                        headings[heading_index],
                    )
                )
            if len(candidates) >= MAX_LOCATOR_CANDIDATES_PER_OPPORTUNITY:
                break
        result.append(
            OpportunityLocatorCandidates(
                opportunity.recommendation_id,
                tuple(candidates),
            )
        )
    return tuple(result)


def page_evidence_text(page: SiteContentEvidence) -> tuple[str, ...]:
    values: list[str] = []
    values.extend(value for value in (page.title, page.description, page.body_text) if value)
    values.extend(page.h1)
    values.extend(page.h2)
    for block in page.structured_content:
        if block.kind is StructuredContentKind.IMAGE_ALT:
            continue
        if block.heading:
            values.append(block.heading)
        if block.text:
            values.append(block.text)
        values.extend(cell for row in block.rows for cell in row)
        values.extend(value for pair in block.pairs for value in pair)
        values.extend(block.items)
    return tuple(values)


_CONTENT_POINT_SEGMENT_SPLIT = re.compile(
    r"(?:[\r\n]+|\s+[0-9]{1,3}\s+|(?<=[.!?;:])\s+|[,;]\s*)"
)


def _candidate_segments(value: str) -> tuple[str, ...]:
    compact = " ".join(value.split())
    if not compact:
        return ()
    result: list[str] = []
    for raw_segment in _CONTENT_POINT_SEGMENT_SPLIT.split(compact):
        segment = raw_segment.strip(" \t-–—,;:")
        if not segment:
            continue
        if len(segment) <= MAX_CONTENT_POINT_SUBJECT_CHARS:
            result.append(segment)
            continue
        words = segment.split()
        current: list[str] = []
        for word in words:
            proposed = " ".join((*current, word))
            if current and len(proposed) > MAX_CONTENT_POINT_SUBJECT_CHARS:
                result.append(" ".join(current))
                current = [word]
            else:
                current.append(word)
        if current:
            result.append(" ".join(current))
    return tuple(result)


def _page_content_point_values(page: SiteContentEvidence) -> tuple[str, ...]:
    values: list[str] = [page.title, *page.h1, *page.h2]
    for block in page.structured_content:
        if block.kind is StructuredContentKind.IMAGE_ALT:
            continue
        if block.heading:
            values.append(block.heading)
        values.extend(block.items)
        values.extend(value for pair in block.pairs for value in pair)
        values.extend(cell for row in block.rows for cell in row)
    for value in (page.body_text, page.description):
        values.extend(_candidate_segments(value))
    for block in page.structured_content:
        if block.kind is not StructuredContentKind.IMAGE_ALT and block.text:
            values.extend(_candidate_segments(block.text))
    return tuple(values)


def _source_content_point_values(
    material: ContentOpportunitySourceMaterial,
) -> tuple[str, ...]:
    return (material.title, *_candidate_segments(material.content))


def _legal_proposed_label(
    value: str,
    *,
    maximum: int,
    evidence: tuple[str, ...],
) -> str | None:
    text = " ".join(value.split())
    if (
        not _is_bounded_text(text, maximum)
        or has_forbidden_prose_syntax(text)
        or contains_absence_claim(text)
        or not proposed_label_is_grounded(text, evidence)
    ):
        return None
    return text


def _build_proposed_heading_candidate_sets(
    catalog: ChangePlanEvidenceCatalog,
) -> tuple[OpportunityProposedHeadingCandidates, ...]:
    pages = catalog.page_by_id()
    sources = catalog.source_by_id()
    result: list[OpportunityProposedHeadingCandidates] = []
    for item in catalog.opportunities:
        opportunity = item.opportunity
        allowed_pages = tuple(
            pages[page_ref]
            for page_ref in opportunity.page_refs
            if page_ref in pages
        )
        allowed_sources = tuple(
            sources[source_ref]
            for source_ref in opportunity.source_refs
            if source_ref in sources
        )
        candidates: list[ProposedHeadingCandidate] = []
        for target_page in allowed_pages:
            existing = {
                normalized_evidence_text(heading)
                for heading in provider_visible_headings(target_page)
            }
            normalized_seen: set[str] = set()
            page_candidates = 0
            for source_index, source in enumerate(allowed_sources):
                values: tuple[str, ...] = (
                    (
                        f"{opportunity.topic.title()} Guide",
                        opportunity.topic.title(),
                    )
                    if source_index == 0
                    else ()
                ) + _source_content_point_values(source)
                evidence = (source.title, source.content)
                for raw in values:
                    text = _legal_proposed_label(
                        raw,
                        maximum=MAX_PROPOSED_HEADING_CHARS,
                        evidence=evidence,
                    )
                    if text is None:
                        continue
                    normalized = normalized_evidence_text(text)
                    if normalized in normalized_seen or normalized in existing:
                        continue
                    normalized_seen.add(normalized)
                    page_candidates += 1
                    candidates.append(
                        ProposedHeadingCandidate(
                            f"{target_page.evidence_id}.PH_{page_candidates:02d}",
                            text,
                            target_page.evidence_id,
                            source.source_id,
                        )
                    )
                    if (
                        page_candidates >= MAX_PROPOSED_HEADING_CANDIDATES_PER_PAGE
                        or len(candidates)
                        >= MAX_PROPOSED_HEADING_CANDIDATES_PER_OPPORTUNITY
                    ):
                        break
                if (
                    page_candidates >= MAX_PROPOSED_HEADING_CANDIDATES_PER_PAGE
                    or len(candidates)
                    >= MAX_PROPOSED_HEADING_CANDIDATES_PER_OPPORTUNITY
                ):
                    break
            if len(candidates) >= MAX_PROPOSED_HEADING_CANDIDATES_PER_OPPORTUNITY:
                break
        result.append(
            OpportunityProposedHeadingCandidates(
                opportunity.recommendation_id,
                tuple(candidates),
            )
        )
    return tuple(result)


def _build_outline_heading_candidate_sets(
    catalog: ChangePlanEvidenceCatalog,
) -> tuple[OpportunityOutlineHeadingCandidates, ...]:
    sources = catalog.source_by_id()
    result: list[OpportunityOutlineHeadingCandidates] = []
    for item in catalog.opportunities:
        candidates: list[OutlineHeadingCandidate] = []
        normalized_seen: set[str] = set()
        per_source_counts: dict[str, int] = {}
        for source_ref in item.opportunity.source_refs:
            source = sources.get(source_ref)
            if source is None:
                continue
            evidence = (source.title, source.content)
            for raw in _source_content_point_values(source):
                text = _legal_proposed_label(
                    raw,
                    maximum=MAX_OUTLINE_HEADING_CHARS,
                    evidence=evidence,
                )
                if text is None:
                    continue
                normalized = normalized_evidence_text(text)
                if normalized in normalized_seen:
                    continue
                normalized_seen.add(normalized)
                per_source_counts[source_ref] = per_source_counts.get(source_ref, 0) + 1
                candidates.append(
                    OutlineHeadingCandidate(
                        f"{source_ref}.OH_{per_source_counts[source_ref]:02d}",
                        text,
                        source_ref,
                    )
                )
                if len(candidates) >= MAX_OUTLINE_HEADING_CANDIDATES_PER_OPPORTUNITY:
                    break
            if len(candidates) >= MAX_OUTLINE_HEADING_CANDIDATES_PER_OPPORTUNITY:
                break
        result.append(
            OpportunityOutlineHeadingCandidates(
                item.opportunity.recommendation_id,
                tuple(candidates),
            )
        )
    return tuple(result)


def _content_point_candidates_for_origin(
    origin_ref: str,
    values: tuple[str, ...],
    evidence: tuple[str, ...],
) -> tuple[ContentPointCandidate, ...]:
    candidates: list[ContentPointCandidate] = []
    normalized_seen: set[str] = set()
    for raw in values:
        text = " ".join(raw.split())
        normalized = normalized_evidence_text(text)
        if (
            not normalized
            or normalized in normalized_seen
            or not _is_bounded_text(text, MAX_CONTENT_POINT_SUBJECT_CHARS)
            or has_forbidden_prose_syntax(text)
            or contains_absence_claim(text)
            or not phrase_is_grounded(text, evidence)
        ):
            continue
        normalized_seen.add(normalized)
        candidates.append(
            ContentPointCandidate(
                f"{origin_ref}.CP_{len(candidates) + 1:02d}",
                text,
                origin_ref,
            )
        )
        if len(candidates) >= MAX_CONTENT_POINT_CANDIDATES_PER_EVIDENCE:
            break
    return tuple(candidates)


def _build_content_point_candidate_sets(
    catalog: ChangePlanEvidenceCatalog,
) -> tuple[OpportunityContentPointCandidates, ...]:
    pages = catalog.page_by_id()
    sources = catalog.source_by_id()
    pools: dict[str, tuple[ContentPointCandidate, ...]] = {}
    for page_ref, page in pages.items():
        pools[page_ref] = _content_point_candidates_for_origin(
            page_ref,
            _page_content_point_values(page),
            page_evidence_text(page),
        )
    for source_ref, material in sources.items():
        pools[source_ref] = _content_point_candidates_for_origin(
            source_ref,
            _source_content_point_values(material),
            (material.title, material.content),
        )

    remaining = MAX_CONTENT_POINT_CANDIDATES_GLOBAL
    result: list[OpportunityContentPointCandidates] = []
    for item in catalog.opportunities:
        selected: list[ContentPointCandidate] = []
        normalized_seen: set[str] = set()
        opportunity = item.opportunity
        origin_refs = (*opportunity.page_refs, *opportunity.source_refs)
        for candidate_index in range(MAX_CONTENT_POINT_CANDIDATES_PER_EVIDENCE):
            for origin_ref in origin_refs:
                origin_candidates = pools.get(origin_ref, ())
                if candidate_index >= len(origin_candidates):
                    continue
                candidate = origin_candidates[candidate_index]
                normalized = normalized_evidence_text(candidate.text)
                if normalized in normalized_seen:
                    continue
                normalized_seen.add(normalized)
                selected.append(candidate)
                remaining -= 1
                if (
                    len(selected) >= MAX_CONTENT_POINT_CANDIDATES_PER_OPPORTUNITY
                    or remaining <= 0
                ):
                    break
            if (
                len(selected) >= MAX_CONTENT_POINT_CANDIDATES_PER_OPPORTUNITY
                or remaining <= 0
            ):
                break
        result.append(
            OpportunityContentPointCandidates(
                opportunity.recommendation_id,
                tuple(selected),
            )
        )
    return tuple(result)


def operation_evidence_texts(
    specification: BaseChangePlanSpecification,
    catalog: ChangePlanEvidenceCatalog,
) -> tuple[str, ...]:
    pages = catalog.page_by_id()
    sources = catalog.source_by_id()
    values: list[str] = []
    for reference in specification.page_refs:
        if reference in pages:
            values.extend(page_evidence_text(pages[reference]))
    for reference in specification.source_refs:
        if reference in sources:
            values.extend((sources[reference].title, sources[reference].content))
    return tuple(values)


def source_evidence_texts(
    specification: BaseChangePlanSpecification,
    catalog: ChangePlanEvidenceCatalog,
) -> tuple[str, ...]:
    sources = catalog.source_by_id()
    return tuple(
        value
        for reference in specification.source_refs
        if reference in sources
        for value in (sources[reference].title, sources[reference].content)
    )


def derive_section_locator(
    specification: BaseChangePlanSpecification,
    catalog: ChangePlanEvidenceCatalog,
) -> tuple[SectionLocator | None, str | None]:
    locator = specification.locator
    pages = catalog.page_by_id()
    if locator.locator_kind is SectionLocatorKind.NEW_PAGE:
        if locator.page_ref is not None or locator.target_heading is not None:
            return None, ChangePlanValidationCategory.TARGET_LOCATOR_INVALID.value
        return SectionLocator(SectionLocatorKind.NEW_PAGE, None, None, None, None), None
    if locator.page_ref is None or locator.page_ref not in pages:
        return None, ChangePlanValidationCategory.UNKNOWN_PAGE_REFERENCE.value
    if locator.locator_kind is SectionLocatorKind.PAGE_LEVEL:
        if locator.target_heading is not None:
            return None, ChangePlanValidationCategory.TARGET_LOCATOR_INVALID.value
        return SectionLocator(SectionLocatorKind.PAGE_LEVEL, locator.page_ref, None, None, None), None
    heading = locator.target_heading
    if not _is_bounded_text(heading, MAX_PROPOSED_HEADING_CHARS):
        return None, ChangePlanValidationCategory.TARGET_LOCATOR_INVALID.value
    page = pages[locator.page_ref]
    if heading not in provider_visible_headings(page):
        return None, ChangePlanValidationCategory.TARGET_LOCATOR_INVALID.value
    kinds: set[ObservedHeadingKind] = set()
    if heading in page.h1:
        kinds.add(ObservedHeadingKind.H1)
    if heading in page.h2:
        kinds.add(ObservedHeadingKind.H2)
    matching_blocks = tuple(
        block
        for block in page.structured_content
        if block.heading == heading and block.kind is not StructuredContentKind.IMAGE_ALT
    )
    if matching_blocks:
        kinds.add(ObservedHeadingKind.STRUCTURED_HEADING)
    if not kinds:
        return None, ChangePlanValidationCategory.TARGET_LOCATOR_INVALID.value
    heading_kind = next(iter(kinds)) if len(kinds) == 1 else ObservedHeadingKind.SEMANTIC_ONLY
    context_source = next(
        (block.text for block in matching_blocks if block.text), page.body_text or heading
    )
    context = " ".join(context_source.split())[:MAX_OBSERVED_CONTEXT_CHARS].rstrip()
    return SectionLocator(
        SectionLocatorKind.EXACT_OBSERVED_HEADING,
        locator.page_ref,
        heading,
        heading_kind,
        context,
    ), None


def validate_common_specification(
    specification: BaseChangePlanSpecification,
    catalog: ChangePlanEvidenceCatalog,
) -> str | None:
    opportunities = catalog.opportunity_by_id()
    pages = catalog.page_by_id()
    sources = catalog.source_by_id()
    opportunity = opportunities.get(specification.opportunity_ref)
    if opportunity is None:
        return ChangePlanValidationCategory.UNKNOWN_OPPORTUNITY_REFERENCE.value
    if (
        not isinstance(specification.page_refs, tuple)
        or len(specification.page_refs) > MAX_PAGE_REFS_PER_OPERATION
        or len(specification.page_refs) != len(set(specification.page_refs))
    ):
        return ChangePlanValidationCategory.FIELD_CONTRACT.value
    if (
        not isinstance(specification.source_refs, tuple)
        or len(specification.source_refs) > MAX_SOURCE_REFS_PER_OPERATION
        or len(specification.source_refs) != len(set(specification.source_refs))
    ):
        return ChangePlanValidationCategory.FIELD_CONTRACT.value
    if any(reference not in pages for reference in specification.page_refs):
        return ChangePlanValidationCategory.UNKNOWN_PAGE_REFERENCE.value
    if any(reference not in sources for reference in specification.source_refs):
        return ChangePlanValidationCategory.UNKNOWN_SOURCE_REFERENCE.value
    if not set(specification.page_refs).issubset(opportunity.page_refs):
        return ChangePlanValidationCategory.EVIDENCE_USE_NOT_ALLOWED.value
    if not set(specification.source_refs).issubset(opportunity.source_refs):
        return ChangePlanValidationCategory.EVIDENCE_USE_NOT_ALLOWED.value
    if specification.source_action_code not in opportunity.action_codes:
        return ChangePlanValidationCategory.OPERATION_NOT_ALLOWED.value
    if specification.operation_type not in CHANGE_OPERATION_COMPATIBILITY[
        specification.source_action_code
    ]:
        return ChangePlanValidationCategory.OPERATION_NOT_ALLOWED.value
    return None


def _validate_phrase(
    value: object,
    maximum: int,
    evidence: tuple[str, ...],
    *,
    proposed: bool = False,
) -> str | None:
    if not _is_bounded_text(value, maximum) or has_forbidden_prose_syntax(value):
        return ChangePlanValidationCategory.FIELD_CONTRACT.value
    assert isinstance(value, str)
    if contains_absence_claim(value):
        return ChangePlanValidationCategory.UNSUPPORTED_ABSENCE_CLAIM.value
    grounded = (
        proposed_label_is_grounded(value, evidence)
        if proposed
        else phrase_is_grounded(value, evidence)
    )
    if not grounded:
        return ChangePlanValidationCategory.CONTENT_NOT_GROUNDED.value
    return None


def _validate_content_points(
    points: tuple[ContentPointSpecification, ...], evidence: tuple[str, ...],
    *, maximum: int = MAX_CONTENT_POINTS_PER_OPERATION,
) -> str | None:
    if not MIN_CONTENT_POINTS_PER_OPERATION <= len(points) <= maximum:
        return ChangePlanValidationCategory.FIELD_CONTRACT.value
    for point in points:
        if not isinstance(point.intent, ContentPointIntent):
            return ChangePlanValidationCategory.FIELD_CONTRACT.value
        error = _validate_phrase(point.subject, MAX_CONTENT_POINT_SUBJECT_CHARS, evidence)
        if error is not None:
            return error
    return None


def _content_point_origins_are_cited(
    points: tuple[ContentPointSpecification, ...],
    specification: BaseChangePlanSpecification,
) -> bool:
    return all(
        point.origin_ref
        in (
            specification.page_refs
            if point.origin_ref.startswith("P")
            else specification.source_refs
        )
        for point in points
    )


def _validate_table(
    table: ComparisonTableSpecification, evidence: tuple[str, ...]
) -> str | None:
    if not _valid_string_tuple(
        table.column_headers,
        MIN_TABLE_COLUMNS,
        MAX_TABLE_COLUMNS,
        MAX_TABLE_LABEL_CHARS,
    ) or not _valid_string_tuple(
        table.row_dimensions,
        MIN_TABLE_DIMENSIONS,
        MAX_TABLE_DIMENSIONS,
        MAX_TABLE_LABEL_CHARS,
    ):
        return ChangePlanValidationCategory.FIELD_CONTRACT.value
    for value in (*table.column_headers, *table.row_dimensions):
        error = _validate_phrase(value, MAX_TABLE_LABEL_CHARS, evidence)
        if error is not None:
            return error
    return None


def _build_grounding_violation(
    specification: BaseChangePlanSpecification,
    *,
    field_path: str,
    value: str,
    evidence: tuple[str, ...],
    cited_ref_ids: tuple[str, ...],
    proposed: bool,
) -> GroundingViolation:
    normalized = normalized_evidence_text(value)
    opportunity_ref, slot, *_ = field_path.split(".")
    if proposed:
        tokens = tuple(
            token
            for token in re.findall(r"[^\W_]+", normalized)
            if token not in _PROPOSAL_WORDS
        )
        evidence_tokens = {
            token
            for text in evidence
            for token in re.findall(r"[^\W_]+", normalized_evidence_text(text))
        }
        matched = sum(token in evidence_tokens for token in tokens)
        return GroundingViolation(
            opportunity_ref=opportunity_ref,
            slot=slot,
            operation_type=specification.operation_type,
            field_path=field_path,
            grounding_mode=GroundingMode.TOKEN_RECOMBINATION,
            cited_ref_ids=cited_ref_ids,
            normalized_length=len(normalized),
            token_coverage_pass=bool(tokens) and matched == len(tokens),
            normalized_token_count=len(tokens),
            matched_token_count=matched,
        )
    return GroundingViolation(
        opportunity_ref=opportunity_ref,
        slot=slot,
        operation_type=specification.operation_type,
        field_path=field_path,
        grounding_mode=GroundingMode.VERBATIM_CONTIGUOUS,
        cited_ref_ids=cited_ref_ids,
        normalized_length=len(normalized),
        contiguous_match=phrase_is_grounded(value, evidence),
    )


def diagnose_grounding_violation(
    specification: ChangePlanSpecification,
    catalog: ChangePlanEvidenceCatalog,
    *,
    field_path: str,
) -> GroundingViolation | None:
    """Locate an already-rejected grounding field without changing validation."""

    evidence = operation_evidence_texts(specification, catalog)
    sources = source_evidence_texts(specification, catalog)
    all_refs = (*specification.page_refs, *specification.source_refs)

    def phrase_violation(
        value: str,
        suffix: str,
        *,
        proposed: bool = False,
        source_only: bool = False,
    ) -> GroundingViolation | None:
        allowed_evidence = sources if source_only else evidence
        error = _validate_phrase(
            value,
            MAX_PROPOSED_HEADING_CHARS
            if suffix.endswith(("proposed_heading", "proposed_title"))
            else MAX_OUTLINE_HEADING_CHARS
            if ".outline_headings[" in suffix
            else MAX_TABLE_LABEL_CHARS
            if "column_headers[" in suffix or "row_dimensions[" in suffix
            else MAX_ANCHOR_INTENT_CHARS
            if suffix.endswith("anchor_intent")
            else MAX_CONTENT_POINT_SUBJECT_CHARS,
            allowed_evidence,
            proposed=proposed,
        )
        if error != ChangePlanValidationCategory.CONTENT_NOT_GROUNDED.value:
            return None
        return _build_grounding_violation(
            specification,
            field_path=f"{field_path}.{suffix}",
            value=value,
            evidence=allowed_evidence,
            cited_ref_ids=(
                specification.source_refs if source_only else all_refs
            ),
            proposed=proposed,
        )

    def content_point_violation(
        points: tuple[ContentPointSpecification, ...],
    ) -> GroundingViolation | None:
        for index, point in enumerate(points):
            violation = phrase_violation(
                point.subject,
                f"content_points[{index}].subject",
            )
            if violation is not None:
                return violation
        return None

    def table_violation(
        table: ComparisonTableSpecification,
        prefix: str = "",
    ) -> GroundingViolation | None:
        for name, values in (
            ("column_headers", table.column_headers),
            ("row_dimensions", table.row_dimensions),
        ):
            for index, value in enumerate(values):
                violation = phrase_violation(
                    value,
                    f"{prefix}{name}[{index}]",
                )
                if violation is not None:
                    return violation
        return None

    if isinstance(specification, ExpandSectionSpecification):
        return content_point_violation(specification.content_points)
    if isinstance(specification, AddSectionSpecification):
        return phrase_violation(
            specification.proposed_heading,
            "proposed_heading",
            proposed=True,
            source_only=True,
        ) or content_point_violation(specification.content_points)
    if isinstance(specification, AddComparisonTableSpecification):
        return phrase_violation(
            specification.proposed_heading,
            "proposed_heading",
            proposed=True,
        ) or table_violation(specification.comparison_table_specification)
    if isinstance(specification, AddInternalLinkSpecification):
        return phrase_violation(
            specification.internal_link_specification.anchor_intent,
            "anchor_intent",
        )
    if isinstance(specification, CreateNewResourceSpecification):
        resource = specification.new_resource_specification
        violation = phrase_violation(
            resource.proposed_title,
            "proposed_title",
            proposed=True,
            source_only=True,
        )
        if violation is not None:
            return violation
        for index, heading in enumerate(resource.outline_headings):
            violation = phrase_violation(
                heading,
                f"outline_headings[{index}]",
                proposed=True,
                source_only=True,
            )
            if violation is not None:
                return violation
        violation = content_point_violation(resource.content_points)
        if violation is not None:
            return violation
        if resource.comparison_table_specification is not None:
            return table_violation(
                resource.comparison_table_specification,
                "comparison_table_brief.",
            )
    return None


def validate_and_finalize_specification(
    number: int,
    specification: ChangePlanSpecification,
    catalog: ChangePlanEvidenceCatalog,
    *,
    first_party_scope: FirstPartyPlanningScope | None = None,
    task_id: str | None = None,
) -> tuple[ChangeOperation | None, str | None]:
    """Validate one strict specification and deterministically finalize it."""

    common_error = validate_common_specification(specification, catalog)
    if common_error is not None:
        return None, common_error
    capability_error = comparison_operation_error(specification)
    if capability_error is not None:
        return None, capability_error
    p_only = first_party_scope is not None
    if p_only:
        if isinstance(specification, ExpandSectionSpecification) and any(
            point.intent is ContentPointIntent.COMPARE for point in specification.content_points
        ):
            return None, ChangePlanValidationCategory.COMPARISON_UNAVAILABLE.value
        scope = first_party_scope
        opportunity = catalog.opportunity_by_id()[specification.opportunity_ref]
        if (
            not isinstance(scope, FirstPartyPlanningScope)
            or not scope.matches_task(task_id)
            or not scope.matches_packet(catalog.site_content)
            or catalog.page_by_id() != {p.evidence_id: p for p in scope.site_content.pages}
            or catalog.sources
            or not isinstance(specification, ExpandSectionSpecification)
            or specification.operation_type is not ChangeOperationType.EXPAND_SECTION
            or specification.source_action_code is not ContentOpportunityActionCode.EXPAND_PAGE_SECTION
            or opportunity.recommendation_id != "R1"
            or opportunity.action_codes != (ContentOpportunityActionCode.EXPAND_PAGE_SECTION,)
            or opportunity.opportunity_type is not ContentOpportunityType.EXPAND_OBSERVED_CONTENT
            or opportunity.topic != scope.heading or opportunity.source_refs or opportunity.audit_refs
            or opportunity.page_refs != (scope.page_ref,)
            or specification.page_refs != (scope.page_ref,) or specification.source_refs
            or specification.locator != SectionLocatorSpecification(SectionLocatorKind.EXACT_OBSERVED_HEADING, scope.page_ref, scope.heading)
            or tuple(point.subject for point in specification.content_points) != scope.quotes
            or any(point.origin_ref != scope.page_ref or point.intent not in {ContentPointIntent.DESCRIBE, ContentPointIntent.SUMMARIZE} for point in specification.content_points)
        ):
            return None, ChangePlanValidationCategory.EVIDENCE_USE_NOT_ALLOWED.value
    locator, locator_error = derive_section_locator(specification, catalog)
    if locator is None:
        return None, locator_error
    evidence = operation_evidence_texts(specification, catalog)
    sources = source_evidence_texts(specification, catalog)
    pages = catalog.page_by_id()
    proposed_heading: str | None = None
    content_points: tuple[ContentPoint, ...] = ()
    comparison: ComparisonTableSpec | None = None
    internal_link: InternalLinkSpec | None = None
    new_resource: NewResourceSpec | None = None
    ordered_headings: tuple[str, ...] = ()
    section_purpose: SectionPurpose | None = None
    target_kind = ChangeTargetKind.MODIFY_EXISTING_PAGE

    if isinstance(specification, ExpandSectionSpecification):
        if not _content_point_origins_are_cited(
            specification.content_points, specification
        ):
            return None, ChangePlanValidationCategory.EVIDENCE_USE_NOT_ALLOWED.value
        if (
            len(specification.page_refs) < MIN_EXISTING_PAGE_REFS_PER_OPERATION
            or len(specification.source_refs) < (0 if p_only else MIN_SOURCE_REFS_PER_OPERATION)
        ):
            category = (
                ChangePlanValidationCategory.UNKNOWN_PAGE_REFERENCE
                if not specification.page_refs
                else ChangePlanValidationCategory.UNKNOWN_SOURCE_REFERENCE
            )
            return None, category.value
        if specification.locator.page_ref not in specification.page_refs:
            return None, ChangePlanValidationCategory.EVIDENCE_USE_NOT_ALLOWED.value
        error = _validate_content_points(
            specification.content_points, evidence,
            maximum=MAX_FIRST_PARTY_EXCERPTS if p_only else MAX_CONTENT_POINTS_PER_OPERATION,
        )
        if error:
            return None, error
        content_points = tuple(
            ContentPoint(item.intent, item.subject) for item in specification.content_points
        )
    elif isinstance(specification, ProposeSectionReorderSpecification):
        if (
            len(specification.page_refs) != REORDER_PAGE_REFS
            or len(specification.source_refs) < MIN_SOURCE_REFS_PER_OPERATION
        ):
            return None, ChangePlanValidationCategory.EVIDENCE_USE_NOT_ALLOWED.value
        page_ref = specification.page_refs[0]
        if specification.locator.locator_kind is not SectionLocatorKind.PAGE_LEVEL or specification.locator.page_ref != page_ref:
            return None, ChangePlanValidationCategory.TARGET_LOCATOR_INVALID.value
        if not _valid_string_tuple(
            specification.ordered_headings,
            MIN_REORDER_HEADINGS,
            MAX_REORDER_HEADINGS,
            MAX_PROPOSED_HEADING_CHARS,
        ):
            return None, ChangePlanValidationCategory.FIELD_CONTRACT.value
        page = pages[page_ref]
        observed = set(provider_visible_headings(page))
        if any(heading not in observed for heading in specification.ordered_headings):
            return None, ChangePlanValidationCategory.TARGET_LOCATOR_INVALID.value
        ordered_headings = specification.ordered_headings
    elif isinstance(specification, AddSectionSpecification):
        if not _content_point_origins_are_cited(
            specification.content_points, specification
        ):
            return None, ChangePlanValidationCategory.EVIDENCE_USE_NOT_ALLOWED.value
        if (
            len(specification.page_refs) < MIN_EXISTING_PAGE_REFS_PER_OPERATION
            or len(specification.source_refs) < MIN_SOURCE_REFS_PER_OPERATION
        ):
            return None, ChangePlanValidationCategory.EVIDENCE_USE_NOT_ALLOWED.value
        if specification.locator.page_ref not in specification.page_refs:
            return None, ChangePlanValidationCategory.EVIDENCE_USE_NOT_ALLOWED.value
        expected = {
            ContentOpportunityActionCode.ADD_BUYER_GUIDANCE: SectionPurpose.BUYER_GUIDANCE,
            ContentOpportunityActionCode.ADD_TECHNICAL_DOCUMENTATION: SectionPurpose.TECHNICAL_DOCUMENTATION,
        }.get(specification.source_action_code)
        if expected is not specification.section_purpose:
            return None, ChangePlanValidationCategory.OPERATION_NOT_ALLOWED.value
        target_page = pages[specification.locator.page_ref]
        proposed_normalized = normalized_evidence_text(specification.proposed_heading)
        if proposed_normalized in {
            normalized_evidence_text(heading)
            for heading in provider_visible_headings(target_page)
        }:
            return None, ChangePlanValidationCategory.TARGET_LOCATOR_INVALID.value
        error = _validate_phrase(
            specification.proposed_heading,
            MAX_PROPOSED_HEADING_CHARS,
            sources,
            proposed=True,
        ) or _validate_content_points(specification.content_points, evidence)
        if error:
            return None, error
        proposed_heading = specification.proposed_heading
        section_purpose = specification.section_purpose
        content_points = tuple(
            ContentPoint(item.intent, item.subject) for item in specification.content_points
        )
    elif isinstance(specification, AddComparisonTableSpecification):
        if (
            len(specification.page_refs) < MIN_EXISTING_PAGE_REFS_PER_OPERATION
            or len(specification.source_refs) < MIN_SOURCE_REFS_PER_OPERATION
        ):
            return None, ChangePlanValidationCategory.EVIDENCE_USE_NOT_ALLOWED.value
        if specification.locator.page_ref not in specification.page_refs:
            return None, ChangePlanValidationCategory.EVIDENCE_USE_NOT_ALLOWED.value
        error = _validate_phrase(
            specification.proposed_heading,
            MAX_PROPOSED_HEADING_CHARS,
            evidence,
            proposed=True,
        ) or _validate_table(specification.comparison_table_specification, evidence)
        if error:
            return None, error
        proposed_heading = specification.proposed_heading
        comparison = ComparisonTableSpec(
            specification.comparison_table_specification.column_headers,
            specification.comparison_table_specification.row_dimensions,
        )
    elif isinstance(specification, AddInternalLinkSpecification):
        link = specification.internal_link_specification
        if (
            len(specification.source_refs) < MIN_SOURCE_REFS_PER_OPERATION
            or len(specification.page_refs) < MIN_INTERNAL_LINK_PAGE_REFS
        ):
            return None, ChangePlanValidationCategory.INTERNAL_LINK_INVALID.value
        if (
            link.source_page_ref == link.target_page_ref
            or link.source_page_ref not in specification.page_refs
            or link.target_page_ref not in specification.page_refs
            or specification.locator.locator_kind is not SectionLocatorKind.PAGE_LEVEL
            or specification.locator.page_ref != link.source_page_ref
        ):
            return None, ChangePlanValidationCategory.INTERNAL_LINK_INVALID.value
        source_origin = canonical_url_origin(pages[link.source_page_ref].final_url)
        target_origin = canonical_url_origin(pages[link.target_page_ref].final_url)
        if source_origin is None or source_origin != target_origin:
            return None, ChangePlanValidationCategory.INTERNAL_LINK_INVALID.value
        error = _validate_phrase(link.anchor_intent, MAX_ANCHOR_INTENT_CHARS, evidence)
        if error:
            return None, error
        internal_link = InternalLinkSpec(
            link.source_page_ref,
            link.target_page_ref,
            pages[link.source_page_ref].final_url,
            pages[link.target_page_ref].final_url,
            link.anchor_intent,
        )
    elif isinstance(specification, CreateNewResourceSpecification):
        resource = specification.new_resource_specification
        if not _content_point_origins_are_cited(resource.content_points, specification):
            return None, ChangePlanValidationCategory.EVIDENCE_USE_NOT_ALLOWED.value
        if (
            len(specification.source_refs) < MIN_SOURCE_REFS_PER_OPERATION
            or specification.locator.locator_kind is not SectionLocatorKind.NEW_PAGE
        ):
            return None, ChangePlanValidationCategory.EVIDENCE_USE_NOT_ALLOWED.value
        if any(ref not in specification.page_refs for ref in resource.suggested_source_page_refs):
            return None, ChangePlanValidationCategory.EVIDENCE_USE_NOT_ALLOWED.value
        if not _valid_string_tuple(
            resource.outline_headings,
            MIN_OUTLINE_HEADINGS,
            MAX_OUTLINE_HEADINGS,
            MAX_OUTLINE_HEADING_CHARS,
        ):
            return None, ChangePlanValidationCategory.FIELD_CONTRACT.value
        expected_purpose = NEW_RESOURCE_PURPOSE_BY_ACTION.get(
            specification.source_action_code
        )
        if resource.resource_purpose is not expected_purpose:
            return None, ChangePlanValidationCategory.OPERATION_NOT_ALLOWED.value
        error = _validate_phrase(resource.proposed_title, MAX_PROPOSED_HEADING_CHARS, sources, proposed=True)
        if error is None:
            for heading in resource.outline_headings:
                error = _validate_phrase(heading, MAX_OUTLINE_HEADING_CHARS, sources, proposed=True)
                if error:
                    break
        if error is None:
            error = _validate_content_points(resource.content_points, evidence)
        if error is None and resource.comparison_table_specification is not None:
            error = _validate_table(resource.comparison_table_specification, evidence)
        if error:
            return None, error
        if (
            specification.source_action_code is ContentOpportunityActionCode.ADD_COMPARISON_TABLE
            and resource.comparison_table_specification is None
        ):
            return None, ChangePlanValidationCategory.OPERATION_NOT_ALLOWED.value
        nested = None
        if resource.comparison_table_specification is not None:
            nested = ComparisonTableSpec(
                resource.comparison_table_specification.column_headers,
                resource.comparison_table_specification.row_dimensions,
            )
        finalized_points = tuple(
            ContentPoint(item.intent, item.subject) for item in resource.content_points
        )
        new_resource = NewResourceSpec(
            resource.resource_purpose,
            resource.proposed_title,
            resource.outline_headings,
            finalized_points,
            resource.suggested_source_page_refs,
            nested,
        )
        proposed_heading = resource.proposed_title
        content_points = finalized_points
        comparison = nested
        target_kind = ChangeTargetKind.CREATE_NEW_PAGE
    else:
        return None, ChangePlanValidationCategory.FIELD_CONTRACT.value

    return ChangeOperation(
        change_id=f"C{number}",
        opportunity_ref=specification.opportunity_ref,
        source_action_code=specification.source_action_code,
        operation_type=specification.operation_type,
        target_kind=target_kind,
        locator=locator,
        proposed_heading=proposed_heading,
        content_points=content_points,
        comparison_table_spec=comparison,
        internal_link_spec=internal_link,
        new_resource_spec=new_resource,
        page_refs=specification.page_refs,
        source_refs=specification.source_refs,
        ordered_headings=ordered_headings,
        section_purpose=section_purpose,
        audit_refs=catalog.opportunity_by_id()[
            specification.opportunity_ref
        ].audit_refs,
    ), None
