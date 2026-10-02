from __future__ import annotations

from datetime import UTC, datetime, timedelta
from contextlib import closing
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from foreign_trade_geo_agent.core.audit import AuditStatus, SiteAuditResult
from foreign_trade_geo_agent.core.history import (
    ArtifactRecord,
    ArtifactType,
    HistoryConflictError,
    RunStatus,
    WordPressAttemptState,
    WordPressDraftAttempt,
    WordPressVerification,
    WordPressVerificationFailureKind,
    WordPressVerificationLookupKind,
    WordPressVerificationOutcome,
    UnsupportedHistoryVersionError,
    WorkflowRun,
)
from tests.test_wordpress_delivery_workflow import draft_report
from foreign_trade_geo_agent.storage.sqlite import SQLiteHistoryStore
from tests.review_fixtures import CONTENT_DRAFT_ARTIFACT_ID, persist_review_fixture
from tests.wordpress_verification_fixtures import (
    ATTEMPT_SUCCESS,
    ATTEMPT_UNKNOWN,
    REMOTE_POST_ID,
    persist_success_attempt,
    persist_unknown_attempt,
)


RUN_1 = "11111111-1111-4111-8111-111111111111"
RUN_2 = "22222222-2222-4222-8222-222222222222"
ARTIFACT_1 = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
ARTIFACT_2 = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
ARTIFACT_3 = "99999999-9999-4999-8999-999999999999"
ATTEMPT_1 = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
ATTEMPT_2 = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
NOW = datetime(2026, 10, 2, 8, 30, tzinfo=UTC)


def running_run(run_id: str, *, site_key: str = "https://example.com:443", started_at: datetime = NOW) -> WorkflowRun:
    return WorkflowRun(
        run_id=run_id,
        site_key=site_key,
        workflow_name="content_draft",
        started_at=started_at,
        completed_at=None,
        status=RunStatus.RUNNING,
        failure_kind=None,
        sanitized_error=None,
    )


def audit() -> SiteAuditResult:
    return SiteAuditResult(
        url="https://example.com",
        status=AuditStatus.FAILED,
        score=None,
        band=None,
        score_breakdown={},
        recommendations=(),
        error="audit_failed",
        source="test",
        source_version="1",
    )


class SQLiteHistoryStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "history.sqlite3"
        self.store = SQLiteHistoryStore(self.db_path)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_initializes_v2_schema_with_foreign_keys_constraints_and_indexes(self) -> None:
        self.assertTrue(self.db_path.is_file())
        with closing(sqlite3.connect(self.db_path)) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 2)
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            indexes = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='index'")}
            self.assertTrue(
                {
                    "runs",
                    "artifacts",
                    "wordpress_draft_attempts",
                    "wordpress_draft_verifications",
                }
                <= tables
            )
            self.assertIn("uq_wp_attempts_blocking_fingerprint", indexes)
            self.assertIn("ix_wp_verifications_attempt", indexes)
            unique_sql = connection.execute(
                "SELECT sql FROM sqlite_master WHERE name='uq_wp_attempts_blocking_fingerprint'"
            ).fetchone()[0]
            self.assertIn("WHERE outcome IN ('pending','success','unknown')", unique_sql)
            self.assertTrue(connection.execute("PRAGMA foreign_key_list(artifacts)").fetchall())
            self.assertTrue(
                connection.execute(
                    "PRAGMA foreign_key_list(wordpress_draft_verifications)"
                ).fetchall()
            )
        self.assertTrue(self.store.foreign_keys_enabled())

    def test_reopen_preserves_runs_and_artifacts(self) -> None:
        self.store.create_run(running_run(RUN_1))
        self.store.append_artifact(
            ArtifactRecord(
                artifact_id=ARTIFACT_1,
                run_id=RUN_1,
                artifact_type=ArtifactType.SITE_AUDIT,
                payload_version=1,
                created_at=NOW,
                payload=audit(),
            )
        )
        reopened = SQLiteHistoryStore(self.db_path)
        self.assertEqual(reopened.get_run(RUN_1), running_run(RUN_1))
        self.assertEqual(reopened.get_artifact(ARTIFACT_1).payload, audit())

    def test_unknown_user_version_fails_closed(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute("PRAGMA user_version = 99")
            connection.commit()
        with self.assertRaises(UnsupportedHistoryVersionError):
            SQLiteHistoryStore(self.db_path)

    def test_missing_parent_directory_is_not_created(self) -> None:
        path = Path(self.temp.name) / "missing" / "history.sqlite3"
        with self.assertRaises(FileNotFoundError):
            SQLiteHistoryStore(path)
        self.assertFalse(path.parent.exists())

    def test_memory_database_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            SQLiteHistoryStore(":memory:")

    def test_duplicate_run_and_invalid_atomic_finishes_are_conflicts(self) -> None:
        self.store.create_run(running_run(RUN_1))
        with self.assertRaises(HistoryConflictError):
            self.store.create_run(running_run(RUN_1))
        finished = self.store.finish_run(
            RUN_1,
            status=RunStatus.SUCCEEDED,
            completed_at=NOW + timedelta(minutes=1),
        )
        self.assertEqual(finished.status, RunStatus.SUCCEEDED)
        with self.assertRaises(HistoryConflictError):
            self.store.finish_run(
                RUN_1,
                status=RunStatus.FAILED,
                completed_at=NOW + timedelta(minutes=2),
                failure_kind="late_failure",
                sanitized_error="late failure",
            )

    def test_finish_run_cannot_commit_completion_before_start(self) -> None:
        self.store.create_run(running_run(RUN_1))
        with self.assertRaises(HistoryConflictError):
            self.store.finish_run(
                RUN_1,
                status=RunStatus.SUCCEEDED,
                completed_at=NOW - timedelta(seconds=1),
            )
        self.assertEqual(self.store.get_run(RUN_1).status, RunStatus.RUNNING)

    def test_same_second_fractional_run_completion_succeeds(self) -> None:
        started_at = datetime(2026, 10, 2, 8, 30, 0, 0, tzinfo=UTC)
        completed_at = datetime(2026, 10, 2, 8, 30, 0, 500000, tzinfo=UTC)
        self.store.create_run(running_run(RUN_1, started_at=started_at))
        finished = self.store.finish_run(
            RUN_1,
            status=RunStatus.SUCCEEDED,
            completed_at=completed_at,
        )
        self.assertEqual(finished.completed_at, completed_at)
        reopened = SQLiteHistoryStore(self.db_path)
        self.assertEqual(reopened.get_run(RUN_1).completed_at, completed_at)

    def test_same_second_reverse_chronology_run_is_rejected_and_stays_running(self) -> None:
        started_at = datetime(2026, 10, 2, 8, 30, 0, 500000, tzinfo=UTC)
        completed_at = datetime(2026, 10, 2, 8, 30, 0, 0, tzinfo=UTC)
        self.store.create_run(running_run(RUN_1, started_at=started_at))
        with self.assertRaises(HistoryConflictError):
            self.store.finish_run(
                RUN_1,
                status=RunStatus.SUCCEEDED,
                completed_at=completed_at,
            )
        reopened = SQLiteHistoryStore(self.db_path)
        self.assertEqual(reopened.get_run(RUN_1).status, RunStatus.RUNNING)
        self.assertIsNone(reopened.get_run(RUN_1).completed_at)

    def test_invalid_terminal_run_metadata_rolls_back_without_finishing(self) -> None:
        for failure_kind in ("", "   "):
            with self.subTest(failure_kind=failure_kind):
                store = self._new_store(f"run-blank-{len(failure_kind)}.sqlite3")
                store.create_run(running_run(RUN_1))
                with self.assertRaises(ValueError):
                    store.finish_run(
                        RUN_1,
                        status=RunStatus.FAILED,
                        completed_at=NOW + timedelta(seconds=1),
                        failure_kind=failure_kind,
                        sanitized_error="failed",
                    )
                self.assertEqual(store.get_run(RUN_1).status, RunStatus.RUNNING)

    def test_blank_terminal_run_fields_are_rejected_at_database_layer(self) -> None:
        self.store.create_run(running_run(RUN_1))
        completed = (NOW + timedelta(minutes=1)).astimezone(UTC).isoformat().replace("+00:00", "Z")
        with closing(sqlite3.connect(self.db_path)) as connection:
            for column in ("failure_kind", "sanitized_error"):
                for blank in ("", "   "):
                    with self.subTest(column=column, blank=blank):
                        if column == "failure_kind":
                            parameters = (completed, blank, "storage failure", RUN_1)
                        else:
                            parameters = (completed, "storage failure", blank, RUN_1)
                        with self.assertRaises(sqlite3.IntegrityError):
                            connection.execute(
                                "UPDATE runs SET completed_at=?,status='failed',failure_kind=?,sanitized_error=? WHERE run_id=? AND status='running'",
                                parameters,
                            )
                        connection.rollback()
        self.assertEqual(self.store.get_run(RUN_1).status, RunStatus.RUNNING)

    def test_database_check_rejects_null_required_run_metadata(self) -> None:
        self.store.create_run(running_run(RUN_1))
        completed = "2026-10-02T08:31:00.000000Z"
        cases = (
            (None, "storage failure"),
            ("storage failure", None),
        )
        with closing(sqlite3.connect(self.db_path)) as connection:
            for failure_kind, sanitized_error in cases:
                with self.subTest(failure_kind=failure_kind, sanitized_error=sanitized_error):
                    with self.assertRaises(sqlite3.IntegrityError):
                        connection.execute(
                            "UPDATE runs SET completed_at=?,status='failed',failure_kind=?,sanitized_error=? WHERE run_id=? AND status='running'",
                            (completed, failure_kind, sanitized_error, RUN_1),
                        )
                    connection.rollback()
        self.assertEqual(self.store.get_run(RUN_1).status, RunStatus.RUNNING)

    def test_list_runs_is_site_isolated_limited_and_deterministically_ordered(self) -> None:
        self.store.create_run(running_run(RUN_1, started_at=NOW))
        self.store.create_run(running_run(RUN_2, started_at=NOW + timedelta(minutes=1)))
        other_id = "33333333-3333-4333-8333-333333333333"
        self.store.create_run(running_run(other_id, site_key="https://other.example:443"))
        self.assertEqual(
            [item.run_id for item in self.store.list_runs_for_site("https://example.com:443")],
            [RUN_2, RUN_1],
        )
        self.assertEqual(len(self.store.list_runs_for_site("https://example.com:443", limit=1)), 1)
        with self.assertRaises(ValueError):
            self.store.list_runs_for_site("https://example.com:443", limit=0)

    def test_artifacts_are_append_only_and_ordered(self) -> None:
        self.store.create_run(running_run(RUN_1))
        for artifact_id, created_at in (
            (ARTIFACT_2, NOW + timedelta(seconds=1)),
            (ARTIFACT_1, NOW),
        ):
            self.store.append_artifact(
                ArtifactRecord(
                    artifact_id=artifact_id,
                    run_id=RUN_1,
                    artifact_type=ArtifactType.SITE_AUDIT,
                    payload_version=1,
                    created_at=created_at,
                    payload=audit(),
                )
            )
        self.assertEqual(
            [item.artifact_id for item in self.store.list_artifacts(RUN_1)],
            [ARTIFACT_1, ARTIFACT_2],
        )
        with self.assertRaises(HistoryConflictError):
            self.store.append_artifact(self.store.get_artifact(ARTIFACT_1))

    def test_same_second_artifacts_order_chronologically(self) -> None:
        self.store.create_run(running_run(RUN_1))
        values = (
            (ARTIFACT_3, datetime(2026, 10, 2, 8, 30, 0, 900000, tzinfo=UTC)),
            (ARTIFACT_1, datetime(2026, 10, 2, 8, 30, 0, 0, tzinfo=UTC)),
            (ARTIFACT_2, datetime(2026, 10, 2, 8, 30, 0, 500000, tzinfo=UTC)),
        )
        for artifact_id, created_at in values:
            self.store.append_artifact(
                ArtifactRecord(
                    artifact_id=artifact_id,
                    run_id=RUN_1,
                    artifact_type=ArtifactType.SITE_AUDIT,
                    payload_version=1,
                    created_at=created_at,
                    payload=audit(),
                )
            )
        self.assertEqual(
            [item.artifact_id for item in self.store.list_artifacts(RUN_1)],
            [ARTIFACT_1, ARTIFACT_2, ARTIFACT_3],
        )

    def test_same_second_runs_order_descending_chronologically(self) -> None:
        self.store.create_run(
            running_run(RUN_1, started_at=datetime(2026, 10, 2, 8, 30, 0, 0, tzinfo=UTC))
        )
        self.store.create_run(
            running_run(RUN_2, started_at=datetime(2026, 10, 2, 8, 30, 0, 500000, tzinfo=UTC))
        )
        self.assertEqual(
            [item.run_id for item in self.store.list_runs_for_site("https://example.com:443")],
            [RUN_2, RUN_1],
        )

    def test_failed_artifact_insert_rolls_back(self) -> None:
        missing_run_artifact = ArtifactRecord(
            artifact_id=ARTIFACT_1,
            run_id=RUN_1,
            artifact_type=ArtifactType.SITE_AUDIT,
            payload_version=1,
            created_at=NOW,
            payload=audit(),
        )
        with self.assertRaises(HistoryConflictError):
            self.store.append_artifact(missing_run_artifact)
        self.assertIsNone(self.store.get_artifact(ARTIFACT_1))

    def _new_store(self, name: str) -> SQLiteHistoryStore:
        return SQLiteHistoryStore(Path(self.temp.name) / name)

    def _prepare_content_draft(self) -> None:
        self._prepare_content_draft_in(self.store)

    def _prepare_content_draft_in(self, store: SQLiteHistoryStore) -> None:
        store.create_run(running_run(RUN_1))
        store.append_artifact(
            ArtifactRecord(ARTIFACT_1, RUN_1, ArtifactType.CONTENT_DRAFT, 1, NOW, draft_report())
        )

    def _pending(self, attempt_id: str = ATTEMPT_1, fingerprint: str = "a" * 64) -> WordPressDraftAttempt:
        return WordPressDraftAttempt(
            attempt_id=attempt_id,
            run_id=RUN_1,
            content_draft_artifact_id=ARTIFACT_1,
            draft_item_id="D1",
            target_site_key="https://cms.example.com:443",
            fingerprint_version=1,
            request_fingerprint=fingerprint,
            attempted_at=NOW,
            completed_at=None,
            outcome=WordPressAttemptState.PENDING,
            remote_post_id=None,
            remote_link=None,
            failure_kind=None,
            sanitized_error=None,
        )

    def test_attempt_pending_reopens_and_compare_and_set_finish_is_terminal(self) -> None:
        self._prepare_content_draft()
        self.store.begin_wordpress_attempt(self._pending())
        reopened = SQLiteHistoryStore(self.db_path)
        self.assertEqual(reopened.list_wordpress_attempts(RUN_1)[0].outcome, WordPressAttemptState.PENDING)
        finished = reopened.finish_wordpress_attempt(
            ATTEMPT_1,
            outcome=WordPressAttemptState.SUCCESS,
            completed_at=NOW + timedelta(seconds=1),
            remote_post_id=41,
            remote_link="https://cms.example.com/?p=41",
        )
        self.assertEqual(finished.outcome, WordPressAttemptState.SUCCESS)
        with self.assertRaises(HistoryConflictError):
            reopened.finish_wordpress_attempt(
                ATTEMPT_1,
                outcome=WordPressAttemptState.UNKNOWN,
                completed_at=NOW + timedelta(seconds=2),
                failure_kind="timeout",
                sanitized_error="request outcome unknown",
            )

    def test_attempt_finish_cannot_commit_completion_before_attempt(self) -> None:
        self._prepare_content_draft()
        self.store.begin_wordpress_attempt(self._pending())
        with self.assertRaises(HistoryConflictError):
            self.store.finish_wordpress_attempt(
                ATTEMPT_1,
                outcome=WordPressAttemptState.UNKNOWN,
                completed_at=NOW - timedelta(seconds=1),
                failure_kind="timeout",
                sanitized_error="request outcome unknown",
            )
        self.assertEqual(
            self.store.list_wordpress_attempts(RUN_1)[0].outcome,
            WordPressAttemptState.PENDING,
        )

    def test_same_second_fractional_attempt_completion_succeeds(self) -> None:
        self._prepare_content_draft()
        pending = self._pending()
        object.__setattr__(pending, "attempted_at", datetime(2026, 10, 2, 8, 30, 0, 0, tzinfo=UTC))
        self.store.begin_wordpress_attempt(pending)
        finished = self.store.finish_wordpress_attempt(
            ATTEMPT_1,
            outcome=WordPressAttemptState.SUCCESS,
            completed_at=datetime(2026, 10, 2, 8, 30, 0, 500000, tzinfo=UTC),
            remote_post_id=41,
            remote_link="https://cms.example.com/?p=41",
        )
        self.assertEqual(finished.outcome, WordPressAttemptState.SUCCESS)
        reopened = SQLiteHistoryStore(self.db_path)
        self.assertEqual(
            reopened.list_wordpress_attempts(RUN_1)[0].completed_at,
            datetime(2026, 10, 2, 8, 30, 0, 500000, tzinfo=UTC),
        )

    def test_same_second_reverse_chronology_attempt_is_rejected_and_stays_pending(self) -> None:
        self._prepare_content_draft()
        pending = self._pending()
        object.__setattr__(pending, "attempted_at", datetime(2026, 10, 2, 8, 30, 0, 500000, tzinfo=UTC))
        self.store.begin_wordpress_attempt(pending)
        with self.assertRaises(HistoryConflictError):
            self.store.finish_wordpress_attempt(
                ATTEMPT_1,
                outcome=WordPressAttemptState.SUCCESS,
                completed_at=datetime(2026, 10, 2, 8, 30, 0, 0, tzinfo=UTC),
                remote_post_id=41,
                remote_link="https://cms.example.com/?p=41",
            )
        reopened = SQLiteHistoryStore(self.db_path)
        self.assertEqual(
            reopened.list_wordpress_attempts(RUN_1)[0].outcome,
            WordPressAttemptState.PENDING,
        )

    def test_invalid_terminal_attempt_metadata_rolls_back_without_finishing(self) -> None:
        for failure_kind in ("", "   "):
            with self.subTest(failure_kind=failure_kind):
                store = self._new_store(f"attempt-blank-{len(failure_kind)}.sqlite3")
                self._prepare_content_draft_in(store)
                store.begin_wordpress_attempt(self._pending())
                with self.assertRaises(ValueError):
                    store.finish_wordpress_attempt(
                        ATTEMPT_1,
                        outcome=WordPressAttemptState.UNKNOWN,
                        completed_at=NOW + timedelta(seconds=1),
                        failure_kind=failure_kind,
                        sanitized_error="request outcome unknown",
                    )
                self.assertEqual(
                    store.list_wordpress_attempts(RUN_1)[0].outcome,
                    WordPressAttemptState.PENDING,
                )

    def test_blank_terminal_attempt_fields_are_rejected_at_database_layer(self) -> None:
        self._prepare_content_draft()
        self.store.begin_wordpress_attempt(self._pending())
        completed = (NOW + timedelta(minutes=1)).astimezone(UTC).isoformat().replace("+00:00", "Z")
        with closing(sqlite3.connect(self.db_path)) as connection:
            for column in ("failure_kind", "sanitized_error"):
                for blank in ("", "   "):
                    with self.subTest(column=column, blank=blank):
                        if column == "failure_kind":
                            parameters = (completed, blank, "request outcome unknown", ATTEMPT_1)
                        else:
                            parameters = (completed, "timeout", blank, ATTEMPT_1)
                        with self.assertRaises(sqlite3.IntegrityError):
                            connection.execute(
                                "UPDATE wordpress_draft_attempts SET completed_at=?,outcome='unknown',failure_kind=?,sanitized_error=? WHERE attempt_id=? AND outcome='pending'",
                                parameters,
                            )
                        connection.rollback()
        self.assertEqual(
            self.store.list_wordpress_attempts(RUN_1)[0].outcome,
            WordPressAttemptState.PENDING,
        )

    def test_database_check_rejects_null_required_attempt_metadata(self) -> None:
        self._prepare_content_draft()
        self.store.begin_wordpress_attempt(self._pending())
        completed = "2026-10-02T08:31:00.000000Z"
        cases = (
            ("success", 41, None, None, None),
            ("success", None, "https://cms.example.com/?p=41", None, None),
            ("unknown", None, None, None, "request outcome unknown"),
            ("unknown", None, None, "timeout", None),
        )
        with closing(sqlite3.connect(self.db_path)) as connection:
            for outcome, remote_post_id, remote_link, failure_kind, sanitized_error in cases:
                with self.subTest(outcome=outcome):
                    with self.assertRaises(sqlite3.IntegrityError):
                        connection.execute(
                            "UPDATE wordpress_draft_attempts SET completed_at=?,outcome=?,remote_post_id=?,remote_link=?,failure_kind=?,sanitized_error=? WHERE attempt_id=? AND outcome='pending'",
                            (
                                completed,
                                outcome,
                                remote_post_id,
                                remote_link,
                                failure_kind,
                                sanitized_error,
                                ATTEMPT_1,
                            ),
                        )
                    connection.rollback()
        self.assertEqual(
            self.store.list_wordpress_attempts(RUN_1)[0].outcome,
            WordPressAttemptState.PENDING,
        )

    def test_attempt_success_rejects_invalid_remote_link(self) -> None:
        self._prepare_content_draft()
        self.store.begin_wordpress_attempt(self._pending())
        with self.assertRaises(ValueError):
            self.store.finish_wordpress_attempt(
                ATTEMPT_1,
                outcome=WordPressAttemptState.SUCCESS,
                completed_at=NOW + timedelta(seconds=1),
                remote_post_id=41,
                remote_link="https://example.com:99999/x",
            )
        self.assertEqual(
            self.store.list_wordpress_attempts(RUN_1)[0].outcome,
            WordPressAttemptState.PENDING,
        )

    def test_failed_definitely_can_retry_but_blocking_states_cannot(self) -> None:
        self._prepare_content_draft()
        self.store.begin_wordpress_attempt(self._pending())
        self.store.finish_wordpress_attempt(
            ATTEMPT_1,
            outcome=WordPressAttemptState.FAILED_DEFINITELY,
            completed_at=NOW + timedelta(seconds=1),
            failure_kind="auth_failed",
            sanitized_error="authentication rejected",
        )
        self.store.begin_wordpress_attempt(self._pending(ATTEMPT_2))
        with self.assertRaises(HistoryConflictError):
            self.store.begin_wordpress_attempt(
                self._pending("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee")
            )

    def test_separate_store_connection_cannot_insert_second_blocking_fingerprint(self) -> None:
        self._prepare_content_draft()
        self.store.begin_wordpress_attempt(self._pending())
        competing_store = SQLiteHistoryStore(self.db_path)
        with self.assertRaises(HistoryConflictError) as raised:
            competing_store.begin_wordpress_attempt(self._pending(ATTEMPT_2))
        self.assertNotIn("UNIQUE", str(raised.exception).upper())
        self.assertNotIn("SQLITE", str(raised.exception).upper())

    def test_success_and_unknown_each_keep_fingerprint_blocked(self) -> None:
        for outcome in (WordPressAttemptState.SUCCESS, WordPressAttemptState.UNKNOWN):
            with self.subTest(outcome=outcome):
                path = Path(self.temp.name) / f"{outcome.value}.sqlite3"
                store = SQLiteHistoryStore(path)
                store.create_run(running_run(RUN_1))
                store.append_artifact(
                    ArtifactRecord(ARTIFACT_1, RUN_1, ArtifactType.CONTENT_DRAFT, 1, NOW, draft_report())
                )
                store.begin_wordpress_attempt(self._pending())
                kwargs = (
                    {"remote_post_id": 41, "remote_link": "https://cms.example.com/?p=41"}
                    if outcome is WordPressAttemptState.SUCCESS
                    else {"failure_kind": "timeout", "sanitized_error": "request outcome unknown"}
                )
                store.finish_wordpress_attempt(
                    ATTEMPT_1,
                    outcome=outcome,
                    completed_at=NOW + timedelta(seconds=1),
                    **kwargs,
                )
                with self.assertRaises(HistoryConflictError):
                    store.begin_wordpress_attempt(self._pending(ATTEMPT_2))

    def test_attempt_rejects_wrong_run_non_draft_artifact_and_nonexistent_draft_id(self) -> None:
        self._prepare_content_draft()
        other_run = "99999999-9999-4999-8999-999999999999"
        self.store.create_run(running_run(other_run))
        wrong_run = self._pending()
        object.__setattr__(wrong_run, "run_id", other_run)
        with self.assertRaises(HistoryConflictError):
            self.store.begin_wordpress_attempt(wrong_run)

        audit_id = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
        self.store.append_artifact(ArtifactRecord(audit_id, RUN_1, ArtifactType.SITE_AUDIT, 1, NOW, audit()))
        non_draft = self._pending(ATTEMPT_2, "b" * 64)
        object.__setattr__(non_draft, "content_draft_artifact_id", audit_id)
        with self.assertRaises(HistoryConflictError):
            self.store.begin_wordpress_attempt(non_draft)

        missing_item = self._pending("ffffffff-ffff-4fff-8fff-ffffffffffff", "c" * 64)
        object.__setattr__(missing_item, "draft_item_id", "D2")
        with self.assertRaises(HistoryConflictError):
            self.store.begin_wordpress_attempt(missing_item)

    def test_attempt_queries_are_ordered_and_filter_by_draft_and_fingerprint(self) -> None:
        self._prepare_content_draft()
        first = self._pending(ATTEMPT_1, "a" * 64)
        second = self._pending(ATTEMPT_2, "b" * 64)
        object.__setattr__(second, "attempted_at", NOW + timedelta(seconds=1))
        self.store.begin_wordpress_attempt(second)
        self.store.begin_wordpress_attempt(first)
        self.assertEqual([item.attempt_id for item in self.store.list_wordpress_attempts(RUN_1)], [ATTEMPT_1, ATTEMPT_2])
        self.assertEqual(len(self.store.list_wordpress_attempts_for_draft(ARTIFACT_1, "D1")), 2)
        self.assertEqual(self.store.find_wordpress_attempts_by_fingerprint("https://cms.example.com:443", "b" * 64)[0].attempt_id, ATTEMPT_2)


class SQLiteVerificationHistoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "history.sqlite3"
        persist_review_fixture(self.db_path)
        persist_success_attempt(self.db_path)
        persist_unknown_attempt(self.db_path)
        self.store = SQLiteHistoryStore(self.db_path)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _record(self, verification_id: str, **overrides: object) -> WordPressVerification:
        values: dict[str, object] = {
            "verification_id": verification_id,
            "attempt_id": ATTEMPT_SUCCESS,
            "run_id": RUN_1,
            "content_draft_artifact_id": CONTENT_DRAFT_ARTIFACT_ID,
            "draft_item_id": "D1",
            "target_site_key": "https://example.com:443",
            "lookup_kind": WordPressVerificationLookupKind.REMOTE_ID,
            "observed_remote_post_id": None,
            "observed_status": None,
            "outcome": WordPressVerificationOutcome.UNKNOWN,
            "failure_kind": WordPressVerificationFailureKind.TIMEOUT,
            "sanitized_error": "WordPress draft read timed out.",
            "verified_at": NOW,
        }
        values.update(overrides)
        return WordPressVerification(**values)  # type: ignore[arg-type]

    def test_append_and_list_are_ordered_and_do_not_touch_the_attempt(self) -> None:
        before = self.store.get_wordpress_attempt(ATTEMPT_SUCCESS)
        first = "10000000-0000-4000-8000-000000000001"
        second = "10000000-0000-4000-8000-000000000002"
        self.store.append_wordpress_verification(self._record(first))
        later = self._record(second)
        object.__setattr__(later, "verified_at", NOW + timedelta(seconds=5))
        self.store.append_wordpress_verification(later)

        records = self.store.list_wordpress_verifications(ATTEMPT_SUCCESS)

        self.assertEqual([item.verification_id for item in records], [first, second])
        self.assertEqual(self.store.get_wordpress_attempt(ATTEMPT_SUCCESS), before)
        self.assertEqual(records[0].outcome, WordPressVerificationOutcome.UNKNOWN)
        self.assertEqual(records[0].lookup_kind, WordPressVerificationLookupKind.REMOTE_ID)

    def test_unknown_attempt_lookup_is_a_read_method(self) -> None:
        self.assertEqual(self.store.get_wordpress_attempt(ATTEMPT_UNKNOWN).attempt_id, ATTEMPT_UNKNOWN)
        self.assertIsNone(self.store.get_wordpress_attempt(ARTIFACT_3))

    def test_reader_reopen_recovers_attempt_and_verification_history(self) -> None:
        from foreign_trade_geo_agent.storage.sqlite import SQLiteHistoryReader

        verification_id = "10000000-0000-4000-8000-000000000009"
        self.store.append_wordpress_verification(self._record(verification_id))

        reader = SQLiteHistoryReader(self.db_path)
        attempt = reader.get_wordpress_attempt(ATTEMPT_SUCCESS)
        records = reader.list_wordpress_verifications(ATTEMPT_SUCCESS)

        self.assertEqual(attempt.remote_post_id, REMOTE_POST_ID)
        self.assertEqual([item.verification_id for item in records], [verification_id])
        self.assertEqual(records[0].outcome, WordPressVerificationOutcome.UNKNOWN)

    def test_database_check_rejects_confused_unknown_and_unresolved(self) -> None:
        connection = sqlite3.connect(self.db_path)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO wordpress_draft_verifications VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        "20000000-0000-4000-8000-000000000001",
                        ATTEMPT_SUCCESS,
                        RUN_1,
                        CONTENT_DRAFT_ARTIFACT_ID,
                        "D1",
                        "https://example.com:443",
                        "none",
                        None,
                        None,
                        "unknown",
                        "timeout",
                        "WordPress draft read timed out.",
                        "2026-10-03T09:15:00.000000Z",
                    ),
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO wordpress_draft_verifications VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        "20000000-0000-4000-8000-000000000002",
                        ATTEMPT_SUCCESS,
                        RUN_1,
                        CONTENT_DRAFT_ARTIFACT_ID,
                        "D1",
                        "https://example.com:443",
                        "remote_id",
                        41,
                        "draft",
                        "unresolved",
                        "no_remote_identifier",
                        "No remote identifier is available.",
                        "2026-10-03T09:15:00.000000Z",
                    ),
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO wordpress_draft_verifications VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        "20000000-0000-4000-8000-000000000003",
                        ATTEMPT_SUCCESS,
                        RUN_1,
                        CONTENT_DRAFT_ARTIFACT_ID,
                        "D1",
                        "https://example.com:443",
                        "none",
                        None,
                        None,
                        "unresolved",
                        None,
                        None,
                        "2026-10-03T09:15:00.000000Z",
                    ),
                )
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
