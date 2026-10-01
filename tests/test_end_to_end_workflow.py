from __future__ import annotations

from collections.abc import Callable
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime
import asyncio
import inspect
from threading import Event
import unittest

from foreign_trade_geo_agent.core.change_plan import (
    CHANGE_PLAN_LIMITATIONS,
    ChangePlanReport,
    ChangePlanStatus,
)
from foreign_trade_geo_agent.core.content_draft import (
    CONTENT_DRAFT_LIMITATIONS,
    ContentDraftInput,
    ContentDraftReport,
    ContentDraftStatus,
)
from foreign_trade_geo_agent.core.content_opportunity import (
    CONTENT_OPPORTUNITY_LIMITATIONS,
    ContentOpportunityReport,
    ContentOpportunitySource,
    ContentOpportunityStatus,
)
from foreign_trade_geo_agent.core.crawling import (
    CrawlResourceStats,
    CrawlStopReason,
    CrawledPage,
    LinkPriorityPolicy,
    RobotsStatus,
    SiteCrawlReport,
)
from foreign_trade_geo_agent.core.extraction import PageExtractionStatus
from foreign_trade_geo_agent.core.fetching import UrlOrigin
from foreign_trade_geo_agent.core.history import (
    ArtifactRecord,
    ArtifactType,
    HistoryConflictError,
    HistoryStoreError,
    RunStatus,
    WorkflowRun,
)
from foreign_trade_geo_agent.core.orchestration import (
    ArtifactRef,
    EndToEndRunRequest,
    EndToEndRunResult,
    EndToEndStage,
)
from foreign_trade_geo_agent.core.research import (
    ResearchEvidenceClassification,
    ResearchReport,
    ResearchSource,
    ResearchStatus,
)
from foreign_trade_geo_agent.core.site_content import (
    SiteContentEvidence,
    SiteContentPacket,
)
from foreign_trade_geo_agent.workflows.end_to_end import EndToEndWorkflow


RUN_ID = "11111111-1111-4111-8111-111111111111"
ARTIFACT_IDS = (
    "22222222-2222-4222-8222-222222222221",
    "22222222-2222-4222-8222-222222222222",
    "22222222-2222-4222-8222-222222222223",
    "22222222-2222-4222-8222-222222222224",
    "22222222-2222-4222-8222-222222222225",
)
NOW = datetime(2026, 10, 2, 8, 30, tzinfo=UTC)


def crawl_report(
    *,
    stop_reason: CrawlStopReason = CrawlStopReason.COMPLETED,
    include_page: bool = True,
) -> SiteCrawlReport:
    pages = ()
    if include_page:
        pages = (
            CrawledPage(
                requested_url="https://example.com/",
                final_url="https://example.com/",
                depth=0,
                http_status=200,
                content_type="text/html",
                title="Example",
                description="Industrial products",
                canonical="https://example.com/",
                h1=("Industrial products",),
                h2=(),
                body_text="Observed product information.",
                published_date=None,
                internal_links=(),
                extraction_status=PageExtractionStatus.SUCCESS,
                extraction_failure_kind=None,
            ),
        )
    return SiteCrawlReport(
        seed_url="https://example.com/",
        exact_origin=UrlOrigin("https", "example.com", 443),
        pages=pages,
        failures=(),
        resources=CrawlResourceStats(2, 1, 2, 0, 100, 100),
        robots_status=RobotsStatus.ALLOWED,
        crawl_delay=None,
        stop_reason=stop_reason,
        budget_exhausted=stop_reason is not CrawlStopReason.COMPLETED,
        link_priority_policy=LinkPriorityPolicy.DOCUMENT_ORDER,
    )


def failed_crawled_page(
    *,
    final_url: str = "https://example.com/failed",
    title: str | None = None,
    canonical: str | None = None,
    internal_links: tuple[str, ...] = (),
) -> CrawledPage:
    return CrawledPage(
        requested_url=final_url,
        final_url=final_url,
        depth=0,
        http_status=200,
        content_type="text/html",
        title=title,
        description=None,
        canonical=canonical,
        h1=(),
        h2=(),
        body_text=None,
        published_date=None,
        internal_links=internal_links,
        extraction_status=PageExtractionStatus.FAILED,
        extraction_failure_kind=None,
    )


def site_packet() -> SiteContentPacket:
    page = SiteContentEvidence(
        evidence_id="P1",
        final_url="https://example.com/",
        title="Example",
        description="Industrial products",
        h1=("Industrial products",),
        h2=(),
        body_text="Observed product information.",
        structured_content=(),
        extraction_status=PageExtractionStatus.SUCCESS,
        extraction_failure_kind=None,
        structured_content_truncated=False,
        content_truncated=False,
    )
    return SiteContentPacket(
        pages=(page,),
        source_page_count=1,
        crawl_stop_reason=CrawlStopReason.COMPLETED,
        crawl_budget_exhausted=False,
        truncated=False,
    )


