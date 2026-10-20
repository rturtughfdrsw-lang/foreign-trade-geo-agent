"""Independent append-only Preview snapshots, reservations, results and feedback."""
from contextlib import closing, contextmanager
from dataclasses import asdict
from pathlib import Path
import json
import sqlite3
from uuid import uuid4

from foreign_trade_geo_agent.core.commercial_preview import (
    admit, canonical, digest, material, request_digest, require,
)
from foreign_trade_geo_agent.core.developer_feedback import validate_feedback
from foreign_trade_geo_agent.core.history import validate_uuid

_SCHEMA = '''
CREATE TABLE IF NOT EXISTS preview_snapshots (
 run_id TEXT NOT NULL, revision INTEGER NOT NULL, payload TEXT NOT NULL,
 PRIMARY KEY(run_id,revision));
CREATE TABLE IF NOT EXISTS preview_executions (
 attempt_id TEXT PRIMARY KEY, run_id TEXT NOT NULL UNIQUE, task_id TEXT NOT NULL,
 confirmation_id TEXT NOT NULL UNIQUE, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS preview_results (
 attempt_id TEXT PRIMARY KEY REFERENCES preview_executions(attempt_id), payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS preview_feedback (
 submission_id TEXT PRIMARY KEY, namespace TEXT NOT NULL CHECK(namespace='COMMERCIAL_PREVIEW'),
 run_id TEXT NOT NULL, object_id TEXT NOT NULL, version INTEGER NOT NULL,
 digest TEXT NOT NULL, payload TEXT NOT NULL);
'''


