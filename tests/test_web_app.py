from __future__ import annotations

from pathlib import Path
import os
import re
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient


class DemoAppTests(unittest.TestCase):
    def test_demo_and_live_use_separate_db_paths_and_job_registries(self) -> None:
        from foreign_trade_geo_agent.web.app import create_app

        with TemporaryDirectory() as directory:
            demo_path = Path(directory) / "demo.sqlite3"
            live_path = Path(directory) / "live.sqlite3"
            app = create_app(db_path=demo_path, live_db_path=live_path)
            with TestClient(app):
                self.assertNotEqual(app.state.demo_db_path, app.state.live_db_path)
                self.assertIsNot(app.state.demo_jobs, app.state.live_jobs)

    def test_demo_start_route_remains_backward_compatible(self) -> None:
        from foreign_trade_geo_agent.web.app import create_app

        with TemporaryDirectory() as directory, TestClient(
            create_app(db_path=Path(directory) / "demo.sqlite3")
        ) as client:
            response = client.post("/start", follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertTrue(response.headers["location"].startswith("/jobs/"))

    def test_create_app_without_provider_keys_keeps_demo_usable_and_live_unavailable(self) -> None:
        from foreign_trade_geo_agent.web.app import create_app

        with TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            app = create_app(db_path=Path(directory) / "demo.sqlite3")
            with TestClient(app) as client:
                demo = client.get("/")
                live = client.get("/live/start")

        self.assertEqual(demo.status_code, 200)
        self.assertIn("Start Analysis", demo.text)
        self.assertIn("Live analysis is unavailable", live.text)

    def test_zero_key_live_post_creates_no_job_run_or_network(self) -> None:
        from foreign_trade_geo_agent.web.app import create_app

        with TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            app = create_app(
                db_path=Path(directory) / "demo.sqlite3",
                live_db_path=Path(directory) / "live.sqlite3",
            )
            with TestClient(app) as client:
                page = client.get("/live/start")
                token = re.search(
                    r'name="csrf_token" value="([^"]+)"', page.text
                ).group(1)
                response = client.post(
                    "/live/analyses",
                    headers={"Host": "localhost"},
                    data={
                        "csrf_token": token,
                        "website_url": "https://example.com/",
                        "seo_goal": "Improve SEO",
                    },
                )
                self.assertEqual(len(app.state.live_jobs._jobs), 0)

        self.assertEqual(response.status_code, 503)

    def test_app_factory_constructs_without_network_or_creating_a_run(self) -> None:
        from foreign_trade_geo_agent.web.app import create_app

        with TemporaryDirectory() as directory:
            db_path = Path(directory) / "demo" / "history.sqlite3"
            with patch(
                "socket.getaddrinfo",
                side_effect=AssertionError("network forbidden"),
            ):
                app = create_app(db_path=db_path)

            self.assertEqual(app.title, "SEO Agent MVP Demo")
            self.assertFalse(db_path.exists())

    def test_start_page_shows_exact_fixed_inputs_and_demo_disclosures(self) -> None:
        from foreign_trade_geo_agent.web.app import create_app

        with TemporaryDirectory() as directory:
            app = create_app(db_path=Path(directory) / "history.sqlite3")
            with TestClient(app) as client:
                response = client.get("/")

        self.assertEqual(response.status_code, 200)
        html = response.text
        self.assertIn("Demo Mode", html)
        self.assertIn("NovaCNC Machinery", html)
        self.assertIn("https://novacnc.example/", html)
        self.assertIn("Improve product-page SEO and content coverage", html)
        self.assertIn("English", html)
        self.assertIn(
            "Crawl the site, audit SEO, research the category, and plan content changes",
            html,
        )
        self.assertIn(
            "This demo uses a deterministic local snapshot and does not contact external services.",
            html,
        )
        self.assertIn("Plan evidence-backed SEO improvements for NovaCNC Machinery", html)
        self.assertNotIn("Fixed demonstration", html)
        self.assertIn('/static/htmx-2.0.11.min.js', html)
        self.assertNotIn("cdn", html.casefold())
        self.assertNotIn('name="site_url"', html)
        self.assertNotIn('name="research_question"', html)
        self.assertNotIn('name="target_language"', html)

    def test_start_navigation_marks_current_step_and_locks_invalid_destinations(self) -> None:
        from foreign_trade_geo_agent.web.app import create_app

        with TemporaryDirectory() as directory:
            app = create_app(db_path=Path(directory) / "history.sqlite3")
            with TestClient(app) as client:
                response = client.get("/")

        self.assertEqual(response.status_code, 200)
        html = response.text
        self.assertIn('data-step="start"', html)
        self.assertIn('aria-current="page"', html)
        for step in (
            "progress",
            "results",
            "changes",
            "draft",
            "delivery",
            "verification",
        ):
            self.assertIn(f'data-step="{step}"', html)
        self.assertEqual(html.count('aria-disabled="true"'), 6)
        self.assertNotIn('href="/runs/None', html)
        self.assertIn("Locked", html)

    def test_routes_need_no_session_and_set_no_required_cookie(self) -> None:
        from foreign_trade_geo_agent.web.app import create_app

        with TemporaryDirectory() as directory:
            app = create_app(db_path=Path(directory) / "history.sqlite3")
            with TestClient(app) as client:
                response = client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("set-cookie", response.headers)


if __name__ == "__main__":
    unittest.main()
