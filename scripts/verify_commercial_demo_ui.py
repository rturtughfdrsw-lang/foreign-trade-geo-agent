"""Opt-in local browser QA. Uses fresh synthetic SQLite and ephemeral credentials."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import threading
import time
from unittest.mock import patch

import uvicorn

from foreign_trade_geo_agent.web.render_demo import create_demo_app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--playwright-module', default='playwright')
    parser.add_argument('--browser-channel', default='msedge')
    parser.add_argument('--output', type=Path, default=Path('.data/ui-verification'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    credentials = dict(DEMO_USERNAME='local-ui-test', DEMO_PASSWORD=secrets.token_urlsafe(32))
    with patch.dict(os.environ, credentials, clear=True):
        app = create_demo_app()
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', access_log=False, log_level='critical'))
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
        thread = threading.Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 20
            while not server.started and thread.is_alive() and time.monotonic() < deadline:
                time.sleep(.1)
            if not server.started:
                raise RuntimeError('Local demo server did not start')
            directory = Path(app.state.data_dir)
            hashes = lambda: {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.glob('*.sqlite3')}
            before = hashes()
            assert before, 'No demo databases found'
            env = {k: v for k, v in os.environ.items() if k.upper() in {
                'PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'USERPROFILE', 'LOCALAPPDATA', 'APPDATA', 'COMSPEC',
                'PROGRAMFILES', 'PROGRAMFILES(X86)', 'PROGRAMW6432'}}
            env.update(credentials, DEMO_URL=f'http://127.0.0.1:{port}',
                DEMO_PLAYWRIGHT_MODULE=args.playwright_module, DEMO_BROWSER_CHANNEL=args.browser_channel,
                DEMO_SCREENSHOTS=str(args.output.resolve()))
            subprocess.run(['node', str(Path(__file__).with_suffix('.cjs'))], env=env, check=True)
            assert hashes() == before, 'Browser navigation changed the database'
            flow = app.state.workflow
            state = flow.store.read(flow.store.list_runs()[0])
            assert state['reviews'] == [] and state['confirmation'] is None
            assert state['production_authorized'] is False and flow.writer.calls == 0
            print(json.dumps(dict(database_unchanged=True, production_authorized=False, writer_calls=0)))
        finally:
            server.should_exit = True
            thread.join(timeout=10)
    assert not directory.exists(), 'Temporary demo data not removed on shutdown'


if __name__ == '__main__':
    main()
