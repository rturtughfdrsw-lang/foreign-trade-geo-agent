"""Deterministically select bounded observed content from a site crawl."""

from dataclasses import dataclass, field

from foreign_trade_geo_agent.core.crawling import CrawledPage, SiteCrawlReport
from foreign_trade_geo_agent.core.extraction import (
    StructuredContentBlock,
    StructuredContentKind,
)
from foreign_trade_geo_agent.core.site_content import (
    SiteContentEvidence,
    SiteContentPacket,
    SiteContentPacketLimits,
)


_BLOCK_PRIORITY = (
    StructuredContentKind.TABLE,
    StructuredContentKind.KEY_VALUE,
    StructuredContentKind.DEFINITION_LIST,
    StructuredContentKind.SECTION,
    StructuredContentKind.LIST,
    StructuredContentKind.IMAGE_ALT,
)
_LOW_VALUE_REMOVAL_PRIORITY = (
    StructuredContentKind.IMAGE_ALT,
    StructuredContentKind.LIST,
    StructuredContentKind.SECTION,
)
_PRIMARY_REMOVAL_PRIORITY = (
    StructuredContentKind.DEFINITION_LIST,
    StructuredContentKind.KEY_VALUE,
    StructuredContentKind.TABLE,
)
_UI_LABELS = frozenset(
    {
        "login",
        "log in",
        "sign in",
        "account",
        "my account",
        "menu",
        "navigation",
        "breadcrumb",
    }
)


@dataclass(slots=True)
class _MutableEvidence:
    evidence_id: str
    source: CrawledPage
    title: str | None
    description: str | None
    h1: tuple[str, ...]
    h2: tuple[str, ...]
    body_text: str | None
    structured_content: list[StructuredContentBlock] = field(default_factory=list)
    content_truncated: bool = False
    filtered_ui_blocks: int = 0
    structured_chars: int = 0
    kind_counts: dict[StructuredContentKind, int] = field(default_factory=dict)


