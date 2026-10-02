"""Core verification models and their UNKNOWN/UNRESOLVED invariants."""

from __future__ import annotations

from datetime import UTC, datetime
import unittest

from foreign_trade_geo_agent.core.history import (
    WordPressAttemptState,
    WordPressDraftAttempt,
    WordPressVerification,
    WordPressVerificationFailureKind as FailureKind,
    WordPressVerificationLookupKind as LookupKind,
    WordPressVerificationOutcome as Outcome,
)
from foreign_trade_geo_agent.core.wordpress_verification import (
    WordPressDraftReadOutcome,
    WordPressDraftReadRequest,
    WordPressDraftReadResult,
    WordPressDraftVerificationResult,
    WordPressVerificationRequest,
    WordPressVerificationValidationError,
)


RUN_ID = "11111111-1111-4111-8111-111111111111"
ARTIFACT_ID = "22222222-2222-4222-8222-222222222222"
ATTEMPT_ID = "33333333-3333-4333-8333-333333333333"
VERIFICATION_ID = "44444444-4444-4444-8444-444444444444"
NOW = datetime(2026, 10, 3, 8, 30, tzinfo=UTC)
SITE_KEY = "https://example.com:443"


def verification(**overrides: object) -> WordPressVerification:
    values: dict[str, object] = {
        "verification_id": VERIFICATION_ID,
        "attempt_id": ATTEMPT_ID,
        "run_id": RUN_ID,
        "content_draft_artifact_id": ARTIFACT_ID,
        "draft_item_id": "D1",
        "target_site_key": SITE_KEY,
        "lookup_kind": LookupKind.REMOTE_ID,
        "observed_remote_post_id": None,
        "observed_status": None,
        "outcome": Outcome.UNKNOWN,
        "failure_kind": FailureKind.TIMEOUT,
        "sanitized_error": "WordPress draft read timed out.",
        "verified_at": NOW,
    }
    values.update(overrides)
    return WordPressVerification(**values)  # type: ignore[arg-type]


class WordPressVerificationRecordTests(unittest.TestCase):
    def test_accepts_every_outcome_with_its_own_shape(self) -> None:
        records = (
            verification(
                outcome=Outcome.VERIFIED,
                lookup_kind=LookupKind.REMOTE_ID,
                observed_remote_post_id=41,
                observed_status="draft",
                failure_kind=None,
                sanitized_error=None,
            ),
            verification(
                outcome=Outcome.NOT_FOUND,
                lookup_kind=LookupKind.REMOTE_ID,
                failure_kind=None,
                sanitized_error=None,
            ),
            verification(
                outcome=Outcome.MISMATCH,
                lookup_kind=LookupKind.REMOTE_ID,
                observed_remote_post_id=41,
                observed_status="publish",
                failure_kind=FailureKind.RESPONSE_NOT_DRAFT,
            ),
            verification(outcome=Outcome.UNKNOWN, failure_kind=FailureKind.TIMEOUT),
            verification(
                outcome=Outcome.UNRESOLVED,
                lookup_kind=LookupKind.NONE,
                failure_kind=FailureKind.NO_REMOTE_IDENTIFIER,
                sanitized_error="No remote identifier is available.",
            ),
        )
        for record in records:
            with self.subTest(outcome=record.outcome):
                self.assertIsInstance(record, WordPressVerification)

    def test_unknown_requires_an_attempted_remote_lookup(self) -> None:
        with self.assertRaises(ValueError):
            verification(outcome=Outcome.UNKNOWN, lookup_kind=LookupKind.NONE)

    def test_unknown_requires_a_remote_failure_kind(self) -> None:
        with self.assertRaises(ValueError):
            verification(
                outcome=Outcome.UNKNOWN,
                lookup_kind=LookupKind.REMOTE_ID,
                failure_kind=FailureKind.NO_REMOTE_IDENTIFIER,
            )

    def test_unresolved_never_carries_a_remote_lookup(self) -> None:
        with self.assertRaises(ValueError):
            verification(
                outcome=Outcome.UNRESOLVED,
                lookup_kind=LookupKind.REMOTE_ID,
                failure_kind=FailureKind.NO_REMOTE_IDENTIFIER,
            )

    def test_unresolved_never_observes_a_remote_object(self) -> None:
        with self.assertRaises(ValueError):
            verification(
                outcome=Outcome.UNRESOLVED,
                lookup_kind=LookupKind.NONE,
                observed_remote_post_id=41,
                failure_kind=FailureKind.NO_REMOTE_IDENTIFIER,
            )

    def test_verified_requires_draft_status_and_no_failure(self) -> None:
        with self.assertRaises(ValueError):
            verification(
                outcome=Outcome.VERIFIED,
                lookup_kind=LookupKind.REMOTE_ID,
                observed_remote_post_id=41,
                observed_status="publish",
                failure_kind=None,
                sanitized_error=None,
            )
        with self.assertRaises(ValueError):
            verification(
                outcome=Outcome.VERIFIED,
                lookup_kind=LookupKind.REMOTE_ID,
                observed_remote_post_id=41,
                observed_status="draft",
                failure_kind=FailureKind.TIMEOUT,
            )

    def test_not_found_requires_a_remote_lookup_and_no_failure(self) -> None:
        with self.assertRaises(ValueError):
            verification(
                outcome=Outcome.NOT_FOUND,
                lookup_kind=LookupKind.NONE,
                failure_kind=None,
                sanitized_error=None,
            )

    def test_failure_and_error_fields_follow_the_outcome(self) -> None:
        with self.assertRaises(ValueError):
            verification(
                outcome=Outcome.NOT_FOUND,
                lookup_kind=LookupKind.REMOTE_ID,
                failure_kind=None,
                sanitized_error="unexpected",
            )
        with self.assertRaises(ValueError):
            verification(
                outcome=Outcome.MISMATCH,
                lookup_kind=LookupKind.REMOTE_ID,
                failure_kind=FailureKind.RESPONSE_NOT_DRAFT,
                sanitized_error=None,
            )

    def test_identifiers_time_and_site_are_validated(self) -> None:
        with self.assertRaises(ValueError):
            verification(verification_id="not-a-uuid")
        with self.assertRaises(ValueError):
            verification(draft_item_id="d1")
        with self.assertRaises(ValueError):
            verification(target_site_key="https://example.com")
        with self.assertRaises(ValueError):
            verification(verified_at=datetime(2026, 10, 3, 8, 30))


