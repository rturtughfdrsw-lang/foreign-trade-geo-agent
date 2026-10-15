"""Independent TEST-only permits. Never reads P1 or Intake authorization journals."""
from datetime import UTC, datetime
from contextlib import contextmanager
from pathlib import Path
import sqlite3


class WebExperimentLedger:
    """One fixed server ledger, unique bundle and permit, commit before HTTP.

    The local operator owns the filesystem trust boundary. Deleting/restoring
    this ledger is forbidden; this is not a tamper-proof production authority.
    Live composition supplies a fixed path, never a browser/journal path.
    """
    def __init__(self, path):
        self.path = Path(path)

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS permits ('
                'permit TEXT PRIMARY KEY, bundle TEXT UNIQUE NOT NULL, directory TEXT NOT NULL, '
                'request TEXT NOT NULL, mode TEXT NOT NULL, expires TEXT NOT NULL, '
                'budget INTEGER NOT NULL CHECK(budget=1), claimed TEXT)')

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        try:
            db.execute('PRAGMA synchronous=FULL')
            with db:
                yield db
        finally:
            db.close()

    def issue(self, permit, bundle, directory, request, mode, expires):
        if mode not in {'MOCK', 'LIVE'} or expires.tzinfo is None or expires <= datetime.now(UTC):
            raise ValueError('PERMIT_INVALID')
        with self._connect() as db:
            # No update/renew/reissue API. A consumed bundle stays consumed.
            db.execute('INSERT INTO permits VALUES (?,?,?,?,?,?,1,NULL)',
                (permit, bundle, str(Path(directory).resolve()), request, mode, expires.isoformat()))

    def read(self, permit):
        # Missing ledger fails closed, rather than creating an empty replacement.
        if not self.path.is_file():
            raise ValueError('PERMIT_LEDGER_MISSING')
        with self._connect() as db:
            row = db.execute('SELECT * FROM permits WHERE permit=?', (permit,)).fetchone()
        if row is None:
            raise ValueError('PERMIT_MISSING')
        return row

    def validate(self, permit, bundle, directory, request, mode, *, unclaimed=False):
        row = self.read(permit)
        if row[1:5] != (bundle, str(Path(directory).resolve()), request, mode):
            raise ValueError('PERMIT_BINDING_CHANGED')
        if unclaimed and (row[7] is not None or datetime.now(UTC) >= datetime.fromisoformat(row[5])):
            raise ValueError('PERMIT_EXPIRED_OR_CONSUMED')
        return row

    def claim(self, permit, bundle, directory, request, mode):
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM permits WHERE permit=?', (permit,)).fetchone()
            if row is None or row[1:5] != (bundle, str(Path(directory).resolve()), request, mode) \
                    or row[7] is not None or datetime.now(UTC) >= datetime.fromisoformat(row[5]):
                raise ValueError('PERMIT_EXPIRED_OR_CONSUMED')
            db.execute('UPDATE permits SET claimed=? WHERE permit=? AND claimed IS NULL',
                (datetime.now(UTC).isoformat(), permit))
            db.commit()  # MUST succeed before any transport/credential creation.
