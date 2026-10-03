from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4

from fastapi.testclient import TestClient

from foreign_trade_geo_agent.core.history import (
    ArtifactType,
    WordPressAttemptState,
    WordPressDraftAttempt,
    site_key_from_url,
)
from foreign_trade_geo_agent.core.orchestration import EndToEndRunRequest
from foreign_trade_geo_agent.core.wordpress_draft import (
    build_wordpress_draft_request,
    wordpress_request_fingerprint,
)
from foreign_trade_geo_agent.storage.sqlite import SQLiteHistoryStore
from foreign_trade_geo_agent.web.application import DeliverySetupState
from foreign_trade_geo_agent.web.app import create_app
from foreign_trade_geo_agent.web.composition import build_demo_composition
from foreign_trade_geo_agent.web.demo_boundaries import (
    DEMO_RESEARCH_QUESTION,
    DEMO_SITE_URL,
    DEMO_TARGET_LANGUAGE,
)
from foreign_trade_geo_agent.web.demo_wordpress import demo_wordpress_origin
from foreign_trade_geo_agent.web.presenters import present_navigation


HOSTILE = "<script>alert(1)</script>"
ESCAPED = "&lt;script&gt;alert(1)&lt;/script&gt;"


async def _completed_run(db_path: Path) -> str:
    composition = build_demo_composition(db_path)
    result = await composition.planning_workflow().run(
        EndToEndRunRequest(
            DEMO_SITE_URL,
            DEMO_RESEARCH_QUESTION,
            DEMO_TARGET_LANGUAGE,
        )
    )
    return result.run.run_id


def _seed_unknown_hostile(composition, run_id: str) -> str:
    artifacts = composition.history_reader.list_artifacts(run_id)
    draft_artifact = next(
        item
        for item in artifacts
        if item.artifact_type is ArtifactType.CONTENT_DRAFT
    )
    draft = next(
        item for item in draft_artifact.payload.drafts if item.draft_id == "D1"
    )
    target = demo_wordpress_origin(run_id)
    site_key = site_key_from_url(target)
    request = build_wordpress_draft_request(
        draft,
        title_override="NovaCNC Machining Center Buyer Guide",
    )
    fingerprint = wordpress_request_fingerprint(site_key, request)
    pending = WordPressDraftAttempt(
        attempt_id=str(uuid4()),
        run_id=run_id,
        content_draft_artifact_id=draft_artifact.artifact_id,
        draft_item_id="D1",
        target_site_key=site_key,
        fingerprint_version=1,
        request_fingerprint=fingerprint,
        attempted_at=datetime.now(UTC) - timedelta(seconds=5),
        completed_at=None,
        outcome=WordPressAttemptState.PENDING,
        remote_post_id=None,
        remote_link=None,
        failure_kind=None,
        sanitized_error=None,
    )
    composition.history_store.begin_wordpress_attempt(pending)
    terminal = composition.history_store.finish_wordpress_attempt(
        pending.attempt_id,
        outcome=WordPressAttemptState.UNKNOWN,
        completed_at=datetime.now(UTC),
        failure_kind="timeout",
        sanitized_error=HOSTILE,
    )
    return terminal.attempt_id


