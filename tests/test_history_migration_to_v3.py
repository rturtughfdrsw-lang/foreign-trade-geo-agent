"""Schema v1/v2/v3 -> v4 migrations preserve legacy data without diagnostics."""

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
    _MIGRATION_V1_TO_V2,
    _MIGRATION_V2_TO_V3,
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
    def assert_legacy_rows_preserved_with_null_diagnostics(
        self,
        db_path: Path,
        before: tuple[object, ...],
    ) -> None:
        after = raw_table_dump(db_path)
        self.assertEqual(
            tuple(row[:-2] for row in after[0]),
            before[0],
        )
        self.assertTrue(all(row[-2:] == (None, None) for row in after[0]))
        self.assertEqual(after[1:], before[1:])

    def _build_v2_database(self, db_path: Path) -> None:
        build_v1_database(db_path)
        connection = sqlite3.connect(db_path)
        try:
            connection.executescript(_MIGRATION_V1_TO_V2)
        finally:
            connection.close()

    def _build_v3_database(self, db_path: Path) -> None:
        self._build_v2_database(db_path)
        connection = sqlite3.connect(db_path)
        try:
            connection.executescript(_MIGRATION_V2_TO_V3)
        finally:
            connection.close()

    def test_empty_database_initializes_directly_to_v4(self) -> None:
        with TemporaryDirectory() as temporary:
            db_path = Path(temporary) / "history.sqlite3"

            SQLiteHistoryStore(db_path)

            self.assertEqual(user_version(db_path), 4)
            self.assertIn("analysis_run_inputs", table_names(db_path))

    def test_v1_database_migrates_to_v4_without_fabricating_diagnostics(self) -> None:
        with TemporaryDirectory() as temporary:
            db_path = Path(temporary) / "history.sqlite3"
            build_v1_database(db_path)
            before = raw_table_dump(db_path)
            self.assertEqual(user_version(db_path), 1)
            self.assertNotIn("wordpress_draft_verifications", table_names(db_path))

            store = SQLiteHistoryStore(db_path)

            self.assertEqual(user_version(db_path), 4)
            self.assertIn("wordpress_draft_verifications", table_names(db_path))
            self.assertIn("analysis_run_inputs", table_names(db_path))
            self.assert_legacy_rows_preserved_with_null_diagnostics(db_path, before)
            self.assertIsNone(store.get_analysis_run_input(RUN_ID))
            run = store.get_run(RUN_ID)
            self.assertIsNotNone(run)
            self.assertIsNone(run.final_validation_category)
            self.assertIsNone(run.writer_attempt_count)
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

    def test_v2_database_migrates_to_v4_without_fabricating_diagnostics(self) -> None:
        with TemporaryDirectory() as temporary:
            db_path = Path(temporary) / "history.sqlite3"
            self._build_v2_database(db_path)
            before = raw_table_dump(db_path)

            store = SQLiteHistoryStore(db_path)

            self.assertEqual(user_version(db_path), 4)
            self.assert_legacy_rows_preserved_with_null_diagnostics(db_path, before)
            self.assertIsNone(store.get_analysis_run_input(RUN_ID))
            run = store.get_run(RUN_ID)
            self.assertIsNone(run.final_validation_category)
            self.assertIsNone(run.writer_attempt_count)

    def test_v3_database_migrates_to_v4_without_fabricating_diagnostics(self) -> None:
        with TemporaryDirectory() as temporary:
            db_path = Path(temporary) / "history.sqlite3"
            self._build_v3_database(db_path)
            before = raw_table_dump(db_path)

            store = SQLiteHistoryStore(db_path)

            self.assertEqual(user_version(db_path), 4)
            self.assert_legacy_rows_preserved_with_null_diagnostics(db_path, before)
            run = store.get_run(RUN_ID)
            self.assertIsNone(run.final_validation_category)
            self.assertIsNone(run.writer_attempt_count)

    def test_existing_demo_database_migrates_without_changing_wordpress_rows(self) -> None:
        with TemporaryDirectory() as temporary:
            db_path = Path(temporary) / "history.sqlite3"
            self._build_v2_database(db_path)
            stamp = NOW.isoformat(timespec="microseconds").replace("+00:00", "Z")
            connection = sqlite3.connect(db_path)
            try:
                connection.execute(
                    "INSERT INTO wordpress_draft_attempts(attempt_id,run_id,content_draft_artifact_id,draft_item_id,target_site_key,fingerprint_version,request_fingerprint,attempted_at,completed_at,outcome,remote_post_id,remote_link,failure_kind,sanitized_error) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        ATTEMPT_SUCCESS,
                        RUN_ID,
                        CONTENT_DRAFT_ARTIFACT_ID,
                        "D1",
                        "https://example.com:443",
                        1,
                        "0" * 64,
                        stamp,
                        stamp,
                        "success",
                        654,
                        "https://example.com/wp-admin/post.php?post=654&action=edit",
                        None,
                        None,
                    ),
                )
                connection.commit()
            finally:
                connection.close()
            before = raw_table_dump(db_path)

            store = SQLiteHistoryStore(db_path)

            self.assertEqual(user_version(db_path), 4)
            self.assert_legacy_rows_preserved_with_null_diagnostics(db_path, before)
            attempt = store.get_wordpress_attempt(ATTEMPT_SUCCESS)
            self.assertIsNotNone(attempt)
            self.assertEqual(attempt.remote_post_id, 654)

    def test_read_only_v1_v2_v3_reader_returns_null_diagnostics_without_migrating(self) -> None:
        for version in (1, 2, 3):
            with self.subTest(version=version), TemporaryDirectory() as temporary:
                db_path = Path(temporary) / "history.sqlite3"
                if version == 1:
                    build_v1_database(db_path)
                elif version == 2:
                    self._build_v2_database(db_path)
                else:
                    self._build_v3_database(db_path)

                reader = SQLiteHistoryReader(db_path)

                self.assertIsNone(reader.get_analysis_run_input(RUN_ID))
                run = reader.get_run(RUN_ID)
                self.assertIsNone(run.final_validation_category)
                self.assertIsNone(run.writer_attempt_count)
                self.assertEqual(user_version(db_path), version)

    def test_legacy_run_without_input_remains_readable(self) -> None:
        with TemporaryDirectory() as temporary:
            db_path = Path(temporary) / "history.sqlite3"
            build_v1_database(db_path)

            view = _review(db_path)
            reader = SQLiteHistoryReader(db_path)

            self.assertEqual(user_version(db_path), 1)
            self.assertEqual(view.draft.draft_id, "D1")
            self.assertEqual(reader.list_wordpress_verifications(ATTEMPT_SUCCESS), ())
            self.assertIsNotNone(reader.get_run(RUN_ID))

    def test_migrated_v1_database_still_supports_blocker_two_review(self) -> None:
        with TemporaryDirectory() as temporary:
            db_path = Path(temporary) / "history.sqlite3"
            build_v1_database(db_path)

            SQLiteHistoryStore(db_path)
            view = _review(db_path)

            self.assertEqual(user_version(db_path), 4)
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
                connection.execute("PRAGMA user_version = 5")
                connection.commit()
            finally:
                connection.close()

            with self.assertRaises(UnsupportedHistoryVersionError):
                SQLiteHistoryStore(db_path)
            with self.assertRaises(UnsupportedHistoryVersionError):
                SQLiteHistoryReader(db_path)


if __name__ == "__main__":
    unittest.main()