def research_report(
    status: ResearchStatus = ResearchStatus.SUCCESS,
) -> ResearchReport:
    if status is not ResearchStatus.SUCCESS:
        return ResearchReport("buyer question", status, None, (), "SECRET provider error")
    return ResearchReport(
        question="buyer question",
        status=ResearchStatus.SUCCESS,
        draft_text="Supported research [S1].",
        sources=(ResearchSource("S1", "Source", "https://source.example/report"),),
        error=None,
    )


def opportunity_report(
    status: ContentOpportunityStatus = ContentOpportunityStatus.SUCCESS,
) -> ContentOpportunityReport:
    if status is not ContentOpportunityStatus.SUCCESS:
        return ContentOpportunityReport(status, (), (), (), (), "SECRET opportunity error")
    classifications = (
        ResearchEvidenceClassification.EXTERNAL_RESEARCH_CONTEXT,
        ResearchEvidenceClassification.UNVERIFIED_SEARCH_RESULT,
    )
    return ContentOpportunityReport(
        status=ContentOpportunityStatus.SUCCESS,
        opportunities=(),
        pages=(),
        sources=(
            ContentOpportunitySource(
                "S1", "Source", "https://source.example/report", classifications
            ),
        ),
        limitations=CONTENT_OPPORTUNITY_LIMITATIONS,
        error=None,
    )


def change_plan_report(
    status: ChangePlanStatus = ChangePlanStatus.SUCCESS,
) -> ChangePlanReport:
    if status is not ChangePlanStatus.SUCCESS:
        return ChangePlanReport(status, (), (), None)
    return ChangePlanReport(
        status=ChangePlanStatus.SUCCESS,
        operations=(),
        limitations=CHANGE_PLAN_LIMITATIONS,
        error=None,
    )


def draft_report(
    status: ContentDraftStatus = ContentDraftStatus.SUCCESS,
) -> ContentDraftReport:
    if status is not ContentDraftStatus.SUCCESS:
        return ContentDraftReport(status, (), (), None)
    return ContentDraftReport(
        status=ContentDraftStatus.SUCCESS,
        drafts=(),
        limitations=CONTENT_DRAFT_LIMITATIONS,
        error=None,
    )


class FakeHistoryStore:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.created: WorkflowRun | None = None
        self.artifacts: list[ArtifactRecord] = []
        self.finish_calls: list[dict[str, object]] = []

    def create_run(self, run: WorkflowRun) -> None:
        self.events.append("create_run")
        self.created = run

    def append_artifact(self, artifact: ArtifactRecord) -> None:
        self.events.append(f"append:{artifact.artifact_type.value}")
        self.artifacts.append(artifact)

    def finish_run(self, run_id: str, **kwargs: object) -> WorkflowRun:
        status = kwargs["status"]
        assert isinstance(status, RunStatus)
        self.events.append(f"finish:{status.value}")
        self.finish_calls.append({"run_id": run_id, **kwargs})
        assert self.created is not None
        return WorkflowRun(
            run_id=run_id,
            site_key=self.created.site_key,
            workflow_name=self.created.workflow_name,
            started_at=self.created.started_at,
            completed_at=kwargs["completed_at"],
            status=status,
            failure_kind=kwargs.get("failure_kind"),
            sanitized_error=kwargs.get("sanitized_error"),
        )


class FailingHistoryStore(FakeHistoryStore):
    def __init__(
        self,
        events: list[str],
        *,
        fail_create: HistoryStoreError | None = None,
        fail_append_type: ArtifactType | None = None,
        append_error: HistoryStoreError | None = None,
        finish_error: HistoryStoreError | None = None,
    ) -> None:
        super().__init__(events)
        self.fail_create = fail_create
        self.fail_append_type = fail_append_type
        self.append_error = append_error or HistoryStoreError("append failed")
        self.finish_error = finish_error

    def create_run(self, run: WorkflowRun) -> None:
        self.events.append("create_run")
        if self.fail_create is not None:
            raise self.fail_create
        self.created = run

    def append_artifact(self, artifact: ArtifactRecord) -> None:
        self.events.append(f"append:{artifact.artifact_type.value}")
        if artifact.artifact_type is self.fail_append_type:
            raise self.append_error
        self.artifacts.append(artifact)

    def finish_run(self, run_id: str, **kwargs: object) -> WorkflowRun:
        if self.finish_error is not None:
            status = kwargs["status"]
            assert isinstance(status, RunStatus)
            self.events.append(f"finish:{status.value}")
            self.finish_calls.append({"run_id": run_id, **kwargs})
            raise self.finish_error
        return super().finish_run(run_id, **kwargs)


