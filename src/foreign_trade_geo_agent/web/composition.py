"""Fail-closed composition for the deterministic local Demo."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from foreign_trade_geo_agent.adapters.page_extractor import TrafilaturaPageExtractor
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
from foreign_trade_geo_agent.workflows.change_plan import ChangePlanWorkflow
from foreign_trade_geo_agent.workflows.content_draft import ContentDraftWorkflow
from foreign_trade_geo_agent.workflows.content_draft_review import ContentDraftReviewWorkflow
from foreign_trade_geo_agent.workflows.content_opportunity import ContentOpportunityWorkflow
from foreign_trade_geo_agent.workflows.end_to_end import EndToEndWorkflow
from foreign_trade_geo_agent.workflows.industry_research import IndustryResearchWorkflow
from foreign_trade_geo_agent.workflows.site_content_packet import SiteContentPacketBuilder
from foreign_trade_geo_agent.workflows.site_crawl import SiteCrawlWorkflow


@dataclass(frozen=True, slots=True)
class DemoComposition:
    db_path: Path
    history_reader: SQLiteHistoryReader
    review_workflow: ContentDraftReviewWorkflow

    def planning_workflow(
        self,
        progress_observer: EndToEndProgressObserver | None = None,
    ) -> EndToEndWorkflow:
        history_store = SQLiteHistoryStore(self.db_path)
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
            history_store=history_store,
            progress_observer=progress_observer,
        )


def build_demo_composition(db_path: str | Path) -> DemoComposition:
    path = Path(db_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    SQLiteHistoryStore(path)
    history_reader = SQLiteHistoryReader(path)
    return DemoComposition(
        db_path=path,
        history_reader=history_reader,
        review_workflow=ContentDraftReviewWorkflow(history_reader=history_reader),
    )
