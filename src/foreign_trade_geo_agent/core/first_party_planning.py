"""Explicit offline excerpt-planning scope, never evidence/review authority.

This transient input is supplied by the caller, never parsed from a provider or
artifact. It permits only planning a presentation of exact observed excerpts.
It has no approved/sufficient state and is deliberately not a Draft input.
"""
from dataclasses import dataclass
import re

from foreign_trade_geo_agent.core.extraction import PageExtractionStatus, StructuredContentKind
from foreign_trade_geo_agent.core.site_content import SiteContentPacket

MAX_FIRST_PARTY_EXCERPT_CHARS = 120
# One literal expansion may use the existing per-opportunity point budget
# (two operations of five points), without inventing an extra Change. Each
# fragment still has its own exact span and the unchanged 120-character cap.
MAX_FIRST_PARTY_EXCERPTS = 10


@dataclass(frozen=True, slots=True)
class FirstPartyExcerpt:
    field: str
    start: int
    end: int
    quote: str
    structured_index: int | None = None

    def __post_init__(self) -> None:
        if (
            self.field not in {"body_text", "structured_text"}
            or type(self.start) is not int or type(self.end) is not int
            or not 0 <= self.start < self.end
            or type(self.quote) is not str or not self.quote.strip()
            or len(self.quote) > MAX_FIRST_PARTY_EXCERPT_CHARS
            or self.field == "body_text" and self.structured_index is not None
            or self.field == "structured_text" and (
                type(self.structured_index) is not int or self.structured_index < 0
            )
        ):
            raise ValueError("First-party excerpt is invalid.")


@dataclass(frozen=True, slots=True)
class FirstPartyPlanningScope:
    task_id: str
    site_content: SiteContentPacket
    page_ref: str
    heading: str
    excerpts: tuple[FirstPartyExcerpt, ...]
    task_kind: str = "ATTRIBUTED_EXCERPT"

    def __post_init__(self) -> None:
        if (
            type(self.task_id) is not str
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", self.task_id) is None
            or self.task_kind != "ATTRIBUTED_EXCERPT"
            or not isinstance(self.site_content, SiteContentPacket)
            or type(self.page_ref) is not str
            or re.fullmatch(r"P[1-9][0-9]*", self.page_ref) is None
            or type(self.heading) is not str or not self.heading.strip()
            or len(self.heading) > 120
            or not isinstance(self.excerpts, tuple)
            or not 1 <= len(self.excerpts) <= MAX_FIRST_PARTY_EXCERPTS
            or not all(isinstance(item, FirstPartyExcerpt) for item in self.excerpts)
            or len({item.quote for item in self.excerpts}) != len(self.excerpts)
        ):
            raise ValueError("First-party planning scope is invalid.")
        selected = tuple(p for p in self.site_content.pages if p.evidence_id == self.page_ref)
        if len(selected) != 1:
            raise ValueError("First-party planning page binding is invalid.")
        page = selected[0]
        observed_headings = (*page.h1, *page.h2, *(b.heading for b in page.structured_content if b.kind is not StructuredContentKind.IMAGE_ALT))
        if page.extraction_status is not PageExtractionStatus.SUCCESS or self.heading not in observed_headings:
            raise ValueError("First-party planning requires an observed heading.")
        for item in self.excerpts:
            if item.field == "body_text":
                if page.h1 != (self.heading,) or page.h2 or any(
                    block.heading and block.kind is not StructuredContentKind.IMAGE_ALT
                    for block in page.structured_content
                ):
                    raise ValueError("Body excerpt requires an unambiguous single-heading page.")
                text = page.body_text
                truncated = page.content_truncated
            else:
                if item.structured_index >= len(page.structured_content):
                    raise ValueError("First-party excerpt field is unavailable.")
                block = page.structured_content[item.structured_index]
                if block.kind is StructuredContentKind.IMAGE_ALT or block.heading != self.heading:
                    raise ValueError("First-party excerpt is outside the observed section.")
                text = block.text
                truncated = page.structured_content_truncated
            # No inference from truncated fields, metadata, or image context.
            if truncated or type(text) is not str or item.end > len(text) or text[item.start:item.end] != item.quote:
                raise ValueError("First-party excerpt is not an exact complete-field observation.")

    def matches_packet(self, packet: SiteContentPacket) -> bool:
        return isinstance(packet, SiteContentPacket) and packet == self.site_content

    def matches_task(self, task_id: str | None) -> bool:
        return type(task_id) is str and task_id == self.task_id

    @property
    def quotes(self) -> tuple[str, ...]:
        return tuple(item.quote for item in self.excerpts)
