"""Provider-independent types for evidence-grounded site optimization drafts."""

from dataclasses import dataclass
from enum import Enum
import json
import re
from urllib.parse import urlsplit

from .audit import AuditEvidence, AuditEvidenceCategory, AuditEvidenceOutcome


MAX_REQUEST_URL_CHARS = 2_048
MAX_RESEARCH_TOPIC_CHARS = 200
MAX_PRODUCT_TERMS = 5
MAX_PRODUCT_TERM_CHARS = 80
MAX_TARGET_MARKETS = 3
MAX_TARGET_MARKET_CHARS = 80
MAX_AUDIT_EVIDENCE = 24
MAX_AUDIT_MATERIAL_CHARS = 8_000
MAX_SOURCES = 6
MAX_SOURCE_TITLE_CHARS = 200
MAX_SOURCE_CONTENT_CHARS = 1_000
MAX_TOTAL_SOURCE_CONTENT_CHARS = 6_000
MAX_DYNAMIC_MATERIAL_CHARS = 16_000
MAX_RECOMMENDATIONS = 5
MAX_ACTIONS = 3
MAX_TITLE_CHARS = 160
MAX_RATIONALE_CHARS = 600
MAX_ACTION_CHARS = 240


class OptimizationStatus(str, Enum):
    SUCCESS = "success"
    AUDIT_FAILED = "audit_failed"
    INSUFFICIENT_AUDIT_EVIDENCE = "insufficient_audit_evidence"
    SEARCH_FAILED = "search_failed"
    NO_SEARCH_RESULTS = "no_search_results"
    GENERATION_FAILED = "generation_failed"
    INVALID_OUTPUT = "invalid_output"
    WORKFLOW_TIMEOUT = "workflow_timeout"


class OptimizationGenerationStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"


class RecommendationKind(str, Enum):
    TECHNICAL_FIX = "TECHNICAL_FIX"
    POLICY_REVIEW = "POLICY_REVIEW"
    CONTENT_OPPORTUNITY = "CONTENT_OPPORTUNITY"


