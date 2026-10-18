"""Authenticated, read-only public demo; no local data or live configuration."""
import base64
import binascii
from collections import deque
from contextlib import asynccontextmanager
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
from tempfile import TemporaryDirectory
import time

from fastapi import FastAPI
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import JSONResponse

from foreign_trade_geo_agent.commercial_preview_runtime import build_preview_runtime, ORIGIN, FIXTURES
from foreign_trade_geo_agent.core.commercial_preview import digest
from foreign_trade_geo_agent.web.commercial_preview import create_preview_app
from foreign_trade_geo_agent.web.commercial_demo_ui import CSP


HEADERS = {'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
           'Referrer-Policy': 'same-origin', 'X-Robots-Tag': 'noindex, nofollow',
           'Strict-Transport-Security': 'max-age=31536000',
           'Content-Security-Policy': CSP}


class DemoBoundary:
    """Applies to every route, including errors, unknown paths and future APIs."""
    def __init__(self, app, username, password):
        self.app = app
        self.expected = hashlib.sha256((username+':'+password).encode('utf-8')).digest()
        self.failures = deque(maxlen=20)

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'websocket':
            await send({'type': 'websocket.close', 'code': 1008})
            return
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)

        async def response(code, message, extra=None):
            await JSONResponse({'detail': message}, status_code=code,
                               headers={**HEADERS, **(extra or {})})(scope, receive, send)

        # Render terminates TLS and uvicorn processes its forwarded scheme.
        host = dict(scope['headers']).get(b'host', b'').split(b':')[0]
        health = scope['path'] == '/healthz' and scope['method'] in {'GET', 'HEAD'}
        if not health and scope['scheme'] != 'https' and host not in {b'localhost', b'127.0.0.1'}:
            return await response(400, 'HTTPS_REQUIRED')
        if not health:
            credentials = [v for k, v in scope['headers'] if k == b'authorization']
            decoded = b''
            if len(credentials) == 1 and len(credentials[0]) <= 1024:
                scheme, _, value = credentials[0].partition(b' ')
                if scheme.lower() == b'basic':
                    try:
                        decoded = base64.b64decode(value, validate=True)
                    except (ValueError, binascii.Error):
                        pass
            if not hmac.compare_digest(hashlib.sha256(decoded).digest(), self.expected):
                now = time.monotonic()
                while self.failures and self.failures[0] <= now-60:
                    self.failures.popleft()
                if len(self.failures) == 20:
                    return await response(429, 'RETRY_LATER', {'Retry-After': '60'})
                self.failures.append(now)
                return await response(401, 'AUTHENTICATION_REQUIRED',
                                      {'WWW-Authenticate': 'Basic realm="SEO Demo", charset="UTF-8"'})
        if scope['method'] not in {'GET', 'HEAD'}:
            return await response(403, 'READ_ONLY_DEMO')
        started = False

        async def safe_send(message):
            nonlocal started
            if message['type'] == 'http.response.start':
                started = True
                keys = {k.lower().encode() for k in HEADERS}
                message['headers'] = [(k, v) for k, v in message.get('headers', []) if k.lower() not in keys]
                message['headers'] += [(k.lower().encode(), v.encode()) for k, v in HEADERS.items()]
            await send(message)
        try:
            await self.app(scope, receive, safe_send)
        except Exception:
            # Never pass arbitrary exception text or secret-bearing tracebacks to logs.
            if not started:
                await response(500, 'DEMO_REQUEST_FAILED')


async def seed_demo(flow):
    state = await flow.analyze(ORIGIN+'/')
    def binding():
        return state['run_id'], state['revision'], digest(state)
    state = flow.confirm_task(*binding(), title='Aster Stainless Steel Enclosures: A Factual Overview',
        reader_question='What does Aster supply and what must a buyer confirm?',
        required_facts=('Describe the enclosure product.', 'Describe the fabrication capability.'),
        scope='Aster stainless steel enclosure fabrication for reviewed industrial equipment drawings.',
        limitations='Project-specific suitability, ratings and delivery must be separately confirmed.')
    for key, content in json.loads((FIXTURES/'demo_evidence.json').read_text(encoding='utf-8')).items():
        state = flow.supplement(*binding(), obligation_id=key, content=content,
                               label='SYNTHETIC DEMO', locator='fixture://'+key)
    # No reviews, execution confirmations, generation or delivery are seeded.


def create_demo_app():
    username, password = os.environ.get('DEMO_USERNAME', ''), os.environ.get('DEMO_PASSWORD', '')
    if (not re.fullmatch(r'[A-Za-z0-9_.-]{3,64}', username)
            or not 24 <= len(password) <= 128 or not password.isascii()
            or any(ord(c) < 33 or ord(c) > 126 for c in password)):
        raise ValueError('DEMO_AUTH_CONFIGURATION_REQUIRED')
    hostname = os.environ.get('RENDER_EXTERNAL_HOSTNAME', '')
    if hostname and not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,62}\.onrender\.com', hostname):
        raise ValueError('DEMO_HOST_CONFIGURATION_INVALID')
    if os.environ.get('RENDER') and not hostname:
        raise ValueError('DEMO_HOST_CONFIGURATION_REQUIRED')
    allowed = ['localhost', '127.0.0.1'] + ([hostname] if hostname else [])

    @asynccontextmanager
    async def lifespan(app):
        # A fresh directory on every process start. No configurable database path.
        with TemporaryDirectory(prefix='seo-render-demo-') as directory:
            flow = build_preview_runtime(Path(directory))
            await seed_demo(flow)
            app.state.workflow, app.state.data_dir = flow, directory
            preview = create_preview_app(flow, allowed_hosts=allowed, read_only=True)
            app.mount('/', preview)
            async with preview.router.lifespan_context(preview):
                yield

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

    @app.api_route('/healthz', methods=['GET', 'HEAD'])
    async def health():
        return {'status': 'ok'}

    @app.get('/status')
    async def status():
        return dict(profile='RENDER_READ_ONLY_DEMO', data_kind='SYNTHETIC',
                    production_authorized=False, live_model_enabled=False, persistent=False)

    app.add_middleware(DemoBoundary, username=username, password=password)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed)
    return app
