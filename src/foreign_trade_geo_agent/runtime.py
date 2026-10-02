"""Runtime-only configuration and object-graph construction."""

from __future__ import annotations

from collections.abc import Callable
import os
from pathlib import Path

from dotenv import dotenv_values

from foreign_trade_geo_agent.adapters.deepseek_change_plan import (
    DeepSeekChangePlanWriter,
)
from foreign_trade_geo_agent.adapters.deepseek_content_draft import (
    DeepSeekContentDraftWriter,
)
from foreign_trade_geo_agent.adapters.deepseek_content_opportunity import (
    DeepSeekContentOpportunityWriter,
)
from foreign_trade_geo_agent.adapters.deepseek_research import DeepSeekResearchWriter
from foreign_trade_geo_agent.adapters.page_extractor import TrafilaturaPageExtractor
from foreign_trade_geo_agent.adapters.geo_optimizer import GeoOptimizerAdapter
from foreign_trade_geo_agent.adapters.safe_http import (
    SafeHtmlFetcher,
    SystemHostResolver,
)
from foreign_trade_geo_agent.adapters.tavily_search import TavilySearchAdapter
from foreign_trade_geo_agent.adapters.wordpress_rest import WordPressRestDraftPublisher
from foreign_trade_geo_agent.adapters.wordpress_rest import WordPressRestDraftReader
from foreign_trade_geo_agent.core.crawling import LinkPriorityPolicy
from foreign_trade_geo_agent.core.ports import (
    ChangePlanWriter,
    ContentDraftPublisher,
    ContentDraftWriter,
    ContentOpportunityWriter,
    CrawlFetcher,
    ResearchWriter,
    SearchProvider,
    SiteAuditor,
    WordPressDraftReader,
)
from foreign_trade_geo_agent.storage.sqlite import (
    SQLiteHistoryReader,
    SQLiteHistoryStore,
)
from foreign_trade_geo_agent.workflows.approved_wordpress_delivery import (
    ApprovedWordPressDraftDeliveryWorkflow,
)
from foreign_trade_geo_agent.workflows.change_plan import ChangePlanWorkflow
from foreign_trade_geo_agent.workflows.content_draft import ContentDraftWorkflow
from foreign_trade_geo_agent.workflows.content_draft_review import (
    ContentDraftReviewWorkflow,
)
from foreign_trade_geo_agent.workflows.content_opportunity import (
    ContentOpportunityWorkflow,
)
from foreign_trade_geo_agent.workflows.end_to_end import EndToEndWorkflow
from foreign_trade_geo_agent.workflows.industry_research import (
    IndustryResearchWorkflow,
)
from foreign_trade_geo_agent.workflows.site_content_packet import (
    SiteContentPacketBuilder,
)
from foreign_trade_geo_agent.workflows.site_crawl import SiteCrawlWorkflow
from foreign_trade_geo_agent.workflows.wordpress_delivery import (
    WordPressDeliveryWorkflow,
)
from foreign_trade_geo_agent.workflows.wordpress_verification import (
    WordPressDraftVerificationWorkflow,
)


def load_runtime_environment(cwd: Path | None = None) -> None:
    """Load a working-directory ``.env`` without replacing process values."""

    env_path = (Path.cwd() if cwd is None else Path(cwd)) / ".env"
    if not env_path.is_file():
        return
    for name, value in dotenv_values(env_path).items():
        if value is not None:
            os.environ.setdefault(name, value)


def _history_store(path: str | Path) -> SQLiteHistoryStore:
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return SQLiteHistoryStore(db_path)


def _run_geo_optimizer_audit(url: str) -> object:
    """Load the optional audit provider only when a planning run reaches audit."""

    from geo_optimizer import audit

    return audit(url)


def build_planning_workflow(
    db_path: str | Path,
    *,
    fetcher: CrawlFetcher | None = None,
    site_auditor: SiteAuditor | None = None,
    search_provider: SearchProvider | None = None,
    research_writer: ResearchWriter | None = None,
    content_opportunity_writer: ContentOpportunityWriter | None = None,
    change_plan_writer: ChangePlanWriter | None = None,
    content_draft_writer: ContentDraftWriter | None = None,
) -> EndToEndWorkflow:
    """Construct the fixed planning chain without executing it."""

    history_store = _history_store(db_path)
    site_crawl = SiteCrawlWorkflow(
        (
            SafeHtmlFetcher(resolver=SystemHostResolver())
            if fetcher is None
            else fetcher
        ),
        TrafilaturaPageExtractor(),
        max_pages=5,
        max_depth=1,
        max_concurrency=1,
        max_request_attempts=35,
        link_priority_policy=LinkPriorityPolicy.B2B_CONTENT_V1,
    )
    return EndToEndWorkflow(
        site_crawl=site_crawl,
        packet_builder=SiteContentPacketBuilder(),
        site_auditor=(
            GeoOptimizerAdapter(
                audit_func=_run_geo_optimizer_audit,
                source_version="runtime",
            )
            if site_auditor is None
            else site_auditor
        ),
        industry_research=IndustryResearchWorkflow(
            TavilySearchAdapter() if search_provider is None else search_provider,
            DeepSeekResearchWriter() if research_writer is None else research_writer,
        ),
        content_opportunity=ContentOpportunityWorkflow(
            (
                DeepSeekContentOpportunityWriter()
                if content_opportunity_writer is None
                else content_opportunity_writer
            )
        ),
        change_plan=ChangePlanWorkflow(
            DeepSeekChangePlanWriter()
            if change_plan_writer is None
            else change_plan_writer
        ),
        content_draft=ContentDraftWorkflow(
            DeepSeekContentDraftWriter()
            if content_draft_writer is None
            else content_draft_writer
        ),
        history_store=history_store,
    )


def build_delivery_workflow(
    db_path: str | Path,
    *,
    target_site_url: str,
    username: str,
    application_password: str,
    publisher: ContentDraftPublisher | None = None,
) -> ApprovedWordPressDraftDeliveryWorkflow:
    """Construct exact-one-draft delivery without sending a request."""

    history_store = _history_store(db_path)
    wordpress_delivery = WordPressDeliveryWorkflow(
        publisher=(
            WordPressRestDraftPublisher(
                base_url=target_site_url,
                username=username,
                application_password=application_password,
            )
            if publisher is None
            else publisher
        ),
        history_store=history_store,
    )
    return ApprovedWordPressDraftDeliveryWorkflow(
        history_store=history_store,
        wordpress_delivery=wordpress_delivery,
    )


def build_review_workflow(db_path: str | Path) -> ContentDraftReviewWorkflow:
    """Construct read-only draft inspection without creating any database."""

    return ContentDraftReviewWorkflow(
        history_reader=SQLiteHistoryReader(Path(db_path)),
    )


def build_verification_workflow(
    db_path: str | Path,
    *,
    username: str,
    application_password: str,
    draft_reader_factory: Callable[[str], WordPressDraftReader] | None = None,
) -> WordPressDraftVerificationWorkflow:
    """Construct remote read-only verification with append-only local history."""

    path = Path(db_path)
    if not path.is_file():
        raise FileNotFoundError("History database does not exist.")
    history_store = SQLiteHistoryStore(path)

    if draft_reader_factory is None:
        def reader_factory(site_key: str) -> WordPressRestDraftReader:
            return WordPressRestDraftReader(
                base_url=site_key,
                username=username,
                application_password=application_password,
            )
    else:
        reader_factory = draft_reader_factory

    return WordPressDraftVerificationWorkflow(
        history_store=history_store,
        draft_reader_factory=reader_factory,
    )