class SiteContentPacketBuilder:
    """Build one offline packet of observed page content without inference."""

    def __init__(self, limits: SiteContentPacketLimits | None = None) -> None:
        if limits is not None and not isinstance(limits, SiteContentPacketLimits):
            raise TypeError("Site content packet limits are invalid.")
        self._limits = limits or SiteContentPacketLimits()

    def build(self, report: SiteCrawlReport) -> SiteContentPacket:
        if not isinstance(report, SiteCrawlReport):
            raise TypeError("Site content packets require a SiteCrawlReport.")

        selected_sources = report.pages[: self._limits.max_pages]
        packet_truncated = len(report.pages) > len(selected_sources)
        pages: list[_MutableEvidence] = []
        site_content_remaining = self._limits.max_site_content_chars

        for index, source in enumerate(selected_sources, start=1):
            page = self._prepare_page(source, index)
            normalized_body = self._normalize_optional(source.body_text)
            if normalized_body is not None:
                body_limit = min(
                    self._limits.max_body_chars_per_page,
                    site_content_remaining,
                )
                if body_limit > 0:
                    page.body_text = normalized_body[:body_limit]
                    site_content_remaining -= len(page.body_text)
                if page.body_text != normalized_body:
                    page.content_truncated = True
            pages.append(page)

        candidates = [self._candidate_blocks(page) for page in pages]
        site_table_remaining = self._limits.max_site_table_chars
        for kind in _BLOCK_PRIORITY:
            for page, page_candidates in zip(pages, candidates, strict=True):
                for block in page_candidates:
                    if block.kind is not kind:
                        continue
                    if not self._has_block_capacity(page, kind):
                        page.content_truncated = True
                        continue
                    available = min(
                        self._limits.max_structured_chars_per_page
                        - page.structured_chars,
                        site_content_remaining,
                    )
                    if available <= 0:
                        page.content_truncated = True
                        continue
                    table_available = (
                        min(self._limits.max_chars_per_table, site_table_remaining)
                        if kind is StructuredContentKind.TABLE
                        else available
                    )
                    fitted, was_truncated = self._fit_block(
                        block,
                        max_chars=available,
                        max_table_chars=table_available,
                    )
                    if fitted is None:
                        page.content_truncated = True
                        continue
                    block_chars = self._block_chars(fitted)
                    page.structured_content.append(fitted)
                    page.structured_chars += block_chars
                    site_content_remaining -= block_chars
                    page.kind_counts[kind] = page.kind_counts.get(kind, 0) + 1
                    if kind is StructuredContentKind.TABLE:
                        site_table_remaining -= self._table_chars(fitted)
                    if was_truncated:
                        page.content_truncated = True

        packet_truncated = packet_truncated or any(
            page.content_truncated for page in pages
        )
        return self._fit_serialization(
            pages,
            report,
            packet_truncated=packet_truncated,
        )

    def _prepare_page(self, source: CrawledPage, index: int) -> _MutableEvidence:
        title, title_truncated = self._bounded_optional(
            source.title,
            self._limits.max_title_chars,
        )
        description, description_truncated = self._bounded_optional(
            source.description,
            self._limits.max_description_chars,
        )
        h1, h1_truncated = self._bounded_headings(source.h1)
        h2, h2_truncated = self._bounded_headings(source.h2)
        return _MutableEvidence(
            evidence_id=f"P{index}",
            source=source,
            title=title,
            description=description,
            h1=h1,
            h2=h2,
            body_text=None,
            content_truncated=(
                title_truncated
                or description_truncated
                or h1_truncated
                or h2_truncated
            ),
        )

    def _candidate_blocks(
        self,
        page: _MutableEvidence,
    ) -> tuple[StructuredContentBlock, ...]:
        candidates: list[StructuredContentBlock] = []
        seen: set[StructuredContentBlock] = set()
        for source_block in page.source.structured_content:
            block = self._normalize_block(source_block)
            if block in seen:
                continue
            seen.add(block)
            if self._is_ui_noise(block):
                page.filtered_ui_blocks += 1
                continue
            if (
                page.body_text is not None
                and self._payload_signature(block) == page.body_text
            ):
                continue
            candidates.append(block)
        return tuple(candidates)

    def _has_block_capacity(
        self,
        page: _MutableEvidence,
        kind: StructuredContentKind,
    ) -> bool:
        if len(page.structured_content) >= self._limits.max_structured_blocks_per_page:
            return False
        kind_limit = {
            StructuredContentKind.TABLE: self._limits.max_tables_per_page,
            StructuredContentKind.DEFINITION_LIST: (
                self._limits.max_definition_lists_per_page
            ),
            StructuredContentKind.KEY_VALUE: self._limits.max_key_value_blocks_per_page,
            StructuredContentKind.SECTION: self._limits.max_sections_per_page,
            StructuredContentKind.LIST: self._limits.max_lists_per_page,
            StructuredContentKind.IMAGE_ALT: self._limits.max_image_alts_per_page,
        }[kind]
        return page.kind_counts.get(kind, 0) < kind_limit

    def _fit_block(
        self,
        block: StructuredContentBlock,
        *,
        max_chars: int,
        max_table_chars: int,
    ) -> tuple[StructuredContentBlock | None, bool]:
        heading, heading_truncated = self._bounded_optional(
            block.heading,
            self._limits.max_heading_chars,
        )
        truncated = heading_truncated

        if block.kind is StructuredContentKind.TABLE:
            rows, rows_truncated = self._fit_rows(
                block.rows,
                min(max_chars - len(heading or ""), max_table_chars),
            )
            truncated = truncated or rows_truncated
            if not rows:
                return None, True
            fitted = StructuredContentBlock(block.kind, heading=heading, rows=rows)
        elif block.kind in {
            StructuredContentKind.DEFINITION_LIST,
            StructuredContentKind.KEY_VALUE,
        }:
            pairs, pairs_truncated = self._fit_pairs(
                block.pairs,
                max_chars - len(heading or ""),
            )
            truncated = truncated or pairs_truncated
            if not pairs:
                return None, True
            fitted = StructuredContentBlock(block.kind, heading=heading, pairs=pairs)
        elif block.kind is StructuredContentKind.LIST:
            items, items_truncated = self._fit_items(
                block.items,
                max_chars - len(heading or ""),
            )
            truncated = truncated or items_truncated
            if not items:
                return None, True
            fitted = StructuredContentBlock(block.kind, heading=heading, items=items)
        else:
            text_limit = (
                self._limits.max_section_chars
                if block.kind is StructuredContentKind.SECTION
                else self._limits.max_field_chars
            )
            remaining = max_chars - len(heading or "")
            text, text_truncated = self._bounded_required(
                block.text or "",
                min(text_limit, remaining),
            )
            truncated = truncated or text_truncated
            if text is None:
                return None, True
            fitted = StructuredContentBlock(block.kind, heading=heading, text=text)

        if self._block_chars(fitted) > max_chars:
            return None, True
        return fitted, truncated

    def _fit_rows(
        self,
        rows: tuple[tuple[str, ...], ...],
        budget: int,
    ) -> tuple[tuple[tuple[str, ...], ...], bool]:
        if budget <= 0:
            return (), True
        fitted: list[tuple[str, ...]] = []
        truncated = len(rows) > self._limits.max_rows_per_table
        remaining = budget
        for source_row in rows[: self._limits.max_rows_per_table]:
            if remaining <= 0:
                truncated = True
                break
            if len(source_row) > self._limits.max_cells_per_row:
                truncated = True
            row: list[str] = []
            for source_cell in source_row[: self._limits.max_cells_per_row]:
                cell, field_truncated = self._bounded_cell(source_cell)
                truncated = truncated or field_truncated
                if len(cell) > remaining:
                    cell = cell[:remaining]
                    truncated = True
                row.append(cell)
                remaining -= len(cell)
                if remaining <= 0:
                    if len(row) < len(source_row):
                        truncated = True
                    break
            if row and any(row):
                fitted.append(tuple(row))
            if remaining <= 0:
                if len(fitted) < len(rows):
                    truncated = True
                break
        return tuple(fitted), truncated

    def _fit_pairs(
        self,
        pairs: tuple[tuple[str, str], ...],
        budget: int,
    ) -> tuple[tuple[tuple[str, str], ...], bool]:
        fitted: list[tuple[str, str]] = []
        truncated = len(pairs) > self._limits.max_pairs_per_block
        remaining = budget
        for source_key, source_value in pairs[: self._limits.max_pairs_per_block]:
            key, key_truncated = self._bounded_required(
                source_key,
                min(self._limits.max_field_chars, max(0, remaining - 1)),
            )
            if key is None:
                truncated = True
                break
            remaining -= len(key)
            value, value_truncated = self._bounded_required(
                source_value,
                min(self._limits.max_field_chars, remaining),
            )
            if value is None:
                truncated = True
                break
            remaining -= len(value)
            fitted.append((key, value))
            truncated = truncated or key_truncated or value_truncated
            if remaining <= 0:
                if len(fitted) < len(pairs):
                    truncated = True
                break
        return tuple(fitted), truncated

    def _fit_items(
        self,
        items: tuple[str, ...],
        budget: int,
    ) -> tuple[tuple[str, ...], bool]:
        fitted: list[str] = []
        truncated = len(items) > self._limits.max_items_per_list
        remaining = budget
        for source_item in items[: self._limits.max_items_per_list]:
            item, item_truncated = self._bounded_required(
                source_item,
                min(self._limits.max_field_chars, remaining),
            )
            if item is None:
                truncated = True
                break
            fitted.append(item)
            remaining -= len(item)
            truncated = truncated or item_truncated
            if remaining <= 0:
                if len(fitted) < len(items):
                    truncated = True
                break
        return tuple(fitted), truncated

    def _fit_serialization(
        self,
        pages: list[_MutableEvidence],
        report: SiteCrawlReport,
        *,
        packet_truncated: bool,
    ) -> SiteContentPacket:
        while True:
            packet = self._freeze_packet(
                pages,
                report,
                packet_truncated=packet_truncated,
            )
            serialized = packet.to_json()
            char_overflow = len(serialized) - self._limits.max_serialized_chars
            byte_overflow = (
                len(serialized.encode("utf-8")) - self._limits.max_serialized_bytes
            )
            if char_overflow <= 0 and byte_overflow <= 0:
                return packet
            packet_truncated = True
            if self._remove_block_by_priority(
                pages,
                _LOW_VALUE_REMOVAL_PRIORITY,
            ):
                continue
            body_page = next(
                (page for page in reversed(pages) if page.body_text),
                None,
            )
            if body_page is not None and body_page.body_text is not None:
                cut = max(char_overflow, (byte_overflow + 3) // 4, 1)
                kept = body_page.body_text[: max(0, len(body_page.body_text) - cut)]
                body_page.body_text = kept or None
                body_page.content_truncated = True
                continue
            if self._remove_block_by_priority(
                pages,
                _PRIMARY_REMOVAL_PRIORITY,
            ):
                continue
            if self._remove_optional_metadata(pages):
                continue
            if pages:
                pages.pop()
                continue
            raise ValueError("Serialized site content limits are too small for a packet.")

    @staticmethod
    def _remove_block_by_priority(
        pages: list[_MutableEvidence],
        priorities: tuple[StructuredContentKind, ...],
    ) -> bool:
        for kind in priorities:
            for page in reversed(pages):
                for index in range(len(page.structured_content) - 1, -1, -1):
                    if page.structured_content[index].kind is kind:
                        del page.structured_content[index]
                        page.content_truncated = True
                        return True
        return False

    @staticmethod
    def _remove_optional_metadata(pages: list[_MutableEvidence]) -> bool:
        for page in reversed(pages):
            if page.description is not None:
                page.description = None
                page.content_truncated = True
                return True
            if page.h2:
                page.h2 = page.h2[:-1]
                page.content_truncated = True
                return True
            if page.h1:
                page.h1 = page.h1[:-1]
                page.content_truncated = True
                return True
            if page.title is not None:
                page.title = None
                page.content_truncated = True
                return True
        return False

    @staticmethod
    def _freeze_packet(
        pages: list[_MutableEvidence],
        report: SiteCrawlReport,
        *,
        packet_truncated: bool,
    ) -> SiteContentPacket:
        evidence = tuple(
            SiteContentEvidence(
                evidence_id=page.evidence_id,
                final_url=page.source.final_url,
                title=page.title,
                description=page.description,
                h1=page.h1,
                h2=page.h2,
                body_text=page.body_text,
                structured_content=tuple(page.structured_content),
                extraction_status=page.source.extraction_status,
                extraction_failure_kind=page.source.extraction_failure_kind,
                structured_content_truncated=(
                    page.source.structured_content_truncated
                ),
                content_truncated=page.content_truncated,
                filtered_ui_blocks=page.filtered_ui_blocks,
            )
            for page in pages
        )
        return SiteContentPacket(
            pages=evidence,
            source_page_count=len(report.pages),
            crawl_stop_reason=report.stop_reason,
            crawl_budget_exhausted=report.budget_exhausted,
            truncated=packet_truncated or any(
                item.content_truncated for item in evidence
            ),
        )

    def _bounded_headings(
        self,
        values: tuple[str, ...],
    ) -> tuple[tuple[str, ...], bool]:
        result: list[str] = []
        seen: set[str] = set()
        truncated = len(values) > self._limits.max_headings_per_level
        for value in values[: self._limits.max_headings_per_level]:
            normalized = self._normalize(value)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            bounded = normalized[: self._limits.max_heading_chars]
            truncated = truncated or bounded != normalized
            result.append(bounded)
        return tuple(result), truncated

    def _normalize_block(self, block: StructuredContentBlock) -> StructuredContentBlock:
        heading = self._normalize_optional(block.heading)
        if block.kind is StructuredContentKind.TABLE:
            rows = tuple(
                tuple(self._normalize(cell) for cell in row)
                for row in block.rows
            )
            return StructuredContentBlock(block.kind, heading=heading, rows=rows)
        if block.kind in {
            StructuredContentKind.DEFINITION_LIST,
            StructuredContentKind.KEY_VALUE,
        }:
            pairs = tuple(
                (self._normalize(key), self._normalize(value))
                for key, value in block.pairs
            )
            return StructuredContentBlock(block.kind, heading=heading, pairs=pairs)
        if block.kind is StructuredContentKind.LIST:
            items = tuple(self._normalize(item) for item in block.items)
            return StructuredContentBlock(block.kind, heading=heading, items=items)
        return StructuredContentBlock(
            block.kind,
            heading=heading,
            text=self._normalize(block.text or ""),
        )

    @staticmethod
    def _is_ui_noise(block: StructuredContentBlock) -> bool:
        labels = [block.heading]
        if block.kind is StructuredContentKind.IMAGE_ALT:
            labels.append(block.text)
        return any(
            label is not None
            and " ".join(label.split()).casefold().strip(" :_-") in _UI_LABELS
            for label in labels
        )

    def _bounded_optional(
        self,
        value: str | None,
        limit: int,
    ) -> tuple[str | None, bool]:
        normalized = self._normalize_optional(value)
        if normalized is None:
            return None, False
        return normalized[:limit], len(normalized) > limit

    def _bounded_required(
        self,
        value: str,
        limit: int,
    ) -> tuple[str | None, bool]:
        normalized = self._normalize(value)
        if not normalized or limit <= 0:
            return None, bool(normalized)
        return normalized[:limit], len(normalized) > limit

    def _bounded_cell(self, value: str) -> tuple[str, bool]:
        normalized = self._normalize(value)
        return (
            normalized[: self._limits.max_field_chars],
            len(normalized) > self._limits.max_field_chars,
        )

    @staticmethod
    def _normalize_optional(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        return normalized or None

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(value.split())

    @staticmethod
    def _block_chars(block: StructuredContentBlock) -> int:
        return len(block.heading or "") + SiteContentPacketBuilder._payload_chars(block)

    @staticmethod
    def _table_chars(block: StructuredContentBlock) -> int:
        return sum(len(cell) for row in block.rows for cell in row)

    @staticmethod
    def _payload_chars(block: StructuredContentBlock) -> int:
        return (
            sum(len(cell) for row in block.rows for cell in row)
            + sum(len(key) + len(value) for key, value in block.pairs)
            + sum(len(item) for item in block.items)
            + len(block.text or "")
        )

    @staticmethod
    def _payload_signature(block: StructuredContentBlock) -> str:
        if block.rows:
            values = (cell for row in block.rows for cell in row)
        elif block.pairs:
            values = (value for pair in block.pairs for value in pair)
        elif block.items:
            values = iter(block.items)
        else:
            values = iter((block.text or "",))
        return " ".join(value for value in values if value)
