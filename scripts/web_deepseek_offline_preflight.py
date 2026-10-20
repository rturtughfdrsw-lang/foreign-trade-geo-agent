"""Offline-only browser acceptance launcher, never accepts a LIVE mode or key."""
import argparse
import asyncio
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from uuid import uuid4

import httpx
import uvicorn

from scripts.prepare_web_mvp import prepare
from scripts.demo_seo_e_only import DOCUMENT
from scripts.web_generation_demo import build_mock_executor
from scripts.web_deepseek_experiment import compose
from foreign_trade_geo_agent.storage.web_experiment import WebExperimentLedger
from foreign_trade_geo_agent.web.app import create_app
from foreign_trade_geo_agent.web.experiment import freeze


def setup(directory):
    prepare(directory)
    app = create_app(mvp_dir=directory, db_path=directory / 'demo.sqlite3', live_db_path=directory / 'live.sqlite3')
    service = app.state.mvp_service
    service.generation_executor = build_mock_executor(directory)
    service.submit(expected_sha256=service.evidence()['expected_sha256'], content=DOCUMENT, source_label='Frozen Web E1')
    asyncio.run(service.recheck(expected_sha256=service.evidence()['expected_sha256']))
    bundle = freeze(service)
    manifest = json.loads((directory / 'web-experiment/bundle.json').read_bytes())
    ledger = WebExperimentLedger(directory.parent / 'offline-permits.sqlite3')
    ledger.initialize()
    permit = 'WEB-TEST-MOCK-' + uuid4().hex
    ledger.issue(permit, bundle, directory, manifest['request_sha256'], 'MOCK', datetime.now(UTC) + timedelta(hours=1))
    (directory / 'offline-permit.json').write_text(json.dumps({'bundle': bundle, 'permit': permit}), encoding='utf-8')


def build(directory, scenario):
    config = json.loads((directory / 'offline-permit.json').read_bytes())
    ledger = WebExperimentLedger(directory.parent / 'offline-permits.sqlite3')
    fixture = (directory / 'candidate/04-writer-output.json').read_text(encoding='utf-8')

    async def respond(request):
        assert ledger.read(config['permit'])[7] is not None
        assert request.content == (directory / 'web-experiment/request.json').read_bytes()
        await asyncio.sleep(4 if scenario in {'duplicate', 'disconnect'} else .2)
        if scenario == 'timeout':
            raise httpx.ReadTimeout('OFFLINE fixture timeout', request=request)
        if scenario == 'disconnect':
            raise httpx.ReadError('OFFLINE fixture disconnect', request=request)
        if scenario == 'http':
            return httpx.Response(503, json={'error': 'OFFLINE fixture HTTP failure'})
        body = {'model': 'deepseek-flash', 'choices': [{'message': {
            'content': '{invalid candidate' if scenario == 'validator' else fixture}, 'finish_reason': 'stop'}]}
        if scenario != 'no-usage':
            body['usage'] = {'prompt_tokens': 1500, 'completion_tokens': 1100, 'total_tokens': 2600}
        return httpx.Response(200, json=body)

    app = compose(directory, config['bundle'], ledger, config['permit'], transport=httpx.MockTransport(respond))
    # Acceptance harness only: lets the browser deliberately replay the same
    # POST after restart, using the new process's CSRF. No permit is minted.
    from fastapi.responses import HTMLResponse
    @app.get('/offline-replay', response_class=HTMLResponse)
    def replay():
        import html
        return '<h1>OFFLINE duplicate replay harness</h1><form method="post" action="/mvp/generate">' \
            + '<input type="hidden" name="csrf_token" value="' + html.escape(app.state.csrf_token) + '">' \
            + '<input type="hidden" name="binding_sha256" value="' + config['bundle'] + '">' \
            + '<button type="submit">重提同一冻结请求（Mock）</button></form>'
    if scenario == 'persistence':
        from foreign_trade_geo_agent.web import generation
        original = generation.save_bytes
        def fail_result(path, raw):
            if path.name == 'result.json':
                raise OSError('OFFLINE fixture retention failure')
            original(path, raw)
        generation.save_bytes = fail_result
    # No external socket is permitted even if an unintended code path is reached.
    import socket
    original_connect = socket.socket.connect
    def loopback_only(sock, address):
        import ipaddress
        if not isinstance(address, tuple) or not ipaddress.ip_address(address[0]).is_loopback:
            raise AssertionError('EXTERNAL NETWORK FORBIDDEN')
        return original_connect(sock, address)
    socket.socket.connect = loopback_only
    def forbid_live(*args, **kwargs):
        raise AssertionError('LIVE TRANSPORT FORBIDDEN')
    httpx.AsyncHTTPTransport = forbid_live
    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--scenario', choices=['success', 'validator', 'http', 'timeout', 'no-usage',
                                               'duplicate', 'disconnect', 'stale', 'persistence'], required=True)
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    directory = args.directory.resolve()
    if not args.resume:
        setup(directory)
    uvicorn.run(build(directory, args.scenario), host='127.0.0.1', port=args.port)


if __name__ == '__main__':
    main()
