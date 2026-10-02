"""Shared fixtures for the BLOCKER-3 WordPress verification tests."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import hashlib
from pathlib import Path
import sqlite3

from foreign_trade_geo_agent.core.history import (
    ArtifactType,
    RunStatus,
    WordPressAttemptState,
    WordPressDraftAttempt,
)
from foreign_trade_geo_agent.core.research import (
    ResearchReport,
    ResearchSource,
    ResearchStatus,
)
from foreign_trade_geo_agent.core.audit import (
    AuditEvidence,
    AuditEvidenceCategory,
    AuditEvidenceOutcome,
    AuditStatus,
    SiteAuditResult,
)
from foreign_trade_geo_agent.storage.serialization import encode_artifact
from foreign_trade_geo_agent.storage.sqlite import SQLiteHistoryStore
from tests.review_fixtures import (
    CHANGE_PLAN_ARTIFACT_ID,
    CONTENT_DRAFT_ARTIFACT_ID,
    CONTENT_OPPORTUNITY_ARTIFACT_ID,
    INDUSTRY_RESEARCH_ARTIFACT_ID,
    NOW,
    RUN_ID,
    SITE_CONTENT_ARTIFACT_ID,
    SITE_AUDIT_ARTIFACT_ID,
    WORKFLOW_NAME,
    build_review_domain,
)


ATTEMPT_SUCCESS = "aaaa1111-1111-4111-8111-111111111111"
ATTEMPT_UNKNOWN = "bbbb2222-2222-4222-8222-222222222222"
ATTEMPT_PENDING = "cccc3333-3333-4333-8333-333333333333"
ATTEMPT_FAILED = "dddd4444-4444-4444-8444-444444444444"
TARGET_SITE_KEY = "https://example.com:443"
REMOTE_POST_ID = 41
REMOTE_LINK = "https://example.com/?p=41"


V1_SCHEMA = """
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
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def fingerprint(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _begin_attempt(
    store: SQLiteHistoryStore,
    *,
    attempt_id: str,
    seed: str,
    target_site_key: str = TARGET_SITE_KEY,
) -> None:
    store.begin_wordpress_attempt(
        WordPressDraftAttempt(
            attempt_id=attempt_id,
            run_id=RUN_ID,
            content_draft_artifact_id=CONTENT_DRAFT_ARTIFACT_ID,
            draft_item_id="D1",
            target_site_key=target_site_key,
            fingerprint_version=1,
            request_fingerprint=fingerprint(seed),
            attempted_at=NOW,
            completed_at=None,
            outcome=WordPressAttemptState.PENDING,
            remote_post_id=None,
            remote_link=None,
            failure_kind=None,
            sanitized_error=None,
        )
    )


def persist_attempt(
    db_path: str | Path,
    *,
    outcome: WordPressAttemptState,
    attempt_id: str,
    seed: str,
    remote_post_id: int | None = None,
    remote_link: str | None = None,
    failure_kind: str | None = None,
    sanitized_error: str | None = None,
    target_site_key: str = TARGET_SITE_KEY,
) -> WordPressDraftAttempt:
    """Persist one terminal (or pending) WordPress attempt into a real store."""

    store = SQLiteHistoryStore(Path(db_path))
    _begin_attempt(
        store,
        attempt_id=attempt_id,
        seed=seed,
        target_site_key=target_site_key,
    )
    if outcome is WordPressAttemptState.PENDING:
        attempt = store.list_wordpress_attempts(RUN_ID)[-1]
        return attempt
    return store.finish_wordpress_attempt(
        attempt_id,
        outcome=outcome,
        completed_at=NOW,
        remote_post_id=remote_post_id,
        remote_link=remote_link,
        failure_kind=failure_kind,
        sanitized_error=sanitized_error,
    )


def persist_success_attempt(
    db_path: str | Path,
    *,
    attempt_id: str = ATTEMPT_SUCCESS,
    remote_post_id: int = REMOTE_POST_ID,
    remote_link: str = REMOTE_LINK,
    target_site_key: str = TARGET_SITE_KEY,
) -> WordPressDraftAttempt:
    return persist_attempt(
        db_path,
        outcome=WordPressAttemptState.SUCCESS,
        attempt_id=attempt_id,
        seed=f"success:{attempt_id}",
        remote_post_id=remote_post_id,
        remote_link=remote_link,
        target_site_key=target_site_key,
    )


def persist_unknown_attempt(
    db_path: str | Path,
    *,
    attempt_id: str = ATTEMPT_UNKNOWN,
) -> WordPressDraftAttempt:
    return persist_attempt(
        db_path,
        outcome=WordPressAttemptState.UNKNOWN,
        attempt_id=attempt_id,
        seed=f"unknown:{attempt_id}",
        failure_kind="timeout",
        sanitized_error="WordPress request timed out.",
    )


def persist_pending_attempt(
    db_path: str | Path,
    *,
    attempt_id: str = ATTEMPT_PENDING,
) -> WordPressDraftAttempt:
    return persist_attempt(
        db_path,
        outcome=WordPressAttemptState.PENDING,
        attempt_id=attempt_id,
        seed=f"pending:{attempt_id}",
    )


def persist_failed_attempt(
    db_path: str | Path,
    *,
    attempt_id: str = ATTEMPT_FAILED,
) -> WordPressDraftAttempt:
    return persist_attempt(
        db_path,
        outcome=WordPressAttemptState.FAILED_DEFINITELY,
        attempt_id=attempt_id,
        seed=f"failed:{attempt_id}",
        failure_kind="auth_failed",
        sanitized_error="WordPress authentication was rejected.",
    )


def build_v1_database(db_path: str | Path) -> None:
    """Build a genuine schema-v1 database with one complete review chain."""

    domain = asyncio.run(build_review_domain())
    audit = SiteAuditResult(
        url="https://example.com/",
        status=AuditStatus.SUCCESS,
        score=90,
        band="good",
        score_breakdown={},
        recommendations=(),
        error=None,
        source="fake",
        source_version="1",
        evidence=(
            AuditEvidence(
                AuditEvidenceCategory.META,
                "meta.title.present",
                False,
                AuditEvidenceOutcome.ABSENT,
                "meta.title.present",
            ),
        ),
    )
    research = ResearchReport(
        question="buyer question",
        status=ResearchStatus.SUCCESS,
        draft_text="Research [S1].",
        sources=(ResearchSource("S1", "Source", "https://source.example/s1"),),
        error=None,
    )
    connection = sqlite3.connect(Path(db_path))
    try:
        connection.executescript(V1_SCHEMA)
        stamp = _timestamp(NOW)
        connection.execute(
            "INSERT INTO runs(run_id,site_key,workflow_name,started_at,completed_at,status,failure_kind,sanitized_error) VALUES(?,?,?,?,?,?,?,?)",
            (RUN_ID, "https://example.com:443", WORKFLOW_NAME, stamp, stamp, "succeeded", None, None),
        )
        for artifact_type, artifact_id, payload in (
            (ArtifactType.SITE_CONTENT, SITE_CONTENT_ARTIFACT_ID, domain.site_content),
            (ArtifactType.SITE_AUDIT, SITE_AUDIT_ARTIFACT_ID, audit),
            (ArtifactType.INDUSTRY_RESEARCH, INDUSTRY_RESEARCH_ARTIFACT_ID, research),
            (
                ArtifactType.CONTENT_OPPORTUNITY,
                CONTENT_OPPORTUNITY_ARTIFACT_ID,
                domain.opportunity_report,
            ),
            (ArtifactType.CHANGE_PLAN, CHANGE_PLAN_ARTIFACT_ID, domain.change_plan),
            (ArtifactType.CONTENT_DRAFT, CONTENT_DRAFT_ARTIFACT_ID, domain.content_draft),
        ):
            connection.execute(
                "INSERT INTO artifacts(artifact_id,run_id,artifact_type,payload_version,created_at,payload_json) VALUES(?,?,?,?,?,?)",
                (
                    artifact_id,
                    RUN_ID,
                    artifact_type.value,
                    1,
                    stamp,
                    encode_artifact(artifact_type, payload),
                ),
            )
        connection.commit()
    finally:
        connection.close()


def raw_table_dump(db_path: str | Path) -> tuple[object, ...]:
    """Return all rows of the three v1 business tables for comparison."""

    connection = sqlite3.connect(Path(db_path))
    try:
        return tuple(
            tuple(connection.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall())
            for table in ("runs", "artifacts", "wordpress_draft_attempts")
        )
    finally:
        connection.close()


def user_version(db_path: str | Path) -> int:
    connection = sqlite3.connect(Path(db_path))
    try:
        return int(connection.execute("PRAGMA user_version").fetchone()[0])
    finally:
        connection.close()


def table_names(db_path: str | Path) -> set[str]:
    connection = sqlite3.connect(Path(db_path))
    try:
        return {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    finally:
        connection.close()
