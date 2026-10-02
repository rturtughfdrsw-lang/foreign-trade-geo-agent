"""Deterministic text and JSON rendering for WordPress verification results."""

from __future__ import annotations

from datetime import UTC, datetime
import json
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
    WordPressDraftVerificationResult,
)
from foreign_trade_geo_agent.reporting.wordpress_verification import (
    render_wordpress_verification_text,
    wordpress_verification_payload,
)


RUN_ID = "11111111-1111-4111-8111-111111111111"
ARTIFACT_ID = "22222222-2222-4222-8222-222222222222"
ATTEMPT_ID = "33333333-3333-4333-8333-333333333333"
VERIFICATION_ID = "44444444-4444-4444-8444-444444444444"
NOW = datetime(2026, 10, 3, 9, 15, tzinfo=UTC)
SITE_KEY = "https://example.com:443"
NO_RETRY_WARNING = "Do not retry create while remote state is uncertain."


def attempt(outcome: WordPressAttemptState) -> WordPressDraftAttempt:
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
        remote_post_id=41 if success else None,
        remote_link="https://example.com/?p=41" if success else None,
        failure_kind=None if success or pending else "timeout",
        sanitized_error=None if success or pending else "WordPress request timed out.",
    )


def record(outcome: Outcome, **overrides: object) -> WordPressVerification:
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
        "outcome": outcome,
        "failure_kind": FailureKind.TIMEOUT,
        "sanitized_error": "WordPress draft read timed out.",
        "verified_at": NOW,
    }
    values.update(overrides)
    return WordPressVerification(**values)  # type: ignore[arg-type]


class WordPressVerificationTextTests(unittest.TestCase):
    def test_unknown_shows_both_dimensions_and_the_no_retry_warning(self) -> None:
        result = WordPressDraftVerificationResult(
            attempt=attempt(WordPressAttemptState.SUCCESS),
            verification=record(Outcome.UNKNOWN),
        )

        rendered = render_wordpress_verification_text(result)

        self.assertIn("Create outcome: SUCCESS", rendered)
        self.assertIn("Verification outcome: UNKNOWN", rendered)
        self.assertIn(f"Attempt: {ATTEMPT_ID}", rendered)
        self.assertIn(f"Run: {RUN_ID}", rendered)
        self.assertIn("Draft: D1", rendered)
        self.assertIn("Remote post ID: 41", rendered)
        self.assertIn("Failure kind: timeout", rendered)
        self.assertIn("Manual action required: yes", rendered)
        self.assertIn(NO_RETRY_WARNING, rendered)
        self.assertIn(
            "Remote verification is read-only; local verification history "
            "is append-only.",
            rendered,
        )
        self.assertNotIn("verify is read-only", rendered)
        self.assertNotIn("overall", rendered.casefold())

    def test_unresolved_warns_and_states_that_no_lookup_was_possible(self) -> None:
        result = WordPressDraftVerificationResult(
            attempt=attempt(WordPressAttemptState.UNKNOWN),
            verification=record(
                Outcome.UNRESOLVED,
                lookup_kind=LookupKind.NONE,
                failure_kind=FailureKind.NO_REMOTE_IDENTIFIER,
                sanitized_error="No remote identifier is available.",
            ),
        )

        rendered = render_wordpress_verification_text(result)

        self.assertIn("Create outcome: UNKNOWN", rendered)
        self.assertIn("Verification outcome: UNRESOLVED", rendered)
        self.assertIn("Failure kind: no_remote_identifier", rendered)
        self.assertIn("Remote post ID: (none)", rendered)
        self.assertIn("Manual action required: yes", rendered)
        self.assertIn(NO_RETRY_WARNING, rendered)

    def test_verified_needs_no_manual_action_and_omits_the_warning(self) -> None:
        result = WordPressDraftVerificationResult(
            attempt=attempt(WordPressAttemptState.SUCCESS),
            verification=record(
                Outcome.VERIFIED,
                observed_remote_post_id=41,
                observed_status="draft",
                failure_kind=None,
                sanitized_error=None,
            ),
        )

        rendered = render_wordpress_verification_text(result)

        self.assertIn("Verification outcome: VERIFIED", rendered)
        self.assertIn("Observed status: draft", rendered)
        self.assertIn("Manual action required: no", rendered)
        self.assertNotIn(NO_RETRY_WARNING, rendered)

    def test_failed_definitely_is_not_applicable(self) -> None:
        result = WordPressDraftVerificationResult(
            attempt=attempt(WordPressAttemptState.FAILED_DEFINITELY),
            verification=None,
        )

        rendered = render_wordpress_verification_text(result)

        self.assertIn("Create outcome: FAILED_DEFINITELY", rendered)
        self.assertIn("Verification: NOT APPLICABLE", rendered)
        self.assertIn("Manual action required: no", rendered)
        self.assertIn("no remote object is expected", rendered)
        self.assertNotIn(NO_RETRY_WARNING, rendered)


class WordPressVerificationJsonTests(unittest.TestCase):
    def test_payload_mirrors_the_result_without_credentials(self) -> None:
        result = WordPressDraftVerificationResult(
            attempt=attempt(WordPressAttemptState.SUCCESS),
            verification=record(Outcome.UNKNOWN),
        )

        payload = wordpress_verification_payload(result)
        restored = json.loads(json.dumps(payload, ensure_ascii=False))

        self.assertEqual(restored["attempt_id"], ATTEMPT_ID)
        self.assertEqual(restored["run_id"], RUN_ID)
        self.assertEqual(restored["draft_item_id"], "D1")
        self.assertEqual(restored["create_outcome"], "success")
        self.assertEqual(restored["remote_post_id"], 41)
        self.assertEqual(restored["verification_outcome"], "unknown")
        self.assertEqual(restored["failure_kind"], "timeout")
        self.assertTrue(restored["manual_action_required"])
        self.assertFalse(restored["not_applicable"])
        self.assertEqual(restored["remote_mode"], "read_only")
        self.assertEqual(restored["local_history_mode"], "append_only")
        self.assertEqual(restored["no_retry_warning"], NO_RETRY_WARNING)

    def test_not_applicable_payload_has_no_verification_record(self) -> None:
        result = WordPressDraftVerificationResult(
            attempt=attempt(WordPressAttemptState.FAILED_DEFINITELY),
            verification=None,
        )

        payload = wordpress_verification_payload(result)

        self.assertTrue(payload["not_applicable"])
        self.assertIsNone(payload["verification_outcome"])
        self.assertFalse(payload["manual_action_required"])
        self.assertIsNone(payload["verified_at"])
        self.assertIsNone(payload["no_retry_warning"])


if __name__ == "__main__":
    unittest.main()
