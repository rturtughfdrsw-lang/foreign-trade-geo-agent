from __future__ import annotations

import html as html_module
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from foreign_trade_geo_agent.web.presenters import (
    DemoProgressStageView,
    DemoProgressView,
    DemoStartResult,
    present_navigation,
)


STAGES = tuple(
    DemoProgressStageView(str(number), label, "Waiting")
    for number, label in enumerate(
        (
            "Website Crawl",
            "SEO Audit",
            "Industry Research",
            "Content Opportunities",
            "Change Plan",
            "Content Draft",
        ),
        start=1,
    )
)


class _RouteService:
    def __init__(self, progress: DemoProgressView) -> None:
        self.progress = progress
        self.start_calls = 0

    def start_demo_analysis(self) -> DemoStartResult:
        self.start_calls += 1
        return DemoStartResult(job_id="job-1")

    def get_progress(
        self,
        *,
        job_id: str | None = None,
        run_id: str | None = None,
    ) -> DemoProgressView:
        return self.progress

    def navigation(self, *, current_step: str, run_id: str | None = None):
        return present_navigation(
            current_step=current_step,
            destinations={
                "start": "/",
                "progress": None if run_id is None else f"/runs/{run_id}/progress",
                "results": None,
                "changes": None,
                "draft": None,
            },
        )


def _app_for(service: _RouteService, db_path: Path):
    from foreign_trade_geo_agent.web.app import create_app

    return create_app(
        db_path=db_path,
        service_factory=lambda _path, _jobs: service,
    )


class DemoProgressRouteTests(unittest.TestCase):
    def test_start_post_returns_job_progress_without_waiting_for_workflow(self) -> None:
        with TemporaryDirectory() as directory:
            service = _RouteService(
                DemoProgressView(
                    location="/jobs/job-1",
                    run_id=None,
                    stages=STAGES,
                    terminal=False,
                    polling=True,
                    interrupted=False,
                    message=None,
                )
            )
            app = _app_for(service, Path(directory) / "history.sqlite3")
            with TestClient(app) as client:
                response = client.post("/start", follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/jobs/job-1")
        self.assertEqual(service.start_calls, 1)

    def test_progress_partial_replaces_url_after_run_started(self) -> None:
        run_id = "11111111-1111-4111-8111-111111111111"
        with TemporaryDirectory() as directory:
            service = _RouteService(
                DemoProgressView(
                    location=f"/runs/{run_id}/progress",
                    run_id=run_id,
                    stages=(
                        DemoProgressStageView("crawl", "Website Crawl", "Complete"),
                        *STAGES[1:],
                    ),
                    terminal=False,
                    polling=True,
                    interrupted=False,
                    message=None,
                )
            )
            app = _app_for(service, Path(directory) / "history.sqlite3")
            with TestClient(app) as client:
                response = client.get(
                    "/jobs/job-1",
                    headers={"HX-Request": "true"},
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers["HX-Replace-Url"],
            f"/runs/{run_id}/progress",
        )
        self.assertIn('hx-trigger="every 750ms"', response.text)
        self.assertIn(f'hx-get="/runs/{run_id}/progress"', response.text)

    def test_terminal_and_interrupted_progress_stop_htmx_polling(self) -> None:
        run_id = "11111111-1111-4111-8111-111111111111"
        for interrupted, message in (
            (False, None),
            (True, "Interrupted — operator check required"),
        ):
            with self.subTest(interrupted=interrupted), TemporaryDirectory() as directory:
                service = _RouteService(
                    DemoProgressView(
                        location=f"/runs/{run_id}/progress",
                        run_id=run_id,
                        stages=STAGES,
                        terminal=True,
                        polling=False,
                        interrupted=interrupted,
                        message=message,
                    )
                )
                app = _app_for(service, Path(directory) / "history.sqlite3")
                with TestClient(app) as client:
                    response = client.get(f"/runs/{run_id}/progress")

            self.assertEqual(response.status_code, 200)
            self.assertNotIn("hx-trigger", response.text)
            self.assertNotIn("hx-get", response.text)
            if interrupted:
                self.assertIn("Interrupted — operator check required", response.text)

    def test_progress_states_have_visible_non_color_indicators(self) -> None:
        run_id = "11111111-1111-4111-8111-111111111111"
        with TemporaryDirectory() as directory:
            service = _RouteService(
                DemoProgressView(
                    location=f"/runs/{run_id}/progress",
                    run_id=run_id,
                    stages=(
                        DemoProgressStageView("crawl", "Website Crawl", "Complete"),
                        DemoProgressStageView("audit", "SEO Audit", "Running"),
                        DemoProgressStageView("research", "Industry Research", "Waiting"),
                        DemoProgressStageView("draft", "Content Draft", "Failed"),
                    ),
                    terminal=False,
                    polling=True,
                    interrupted=False,
                    message=None,
                )
            )
            app = _app_for(service, Path(directory) / "history.sqlite3")
            with TestClient(app) as client:
                response = client.get(f"/runs/{run_id}/progress")

        self.assertEqual(response.status_code, 200)
        visible = " ".join(html_module.unescape(response.text).split())
        for state, icon, label in (
            ("complete", "✓", "Complete"),
            ("running", "●", "Running"),
            ("waiting", "○", "Waiting"),
            ("failed", "!", "Failed"),
        ):
            self.assertRegex(
                visible,
                rf'class="stage stage-{state}".*?{icon}.*?{label}',
            )


if __name__ == "__main__":
    unittest.main()
