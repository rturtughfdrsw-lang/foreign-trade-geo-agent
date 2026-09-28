"""Provider-independent models for evidence-grounded content opportunities."""

from dataclasses import dataclass
from enum import Enum
import json
import re

from .extraction import PageExtractionStatus
from .research import ResearchEvidenceClassification
from .site_content import SiteContentEvidenceScope, SiteContentPacket


MAX_SITE_PAGES = 5
MAX_SITE_PACKET_CHARS = 16_000
MAX_SITE_PACKET_BYTES = 32 * 1024
MAX_RESEARCH_SOURCES = 4
MAX_SOURCE_TITLE_CHARS = 160
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


@dataclass(frozen=True, slots=True)
class ContentOpportunityReport:
    status: ContentOpportunityStatus
    opportunities: tuple[ContentOpportunity, ...]
    pages: tuple[ContentOpportunityPage, ...]
    sources: tuple[ContentOpportunitySource, ...]
    limitations: tuple[str, ...]
    error: str | None
    requires_human_review: bool = True

    def __post_init__(self) -> None:
        if not self.requires_human_review:
            raise ValueError("Content opportunity reports require human review.")
        if self.status is ContentOpportunityStatus.SUCCESS:
            if not self.sources or self.error is not None:
                raise ValueError("Successful content opportunity report is invalid.")
            return
        if self.opportunities or self.pages or self.sources or not self.error:
            raise ValueError("Failed content opportunity reports cannot carry payloads.")
