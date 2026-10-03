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


def _seed_failed_definitely(composition, run_id: str) -> str:
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
        outcome=WordPressAttemptState.FAILED_DEFINITELY,
        completed_at=datetime.now(UTC),
        failure_kind="http_status",
        sanitized_error="WordPress API returned HTTP 400.",
    )
    return terminal.attempt_id


def _create_success(client: TestClient, run_id: str) -> str:
    created = client.post(
        f"/runs/{run_id}/drafts/D1/delivery",
        data={"intent_confirmed": "true"},
        follow_redirects=False,
    )
    return created.headers["location"].rsplit("/", 1)[1]


class DemoVerificationRouteTests(unittest.TestCase):
    def test_explicit_verify_redirects_and_shows_verified(self) -> None:
        with TemporaryDirectory() as directory:
            db_path = Path(directory) / "history.sqlite3"
            run_id = asyncio.run(_completed_run(db_path))
            with TestClient(create_app(db_path=db_path)) as client:
                attempt_id = _create_success(client, run_id)
                verified = client.post(
                    f"/runs/{run_id}/deliveries/{attempt_id}/verify",
                    follow_redirects=False,
                )
                response = client.get(verified.headers["location"])

        self.assertEqual(verified.status_code, 303)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Create outcome: SUCCESS", response.text)
        self.assertIn("Verification outcome: VERIFIED", response.text)

    def test_verification_result_shows_two_orthogonal_outcomes(self) -> None:
        with TemporaryDirectory() as directory:
            db_path = Path(directory) / "history.sqlite3"
            run_id = asyncio.run(_completed_run(db_path))
            with TestClient(create_app(db_path=db_path)) as client:
                attempt_id = _create_success(client, run_id)
                client.post(
                    f"/runs/{run_id}/deliveries/{attempt_id}/verify",
                    follow_redirects=False,
                )
                response = client.get(
                    f"/runs/{run_id}/deliveries/{attempt_id}/verification"
                )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Create outcome", response.text)
        self.assertIn("Verification outcome", response.text)

    def test_verification_get_has_no_side_effect(self) -> None:
        with TemporaryDirectory() as directory:
            db_path = Path(directory) / "history.sqlite3"
            run_id = asyncio.run(_completed_run(db_path))
            with TestClient(create_app(db_path=db_path)) as client:
                attempt_id = _create_success(client, run_id)
                response = client.get(
                    f"/runs/{run_id}/deliveries/{attempt_id}/verification"
                )
                verifications = SQLiteHistoryStore(db_path).list_wordpress_verifications(
                    attempt_id
                )

        self.assertEqual(response.status_code, 200)
        self.assertIn("NOT ATTEMPTED", response.text)
        self.assertEqual(verifications, ())

    def test_failed_definitely_is_not_applicable_and_has_no_verify_cta(self) -> None:
        with TemporaryDirectory() as directory:
            db_path = Path(directory) / "history.sqlite3"
            composition = build_demo_composition(db_path)
            run_id = asyncio.run(_completed_run(db_path))
            attempt_id = _seed_failed_definitely(composition, run_id)
            with TestClient(create_app(db_path=db_path)) as client:
                delivery = client.get(f"/runs/{run_id}/deliveries/{attempt_id}")
                verified = client.post(
                    f"/runs/{run_id}/deliveries/{attempt_id}/verify",
                    follow_redirects=False,
                )
                verification = client.get(verified.headers["location"])
                verifications = SQLiteHistoryStore(db_path).list_wordpress_verifications(
                    attempt_id
                )

        self.assertEqual(delivery.status_code, 200)
        self.assertNotIn("Verify Draft", delivery.text)
        self.assertIn("Try Delivery Again", delivery.text)
        self.assertEqual(verified.status_code, 303)
        self.assertEqual(verification.status_code, 200)
        self.assertIn("NOT APPLICABLE", verification.text)
        self.assertEqual(verifications, ())

    def test_not_attempted_is_derived_before_verify(self) -> None:
        with TemporaryDirectory() as directory:
            db_path = Path(directory) / "history.sqlite3"
            run_id = asyncio.run(_completed_run(db_path))
            with TestClient(create_app(db_path=db_path)) as client:
                attempt_id = _create_success(client, run_id)
                response = client.get(
                    f"/runs/{run_id}/deliveries/{attempt_id}/verification"
                )

        self.assertEqual(response.status_code, 200)
        self.assertIn("NOT ATTEMPTED", response.text)


if __name__ == "__main__":
    unittest.main()
