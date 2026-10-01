"""Provider-independent models for evidence-grounded content opportunities."""

from dataclasses import dataclass
from enum import Enum
import json
import re
from types import MappingProxyType
import unicodedata
from urllib.parse import SplitResult, urlsplit, urlunsplit

from .extraction import PageExtractionStatus, StructuredContentKind
from .research import (
    ResearchEvidenceClassification,
    ResearchReport,
    ResearchStatus,
)
from .site_content import SiteContentEvidenceScope, SiteContentPacket


MAX_SITE_PAGES = 5
MAX_SITE_PACKET_CHARS = 16_000
MAX_SITE_PACKET_BYTES = 32 * 1024
MAX_RESEARCH_SOURCES = 4
MAX_SOURCE_TITLE_CHARS = 160
MAX_CONTENT_OPPORTUNITY_SOURCE_URL_CHARS = 2_048
# Public client-report site URLs are preserved whole up to this bound.
MAX_CONTENT_OPPORTUNITY_CLIENT_SITE_URL_CHARS = 2_048
MAX_SOURCE_CONTENT_CHARS = 750
MAX_TOTAL_SOURCE_CONTENT_CHARS = 3_000
MAX_SOURCE_PACKET_CHARS = 4_000
MAX_SOURCE_PACKET_BYTES = 12 * 1024
MAX_SYSTEM_PROMPT_CHARS = 6_000
MAX_SYSTEM_PROMPT_BYTES = 12 * 1024
MAX_USER_MATERIAL_CHARS = 22_000
MAX_USER_MATERIAL_BYTES = 48 * 1024
MAX_INPUT_ENVELOPE_CHARS = 28_000
MAX_INPUT_ENVELOPE_BYTES = 60 * 1024
MAX_OPPORTUNITIES = 4
MAX_ACTION_CODES = 3
MAX_TOPIC_CHARS = 120
MAX_RAW_OUTPUT_CHARS = 12_000
MAX_RAW_OUTPUT_BYTES = 24 * 1024

CONTENT_OPPORTUNITY_LIMITATIONS = (
    "P evidence records observed page content only and never supports absence claims.",
    "S evidence is unverified external search context, not an authoritative or native AI-platform citation.",
    "Truncated inputs are incomplete and cannot establish that omitted content is absent.",
    "Opportunities do not guarantee rankings, AI mentions, or inquiries and require human review.",
)


class ContentOpportunityStatus(str, Enum):
    SUCCESS = "success"
    INSUFFICIENT_RESEARCH_EVIDENCE = "insufficient_research_evidence"
    INPUT_TOO_LARGE = "input_too_large"
    GENERATION_FAILED = "generation_failed"
    INVALID_OUTPUT = "invalid_output"
    WORKFLOW_TIMEOUT = "workflow_timeout"


class ContentOpportunityGenerationStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"


class ContentOpportunityType(str, Enum):
    EXPAND_OBSERVED_CONTENT = "EXPAND_OBSERVED_CONTENT"
    REORGANIZE_OBSERVED_CONTENT = "REORGANIZE_OBSERVED_CONTENT"
    NEW_SUPPORTING_CONTENT = "NEW_SUPPORTING_CONTENT"


