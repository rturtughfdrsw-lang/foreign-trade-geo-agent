"""Public demo boundaries use synthetic data, temporary databases and no network."""
import hashlib
import os
from pathlib import Path
import secrets
import socket
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from foreign_trade_geo_agent.web.render_demo import create_demo_app


class RenderDemoTests(unittest.TestCase):
    def setUp(self):
        self.password = secrets.token_urlsafe(32)
        self.env = dict(DEMO_USERNAME='demo-test', DEMO_PASSWORD=self.password,
                        RENDER_EXTERNAL_HOSTNAME='demo-test.onrender.com')
        self.enterContext(patch.dict(os.environ, self.env, clear=True))
        connect = socket.socket.connect
        def local_only(sock, address):
            # Windows asyncio creates a loopback socket pair for its event loop.
            if isinstance(address, tuple) and address[0] in {'127.0.0.1', '::1'}:
                return connect(sock, address)
            raise AssertionError('NETWORK_FORBIDDEN')
        self.enterContext(patch('socket.socket.connect', local_only))
        self.app = create_demo_app()
        self.client = self.enterContext(TestClient(self.app, base_url='https://demo-test.onrender.com'))
        self.auth = (self.env['DEMO_USERNAME'], self.password)

    def test_missing_or_weak_credentials_fail_closed(self):
        for values in ({}, {'DEMO_USERNAME': 'demo', 'DEMO_PASSWORD': 'short'}):
            with self.subTest(values=list(values)), patch.dict(os.environ, values, clear=True):
                with self.assertRaisesRegex(ValueError, 'DEMO_AUTH_CONFIGURATION_REQUIRED'):
                    create_demo_app()

    def test_health_only_is_public_and_business_routes_require_auth(self):
        health = self.client.get('/healthz')
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json(), {'status': 'ok'})
        self.assertEqual(self.client.get('http://demo-test.onrender.com/healthz').status_code, 200)
        for path in ('/', '/status', '/runs/missing', '/docs', '/openapi.json', '/.env', '/healthz/extra'):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 401)
                self.assertIn('Basic', response.headers['www-authenticate'])
                self.assertEqual(response.headers['cache-control'], 'no-store')
        self.assertEqual(self.client.get('/', auth=('wrong', self.password)).status_code, 401)
        self.assertEqual(self.client.get('/', headers={'Authorization': 'Basic %%%'}).status_code, 401)

    def test_chinese_demo_is_readonly_and_does_not_expose_internal_configuration(self):
        page = self.client.get('/', auth=self.auth)
        self.assertEqual(page.status_code, 200)
        self.assertIn('只读演示', page.text)
        self.assertIn('重启', page.text)
        self.assertNotIn('<form', page.text)
        status = self.client.get('/status', auth=self.auth).json()
        self.assertFalse(status['production_authorized'])
        self.assertEqual(status['data_kind'], 'SYNTHETIC')
        self.assertFalse(status['live_model_enabled'])
        self.assertNotIn('writer', status)
        self.assertNotIn(self.password, page.text)
        flow = self.app.state.workflow
        run = flow.store.list_runs()[0]
        detail = self.client.get('/runs/'+run, auth=self.auth)
        self.assertEqual(detail.status_code, 200)
        self.assertIn('这篇文章要回答什么问题', detail.text)
        self.assertIn('disabled', detail.text)
        self.assertEqual(flow.store.read(run)['reviews'], [])
        self.assertIsNone(flow.store.read(run)['confirmation'])
        self.assertEqual(flow.writer.calls, 0)

    def test_all_mutations_are_denied_without_changing_demo_databases(self):
        folder = Path(self.app.state.data_dir)
        before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.glob('*.sqlite3')}
        run = self.app.state.workflow.store.list_runs()[0]
        for path in ('/analyze', '/runs/'+run+'/review', '/runs/'+run+'/confirm',
                     '/runs/'+run+'/generate', '/runs/'+run+'/feedback', '/status', '/healthz'):
            for method in ('POST', 'PUT', 'PATCH', 'DELETE'):
                self.assertEqual(self.client.request(method, path, auth=self.auth).status_code, 403)
        after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.glob('*.sqlite3')}
        self.assertEqual(before, after)

    def test_host_https_files_and_errors_fail_closed(self):
        self.assertEqual(self.client.get('/', auth=self.auth, headers={'host': 'evil.example'}).status_code, 400)
        self.assertEqual(self.client.get('http://demo-test.onrender.com/', auth=self.auth).status_code, 400)
        for path in ('/.env', '/docs', '/openapi.json', '/debug', '/.git/config'):
            self.assertEqual(self.client.get(path, auth=self.auth).status_code, 404)
        with patch.object(self.app.state.workflow.store, 'list_runs', side_effect=RuntimeError(self.password)):
            response = self.client.get('/', auth=self.auth)
        self.assertEqual(response.status_code, 500)
        self.assertNotIn(self.password, response.text)

    def test_fresh_start_has_distinct_temporary_data_and_no_real_credentials(self):
        first = self.app.state.data_dir
        with patch.dict(os.environ, {'PREVIEW_DATA_DIR': '/formal/database', 'DEEPSEEK_API_KEY': 'unused-test-marker'}):
            second = create_demo_app()
            with TestClient(second, base_url='https://demo-test.onrender.com'):
                self.assertNotEqual(first, second.state.data_dir)
                self.assertEqual(second.state.workflow.writer.policy()['model'], 'FAKE')
                self.assertFalse(second.state.workflow.analyzer.config.enabled)
                self.assertEqual(len(second.state.workflow.store.list_runs()), 1)
            self.assertFalse(Path(second.state.data_dir).exists())

    def test_failed_auth_is_rate_limited(self):
        for _ in range(20):
            self.client.get('/', auth=('bad', 'bad'))
        self.assertEqual(self.client.get('/', auth=('bad', 'bad')).status_code, 429)
        self.assertEqual(self.client.get('/', auth=self.auth).status_code, 200)


if __name__ == '__main__':
    unittest.main()
