"""Bounded, provider-independent evidence packets from site crawl results."""

from dataclasses import dataclass
from enum import Enum
import json
import re

from .crawling import CrawlStopReason
from .extraction import (
    PageExtractionFailureKind,
    PageExtractionStatus,
    StructuredContentBlock,
    StructuredContentKind,
)


class SiteContentEvidenceScope(str, Enum):
    """The only claim supported by a site-content packet."""

    OBSERVED_PRESENT_ONLY = "observed_present_only"


class SiteContentBlockUse(str, Enum):
    """Permitted evidentiary use of one serialized structured block."""

    OBSERVED_PRESENT = "observed_present"
    CONTEXT_ONLY = "context_only"


@dataclass(frozen=True, slots=True)
class SiteContentPacketLimits:
    """Hard selection and serialization limits for one evidence packet."""

    max_pages: int = 5
    max_title_chars: int = 200
    max_description_chars: int = 500
    max_headings_per_level: int = 8
    max_heading_chars: int = 160
    max_body_chars_per_page: int = 600
    max_structured_blocks_per_page: int = 24
    max_tables_per_page: int = 6
    max_definition_lists_per_page: int = 6
    max_key_value_blocks_per_page: int = 6
    max_sections_per_page: int = 6
    max_lists_per_page: int = 6
    max_image_alts_per_page: int = 8
    max_rows_per_table: int = 32
    max_cells_per_row: int = 16
    max_pairs_per_block: int = 32
    max_items_per_list: int = 32
    max_field_chars: int = 256
    max_section_chars: int = 1_200
    max_chars_per_table: int = 3_000
    max_structured_chars_per_page: int = 3_500
    max_site_table_chars: int = 6_000
    max_site_content_chars: int = 11_000
    max_serialized_chars: int = 16_000
    max_serialized_bytes: int = 32 * 1024

    def __post_init__(self) -> None:
        values = (
            self.max_pages,
            self.max_title_chars,
            self.max_description_chars,
            self.max_headings_per_level,
            self.max_heading_chars,
            self.max_body_chars_per_page,
            self.max_structured_blocks_per_page,
            self.max_tables_per_page,
            self.max_definition_lists_per_page,
            self.max_key_value_blocks_per_page,
            self.max_sections_per_page,
            self.max_lists_per_page,
            self.max_image_alts_per_page,
            self.max_rows_per_table,
            self.max_cells_per_row,
            self.max_pairs_per_block,
            self.max_items_per_list,
            self.max_field_chars,
            self.max_section_chars,
            self.max_chars_per_table,
            self.max_structured_chars_per_page,
            self.max_site_table_chars,
            self.max_site_content_chars,
            self.max_serialized_chars,
            self.max_serialized_bytes,
        )
        if any(type(value) is not int or value <= 0 for value in values):
            raise ValueError("Site content packet limits must be positive integers.")


@dataclass(frozen=True, slots=True)
class SiteContentEvidence:
    """One numbered page observation; it never represents an absence check."""

    evidence_id: str
    final_url: str
    title: str | None
    description: str | None
    h1: tuple[str, ...]
    h2: tuple[str, ...]
    body_text: str | None
    structured_content: tuple[StructuredContentBlock, ...]
    extraction_status: PageExtractionStatus
    extraction_failure_kind: PageExtractionFailureKind | None
    structured_content_truncated: bool
    content_truncated: bool
    filtered_ui_blocks: int = 0

    def __post_init__(self) -> None:
        if re.fullmatch(r"P[1-9][0-9]*", self.evidence_id) is None:
            raise ValueError("Page evidence ID must use the P1 format.")
        if type(self.final_url) is not str or not self.final_url:
            raise ValueError("Page evidence requires a final URL.")
        if not isinstance(self.h1, tuple) or not all(
            type(item) is str and item for item in self.h1
        ):
            raise ValueError("Page evidence H1 values are invalid.")
        if not isinstance(self.h2, tuple) or not all(
            type(item) is str and item for item in self.h2
        ):
            raise ValueError("Page evidence H2 values are invalid.")
        if not isinstance(self.structured_content, tuple) or not all(
            isinstance(block, StructuredContentBlock)
            for block in self.structured_content
        ):
            raise ValueError("Page structured evidence is invalid.")
        if not isinstance(self.extraction_status, PageExtractionStatus):
            raise ValueError("Page extraction status is invalid.")
        if self.extraction_failure_kind is not None and not isinstance(
            self.extraction_failure_kind, PageExtractionFailureKind
        ):
            raise ValueError("Page extraction failure kind is invalid.")
        if type(self.structured_content_truncated) is not bool:
            raise ValueError("Source structured truncation state is invalid.")
        if type(self.content_truncated) is not bool:
            raise ValueError("Packet content truncation state is invalid.")
        if type(self.filtered_ui_blocks) is not int or self.filtered_ui_blocks < 0:
            raise ValueError("Filtered UI block count is invalid.")


