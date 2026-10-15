"""Runtime-only configuration and object-graph construction."""

from __future__ import annotations

from collections.abc import Callable, Mapping
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
from foreign_trade_geo_agent.adapters.safe_http import (
    SafeHtmlFetcher,
    SystemHostResolver,
)
from foreign_trade_geo_agent.adapters.tavily_search import TavilySearchAdapter
from foreign_trade_geo_agent.adapters.wordpress_rest import WordPressRestDraftPublisher
from foreign_trade_geo_agent.adapters.wordpress_rest import WordPressRestDraftReader
from foreign_trade_geo_agent.core.crawling import LinkPriorityPolicy
from foreign_trade_geo_agent.core.orchestration import EndToEndProgressObserver
from foreign_trade_geo_agent.core.ports import (
    ChangePlanWriter,
    ContentDraftPublisher,
    ContentDraftWriter,
    ContentDraftAdmission,
    ContentOpportunityWriter,
    CrawlFetcher,
    ResearchWriter,
    SearchProvider,
    PlanningSiteAuditor,
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
from foreign_trade_geo_agent.workflows.crawl_seo_audit import CrawlSeoAuditor
from foreign_trade_geo_agent.workflows.industry_research import (
    IndustryResearchWorkflow,
)
from foreign_trade_geo_agent.workflows.site_content_packet import (
    SiteContentPacketBuilder,
)
from foreign_trade_geo_agent.workflows.site_crawl import SiteCrawlWorkflow
from foreign_trade_geo_agent.workflows.run_diagnostics import RunDiagnosticContext
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


def planning_provider_configuration_ready(
    environ: Mapping[str, str] | None = None,
) -> bool:
    """Return whether both planning provider credentials are non-empty."""

    values = os.environ if environ is None else environ
    return all(
        isinstance(values.get(name), str) and bool(values[name].strip())
        for name in ("TAVILY_API_KEY", "DEEPSEEK_API_KEY")
    )


def _history_store(path: str | Path) -> SQLiteHistoryStore:
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return SQLiteHistoryStore(db_path)


def build_planning_evidence_workflow(db_path, intake_db_path, *, run_id, plan_id, create=False):
    """Local operator composition; no model, reviewer authority or CMS ports.

    Validate the immutable source run before creating the separate, existing
    intake journal. The retained writer only revalidates the original Plan.
    """
    from foreign_trade_geo_agent.adapters.retained_intake_plan import RetainedIntakePlanWriter
    from foreign_trade_geo_agent.storage.evidence_intake import SQLiteEvidenceIntakeStore
    from foreign_trade_geo_agent.workflows.evidence_intake import EvidenceIntakeWorkflow
    from foreign_trade_geo_agent.workflows.planning_evidence import PlanningEvidenceWorkflow

    history = SQLiteHistoryReader(db_path)
    PlanningEvidenceWorkflow(history, None).origin(run_id, plan_id)
    path = Path(intake_db_path)
    if create and not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        store = SQLiteEvidenceIntakeStore.create(path)
    else:
        store = SQLiteEvidenceIntakeStore(path)
    app = PlanningEvidenceWorkflow(history, EvidenceIntakeWorkflow(store))
    return store, app, ChangePlanWorkflow(RetainedIntakePlanWriter())


def build_planning_workflow(
    db_path: str | Path,
    *,
    fetcher: CrawlFetcher | None = None,
    planning_site_auditor: PlanningSiteAuditor | None = None,
    search_provider: SearchProvider | None = None,
    research_writer: ResearchWriter | None = None,
    content_opportunity_writer: ContentOpportunityWriter | None = None,
    change_plan_writer: ChangePlanWriter | None = None,
    content_draft_writer: ContentDraftWriter | None = None,
    progress_observer: EndToEndProgressObserver | None = None,
    intake_admission: ContentDraftAdmission | None = None,
) -> EndToEndWorkflow:
    """Production CLI/Live chain; Draft is locked without a trusted authority.

    An optional intake admission supplies current-binding diagnostics only; it
    cannot grant Draft execution. No production authorization purpose is wired.
    """
    from foreign_trade_geo_agent.evidence_review_composition import ProductionDraftAdmission

    return _compose_planning_workflow(
        db_path, fetcher=fetcher, planning_site_auditor=planning_site_auditor,
        search_provider=search_provider, research_writer=research_writer,
        content_opportunity_writer=content_opportunity_writer, change_plan_writer=change_plan_writer,
        content_draft_writer=content_draft_writer, progress_observer=progress_observer,
        intake_admission=ProductionDraftAdmission() if intake_admission is None else intake_admission,
    )


def build_isolated_test_planning_workflow(
    db_path: str | Path,
    *,
    fetcher: CrawlFetcher,
    search_provider: SearchProvider,
    research_writer: ResearchWriter,
    content_opportunity_writer: ContentOpportunityWriter,
    change_plan_writer: ChangePlanWriter,
    content_draft_writer: ContentDraftWriter,
    planning_site_auditor: PlanningSiteAuditor | None = None,
    progress_observer: EndToEndProgressObserver | None = None,
) -> EndToEndWorkflow:
    """Explicit offline fixture root using the same chain and native validators.

    All external ports must be provided; never selected by CLI, Live API, flags
    or environment. Injected ports are trusted Python test code, not user JSON.
    """
    if any(port is None for port in (fetcher, search_provider, research_writer,
            content_opportunity_writer, change_plan_writer, content_draft_writer)):
        raise ValueError("ISOLATED_TEST_PORTS_REQUIRED")
    return _compose_planning_workflow(
        db_path, fetcher=fetcher, planning_site_auditor=planning_site_auditor,
        search_provider=search_provider, research_writer=research_writer,
        content_opportunity_writer=content_opportunity_writer, change_plan_writer=change_plan_writer,
        content_draft_writer=content_draft_writer, progress_observer=progress_observer,
    )


def _compose_planning_workflow(
    db_path: str | Path,
    *,
    fetcher: CrawlFetcher | None = None,
    planning_site_auditor: PlanningSiteAuditor | None = None,
    search_provider: SearchProvider | None = None,
    research_writer: ResearchWriter | None = None,
    content_opportunity_writer: ContentOpportunityWriter | None = None,
    change_plan_writer: ChangePlanWriter | None = None,
    content_draft_writer: ContentDraftWriter | None = None,
    progress_observer: EndToEndProgressObserver | None = None,
    intake_admission: ContentDraftAdmission | None = None,
) -> EndToEndWorkflow:
    """One object graph shared by production and explicitly isolated fixtures."""

    history_store = _history_store(db_path)
    run_diagnostics = RunDiagnosticContext()
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
        planning_site_auditor=(
            CrawlSeoAuditor()
            if planning_site_auditor is None
            else planning_site_auditor
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
            else change_plan_writer,
            run_diagnostics=run_diagnostics,
        ),
        content_draft=ContentDraftWorkflow(
            DeepSeekContentDraftWriter()
            if content_draft_writer is None
            else content_draft_writer,
            intake_admission=intake_admission,
        ),
        history_store=history_store,
        progress_observer=progress_observer,
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