class WordPressVerificationRequestTests(unittest.TestCase):
    def test_accepts_a_canonical_attempt_id(self) -> None:
        request = WordPressVerificationRequest(attempt_id=ATTEMPT_ID)

        self.assertEqual(request.attempt_id, ATTEMPT_ID)

    def test_rejects_non_canonical_attempt_ids(self) -> None:
        for value in ("", "not-a-uuid", "33333333-3333-4333-8333-33333333333", 7):
            with self.subTest(value=value):
                with self.assertRaises(WordPressVerificationValidationError):
                    WordPressVerificationRequest(attempt_id=value)  # type: ignore[arg-type]


class WordPressDraftReadModelsTests(unittest.TestCase):
    def test_read_request_requires_a_positive_post_id(self) -> None:
        self.assertEqual(
            WordPressDraftReadRequest(remote_post_id=41).remote_post_id,
            41,
        )
        for value in (0, -1, True, "41"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    WordPressDraftReadRequest(remote_post_id=value)  # type: ignore[arg-type]

    def test_read_result_shapes_are_consistent(self) -> None:
        found = WordPressDraftReadResult(
            outcome=WordPressDraftReadOutcome.FOUND,
            remote_post_id=41,
            status="draft",
            link="https://example.com/?p=41",
            has_title=True,
            has_content=True,
            failure_kind=None,
            error=None,
        )
        self.assertEqual(found.status, "draft")
        with self.assertRaises(ValueError):
            WordPressDraftReadResult(
                outcome=WordPressDraftReadOutcome.FOUND,
                remote_post_id=None,
                status="draft",
                link=None,
                has_title=False,
                has_content=False,
                failure_kind=None,
                error=None,
            )
        with self.assertRaises(ValueError):
            WordPressDraftReadResult(
                outcome=WordPressDraftReadOutcome.FAILED,
                remote_post_id=None,
                status=None,
                link=None,
                has_title=False,
                has_content=False,
                failure_kind=None,
                error="WordPress draft read failed.",
            )


class WordPressDraftVerificationResultTests(unittest.TestCase):
    def _attempt(self, outcome: WordPressAttemptState, remote_post_id: int | None) -> WordPressDraftAttempt:
        success = outcome is WordPressAttemptState.SUCCESS
        pending = outcome is WordPressAttemptState.PENDING
        return WordPressDraftAttempt(
            attempt_id=ATTEMPT_ID,
            run_id=RUN_ID,
            content_draft_artifact_id=ARTIFACT_ID,
            draft_item_id="D1",
            target_site_key=SITE_KEY,
            fingerprint_version=1,
            request_fingerprint="a" * 64,
            attempted_at=NOW,
            completed_at=None if pending else NOW,
            outcome=outcome,
            remote_post_id=remote_post_id,
            remote_link="https://example.com/?p=41" if success else None,
            failure_kind=None if success or pending else "timeout",
            sanitized_error=None if success or pending else "WordPress request timed out.",
        )

    def test_not_applicable_when_no_verification_was_required(self) -> None:
        result = WordPressDraftVerificationResult(
            attempt=self._attempt(WordPressAttemptState.FAILED_DEFINITELY, None),
            verification=None,
        )

        self.assertTrue(result.not_applicable)
        self.assertIsNone(result.verification_outcome)
        self.assertFalse(result.manual_action_required)

    def test_manual_action_tracks_the_verification_outcome(self) -> None:
        verified = WordPressDraftVerificationResult(
            attempt=self._attempt(WordPressAttemptState.SUCCESS, 41),
            verification=verification(
                outcome=Outcome.VERIFIED,
                observed_remote_post_id=41,
                observed_status="draft",
                failure_kind=None,
                sanitized_error=None,
            ),
        )
        unresolved = WordPressDraftVerificationResult(
            attempt=self._attempt(WordPressAttemptState.UNKNOWN, None),
            verification=verification(
                outcome=Outcome.UNRESOLVED,
                lookup_kind=LookupKind.NONE,
                failure_kind=FailureKind.NO_REMOTE_IDENTIFIER,
            ),
        )

        self.assertFalse(verified.not_applicable)
        self.assertFalse(verified.manual_action_required)
        self.assertEqual(verified.verification_outcome, Outcome.VERIFIED)
        self.assertTrue(unresolved.manual_action_required)
        self.assertEqual(unresolved.verification_outcome, Outcome.UNRESOLVED)


if __name__ == "__main__":
    unittest.main()