@dataclass(frozen=True, slots=True)
class SiteContentPacket:
    """Deterministic LLM-ready observations from a bounded crawl report."""

    pages: tuple[SiteContentEvidence, ...]
    source_page_count: int
    crawl_stop_reason: CrawlStopReason
    crawl_budget_exhausted: bool
    truncated: bool
    evidence_scope: SiteContentEvidenceScope = (
        SiteContentEvidenceScope.OBSERVED_PRESENT_ONLY
    )
    supports_absence_claims: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.pages, tuple) or not all(
            isinstance(page, SiteContentEvidence) for page in self.pages
        ):
            raise ValueError("Site content packet pages are invalid.")
        if type(self.source_page_count) is not int or self.source_page_count < len(
            self.pages
        ):
            raise ValueError("Site content packet source page count is invalid.")
        if not isinstance(self.crawl_stop_reason, CrawlStopReason):
            raise ValueError("Site content packet crawl stop reason is invalid.")
        if type(self.crawl_budget_exhausted) is not bool or type(self.truncated) is not bool:
            raise ValueError("Site content packet state is invalid.")
        if self.evidence_scope is not SiteContentEvidenceScope.OBSERVED_PRESENT_ONLY:
            raise ValueError("Site content packets support observed content only.")
        if self.supports_absence_claims is not False:
            raise ValueError("Site content packets cannot support absence claims.")

    def to_json(self) -> str:
        """Serialize the packet deterministically without interpreting page text."""

        payload = {
            "evidence_scope": self.evidence_scope.value,
            "supports_absence_claims": self.supports_absence_claims,
            "source_page_count": self.source_page_count,
            "crawl_stop_reason": self.crawl_stop_reason.value,
            "crawl_budget_exhausted": self.crawl_budget_exhausted,
            "truncated": self.truncated,
            "pages": [self._page_payload(page) for page in self.pages],
        }
        return json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    @classmethod
    def _page_payload(cls, page: SiteContentEvidence) -> dict[str, object]:
        return {
            "evidence_id": page.evidence_id,
            "final_url": page.final_url,
            "title": page.title,
            "description": page.description,
            "h1": page.h1,
            "h2": page.h2,
            "body_text": page.body_text,
            "structured_content": [
                cls._block_payload(block) for block in page.structured_content
            ],
            "extraction_status": page.extraction_status.value,
            "extraction_failure_kind": (
                None
                if page.extraction_failure_kind is None
                else page.extraction_failure_kind.value
            ),
            "structured_content_truncated": page.structured_content_truncated,
            "content_truncated": page.content_truncated,
            "filtered_ui_blocks": page.filtered_ui_blocks,
        }

    @staticmethod
    def _block_payload(block: StructuredContentBlock) -> dict[str, object]:
        return {
            "kind": block.kind.value,
            "evidence_use": (
                SiteContentBlockUse.CONTEXT_ONLY.value
                if block.kind is StructuredContentKind.IMAGE_ALT
                else SiteContentBlockUse.OBSERVED_PRESENT.value
            ),
            "heading": block.heading,
            "rows": block.rows,
            "pairs": block.pairs,
            "items": block.items,
            "text": block.text,
        }
