from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4

from foreign_trade_geo_agent.core.history import (
    ArtifactType,
    WordPressAttemptState,
    WordPressDraftAttempt,
    WordPressVerificationOutcome,
    site_key_from_url,
)
from foreign_trade_geo_agent.core.orchestration import EndToEndRunRequest
from foreign_trade_geo_agent.core.wordpress_draft import (
    build_wordpress_draft_request,
    wordpress_request_fingerprint,
)
from foreign_trade_geo_agent.web.application import (
    DemoApplicationError,
    DemoApplicationService,
)
from foreign_trade_geo_agent.web.composition import build_demo_composition
from foreign_trade_geo_agent.web.demo_boundaries import (
    DEMO_RESEARCH_QUESTION,
    DEMO_SITE_URL,
    DEMO_TARGET_LANGUAGE,
)
from foreign_trade_geo_agent.web.demo_wordpress import (
    DEMO_WORDPRESS_POST_ID,
    demo_wordpress_origin,
)
from foreign_trade_geo_agent.web.jobs import LocalJobRegistry


async def _completed_service(directory: str):
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
    return composition, service, result.run.run_id


def _seed_failed_definitely(composition, run_id: str) -> str:
    artifacts = composition.history_reader.list_artifacts(run_id)
    draft_artifact = next(
        item
        for item in artifacts
        if item.artifact_type is ArtifactType.CONTENT_DRAFT
    )
    report = draft_artifact.payload
    draft = next(item for item in report.drafts if item.draft_id == "D1")
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


