"""Append-only local intake journal; reuses storage's strict dataclass codec.

Separate V1 journal (as with review receipts), never a HistoryStore migration,
review authority or P/S artifact. Opening cannot create/migrate a database.
"""
from contextlib import closing, contextmanager
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from foreign_trade_geo_agent.core.evidence_intake import (
    IntakeCheck, IntakeSnapshot, IntakeStatus, MAX_SNAPSHOT_BYTES, native_plan_error,
    require, snapshot_digest, validate_assessment,
    rebind_preserves_task,
)
from foreign_trade_geo_agent.core.evidence_sufficiency import bounded_id
from .serialization import _decode, _encode, _unique_object

_TABLES = {
    "intake_snapshots": "CREATE TABLE intake_snapshots (project_id TEXT NOT NULL, task_id TEXT NOT NULL, "
        "revision INTEGER NOT NULL, digest TEXT NOT NULL, parent_digest TEXT, payload TEXT NOT NULL, "
        "PRIMARY KEY(project_id,task_id,revision))",
    "intake_checks": "CREATE TABLE intake_checks (check_id TEXT PRIMARY KEY NOT NULL, project_id TEXT NOT NULL, "
        "task_id TEXT NOT NULL, digest TEXT NOT NULL, payload TEXT NOT NULL)",
}
_TRIGGERS = {
    f"{table}_no_{action.lower()}": f"CREATE TRIGGER {table}_no_{action.lower()} BEFORE {action} ON {table} "
        "BEGIN SELECT RAISE(ABORT, 'Intake journal is immutable'); END"
    for table in _TABLES for action in ("UPDATE", "DELETE")
}
_DDL = ";\n".join((*_TABLES.values(), *_TRIGGERS.values(), "PRAGMA user_version=1")) + ";"
_SCHEMA = sorted([
    *(("table", name, name, sql) for name, sql in _TABLES.items()),
    *(("index", f"sqlite_autoindex_{name}_1", name, None) for name in _TABLES),
    *(("trigger", name, name.rsplit("_no_", 1)[0], sql) for name, sql in _TRIGGERS.items()),
], key=lambda row: row[1])