class SQLitePreviewStore:
    def __init__(self, path: Path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript(_SCHEMA)
            for table in ('preview_snapshots', 'preview_executions', 'preview_results', 'preview_feedback'):
                for action in ('UPDATE', 'DELETE'):
                    db.execute(f"CREATE TRIGGER IF NOT EXISTS {table}_no_{action} BEFORE {action} ON {table} "
                               "BEGIN SELECT RAISE(ABORT,'append-only Preview'); END")

    @contextmanager
    def connection(self):
        with closing(sqlite3.connect(self.path, timeout=5)) as db:
            db.execute('PRAGMA foreign_keys=ON')
            with db:
                yield db

    @staticmethod
    def encode(value):
        raw = canonical(value)
        require(len(raw.encode('utf-8')) <= 1_000_000, 'PREVIEW_STORAGE_BUDGET')
        return raw

    def create(self, state):
        validate_uuid(state['run_id'], 'run_id')
        require(state['revision'] == 1)
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            require(db.execute('SELECT COUNT(DISTINCT run_id) FROM preview_snapshots').fetchone()[0] < 200,
                    'PREVIEW_RUN_BUDGET')
            db.execute('INSERT INTO preview_snapshots VALUES (?,?,?)',
                       (state['run_id'], 1, self.encode(state)))

    def _read(self, db, run_id):
        validate_uuid(run_id, 'run_id')
        row = db.execute('SELECT payload FROM preview_snapshots WHERE run_id=? '
                         'ORDER BY revision DESC LIMIT 1', (run_id,)).fetchone()
        require(row is not None, 'PREVIEW_NOT_FOUND')
        return json.loads(row[0])

    def read(self, run_id):
        with self.connection() as db:
            return self._read(db, run_id)

    def list_runs(self):
        with self.connection() as db:
            return [r[0] for r in db.execute('SELECT DISTINCT run_id FROM preview_snapshots LIMIT 200')]

    def save(self, state, expected_revision):
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            old = self._read(db, state['run_id'])
            require(old['revision'] == expected_revision, 'PREVIEW_STALE_FORM')
            require(expected_revision < 1000, 'PREVIEW_REVISION_BUDGET')
            state = dict(state, revision=expected_revision + 1)
            db.execute('INSERT INTO preview_snapshots VALUES (?,?,?)',
                       (state['run_id'], state['revision'], self.encode(state)))
        return state

    def reserve(self, state, confirmation):
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            current = self._read(db, state['run_id'])
            require(current['revision'] == state['revision'], 'PREVIEW_STALE_FORM')
            admit(current, confirmation)
            row = db.execute('SELECT payload FROM preview_executions WHERE run_id=?',
                             (state['run_id'],)).fetchone()
            if row:
                existing = json.loads(row[0])
                require(existing['confirmation'] == asdict(confirmation), 'PREVIEW_EXECUTION_CONSUMED')
                return dict(existing, duplicate=True)
            value = dict(attempt_id=str(uuid4()), run_id=state['run_id'],
                         task_id=state['task']['task_id'], confirmation=asdict(confirmation),
                         request_digest=request_digest(state), material=material(state),
                         production_authorized=False, status='UNKNOWN')
            db.execute('INSERT INTO preview_executions VALUES (?,?,?,?,?)',
                       (value['attempt_id'], value['run_id'], value['task_id'],
                        confirmation.confirmation_id, self.encode(value)))
        # Commit completes before the caller can invoke Writer.
        return dict(value, duplicate=False)

    def finish(self, attempt_id, result):
        validate_uuid(attempt_id, 'attempt_id')
        require(result['production_authorized'] is False)
        with self.connection() as db:
            db.execute('INSERT INTO preview_results VALUES (?,?)', (attempt_id, self.encode(result)))
        return result

    def attempt(self, run_id):
        validate_uuid(run_id, 'run_id')
        with self.connection() as db:
            row = db.execute('SELECT e.payload,r.payload FROM preview_executions e '
                             'LEFT JOIN preview_results r USING(attempt_id) WHERE e.run_id=?', (run_id,)).fetchone()
        if not row:
            return None
        value = json.loads(row[0])
        value['result'] = json.loads(row[1]) if row[1] else None
        return value

    def feedback(self, run_id, object_id, version, object_digest, submission_id, note):
        for name, value in [('run_id', run_id), ('object_id', object_id), ('submission_id', submission_id)]:
            validate_uuid(value, name)
        validate_feedback(note, '', 'observation')
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            state = self._read(db, run_id)
            row = db.execute('SELECT e.payload,r.payload FROM preview_executions e '
                             'LEFT JOIN preview_results r USING(attempt_id) WHERE e.run_id=?', (run_id,)).fetchone()
            attempt = json.loads(row[0]) if row else None
            if attempt is not None:
                attempt['result'] = json.loads(row[1]) if row[1] else None
            require(feedback_binding(state, attempt) ==
                    (object_id, version, object_digest), 'PREVIEW_FEEDBACK_BINDING')
            payload = self.encode(dict(kind='LOCAL_PREVIEW_FEEDBACK', note=note,
                                       production_authorized=False))
            values = (submission_id, 'COMMERCIAL_PREVIEW', run_id, object_id, version, object_digest, payload)
            old = db.execute('SELECT * FROM preview_feedback WHERE submission_id=?', (submission_id,)).fetchone()
            if old:
                require(old == values, 'PREVIEW_FEEDBACK_CONFLICT')
                return
            require(db.execute('SELECT COUNT(*) FROM preview_feedback WHERE run_id=?',
                               (run_id,)).fetchone()[0] < 200, 'PREVIEW_FEEDBACK_BUDGET')
            db.execute('INSERT INTO preview_feedback VALUES (?,?,?,?,?,?,?)', values)

    def list_feedback(self, run_id):
        with self.connection() as db:
            return [dict(submission_id=r[0], object_id=r[3], version=r[4], digest=r[5], **json.loads(r[6]))
                    for r in db.execute('SELECT * FROM preview_feedback WHERE run_id=? ORDER BY rowid', (run_id,))]


def feedback_binding(state, attempt):
    return (attempt['attempt_id'] if attempt else state['task']['task_id'],
            attempt['material']['task']['version'] if attempt else state['task']['version'],
            digest({'state': state, 'attempt': attempt}))
