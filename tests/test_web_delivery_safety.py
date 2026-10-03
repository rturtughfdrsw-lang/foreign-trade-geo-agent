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
    WordPressVerificationLookupKind,
    site_key_from_url,
)
from foreign_trade_geo_agent.core.orchestration import EndToEndRunRequest
from foreign_trade_geo_agent.core.wordpress_draft import (
    build_wordpress_draft_request,
    wordpress_request_fingerprint,
)
from foreign_trade_geo_agent.storage.sqlite import SQLiteHistoryStore
from foreign_trade_geo_agent.web.app import create_app
from foreign_trade_geo_agent.web.composition import build_demo_composition
from foreign_trade_geo_agent.web.demo_boundaries import (
    DEMO_RESEARCH_QUESTION,
    DEMO_SITE_URL,
    DEMO_TARGET_LANGUAGE,
)
from foreign_trade_geo_agent.web.demo_wordpress import demo_wordpress_origin


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


def _seed_attempt(composition, run_id: str, outcome, error: str | None = None) -> str:
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
        title_override="Expand observed CNC machining center content",
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
        outcome=outcome,
        completed_at=datetime.now(UTC),
        failure_kind="timeout" if outcome is WordPressAttemptState.UNKNOWN else "http_status",
        sanitized_error=error or "controlled failure",
    )
    return terminal.attempt_id


class DemoDeliverySafetyTests(unittest.TestCase):
    def test_unknown_result_shows_no_retry_warning_and_no_create_cta(self) -> None:
        with TemporaryDirectory() as directory:
            db_path = Path(directory) / "history.sqlite3"
            composition = build_demo_composition(db_path)
            run_id = asyncio.run(_completed_run(db_path))
            attempt_id = _seed_attempt(
                composition, run_id, WordPressAttemptState.UNKNOWN
            )
            with TestClient(create_app(db_path=db_path)) as client:
                response = client.get(f"/runs/{run_id}/deliveries/{attempt_id}")

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "Do not retry create while remote state is uncertain.",
            response.text,
        )
        self.assertNotIn("Create WordPress Draft", response.text)
        self.assertIn("Verify Draft", response.text)

    def test_unknown_verify_is_unresolved_with_zero_get(self) -> None:
        with TemporaryDirectory() as directory:
            db_path = Path(directory) / "history.sqlite3"
            composition = build_demo_composition(db_path)
            run_id = asyncio.run(_completed_run(db_path))
            attempt_id = _seed_attempt(
                composition, run_id, WordPressAttemptState.UNKNOWN
            )
            with TestClient(create_app(db_path=db_path)) as client:
                client.post(
                    f"/runs/{run_id}/deliveries/{attempt_id}/verify",
                    follow_redirects=False,
                )
                response = client.get(
                    f"/runs/{run_id}/deliveries/{attempt_id}/verification"
                )
            verifications = SQLiteHistoryStore(db_path).list_wordpress_verifications(
                attempt_id
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Verification outcome: UNRESOLVED", response.text)
        self.assertEqual(len(verifications), 1)
        self.assertIs(
            verifications[0].lookup_kind,
            WordPressVerificationLookupKind.NONE,
        )

    def test_unknown_second_create_is_blocked_and_posts_once(self) -> None:
        with TemporaryDirectory() as directory:
            db_path = Path(directory) / "history.sqlite3"
            composition = build_demo_composition(db_path)
            run_id = asyncio.run(_completed_run(db_path))
            attempt_id = _seed_attempt(
                composition, run_id, WordPressAttemptState.UNKNOWN
            )
            with TestClient(create_app(db_path=db_path)) as client:
                response = client.post(
                    f"/runs/{run_id}/drafts/D1/delivery",
                    data={"intent_confirmed": "true"},
                    follow_redirects=False,
                )
            attempts = SQLiteHistoryStore(db_path).list_wordpress_attempts(run_id)

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"].rsplit("/", 1)[1], attempt_id)
        self.assertEqual(len(attempts), 1)

    def test_failed_definitely_result_shows_try_delivery_again(self) -> None:
        with TemporaryDirectory() as directory:
            db_path = Path(directory) / "history.sqlite3"
            composition = build_demo_composition(db_path)
            run_id = asyncio.run(_completed_run(db_path))
            attempt_id = _seed_attempt(
                composition, run_id, WordPressAttemptState.FAILED_DEFINITELY
            )
            with TestClient(create_app(db_path=db_path)) as client:
                response = client.get(f"/runs/{run_id}/deliveries/{attempt_id}")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Try Delivery Again", response.text)
        self.assertNotIn("Verify Draft", response.text)

    def test_failed_definitely_setup_renders_and_retry_creates_new_attempt(self) -> None:
        with TemporaryDirectory() as directory:
            db_path = Path(directory) / "history.sqlite3"
            composition = build_demo_composition(db_path)
            run_id = asyncio.run(_completed_run(db_path))
            failed_id = _seed_attempt(
                composition, run_id, WordPressAttemptState.FAILED_DEFINITELY
            )
            with TestClient(create_app(db_path=db_path)) as client:
                setup = client.get(f"/runs/{run_id}/drafts/D1/delivery")
                created = client.post(
                    f"/runs/{run_id}/drafts/D1/delivery",
                    data={"intent_confirmed": "true"},
                    follow_redirects=False,
                )
            attempts = SQLiteHistoryStore(db_path).list_wordpress_attempts(run_id)

        self.assertEqual(setup.status_code, 200)
        self.assertEqual(created.status_code, 303)
        new_id = created.headers["location"].rsplit("/", 1)[1]
        self.assertNotEqual(new_id, failed_id)
        self.assertEqual(len(attempts), 2)
        self.assertIs(
            next(a for a in attempts if a.attempt_id == new_id).outcome,
            WordPressAttemptState.SUCCESS,
        )

    def test_three_attempts_selection_points_to_latest_success(self) -> None:
        with TemporaryDirectory() as directory:
            db_path = Path(directory) / "history.sqlite3"
            composition = build_demo_composition(db_path)
            run_id = asyncio.run(_completed_run(db_path))
            _seed_attempt(composition, run_id, WordPressAttemptState.FAILED_DEFINITELY)
            _seed_attempt(composition, run_id, WordPressAttemptState.FAILED_DEFINITELY)
            with TestClient(create_app(db_path=db_path)) as client:
                created = client.post(
                    f"/runs/{run_id}/drafts/D1/delivery",
                    data={"intent_confirmed": "true"},
                    follow_redirects=False,
                )
                setup = client.get(
                    f"/runs/{run_id}/drafts/D1/delivery",
                    follow_redirects=False,
                )

        self.assertEqual(created.status_code, 303)
        self.assertEqual(setup.status_code, 303)
        self.assertEqual(
            setup.headers["location"],
            created.headers["location"],
        )


if __name__ == "__main__":
    unittest.main()
