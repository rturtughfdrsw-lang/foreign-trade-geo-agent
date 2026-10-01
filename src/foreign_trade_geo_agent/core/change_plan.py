"""Provider-independent, evidence-grounded change-plan contracts."""

from dataclasses import dataclass
from enum import Enum
import json
import re
from types import MappingProxyType
import unicodedata

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
    build_content_opportunity_evidence_catalog,
    finalized_content_opportunity_error,
    parse_safe_http_url,
)
from .fetching import UrlOrigin
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
MAX_CONTENT_POINT_SUBJECT_CHARS = 120
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
MAX_INPUT_ENVELOPE_CHARS = 36_000
MAX_INPUT_ENVELOPE_BYTES = 76 * 1024
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
    TARGET_LOCATOR_INVALID = "TARGET_LOCATOR_INVALID"
    EVIDENCE_USE_NOT_ALLOWED = "EVIDENCE_USE_NOT_ALLOWED"
    CONTENT_NOT_GROUNDED = "CONTENT_NOT_GROUNDED"
    INTERNAL_LINK_INVALID = "INTERNAL_LINK_INVALID"
    UNSUPPORTED_ABSENCE_CLAIM = "UNSUPPORTED_ABSENCE_CLAIM"
    INPUT_TOO_LARGE = "INPUT_TOO_LARGE"


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
            f"content point subject: at most {MAX_CONTENT_POINT_SUBJECT_CHARS} characters.",
            f"- proposed heading or title: at most {MAX_PROPOSED_HEADING_CHARS} characters.",
            f"- ordered_headings: {MIN_REORDER_HEADINGS} to {MAX_REORDER_HEADINGS}; "
            f"ordered heading: at most {MAX_PROPOSED_HEADING_CHARS} characters.",
            f"- outline_headings: {MIN_OUTLINE_HEADINGS} to {MAX_OUTLINE_HEADINGS}; "
            f"outline heading: at most {MAX_OUTLINE_HEADING_CHARS} characters.",
            f"- table columns: {MIN_TABLE_COLUMNS} to {MAX_TABLE_COLUMNS}; "
            f"table dimensions: {MIN_TABLE_DIMENSIONS} to {MAX_TABLE_DIMENSIONS}; "
            f"table label: at most {MAX_TABLE_LABEL_CHARS} characters.",
            f"- anchor_intent: at most {MAX_ANCHOR_INTENT_CHARS} characters.",
            f"- suggested_source_page_refs: {MIN_PAGE_REFS_PER_OPERATION} to "
            f"{MAX_PAGE_REFS_PER_OPERATION}.",
            f"- PROPOSE_SECTION_REORDER requires exactly {REORDER_PAGE_REFS} page_ref.",
        )
    )


@dataclass(frozen=True, slots=True)
class ChangePlanInput:
    site_content: SiteContentPacket
    opportunities: ContentOpportunityReport

    def __post_init__(self) -> None:
        if not isinstance(self.site_content, SiteContentPacket):
            raise TypeError("Change plan input requires SiteContentPacket.")
        if not isinstance(self.opportunities, ContentOpportunityReport):
            raise TypeError("Change plan input requires ContentOpportunityReport.")
        if self.opportunities.status is not ContentOpportunityStatus.SUCCESS:
            raise ValueError("Change plan input requires a successful opportunity report.")


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
class ChangePlanEvidenceCatalog:
    opportunities: tuple[ChangePlanOpportunityEvidence, ...]
    pages: tuple[ChangePlanPageEvidence, ...]
    sources: tuple[ChangePlanSourceEvidence, ...]

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

    def __post_init__(self) -> None:
        if not isinstance(self.input, ChangePlanInput) or not isinstance(
            self.catalog, ChangePlanEvidenceCatalog
        ):
            raise ValueError("Change plan prompt is invalid.")

    def material_json(self) -> str:
        """Serialize only bounded P/S/R evidence and the evidence-use contract."""

        payload = {
            "contract": {
                "evidence_scope": SiteContentEvidenceScope.OBSERVED_PRESENT_ONLY.value,
                "supports_absence_claims": False,
                "requires_human_review": True,
                "semantic_locators_only": True,
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
                }
                for item in self.catalog.opportunities
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
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


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
    return ChangePlanPrompt(
        input=value,
        catalog=ChangePlanEvidenceCatalog(
            opportunities=tuple(
                ChangePlanOpportunityEvidence(item) for item in opportunity_items
            ),
            pages=pages,
            sources=sources,
        ),
    )


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
    catalog = build_content_opportunity_evidence_catalog(packet, materials)
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
        if finalized_content_opportunity_error(
            item,
            expected_number,
            catalog,
            materials,
        ) is not None:
            return ChangePlanValidationCategory.FIELD_CONTRACT.value
    return None


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
            valid = (
                existing_target
                and self.proposed_heading is None
                and MIN_CONTENT_POINTS_PER_OPERATION
                <= len(self.content_points)
                <= MAX_CONTENT_POINTS_PER_OPERATION
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


@dataclass(frozen=True, slots=True)
class ChangePlanReport:
    status: ChangePlanStatus
    operations: tuple[ChangeOperation, ...]
    limitations: tuple[str, ...]
    error: str | None
    requires_human_review: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.status, ChangePlanStatus) or not self.requires_human_review:
            raise ValueError("Change plan reports require human review.")
        if not isinstance(self.operations, tuple) or not all(
            isinstance(item, ChangeOperation) for item in self.operations
        ):
            raise ValueError("Change plan operations are invalid.")
        if self.status is ChangePlanStatus.SUCCESS:
            if self.error is not None or self.limitations != CHANGE_PLAN_LIMITATIONS:
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
    context = " ".join(context_source.split())[:MAX_OBSERVED_CONTEXT_CHARS]
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
    points: tuple[ContentPointSpecification, ...], evidence: tuple[str, ...]
) -> str | None:
    if not MIN_CONTENT_POINTS_PER_OPERATION <= len(points) <= MAX_CONTENT_POINTS_PER_OPERATION:
        return ChangePlanValidationCategory.FIELD_CONTRACT.value
    for point in points:
        if not isinstance(point.intent, ContentPointIntent):
            return ChangePlanValidationCategory.FIELD_CONTRACT.value
        error = _validate_phrase(point.subject, MAX_CONTENT_POINT_SUBJECT_CHARS, evidence)
        if error is not None:
            return error
    return None


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


def validate_and_finalize_specification(
    number: int,
    specification: ChangePlanSpecification,
    catalog: ChangePlanEvidenceCatalog,
) -> tuple[ChangeOperation | None, str | None]:
    """Validate one strict specification and deterministically finalize it."""

    common_error = validate_common_specification(specification, catalog)
    if common_error is not None:
        return None, common_error
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
        if (
            len(specification.page_refs) < MIN_EXISTING_PAGE_REFS_PER_OPERATION
            or len(specification.source_refs) < MIN_SOURCE_REFS_PER_OPERATION
        ):
            category = (
                ChangePlanValidationCategory.UNKNOWN_PAGE_REFERENCE
                if not specification.page_refs
                else ChangePlanValidationCategory.UNKNOWN_SOURCE_REFERENCE
            )
            return None, category.value
        if specification.locator.page_ref not in specification.page_refs:
            return None, ChangePlanValidationCategory.EVIDENCE_USE_NOT_ALLOWED.value
        error = _validate_content_points(specification.content_points, evidence)
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
    ), None