class ContentOpportunityPriority(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ContentOpportunityActionCode(str, Enum):
    EXPAND_PAGE_SECTION = "EXPAND_PAGE_SECTION"
    REORGANIZE_PAGE_SECTIONS = "REORGANIZE_PAGE_SECTIONS"
    CREATE_SUPPORTING_RESOURCE = "CREATE_SUPPORTING_RESOURCE"
    ADD_BUYER_GUIDANCE = "ADD_BUYER_GUIDANCE"
    ADD_TECHNICAL_DOCUMENTATION = "ADD_TECHNICAL_DOCUMENTATION"
    ADD_COMPARISON_TABLE = "ADD_COMPARISON_TABLE"
    ADD_INTERNAL_LINK = "ADD_INTERNAL_LINK"


OPPORTUNITY_ACTION_COMPATIBILITY = MappingProxyType(
    {
        ContentOpportunityType.EXPAND_OBSERVED_CONTENT: frozenset(
            {
                ContentOpportunityActionCode.EXPAND_PAGE_SECTION,
                ContentOpportunityActionCode.ADD_COMPARISON_TABLE,
                ContentOpportunityActionCode.ADD_INTERNAL_LINK,
            }
        ),
        ContentOpportunityType.REORGANIZE_OBSERVED_CONTENT: frozenset(
            {
                ContentOpportunityActionCode.REORGANIZE_PAGE_SECTIONS,
                ContentOpportunityActionCode.ADD_COMPARISON_TABLE,
                ContentOpportunityActionCode.ADD_INTERNAL_LINK,
            }
        ),
        ContentOpportunityType.NEW_SUPPORTING_CONTENT: frozenset(
            {
                ContentOpportunityActionCode.CREATE_SUPPORTING_RESOURCE,
                ContentOpportunityActionCode.ADD_BUYER_GUIDANCE,
                ContentOpportunityActionCode.ADD_TECHNICAL_DOCUMENTATION,
                ContentOpportunityActionCode.ADD_COMPARISON_TABLE,
                ContentOpportunityActionCode.ADD_INTERNAL_LINK,
            }
        ),
    }
)

CONTENT_OPPORTUNITY_ABSENCE_TERMS = (
    "missing",
    "lacks",
    "lack of",
    "not present",
    "absent",
    "缺少",
    "缺失",
    "未覆盖",
    "遗漏",
    "没有",
)
# Backward-compatible private alias for already-reviewed internal callers.
_ABSENCE_TERMS = CONTENT_OPPORTUNITY_ABSENCE_TERMS
_PAGE_DIRECTED_ACTIONS = frozenset(
    {
        ContentOpportunityActionCode.EXPAND_PAGE_SECTION,
        ContentOpportunityActionCode.REORGANIZE_PAGE_SECTIONS,
        ContentOpportunityActionCode.ADD_INTERNAL_LINK,
    }
)


def opportunity_actions_are_compatible(
    opportunity_type: ContentOpportunityType,
    action_codes: tuple[ContentOpportunityActionCode, ...],
) -> bool:
    """Return whether every action is allowed for the selected opportunity type."""

    allowed_actions = OPPORTUNITY_ACTION_COMPATIBILITY[opportunity_type]
    return all(action in allowed_actions for action in action_codes)


def render_opportunity_action_compatibility() -> str:
    """Render deterministic model instructions from the shared compatibility rules."""

    lines = ["Allowed action_codes by opportunity_type:"]
    for opportunity_type in ContentOpportunityType:
        lines.append(f"{opportunity_type.value}:")
        allowed_actions = OPPORTUNITY_ACTION_COMPATIBILITY[opportunity_type]
        lines.extend(
            f"- {action.value}"
            for action in ContentOpportunityActionCode
            if action in allowed_actions
        )
    lines.extend(
        (
            "Rules:",
            "- Only choose action_codes listed for the chosen opportunity_type.",
            "- Do not combine actions from another opportunity_type.",
            "- Return fewer opportunities or [] if no valid combination is supported.",
        )
    )
    return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class ContentOpportunitySourceMaterial:
    source_id: str
    title: str
    content: str
    content_truncated: bool

    def __post_init__(self) -> None:
        if re.fullmatch(r"S[1-9][0-9]*", self.source_id) is None:
            raise ValueError("Opportunity source ID must use the S1 format.")
        if not self.title or len(self.title) > MAX_SOURCE_TITLE_CHARS:
            raise ValueError("Opportunity source title is invalid.")
        if not self.content or len(self.content) > MAX_SOURCE_CONTENT_CHARS:
            raise ValueError("Opportunity source content is invalid.")
        if type(self.content_truncated) is not bool:
            raise ValueError("Opportunity source truncation state is invalid.")


@dataclass(frozen=True, slots=True)
class OpportunityPageEvidence:
    evidence_id: str
    extraction_status: PageExtractionStatus
    content_truncated: bool
    structured_content_truncated: bool
    evidence_scope: SiteContentEvidenceScope
    supports_absence_claims: bool
    has_observed_present: bool
    context_only_only: bool


@dataclass(frozen=True, slots=True)
class OpportunitySourceEvidence:
    evidence_id: str
    content_truncated: bool
    classifications: tuple[ResearchEvidenceClassification, ...]


@dataclass(frozen=True, slots=True)
class OpportunityEvidenceCatalog:
    """Single evidence-use catalog shared by serialization and validation."""

    pages: tuple[OpportunityPageEvidence, ...]
    sources: tuple[OpportunitySourceEvidence, ...]

    def page_by_id(self) -> dict[str, OpportunityPageEvidence]:
        return {page.evidence_id: page for page in self.pages}

    def source_by_id(self) -> dict[str, OpportunitySourceEvidence]:
        return {source.evidence_id: source for source in self.sources}

    def payload(self) -> dict[str, object]:
        return {
            "pages": [
                {
                    "evidence_id": page.evidence_id,
                    "extraction_status": page.extraction_status.value,
                    "content_truncated": page.content_truncated,
                    "structured_content_truncated": page.structured_content_truncated,
                    "evidence_scope": page.evidence_scope.value,
                    "supports_absence_claims": page.supports_absence_claims,
                    "has_observed_present": page.has_observed_present,
                    "context_only_only": page.context_only_only,
                }
                for page in self.pages
            ],
            "sources": [
                {
                    "evidence_id": source.evidence_id,
                    "content_truncated": source.content_truncated,
                    "classifications": tuple(
                        classification.value
                        for classification in source.classifications
                    ),
                }
                for source in self.sources
            ],
        }


@dataclass(frozen=True, slots=True)
class ContentOpportunityPrompt:
    site_content: SiteContentPacket
    catalog: OpportunityEvidenceCatalog
    sources: tuple[ContentOpportunitySourceMaterial, ...]
    research_sources_truncated: bool

    @property
    def evidence_catalog(self) -> OpportunityEvidenceCatalog:
        return self.catalog

    def source_material_json(self) -> str:
        return json.dumps(
            {
                "classifications": (
                    ResearchEvidenceClassification.EXTERNAL_RESEARCH_CONTEXT.value,
                    ResearchEvidenceClassification.UNVERIFIED_SEARCH_RESULT.value,
                ),
                "sources": [
                    {
                        "source_id": source.source_id,
                        "title": source.title,
                        "content": source.content,
                        "content_truncated": source.content_truncated,
                    }
                    for source in self.sources
                ],
                "selection_truncated": self.research_sources_truncated,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )

    def material_json(self) -> str:
        return json.dumps(
            {
                "contract": {
                    "evidence_scope": "observed_present_only",
                    "supports_absence_claims": False,
                    "untrusted_data": True,
                    "allow_empty_opportunities": True,
                },
                "site_content": json.loads(self.site_content.to_json()),
                "evidence_catalog": self.catalog.payload(),
                "external_research": json.loads(self.source_material_json()),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )


@dataclass(frozen=True, slots=True)
class ContentOpportunityGeneration:
    provider: str
    model: str
    status: ContentOpportunityGenerationStatus
    text: str | None
    error: str | None

    def __post_init__(self) -> None:
        if not self.provider.strip() or not self.model.strip():
            raise ValueError("Content opportunity generation requires provider metadata.")
        if self.status is ContentOpportunityGenerationStatus.SUCCESS:
            if self.text is None or not self.text.strip() or self.error is not None:
                raise ValueError("Successful content opportunity generation is invalid.")
        elif self.text is not None or not self.error:
            raise ValueError("Failed content opportunity generation is invalid.")


@dataclass(frozen=True, slots=True)
class ContentOpportunitySpecification:
    opportunity_type: ContentOpportunityType
    priority: ContentOpportunityPriority
    topic: str
    action_codes: tuple[ContentOpportunityActionCode, ...]
    page_refs: tuple[str, ...]
    source_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ContentOpportunityPage:
    evidence_id: str
    final_url: str
    title: str | None


@dataclass(frozen=True, slots=True)
class ContentOpportunitySource:
    source_id: str
    title: str
    url: str
    classifications: tuple[ResearchEvidenceClassification, ...]

    def __post_init__(self) -> None:
        if re.fullmatch(r"S[1-9][0-9]*", self.source_id) is None:
            raise ValueError("Opportunity source ID must use the S1 format.")
        if (
            type(self.title) is not str
            or not self.title
            or self.title != " ".join(self.title.split())
            or len(self.title) > MAX_SOURCE_TITLE_CHARS
        ):
            raise ValueError("Opportunity source title is invalid.")
        if _normalized_source_url(self.url) is None:
            raise ValueError("Opportunity source URL is invalid or too long.")
        if self.classifications != (
            ResearchEvidenceClassification.EXTERNAL_RESEARCH_CONTEXT,
            ResearchEvidenceClassification.UNVERIFIED_SEARCH_RESULT,
        ):
            raise ValueError("Opportunity source classifications are invalid.")


@dataclass(frozen=True, slots=True)
class PreparedContentOpportunitySources:
    materials: tuple[ContentOpportunitySourceMaterial, ...]
    sources: tuple[ContentOpportunitySource, ...]
    selection_truncated: bool


def parse_safe_http_url(
    value: object,
    *,
    max_chars: int | None = None,
) -> SplitResult | None:
    """Parse HTTP(S) without credentials, whitespace, controls, or invalid ports."""

    if (
        type(value) is not str
        or not value
        or max_chars is not None and len(value) > max_chars
        or any(
            character.isspace() or unicodedata.category(character) == "Cc"
            for character in value
        )
    ):
        return None
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except (TypeError, ValueError):
        return None
    if (
        parsed.scheme.casefold() not in {"http", "https"}
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or port is not None and not 0 < port < 65_536
    ):
        return None
    return parsed


def _normalized_source_url(url: str) -> str | None:
    parsed = parse_safe_http_url(
        url,
        max_chars=MAX_CONTENT_OPPORTUNITY_SOURCE_URL_CHARS,
    )
    if parsed is None:
        return None
    port = parsed.port
    scheme = parsed.scheme.casefold()
    host = parsed.hostname.casefold()
    if port is not None and not (
        (scheme == "http" and port == 80)
        or (scheme == "https" and port == 443)
    ):
        host = f"{host}:{port}"
    return urlunsplit((scheme, host, parsed.path or "/", parsed.query, ""))


def prepare_content_opportunity_sources(
    report: ResearchReport,
) -> PreparedContentOpportunitySources | None:
    """Return the canonical bounded sources for the opportunity workflow."""

    if report.status is not ResearchStatus.SUCCESS or report.research_evidence is None:
        return None
    material_by_id = {
        material.source_id: material
        for material in report.research_evidence.materials
    }
    selected: list[ContentOpportunitySourceMaterial] = []
    display: list[ContentOpportunitySource] = []
    seen_urls: set[str] = set()
    total_content = 0
    usable_seen = 0
    classifications = report.research_evidence.classifications

    for source in report.sources:
        material = material_by_id.get(source.source_id)
        if material is None:
            return None
        if (
            type(material.title) is not str
            or type(material.content) is not str
            or type(material.url) is not str
            or type(source.title) is not str
            or type(source.url) is not str
        ):
            continue
        if material.title != source.title or material.url != source.url:
            return None
        normalized_url = _normalized_source_url(material.url)
        title = " ".join(material.title.split())
        content = " ".join(material.content.split())
        if normalized_url is None or not title or not content:
            continue
        if normalized_url in seen_urls:
            continue
        seen_urls.add(normalized_url)
        usable_seen += 1
        if len(selected) >= MAX_RESEARCH_SOURCES:
            continue
        remaining = MAX_TOTAL_SOURCE_CONTENT_CHARS - total_content
        if remaining <= 0:
            continue
        bounded_title = title[:MAX_SOURCE_TITLE_CHARS]
        bounded_content = content[: min(MAX_SOURCE_CONTENT_CHARS, remaining)]
        total_content += len(bounded_content)
        selected.append(
            ContentOpportunitySourceMaterial(
                source_id=source.source_id,
                title=bounded_title,
                content=bounded_content,
                content_truncated=len(bounded_content) < len(content),
            )
        )
        display.append(
            ContentOpportunitySource(
                source_id=source.source_id,
                title=bounded_title,
                url=source.url,
                classifications=classifications,
            )
        )
    if not selected:
        return None
    return PreparedContentOpportunitySources(
        materials=tuple(selected),
        sources=tuple(display),
        selection_truncated=usable_seen > len(selected),
    )


@dataclass(frozen=True, slots=True)
class ContentOpportunity:
    recommendation_id: str
    opportunity_type: ContentOpportunityType
    priority: ContentOpportunityPriority
    topic: str
    title: str
    rationale: str
    actions: tuple[str, ...]
    page_refs: tuple[str, ...]
    source_refs: tuple[str, ...]
    action_codes: tuple[ContentOpportunityActionCode, ...] = ()

    def __post_init__(self) -> None:
        if (
            not isinstance(self.action_codes, tuple)
            or len(self.action_codes) > MAX_ACTION_CODES
            or not all(
                isinstance(code, ContentOpportunityActionCode)
                for code in self.action_codes
            )
            or len(self.action_codes) != len(set(self.action_codes))
        ):
            raise ValueError("Content opportunity action provenance is invalid.")


def build_content_opportunity_evidence_catalog(
    packet: SiteContentPacket,
    sources: tuple[ContentOpportunitySourceMaterial, ...],
) -> OpportunityEvidenceCatalog:
    """Build the evidence-use contract shared by generation and validation."""

    pages: list[OpportunityPageEvidence] = []
    for page in packet.pages:
        has_observed = page.extraction_status is PageExtractionStatus.SUCCESS and (
            bool(page.body_text and page.body_text.strip())
            or any(
                block.kind is not StructuredContentKind.IMAGE_ALT
                for block in page.structured_content
            )
        )
        has_context = any(
            block.kind is StructuredContentKind.IMAGE_ALT
            for block in page.structured_content
        )
        pages.append(
            OpportunityPageEvidence(
                evidence_id=page.evidence_id,
                extraction_status=page.extraction_status,
                content_truncated=page.content_truncated,
                structured_content_truncated=page.structured_content_truncated,
                evidence_scope=packet.evidence_scope,
                supports_absence_claims=packet.supports_absence_claims,
                has_observed_present=has_observed,
                context_only_only=has_context and not has_observed,
            )
        )
    classifications = (
        ResearchEvidenceClassification.EXTERNAL_RESEARCH_CONTEXT,
        ResearchEvidenceClassification.UNVERIFIED_SEARCH_RESULT,
    )
    return OpportunityEvidenceCatalog(
        pages=tuple(pages),
        sources=tuple(
            OpportunitySourceEvidence(
                evidence_id=source.source_id,
                content_truncated=source.content_truncated,
                classifications=classifications,
            )
            for source in sources
        ),
    )


def validate_content_opportunity_topic(
    value: object,
) -> tuple[str | None, str | None]:
    """Normalize and validate one provider-supplied opportunity topic."""

    if type(value) is not str or "\n" in value or "\r" in value:
        return None, "FIELD_CONTRACT"
    topic = " ".join(value.split())
    if not topic or len(topic) > MAX_TOPIC_CHARS:
        return None, "FIELD_CONTRACT"
    if re.search(
        r"(?:[a-z][a-z0-9+.-]*://|www\.|"
        r"\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,63}\b|"
        r"\b(?:[a-z0-9-]+\.)+[a-z]{2,63}(?:/[^\s]*)?|"
        r"\b[PSA][1-9][0-9]*\b|\[[PSA][^\]]*\])",
        topic,
        flags=re.IGNORECASE,
    ):
        return None, "FIELD_CONTRACT"
    folded = unicodedata.normalize("NFKC", topic).casefold()
    if any(term in folded for term in _ABSENCE_TERMS):
        return None, "UNSUPPORTED_ABSENCE_CLAIM"
    return topic, None


def _validate_opportunity_refs(
    values: object,
    prefix: str,
    known: set[str],
) -> tuple[tuple[str, ...] | None, str | None]:
    if not isinstance(values, tuple) or any(type(item) is not str for item in values):
        return None, "FIELD_CONTRACT"
    if len(values) != len(set(values)):
        return None, "UNKNOWN_OR_DUPLICATE_REFERENCE"
    for reference in values:
        namespace = re.fullmatch(r"([PSA])[1-9][0-9]*", reference)
        if namespace is not None and namespace.group(1) != prefix:
            return None, "REFERENCE_NAMESPACE_NOT_ALLOWED"
        if (
            re.fullmatch(fr"{prefix}[1-9][0-9]*", reference) is None
            or reference not in known
        ):
            return None, "UNKNOWN_OR_DUPLICATE_REFERENCE"
    return values, None


def validate_content_opportunity_specification(
    specification: ContentOpportunitySpecification,
    catalog: OpportunityEvidenceCatalog,
    sources: tuple[ContentOpportunitySourceMaterial, ...],
) -> str | None:
    """Return an error category when a validated specification is inconsistent."""

    if (
        not isinstance(specification, ContentOpportunitySpecification)
        or not isinstance(specification.opportunity_type, ContentOpportunityType)
        or not isinstance(specification.priority, ContentOpportunityPriority)
    ):
        return "FIELD_CONTRACT"
    topic, topic_error = validate_content_opportunity_topic(specification.topic)
    if topic is None or topic != specification.topic:
        return topic_error or "FIELD_CONTRACT"
    action_codes = specification.action_codes
    if (
        not isinstance(action_codes, tuple)
        or not 1 <= len(action_codes) <= MAX_ACTION_CODES
        or not all(isinstance(code, ContentOpportunityActionCode) for code in action_codes)
        or len(action_codes) != len(set(action_codes))
    ):
        return "ACTION_NOT_ALLOWED"
    page_refs, page_error = _validate_opportunity_refs(
        specification.page_refs,
        "P",
        set(catalog.page_by_id()),
    )
    if page_refs is None:
        return page_error or "FIELD_CONTRACT"
    source_refs, source_error = _validate_opportunity_refs(
        specification.source_refs,
        "S",
        set(catalog.source_by_id()),
    )
    if source_refs is None:
        return source_error or "FIELD_CONTRACT"

    if specification.opportunity_type in {
        ContentOpportunityType.EXPAND_OBSERVED_CONTENT,
        ContentOpportunityType.REORGANIZE_OBSERVED_CONTENT,
    } and not page_refs:
        return "PAGE_REFERENCE_REQUIRED"
    if not source_refs:
        return "SOURCE_REFERENCE_REQUIRED"
    if any(action in _PAGE_DIRECTED_ACTIONS for action in action_codes) and not page_refs:
        return "PAGE_REFERENCE_REQUIRED"
    if not opportunity_actions_are_compatible(
        specification.opportunity_type,
        action_codes,
    ):
        return "OPPORTUNITY_TYPE_MISMATCH"

    page_by_id = catalog.page_by_id()
    if any(
        page_by_id[reference].extraction_status is not PageExtractionStatus.SUCCESS
        for reference in page_refs
    ):
        return "EVIDENCE_USE_NOT_ALLOWED"
    if specification.opportunity_type in {
        ContentOpportunityType.EXPAND_OBSERVED_CONTENT,
        ContentOpportunityType.REORGANIZE_OBSERVED_CONTENT,
    } and any(not page_by_id[reference].has_observed_present for reference in page_refs):
        return "EVIDENCE_USE_NOT_ALLOWED"

    source_by_id = {source.source_id: source for source in sources}
    if any(reference not in source_by_id for reference in source_refs):
        return "UNKNOWN_OR_DUPLICATE_REFERENCE"
    normalized_topic = " ".join(
        unicodedata.normalize("NFKC", topic).casefold().split()
    )
    grounded_texts = tuple(
        value
        for reference in source_refs
        for value in (
            source_by_id[reference].title,
            source_by_id[reference].content,
        )
    )
    if not any(
        normalized_topic
        in " ".join(unicodedata.normalize("NFKC", value).casefold().split())
        for value in grounded_texts
    ):
        return "TOPIC_NOT_GROUNDED"
    return None


def _render_content_opportunity_action(
    code: ContentOpportunityActionCode,
    topic: str,
    page_refs: str,
    source_refs: str,
) -> str:
    return {
        ContentOpportunityActionCode.EXPAND_PAGE_SECTION: f"Review {page_refs} and {source_refs}, then consider expanding the observed section about {topic}.",
        ContentOpportunityActionCode.REORGANIZE_PAGE_SECTIONS: f"Review {page_refs} and {source_refs}, then consider reorganizing the observed material about {topic}.",
        ContentOpportunityActionCode.CREATE_SUPPORTING_RESOURCE: f"Review {source_refs}, then consider a supporting resource about {topic}.",
        ContentOpportunityActionCode.ADD_BUYER_GUIDANCE: f"Review {source_refs}, then consider buyer guidance about {topic}.",
        ContentOpportunityActionCode.ADD_TECHNICAL_DOCUMENTATION: f"Review {source_refs}, then consider technical documentation about {topic}.",
        ContentOpportunityActionCode.ADD_COMPARISON_TABLE: f"Review {source_refs}, then consider a comparison table about {topic}.",
        ContentOpportunityActionCode.ADD_INTERNAL_LINK: f"After human review, consider linking {page_refs} to an approved resource about {topic}.",
    }[code]


def finalize_content_opportunity(
    number: int,
    specification: ContentOpportunitySpecification,
) -> ContentOpportunity:
    """Deterministically finalize one already-validated specification."""

    topic = specification.topic
    page_refs = ", ".join(specification.page_refs)
    source_refs = ", ".join(specification.source_refs)
    if specification.opportunity_type is ContentOpportunityType.EXPAND_OBSERVED_CONTENT:
        title = f"Expand observed {topic} content"
        rationale = (
            f"Observed page evidence {page_refs} contains content related to {topic}; "
            f"external research context {source_refs} is unverified and may be considered "
            "only after human review."
        )
    elif specification.opportunity_type is ContentOpportunityType.REORGANIZE_OBSERVED_CONTENT:
        title = f"Reorganize observed {topic} content"
        rationale = (
            f"Observed page evidence {page_refs} contains content related to {topic}; "
            f"external research context {source_refs} is unverified and may inform a "
            "human-reviewed reorganization."
        )
    else:
        title = f"Consider a supporting resource about {topic}"
        rationale = (
            f"External research context {source_refs} discusses {topic}; it is unverified "
            "and may inform consideration of a supporting resource after human review."
        )
        if page_refs:
            rationale += f" Observed page context {page_refs} may be reviewed for placement."
    actions = tuple(
        _render_content_opportunity_action(code, topic, page_refs, source_refs)
        for code in specification.action_codes
    )
    return ContentOpportunity(
        recommendation_id=f"R{number}",
        opportunity_type=specification.opportunity_type,
        priority=specification.priority,
        topic=topic,
        title=title,
        rationale=rationale,
        actions=actions,
        page_refs=specification.page_refs,
        source_refs=specification.source_refs,
        action_codes=specification.action_codes,
    )


def finalized_content_opportunity_error(
    item: ContentOpportunity,
    number: int,
    catalog: OpportunityEvidenceCatalog,
    sources: tuple[ContentOpportunitySourceMaterial, ...],
) -> str | None:
    """Validate one finalized opportunity against the shared business contract."""

    if not isinstance(item, ContentOpportunity):
        return "FIELD_CONTRACT"
    specification = ContentOpportunitySpecification(
        opportunity_type=item.opportunity_type,
        priority=item.priority,
        topic=item.topic,
        action_codes=item.action_codes,
        page_refs=item.page_refs,
        source_refs=item.source_refs,
    )
    error = validate_content_opportunity_specification(
        specification,
        catalog,
        sources,
    )
    if error is not None:
        return error
    if finalize_content_opportunity(number, specification) != item:
        return "FIELD_CONTRACT"
    return None


@dataclass(frozen=True, slots=True)
class ContentOpportunityReport:
    status: ContentOpportunityStatus
    opportunities: tuple[ContentOpportunity, ...]
    pages: tuple[ContentOpportunityPage, ...]
    sources: tuple[ContentOpportunitySource, ...]
    limitations: tuple[str, ...]
    error: str | None
    requires_human_review: bool = True
    source_materials: tuple[ContentOpportunitySourceMaterial, ...] = ()
    research_sources_truncated: bool = False

    def __post_init__(self) -> None:
        if not self.requires_human_review:
            raise ValueError("Content opportunity reports require human review.")
        if not isinstance(self.source_materials, tuple) or not all(
            isinstance(material, ContentOpportunitySourceMaterial)
            for material in self.source_materials
        ):
            raise ValueError("Content opportunity source materials are invalid.")
        if type(self.research_sources_truncated) is not bool:
            raise ValueError("Content opportunity source selection state is invalid.")
        if self.research_sources_truncated and not self.source_materials:
            raise ValueError("Truncated source selection requires retained materials.")
        if self.status is ContentOpportunityStatus.SUCCESS:
            if not self.sources or self.error is not None:
                raise ValueError("Successful content opportunity report is invalid.")
            return
        if (
            self.opportunities
            or self.pages
            or self.sources
            or self.source_materials
            or self.research_sources_truncated
            or not self.error
        ):
            raise ValueError("Failed content opportunity reports cannot carry payloads.")
