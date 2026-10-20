"""Append-only SQLite feedback journal referencing the existing native Draft.

Kept beside the intake journal because that journal validates an exact schema.
No native artifact, history schema, authority receipt or delivery state is changed.
"""
from contextlib import closing
from contextlib import contextmanager
from pathlib import Path
import sqlite3

from foreign_trade_geo_agent.core.content_draft_review import (
    LocalDraftRevision, MAX_LOCAL_REVISIONS, local_text_digest, validate_local_review_text,
)
from foreign_trade_geo_agent.core.history import HistoryConflictError, HistoryStoreError
from foreign_trade_geo_agent.storage.evidence_intake import _dump, _load

_TABLE = """CREATE TABLE local_draft_revisions (
origin_sha256 TEXT NOT NULL, version INTEGER NOT NULL, payload TEXT NOT NULL,
note TEXT NOT NULL, PRIMARY KEY(origin_sha256, version))"""
_TRIGGERS = tuple(
    f"CREATE TRIGGER local_draft_no_{action.lower()} BEFORE {action} ON local_draft_revisions "
    "BEGIN SELECT RAISE(ABORT, 'Local draft review is immutable'); END"
    for action in ("UPDATE", "DELETE")
)


class SQLiteLocalDraftReviewStore:
    def __init__(self, path: Path):
        self.path = Path(path)

    @contextmanager
    def version_guard(self):
        """Keep article appends from racing a version-specific validation save."""
        with closing(sqlite3.connect(self.path.as_uri() + '?mode=rw', uri=True)) as db:
            db.execute('BEGIN IMMEDIATE')
            self._check_schema(db)
            yield
            db.rollback()

    def _check_schema(self, db):
        expected = sorted((_TABLE, *_TRIGGERS))
        actual = sorted(row[0] for row in db.execute(
            "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%'"))
        if actual != expected or db.execute("PRAGMA user_version").fetchone()[0] != 1:
            raise HistoryStoreError("Local review journal is unavailable.")

    def _read(self, db, origin):
        self._check_schema(db)
        rows = db.execute("SELECT version, payload, note FROM local_draft_revisions "
            "WHERE origin_sha256=? ORDER BY version LIMIT ?", (origin, MAX_LOCAL_REVISIONS + 1)).fetchall()
        if len(rows) > MAX_LOCAL_REVISIONS:
            raise HistoryStoreError("Local review limit exceeded.")
        result = []
        for version, payload, note in rows:
            record = _load(payload, LocalDraftRevision)
            if (record.origin_sha256 != origin or record.version != version
                    or version != len(result) + 1 or note != record.note):
                raise HistoryStoreError("Local review journal is invalid.")
            result.append(record)
        return tuple(result)

    def revisions(self, origin_sha256):
        if not self.path.exists():
            return ()
        try:
            with closing(sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)) as db:
                return self._read(db, origin_sha256)
        except Exception:
            raise HistoryStoreError("Local review journal is unavailable.") from None

    def append(self, *, origin_sha256, expected_version, original_body, body_text, note,
               status, frozen_evidence_sha256, observed_evidence_sha256, saved_at, candidate_decisions=()):
        validate_local_review_text(body_text, note, status)
        if type(expected_version) is not int or expected_version < 0:
            raise HistoryConflictError("Local review version is stale.")
        # Exclusive creation only on the first write. Never replace a damaged file.
        try:
            with self.path.open("xb"):
                pass
            created = True
        except FileExistsError:
            created = False
        try:
            with closing(sqlite3.connect(self.path)) as db:
                db.execute("BEGIN IMMEDIATE")
                if created:
                    db.execute(_TABLE)
                    for sql in _TRIGGERS:
                        db.execute(sql)
                    db.execute("PRAGMA user_version=1")
                    # Keep a readable empty journal even when the first append
                    # conflicts or fails validation and its transaction rolls back.
                    db.commit()
                    db.execute("BEGIN IMMEDIATE")
                history = self._read(db, origin_sha256)
                if expected_version != len(history) or len(history) >= MAX_LOCAL_REVISIONS:
                    raise HistoryConflictError("Local review version is stale or full.")
                previous = history[-1] if history else None
                changed = body_text != (previous.body_text if previous else original_body)
                pending = (changed or frozen_evidence_sha256 != observed_evidence_sha256
                    or bool(previous and previous.validation_state == "PENDING_REVALIDATION"))
                record = LocalDraftRevision(origin_sha256, len(history) + 1, len(history), body_text,
                    local_text_digest(body_text), note, "PENDING_REVIEW" if changed else status,
                    "PENDING_REVALIDATION" if pending else "HISTORICAL_NATIVE_VALIDATION",
                    frozen_evidence_sha256, observed_evidence_sha256, saved_at, candidate_decisions)
                db.execute("INSERT INTO local_draft_revisions VALUES (?,?,?,?)",
                    (origin_sha256, record.version, _dump(record), record.note))
                db.commit()
                return record
        except HistoryConflictError:
            raise
        except Exception:
            raise HistoryStoreError("Local review was not saved.") from None


