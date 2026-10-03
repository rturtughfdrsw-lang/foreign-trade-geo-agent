from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient


class DemoAppTests(unittest.TestCase):
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
        for step in ("progress", "results", "changes", "draft"):
            self.assertIn(f'data-step="{step}"', html)
        self.assertEqual(html.count('aria-disabled="true"'), 4)
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