class DemoDeliveryRouteTests(unittest.TestCase):
    def test_setup_renders_selected_draft_and_sandbox_target(self) -> None:
        with TemporaryDirectory() as directory:
            db_path = Path(directory) / "history.sqlite3"
            run_id = asyncio.run(_completed_run(db_path))
            with TestClient(create_app(db_path=db_path)) as client:
                response = client.get(f"/runs/{run_id}/drafts/D1/delivery")

        self.assertEqual(response.status_code, 200)
        html = response.text
        self.assertIn("D1", html)
        self.assertIn("Demo WordPress Sandbox", html)
        self.assertIn(demo_wordpress_origin(run_id), html)
        self.assertIn("Expand observed CNC machining center content", html)

    def test_setup_renders_intent_checkbox_and_exact_create_cta(self) -> None:
        with TemporaryDirectory() as directory:
            db_path = Path(directory) / "history.sqlite3"
            run_id = asyncio.run(_completed_run(db_path))
            with TestClient(create_app(db_path=db_path)) as client:
                response = client.get(f"/runs/{run_id}/drafts/D1/delivery")

        self.assertEqual(response.status_code, 200)
        html = response.text
        self.assertIn('name="intent_confirmed"', html)
        self.assertIn(
            "I reviewed this draft and intend to create a WordPress draft.",
            html,
        )
        self.assertIn("Create WordPress Draft", html)

    def test_forbidden_action_cta_strings_are_absent(self) -> None:
        with TemporaryDirectory() as directory:
            db_path = Path(directory) / "history.sqlite3"
            run_id = asyncio.run(_completed_run(db_path))
            with TestClient(create_app(db_path=db_path)) as client:
                response = client.get(f"/runs/{run_id}/drafts/D1/delivery")

        self.assertEqual(response.status_code, 200)
        html = response.text
        for forbidden in (
            "Publish",
            "Approve & Publish",
            "Push Live",
            "Deploy",
            "Update Existing Post",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, html)
        self.assertIn("No publishing", html)

    def test_setup_checkbox_has_required_semantics(self) -> None:
        with TemporaryDirectory() as directory:
            db_path = Path(directory) / "history.sqlite3"
            run_id = asyncio.run(_completed_run(db_path))
            with TestClient(create_app(db_path=db_path)) as client:
                response = client.get(f"/runs/{run_id}/drafts/D1/delivery")

        self.assertEqual(response.status_code, 200)
        html = response.text
        self.assertIn('name="intent_confirmed"', html)
        self.assertIn("required", html)

    def test_hostile_draft_context_is_escaped_in_setup(self) -> None:
        class FakeService:
            def load_delivery_setup(self, run_id: str, draft_id: str):
                return DeliverySetupState(
                    run_id=run_id,
                    draft_id="D1",
                    content_draft_artifact_id="22222222-2222-4222-8222-222222222222",
                    draft_title=f"Expand observed {HOSTILE} content",
                    change_context="C1",
                    target_site_url="https://demo-wordpress-x.example",
                    existing_attempt_id=None,
                )

            def navigation(self, *, current_step: str, run_id: str | None = None):
                return present_navigation(
                    current_step=current_step,
                    destinations={
                        "start": "/",
                        "progress": None,
                        "results": None,
                        "changes": None,
                        "draft": None,
                    },
                )

        with TemporaryDirectory() as directory:
            db_path = Path(directory) / "history.sqlite3"
            app = create_app(
                db_path=db_path,
                service_factory=lambda _path, _jobs: FakeService(),
            )
            with TestClient(app) as client:
                response = client.get(
                    "/runs/11111111-1111-4111-8111-111111111111/drafts/D1/delivery"
                )

        self.assertEqual(response.status_code, 200)
        html = response.text
        self.assertNotIn(HOSTILE, html)
        self.assertIn(ESCAPED, html)

    def test_setup_get_has_no_side_effect(self) -> None:
        with TemporaryDirectory() as directory:
            db_path = Path(directory) / "history.sqlite3"
            run_id = asyncio.run(_completed_run(db_path))
            with TestClient(create_app(db_path=db_path)) as client:
                response = client.get(f"/runs/{run_id}/drafts/D1/delivery")
            attempts = SQLiteHistoryStore(db_path).list_wordpress_attempts(run_id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(attempts, ())

    def test_create_post_redirects_to_result(self) -> None:
        with TemporaryDirectory() as directory:
            db_path = Path(directory) / "history.sqlite3"
            run_id = asyncio.run(_completed_run(db_path))
            with TestClient(create_app(db_path=db_path)) as client:
                response = client.post(
                    f"/runs/{run_id}/drafts/D1/delivery",
                    data={"intent_confirmed": "true"},
                    follow_redirects=False,
                )

        self.assertEqual(response.status_code, 303)
        self.assertTrue(
            response.headers["location"].startswith(f"/runs/{run_id}/deliveries/")
        )

    def test_result_shows_success_draft_remote_id_and_verify_cta(self) -> None:
        with TemporaryDirectory() as directory:
            db_path = Path(directory) / "history.sqlite3"
            run_id = asyncio.run(_completed_run(db_path))
            with TestClient(create_app(db_path=db_path)) as client:
                created = client.post(
                    f"/runs/{run_id}/drafts/D1/delivery",
                    data={"intent_confirmed": "true"},
                    follow_redirects=False,
                )
                response = client.get(created.headers["location"])

        self.assertEqual(response.status_code, 200)
        html = response.text
        self.assertIn("Draft created", html)
        self.assertIn("Create outcome: SUCCESS", html)
        self.assertIn("41", html)
        self.assertIn("Verify Draft →", html)

    def test_create_without_checkbox_is_sanitized_and_posts_nothing(self) -> None:
        with TemporaryDirectory() as directory:
            db_path = Path(directory) / "history.sqlite3"
            run_id = asyncio.run(_completed_run(db_path))
            with TestClient(create_app(db_path=db_path)) as client:
                response = client.post(
                    f"/runs/{run_id}/drafts/D1/delivery",
                    follow_redirects=False,
                )
            attempts = SQLiteHistoryStore(db_path).list_wordpress_attempts(run_id)

        self.assertNotEqual(response.status_code, 200)
        self.assertIn("intent", response.text)
        self.assertEqual(attempts, ())

    def test_repeat_create_is_blocked_and_posts_once(self) -> None:
        with TemporaryDirectory() as directory:
            db_path = Path(directory) / "history.sqlite3"
            run_id = asyncio.run(_completed_run(db_path))
            with TestClient(create_app(db_path=db_path)) as client:
                first = client.post(
                    f"/runs/{run_id}/drafts/D1/delivery",
                    data={"intent_confirmed": "true"},
                    follow_redirects=False,
                )
                second = client.post(
                    f"/runs/{run_id}/drafts/D1/delivery",
                    data={"intent_confirmed": "true"},
                    follow_redirects=False,
                )
            attempts = SQLiteHistoryStore(db_path).list_wordpress_attempts(run_id)

        self.assertEqual(first.status_code, 303)
        self.assertEqual(second.headers["location"], first.headers["location"])
        self.assertEqual(len(attempts), 1)

    def test_result_get_has_no_side_effect(self) -> None:
        with TemporaryDirectory() as directory:
            db_path = Path(directory) / "history.sqlite3"
            run_id = asyncio.run(_completed_run(db_path))
            with TestClient(create_app(db_path=db_path)) as client:
                created = client.post(
                    f"/runs/{run_id}/drafts/D1/delivery",
                    data={"intent_confirmed": "true"},
                    follow_redirects=False,
                )
                before = SQLiteHistoryStore(db_path).list_wordpress_attempts(run_id)
                response = client.get(created.headers["location"])
                after = SQLiteHistoryStore(db_path).list_wordpress_attempts(run_id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(after, before)

    def test_hostile_error_is_escaped_in_result(self) -> None:
        with TemporaryDirectory() as directory:
            db_path = Path(directory) / "history.sqlite3"
            composition = build_demo_composition(db_path)
            run_id = asyncio.run(_completed_run(db_path))
            attempt_id = _seed_unknown_hostile(composition, run_id)
            with TestClient(create_app(db_path=db_path)) as client:
                response = client.get(
                    f"/runs/{run_id}/deliveries/{attempt_id}"
                )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(HOSTILE, response.text)
        self.assertIn(ESCAPED, response.text)


if __name__ == "__main__":
    unittest.main()
