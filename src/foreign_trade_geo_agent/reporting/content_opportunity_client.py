"""Immutable presentation contract for content-opportunity client reports."""

from __future__ import annotations

from dataclasses import dataclass
import re

from foreign_trade_geo_agent.core.content_opportunity import (
    CONTENT_OPPORTUNITY_LIMITATIONS,
    MAX_CONTENT_OPPORTUNITY_CLIENT_SITE_URL_CHARS,
    MAX_OPPORTUNITIES,
    MAX_RESEARCH_SOURCES,
    MAX_SOURCE_PACKET_BYTES,
    MAX_SOURCE_PACKET_CHARS,
    MAX_SITE_PACKET_BYTES,
    MAX_SITE_PACKET_CHARS,
    MAX_SITE_PAGES,
    MAX_TOTAL_SOURCE_CONTENT_CHARS,
    MAX_USER_MATERIAL_BYTES,
    MAX_USER_MATERIAL_CHARS,
    ContentOpportunityPriority,
    ContentOpportunityPrompt,
    ContentOpportunityReport,
    ContentOpportunityStatus,
    ContentOpportunityType,
    build_content_opportunity_evidence_catalog,
    finalized_content_opportunity_error,
    parse_safe_http_url,
    prepare_content_opportunity_sources,
)
from foreign_trade_geo_agent.core.crawling import (
    CrawlStopReason,
    SiteCrawlReport,
)
from foreign_trade_geo_agent.core.extraction import StructuredContentBlock
from foreign_trade_geo_agent.core.research import ResearchReport, ResearchStatus
from foreign_trade_geo_agent.core.site_content import (
    SiteContentEvidence,
    SiteContentPacket,
)


class ContentOpportunityClientReportError(ValueError):
    """A controlled cross-object validation failure."""


@dataclass(frozen=True, slots=True)
class ContentOpportunityClientReportInput:
    site_crawl_report: SiteCrawlReport
    site_content_packet: SiteContentPacket
    research_report: ResearchReport
    opportunity_report: ContentOpportunityReport


@dataclass(frozen=True, slots=True)
class ClientReportSummaryView:
    site_url: str
    report_status: str
    crawled_page_count: int
    page_evidence_count: int
    eligible_source_count: int
    opportunity_count: int
    opportunity_type_counts: tuple[tuple[str, int], ...]
    priority_counts: tuple[tuple[str, int], ...]
    requires_human_review: bool


@dataclass(frozen=True, slots=True)
class ClientStructuredBlockView:
    kind: str
    heading: str | None
    rows: tuple[tuple[str, ...], ...]
    pairs: tuple[tuple[str, str], ...]
    items: tuple[str, ...]
    text: str | None


@dataclass(frozen=True, slots=True)
class ClientPageEvidenceView:
    evidence_id: str
    title: str | None
    url: str
    description: str | None
    h1: tuple[str, ...]
    h2: tuple[str, ...]
    body_excerpt: str | None
    structured_content: tuple[ClientStructuredBlockView, ...]
    content_truncated: bool
    structured_content_truncated: bool


@dataclass(frozen=True, slots=True)
class ClientResearchEvidenceView:
    source_id: str
    title: str
    url: str
    content: str
    classifications: tuple[str, ...]
    content_truncated: bool


@dataclass(frozen=True, slots=True)
class ClientOpportunityIndexView:
    recommendation_id: str
    opportunity_type: str
    priority: str
    topic: str


@dataclass(frozen=True, slots=True)
class ClientOpportunityView:
    recommendation_id: str
    opportunity_type: str
    priority: str
    topic: str
    title: str
    rationale: str
    actions: tuple[str, ...]
    page_refs: tuple[str, ...]
    source_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ClientPageIndexView:
    evidence_id: str
    title: str | None
    url: str


@dataclass(frozen=True, slots=True)
class ClientSourceIndexView:
    source_id: str
    title: str
    url: str
    classifications: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ClientRecommendationEvidenceIndexView:
    recommendation_id: str
    page_refs: tuple[str, ...]
    source_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ClientEvidenceIndexView:
    pages: tuple[ClientPageIndexView, ...]
    sources: tuple[ClientSourceIndexView, ...]
    recommendations: tuple[ClientRecommendationEvidenceIndexView, ...]