class DemoDeliveryApplicationTests(unittest.IsolatedAsyncioTestCase):
    async def test_setup_without_attempt_returns_draft_and_sandbox_target(self) -> None:
        with TemporaryDirectory() as directory:
            composition, service, run_id = await _completed_service(directory)
            setup = service.load_delivery_setup(run_id, "D1")

        self.assertEqual(setup.draft_id, "D1")
        self.assertEqual(setup.target_site_url, demo_wordpress_origin(run_id))
        self.assertIsNone(setup.existing_attempt_id)
        self.assertTrue(setup.draft_title)

    async def test_create_without_intent_raises_and_posts_nothing(self) -> None:
        with TemporaryDirectory() as directory:
            composition, service, run_id = await _completed_service(directory)
            with self.assertRaises(DemoApplicationError):
                await service.create_wordpress_draft(
                    run_id, "D1", intent_confirmed=False
                )
            observations = composition.wordpress_transport.observations

        self.assertEqual(len(observations), 0)

    async def test_create_success_persists_attempt_and_returns_attempt_id(self) -> None:
        with TemporaryDirectory() as directory:
            composition, service, run_id = await _completed_service(directory)
            attempt_id = await service.create_wordpress_draft(
                run_id, "D1", intent_confirmed=True
            )
            attempt = composition.history_store.get_wordpress_attempt(attempt_id)
            posts = tuple(
                observation
                for observation in composition.wordpress_transport.observations
                if observation.method == "POST"
            )

        self.assertIsNotNone(attempt)
        self.assertIs(attempt.outcome, WordPressAttemptState.SUCCESS)
        self.assertEqual(attempt.remote_post_id, DEMO_WORDPRESS_POST_ID)
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].requested_status, "draft")

    async def test_load_result_success(self) -> None:
        with TemporaryDirectory() as directory:
            composition, service, run_id = await _completed_service(directory)
            attempt_id = await service.create_wordpress_draft(
                run_id, "D1", intent_confirmed=True
            )
            attempt = service.load_delivery_result(run_id, attempt_id)

        self.assertIs(attempt.outcome, WordPressAttemptState.SUCCESS)

    async def test_verify_success_appends_verified(self) -> None:
        with TemporaryDirectory() as directory:
            composition, service, run_id = await _completed_service(directory)
            attempt_id = await service.create_wordpress_draft(
                run_id, "D1", intent_confirmed=True
            )
            await service.verify_wordpress_draft(run_id, attempt_id)
            state = service.load_verification_result(run_id, attempt_id)
            gets = tuple(
                observation
                for observation in composition.wordpress_transport.observations
                if observation.method == "GET"
            )

        self.assertIs(state.verification.outcome, WordPressVerificationOutcome.VERIFIED)
        self.assertEqual(len(gets), 1)

    async def test_unknown_create_verifies_to_unresolved_with_zero_get(self) -> None:
        with TemporaryDirectory() as directory:
            composition, service, run_id = await _completed_service(directory)
            composition.wordpress_transport.post_timeout = True
            attempt_id = await service.create_wordpress_draft(
                run_id, "D1", intent_confirmed=True
            )
            attempt = composition.history_store.get_wordpress_attempt(attempt_id)
            await service.verify_wordpress_draft(run_id, attempt_id)
            state = service.load_verification_result(run_id, attempt_id)
            gets = tuple(
                observation
                for observation in composition.wordpress_transport.observations
                if observation.method == "GET"
            )
            posts = tuple(
                observation
                for observation in composition.wordpress_transport.observations
                if observation.method == "POST"
            )

        self.assertIs(attempt.outcome, WordPressAttemptState.UNKNOWN)
        self.assertIs(state.verification.outcome, WordPressVerificationOutcome.UNRESOLVED)
        self.assertEqual(len(gets), 0)
        self.assertEqual(len(posts), 1)

    async def test_failed_definitely_is_not_applicable(self) -> None:
        with TemporaryDirectory() as directory:
            composition, service, run_id = await _completed_service(directory)
            attempt_id = _seed_failed_definitely(composition, run_id)
            await service.verify_wordpress_draft(run_id, attempt_id)
            state = service.load_verification_result(run_id, attempt_id)
            gets = tuple(
                observation
                for observation in composition.wordpress_transport.observations
                if observation.method == "GET"
            )

        self.assertIsNone(state.verification)
        self.assertEqual(len(gets), 0)

    async def test_draft_from_other_run_is_rejected_with_zero_post(self) -> None:
        with TemporaryDirectory() as directory:
            composition, service, run_id = await _completed_service(directory)
            with self.assertRaises(DemoApplicationError):
                await service.create_wordpress_draft(
                    "11111111-1111-4111-8111-111111111111",
                    "D1",
                    intent_confirmed=True,
                )
            observations = composition.wordpress_transport.observations

        self.assertEqual(len(observations), 0)

    async def test_attempt_from_other_run_is_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            composition, service, run_id = await _completed_service(directory)
            attempt_id = await service.create_wordpress_draft(
                run_id, "D1", intent_confirmed=True
            )
            with self.assertRaises(DemoApplicationError):
                service.load_delivery_result(
                    "11111111-1111-4111-8111-111111111111",
                    attempt_id,
                )

    async def test_verify_attempt_from_other_run_rejected_before_workflow(self) -> None:
        with TemporaryDirectory() as directory:
            composition, service, run_id = await _completed_service(directory)
            attempt_id = await service.create_wordpress_draft(
                run_id, "D1", intent_confirmed=True
            )
            with self.assertRaises(DemoApplicationError):
                await service.verify_wordpress_draft(
                    "11111111-1111-4111-8111-111111111111",
                    attempt_id,
                )
            gets = tuple(
                observation
                for observation in composition.wordpress_transport.observations
                if observation.method == "GET"
            )

        self.assertEqual(len(gets), 0)

    async def test_unknown_draft_id_in_valid_run_fails_sanitized(self) -> None:
        with TemporaryDirectory() as directory:
            composition, service, run_id = await _completed_service(directory)
            with self.assertRaises(DemoApplicationError) as raised:
                service.load_delivery_setup(run_id, "D99")

        self.assertNotIn("Traceback", str(raised.exception))

    async def test_latest_attempt_is_selected_deterministically(self) -> None:
        with TemporaryDirectory() as directory:
            composition, service, run_id = await _completed_service(directory)
            failed_one = _seed_failed_definitely(composition, run_id)
            failed_two = _seed_failed_definitely(composition, run_id)
            success = await service.create_wordpress_draft(
                run_id, "D1", intent_confirmed=True
            )
            setup = service.load_delivery_setup(run_id, "D1")

        self.assertEqual(setup.existing_attempt_id, success)
        self.assertNotEqual(setup.existing_attempt_id, failed_one)
        self.assertNotEqual(setup.existing_attempt_id, failed_two)

    async def test_latest_verification_is_selected_deterministically(self) -> None:
        with TemporaryDirectory() as directory:
            composition, service, run_id = await _completed_service(directory)
            attempt_id = await service.create_wordpress_draft(
                run_id, "D1", intent_confirmed=True
            )
            await service.verify_wordpress_draft(run_id, attempt_id)
            first = service.load_verification_result(run_id, attempt_id).verification
            await service.verify_wordpress_draft(run_id, attempt_id)
            state = service.load_verification_result(run_id, attempt_id)

        self.assertIsNotNone(first)
        self.assertIsNotNone(state.verification)
        self.assertGreaterEqual(
            state.verification.verified_at,
            first.verified_at,
        )


if __name__ == "__main__":
    unittest.main()