class BlockingSuccessHistoryStore(FakeHistoryStore):
    def __init__(
        self,
        events: list[str],
        *,
        cleanup_error: HistoryStoreError | None = None,
    ) -> None:
        super().__init__(events)
        self.cleanup_error = cleanup_error
        self.success_finish_entered = Event()
        self.release_success_finish = Event()
        self.cleanup_attempted = Event()

    def finish_run(self, run_id: str, **kwargs: object) -> WorkflowRun:
        status = kwargs["status"]
        assert isinstance(status, RunStatus)
        if status is RunStatus.SUCCEEDED:
            self.events.append("finish:succeeded:entered")
            self.success_finish_entered.set()
            if not self.release_success_finish.wait(timeout=5):
                raise AssertionError("Timed out waiting to release success finish.")
            return super().finish_run(run_id, **kwargs)

        self.cleanup_attempted.set()
        self.release_success_finish.set()
        if self.cleanup_error is not None:
            self.events.append("finish:failed")
            self.finish_calls.append({"run_id": run_id, **kwargs})
            raise self.cleanup_error
        return super().finish_run(run_id, **kwargs)


class FakeCrawl:
    def __init__(self, events: list[str], report: SiteCrawlReport) -> None:
        self.events = events
        self.report = report
        self.calls = 0

    async def run(self, seed_url: str) -> SiteCrawlReport:
        self.events.append("crawl")
        self.calls += 1
        self.seed_url = seed_url
        return self.report


class InvalidCrawl(FakeCrawl):
    async def run(self, seed_url: str) -> SiteCrawlReport:
        self.events.append("crawl")
        self.calls += 1
        return "invalid crawl result"  # type: ignore[return-value]


class FakePacketBuilder:
    def __init__(self, events: list[str], packet: SiteContentPacket) -> None:
        self.events = events
        self.packet = packet
        self.calls = 0

    def build(self, report: SiteCrawlReport) -> SiteContentPacket:
        self.events.append("packet")
        self.calls += 1
        self.report = report
        return self.packet


class RaisingPacketBuilder(FakePacketBuilder):
    def __init__(self, events: list[str], error: Exception) -> None:
        super().__init__(events, site_packet())
        self.error = error

    def build(self, report: SiteCrawlReport) -> SiteContentPacket:
        self.events.append("packet")
        self.calls += 1
        raise self.error


class FakeResearch:
    def __init__(self, events: list[str], report: ResearchReport) -> None:
        self.events = events
        self.report = report
        self.calls = 0

    async def run(self, question: str) -> ResearchReport:
        self.events.append("research")
        self.calls += 1
        self.question = question
        return self.report


class RaisingResearch(FakeResearch):
    def __init__(self, events: list[str], error: BaseException) -> None:
        super().__init__(events, research_report())
        self.error = error

    async def run(self, question: str) -> ResearchReport:
        self.events.append("research")
        self.calls += 1
        raise self.error


class FakeOpportunity:
    def __init__(self, events: list[str], report: ContentOpportunityReport) -> None:
        self.events = events
        self.report = report
        self.calls = 0

    async def run(
        self, packet: SiteContentPacket, research: ResearchReport
    ) -> ContentOpportunityReport:
        self.events.append("opportunity")
        self.calls += 1
        self.inputs = (packet, research)
        return self.report


class FakeChangePlan:
    def __init__(self, events: list[str], report: ChangePlanReport) -> None:
        self.events = events
        self.report = report
        self.calls = 0

    async def run(
        self, packet: SiteContentPacket, opportunity: ContentOpportunityReport
    ) -> ChangePlanReport:
        self.events.append("change_plan")
        self.calls += 1
        self.inputs = (packet, opportunity)
        return self.report


class FakeDraft:
    def __init__(self, events: list[str], report: ContentDraftReport) -> None:
        self.events = events
        self.report = report
        self.calls = 0

    async def run(self, value: ContentDraftInput) -> ContentDraftReport:
        self.events.append("content_draft")
        self.calls += 1
        self.input = value
        return self.report


