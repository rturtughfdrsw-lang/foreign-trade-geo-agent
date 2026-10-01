"""Synchronous SQLite v1 implementation of historical persistence."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
import sqlite3
from typing import Iterator

from foreign_trade_geo_agent.core.history import (
    ArtifactRecord,
    ArtifactType,
    HistoryConflictError,
    HistoryStoreError,
    MalformedHistoryDataError,
    RunStatus,
    UnsupportedHistoryVersionError,
    WorkflowRun,
    WordPressAttemptState,
    WordPressDraftAttempt,
    validate_aware_datetime,
    validate_optional_sanitized_text,
    validate_uuid,
    valid_public_remote_link,
)
from foreign_trade_geo_agent.storage.serialization import decode_artifact, encode_artifact


_SCHEMA_VERSION = 1
_SCHEMA = """
BEGIN IMMEDIATE;
CREATE TABLE runs (
    run_id TEXT PRIMARY KEY NOT NULL,
    site_key TEXT NOT NULL,
    workflow_name TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL CHECK (status IN ('running','succeeded','failed','needs_reconciliation')),
    failure_kind TEXT,
    sanitized_error TEXT,
    CHECK (completed_at IS NULL OR completed_at >= started_at),
    CHECK (
        (status = 'running' AND completed_at IS NULL AND failure_kind IS NULL AND sanitized_error IS NULL)
        OR (status = 'succeeded' AND completed_at IS NOT NULL AND failure_kind IS NULL AND sanitized_error IS NULL)
        OR (status IN ('failed','needs_reconciliation') AND completed_at IS NOT NULL AND failure_kind IS NOT NULL AND sanitized_error IS NOT NULL AND length(TRIM(failure_kind)) > 0 AND length(TRIM(sanitized_error)) > 0)
    )
);
CREATE INDEX ix_runs_site_started ON runs(site_key, started_at DESC, run_id DESC);

