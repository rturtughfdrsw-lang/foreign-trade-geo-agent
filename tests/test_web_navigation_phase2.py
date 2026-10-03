from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4

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
from foreign_trade_geo_agent.web.application import DemoApplicationService
from foreign_trade_geo_agent.web.composition import build_demo_composition
from foreign_trade_geo_agent.web.demo_boundaries import (
    DEMO_RESEARCH_QUESTION,
    DEMO_SITE_URL,
    DEMO_TARGET_LANGUAGE,
)
from foreign_trade_geo_agent.web.demo_wordpress import demo_wordpress_origin
from foreign_trade_geo_agent.web.jobs import LocalJobRegistry


async def _service_with_run(directory: str):
    db_path = Path(directory) / "history.sqlite3"
    composition = build_demo_composition(db_path)
    result = await composition.planning_workflow().run(
        EndToEndRunRequest(
            DEMO_SITE_URL,
            DEMO_RESEARCH_QUESTION,
            DEMO_TARGET_LANGUAGE,
        )
    )
    service = DemoApplicationService(composition, LocalJobRegistry())
    return composition, service, result.run.run_id, db_path


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
        outcome=WordPressAttemptState.FAILED_DEFINITELY,
        completed_at=datetime.now(UTC),
        failure_kind="http_status",
        sanitized_error="WordPress API returned HTTP 400.",
    )
    return terminal.attempt_id


class DemoNavigationPhase2Tests(unittest.IsolatedAsyncioTestCase):
    async def test_rail_has_seven_steps_in_order(self) -> None:
        with TemporaryDirectory() as directory:
            _composition, service, _run_id, _db_path = await _service_with_run(directory)
            navigation = service.navigation(current_step="start", run_id=None)

        self.assertEqual(
            tuple(item.key for item in navigation.items),
            (
                "start",
                "progress",
                "results",
                "changes",
                "draft",
                "delivery",
                "verification",
            ),
        )

    async def test_delivery_available_when_draft_exists(self) -> None:
        with TemporaryDirectory() as directory:
            _composition, service, run_id, _db_path = await _service_with_run(directory)
            navigation = service.navigation(current_step="draft", run_id=run_id)
            by_key = {item.key: item for item in navigation.items}

        self.assertEqual(by_key["draft"].state, "active")
        self.assertEqual(by_key["delivery"].state, "available")
        self.assertEqual(by_key["verification"].state, "locked")
        self.assertEqual(
            by_key["delivery"].href,
            f"/runs/{run_id}/drafts/D1/delivery",
        )

    async def test_verification_available_after_success(self) -> None:
        with TemporaryDirectory() as directory:
            composition, service, run_id, _db_path = await _service_with_run(directory)
            attempt_id = await service.create_wordpress_draft(
                run_id, "D1", intent_confirmed=True
            )
            navigation = service.navigation(current_step="delivery", run_id=run_id)
            by_key = {item.key: item for item in navigation.items}

        self.assertEqual(by_key["delivery"].state, "active")
        self.assertEqual(by_key["verification"].state, "available")
        self.assertEqual(
            by_key["delivery"].href,
            f"/runs/{run_id}/deliveries/{attempt_id}",
        )
        self.assertEqual(
            by_key["verification"].href,
            f"/runs/{run_id}/deliveries/{attempt_id}/verification",
        )

    async def test_verification_locked_for_failed_definitely(self) -> None:
        with TemporaryDirectory() as directory:
            composition, service, run_id, _db_path = await _service_with_run(directory)
            _seed_failed_definitely(composition, run_id)
            navigation = service.navigation(current_step="delivery", run_id=run_id)
            by_key = {item.key: item for item in navigation.items}

        self.assertEqual(by_key["delivery"].state, "active")
        self.assertEqual(by_key["verification"].state, "locked")
        self.assertIsNone(by_key["verification"].href)
        self.assertEqual(
            by_key["delivery"].href,
            f"/runs/{run_id}/drafts/D1/delivery",
        )

    async def test_refresh_recovers_delivery_and_verification_from_sqlite(self) -> None:
        with TemporaryDirectory() as directory:
            _composition, service, run_id, db_path = await _service_with_run(directory)
            attempt_id = await service.create_wordpress_draft(
                run_id, "D1", intent_confirmed=True
            )
            fresh = DemoApplicationService(
                build_demo_composition(db_path),
                LocalJobRegistry(),
            )
            navigation = fresh.navigation(current_step="delivery", run_id=run_id)

        self.assertEqual(
            navigation.items[5].href,
            f"/runs/{run_id}/deliveries/{attempt_id}",
        )

    async def test_navigation_points_to_latest_attempt(self) -> None:
        with TemporaryDirectory() as directory:
            composition, service, run_id, _db_path = await _service_with_run(directory)
            _seed_failed_definitely(composition, run_id)
            _seed_failed_definitely(composition, run_id)
            success_id = await service.create_wordpress_draft(
                run_id, "D1", intent_confirmed=True
            )
            navigation = service.navigation(current_step="draft", run_id=run_id)
            by_key = {item.key: item for item in navigation.items}

        self.assertEqual(
            by_key["delivery"].href,
            f"/runs/{run_id}/deliveries/{success_id}",
        )


if __name__ == "__main__":
    unittest.main()