@dataclass(frozen=True, slots=True)
class ContentOpportunityClientReportView:
    summary: ClientReportSummaryView
    scope_and_method: tuple[str, ...]
    evidence_scope: str
    supports_absence_claims: bool
    packet_truncated: bool
    pages: tuple[ClientPageEvidenceView, ...]
    research_sources_truncated: bool
    research_sources: tuple[ClientResearchEvidenceView, ...]
    opportunity_index: tuple[ClientOpportunityIndexView, ...]
    existing_page_opportunities: tuple[ClientOpportunityView, ...]
    new_supporting_content_opportunities: tuple[ClientOpportunityView, ...]
    evidence_index: ClientEvidenceIndexView
    limitations: tuple[str, ...]
    requires_human_review: bool


_PAGE_ID = re.compile(r"P[1-9][0-9]*\Z")
_SOURCE_ID = re.compile(r"S[1-9][0-9]*\Z")
_RECOMMENDATION_ID = re.compile(r"R[1-9][0-9]*\Z")


def _fail(message: str) -> None:
    raise ContentOpportunityClientReportError(message)


def _safe_origin(url: object) -> tuple[str, str, int] | None:
    parsed = parse_safe_http_url(
        url,
        max_chars=MAX_CONTENT_OPPORTUNITY_CLIENT_SITE_URL_CHARS,
    )
    if parsed is None:
        return None
    scheme = parsed.scheme.casefold()
    port = parsed.port
    return (
        scheme,
        parsed.hostname.casefold().rstrip("."),
        port or (443 if scheme == "https" else 80),
    )


def _validate_ids(values: tuple[str, ...], pattern: re.Pattern[str], label: str) -> None:
    if (
        not all(type(value) is str for value in values)
        or len(values) != len(set(values))
        or any(pattern.fullmatch(value) is None for value in values)
    ):
        _fail(f"{label} IDs are invalid or duplicated.")


def _normalized(value: str) -> str:
    return " ".join(value.split())


def _metadata_is_prefix(selected: str | None, source: str | None) -> bool:
    if selected is None:
        return True
    if source is None:
        return False
    return _normalized(source).startswith(selected)


def _structured_block(block: StructuredContentBlock) -> ClientStructuredBlockView:
    return ClientStructuredBlockView(
        kind=block.kind.value,
        heading=block.heading,
        rows=block.rows,
        pairs=block.pairs,
        items=block.items,
        text=block.text,
    )


def _page_view(page: SiteContentEvidence) -> ClientPageEvidenceView:
    return ClientPageEvidenceView(
        evidence_id=page.evidence_id,
        title=page.title,
        url=page.final_url,
        description=page.description,
        h1=page.h1,
        h2=page.h2,
        body_excerpt=page.body_text,
        structured_content=tuple(_structured_block(block) for block in page.structured_content),
        content_truncated=page.content_truncated,
        structured_content_truncated=page.structured_content_truncated,
    )


