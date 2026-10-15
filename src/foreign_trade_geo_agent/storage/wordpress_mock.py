"""Append-only, local TEST-only exchange journal; never production authority."""
from contextlib import closing
from datetime import UTC, datetime
import json
from pathlib import Path
import sqlite3

from foreign_trade_geo_agent.core.history import HistoryStoreError


class SQLiteWordPressMockJournal:
    def __init__(self, path):
        self.path = Path(path).resolve()

    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=5)
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('CREATE TABLE IF NOT EXISTS claims ('
                   'binding TEXT PRIMARY KEY, payload TEXT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS events ('
                   'binding TEXT NOT NULL REFERENCES claims(binding), kind TEXT NOT NULL '
                   "CHECK(kind IN ('exchange','result')), payload TEXT NOT NULL, PRIMARY KEY(binding,kind))")
        for table in ('claims', 'events'):
            for action in ('UPDATE', 'DELETE'):
                db.execute(f'CREATE TRIGGER IF NOT EXISTS {table}_no_{action} '
                           f'BEFORE {action} ON {table} BEGIN '
                           "SELECT RAISE(ABORT, 'TEST journal is append-only'); END")
        db.commit()
        return db

    @staticmethod
    def _dump(payload):
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, allow_nan=False)

    def claim(self, binding, payload):
        try:
            with closing(self._connect()) as db:
                db.execute('BEGIN IMMEDIATE')
                if db.execute('SELECT 1 FROM claims WHERE binding=?', (binding,)).fetchone():
                    return False
                db.execute('INSERT INTO claims VALUES (?,?)',
                           (binding, self._dump(dict(payload, claimed_at=datetime.now(UTC).isoformat()))))
                db.commit()
                return True
        except Exception:
            raise HistoryStoreError('TEST delivery claim unavailable; no retry permitted.') from None

    def append(self, binding, kind, payload):
        try:
            with closing(self._connect()) as db:
                db.execute('INSERT INTO events VALUES (?,?,?)', (binding, kind, self._dump(payload)))
                db.commit()
        except Exception:
            raise HistoryStoreError('TEST delivery result could not be saved; no retry permitted.') from None

    def records(self):
        if not self.path.exists():
            return ()
        try:
            with closing(self._connect()) as db:
                rows = db.execute('SELECT binding,payload FROM claims ORDER BY rowid DESC LIMIT 21').fetchall()
                if len(rows) > 20:
                    raise ValueError()
                records = []
                for binding, raw in rows:
                    claim = json.loads(raw)
                    if claim['binding_sha256'] != binding or claim['profile'] != 'WORDPRESS_MOCK_TEST_ONLY_V1':
                        raise ValueError()
                    events = {kind: json.loads(payload) for kind, payload in db.execute(
                        'SELECT kind,payload FROM events WHERE binding=?', (binding,))}
                    records.append(dict(claim=claim, **events))
                return tuple(records)
        except Exception:
            raise HistoryStoreError('TEST delivery journal unavailable; execution blocked.') from None
