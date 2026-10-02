"""Verification workflow matrix: create outcome vs verification outcome."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from foreign_trade_geo_agent.core.history import (
    WordPressVerificationFailureKind as FailureKind,
    WordPressVerificationLookupKind as LookupKind,
    WordPressVerificationOutcome as Outcome,
)
from foreign_trade_geo_agent.core.wordpress_verification import (
    WordPressDraftReadOutcome,
    WordPressDraftReadResult,
    WordPressVerificationRequest,
)
from foreign_trade_geo_agent.storage.sqlite import SQLiteHistoryStore
from foreign_trade_geo_agent.workflows.wordpress_verification import (
    WordPressDraftVerificationWorkflow,
    WordPressVerificationError,
)
from tests.review_fixtures import build_review_domain, persist_review_domain
from tests.wordpress_verification_fixtures import (
    ATTEMPT_FAILED,
    ATTEMPT_PENDING,
    ATTEMPT_SUCCESS,
    ATTEMPT_UNKNOWN,
    REMOTE_LINK,
    REMOTE_POST_ID,
    TARGET_SITE_KEY,
    persist_failed_attempt,
    persist_pending_attempt,
    persist_success_attempt,
    persist_unknown_attempt,
)


VERIFICATION_ID = "55555555-5555-4555-8555-555555555555"
NOW = datetime(2026, 10, 3, 9, 15, tzinfo=UTC)


class FakeDraftReader:
    def __init__(
        self,
        *,
        target_site_key: str = TARGET_SITE_KEY,
        result: WordPressDraftReadResult | None = None,
        error: BaseException | None = None,
    ) -> None:
        self.target_site_key = target_site_key
        self._result = result
        self._error = error
        self.calls: list[object] = []

    async def read_draft(self, request: object) -> WordPressDraftReadResult:
        self.calls.append(request)
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result


def found(
    *,
    post_id: int = REMOTE_POST_ID,
    status: str = "draft",
    link: str | None = REMOTE_LINK,
) -> WordPressDraftReadResult:
    return WordPressDraftReadResult(
        outcome=WordPressDraftReadOutcome.FOUND,
        remote_post_id=post_id,
        status=status,
        link=link,
        has_title=True,
        has_content=True,
        failure_kind=None,
        error=None,
    )


def not_found() -> WordPressDraftReadResult:
    return WordPressDraftReadResult(
        outcome=WordPressDraftReadOutcome.NOT_FOUND,
        remote_post_id=None,
        status=None,
        link=None,
        has_title=False,
        has_content=False,
        failure_kind=None,
        error=None,
    )


def failed(
    kind: FailureKind,
    error: str = "WordPress draft read failed.",
) -> WordPressDraftReadResult:
    return WordPressDraftReadResult(
        outcome=WordPressDraftReadOutcome.FAILED,
        remote_post_id=None,
        status=None,
        link=None,
        has_title=False,
        has_content=False,
        failure_kind=kind,
        error=error,
    )


class WordPressDraftVerificationWorkflowTests(unittest.IsolatedAsyncioTestCase):
    def _workflow(self, db_path: Path, reader: FakeDraftReader) -> WordPressDraftVerificationWorkflow:
        counter = {"value": 0}

        def next_id() -> str:
            counter["value"] += 1
            return f"55555555-5555-4555-8555-{counter['value']:012d}"

        return WordPressDraftVerificationWorkflow(
            history_store=SQLiteHistoryStore(db_path),
            draft_reader_factory=lambda _site_key: reader,
            id_factory=next_id,
            clock=lambda: NOW,
        )

    async def _verify(
        self,
        reader: FakeDraftReader,
    ):
        with TemporaryDirectory() as temporary:
            db_path = Path(temporary) / "history.sqlite3"
            persist_review_domain(db_path, await build_review_domain())
            persist_success_attempt(db_path)
            workflow = self._workflow(db_path, reader)
            return await workflow.verify(
                WordPressVerificationRequest(attempt_id=ATTEMPT_SUCCESS)
            )

    async def test_verified_success_attempt_records_draft_identity(self) -> None:
        reader = FakeDraftReader(result=found())

        result = await self._verify(reader)

        self.assertFalse(result.not_applicable)
        self.assertEqual(result.verification_outcome, Outcome.VERIFIED)
        self.assertFalse(result.manual_action_required)
        verification = result.verification
        assert verification is not None
        self.assertEqual(verification.lookup_kind, LookupKind.REMOTE_ID)
        self.assertEqual(verification.observed_remote_post_id, REMOTE_POST_ID)
        self.assertEqual(verification.observed_status, "draft")
        self.assertIsNone(verification.failure_kind)
        self.assertEqual(len(reader.calls), 1)

    async def test_non_draft_status_is_a_mismatch(self) -> None:
        reader = FakeDraftReader(result=found(status="publish"))

        result = await self._verify(reader)

        self.assertEqual(result.verification_outcome, Outcome.MISMATCH)
        self.assertEqual(
            result.verification.failure_kind,
            FailureKind.RESPONSE_NOT_DRAFT,
        )
        self.assertTrue(result.manual_action_required)

    async def test_wrong_remote_id_is_a_mismatch(self) -> None:
        reader = FakeDraftReader(result=found(post_id=99))

        result = await self._verify(reader)

        self.assertEqual(result.verification_outcome, Outcome.MISMATCH)
        self.assertEqual(
            result.verification.failure_kind,
            FailureKind.POST_ID_MISMATCH,
        )
        self.assertEqual(result.verification.observed_remote_post_id, 99)

    async def test_foreign_link_origin_is_a_mismatch(self) -> None:
        reader = FakeDraftReader(result=found(link="https://other.example/?p=41"))

        result = await self._verify(reader)

        self.assertEqual(result.verification_outcome, Outcome.MISMATCH)
        self.assertEqual(
            result.verification.failure_kind,
            FailureKind.LINK_ORIGIN_MISMATCH,
        )

    async def test_missing_link_is_a_mismatch(self) -> None:
        reader = FakeDraftReader(result=found(link=None))

        result = await self._verify(reader)

        self.assertEqual(result.verification_outcome, Outcome.MISMATCH)
        self.assertEqual(
            result.verification.failure_kind,
            FailureKind.LINK_ORIGIN_MISMATCH,
        )

    async def test_trusted_404_is_not_found(self) -> None:
        reader = FakeDraftReader(result=not_found())

        result = await self._verify(reader)

        self.assertEqual(result.verification_outcome, Outcome.NOT_FOUND)
        self.assertTrue(result.manual_action_required)
        self.assertIsNone(result.verification.failure_kind)
        self.assertEqual(result.verification.lookup_kind, LookupKind.REMOTE_ID)

    async def test_remote_failure_is_unknown_and_keeps_the_create_fact(self) -> None:
        reader = FakeDraftReader(result=failed(FailureKind.TIMEOUT))

        with TemporaryDirectory() as temporary:
            db_path = Path(temporary) / "history.sqlite3"
            persist_review_domain(db_path, await build_review_domain())
            persist_success_attempt(db_path)
            store = SQLiteHistoryStore(db_path)
            before = store.get_wordpress_attempt(ATTEMPT_SUCCESS)

            workflow = self._workflow(db_path, reader)
            result = await workflow.verify(
                WordPressVerificationRequest(attempt_id=ATTEMPT_SUCCESS)
            )

            after = SQLiteHistoryStore(db_path).get_wordpress_attempt(ATTEMPT_SUCCESS)

        self.assertEqual(result.verification_outcome, Outcome.UNKNOWN)
        self.assertEqual(result.verification.failure_kind, FailureKind.TIMEOUT)
        self.assertTrue(result.manual_action_required)
        self.assertEqual(len(reader.calls), 1)
        self.assertEqual(before, after)
        self.assertEqual(after.remote_post_id, REMOTE_POST_ID)
        self.assertEqual(after.outcome.value, "success")
        self.assertEqual(result.attempt.outcome.value, "success")

    async def test_unknown_attempt_without_id_is_unresolved_without_requests(self) -> None:
        reader = FakeDraftReader(result=found())

        with TemporaryDirectory() as temporary:
            db_path = Path(temporary) / "history.sqlite3"
            persist_review_domain(db_path, await build_review_domain())
            persist_unknown_attempt(db_path)
            workflow = self._workflow(db_path, reader)

            result = await workflow.verify(
                WordPressVerificationRequest(attempt_id=ATTEMPT_UNKNOWN)
            )
            verification = result.verification

        self.assertEqual(result.verification_outcome, Outcome.UNRESOLVED)
        self.assertEqual(
            verification.failure_kind,
            FailureKind.NO_REMOTE_IDENTIFIER,
        )
        self.assertEqual(verification.lookup_kind, LookupKind.NONE)
        self.assertIsNone(verification.observed_remote_post_id)
        self.assertTrue(result.manual_action_required)
        self.assertEqual(reader.calls, [])
        self.assertEqual(result.attempt.outcome.value, "unknown")

    async def test_pending_attempt_without_id_is_unresolved_without_requests(self) -> None:
        reader = FakeDraftReader(result=found())

        with TemporaryDirectory() as temporary:
            db_path = Path(temporary) / "history.sqlite3"
            persist_review_domain(db_path, await build_review_domain())
            persist_pending_attempt(db_path)
            workflow = self._workflow(db_path, reader)

            result = await workflow.verify(
                WordPressVerificationRequest(attempt_id=ATTEMPT_PENDING)
            )

        self.assertEqual(result.verification_outcome, Outcome.UNRESOLVED)
        self.assertEqual(reader.calls, [])
        self.assertEqual(result.attempt.outcome.value, "pending")

    async def test_failed_definitely_is_not_applicable_and_appends_nothing(self) -> None:
        reader = FakeDraftReader(result=found())

        with TemporaryDirectory() as temporary:
            db_path = Path(temporary) / "history.sqlite3"
            persist_review_domain(db_path, await build_review_domain())
            persist_failed_attempt(db_path)
            store = SQLiteHistoryStore(db_path)
            workflow = self._workflow(db_path, reader)

            result = await workflow.verify(
                WordPressVerificationRequest(attempt_id=ATTEMPT_FAILED)
            )

            records = store.list_wordpress_verifications(ATTEMPT_FAILED)

        self.assertTrue(result.not_applicable)
        self.assertIsNone(result.verification)
        self.assertFalse(result.manual_action_required)
        self.assertEqual(reader.calls, [])
        self.assertEqual(records, ())
        self.assertEqual(result.attempt.outcome.value, "failed_definitely")

    async def test_site_mismatch_is_unresolved_without_remote_requests(self) -> None:
        reader = FakeDraftReader(
            target_site_key="https://other.example:443",
            result=found(),
        )

        result = await self._verify(reader)

        self.assertEqual(result.verification_outcome, Outcome.UNRESOLVED)
        self.assertEqual(result.verification.failure_kind, FailureKind.SITE_MISMATCH)
        self.assertEqual(result.verification.lookup_kind, LookupKind.NONE)
        self.assertEqual(reader.calls, [])

    async def test_reader_exception_fails_closed_as_unknown(self) -> None:
        reader = FakeDraftReader(error=RuntimeError("SECRET reader failure"))

        result = await self._verify(reader)

        self.assertEqual(result.verification_outcome, Outcome.UNKNOWN)
        self.assertEqual(result.verification.failure_kind, FailureKind.REQUEST_FAILED)
        self.assertNotIn("SECRET", result.verification.sanitized_error or "")
        self.assertEqual(len(reader.calls), 1)

    async def test_unknown_attempt_id_raises(self) -> None:
        reader = FakeDraftReader(result=found())

        with TemporaryDirectory() as temporary:
            db_path = Path(temporary) / "history.sqlite3"
            persist_review_domain(db_path, await build_review_domain())
            workflow = self._workflow(db_path, reader)

            with self.assertRaises(WordPressVerificationError):
                await workflow.verify(
                    WordPressVerificationRequest(
                        attempt_id="99999999-9999-4999-8999-999999999999"
                    )
                )

        self.assertEqual(reader.calls, [])

    async def test_repeat_verify_only_appends_history_and_never_recreates(self) -> None:
        reader = FakeDraftReader(result=failed(FailureKind.TIMEOUT))

        with TemporaryDirectory() as temporary:
            db_path = Path(temporary) / "history.sqlite3"
            persist_review_domain(db_path, await build_review_domain())
            persist_success_attempt(db_path)
            store = SQLiteHistoryStore(db_path)
            before_attempts = store.list_wordpress_attempts(store.get_wordpress_attempt(ATTEMPT_SUCCESS).run_id)
            before_artifacts = store.list_artifacts(
                store.get_wordpress_attempt(ATTEMPT_SUCCESS).run_id
            )
            workflow = self._workflow(db_path, reader)
            request = WordPressVerificationRequest(attempt_id=ATTEMPT_SUCCESS)

            first = await workflow.verify(request)
            second = await workflow.verify(request)
            records = store.list_wordpress_verifications(ATTEMPT_SUCCESS)
            after_attempts = store.list_wordpress_attempts(
                store.get_wordpress_attempt(ATTEMPT_SUCCESS).run_id
            )
            after_artifacts = store.list_artifacts(
                store.get_wordpress_attempt(ATTEMPT_SUCCESS).run_id
            )

        self.assertEqual(before_attempts, after_attempts)
        self.assertEqual(before_artifacts, after_artifacts)
        self.assertEqual(len(records), 2)
        self.assertEqual(len(reader.calls), 2)
        self.assertEqual(first.verification_outcome, Outcome.UNKNOWN)
        self.assertEqual(second.verification_outcome, Outcome.UNKNOWN)
        self.assertFalse(hasattr(workflow, "_publisher"))
        self.assertFalse(hasattr(workflow, "_wordpress_delivery"))

    async def test_unknown_requires_a_reader_call_and_unresolved_never_calls(self) -> None:
        unknown_reader = FakeDraftReader(result=failed(FailureKind.TIMEOUT))
        unresolved_reader = FakeDraftReader(result=found())

        unknown_result = await self._verify(unknown_reader)

        with TemporaryDirectory() as temporary:
            db_path = Path(temporary) / "history.sqlite3"
            persist_review_domain(db_path, await build_review_domain())
            persist_unknown_attempt(db_path)
            workflow = self._workflow(db_path, unresolved_reader)
            unresolved_result = await workflow.verify(
                WordPressVerificationRequest(attempt_id=ATTEMPT_UNKNOWN)
            )

        self.assertEqual(unknown_result.verification_outcome, Outcome.UNKNOWN)
        self.assertEqual(len(unknown_reader.calls), 1)
        self.assertEqual(unresolved_result.verification_outcome, Outcome.UNRESOLVED)
        self.assertEqual(len(unresolved_reader.calls), 0)


if __name__ == "__main__":
    unittest.main()
