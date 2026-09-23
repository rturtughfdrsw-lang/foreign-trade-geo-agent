"""Provider-independent results for offline HTML page extraction."""

from dataclasses import dataclass
from enum import Enum


class PageExtractionStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"


class PageExtractionFailureKind(str, Enum):
    INVALID_INPUT = "invalid_input"
    EMPTY_CONTENT = "empty_content"
    EXTRACTION_FAILED = "extraction_failed"
    EXTRACTION_TIMEOUT = "extraction_timeout"
    INPUT_TOO_LARGE = "input_too_large"
    OUTPUT_TOO_LARGE = "output_too_large"
    WORKER_FAILED = "worker_failed"


@dataclass(frozen=True, slots=True)
class PageExtractionResult:
    final_url: str
    status: PageExtractionStatus
    title: str | None
    description: str | None
    canonical: str | None
    h1: tuple[str, ...]
    h2: tuple[str, ...]
    body_text: str | None
    published_date: str | None
    failure_kind: PageExtractionFailureKind | None
    error: str | None

    def __post_init__(self) -> None:
        if self.status is PageExtractionStatus.SUCCESS:
            if not self.body_text or self.failure_kind is not None or self.error is not None:
                raise ValueError("Successful page extraction result is inconsistent.")
        elif self.body_text is not None or self.failure_kind is None or not self.error:
            raise ValueError("Failed page extraction result is inconsistent.")