def build_content_opportunity_client_report_view(
    report_input: ContentOpportunityClientReportInput,
) -> ContentOpportunityClientReportView:
    """Validate mutually consistent workflow objects and build a deterministic view."""

    if not isinstance(report_input, ContentOpportunityClientReportInput):
        _fail("Client reports require the immutable four-object input contract.")
    crawl = report_input.site_crawl_report
    packet = report_input.site_content_packet
    research = report_input.research_report
    opportunity = report_input.opportunity_report
    if not isinstance(crawl, SiteCrawlReport) or not isinstance(packet, SiteContentPacket):
        _fail("Client report crawl inputs are invalid.")
    if not isinstance(research, ResearchReport) or not isinstance(opportunity, ContentOpportunityReport):
        _fail("Client report workflow inputs are invalid.")
    if research.status is not ResearchStatus.SUCCESS or opportunity.status is not ContentOpportunityStatus.SUCCESS:
        _fail("Only successful workflow objects can produce a client report.")
    if opportunity.limitations != CONTENT_OPPORTUNITY_LIMITATIONS:
        _fail("Content opportunity limitations do not match the fixed contract.")
    if not crawl.pages or crawl.exact_origin is None or crawl.stop_reason in {
        CrawlStopReason.INVALID_SEED,
        CrawlStopReason.ROBOTS_POLICY,
    }:
        _fail("The crawl report is not a successful observed-content input.")
    seed_origin = _safe_origin(crawl.seed_url)
    if seed_origin is None or seed_origin != (
        crawl.exact_origin.scheme,
        crawl.exact_origin.host,
        crawl.exact_origin.port,
    ):
        _fail("The crawl seed URL and exact origin are inconsistent.")

    packet_json = packet.to_json()
    if (
        len(packet.pages) > MAX_SITE_PAGES
        or len(packet_json) > MAX_SITE_PACKET_CHARS
        or len(packet_json.encode("utf-8")) > MAX_SITE_PACKET_BYTES
        or len(opportunity.source_materials) > MAX_RESEARCH_SOURCES
        or len(opportunity.sources) > MAX_RESEARCH_SOURCES
        or len(opportunity.opportunities) > MAX_OPPORTUNITIES
        or sum(len(item.content) for item in opportunity.source_materials) > MAX_TOTAL_SOURCE_CONTENT_CHARS
    ):
        _fail("Client report input exceeds an upstream fixed budget.")
    if not packet.pages or not opportunity.sources or not opportunity.source_materials:
        _fail("Successful client reports require exact P and S evidence.")
    if (
        packet.source_page_count != len(crawl.pages)
        or packet.crawl_stop_reason is not crawl.stop_reason
        or packet.crawl_budget_exhausted is not crawl.budget_exhausted
        or (
            len(packet.pages) < min(len(crawl.pages), MAX_SITE_PAGES)
            and not packet.truncated
        )
    ):
        _fail("The crawl report and site content packet are inconsistent.")

    page_ids = tuple(page.evidence_id for page in packet.pages)
    source_ids = tuple(item.source_id for item in opportunity.source_materials)
    display_source_ids = tuple(item.source_id for item in opportunity.sources)
    recommendation_ids = tuple(item.recommendation_id for item in opportunity.opportunities)
    _validate_ids(page_ids, _PAGE_ID, "Page evidence")
    _validate_ids(source_ids, _SOURCE_ID, "Source material")
    _validate_ids(display_source_ids, _SOURCE_ID, "Source evidence")
    _validate_ids(recommendation_ids, _RECOMMENDATION_ID, "Recommendation")
    if source_ids != display_source_ids:
        _fail("Exact source materials and display source metadata do not align.")

    for source_page, selected_page in zip(crawl.pages, packet.pages, strict=False):
        if (
            _safe_origin(source_page.requested_url) != seed_origin
            or _safe_origin(source_page.final_url) != seed_origin
            or _safe_origin(selected_page.final_url) != seed_origin
            or source_page.final_url != selected_page.final_url
            or source_page.extraction_status is not selected_page.extraction_status
            or source_page.extraction_failure_kind is not selected_page.extraction_failure_kind
            or not _metadata_is_prefix(selected_page.title, source_page.title)
            or not _metadata_is_prefix(selected_page.description, source_page.description)
        ):
            _fail("A selected P evidence item conflicts with its crawl page.")

    opportunity_pages = {item.evidence_id: item for item in opportunity.pages}
    _validate_ids(tuple(opportunity_pages), _PAGE_ID, "Opportunity page")
    if tuple(opportunity_pages) != page_ids:
        _fail("Opportunity page metadata does not align with selected P evidence.")
    for page in packet.pages:
        display_page = opportunity_pages[page.evidence_id]
        if display_page.final_url != page.final_url or display_page.title != page.title:
            _fail("Opportunity page metadata conflicts with selected P evidence.")

    prepared_sources = prepare_content_opportunity_sources(research)
    if prepared_sources is None:
        _fail("Successful client reports require retained research evidence.")
    if (
        prepared_sources.materials != opportunity.source_materials
        or prepared_sources.sources != opportunity.sources
        or prepared_sources.selection_truncated
        is not opportunity.research_sources_truncated
    ):
        _fail("Opportunity sources conflict with canonical research evidence.")

    catalog = build_content_opportunity_evidence_catalog(
        packet,
        opportunity.source_materials,
    )
    prompt = ContentOpportunityPrompt(
        site_content=packet,
        catalog=catalog,
        sources=opportunity.source_materials,
        research_sources_truncated=opportunity.research_sources_truncated,
    )
    source_json = prompt.source_material_json()
    material_json = prompt.material_json()
    if (
        len(source_json) > MAX_SOURCE_PACKET_CHARS
        or len(source_json.encode("utf-8")) > MAX_SOURCE_PACKET_BYTES
        or len(material_json) > MAX_USER_MATERIAL_CHARS
        or len(material_json.encode("utf-8")) > MAX_USER_MATERIAL_BYTES
    ):
        _fail("Client report input exceeds an upstream fixed budget.")
    for number, item in enumerate(opportunity.opportunities, start=1):
        if finalized_content_opportunity_error(
            item,
            number,
            catalog,
            opportunity.source_materials,
        ) is not None:
            _fail("An R recommendation violates the validated opportunity contract.")

    type_counts = tuple(
        (
            opportunity_type.value,
            sum(item.opportunity_type is opportunity_type for item in opportunity.opportunities),
        )
        for opportunity_type in ContentOpportunityType
    )
    priority_counts = tuple(
        (
            priority.value,
            sum(item.priority is priority for item in opportunity.opportunities),
        )
        for priority in ContentOpportunityPriority
    )
    full_opportunities = tuple(
        ClientOpportunityView(
            recommendation_id=item.recommendation_id,
            opportunity_type=item.opportunity_type.value,
            priority=item.priority.value,
            topic=item.topic,
            title=item.title,
            rationale=item.rationale,
            actions=item.actions,
            page_refs=item.page_refs,
            source_refs=item.source_refs,
        )
        for item in opportunity.opportunities
    )
    existing_types = {
        ContentOpportunityType.EXPAND_OBSERVED_CONTENT.value,
        ContentOpportunityType.REORGANIZE_OBSERVED_CONTENT.value,
    }
    page_views = tuple(_page_view(page) for page in packet.pages)
    research_views = tuple(
        ClientResearchEvidenceView(
            source_id=material.source_id,
            title=display.title,
            url=display.url,
            content=material.content,
            classifications=tuple(value.value for value in display.classifications),
            content_truncated=material.content_truncated,
        )
        for material, display in zip(opportunity.source_materials, opportunity.sources, strict=True)
    )
    return ContentOpportunityClientReportView(
        summary=ClientReportSummaryView(
            site_url=crawl.seed_url,
            report_status="Success",
            crawled_page_count=len(crawl.pages),
            page_evidence_count=len(packet.pages),
            eligible_source_count=len(opportunity.source_materials),
            opportunity_count=len(opportunity.opportunities),
            opportunity_type_counts=type_counts,
            priority_counts=priority_counts,
            requires_human_review=opportunity.requires_human_review,
        ),
        scope_and_method=(
            "Public website crawl.",
            "Observed-present-only page evidence; absence claims are not supported.",
            "Bounded evidence selection from the stable workflow objects.",
            "External research context is unverified and requires human review.",
            "No ranking guarantee, AI mention guarantee, or inquiry guarantee.",
        ),
        evidence_scope=packet.evidence_scope.value,
        supports_absence_claims=packet.supports_absence_claims,
        packet_truncated=packet.truncated,
        pages=page_views,
        research_sources_truncated=opportunity.research_sources_truncated,
        research_sources=research_views,
        opportunity_index=tuple(
            ClientOpportunityIndexView(
                item.recommendation_id,
                item.opportunity_type,
                item.priority,
                item.topic,
            )
            for item in full_opportunities
        ),
        existing_page_opportunities=tuple(
            item for item in full_opportunities if item.opportunity_type in existing_types
        ),
        new_supporting_content_opportunities=tuple(
            item
            for item in full_opportunities
            if item.opportunity_type == ContentOpportunityType.NEW_SUPPORTING_CONTENT.value
        ),
        evidence_index=ClientEvidenceIndexView(
            pages=tuple(ClientPageIndexView(page.evidence_id, page.title, page.url) for page in page_views),
            sources=tuple(
                ClientSourceIndexView(source.source_id, source.title, source.url, source.classifications)
                for source in research_views
            ),
            recommendations=tuple(
                ClientRecommendationEvidenceIndexView(item.recommendation_id, item.page_refs, item.source_refs)
                for item in full_opportunities
            ),
        ),
        limitations=opportunity.limitations,
        requires_human_review=opportunity.requires_human_review,
    )


__all__ = [
    "ClientEvidenceIndexView",
    "ClientOpportunityIndexView",
    "ClientOpportunityView",
    "ClientPageEvidenceView",
    "ClientReportSummaryView",
    "ClientResearchEvidenceView",
    "ClientStructuredBlockView",
    "ContentOpportunityClientReportError",
    "ContentOpportunityClientReportInput",
    "ContentOpportunityClientReportView",
    "build_content_opportunity_client_report_view",
]
