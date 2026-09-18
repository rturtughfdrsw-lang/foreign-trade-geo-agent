"""Provider-independent data types for AI visibility monitoring."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Mapping


class ResponseStatus(str, Enum):
    """Outcome of one provider call."""

    SUCCESS = "success"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class Citation:
    """Minimal citation data shared across providers."""

    url: str
    title: str | None = None

    def __post_init__(self) -> None:
        if not self.url.strip():
            raise ValueError("A citation requires a non-empty URL.")


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    """Raw provider outcome before brand and competitor analysis."""

    provider: str
    model: str
    status: ResponseStatus
    text: str | None
    citations: tuple[Citation, ...]
    error: str | None

    def __post_init__(self) -> None:
        if not self.provider.strip():
            raise ValueError("A provider response requires a provider name.")
        if not self.model.strip():
            raise ValueError("A provider response requires a model name.")

        if self.status is ResponseStatus.SUCCESS:
            if self.text is None or self.error is not None:
                raise ValueError("A successful provider response requires text and no error.")
            return

        if self.text is not None or self.citations or not self.error:
            raise ValueError(
                "A failed provider response requires no text or citations and a non-empty error."
            )


@dataclass(frozen=True, slots=True)
class VisibilityObservation:
    """Brand analysis for one prompt and one provider response."""

    prompt: str
    provider: str
    model: str
    response: ProviderResponse
    target_mentioned: bool | None
    mentioned_competitors: tuple[str, ...]
    timestamp: datetime

    def __post_init__(self) -> None:
        if self.provider != self.response.provider or self.model != self.response.model:
            raise ValueError("Observation provider metadata must match its response.")

        if self.response.status is ResponseStatus.FAILED:
            if self.target_mentioned is not None or self.mentioned_competitors:
                raise ValueError("A failed response cannot contain mention observations.")
            return

        if self.target_mentioned is None:
            raise ValueError("A successful response requires a target mention observation.")


@dataclass(frozen=True, slots=True)
class VisibilityReport:
    """Aggregate visibility metrics for one monitoring run."""

    target_brand: str
    total_attempts: int
    successful_observations: int
    failed_observations: int
    mentioned_count: int
    mention_rate: float | None
    competitor_mention_counts: Mapping[str, int]
    competitor_mention_rates: Mapping[str, float | None]
    citation_count: int
    observations: tuple[VisibilityObservation, ...]
