from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from foreign_trade_geo_agent.core.history import ArtifactType, RunStatus
from foreign_trade_geo_agent.core.live_analysis import LiveAnalysisInput
from foreign_trade_geo_agent.core.orchestration import EndToEndRunRequest
from foreign_trade_geo_agent.core.search import SearchResponse, SearchStatus
from foreign_trade_geo_agent.web.composition import build_live_composition
from foreign_trade_geo_agent.web.jobs import LocalJobRegistry
from foreign_trade_geo_agent.web.live_application import (
    LiveApplicationError,
    LiveApplicationService,
)
from tests.test_mvp_composed_flow import (
    SITE_URL,
    _FixtureAuditor,
    _FixtureChangePlanWriter,
    _FixtureContentDraftWriter,
    _FixtureFetcher,
    _FixtureOpportunityWriter,
    _FixtureResearchWriter,
    _FixtureSearchProvider,
)


class _CountingRegistry(LocalJobRegistry):
    def __init__(self) -> None:
        super().__init__()
        self.created = 0

    def create_job(self) -> str:
        self.created += 1
        return super().create_job()


class _UnavailableComposition:
    providers_ready = False

    def __init__(self) -> None:
        self.calls = 0

    def planning_workflow(self, _observer: object = None) -> object:
        self.calls += 1
        raise AssertionError("Unconfigured Live must not construct a workflow.")


class _GatedWorkflow:
    def __init__(self, started: asyncio.Event, release: asyncio.Event) -> None:
        self.started = started
        self.release = release
        self.calls = 0

    async def run(self, _request: EndToEndRunRequest) -> object:
        self.calls += 1
        self.started.set()
        await self.release.wait()
        return object()


class _ReadyComposition:
    providers_ready = True

    def __init__(self, workflow: object) -> None:
        self.workflow = workflow
        self.calls = 0

    def planning_workflow(self, _observer: object = None) -> object:
        self.calls += 1
        return self.workflow


class _FailedSearchProvider:
    async def search(self, query: str) -> SearchResponse:
        return SearchResponse(
            query=query,
            status=SearchStatus.FAILED,
            results=(),
            error="sanitized search failure",
        )


async def _wait_terminal(registry: LocalJobRegistry, job_id: str):
    for _ in range(300):
        snapshot = registry.get_job(job_id)
        if snapshot is not None and not snapshot.active:
            return snapshot
        await asyncio.sleep(0.01)
    raise AssertionError("Live job did not reach a terminal state.")


class LiveApplicationServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_unconfigured_server_rejects_before_job_run_or_network(self) -> None:
        composition = _UnavailableComposition()
        jobs = _CountingRegistry()
        service = LiveApplicationService(composition, jobs)

        with self.assertRaises(LiveApplicationError):
            service.start_live_analysis(LiveAnalysisInput(SITE_URL, "Improve SEO"))

        self.assertEqual(jobs.created, 0)
        self.assertEqual(composition.calls, 0)

    async def test_unconfigured_message_is_fixed_and_sanitized(self) -> None:
        service = LiveApplicationService(_UnavailableComposition(), _CountingRegistry())

        with self.assertRaisesRegex(
            LiveApplicationError,
            r"^Live analysis is unavailable because provider configuration is incomplete\.$",
        ):
            service.start_live_analysis(LiveAnalysisInput(SITE_URL, "Improve SEO"))

    async def test_invalid_input_creates_no_job_or_run(self) -> None:
        jobs = _CountingRegistry()
        service = LiveApplicationService(
            _ReadyComposition(_GatedWorkflow(asyncio.Event(), asyncio.Event())),
            jobs,
        )

        with self.assertRaisesRegex(LiveApplicationError, r"^Live analysis input is invalid\.$"):
            service.start_live_analysis(object())  # type: ignore[arg-type]

        self.assertEqual(jobs.created, 0)

    async def test_configured_submission_schedules_one_background_workflow(self) -> None:
        started = asyncio.Event()
        release = asyncio.Event()
        workflow = _GatedWorkflow(started, release)
        jobs = _CountingRegistry()
        service = LiveApplicationService(_ReadyComposition(workflow), jobs)

        result = service.start_live_analysis(LiveAnalysisInput(SITE_URL, "Improve SEO"))
        await asyncio.wait_for(started.wait(), timeout=1)

        self.assertEqual(jobs.created, 1)
        self.assertEqual(workflow.calls, 1)
        self.assertTrue(jobs.get_job(result.job_id).active)  # type: ignore[union-attr]
        release.set()
        await _wait_terminal(jobs, result.job_id)

    async def test_completed_live_run_has_required_analysis_input(self) -> None:
        with TemporaryDirectory() as directory:
            composition = build_live_composition(
                Path(directory) / "live.sqlite3",
                provider_configuration_ready=True,
                fetcher=_FixtureFetcher(),
                planning_site_auditor=_FixtureAuditor(),
                search_provider=_FixtureSearchProvider(),
                research_writer=_FixtureResearchWriter(),
                content_opportunity_writer=_FixtureOpportunityWriter(),
                change_plan_writer=_FixtureChangePlanWriter(),
                content_draft_writer=_FixtureContentDraftWriter(),
            )
            jobs = LocalJobRegistry()
            service = LiveApplicationService(composition, jobs)
            started = service.start_live_analysis(
                LiveAnalysisInput(SITE_URL, "Improve organic search visibility")
            )
            snapshot = await _wait_terminal(jobs, started.job_id)
            assert snapshot.run_id is not None
            run = composition.history_reader.get_run(snapshot.run_id)
            analysis_input = composition.history_reader.get_analysis_run_input(
                snapshot.run_id
            )

        self.assertIs(run.status, RunStatus.FAILED)  # type: ignore[union-attr]
        self.assertEqual(run.failure_kind, "content_draft.invalid_input")
        self.assertEqual(analysis_input.website_url, SITE_URL)  # type: ignore[union-attr]
        self.assertEqual(analysis_input.seo_goal, "Improve organic search visibility")  # type: ignore[union-attr]

    async def test_provider_failure_persists_failed_run_without_fabricated_artifacts(self) -> None:
        with TemporaryDirectory() as directory:
            composition = build_live_composition(
                Path(directory) / "live.sqlite3",
                provider_configuration_ready=True,
                fetcher=_FixtureFetcher(),
                planning_site_auditor=_FixtureAuditor(),
                search_provider=_FailedSearchProvider(),
                research_writer=_FixtureResearchWriter(),
                content_opportunity_writer=_FixtureOpportunityWriter(),
                change_plan_writer=_FixtureChangePlanWriter(),
                content_draft_writer=_FixtureContentDraftWriter(),
            )
            jobs = LocalJobRegistry()
            started = LiveApplicationService(composition, jobs).start_live_analysis(
                LiveAnalysisInput(SITE_URL, "Improve SEO")
            )
            snapshot = await _wait_terminal(jobs, started.job_id)
            assert snapshot.run_id is not None
            run = composition.history_reader.get_run(snapshot.run_id)
            artifacts = composition.history_reader.list_artifacts(snapshot.run_id)

        self.assertIs(run.status, RunStatus.FAILED)  # type: ignore[union-attr]
        self.assertEqual(
            tuple(item.artifact_type for item in artifacts),
            (ArtifactType.SITE_CONTENT, ArtifactType.SITE_AUDIT),
        )

    async def test_second_near_consecutive_start_is_rejected_before_job_run_or_network(self) -> None:
        started = asyncio.Event()
        release = asyncio.Event()
        workflow = _GatedWorkflow(started, release)
        jobs = _CountingRegistry()
        service = LiveApplicationService(_ReadyComposition(workflow), jobs)
        analysis_input = LiveAnalysisInput(SITE_URL, "Improve SEO")

        first = service.start_live_analysis(analysis_input)
        with self.assertRaisesRegex(
            LiveApplicationError,
            r"^A Live analysis is already running\.$",
        ):
            service.start_live_analysis(analysis_input)

        self.assertEqual(jobs.created, 1)
        self.assertEqual(workflow.calls, 0)
        await asyncio.wait_for(started.wait(), timeout=1)
        self.assertEqual(workflow.calls, 1)
        release.set()
        await _wait_terminal(jobs, first.job_id)

    async def test_terminal_live_job_releases_single_active_slot(self) -> None:
        started = asyncio.Event()
        release = asyncio.Event()
        workflow = _GatedWorkflow(started, release)
        jobs = _CountingRegistry()
        service = LiveApplicationService(_ReadyComposition(workflow), jobs)
        analysis_input = LiveAnalysisInput(SITE_URL, "Improve SEO")

        first = service.start_live_analysis(analysis_input)
        release.set()
        await _wait_terminal(jobs, first.job_id)
        second = service.start_live_analysis(analysis_input)

        self.assertNotEqual(first.job_id, second.job_id)
        await _wait_terminal(jobs, second.job_id)


if __name__ == "__main__":
    unittest.main()