def _dump(value) -> str:
    raw = json.dumps(_encode(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    require(len(raw.encode("utf-8")) <= MAX_SNAPSHOT_BYTES)
    return raw


def _load(raw: str, root):
    require(type(raw) is str and len(raw.encode("utf-8")) <= MAX_SNAPSHOT_BYTES)
    value = json.loads(raw, object_pairs_hook=_unique_object,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    return _decode(value, root)


def _transition(old: IntakeSnapshot, new: IntakeSnapshot, *, strict_rebind=False):
    """Reject rewriting old records, stale/replayed versions or implicit scope loss."""
    require(new.revision == old.revision + 1 and new.task.project_id == old.task.project_id
            and new.task.task_id == old.task.task_id and new.task.customer_id == old.task.customer_id
            and new.evidence[:len(old.evidence)] == old.evidence
            and new.scope_consents[:len(old.scope_consents)] == old.scope_consents
            and new.submission_ids[:len(old.submission_ids)] == old.submission_ids)
    if new.plan_bound:
        require(not old.plan_bound and new.plan_version == old.plan_version + 1
                and new.task == old.task and new.point_subjects == old.point_subjects
                and new.evidence == old.evidence and new.evidence_version == old.evidence_version
                and new.scope_consents == old.scope_consents and new.submission_ids == old.submission_ids
                and native_plan_error(new.planning_input, new.point_subjects) is None)
        # Preserve readability of pre-integration V1 history. New appends must
        # also preserve native evidence and target, even through direct storage.
        if strict_rebind:
            require(rebind_preserves_task(old, new.planning_input))
        return
    require(new.plan_version == old.plan_version and new.planning_input == old.planning_input
            and len(new.submission_ids) == len(old.submission_ids) + 1)
    added = new.evidence[len(old.evidence):]
    require(new.evidence_version == old.evidence_version + bool(added)
            and all(e.evidence_version == new.evidence_version and e.submission_id == new.submission_ids[-1] for e in added))
    if new.scope_consents == old.scope_consents:
        require(new.task == old.task and new.point_subjects == old.point_subjects and bool(added))
    else:
        require(len(new.scope_consents) == len(old.scope_consents) + 1)
        consent = new.scope_consents[-1]
        require(consent.previous_snapshot_sha256 == snapshot_digest(old)
                and consent.submission_id == new.submission_ids[-1]
                and new.task.task_version == old.task.task_version + 1
                and new.task.goal == consent.adjustment.new_goal)
        retained = tuple(r for r in old.task.requirements if r.requirement_id in consent.adjustment.retained_requirement_ids)
        require(tuple(r.requirement_id for r in retained) == consent.adjustment.retained_requirement_ids)
        indexes = tuple(dict.fromkeys(r.point_index for r in retained))
        require(tuple(r for r in old.task.requirements if r.point_index in indexes) == retained
                and indexes == tuple(sorted(indexes))
                and new.point_subjects == tuple(old.point_subjects[i] for i in indexes))
        from dataclasses import replace
        require(new.task.requirements == tuple(replace(r, point_index=indexes.index(r.point_index)) for r in retained))
    required = {r.requirement_id: r for r in new.task.requirements}
    require(all(all(r in required and e.supplement.method in required[r].allowed_methods
                    for r in e.supplement.requirement_ids) for e in added))


class SQLiteEvidenceIntakeStore:
    def __init__(self, path: str | Path):
        self._path = Path(path).resolve()
        try:
            require(self._path.is_file())
            with self._connect() as conn:
                self._schema(conn)
        except Exception:
            raise ValueError("INTAKE_STORE_UNAVAILABLE") from None

    @classmethod
    def create(cls, path: str | Path):
        try:
            target = Path(path).resolve()
            with target.open("xb"):
                pass
            with closing(sqlite3.connect(target)) as conn:
                conn.executescript(_DDL)
            return cls(target)
        except Exception:
            raise ValueError("INTAKE_STORE_CREATION_REJECTED") from None

    @contextmanager
    def _connect(self, *, writable=False):
        conn = sqlite3.connect(self._path.as_uri() + ("?mode=rw" if writable else "?mode=ro"), uri=True, timeout=1)
        try:
            conn.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, MAX_SNAPSHOT_BYTES + 4096)
            conn.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, 4096)
            budget = 1000
            def progress():
                nonlocal budget
                budget -= 1
                return int(budget <= 0)
            conn.set_progress_handler(progress, 1000)
            conn.execute("PRAGMA trusted_schema=OFF")
            conn.execute("BEGIN IMMEDIATE" if writable else "BEGIN")
            if not writable:
                conn.execute("PRAGMA query_only=ON")
            self._schema(conn)
            yield conn
            if writable:
                conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _schema(conn):
        require(conn.execute("PRAGMA user_version").fetchone() == (1,))
        rows = conn.execute("SELECT type,name,tbl_name,sql FROM sqlite_schema ORDER BY name LIMIT 9").fetchall()
        require(rows == _SCHEMA)

    @staticmethod
    def _read(conn, project_id, task_id, revision=None):
        require(bounded_id(project_id) and bounded_id(task_id))
        if revision is None:
            rows = conn.execute("SELECT revision,digest,parent_digest,payload FROM intake_snapshots "
                "WHERE project_id=? AND task_id=? ORDER BY revision DESC LIMIT 1", (project_id, task_id)).fetchall()
        else:
            require(type(revision) is int and 1 <= revision <= 1000)
            rows = conn.execute("SELECT revision,digest,parent_digest,payload FROM intake_snapshots "
                "WHERE project_id=? AND task_id=? AND revision=? LIMIT 1", (project_id, task_id, revision)).fetchall()
        require(len(rows) == 1)
        rev, digest, parent, raw = rows[0]
        result = _load(raw, IntakeSnapshot)
        require(result.revision == rev and result.task.project_id == project_id and result.task.task_id == task_id
                and snapshot_digest(result) == digest)
        return result, parent

    def create_snapshot(self, snapshot: IntakeSnapshot) -> None:
        try:
            snapshot = _load(_dump(snapshot), IntakeSnapshot)
            require(snapshot.revision == snapshot.evidence_version == snapshot.plan_version == snapshot.task.task_version == 1
                    and snapshot.plan_bound and not snapshot.evidence and not snapshot.scope_consents
                    and not snapshot.submission_ids and native_plan_error(snapshot.planning_input, snapshot.point_subjects) is None)
            with self._connect(writable=True) as conn:
                require(conn.execute("SELECT 1 FROM intake_snapshots WHERE project_id=? AND task_id=? LIMIT 1",
                    (snapshot.task.project_id, snapshot.task.task_id)).fetchone() is None)
                self._insert(conn, snapshot, None)
        except Exception:
            raise ValueError("INTAKE_STORE_APPEND_REJECTED") from None

    def latest(self, project_id: str, task_id: str) -> IntakeSnapshot:
        try:
            with self._connect() as conn:
                snapshot, parent = self._read(conn, project_id, task_id)
                if snapshot.revision > 1:
                    old, _ = self._read(conn, project_id, task_id, snapshot.revision - 1)
                    require(parent == snapshot_digest(old))
                    _transition(old, snapshot)
                else:
                    require(parent is None)
                return snapshot
        except Exception:
            raise ValueError("INTAKE_STORE_READ_REJECTED") from None

    def get_revision(self, project_id: str, task_id: str, revision: int) -> IntakeSnapshot:
        try:
            with self._connect() as conn:
                return self._read(conn, project_id, task_id, revision)[0]
        except Exception:
            raise ValueError("INTAKE_STORE_READ_REJECTED") from None

    @staticmethod
    def _insert(conn, snapshot, parent):
        conn.execute("INSERT INTO intake_snapshots VALUES (?,?,?,?,?,?)", (snapshot.task.project_id,
            snapshot.task.task_id, snapshot.revision, snapshot_digest(snapshot), parent, _dump(snapshot)))

    def append(self, expected_sha256: str, snapshot: IntakeSnapshot) -> None:
        try:
            snapshot = _load(_dump(snapshot), IntakeSnapshot)
            with self._connect(writable=True) as conn:
                old, _ = self._read(conn, snapshot.task.project_id, snapshot.task.task_id)
                require(snapshot_digest(old) == expected_sha256)
                _transition(old, snapshot, strict_rebind=True)
                self._insert(conn, snapshot, expected_sha256)
        except Exception:
            raise ValueError("INTAKE_STORE_APPEND_REJECTED") from None

    def append_check(self, project_id: str, task_id: str, check: IntakeCheck) -> None:
        try:
            check = _load(_dump(check), IntakeCheck)
            with self._connect(writable=True) as conn:
                current, _ = self._read(conn, project_id, task_id)
                require(snapshot_digest(current) == check.snapshot_sha256)
                if check.assessment is not None:
                    # Persistence validates binding, not identity or meaning.
                    validate_assessment(current, check.assessment, check.assessment.reviewed_at)
                if check.status is IntakeStatus.CANDIDATE_FOR_REVIEW:
                    require(current.plan_bound and native_plan_error(current.planning_input, current.point_subjects) is None)
                conn.execute("INSERT INTO intake_checks VALUES (?,?,?,?,?)",
                             (str(uuid4()), project_id, task_id, check.snapshot_sha256, _dump(check)))
        except Exception:
            raise ValueError("INTAKE_STORE_CHECK_REJECTED") from None

    def checks(self, project_id: str, task_id: str, *, limit=100) -> tuple[IntakeCheck, ...]:
        try:
            require(bounded_id(project_id) and bounded_id(task_id) and type(limit) is int and 1 <= limit <= 100)
            with self._connect() as conn:
                rows = conn.execute("SELECT digest,payload FROM intake_checks WHERE project_id=? AND task_id=? "
                                    "ORDER BY rowid DESC LIMIT ?", (project_id, task_id, limit)).fetchall()
                results = tuple(_load(raw, IntakeCheck) for digest, raw in rows)
                require(all(r.snapshot_sha256 == row[0] for r, row in zip(results, rows)))
                return results
        except Exception:
            raise ValueError("INTAKE_STORE_READ_REJECTED") from None
