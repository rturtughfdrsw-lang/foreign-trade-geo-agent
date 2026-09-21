"""Core data types for site audits."""

from dataclasses import dataclass
from enum import Enum
import math
from typing import Mapping, TypeAlias


MAX_EVIDENCE_COUNT = 96
MAX_EVIDENCE_STRING_LENGTH = 256
MAX_EVIDENCE_TUPLE_ITEMS = 20
MAX_EVIDENCE_TUPLE_ITEM_LENGTH = 128
MAX_CITABILITY_IMPROVEMENTS = 5
MAX_CITABILITY_IMPROVEMENT_LENGTH = 256


AuditEvidenceValue: TypeAlias = (
    bool | int | float | str | None | tuple[str, ...]
)


class AuditStatus(str, Enum):
    """Business-level outcome of a site audit."""

    SUCCESS = "success"
    FAILED = "failed"


class AuditEvidenceCategory(str, Enum):
    """Stable first-release categories for normalized site observations."""

    ROBOTS = "robots"
    LLMS = "llms"
    META = "meta"
    SCHEMA = "schema"
    CONTENT = "content"
    AI_DISCOVERY = "ai_discovery"


class AuditEvidenceOutcome(str, Enum):
    """How confidently one provider observation can be interpreted."""

    OBSERVED = "observed"
    PRESENT = "present"
    ABSENT = "absent"
    NOT_DETECTED = "not_detected"
    WARNING = "warning"
    CHECK_FAILED = "check_failed"
    UNKNOWN = "unknown"
    NOT_CHECKED = "not_checked"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True, slots=True)
class AuditEvidence:
    """One bounded, provider-attributed observation without a report ID."""

    category: AuditEvidenceCategory
    check_key: str
    observed_value: AuditEvidenceValue
    outcome: AuditEvidenceOutcome
    provider_field: str
    note: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.category, AuditEvidenceCategory):
            raise TypeError("Audit evidence category must be an AuditEvidenceCategory.")
        if not isinstance(self.outcome, AuditEvidenceOutcome):
            raise TypeError("Audit evidence outcome must be an AuditEvidenceOutcome.")
        self._validate_label(self.check_key, "check_key")
        self._validate_label(self.provider_field, "provider_field")
        if self.note is not None:
            self._validate_bounded_string(self.note, "note")
        self._validate_value(self.observed_value)

    @staticmethod
    def _validate_label(value: object, field_name: str) -> None:
        if type(value) is not str or not value.strip():
            raise ValueError(f"Audit evidence {field_name} must be a non-empty string.")
        AuditEvidence._validate_bounded_string(value, field_name)

    @staticmethod
    def _validate_bounded_string(value: str, field_name: str) -> None:
        if len(value) > MAX_EVIDENCE_STRING_LENGTH:
            raise ValueError(
                f"Audit evidence {field_name} exceeds "
                f"{MAX_EVIDENCE_STRING_LENGTH} characters."
            )

    @staticmethod
    def _validate_value(value: object) -> None:
        if value is None or type(value) in {bool, int}:
            return
        if type(value) is float:
            if not math.isfinite(value):
                raise ValueError("Audit evidence float values must be finite.")
            return
        if type(value) is str:
            AuditEvidence._validate_bounded_string(value, "observed_value")
            return
        if type(value) is tuple:
            if len(value) > MAX_EVIDENCE_TUPLE_ITEMS:
                raise ValueError(
                    "Audit evidence string tuples exceed "
                    f"{MAX_EVIDENCE_TUPLE_ITEMS} items."
                )
            for item in value:
                if type(item) is not str:
                    raise TypeError(
                        "Audit evidence tuple values must contain only strings."
                    )
                if len(item) > MAX_EVIDENCE_TUPLE_ITEM_LENGTH:
                    raise ValueError(
                        "Audit evidence tuple item exceeds "
                        f"{MAX_EVIDENCE_TUPLE_ITEM_LENGTH} characters."
                    )
            return
        raise TypeError("Audit evidence observed_value has an unsupported type.")


@dataclass(frozen=True, slots=True)
class CitabilitySummary:
    """Bounded upstream citability heuristic, kept separate from observations."""

    score: int
    grade: str
    improvements: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.score) is not int:
            raise TypeError("Citability score must be an integer.")
        if type(self.grade) is not str or not self.grade.strip():
            raise ValueError("Citability grade must be a non-empty string.")
        if len(self.grade) > MAX_EVIDENCE_STRING_LENGTH:
            raise ValueError("Citability grade is too long.")
        if type(self.improvements) is not tuple or any(
            type(item) is not str for item in self.improvements
        ):
            raise TypeError("Citability improvements must be a tuple of strings.")
        if len(self.improvements) > MAX_CITABILITY_IMPROVEMENTS:
            raise ValueError(
                "Citability improvements exceed "
                f"{MAX_CITABILITY_IMPROVEMENTS} items."
            )
        if any(
            len(item) > MAX_CITABILITY_IMPROVEMENT_LENGTH
            for item in self.improvements
        ):
            raise ValueError(
                "A citability improvement exceeds "
                f"{MAX_CITABILITY_IMPROVEMENT_LENGTH} characters."
            )


@dataclass(frozen=True, slots=True)
class SiteAuditResult:
    """Provider-independent result of one site audit."""

    url: str
    status: AuditStatus
    score: int | None
    band: str | None
    score_breakdown: Mapping[str, int]
    recommendations: tuple[str, ...]
    error: str | None
    source: str
    source_version: str
    evidence: tuple[AuditEvidence, ...] = ()
    citability: CitabilitySummary | None = None
    http_status: int | None = None
    audited_at: str | None = None
    audit_duration_ms: int | None = None

    def __post_init__(self) -> None:
        if type(self.evidence) is not tuple or any(
            not isinstance(item, AuditEvidence) for item in self.evidence
        ):
            raise TypeError("Site audit evidence must be a tuple of AuditEvidence.")
        if len(self.evidence) > MAX_EVIDENCE_COUNT:
            raise ValueError(
                f"Site audit evidence exceeds {MAX_EVIDENCE_COUNT} items."
            )
        if self.citability is not None and not isinstance(
            self.citability, CitabilitySummary
        ):
            raise TypeError("Site audit citability must be a CitabilitySummary.")

        if self.status is AuditStatus.SUCCESS:
            if self.score is None or self.error is not None:
                raise ValueError("A successful audit requires a score and no error.")
            return

        if self.score is not None or not self.error:
            raise ValueError("A failed audit requires no score and a non-empty error.")
        if self.evidence or self.citability is not None:
            raise ValueError("A failed audit cannot contain successful audit evidence.")
