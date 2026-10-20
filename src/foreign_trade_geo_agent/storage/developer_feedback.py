"""An independent append-only SQLite journal; never opens workflow databases."""
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
import sqlite3

from foreign_trade_geo_agent.core.developer_feedback import FeedbackBinding, FEEDBACK_KIND, validate_feedback
from foreign_trade_geo_agent.core.history import validate_uuid

_SCHEMA = """
CREATE TABLE IF NOT EXISTS developer_feedback (
 submission_id TEXT PRIMARY KEY NOT NULL,
 database_key TEXT NOT NULL,
 run_id TEXT NOT NULL,
 object_id TEXT NOT NULL,
 version INTEGER NOT NULL,
 digest TEXT NOT NULL,
 kind TEXT NOT NULL CHECK(kind='LOCAL_DEVELOPER_FEEDBACK'),
 disposition TEXT NOT NULL CHECK(disposition IN ('observation','needs_revision')),
 note TEXT NOT NULL CHECK(length(note) BETWEEN 1 AND 2000),
 marked_text TEXT NOT NULL CHECK(length(marked_text)<=2000),
 created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS feedback_object ON developer_feedback(database_key,run_id,object_id,created_at);
CREATE TRIGGER IF NOT EXISTS feedback_no_update BEFORE UPDATE ON developer_feedback
 BEGIN SELECT RAISE(ABORT,'append-only developer feedback'); END;
CREATE TRIGGER IF NOT EXISTS feedback_no_delete BEFORE DELETE ON developer_feedback
 BEGIN SELECT RAISE(ABORT,'append-only developer feedback'); END;
"""


class SQLiteDeveloperFeedbackStore:
    def __init__(self, path: Path):
        self.path = Path(path).resolve()

    def list(self, binding: FeedbackBinding):
        if not self.path.exists():
            return []
        with closing(sqlite3.connect(self.path.as_uri()+'?mode=ro', uri=True, timeout=3)) as db:
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA query_only=ON')
            return [dict(row) for row in db.execute(
                'SELECT * FROM developer_feedback WHERE database_key=? AND run_id=? AND object_id=? '
                'ORDER BY created_at DESC,submission_id DESC LIMIT 100',
                (binding.database, binding.run_id, binding.object_id))]

    def append(self, binding: FeedbackBinding, submission_id, *, note, marked_text, disposition):
        validate_uuid(submission_id, 'submission_id')
        validate_feedback(note, marked_text, disposition)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=3)) as db:
            db.executescript(_SCHEMA)
            db.execute('BEGIN IMMEDIATE')
            values = (submission_id, binding.database, binding.run_id, binding.object_id, binding.version,
                      binding.digest, FEEDBACK_KIND, disposition, note, marked_text)
            existing = db.execute('SELECT submission_id,database_key,run_id,object_id,version,digest,kind,'
                                  'disposition,note,marked_text FROM developer_feedback WHERE submission_id=?',
                                  (submission_id,)).fetchone()
            if existing:
                if existing != values:
                    raise ValueError('Submission conflict')
                return
            count = db.execute('SELECT COUNT(*) FROM developer_feedback WHERE database_key=? AND run_id=? '
                               'AND object_id=?', (binding.database,binding.run_id,binding.object_id)).fetchone()[0]
            if count >= 200:
                raise ValueError('Feedback budget exhausted')
            db.execute('INSERT INTO developer_feedback VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                       (*values, datetime.now(UTC).isoformat()))
            db.commit()
