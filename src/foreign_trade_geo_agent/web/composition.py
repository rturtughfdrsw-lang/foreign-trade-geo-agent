"""Fail-closed composition for the deterministic local Demo."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from foreign_trade_geo_agent.adapters.page_extractor import TrafilaturaPageExtractor
from foreign_trade_geo_agent.adapters.wordpress_rest import (
    WordPressRestDraftPublisher,
    WordPressRestDraftReader,
)
from foreign_trade_geo_agent.core.crawling import LinkPriorityPolicy
from foreign_trade_geo_agent.core.orchestration import EndToEndProgressObserver
from foreign_trade_geo_agent.storage.sqlite import SQLiteHistoryReader, SQLiteHistoryStore
from foreign_trade_geo_agent.web.demo_boundaries import (
    DemoChangePlanWriter,
    DemoContentDraftWriter,
    DemoContentOpportunityWriter,
    DemoCrawlFetcher,
    DemoResearchWriter,
    DemoSearchProvider,
    DemoSiteAuditor,
)
from foreign_trade_geo_agent.web.demo_wordpress import (
    DEMO_WORDPRESS_APPLICATION_PASSWORD,
    DEMO_WORDPRESS_USERNAME,
    DemoWordPressTransport,
)
from foreign_trade_geo_agent.workflows.approved_wordpress_delivery import (
    ApprovedWordPressDraftDeliveryWorkflow,
)
from foreign_trade_geo_agent.workflows.change_plan import ChangePlanWorkflow
from foreign_trade_geo_agent.workflows.content_draft import ContentDraftWorkflow
from foreign_trade_geo_agent.workflows.content_draft_review import ContentDraftReviewWorkflow
from foreign_trade_geo_agent.workflows.content_opportunity import ContentOpportunityWorkflow
from foreign_trade_geo_agent.workflows.end_to_end import EndToEndWorkflow
from foreign_trade_geo_agent.workflows.industry_research import IndustryResearchWorkflow
from foreign_trade_geo_agent.workflows.site_content_packet import SiteContentPacketBuilder
from foreign_trade_geo_agent.workflows.site_crawl import SiteCrawlWorkflow
from foreign_trade_geo_agent.workflows.wordpress_delivery import (
    WordPressDeliveryWorkflow,
)
from foreign_trade_geo_agent.workflows.wordpress_verification import (
    WordPressDraftVerificationWorkflow,
)


class _MonotonicUtcClock:
    """A strictly increasing aware-UTC clock for deterministic Demo ordering."""

    def __init__(self) -> None:
        self._last: datetime | None = None

    def __call__(self) -> datetime:
        now = datetime.now(UTC)
        if self._last is not None and now <= self._last:
            now = self._last + timedelta(microseconds=1)
        self._last = now
        return now


@dataclass(frozen=True, slots=True)
class DemoComposition:
    db_path: Path
    history_reader: SQLiteHistoryReader
    history_store: SQLiteHistoryStore
    review_workflow: ContentDraftReviewWorkflow
    wordpress_transport: DemoWordPressTransport
    clock: _MonotonicUtcClock

    def planning_workflow(
        self,
        progress_observer: EndToEndProgressObserver | None = None,
    ) -> EndToEndWorkflow:
        site_crawl = SiteCrawlWorkflow(
            DemoCrawlFetcher(),
            TrafilaturaPageExtractor(),
            max_pages=2,
            max_depth=1,
            max_concurrency=1,
            max_request_attempts=3,
            link_priority_policy=LinkPriorityPolicy.B2B_CONTENT_V1,
        )
        return EndToEndWorkflow(
            site_crawl=site_crawl,
            packet_builder=SiteContentPacketBuilder(),
            site_auditor=DemoSiteAuditor(),
            industry_research=IndustryResearchWorkflow(
                DemoSearchProvider(),
                DemoResearchWriter(),
            ),
            content_opportunity=ContentOpportunityWorkflow(
                DemoContentOpportunityWriter()
            ),
            change_plan=ChangePlanWorkflow(DemoChangePlanWriter()),
            content_draft=ContentDraftWorkflow(DemoContentDraftWriter()),
            history_store=self.history_store,
            progress_observer=progress_observer,
        )

    def delivery_workflow(
        self,
        target_site_url: str,
    ) -> ApprovedWordPressDraftDeliveryWorkflow:
        publisher = WordPressRestDraftPublisher(
            base_url=target_site_url,
            username=DEMO_WORDPRESS_USERNAME,
            application_password=DEMO_WORDPRESS_APPLICATION_PASSWORD,
            transport=httpx.MockTransport(self.wordpress_transport),
        )
        wordpress_delivery = WordPressDeliveryWorkflow(
            publisher=publisher,
            history_store=self.history_store,
            clock=self.clock,
        )
        return ApprovedWordPressDraftDeliveryWorkflow(
            history_store=self.history_store,
            wordpress_delivery=wordpress_delivery,
        )

    def verification_workflow(self) -> WordPressDraftVerificationWorkflow:
        transport = httpx.MockTransport(self.wordpress_transport)

        def reader_factory(site_key: str) -> WordPressRestDraftReader:
            return WordPressRestDraftReader(
                base_url=site_key,
                username=DEMO_WORDPRESS_USERNAME,
                application_password=DEMO_WORDPRESS_APPLICATION_PASSWORD,
                transport=transport,
            )

        return WordPressDraftVerificationWorkflow(
            history_store=self.history_store,
            draft_reader_factory=reader_factory,
            clock=self.clock,
        )


def build_demo_composition(db_path: str | Path) -> DemoComposition:
    path = Path(db_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    history_store = SQLiteHistoryStore(path)
    history_reader = SQLiteHistoryReader(path)
    return DemoComposition(
        db_path=path,
        history_reader=history_reader,
        history_store=history_store,
        review_workflow=ContentDraftReviewWorkflow(history_reader=history_reader),
        wordpress_transport=DemoWordPressTransport(),
        clock=_MonotonicUtcClock(),
    )