def make_workflow(
    *,
    crawl: SiteCrawlReport | None = None,
    crawl_workflow: FakeCrawl | None = None,
    packet_builder: FakePacketBuilder | None = None,
    research: ResearchReport | None = None,
    research_workflow: FakeResearch | None = None,
    opportunity: ContentOpportunityReport | None = None,
    change_plan: ChangePlanReport | None = None,
    draft: ContentDraftReport | None = None,
    history: FakeHistoryStore | None = None,
    clock: Callable[[], datetime] | None = None,
) -> tuple[EndToEndWorkflow, dict[str, object]]:
    events: list[str] = [] if history is None else history.events
    crawl_stage = crawl_workflow or FakeCrawl(events, crawl or crawl_report())
    packet = packet_builder or FakePacketBuilder(events, site_packet())
    research_stage = research_workflow or FakeResearch(
        events, research or research_report()
    )
    opportunity_stage = FakeOpportunity(
        events, opportunity or opportunity_report()
    )
    change_stage = FakeChangePlan(
        events, change_plan or change_plan_report()
    )
    draft_stage = FakeDraft(events, draft or draft_report())
    store = history or FakeHistoryStore(events)
    identifiers = iter((RUN_ID, *ARTIFACT_IDS))
    workflow = EndToEndWorkflow(
        site_crawl=crawl_stage,
        packet_builder=packet,
        industry_research=research_stage,
        content_opportunity=opportunity_stage,
        change_plan=change_stage,
        content_draft=draft_stage,
        history_store=store,
        id_factory=lambda: next(identifiers),
        clock=clock or (lambda: NOW),
    )
    return workflow, {
        "events": events,
        "crawl": crawl_stage,
        "packet": packet,
        "research": research_stage,
        "opportunity": opportunity_stage,
        "change_plan": change_stage,
        "draft": draft_stage,
        "history": store,
    }


class OrchestrationModelTests(unittest.TestCase):
    def test_request_normalizes_caller_text_and_rejects_credentials(self) -> None:
        request = EndToEndRunRequest(
            "https://example.com/products",
            "  buyer   question  ",
            "  en-US  ",
        )

        self.assertEqual(request.research_question, "buyer question")
        self.assertEqual(request.target_language, "en-US")
        with self.assertRaises(FrozenInstanceError):
            request.target_language = "zh"  # type: ignore[misc]
        with self.assertRaises(ValueError):
            EndToEndRunRequest("https://user:secret@example.com", "question")

    def test_artifact_ref_rejects_noncanonical_identity(self) -> None:
        with self.assertRaises(ValueError):
            ArtifactRef("not-a-uuid", ArtifactType.SITE_CONTENT, 1)


class EndToEndWorkflowSuccessTests(unittest.IsolatedAsyncioTestCase):
    async def test_success_persists_exact_serial_chain_and_returns_refs(self) -> None:
        events: list[str] = []
        crawl = FakeCrawl(events, crawl_report())
        packet_builder = FakePacketBuilder(events, site_packet())
        research = FakeResearch(events, research_report())
        opportunity = FakeOpportunity(events, opportunity_report())
        change_plan = FakeChangePlan(events, change_plan_report())
        content_draft = FakeDraft(events, draft_report())
        history = FakeHistoryStore(events)
        identifiers = iter((RUN_ID, *ARTIFACT_IDS))
        workflow = EndToEndWorkflow(
            site_crawl=crawl,
            packet_builder=packet_builder,
            industry_research=research,
            content_opportunity=opportunity,
            change_plan=change_plan,
            content_draft=content_draft,
            history_store=history,
            id_factory=lambda: next(identifiers),
            clock=lambda: NOW,
        )

        result = await workflow.run(
            EndToEndRunRequest(
                "https://example.com/products",
                "  buyer   question  ",
                " en-US ",
            )
        )

        self.assertEqual(
            events,
            [
                "create_run",
                "crawl",
                "packet",
                "append:site_content",
                "research",
                "append:industry_research",
                "opportunity",
                "append:content_opportunity",
                "change_plan",
                "append:change_plan",
                "content_draft",
                "append:content_draft",
                "finish:succeeded",
            ],
        )
        self.assertEqual(result.run.status, RunStatus.SUCCEEDED)
        self.assertEqual(result.run.workflow_name, "end_to_end_planning_v1")
        self.assertEqual(result.run.site_key, "https://example.com:443")
        self.assertEqual(result.stopped_stage, None)
        self.assertIs(result.crawl_report, crawl.report)
        self.assertIs(result.terminal_report, content_draft.report)
        self.assertTrue(result.requires_human_review)
        self.assertFalse(result.reconciliation_required)
        self.assertEqual(
            tuple(reference.artifact_type for reference in result.artifacts),
            (
                ArtifactType.SITE_CONTENT,
                ArtifactType.INDUSTRY_RESEARCH,
                ArtifactType.CONTENT_OPPORTUNITY,
                ArtifactType.CHANGE_PLAN,
                ArtifactType.CONTENT_DRAFT,
            ),
        )
        self.assertEqual(
            tuple(reference.artifact_id for reference in result.artifacts),
            ARTIFACT_IDS,
        )
        self.assertEqual(
            tuple(artifact.run_id for artifact in history.artifacts),
            (RUN_ID,) * 5,
        )
        self.assertEqual(research.question, "buyer question")
        self.assertEqual(content_draft.input.site_content, packet_builder.packet)
        self.assertEqual(content_draft.input.opportunity_report, opportunity.report)
        self.assertEqual(content_draft.input.change_plan_report, change_plan.report)
        self.assertEqual(content_draft.input.target_language, "en-US")

    def test_constructor_excludes_independent_and_delivery_branches(self) -> None:
        self.assertEqual(
            tuple(inspect.signature(EndToEndWorkflow).parameters),
            (
                "site_crawl",
                "packet_builder",
                "industry_research",
                "content_opportunity",
                "change_plan",
                "content_draft",
                "history_store",
                "id_factory",
                "clock",
            ),
        )
        self.assertEqual(
            tuple(EndToEndStage),
            (
                EndToEndStage.CRAWL,
                EndToEndStage.SITE_CONTENT,
                EndToEndStage.INDUSTRY_RESEARCH,
                EndToEndStage.CONTENT_OPPORTUNITY,
                EndToEndStage.CHANGE_PLAN,
                EndToEndStage.CONTENT_DRAFT,
            ),
        )

    async def test_partial_budget_crawl_with_page_continues(self) -> None:
        workflow, dependencies = make_workflow(
            crawl=crawl_report(stop_reason=CrawlStopReason.TIME_LIMIT)
        )

        result = await workflow.run(
            EndToEndRunRequest("https://example.com/", "question")
        )

        self.assertEqual(result.run.status, RunStatus.SUCCEEDED)
        self.assertEqual(dependencies["packet"].calls, 1)
        self.assertEqual(dependencies["research"].calls, 1)

    async def test_mixed_failed_and_successful_extractions_continue(self) -> None:
        successful_page = crawl_report().pages[0]
        report = replace(
            crawl_report(),
            pages=(failed_crawled_page(), successful_page),
        )
        workflow, dependencies = make_workflow(crawl=report)

        result = await workflow.run(
            EndToEndRunRequest("https://example.com/", "question")
        )

        self.assertEqual(result.run.status, RunStatus.SUCCEEDED)
        self.assertEqual(dependencies["packet"].calls, 1)
        self.assertEqual(dependencies["research"].calls, 1)


class EndToEndWorkflowExpectedFailureTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_failed_extractions_stop_before_packet_and_children(self) -> None:
        report = replace(
            crawl_report(),
            pages=(
                failed_crawled_page(),
                failed_crawled_page(
                    final_url="https://example.com/fetched",
                    title="Fetch metadata title",
                    canonical="https://example.com/fetched",
                    internal_links=("https://example.com/products",),
                ),
            ),
        )
        workflow, dependencies = make_workflow(crawl=report)

        result = await workflow.run(
            EndToEndRunRequest("https://example.com/", "question")
        )

        history = dependencies["history"]
        self.assertEqual(result.run.status, RunStatus.FAILED)
        self.assertEqual(result.stopped_stage, EndToEndStage.CRAWL)
        self.assertEqual(result.artifacts, ())
        self.assertEqual(dependencies["packet"].calls, 0)
        self.assertEqual(dependencies["research"].calls, 0)
        self.assertEqual(dependencies["opportunity"].calls, 0)
        self.assertEqual(dependencies["change_plan"].calls, 0)
        self.assertEqual(dependencies["draft"].calls, 0)
        self.assertEqual(history.artifacts, [])
        self.assertEqual(len(history.finish_calls), 1)
        self.assertEqual(history.finish_calls[0]["status"], RunStatus.FAILED)

    async def test_unusable_crawl_finishes_failed_without_downstream_calls(self) -> None:
        for stop_reason in (
            CrawlStopReason.INVALID_SEED,
            CrawlStopReason.ROBOTS_POLICY,
            CrawlStopReason.TIME_LIMIT,
        ):
            with self.subTest(stop_reason=stop_reason):
                report = crawl_report(
                    stop_reason=stop_reason,
                    include_page=False,
                )
                if stop_reason is CrawlStopReason.INVALID_SEED:
                    report = SiteCrawlReport(
                        seed_url="invalid",
                        exact_origin=None,
                        pages=(),
                        failures=(),
                        resources=report.resources,
                        robots_status=RobotsStatus.NOT_REQUESTED,
                        crawl_delay=None,
                        stop_reason=stop_reason,
                        budget_exhausted=False,
                    )
                workflow, dependencies = make_workflow(crawl=report)

                result = await workflow.run(
                    EndToEndRunRequest("https://example.com/", "question")
                )

                history = dependencies["history"]
                self.assertEqual(result.run.status, RunStatus.FAILED)
                self.assertEqual(result.stopped_stage, EndToEndStage.CRAWL)
                self.assertIs(result.crawl_report, report)
                self.assertIsNone(result.terminal_report)
                self.assertEqual(result.artifacts, ())
                self.assertFalse(result.requires_human_review)
                self.assertEqual(dependencies["packet"].calls, 0)
                self.assertEqual(dependencies["research"].calls, 0)
                self.assertEqual(
                    history.finish_calls[0]["failure_kind"],
                    "site_crawl.no_usable_pages",
                )
                self.assertEqual(
                    history.finish_calls[0]["sanitized_error"],
                    "Site crawl produced no usable evidence.",
                )

    async def test_every_research_failure_status_stops_after_site_content(self) -> None:
        for status in ResearchStatus:
            if status is ResearchStatus.SUCCESS:
                continue
            with self.subTest(status=status):
                failed = research_report(status)
                workflow, dependencies = make_workflow(research=failed)

                result = await workflow.run(
                    EndToEndRunRequest("https://example.com/", "question")
                )

                history = dependencies["history"]
                self.assertEqual(result.run.status, RunStatus.FAILED)
                self.assertEqual(
                    result.stopped_stage,
                    EndToEndStage.INDUSTRY_RESEARCH,
                )
                self.assertIs(result.terminal_report, failed)
                self.assertEqual(
                    tuple(item.artifact_type for item in history.artifacts),
                    (ArtifactType.SITE_CONTENT,),
                )
                self.assertEqual(dependencies["opportunity"].calls, 0)
                self.assertEqual(
                    history.finish_calls[0]["failure_kind"],
                    f"industry_research.{status.value}",
                )
                self.assertNotIn(
                    "SECRET",
                    str(history.finish_calls[0]),
                )

    async def test_opportunity_failure_preserves_prior_artifacts(self) -> None:
        failed = opportunity_report(ContentOpportunityStatus.GENERATION_FAILED)
        workflow, dependencies = make_workflow(opportunity=failed)

        result = await workflow.run(
            EndToEndRunRequest("https://example.com/", "question")
        )

        history = dependencies["history"]
        self.assertEqual(result.stopped_stage, EndToEndStage.CONTENT_OPPORTUNITY)
        self.assertIs(result.terminal_report, failed)
        self.assertEqual(
            tuple(item.artifact_type for item in history.artifacts),
            (ArtifactType.SITE_CONTENT, ArtifactType.INDUSTRY_RESEARCH),
        )
        self.assertEqual(dependencies["change_plan"].calls, 0)
        self.assertEqual(dependencies["draft"].calls, 0)

    async def test_change_plan_failure_stops_draft(self) -> None:
        failed = change_plan_report(ChangePlanStatus.GENERATION_FAILED)
        workflow, dependencies = make_workflow(change_plan=failed)

        result = await workflow.run(
            EndToEndRunRequest("https://example.com/", "question")
        )

        self.assertEqual(result.stopped_stage, EndToEndStage.CHANGE_PLAN)
        self.assertIs(result.terminal_report, failed)
        self.assertEqual(dependencies["draft"].calls, 0)

    async def test_content_draft_failure_finishes_failed(self) -> None:
        failed = draft_report(ContentDraftStatus.GENERATION_FAILED)
        workflow, dependencies = make_workflow(draft=failed)

        result = await workflow.run(
            EndToEndRunRequest("https://example.com/", "question")
        )

        history = dependencies["history"]
        self.assertEqual(result.stopped_stage, EndToEndStage.CONTENT_DRAFT)
        self.assertIs(result.terminal_report, failed)
        self.assertEqual(
            tuple(item.artifact_type for item in history.artifacts),
            (
                ArtifactType.SITE_CONTENT,
                ArtifactType.INDUSTRY_RESEARCH,
                ArtifactType.CONTENT_OPPORTUNITY,
                ArtifactType.CHANGE_PLAN,
            ),
        )


class EndToEndWorkflowHistoryFailureTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_run_failure_makes_zero_child_calls(self) -> None:
        events: list[str] = []
        expected = HistoryStoreError("create failed")
        history = FailingHistoryStore(events, fail_create=expected)
        workflow, dependencies = make_workflow(history=history)

        with self.assertRaises(HistoryStoreError) as raised:
            await workflow.run(
                EndToEndRunRequest("https://example.com/", "question")
            )

        self.assertIs(raised.exception, expected)
        self.assertEqual(events, ["create_run"])
        self.assertEqual(dependencies["crawl"].calls, 0)
        self.assertEqual(history.finish_calls, [])

    async def test_append_failure_stops_children_and_best_effort_finishes(self) -> None:
        events: list[str] = []
        expected = HistoryStoreError("append failed")
        history = FailingHistoryStore(
            events,
            fail_append_type=ArtifactType.SITE_CONTENT,
            append_error=expected,
        )
        workflow, dependencies = make_workflow(history=history)

        with self.assertRaises(HistoryStoreError) as raised:
            await workflow.run(
                EndToEndRunRequest("https://example.com/", "question")
            )

        self.assertIs(raised.exception, expected)
        self.assertEqual(dependencies["research"].calls, 0)
        self.assertEqual(history.finish_calls[0]["status"], RunStatus.FAILED)
        self.assertEqual(
            history.finish_calls[0]["failure_kind"],
            "history.append_failed",
        )

    async def test_append_error_remains_primary_when_failure_finish_also_fails(self) -> None:
        events: list[str] = []
        append_error = HistoryStoreError("append primary")
        history = FailingHistoryStore(
            events,
            fail_append_type=ArtifactType.INDUSTRY_RESEARCH,
            append_error=append_error,
            finish_error=HistoryStoreError("finish secondary"),
        )
        workflow, dependencies = make_workflow(history=history)

        with self.assertRaises(HistoryStoreError) as raised:
            await workflow.run(
                EndToEndRunRequest("https://example.com/", "question")
            )

        self.assertIs(raised.exception, append_error)
        self.assertEqual(dependencies["opportunity"].calls, 0)
        self.assertEqual(len(history.artifacts), 1)
        self.assertEqual(history.finish_calls[0]["status"], RunStatus.FAILED)

    async def test_success_finish_failure_propagates_without_duplicate_artifacts(self) -> None:
        events: list[str] = []
        expected = HistoryStoreError("finish failed")
        history = FailingHistoryStore(events, finish_error=expected)
        workflow, _ = make_workflow(history=history)

        with self.assertRaises(HistoryStoreError) as raised:
            await workflow.run(
                EndToEndRunRequest("https://example.com/", "question")
            )

        self.assertIs(raised.exception, expected)
        self.assertEqual(len(history.artifacts), 5)
        self.assertEqual(len({item.artifact_id for item in history.artifacts}), 5)

    async def test_expected_failure_finish_failure_propagates_store_error(self) -> None:
        events: list[str] = []
        expected = HistoryStoreError("finish failed")
        history = FailingHistoryStore(events, finish_error=expected)
        workflow, _ = make_workflow(
            history=history,
            research=research_report(ResearchStatus.SEARCH_FAILED),
        )

        with self.assertRaises(HistoryStoreError) as raised:
            await workflow.run(
                EndToEndRunRequest("https://example.com/", "question")
            )

        self.assertIs(raised.exception, expected)


class EndToEndWorkflowExceptionTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_crawl_contract_is_internal_error_and_reraised(self) -> None:
        events: list[str] = []
        history = FakeHistoryStore(events)
        workflow, _ = make_workflow(
            crawl_workflow=InvalidCrawl(events, crawl_report()),
            history=history,
        )

        with self.assertRaises(TypeError):
            await workflow.run(
                EndToEndRunRequest("https://example.com/", "question")
            )

        self.assertEqual(history.finish_calls[0]["status"], RunStatus.FAILED)
        self.assertEqual(history.finish_calls[0]["failure_kind"], "internal_error")

    async def test_packet_builder_exception_is_safely_finalized_and_reraised(self) -> None:
        events: list[str] = []
        expected = RuntimeError("SECRET_SENTINEL packet failure")
        packet = RaisingPacketBuilder(events, expected)
        history = FakeHistoryStore(events)
        workflow, _ = make_workflow(packet_builder=packet, history=history)

        with self.assertRaises(RuntimeError) as raised:
            await workflow.run(
                EndToEndRunRequest("https://example.com/", "question")
            )

        self.assertIs(raised.exception, expected)
        self.assertEqual(history.finish_calls[0]["failure_kind"], "internal_error")
        self.assertEqual(
            history.finish_calls[0]["sanitized_error"],
            "Planning workflow failed unexpectedly.",
        )
        self.assertNotIn("SECRET_SENTINEL", str(history.finish_calls))

    async def test_child_exception_remains_primary_when_finish_fails(self) -> None:
        events: list[str] = []
        expected = RuntimeError("SECRET_SENTINEL research failure")
        history = FailingHistoryStore(
            events,
            finish_error=HistoryStoreError("finish secondary"),
        )
        workflow, dependencies = make_workflow(
            research_workflow=RaisingResearch(events, expected),
            history=history,
        )

        with self.assertRaises(RuntimeError) as raised:
            await workflow.run(
                EndToEndRunRequest("https://example.com/", "question")
            )

        self.assertIs(raised.exception, expected)
        self.assertEqual(dependencies["opportunity"].calls, 0)
        self.assertNotIn("SECRET_SENTINEL", str(history.finish_calls))

    async def test_cancellation_best_effort_finishes_and_is_reraised(self) -> None:
        events: list[str] = []
        history = FakeHistoryStore(events)
        workflow, dependencies = make_workflow(
            research_workflow=RaisingResearch(events, asyncio.CancelledError()),
            history=history,
        )

        with self.assertRaises(asyncio.CancelledError):
            await workflow.run(
                EndToEndRunRequest("https://example.com/", "question")
            )

        self.assertEqual(dependencies["opportunity"].calls, 0)
        self.assertEqual(history.finish_calls[0]["status"], RunStatus.FAILED)
        self.assertEqual(history.finish_calls[0]["failure_kind"], "cancelled")
        self.assertEqual(
            history.finish_calls[0]["sanitized_error"],
            "Planning workflow was cancelled.",
        )

    async def test_cancellation_during_success_finish_attempts_failed_finish(self) -> None:
        events: list[str] = []
        history = BlockingSuccessHistoryStore(events)
        workflow, dependencies = make_workflow(history=history)
        task = asyncio.create_task(
            workflow.run(EndToEndRunRequest("https://example.com/", "question"))
        )

        entered = await asyncio.wait_for(
            asyncio.to_thread(history.success_finish_entered.wait, 2),
            timeout=3,
        )
        self.assertTrue(entered)
        self.assertEqual(len(history.artifacts), 5)
        task.cancel()
        try:
            with self.assertRaises(asyncio.CancelledError):
                await task
        finally:
            history.release_success_finish.set()

        self.assertTrue(history.cleanup_attempted.is_set())
        failed_finishes = [
            call
            for call in history.finish_calls
            if call["status"] is RunStatus.FAILED
        ]
        self.assertEqual(len(failed_finishes), 1)
        self.assertEqual(failed_finishes[0]["failure_kind"], "cancelled")
        self.assertEqual(len(history.artifacts), 5)
        self.assertEqual(len({item.artifact_id for item in history.artifacts}), 5)
        self.assertEqual(dependencies["crawl"].calls, 1)
        self.assertEqual(dependencies["research"].calls, 1)
        self.assertEqual(dependencies["opportunity"].calls, 1)
        self.assertEqual(dependencies["change_plan"].calls, 1)
        self.assertEqual(dependencies["draft"].calls, 1)

    async def test_cleanup_conflict_does_not_replace_final_finish_cancellation(
        self,
    ) -> None:
        events: list[str] = []
        history = BlockingSuccessHistoryStore(
            events,
            cleanup_error=HistoryConflictError("success already committed"),
        )
        workflow, dependencies = make_workflow(history=history)
        task = asyncio.create_task(
            workflow.run(EndToEndRunRequest("https://example.com/", "question"))
        )

        entered = await asyncio.wait_for(
            asyncio.to_thread(history.success_finish_entered.wait, 2),
            timeout=3,
        )
        self.assertTrue(entered)
        task.cancel()
        try:
            with self.assertRaises(asyncio.CancelledError):
                await task
        finally:
            history.release_success_finish.set()

        self.assertTrue(history.cleanup_attempted.is_set())
        self.assertEqual(
            sum(
                call["status"] is RunStatus.FAILED
                for call in history.finish_calls
            ),
            1,
        )
        self.assertEqual(len(history.artifacts), 5)
        self.assertEqual(dependencies["crawl"].calls, 1)
        self.assertEqual(dependencies["research"].calls, 1)
        self.assertEqual(dependencies["opportunity"].calls, 1)
        self.assertEqual(dependencies["change_plan"].calls, 1)
        self.assertEqual(dependencies["draft"].calls, 1)

    async def test_final_clock_exception_is_safely_finalized_and_reraised(self) -> None:
        events: list[str] = []
        history = FakeHistoryStore(events)
        expected = RuntimeError("SECRET_SENTINEL clock failure")
        calls = 0

        def clock() -> datetime:
            nonlocal calls
            calls += 1
            if calls == 7:
                raise expected
            return NOW

        workflow, _ = make_workflow(history=history, clock=clock)

        with self.assertRaises(RuntimeError) as raised:
            await workflow.run(
                EndToEndRunRequest("https://example.com/", "question")
            )

        self.assertIs(raised.exception, expected)
        self.assertEqual(len(history.artifacts), 5)
        self.assertEqual(history.finish_calls[0]["status"], RunStatus.FAILED)
        self.assertEqual(history.finish_calls[0]["failure_kind"], "internal_error")
        self.assertNotIn("SECRET_SENTINEL", str(history.finish_calls))

    async def test_failure_finish_clock_exception_is_safely_finalized_and_reraised(self) -> None:
        events: list[str] = []
        history = FakeHistoryStore(events)
        expected = RuntimeError("SECRET_SENTINEL failure clock")
        calls = 0

        def clock() -> datetime:
            nonlocal calls
            calls += 1
            if calls == 3:
                raise expected
            return NOW

        workflow, _ = make_workflow(
            history=history,
            research=research_report(ResearchStatus.SEARCH_FAILED),
            clock=clock,
        )

        with self.assertRaises(RuntimeError) as raised:
            await workflow.run(
                EndToEndRunRequest("https://example.com/", "question")
            )

        self.assertIs(raised.exception, expected)
        self.assertEqual(history.finish_calls[0]["status"], RunStatus.FAILED)
        self.assertEqual(history.finish_calls[0]["failure_kind"], "internal_error")
        self.assertNotIn("SECRET_SENTINEL", str(history.finish_calls))


if __name__ == "__main__":
    unittest.main()
