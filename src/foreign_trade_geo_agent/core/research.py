"""Provider-independent data types for sourced research drafts."""

from dataclasses import dataclass
from enum import Enum


class ResearchGenerationStatus(str, Enum):
    """Outcome of one research-writer call."""

    SUCCESS = "success"
    FAILED = "failed"


class ResearchStatus(str, Enum):
    """Outcome of the fixed industry-research workflow."""

    SUCCESS = "success"
    SEARCH_FAILED = "search_failed"
    NO_RESULTS = "no_results"
    GENERATION_FAILED = "generation_failed"
    INVALID_OUTPUT = "invalid_output"


@dataclass(frozen=True, slots=True)
class ResearchMaterial:
    """One bounded, untrusted source passed to a research writer."""

    source_id: str
    title: str
    url: str
    content: str


@dataclass(frozen=True, slots=True)
class ResearchGeneration:
    """Raw research-writer outcome before citation validation."""

    provider: str
    model: str
    status: ResearchGenerationStatus
    text: str | None
    error: str | None

    def __post_init__(self) -> None:
        if not self.provider.strip() or not self.model.strip():
            raise ValueError("A research generation requires provider metadata.")

        if self.status is ResearchGenerationStatus.SUCCESS:
            if self.text is None or not self.text.strip() or self.error is not None:
                raise ValueError(
                    "A successful research generation requires text and no error."
                )
            return

        if self.text is not None or not self.error:
            raise ValueError(
                "A failed research generation requires no text and a non-empty error."
            )


@dataclass(frozen=True, slots=True)
class ResearchSource:
    """Trusted display metadata copied from a validated search result."""

    source_id: str
    title: str
    url: str


@dataclass(frozen=True, slots=True)
class ResearchReport:
    """A sourced research draft that always requires human review."""

    question: str
    status: ResearchStatus
    draft_text: str | None
    sources: tuple[ResearchSource, ...]
    error: str | None
    requires_human_review: bool = True

    def __post_init__(self) -> None:
        if not self.requires_human_review:
            raise ValueError("Research reports must remain human-review drafts.")

        if self.status is ResearchStatus.SUCCESS:
            if (
                self.draft_text is None
                or not self.draft_text.strip()
                or not self.sources
                or self.error is not None
            ):
                raise ValueError(
                    "A successful research report requires a draft and sources."
                )
            return

        if self.draft_text is not None or self.sources or not self.error:
            raise ValueError(
                "A failed research report requires no draft or sources and an error."
            )
