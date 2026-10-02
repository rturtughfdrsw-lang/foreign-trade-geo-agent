"""Schema v1 -> v2 migration keeps BLOCKER-2 review working."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from foreign_trade_geo_agent.core.history import (
    UnsupportedHistoryVersionError,
    WordPressVerificationFailureKind as FailureKind,
    WordPressVerificationLookupKind as LookupKind,
    WordPressVerificationOutcome as Outcome,
)
from foreign_trade_geo_agent.core.content_draft_review import (
    ContentDraftReviewRequest,
)
from foreign_trade_geo_agent.storage.sqlite import (
    SQLiteHistoryReader,
    SQLiteHistoryStore,
)
from foreign_trade_geo_agent.workflows.content_draft_review import (
    ContentDraftReviewWorkflow,
)
from tests.review_fixtures import CONTENT_DRAFT_ARTIFACT_ID, RUN_ID
from tests.wordpress_verification_fixtures import (
    ATTEMPT_SUCCESS,
    build_v1_database,
    persist_success_attempt,
    raw_table_dump,
    table_names,
    user_version,
)
from foreign_trade_geo_agent.core.history import WordPressVerification


NOW = datetime(2026, 10, 3, 9, 15, tzinfo=UTC)
VERIFICATION_ID = "66666666-6666-4666-8666-666666666666"


def _review(db_path: Path) -> object:
    return ContentDraftReviewWorkflow(
        history_reader=SQLiteHistoryReader(db_path)
    ).review(
        ContentDraftReviewRequest(
            planning_run_id=RUN_ID,
            content_draft_artifact_id=CONTENT_DRAFT_ARTIFACT_ID,
            draft_id="D1",
        )
    )


class SchemaMigrationTests(unittest.TestCase):
    def test_v1_database_migrates_to_v2_without_touching_existing_rows(self) -> None:
        with TemporaryDirectory() as temporary:
            db_path = Path(temporary) / "history.sqlite3"
            build_v1_database(db_path)
            before = raw_table_dump(db_path)
            self.assertEqual(user_version(db_path), 1)
            self.assertNotIn("wordpress_draft_verifications", table_names(db_path))

            store = SQLiteHistoryStore(db_path)

            self.assertEqual(user_version(db_path), 2)
            self.assertIn("wordpress_draft_verifications", table_names(db_path))
            self.assertEqual(raw_table_dump(db_path), before)
            attempt = persist_success_attempt(db_path)
            store.append_wordpress_verification(
                WordPressVerification(
                    verification_id=VERIFICATION_ID,
                    attempt_id=attempt.attempt_id,
                    run_id=RUN_ID,
                    content_draft_artifact_id=CONTENT_DRAFT_ARTIFACT_ID,
                    draft_item_id="D1",
                    target_site_key="https://example.com:443",
                    lookup_kind=LookupKind.NONE,
                    observed_remote_post_id=None,
                    observed_status=None,
                    outcome=Outcome.UNRESOLVED,
                    failure_kind=FailureKind.NO_REMOTE_IDENTIFIER,
                    sanitized_error="No remote identifier is available.",
                    verified_at=NOW,
                )
            )
            self.assertEqual(
                len(store.list_wordpress_verifications(attempt.attempt_id)),
                1,
            )

    def test_read_only_reader_does_not_migrate_a_v1_database(self) -> None:
        with TemporaryDirectory() as temporary:
            db_path = Path(temporary) / "history.sqlite3"
            build_v1_database(db_path)

            view = _review(db_path)
            reader = SQLiteHistoryReader(db_path)

            self.assertEqual(user_version(db_path), 1)
            self.assertEqual(view.draft.draft_id, "D1")
            self.assertEqual(reader.list_wordpress_verifications(ATTEMPT_SUCCESS), ())

    def test_migrated_v1_database_still_supports_blocker_two_review(self) -> None:
        with TemporaryDirectory() as temporary:
            db_path = Path(temporary) / "history.sqlite3"
            build_v1_database(db_path)

            SQLiteHistoryStore(db_path)
            view = _review(db_path)

            self.assertEqual(user_version(db_path), 2)
            self.assertEqual(view.draft.draft_id, "D1")
            self.assertIn(
                "Material selection and port size are observed.",
                view.draft.body_text,
            )
            self.assertEqual(view.change.change_id, "C1")
            self.assertEqual(view.opportunity.recommendation_id, "R1")

    def test_unsupported_future_version_fails_closed(self) -> None:
        with TemporaryDirectory() as temporary:
            db_path = Path(temporary) / "history.sqlite3"
            build_v1_database(db_path)

            connection = sqlite3.connect(db_path)
            try:
                connection.execute("PRAGMA user_version = 3")
                connection.commit()
            finally:
                connection.close()

            with self.assertRaises(UnsupportedHistoryVersionError):
                SQLiteHistoryStore(db_path)
            with self.assertRaises(UnsupportedHistoryVersionError):
                SQLiteHistoryReader(db_path)


if __name__ == "__main__":
    unittest.main()
