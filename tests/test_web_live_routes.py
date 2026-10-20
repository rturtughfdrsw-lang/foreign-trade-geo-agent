from __future__ import annotations

import os
from pathlib import Path
import re
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from foreign_trade_geo_agent.web.app import create_app
from foreign_trade_geo_agent.web.live_application import LiveStartResult


def _csrf(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    if match is None:
        raise AssertionError("CSRF token was not rendered.")
    return match.group(1)


class _RecordingLiveService:
    def __init__(self, *, ready: bool = True) -> None:
        self.providers_ready = ready
        self.calls: list[object] = []

    def start_live_analysis(self, analysis_input: object) -> LiveStartResult:
        self.calls.append(analysis_input)
        return LiveStartResult("11111111-1111-4111-8111-111111111111")


class LiveRouteTests(unittest.TestCase):
    def _app(self, directory: str, service: _RecordingLiveService):
        return create_app(
            db_path=Path(directory) / "demo.sqlite3",
            live_db_path=Path(directory) / "live.sqlite3",
            live_service_factory=lambda _path, _jobs: service,
        )

    def test_start_page_offers_demo_and_live_analysis_modes(self) -> None:
        with TemporaryDirectory() as directory, TestClient(
            self._app(directory, _RecordingLiveService())
        ) as client:
            response = client.get("/")

        self.assertIn("Demo Mode", response.text)
        self.assertIn("Live Analysis", response.text)
        self.assertIn('href="/live/start"', response.text)

    def test_live_form_contains_url_editable_goal_and_fixed_english(self) -> None:
        with TemporaryDirectory() as directory, TestClient(
            self._app(directory, _RecordingLiveService())
        ) as client:
            response = client.get("/live/start")

        self.assertEqual(response.status_code, 200)
        self.assertIn('name="website_url"', response.text)
        self.assertIn('name="seo_goal"', response.text)
        self.assertIn("English", response.text)
        self.assertIn("readonly", response.text)

    def test_valid_submission_redirects_to_profile_scoped_job(self) -> None:
        service = _RecordingLiveService()
        with TemporaryDirectory() as directory, TestClient(
            self._app(directory, service)
        ) as client:
            token = _csrf(client.get("/live/start").text)
            response = client.post(
                "/live/analyses",
                headers={"Host": "127.0.0.1:8000"},
                data={
                    "csrf_token": token,
                    "website_url": "https://example.com",
                    "seo_goal": "Improve search visibility",
                },
                follow_redirects=False,
            )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(
            response.headers["location"],
            "/live/jobs/11111111-1111-4111-8111-111111111111",
        )
        self.assertEqual(len(service.calls), 1)

    def test_invalid_url_renders_safe_validation_error(self) -> None:
        service = _RecordingLiveService()
        with TemporaryDirectory() as directory, TestClient(
            self._app(directory, service)
        ) as client:
            token = _csrf(client.get("/live/start").text)
            response = client.post(
                "/live/analyses",
                headers={"Host": "localhost:8000"},
                data={
                    "csrf_token": token,
                    "website_url": "http://127.0.0.1/private",
                    "seo_goal": "Improve SEO",
                },
            )

        self.assertEqual(response.status_code, 422)
        self.assertIn("Enter a valid public HTTPS website URL.", response.text)
        self.assertNotIn("127.0.0.1/private", response.text)
        self.assertEqual(service.calls, [])

    def test_unconfigured_submission_returns_sanitized_service_message(self) -> None:
        with TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            app = create_app(
                db_path=Path(directory) / "demo.sqlite3",
                live_db_path=Path(directory) / "live.sqlite3",
            )
            with TestClient(app) as client:
                token = _csrf(client.get("/live/start").text)
                response = client.post(
                    "/live/analyses",
                    headers={"Host": "localhost:8000"},
                    data={
                        "csrf_token": token,
                        "website_url": "https://example.com/",
                        "seo_goal": "Improve SEO",
                    },
                )

        self.assertEqual(response.status_code, 503)
        self.assertIn("provider configuration is incomplete", response.text)

    def test_provider_keys_never_appear_in_html(self) -> None:
        secrets = {
            "TAVILY_API_KEY": "tavily-secret-sentinel",
            "DEEPSEEK_API_KEY": "deepseek-secret-sentinel",
        }
        with TemporaryDirectory() as directory, patch.dict(os.environ, secrets, clear=True):
            app = create_app(
                db_path=Path(directory) / "demo.sqlite3",
                live_db_path=Path(directory) / "live.sqlite3",
            )
            with TestClient(app) as client:
                html = client.get("/live/start").text

        self.assertNotIn(secrets["TAVILY_API_KEY"], html)
        self.assertNotIn(secrets["DEEPSEEK_API_KEY"], html)

    def test_live_form_contains_process_local_csrf_token(self) -> None:
        with TemporaryDirectory() as directory, TestClient(
            self._app(directory, _RecordingLiveService())
        ) as client:
            response = client.get("/live/start")
            token = _csrf(response.text)

        self.assertGreaterEqual(len(token), 32)
        self.assertNotIn(token, str(Path(directory) / "live.sqlite3"))

    def test_missing_csrf_is_rejected_before_job_run_or_network(self) -> None:
        service = _RecordingLiveService()
        with TemporaryDirectory() as directory, TestClient(
            self._app(directory, service)
        ) as client:
            response = client.post(
                "/live/analyses",
                headers={"Host": "localhost"},
                data={"website_url": "https://example.com", "seo_goal": "SEO"},
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(service.calls, [])

    def test_incorrect_csrf_is_rejected_before_job_run_or_network(self) -> None:
        service = _RecordingLiveService()
        with TemporaryDirectory() as directory, TestClient(
            self._app(directory, service)
        ) as client:
            response = client.post(
                "/live/analyses",
                headers={"Host": "localhost"},
                data={
                    "csrf_token": "incorrect-token",
                    "website_url": "https://example.com",
                    "seo_goal": "SEO",
                },
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(service.calls, [])

    def test_hostile_host_is_rejected_before_service_call(self) -> None:
        service = _RecordingLiveService()
        with TemporaryDirectory() as directory, TestClient(
            self._app(directory, service)
        ) as client:
            token = _csrf(client.get("/live/start").text)
            response = client.post(
                "/live/analyses",
                headers={"Host": "attacker.example"},
                data={
                    "csrf_token": token,
                    "website_url": "https://example.com",
                    "seo_goal": "SEO",
                },
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(service.calls, [])

    def test_legitimate_local_form_post_succeeds(self) -> None:
        service = _RecordingLiveService()
        with TemporaryDirectory() as directory, TestClient(
            self._app(directory, service)
        ) as client:
            token = _csrf(client.get("/live/start").text)
            response = client.post(
                "/live/analyses",
                headers={"Host": "localhost:49152"},
                data={
                    "csrf_token": token,
                    "website_url": "https://example.com/",
                    "seo_goal": "SEO",
                },
                follow_redirects=False,
            )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(len(service.calls), 1)

    def test_api_key_and_csrf_token_never_appear_in_sanitized_errors(self) -> None:
        service = _RecordingLiveService()
        with TemporaryDirectory() as directory, TestClient(
            self._app(directory, service)
        ) as client:
            token = _csrf(client.get("/live/start").text)
            response = client.post(
                "/live/analyses",
                headers={"Host": "hostile.example"},
                data={"csrf_token": token},
            )

        self.assertNotIn(token, response.text)
        self.assertNotIn("DEEPSEEK_API_KEY", response.text)


if __name__ == "__main__":
    unittest.main()
