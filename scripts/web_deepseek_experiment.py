"""Operator-only frozen Web launcher. Default/preparation never loads credentials.

Future live arming requires NEW explicit human authorization in chat for the
bundle, permit ID and expiry. Never use an old CLI/P1 authorization here.
"""
import argparse
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path

import uvicorn

from scripts.web_generation_demo import build_mock_executor
from foreign_trade_geo_agent.storage.web_experiment import WebExperimentLedger
from foreign_trade_geo_agent.web.app import create_app
from foreign_trade_geo_agent.web.experiment import FrozenWebExecutor, FrozenWebGeneration, freeze
from foreign_trade_geo_agent.web.generation import check, read_json


def live_ledger():
    # Fixed across packages, journals, server restarts and ports. No CLI override.
    base = Path(os.environ['LOCALAPPDATA']) if os.name == 'nt' else Path.home() / '.local/share'
    return WebExperimentLedger(base / 'foreign-trade-geo-agent/web-experiment/permits.sqlite3')


def compose(directory, bundle, ledger, permit, *, transport=None, scope_reviewer=None):
    app = create_app(mvp_dir=directory, db_path=directory / 'demo.sqlite3', live_db_path=directory / 'live.sqlite3')
    service = app.state.mvp_service
    service.scope_reviewer = scope_reviewer
    service.generation_executor = FrozenWebExecutor(directory, bundle, ledger, permit, transport=transport)
    service.generation = FrozenWebGeneration(service)
    # Validate exact current graph and fixed server-side permit before serving.
    service.generation._prepare()
    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['freeze', 'arm-live', 'serve-live'])
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--bundle-sha256')
    parser.add_argument('--permit-id')
    parser.add_argument('--expires-at')
    parser.add_argument('--port', type=int, default=8011)
    args = parser.parse_args()
    directory = args.directory.resolve()
    if args.action == 'freeze':
        check(args.bundle_sha256 is None and args.permit_id is None and args.expires_at is None,
              'FREEZE_IS_NOT_AUTHORIZATION')
        app = create_app(mvp_dir=directory, db_path=directory / 'demo.sqlite3', live_db_path=directory / 'live.sqlite3')
        app.state.mvp_service.generation_executor = build_mock_executor(directory)
        print(json.dumps({'bundle_sha256': freeze(app.state.mvp_service), 'real_requests': 0}))
        return
    check(args.bundle_sha256 and args.permit_id, 'NEW_EXPLICIT_AUTHORIZATION_REQUIRED')
    check(args.permit_id.startswith('WEB-TEST-') and len(args.permit_id) <= 100, 'PERMIT_INVALID')
    ledger = live_ledger()
    if args.action == 'arm-live':
        expiry = datetime.fromisoformat(args.expires_at)
        check(expiry.tzinfo is not None and datetime.now(UTC) < expiry <= datetime.now(UTC) + timedelta(hours=1),
              'EXPIRY_MUST_BE_WITHIN_ONE_HOUR')
        # Validate before minting. No credentials/HTTP here.
        from foreign_trade_geo_agent.web.experiment import code_hashes
        from foreign_trade_geo_agent.web.generation import digest
        root = directory / 'web-experiment'
        manifest_raw = (root / 'bundle.json').read_bytes()
        manifest = json.loads(manifest_raw)
        check(digest(manifest_raw) == args.bundle_sha256 and manifest['code'] == code_hashes(), 'BUNDLE_CHANGED')
        check(all(Path(n).name == n and digest((root / n).read_bytes()) == h
                  for n, h in manifest['files'].items()), 'FROZEN_INPUT_CHANGED')
        ledger.initialize()
        from foreign_trade_geo_agent.adapters.retained_deepseek import restrict_directory
        restrict_directory(ledger.path.parent)
        ledger.issue(args.permit_id, args.bundle_sha256, directory, manifest['request_sha256'], 'LIVE', expiry)
        print('TEST-only permit armed; no model request. Use serve-live, then click once in Web.')
    else:
        check(args.expires_at is None, 'SERVER_CANNOT_RENEW_PERMIT')
        app = compose(directory, args.bundle_sha256, ledger, args.permit_id)
        uvicorn.run(app, host='127.0.0.1', port=args.port)


if __name__ == '__main__':
    main()
