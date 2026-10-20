"""Bounded append-only SQLite receipt CACHE, not a review authority/history migration."""
from contextlib import closing, contextmanager
from pathlib import Path
import sqlite3

from foreign_trade_geo_agent.core.evidence_review_registry import EvidenceReviewReceipt
from foreign_trade_geo_agent.core.evidence_sufficiency import bounded_id

_TABLE_SQL = """CREATE TABLE review_receipts (
    review_id TEXT PRIMARY KEY NOT NULL,
    frozen_target BLOB NOT NULL,
    record BLOB NOT NULL,
    proof BLOB NOT NULL
)"""
_TRIGGERS = {
    "receipt_no_update": "CREATE TRIGGER receipt_no_update BEFORE UPDATE ON review_receipts\n"
                         "BEGIN SELECT RAISE(ABORT, 'Receipt is immutable'); END",
    "receipt_no_delete": "CREATE TRIGGER receipt_no_delete BEFORE DELETE ON review_receipts\n"
                         "BEGIN SELECT RAISE(ABORT, 'Receipt is immutable'); END",
}
_DDL = _TABLE_SQL + ";\n" + ";\n".join(_TRIGGERS.values()) + ";\nPRAGMA user_version=1;"
_SCHEMA = sorted([
    ("table", "review_receipts", "review_receipts", _TABLE_SQL),
    ("index", "sqlite_autoindex_review_receipts_1", "review_receipts", None),
    *(("trigger", name, "review_receipts", sql) for name, sql in _TRIGGERS.items()),
], key=lambda row: row[1])
_COLUMNS = (("review_id", "TEXT", 1, 1), ("frozen_target", "BLOB", 1, 0),
            ("record", "BLOB", 1, 0), ("proof", "BLOB", 1, 0))


class SQLiteEvidenceReviewReceipts:
    """Open existing cache without writes. Missing/wrong databases fail closed."""
    def __init__(self, path: Path | str) -> None:
        self._path = Path(path).resolve()
        try:
            if not self._path.is_file():
                raise ValueError()
            with self._connect() as conn:
                self._validate_schema(conn)
        except Exception:
            raise ValueError("Review receipt store is unavailable.") from None

    @classmethod
    def create(cls, path: Path | str) -> "SQLiteEvidenceReviewReceipts":
        """Explicit local cache creation; never overwrite or migrate a database."""
        target = Path(path).resolve()
        try:
            with target.open("xb"):
                pass
            with closing(sqlite3.connect(target)) as conn:
                with conn:
                    conn.executescript(_DDL)
            return cls(target)
        except Exception:
            raise ValueError("Review receipt store could not be created.") from None

    @contextmanager
    def _connect(self, *, writable=False):
        # Absolute file URI handles spaces/Unicode and cannot create missing DBs.
        conn = sqlite3.connect(self._path.as_uri()+ ("?mode=rw" if writable else "?mode=ro"),
                               uri=True, timeout=1.0)
        try:
            # timeout bounds lock waits, not attacker-controlled SQL execution.
            # Each connection has a finite cumulative VM step budget.
            remaining = 100
            def progress():
                nonlocal remaining
                remaining -= 1
                return int(remaining <= 0)
            conn.set_progress_handler(progress, 1000)
            conn.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 160*1024)
            conn.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, 4096)
            conn.execute("PRAGMA trusted_schema=OFF")
            if not writable:
                conn.execute("PRAGMA query_only=ON")
            else:
                # Hold the SQLite write lock throughout schema validation and
                # INSERT; a concurrent writer cannot swap validated triggers.
                conn.execute("BEGIN IMMEDIATE")
            yield conn
            if writable:
                conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _validate_schema(conn):
        if conn.execute("PRAGMA user_version").fetchone() != (1,):
            raise ValueError()
        columns = conn.execute("PRAGMA table_info(review_receipts)").fetchmany(5)
        if tuple((c[1], c[2], c[3], c[5]) for c in columns) != _COLUMNS:
            raise ValueError()
        # Reject any extra/changed executable objects; append must never execute
        # a trigger obtained from the untrusted cache. Collection is bounded.
        schema = conn.execute("SELECT type,name,tbl_name,sql FROM sqlite_schema "
                              "ORDER BY name LIMIT 5").fetchall()
        if schema != _SCHEMA:
            raise ValueError()

    def append(self, receipt: EvidenceReviewReceipt) -> None:
        """Persist opaque bytes once. Even a signed record is not approval here."""
        try:
            if type(receipt) is not EvidenceReviewReceipt:
                raise ValueError()
            EvidenceReviewReceipt(receipt.review_id, receipt.frozen_target, receipt.record, receipt.proof)
            with self._connect(writable=True) as conn:
                self._validate_schema(conn)
                conn.execute("INSERT INTO review_receipts VALUES (?,?,?,?)",
                    (receipt.review_id, receipt.frozen_target, receipt.record, receipt.proof))
        except Exception:
            raise ValueError("Review receipt could not be appended.") from None

    def get_receipt(self, review_id: str) -> EvidenceReviewReceipt | None:
        try:
            if not bounded_id(review_id):
                raise ValueError()
            with self._connect() as conn:
                self._validate_schema(conn)
                rows = conn.execute("SELECT review_id,frozen_target,record,proof FROM review_receipts "
                                    "WHERE review_id=? LIMIT 2", (review_id,)).fetchall()
            if not rows:
                return None
            if len(rows) != 1:
                raise ValueError()
            return EvidenceReviewReceipt(*rows[0])
        except Exception:
            raise ValueError("Review receipt could not be read.") from None
