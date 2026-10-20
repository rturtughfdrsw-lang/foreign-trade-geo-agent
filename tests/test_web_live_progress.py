from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from foreign_trade_geo_agent.core.history import (
    AnalysisRunInput,
    PlanningValidationCategory,
    RunStatus,
    WorkflowRun,
    site_key_from_url,
)
from foreign_trade_geo_agent.core.orchestration import (
    EndToEndProgressEvent,
    EndToEndProgressEventKind,
    EndToEndRunRequest,
    EndToEndStage,
)
from foreign_trade_geo_agent.core.live_analysis import LiveAnalysisInput
from foreign_trade_geo_agent.web.app import create_app
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


RUN_ID = "11111111-1111-4111-8111-111111111111"
NOW = datetime(2026, 10, 4, 8, 0, tzinfo=UTC)


def _live_composition(db_path: Path):
    return build_live_composition(
        db_path,
        provider_configuration_ready=True,
        fetcher=_FixtureFetcher(),
        planning_site_auditor=_FixtureAuditor(),
        search_provider=_FixtureSearchProvider(),
        research_writer=_FixtureResearchWriter(),
        content_opportunity_writer=_FixtureOpportunityWriter(),
        change_plan_writer=_FixtureChangePlanWriter(),
        content_draft_writer=_FixtureContentDraftWriter(),
    )


class LiveProgressTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_run_validation_diagnostics_remain_operator_only(self) -> None:
        with TemporaryDirectory() as directory:
            composition = _live_composition(Path(directory) / "live.sqlite3")
            running = WorkflowRun(
                RUN_ID,
                site_key_from_url(SITE_URL),
                "end_to_end_planning_v1",
                NOW,
                None,
                RunStatus.RUNNING,
                None,
                None,
            )
            normalized = LiveAnalysisInput(SITE_URL, "Improve SEO")
            composition.history_store.create_analysis_run(
                running,
                AnalysisRunInput(
                    RUN_ID,
                    normalized.website_url,
                    normalized.seo_goal,
                    normalized.target_language,
                    normalized.display_identity,
                ),
            )
            composition.history_store.finish_run(
                RUN_ID,
                status=RunStatus.FAILED,
                completed_at=NOW,
                failure_kind="content_opportunity.invalid_output",
                sanitized_error="Content opportunity stage failed.",
                final_validation_category=PlanningValidationCategory.FIELD_CONTRACT,
                writer_attempt_count=1,
            )

            progress = LiveApplicationService(
                composition, LocalJobRegistry()
            ).get_progress(run_id=RUN_ID)

        self.assertEqual(progress.message, "Content opportunity stage failed.")
        self.assertNotIn("FIELD_CONTRACT", repr(progress))

    async def test_active_job_reports_only_real_stage_events(self) -> None:
        with TemporaryDirectory() as directory:
            composition = _live_composition(Path(directory) / "live.sqlite3")
            jobs = LocalJobRegistry()
            job_id = jobs.create_job()
            observer = jobs.observer_for(job_id)
            observer(
                EndToEndProgressEvent(
                    EndToEndProgressEventKind.RUN_STARTED,
                    RUN_ID,
                    None,
                )
            )
            observer(
                EndToEndProgressEvent(
                    EndToEndProgressEventKind.STAGE_STARTED,
                    RUN_ID,
                    EndToEndStage.CRAWL,
                )
            )
            task = asyncio.create_task(asyncio.Event().wait())
            jobs.attach_task(job_id, task)
            service = LiveApplicationService(composition, jobs)

            progress = service.get_progress(job_id=job_id)
            await jobs.shutdown()

        self.assertEqual(progress.stages[0].state, "Running")
        self.assertTrue(all(stage.state == "Waiting" for stage in progress.stages[1:]))

    async def test_refresh_recovers_completed_stages_from_live_database(self) -> None:
        with TemporaryDirectory() as directory:
            composition = _live_composition(Path(directory) / "live.sqlite3")
            result = await composition.planning_workflow().run(
                EndToEndRunRequest(SITE_URL, "Improve SEO", "en")
            )
            service = LiveApplicationService(composition, LocalJobRegistry())

            progress = service.get_progress(run_id=result.run.run_id)

        self.assertTrue(progress.terminal)
        self.assertFalse(progress.polling)
        self.assertTrue(all(stage.state == "Complete" for stage in progress.stages[:-1]))
        self.assertEqual(progress.stages[-1].state, "Failed")

    async def test_running_run_without_active_job_is_interrupted(self) -> None:
        with TemporaryDirectory() as directory:
            composition = _live_composition(Path(directory) / "live.sqlite3")
            run = WorkflowRun(
                RUN_ID,
                site_key_from_url(SITE_URL),
                "end_to_end_planning_v1",
                NOW,
                None,
                RunStatus.RUNNING,
                None,
                None,
            )
            normalized = LiveAnalysisInput(SITE_URL, "Improve SEO")
            composition.history_store.create_analysis_run(
                run,
                AnalysisRunInput(
                    RUN_ID,
                    normalized.website_url,
                    normalized.seo_goal,
                    normalized.target_language,
                    normalized.display_identity,
                ),
            )
            service = LiveApplicationService(composition, LocalJobRegistry())

            progress = service.get_progress(run_id=RUN_ID)

        self.assertTrue(progress.interrupted)
        self.assertEqual(progress.message, "Interrupted — operator check required")

    async def test_live_run_missing_required_input_is_invariant_failure(self) -> None:
        with TemporaryDirectory() as directory:
            composition = _live_composition(Path(directory) / "live.sqlite3")
            composition.history_store.create_run(
                WorkflowRun(
                    RUN_ID,
                    site_key_from_url(SITE_URL),
                    "end_to_end_planning_v1",
                    NOW,
                    None,
                    RunStatus.RUNNING,
                    None,
                    None,
                )
            )
            service = LiveApplicationService(composition, LocalJobRegistry())

            with self.assertRaisesRegex(
                LiveApplicationError,
                r"^Live analysis history is incomplete\.$",
            ):
                service.get_progress(run_id=RUN_ID)

    async def test_live_workflow_rail_stops_at_draft_review(self) -> None:
        with TemporaryDirectory() as directory:
            db_path = Path(directory) / "live.sqlite3"
            composition = _live_composition(db_path)
            result = await composition.planning_workflow().run(
                EndToEndRunRequest(SITE_URL, "Improve SEO", "en")
            )
            with patch.dict("os.environ", {}, clear=True), TestClient(
                create_app(
                    db_path=Path(directory) / "demo.sqlite3",
                    live_db_path=db_path,
                )
            ) as client:
                response = client.get(
                    f"/live/runs/{result.run.run_id}/progress"
                )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Draft Review", response.text)
        self.assertNotIn("WordPress Delivery", response.text)
        self.assertNotIn("Verification", response.text)

    async def test_progress_contains_no_percentage_timer_tokens_or_reasoning(self) -> None:
        with TemporaryDirectory() as directory:
            composition = _live_composition(Path(directory) / "live.sqlite3")
            result = await composition.planning_workflow().run(
                EndToEndRunRequest(SITE_URL, "Improve SEO", "en")
            )
            service = LiveApplicationService(composition, LocalJobRegistry())

            text = repr(service.get_progress(run_id=result.run.run_id)).casefold()

        for forbidden in ("percent", "timer", "token", "reasoning"):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
