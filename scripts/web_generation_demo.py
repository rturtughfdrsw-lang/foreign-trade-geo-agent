"""Explicit offline composition; ONLY MockTransport, no credentials/live flags."""
import argparse
import asyncio
import json
from pathlib import Path

import httpx
import uvicorn

from scripts.prepare_web_mvp import prepare
from foreign_trade_geo_agent.core.content_draft import ContentDraftInput
from foreign_trade_geo_agent.storage.serialization import _decode
from foreign_trade_geo_agent.storage.evidence_intake import SQLiteEvidenceIntakeStore
from foreign_trade_geo_agent.web.app import create_app
from foreign_trade_geo_agent.web.generation import MockArticleExecutor


def build_mock_executor(directory, *, handler=None, delay=.15):
    directory = Path(directory)
    # Fixture-specific material stays in this offline launcher, outside Web's
    # generic generation logic. Future isolated fixtures can supply another profile.
    value = _decode(json.loads((directory / 'candidate/03-native-input.json').read_text(encoding='utf-8')), ContentDraftInput)
    session = json.loads((directory / 'session.json').read_text(encoding='utf-8'))
    task = SQLiteEvidenceIntakeStore(directory / 'candidate/intake.sqlite3').get_revision(
        session['project_id'], session['task_id'], 1).task

    async def respond(request):
        await asyncio.sleep(delay)
        if handler:
            response = handler(request)
            if asyncio.iscoroutine(response):
                response = await response
            return response
        fixture = json.loads((directory / 'candidate/04-writer-output.json').read_text(encoding='utf-8'))
        return httpx.Response(200, json={'model': 'deepseek-flash', 'choices': [
            {'message': {'content': json.dumps(fixture)}, 'finish_reason': 'stop'}]})
    return MockArticleExecutor(task=task, template=value, transport=httpx.MockTransport(respond))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--port', type=int, default=8010)
    args = parser.parse_args()
    if not args.directory.exists():
        prepare(args.directory)
    app = create_app(mvp_dir=args.directory, db_path=args.directory / 'demo.sqlite3',
                     live_db_path=args.directory / 'live.sqlite3')
    app.state.mvp_service.generation_executor = build_mock_executor(args.directory, delay=2)
    print(f'OFFLINE Mock Web: http://127.0.0.1:{args.port}/mvp/generate')
    uvicorn.run(app, host='127.0.0.1', port=args.port)


if __name__ == '__main__':
    main()