CREATE TABLE artifacts (
    artifact_id TEXT PRIMARY KEY NOT NULL,
    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE RESTRICT,
    artifact_type TEXT NOT NULL CHECK (artifact_type IN ('site_content','site_audit','visibility','site_optimization','industry_research','content_opportunity','change_plan','content_draft')),
    payload_version INTEGER NOT NULL CHECK (payload_version > 0),
    created_at TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE INDEX ix_artifacts_run_created ON artifacts(run_id, created_at, artifact_id);
CREATE INDEX ix_artifacts_run_type_created ON artifacts(run_id, artifact_type, created_at, artifact_id);

CREATE TABLE wordpress_draft_attempts (
    attempt_id TEXT PRIMARY KEY NOT NULL,
    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE RESTRICT,
    content_draft_artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id) ON DELETE RESTRICT,
    draft_item_id TEXT NOT NULL,
    target_site_key TEXT NOT NULL,
    fingerprint_version INTEGER NOT NULL CHECK (fingerprint_version = 1),
    request_fingerprint TEXT NOT NULL CHECK (
        length(request_fingerprint) = 64
        AND request_fingerprint NOT GLOB '*[^0-9a-f]*'
    ),
    attempted_at TEXT NOT NULL,
    completed_at TEXT,
    outcome TEXT NOT NULL CHECK (outcome IN ('pending','success','failed_definitely','unknown')),
    remote_post_id INTEGER,
    remote_link TEXT,
    failure_kind TEXT,
    sanitized_error TEXT,
    CHECK (completed_at IS NULL OR completed_at >= attempted_at),
    CHECK (
        (outcome = 'pending' AND completed_at IS NULL AND remote_post_id IS NULL AND remote_link IS NULL AND failure_kind IS NULL AND sanitized_error IS NULL)
        OR (outcome = 'success' AND completed_at IS NOT NULL AND remote_post_id IS NOT NULL AND remote_post_id > 0 AND remote_link IS NOT NULL AND length(TRIM(remote_link)) > 0 AND failure_kind IS NULL AND sanitized_error IS NULL)
        OR (outcome IN ('failed_definitely','unknown') AND completed_at IS NOT NULL AND remote_post_id IS NULL AND remote_link IS NULL AND failure_kind IS NOT NULL AND sanitized_error IS NOT NULL AND length(TRIM(failure_kind)) > 0 AND length(TRIM(sanitized_error)) > 0)
    )
);
CREATE INDEX ix_wp_attempts_run ON wordpress_draft_attempts(run_id, attempted_at, attempt_id);
CREATE INDEX ix_wp_attempts_draft ON wordpress_draft_attempts(content_draft_artifact_id, draft_item_id, attempted_at, attempt_id);
CREATE INDEX ix_wp_attempts_fingerprint ON wordpress_draft_attempts(target_site_key, request_fingerprint, attempted_at, attempt_id);
CREATE UNIQUE INDEX uq_wp_attempts_blocking_fingerprint
ON wordpress_draft_attempts(target_site_key, request_fingerprint)
WHERE outcome IN ('pending','success','unknown');
PRAGMA user_version = 1;
COMMIT;
"""


def _timestamp(value: datetime) -> str:
    validate_aware_datetime(value, "timestamp")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse_timestamp(value: object) -> datetime:
    if type(value) is not str or not value.endswith("Z"):
        raise MalformedHistoryDataError("Stored timestamp is malformed.")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise MalformedHistoryDataError("Stored timestamp is malformed.") from exc


def _validated_limit(limit: int) -> int:
    if type(limit) is not int or not 1 <= limit <= 1_000:
        raise ValueError("limit must be an integer from 1 to 1000.")
    return limit


class SQLiteHistoryStore:
    """File-backed SQLite history store; each operation owns its connection."""

    def __init__(self, path: str | Path) -> None:
        if str(path) == ":memory:":
            raise ValueError("History database must be file-backed.")
        self._path = Path(path)
        if not self._path.parent.is_dir():
            raise FileNotFoundError("History database parent directory does not exist.")
        self._initialize()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        try:
            connection = sqlite3.connect(self._path, timeout=5.0)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
                connection.close()
                raise HistoryStoreError("SQLite foreign-key enforcement is unavailable.")
            connection.execute("PRAGMA busy_timeout = 5000")
            try:
                yield connection
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
            finally:
                connection.close()
        except sqlite3.DatabaseError as exc:
            raise HistoryStoreError("History storage operation failed.") from exc

    def _initialize(self) -> None:
        with self._connection() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version == 0:
                connection.executescript(_SCHEMA)
            elif version != _SCHEMA_VERSION:
                raise UnsupportedHistoryVersionError("History database version is unsupported.")

    def foreign_keys_enabled(self) -> bool:
        with self._connection() as connection:
            return connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1

    def create_run(self, run: WorkflowRun) -> None:
        if not isinstance(run, WorkflowRun) or run.status is not RunStatus.RUNNING:
            raise ValueError("create_run requires one RUNNING WorkflowRun.")
        try:
            with self._connection() as connection:
                connection.execute(
                    "INSERT INTO runs(run_id,site_key,workflow_name,started_at,completed_at,status,failure_kind,sanitized_error) VALUES(?,?,?,?,?,?,?,?)",
                    (run.run_id, run.site_key, run.workflow_name, _timestamp(run.started_at), None, run.status.value, None, None),
                )
        except HistoryStoreError as exc:
            if isinstance(exc.__cause__, sqlite3.IntegrityError):
                raise HistoryConflictError("Run history conflicts with an existing record.") from exc
            raise

    def finish_run(
        self,
        run_id: str,
        *,
        status: RunStatus,
        completed_at: datetime,
        failure_kind: str | None = None,
        sanitized_error: str | None = None,
    ) -> WorkflowRun:
        validate_uuid(run_id, "run_id")
        if status not in {RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.NEEDS_RECONCILIATION}:
            raise ValueError("finish_run requires a terminal status.")
        validate_optional_sanitized_text(failure_kind, "failure_kind")
        validate_optional_sanitized_text(sanitized_error, "sanitized_error")
        if status is RunStatus.SUCCEEDED:
            if failure_kind is not None or sanitized_error is not None:
                raise ValueError("A successful run cannot have failure fields.")
        elif failure_kind is None or sanitized_error is None:
            raise ValueError("A failed or uncertain run requires sanitized failure fields.")
        completed_text = _timestamp(completed_at)
        with self._connection() as connection:
            try:
                cursor = connection.execute(
                    "UPDATE runs SET completed_at=?,status=?,failure_kind=?,sanitized_error=? WHERE run_id=? AND status='running' AND started_at<=?",
                    (completed_text, status.value, failure_kind, sanitized_error, run_id, completed_text),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("Terminal run fields are inconsistent.") from exc
            if cursor.rowcount != 1:
                raise HistoryConflictError("Run is missing or is no longer running.")
            row = connection.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if row is None:
                raise HistoryConflictError("Run is missing after update.")
            return self._run_from_row(row)

    def append_artifact(self, artifact: ArtifactRecord) -> None:
        if not isinstance(artifact, ArtifactRecord):
            raise TypeError("artifact must be an ArtifactRecord.")
        payload_json = encode_artifact(artifact.artifact_type, artifact.payload, payload_version=artifact.payload_version)
        try:
            with self._connection() as connection:
                connection.execute(
                    "INSERT INTO artifacts(artifact_id,run_id,artifact_type,payload_version,created_at,payload_json) VALUES(?,?,?,?,?,?)",
                    (artifact.artifact_id, artifact.run_id, artifact.artifact_type.value, artifact.payload_version, _timestamp(artifact.created_at), payload_json),
                )
        except HistoryStoreError as exc:
            if isinstance(exc.__cause__, sqlite3.IntegrityError):
                raise HistoryConflictError("Artifact history conflicts with an existing record.") from exc
            raise

    def get_run(self, run_id: str) -> WorkflowRun | None:
        validate_uuid(run_id, "run_id")
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return None if row is None else self._run_from_row(row)

    def list_runs_for_site(self, site_key: str, *, limit: int = 100) -> tuple[WorkflowRun, ...]:
        limit = _validated_limit(limit)
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM runs WHERE site_key=? ORDER BY started_at DESC, run_id DESC LIMIT ?",
                (site_key, limit),
            ).fetchall()
        return tuple(self._run_from_row(row) for row in rows)

    def get_artifact(self, artifact_id: str) -> ArtifactRecord | None:
        validate_uuid(artifact_id, "artifact_id")
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM artifacts WHERE artifact_id=?", (artifact_id,)).fetchone()
        return None if row is None else self._artifact_from_row(row)

    def list_artifacts(
        self,
        run_id: str,
        *,
        artifact_type: ArtifactType | None = None,
        limit: int = 100,
    ) -> tuple[ArtifactRecord, ...]:
        validate_uuid(run_id, "run_id")
        limit = _validated_limit(limit)
        if artifact_type is None:
            sql = "SELECT * FROM artifacts WHERE run_id=? ORDER BY created_at ASC, artifact_id ASC LIMIT ?"
            parameters: tuple[object, ...] = (run_id, limit)
        elif isinstance(artifact_type, ArtifactType):
            sql = "SELECT * FROM artifacts WHERE run_id=? AND artifact_type=? ORDER BY created_at ASC, artifact_id ASC LIMIT ?"
            parameters = (run_id, artifact_type.value, limit)
        else:
            raise ValueError("artifact_type is invalid.")
        with self._connection() as connection:
            rows = connection.execute(sql, parameters).fetchall()
        return tuple(self._artifact_from_row(row) for row in rows)

    def begin_wordpress_attempt(self, attempt: WordPressDraftAttempt) -> None:
        if not isinstance(attempt, WordPressDraftAttempt) or attempt.outcome is not WordPressAttemptState.PENDING:
            raise ValueError("begin_wordpress_attempt requires one PENDING attempt.")
        try:
            with self._connection() as connection:
                row = connection.execute(
                    "SELECT * FROM artifacts WHERE artifact_id=?",
                    (attempt.content_draft_artifact_id,),
                ).fetchone()
                if row is None:
                    raise HistoryConflictError("Content-draft artifact does not exist.")
                artifact = self._artifact_from_row(row)
                if artifact.run_id != attempt.run_id or artifact.artifact_type is not ArtifactType.CONTENT_DRAFT:
                    raise HistoryConflictError("Attempt does not reference this run's content-draft artifact.")
                from foreign_trade_geo_agent.core.content_draft import ContentDraftReport

                if not isinstance(artifact.payload, ContentDraftReport) or attempt.draft_item_id not in {
                    item.draft_id for item in artifact.payload.drafts
                }:
                    raise HistoryConflictError("Draft item does not exist in the referenced artifact.")
                connection.execute(
                    "INSERT INTO wordpress_draft_attempts(attempt_id,run_id,content_draft_artifact_id,draft_item_id,target_site_key,fingerprint_version,request_fingerprint,attempted_at,completed_at,outcome,remote_post_id,remote_link,failure_kind,sanitized_error) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        attempt.attempt_id,
                        attempt.run_id,
                        attempt.content_draft_artifact_id,
                        attempt.draft_item_id,
                        attempt.target_site_key,
                        attempt.fingerprint_version,
                        attempt.request_fingerprint,
                        _timestamp(attempt.attempted_at),
                        None,
                        attempt.outcome.value,
                        None,
                        None,
                        None,
                        None,
                    ),
                )
        except HistoryStoreError as exc:
            if isinstance(exc, HistoryConflictError):
                raise
            if isinstance(exc.__cause__, sqlite3.IntegrityError):
                raise HistoryConflictError("WordPress attempt conflicts with existing history.") from exc
            raise

    def finish_wordpress_attempt(
        self,
        attempt_id: str,
        *,
        outcome: WordPressAttemptState,
        completed_at: datetime,
        remote_post_id: int | None = None,
        remote_link: str | None = None,
        failure_kind: str | None = None,
        sanitized_error: str | None = None,
    ) -> WordPressDraftAttempt:
        validate_uuid(attempt_id, "attempt_id")
        if outcome not in {
            WordPressAttemptState.SUCCESS,
            WordPressAttemptState.FAILED_DEFINITELY,
            WordPressAttemptState.UNKNOWN,
        }:
            raise ValueError("finish_wordpress_attempt requires a terminal outcome.")
        validate_optional_sanitized_text(failure_kind, "failure_kind")
        validate_optional_sanitized_text(sanitized_error, "sanitized_error")
        if outcome is WordPressAttemptState.SUCCESS:
            if (
                type(remote_post_id) is not int
                or remote_post_id <= 0
                or not valid_public_remote_link(remote_link)
                or failure_kind is not None
                or sanitized_error is not None
            ):
                raise ValueError("Successful WordPress attempt fields are inconsistent.")
        elif (
            remote_post_id is not None
            or remote_link is not None
            or failure_kind is None
            or sanitized_error is None
        ):
            raise ValueError("Failed or uncertain WordPress attempt fields are inconsistent.")
        completed_text = _timestamp(completed_at)
        with self._connection() as connection:
            try:
                cursor = connection.execute(
                    "UPDATE wordpress_draft_attempts SET completed_at=?,outcome=?,remote_post_id=?,remote_link=?,failure_kind=?,sanitized_error=? WHERE attempt_id=? AND outcome='pending' AND attempted_at<=?",
                    (completed_text, outcome.value, remote_post_id, remote_link, failure_kind, sanitized_error, attempt_id, completed_text),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("Terminal WordPress attempt fields are inconsistent.") from exc
            if cursor.rowcount != 1:
                raise HistoryConflictError("WordPress attempt is missing or no longer pending.")
            row = connection.execute(
                "SELECT * FROM wordpress_draft_attempts WHERE attempt_id=?",
                (attempt_id,),
            ).fetchone()
            if row is None:
                raise HistoryConflictError("WordPress attempt is missing after update.")
            return self._attempt_from_row(row)

    def list_wordpress_attempts(self, run_id: str, *, limit: int = 100) -> tuple[WordPressDraftAttempt, ...]:
        validate_uuid(run_id, "run_id")
        limit = _validated_limit(limit)
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM wordpress_draft_attempts WHERE run_id=? ORDER BY attempted_at ASC, attempt_id ASC LIMIT ?",
                (run_id, limit),
            ).fetchall()
        return tuple(self._attempt_from_row(row) for row in rows)

    def list_wordpress_attempts_for_draft(
        self,
        content_draft_artifact_id: str,
        draft_item_id: str,
        *,
        limit: int = 100,
    ) -> tuple[WordPressDraftAttempt, ...]:
        validate_uuid(content_draft_artifact_id, "content_draft_artifact_id")
        limit = _validated_limit(limit)
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM wordpress_draft_attempts WHERE content_draft_artifact_id=? AND draft_item_id=? ORDER BY attempted_at ASC, attempt_id ASC LIMIT ?",
                (content_draft_artifact_id, draft_item_id, limit),
            ).fetchall()
        return tuple(self._attempt_from_row(row) for row in rows)

    def find_wordpress_attempts_by_fingerprint(
        self,
        target_site_key: str,
        request_fingerprint: str,
        *,
        limit: int = 100,
    ) -> tuple[WordPressDraftAttempt, ...]:
        limit = _validated_limit(limit)
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM wordpress_draft_attempts WHERE target_site_key=? AND request_fingerprint=? ORDER BY attempted_at ASC, attempt_id ASC LIMIT ?",
                (target_site_key, request_fingerprint, limit),
            ).fetchall()
        return tuple(self._attempt_from_row(row) for row in rows)

    @staticmethod
    def _run_from_row(row: sqlite3.Row) -> WorkflowRun:
        try:
            return WorkflowRun(
                run_id=row["run_id"],
                site_key=row["site_key"],
                workflow_name=row["workflow_name"],
                started_at=_parse_timestamp(row["started_at"]),
                completed_at=None if row["completed_at"] is None else _parse_timestamp(row["completed_at"]),
                status=RunStatus(row["status"]),
                failure_kind=row["failure_kind"],
                sanitized_error=row["sanitized_error"],
            )
        except (ValueError, TypeError, KeyError) as exc:
            raise MalformedHistoryDataError("Stored run is malformed.") from exc

    @staticmethod
    def _artifact_from_row(row: sqlite3.Row) -> ArtifactRecord:
        try:
            artifact_type = ArtifactType(row["artifact_type"])
            version = row["payload_version"]
            return ArtifactRecord(
                artifact_id=row["artifact_id"],
                run_id=row["run_id"],
                artifact_type=artifact_type,
                payload_version=version,
                created_at=_parse_timestamp(row["created_at"]),
                payload=decode_artifact(artifact_type, version, row["payload_json"]),
            )
        except (ValueError, TypeError, KeyError) as exc:
            raise MalformedHistoryDataError("Stored artifact is malformed.") from exc

    @staticmethod
    def _attempt_from_row(row: sqlite3.Row) -> WordPressDraftAttempt:
        try:
            return WordPressDraftAttempt(
                attempt_id=row["attempt_id"],
                run_id=row["run_id"],
                content_draft_artifact_id=row["content_draft_artifact_id"],
                draft_item_id=row["draft_item_id"],
                target_site_key=row["target_site_key"],
                fingerprint_version=row["fingerprint_version"],
                request_fingerprint=row["request_fingerprint"],
                attempted_at=_parse_timestamp(row["attempted_at"]),
                completed_at=None if row["completed_at"] is None else _parse_timestamp(row["completed_at"]),
                outcome=WordPressAttemptState(row["outcome"]),
                remote_post_id=row["remote_post_id"],
                remote_link=row["remote_link"],
                failure_kind=row["failure_kind"],
                sanitized_error=row["sanitized_error"],
            )
        except (ValueError, TypeError, KeyError) as exc:
            raise MalformedHistoryDataError("Stored WordPress attempt is malformed.") from exc