class RecommendationPriority(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class EvidenceUse(str, Enum):
    TECHNICAL_FIX = "TECHNICAL_FIX"
    POLICY_REVIEW = "POLICY_REVIEW"
    CONTEXT_ONLY = "CONTEXT_ONLY"


class TechnicalConstraint(str, Enum):
    PAGE_APPROPRIATE_SCHEMA_REVIEW_ONLY = (
        "PAGE_APPROPRIATE_SCHEMA_REVIEW_ONLY"
    )


@dataclass(frozen=True, slots=True)
class EvidenceUseClassification:
    allowed_uses: tuple[EvidenceUse, ...]
    technical_constraint: TechnicalConstraint | None = None


_ACTIONABLE_TECHNICAL_ABSENCE_KEYS = frozenset(
    {
        "meta.title.present",
        "meta.description.present",
        "meta.canonical.present",
        "content.h1.present",
        "schema.any_present",
    }
)
_ACTIONABLE_TECHNICAL_WARNING_KEYS = frozenset(
    {
        "schema.json_parse_errors",
        "schema.missing_fields",
        "schema.incomplete_types",
    }
)
_POLICY_REVIEW_CATEGORIES = frozenset(
    {
        AuditEvidenceCategory.ROBOTS,
        AuditEvidenceCategory.LLMS,
        AuditEvidenceCategory.AI_DISCOVERY,
    }
)


def classify_audit_evidence_use(
    evidence: AuditEvidence,
) -> EvidenceUseClassification:
    """Classify one bounded audit observation for optimization use."""

    if not isinstance(evidence, AuditEvidence):
        raise TypeError("Evidence-use classification requires AuditEvidence.")
    technical_allowed = (
        evidence.outcome is AuditEvidenceOutcome.ABSENT
        and evidence.check_key in _ACTIONABLE_TECHNICAL_ABSENCE_KEYS
    ) or (
        evidence.outcome is AuditEvidenceOutcome.WARNING
        and evidence.check_key in _ACTIONABLE_TECHNICAL_WARNING_KEYS
    )
    if technical_allowed:
        constraint = (
            TechnicalConstraint.PAGE_APPROPRIATE_SCHEMA_REVIEW_ONLY
            if evidence.check_key == "schema.any_present"
            else None
        )
        return EvidenceUseClassification(
            (EvidenceUse.TECHNICAL_FIX,),
            constraint,
        )
    if evidence.category in _POLICY_REVIEW_CATEGORIES:
        return EvidenceUseClassification((EvidenceUse.POLICY_REVIEW,))
    return EvidenceUseClassification((EvidenceUse.CONTEXT_ONLY,))


@dataclass(frozen=True, slots=True)
class SiteOptimizationRequest:
    url: str
    research_topic: str
    product_terms: tuple[str, ...]
    target_markets: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if type(self.url) is not str or not self.url.strip():
            raise ValueError("Site optimization URL must be a non-empty string.")
        url = self.url.strip()
        if len(url) > MAX_REQUEST_URL_CHARS or any(char.isspace() for char in url):
            raise ValueError("Site optimization URL is invalid or too long.")
        try:
            parsed = urlsplit(url)
            valid_port = parsed.port
        except ValueError as exc:
            raise ValueError("Site optimization URL is invalid.") from exc
        if (
            parsed.scheme.casefold() not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or valid_port is not None and not 0 < valid_port < 65_536
        ):
            raise ValueError("Site optimization URL must be a public HTTP(S) URL without credentials.")

        topic = self._bounded_text(
            self.research_topic,
            "research_topic",
            MAX_RESEARCH_TOPIC_CHARS,
        )
        products = self._bounded_tuple(
            self.product_terms,
            "product_terms",
            min_items=1,
            max_items=MAX_PRODUCT_TERMS,
            max_chars=MAX_PRODUCT_TERM_CHARS,
        )
        markets = self._bounded_tuple(
            self.target_markets,
            "target_markets",
            min_items=0,
            max_items=MAX_TARGET_MARKETS,
            max_chars=MAX_TARGET_MARKET_CHARS,
        )
        object.__setattr__(self, "url", url)
        object.__setattr__(self, "research_topic", topic)
        object.__setattr__(self, "product_terms", products)
        object.__setattr__(self, "target_markets", markets)

    @staticmethod
    def _bounded_text(value: object, name: str, limit: int) -> str:
        if type(value) is not str or not value.strip() or len(value.strip()) > limit:
            raise ValueError(f"{name} must be a non-empty string of at most {limit} characters.")
        return " ".join(value.split())

    @classmethod
    def _bounded_tuple(
        cls,
        value: object,
        name: str,
        *,
        min_items: int,
        max_items: int,
        max_chars: int,
    ) -> tuple[str, ...]:
        if type(value) is not tuple or not min_items <= len(value) <= max_items:
            raise ValueError(f"{name} must contain between {min_items} and {max_items} items.")
        return tuple(cls._bounded_text(item, name, max_chars) for item in value)


@dataclass(frozen=True, slots=True)
class NumberedAuditEvidence:
    evidence_id: str
    evidence: AuditEvidence

    def __post_init__(self) -> None:
        if re.fullmatch(r"A[1-9][0-9]*", self.evidence_id) is None:
            raise ValueError("Audit evidence ID must use the A1 format.")
        if not isinstance(self.evidence, AuditEvidence):
            raise TypeError("Numbered audit evidence requires AuditEvidence.")


@dataclass(frozen=True, slots=True)
class OptimizationSourceMaterial:
    source_id: str
    title: str
    content: str

    def __post_init__(self) -> None:
        if re.fullmatch(r"S[1-9][0-9]*", self.source_id) is None:
            raise ValueError("Source material ID must use the S1 format.")
        if type(self.title) is not str or not self.title.strip() or len(self.title) > MAX_SOURCE_TITLE_CHARS:
            raise ValueError("Source material title is invalid or too long.")
        if type(self.content) is not str or not self.content.strip() or len(self.content) > MAX_SOURCE_CONTENT_CHARS:
            raise ValueError("Source material content is invalid or too long.")


@dataclass(frozen=True, slots=True)
class OptimizationSource:
    source_id: str
    title: str
    url: str


@dataclass(frozen=True, slots=True)
class OptimizationPrompt:
    research_topic: str
    product_terms: tuple[str, ...]
    target_markets: tuple[str, ...]
    audit_evidence: tuple[NumberedAuditEvidence, ...]
    sources: tuple[OptimizationSourceMaterial, ...]

    def _audit_payload(self) -> list[dict[str, object]]:
        payload: list[dict[str, object]] = []
        for item in self.audit_evidence:
            classification = classify_audit_evidence_use(item.evidence)
            payload.append(
                {
                    "evidence_id": item.evidence_id,
                    "category": item.evidence.category.value,
                    "check_key": item.evidence.check_key,
                    "observed_value": item.evidence.observed_value,
                    "outcome": item.evidence.outcome.value,
                    "provider_field": item.evidence.provider_field,
                    "note": item.evidence.note,
                    "allowed_uses": [
                        use.value for use in classification.allowed_uses
                    ],
                    "technical_constraint": (
                        None
                        if classification.technical_constraint is None
                        else classification.technical_constraint.value
                    ),
                }
            )
        return payload

    def material_json(self) -> str:
        return json.dumps(
            {
                "research_topic": self.research_topic,
                "product_terms": self.product_terms,
                "target_markets": self.target_markets,
                "audit_evidence": self._audit_payload(),
                "external_sources": [
                    {
                        "source_id": source.source_id,
                        "title": source.title,
                        "content": source.content,
                    }
                    for source in self.sources
                ],
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )

    def audit_material_chars(self) -> int:
        return len(json.dumps(self._audit_payload(), ensure_ascii=False, separators=(",", ":")))

    def dynamic_material_chars(self) -> int:
        return len(self.material_json())


@dataclass(frozen=True, slots=True)
class OptimizationGeneration:
    provider: str
    model: str
    status: OptimizationGenerationStatus
    text: str | None
    error: str | None

    def __post_init__(self) -> None:
        if not self.provider.strip() or not self.model.strip():
            raise ValueError("Optimization generation requires provider metadata.")
        if self.status is OptimizationGenerationStatus.SUCCESS:
            if self.text is None or not self.text.strip() or self.error is not None:
                raise ValueError("Successful optimization generation requires text and no error.")
        elif self.text is not None or not self.error:
            raise ValueError("Failed optimization generation requires no text and an error.")


@dataclass(frozen=True, slots=True)
class OptimizationRecommendation:
    recommendation_id: str
    kind: RecommendationKind
    priority: RecommendationPriority
    target_category: AuditEvidenceCategory | None
    site_gap_claimed: bool
    title: str
    rationale: str
    actions: tuple[str, ...]
    audit_refs: tuple[str, ...]
    source_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SiteOptimizationReport:
    url: str
    status: OptimizationStatus
    recommendations: tuple[OptimizationRecommendation, ...]
    audit_evidence: tuple[NumberedAuditEvidence, ...]
    sources: tuple[OptimizationSource, ...]
    error: str | None
    limitations: tuple[str, ...] = ()
    requires_human_review: bool = True

    def __post_init__(self) -> None:
        if not self.requires_human_review:
            raise ValueError("Site optimization reports always require human review.")
        if self.status is OptimizationStatus.SUCCESS:
            if not self.recommendations or not self.audit_evidence or not self.sources or self.error is not None:
                raise ValueError("Successful optimization reports require recommendations and both evidence sets.")
            return
        if self.recommendations or self.audit_evidence or self.sources or not self.error:
            raise ValueError("Failed optimization reports cannot carry a successful report payload.")
