"""Provider-independent data types for web search."""

from dataclasses import dataclass
from enum import Enum


class SearchStatus(str, Enum):
    """Outcome of one search provider call."""

    SUCCESS = "success"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class SearchResult:
    """One normalized web search result."""

    title: str
    url: str
    content: str
    score: float | None


@dataclass(frozen=True, slots=True)
class SearchResponse:
    """Normalized outcome from one search provider call."""

    query: str
    status: SearchStatus
    results: tuple[SearchResult, ...]
    error: str | None

    def __post_init__(self) -> None:
        if self.status is SearchStatus.SUCCESS:
            if self.error is not None:
                raise ValueError("A successful search response cannot contain an error.")
            return

        if self.results or not self.error:
            raise ValueError(
                "A failed search response requires no results and a non-empty error."
            )
