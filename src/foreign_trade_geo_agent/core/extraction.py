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


class StructuredContentKind(str, Enum):
    TABLE = "table"
    DEFINITION_LIST = "definition_list"
    KEY_VALUE = "key_value"
    LIST = "list"
    SECTION = "section"
    IMAGE_ALT = "image_alt"


@dataclass(frozen=True, slots=True)
class StructuredContentBlock:
    kind: StructuredContentKind
    heading: str | None = None
    rows: tuple[tuple[str, ...], ...] = ()
    pairs: tuple[tuple[str, str], ...] = ()
    items: tuple[str, ...] = ()
    text: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, StructuredContentKind):
            raise ValueError("Structured content kind is invalid.")
        if self.heading is not None and (
            not isinstance(self.heading, str) or not self.heading
        ):
            raise ValueError("Structured content heading is invalid.")
        if self.text is not None and (not isinstance(self.text, str) or not self.text):
            raise ValueError("Structured content text is invalid.")
        if not isinstance(self.rows, tuple) or not all(
            isinstance(row, tuple)
            and row
            and any(cell for cell in row)
            and all(isinstance(cell, str) for cell in row)
            for row in self.rows
        ):
            raise ValueError("Structured content rows are invalid.")
        if not isinstance(self.pairs, tuple) or not all(
            isinstance(pair, tuple)
            and len(pair) == 2
            and all(isinstance(value, str) and value for value in pair)
            for pair in self.pairs
        ):
            raise ValueError("Structured content pairs are invalid.")
        if not isinstance(self.items, tuple) or not all(
            isinstance(item, str) and item for item in self.items
        ):
            raise ValueError("Structured content items are invalid.")

        populated = {
            "rows": bool(self.rows),
            "pairs": bool(self.pairs),
            "items": bool(self.items),
            "text": self.text is not None,
        }
        required_field = {
            StructuredContentKind.TABLE: "rows",
            StructuredContentKind.DEFINITION_LIST: "pairs",
            StructuredContentKind.KEY_VALUE: "pairs",
            StructuredContentKind.LIST: "items",
            StructuredContentKind.SECTION: "text",
            StructuredContentKind.IMAGE_ALT: "text",
        }[self.kind]
        if not populated[required_field] or any(
            is_populated
            for field, is_populated in populated.items()
            if field != required_field
        ):
            raise ValueError("Structured content fields do not match its kind.")
        if self.kind is StructuredContentKind.SECTION and self.heading is None:
            raise ValueError("Structured content section requires a heading.")


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
    structured_content: tuple[StructuredContentBlock, ...] = ()
    structured_content_truncated: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.structured_content, tuple) or not all(
            isinstance(block, StructuredContentBlock)
            for block in self.structured_content
        ):
            raise ValueError("Structured page content is invalid.")
        if not isinstance(self.structured_content_truncated, bool):
            raise ValueError("Structured content truncation state is invalid.")
        if self.status is PageExtractionStatus.SUCCESS:
            if not self.body_text or self.failure_kind is not None or self.error is not None:
                raise ValueError("Successful page extraction result is inconsistent.")
        elif self.body_text is not None or self.failure_kind is None or not self.error:
            raise ValueError("Failed page extraction result is inconsistent.")