_VALIDATION_TABLE = ('CREATE TABLE local_draft_revalidations (origin_sha256 TEXT NOT NULL, '
    'sequence INTEGER NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(origin_sha256, sequence))')
_VALIDATION_TRIGGERS = tuple(
    f'CREATE TRIGGER local_revalidation_no_{action.lower()} BEFORE {action} ON local_draft_revalidations '
    "BEGIN SELECT RAISE(ABORT, 'Local revalidation is immutable'); END" for action in ('UPDATE', 'DELETE'))


class SQLiteLocalRevalidationStore:
    """Separate bounded journal; existing revision and Intake schemas stay intact."""
    def __init__(self, path):
        self.path = Path(path)

    def _read(self, db, origin):
        from foreign_trade_geo_agent.core.draft_revalidation import LocalRevisionRevalidation
        actual = sorted(r[0] for r in db.execute(
            "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%'"))
        if actual != sorted((_VALIDATION_TABLE, *_VALIDATION_TRIGGERS)) or db.execute('PRAGMA user_version').fetchone()[0] != 1:
            raise HistoryStoreError('Local revalidation journal is unavailable.')
        rows = db.execute('SELECT sequence, payload FROM local_draft_revalidations '
                          'WHERE origin_sha256=? ORDER BY sequence LIMIT 101', (origin,)).fetchall()
        if len(rows) > 100:
            raise HistoryStoreError('Local revalidation limit exceeded.')
        records = []
        for sequence, payload in rows:
            record = _load(payload, LocalRevisionRevalidation)
            if sequence != len(records) + 1 or record.report.origin_sha256 != origin:
                raise HistoryStoreError('Local revalidation binding is invalid.')
            records.append(record)
        return tuple(records)

    def records(self, origin):
        if not self.path.exists():
            return ()
        try:
            with closing(sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True)) as db:
                return self._read(db, origin)
        except Exception:
            raise HistoryStoreError('Local revalidation journal is unavailable.') from None

    def append(self, record):
        try:
            with self.path.open('xb'):
                pass
            created = True
        except FileExistsError:
            created = False
        try:
            with closing(sqlite3.connect(self.path)) as db:
                db.execute('BEGIN IMMEDIATE')
                if created:
                    db.execute(_VALIDATION_TABLE)
                    for sql in _VALIDATION_TRIGGERS:
                        db.execute(sql)
                    db.execute('PRAGMA user_version=1')
                    db.commit()
                    db.execute('BEGIN IMMEDIATE')
                history = self._read(db, record.report.origin_sha256)
                if len(history) >= 100 or (history and history[-1].report.sha256 == record.report.sha256
                        and history[-1].decision == record.decision and history[-1].note == record.note):
                    raise HistoryConflictError('Local revalidation is already recorded or full.')
                db.execute('INSERT INTO local_draft_revalidations VALUES (?,?,?)',
                    (record.report.origin_sha256, len(history) + 1, _dump(record)))
                db.commit()
        except HistoryConflictError:
            raise
        except Exception:
            raise HistoryStoreError('Local revalidation was not saved.') from None
