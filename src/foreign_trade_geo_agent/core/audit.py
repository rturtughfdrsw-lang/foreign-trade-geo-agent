"""Core data types for site audits."""

from dataclasses import dataclass
from enum import Enum
from typing import Mapping


class AuditStatus(str, Enum):
    """Business-level outcome of a site audit."""

    SUCCESS = "success"
    FAILED = "failed"


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

    def __post_init__(self) -> None:
        if self.status is AuditStatus.SUCCESS:
            if self.score is None or self.error is not None:
                raise ValueError("A successful audit requires a score and no error.")
            return

        if self.score is not None or not self.error:
            raise ValueError("A failed audit requires no score and a non-empty error.")
