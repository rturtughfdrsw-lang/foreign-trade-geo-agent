from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from foreign_trade_geo_agent.core.history import RunStatus, WorkflowRun, site_key_from_url
from foreign_trade_geo_agent.core.orchestration import EndToEndRunRequest
from foreign_trade_geo_agent.storage.sqlite import SQLiteHistoryStore
from foreign_trade_geo_agent.web.application import DemoApplicationService
from foreign_trade_geo_agent.web.composition import build_demo_composition
from foreign_trade_geo_agent.web.demo_boundaries import (
    DEMO_RESEARCH_QUESTION,
    DEMO_SITE_URL,
    DEMO_TARGET_LANGUAGE,
)
from foreign_trade_geo_agent.web.jobs import LocalJobRegistry


RUN_ID = "11111111-1111-4111-8111-111111111111"
NOW = datetime(2026, 10, 3, 8, 30, tzinfo=UTC)


class _GatedWorkflow:
    def __init__(self, started: asyncio.Event, release: asyncio.Event) -> None:
        self.started = started
        self.release = release

    async def run(self, _request: EndToEndRunRequest) -> object:
        self.started.set()
        await self.release.wait()
        return object()


class _FailingWorkflow:
    async def run(self, _request: EndToEndRunRequest) -> object:
        await asyncio.sleep(0)
        raise RuntimeError("SECRET provider payload")


class _FakeComposition:
    def __init__(self, db_path: Path, workflow: object) -> None:
        real = build_demo_composition(db_path)
        self.history_reader = real.history_reader
        self.review_workflow = real.review_workflow
        self._workflow = workflow

    def planning_workflow(self, _observer: object = None) -> object:
        return self._workflow


class DemoApplicationProgressTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_creates_job_and_returns_before_gated_workflow_finishes(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            started = asyncio.Event()
            release = asyncio.Event()
            registry = LocalJobRegistry()
            service = DemoApplicationService(
                _FakeComposition(
                    Path(temporary_directory) / "history.sqlite3",
                    _GatedWorkflow(started, release),
                ),
                registry,
            )

            start_result = service.start_demo_analysis()
            await asyncio.wait_for(started.wait(), timeout=1)

            progress = service.get_progress(job_id=start_result.job_id)
            self.assertTrue(progress.polling)
            self.assertFalse(progress.terminal)
            self.assertIsNone(progress.run_id)
            release.set()
            await registry.shutdown()

    async def test_completed_sqlite_run_recovers_without_memory_job(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            composition = build_demo_composition(
                Path(temporary_directory) / "history.sqlite3"
            )
            result = await composition.planning_workflow().run(
                EndToEndRunRequest(
                    DEMO_SITE_URL,
                    DEMO_RESEARCH_QUESTION,
                    DEMO_TARGET_LANGUAGE,
                )
            )
            service = DemoApplicationService(composition, LocalJobRegistry())

            progress = service.get_progress(run_id=result.run.run_id)

            self.assertTrue(progress.terminal)
            self.assertFalse(progress.polling)
            self.assertFalse(progress.interrupted)
            self.assertTrue(all(stage.state == "Complete" for stage in progress.stages))

    async def test_running_sqlite_run_without_active_job_is_interrupted(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            db_path = Path(temporary_directory) / "history.sqlite3"
            composition = build_demo_composition(db_path)
            SQLiteHistoryStore(db_path).create_run(
                WorkflowRun(
                    run_id=RUN_ID,
                    site_key=site_key_from_url(DEMO_SITE_URL),
                    workflow_name="end_to_end_planning_v1",
                    started_at=NOW,
                    completed_at=None,
                    status=RunStatus.RUNNING,
                    failure_kind=None,
                    sanitized_error=None,
                )
            )
            service = DemoApplicationService(composition, LocalJobRegistry())

            progress = service.get_progress(run_id=RUN_ID)

            self.assertTrue(progress.interrupted)
            self.assertTrue(progress.terminal)
            self.assertFalse(progress.polling)
            self.assertEqual(progress.message, "Interrupted — operator check required")

    async def test_unknown_persisted_run_is_a_sanitized_application_error(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            composition = build_demo_composition(
                Path(temporary_directory) / "history.sqlite3"
            )
            service = DemoApplicationService(composition, LocalJobRegistry())

            with self.assertRaisesRegex(
                RuntimeError,
                "^The planning run was not found\\.$",
            ):
                service.get_progress(run_id=RUN_ID)

    async def test_background_failure_is_sanitized_and_stops_polling(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            registry = LocalJobRegistry()
            service = DemoApplicationService(
                _FakeComposition(
                    Path(temporary_directory) / "history.sqlite3",
                    _FailingWorkflow(),
                ),
                registry,
            )
            start_result = service.start_demo_analysis()
            for _ in range(10):
                await asyncio.sleep(0)
                progress = service.get_progress(job_id=start_result.job_id)
                if progress.terminal:
                    break

            self.assertTrue(progress.terminal)
            self.assertFalse(progress.polling)
            self.assertEqual(progress.message, "Analysis failed unexpectedly.")
            self.assertNotIn("SECRET", progress.message or "")


if __name__ == "__main__":
    unittest.main()
