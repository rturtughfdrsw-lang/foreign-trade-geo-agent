"""Actual HTTP route -> frozen server permit -> transport -> native Draft -> SQLite."""
from datetime import UTC, datetime, timedelta
import html
import json
import re
import time
import unittest
from unittest.mock import patch

import httpx

from tests import test_web_mvp as base
from scripts.web_generation_demo import build_mock_executor
from foreign_trade_geo_agent.storage.web_experiment import WebExperimentLedger
from foreign_trade_geo_agent.web.experiment import freeze, FrozenWebExecutor, FrozenWebGeneration


class FrozenWebTests(unittest.TestCase):
    setUpClass = classmethod(base.MVPWebTests.setUpClass.__func__)
    setUp = base.MVPWebTests.setUp
    form = base.MVPWebTests.form

    def configure(self, handler=None, *, expiry=None):
        from scripts.demo_seo_e_only import DOCUMENT
        self.service = self.app.state.mvp_service
        from tests.scope_fixtures import ExplicitTestScopeReviewer
        self.service.scope_reviewer = ExplicitTestScopeReviewer()
        self.service.generation_executor = build_mock_executor(self.package)
        self.client.post('/mvp/evidence', data={**self.form(), 'content': DOCUMENT, 'source_label': 'Frozen E1'})
        self.client.post('/mvp/recheck', data=self.form())
        self.bundle = freeze(self.service)
        self.ledger = WebExperimentLedger(self.root / 'fixed-server-ledger.sqlite3')
        self.ledger.initialize()
        self.expiry = expiry or datetime.now(UTC) + timedelta(minutes=5)
        manifest = json.loads((self.package / 'web-experiment/bundle.json').read_bytes())
        self.request_sha = manifest['request_sha256']
        self.ledger.issue('WEB-TEST-MOCK', self.bundle, self.package, self.request_sha, 'MOCK', self.expiry)
        fixture = (self.package / 'candidate/04-writer-output.json').read_text(encoding='utf-8')
        async def respond(request):
            import asyncio
            await asyncio.sleep(.08)
            self.assertIsNotNone(self.ledger.read('WEB-TEST-MOCK')[7])
            self.assertEqual(request.content, (self.package / 'web-experiment/request.json').read_bytes())
            if handler:
                response = handler(request)
                if asyncio.iscoroutine(response):
                    response = await response
                return response
            return httpx.Response(200, json={'model': 'deepseek-flash', 'usage': {'total_tokens': 321},
                'choices': [{'message': {'content': fixture}, 'finish_reason': 'stop'}]})
        self.executor = FrozenWebExecutor(self.package, self.bundle, self.ledger, 'WEB-TEST-MOCK',
                                          transport=httpx.MockTransport(respond))
        self.service.generation_executor = self.executor
        self.service.generation = FrozenWebGeneration(self.service)

    def generation_form(self):
        page = self.client.get('/mvp/generate')
        return {n: html.unescape(re.search(r'name="' + n + r'" value="([^"]*)"', page.text).group(1))
                for n in ('csrf_token', 'binding_sha256')}

    def finish(self):
        for _ in range(100):
            page = self.client.get('/mvp/generate')
            if 'data-generation-state="RUNNING"' not in page.text:
                return page
            time.sleep(.03)
        self.fail('generation did not finish')

    def test_success_exact_bytes_durable_claim_native_sqlite_and_web_article(self):
        self.configure()
        with patch('httpx.AsyncHTTPTransport', side_effect=AssertionError('REAL HTTP FORBIDDEN')):
            form = self.generation_form()
            self.client.post('/mvp/generate', data=form)
            page = self.finish()
        self.assertIn('data-generation-state="SUCCEEDED"', page.text)
        self.assertIn('模拟数值，非计费记录', page.text)
        self.assertIn('321', page.text)
        article = self.client.get('/mvp/article')
        self.assertIn('E1 → CL3', article.text)
        self.assertTrue(self.service.article()['generated_from_web'])
        self.assertEqual(self.executor.calls, 1)
        self.assertTrue(self.service.article()['version_matches'])
        from foreign_trade_geo_agent.storage.sqlite import SQLiteHistoryReader
        path, result = self.service.generation.selected()
        reader = SQLiteHistoryReader(path)
        self.assertEqual(reader.get_run(result['run_id']).workflow_name, FrozenWebGeneration.workflow_name)
        from foreign_trade_geo_agent.storage.sqlite import SQLiteHistoryStore
        self.assertEqual(SQLiteHistoryStore(path).list_wordpress_attempts(result['run_id']), ())
        self.client.post('/mvp/generate', data=form)
        self.assertEqual(self.executor.calls, 1)

    def test_validator_rejection_retains_raw_candidate_usage_diagnostics(self):
        self.configure(lambda r: httpx.Response(200, json={'model': 'deepseek-flash', 'usage': {'total_tokens': 12},
            'choices': [{'message': {'content': '{bad'}, 'finish_reason': 'stop'}]}))
        self.client.post('/mvp/generate', data=self.generation_form())
        self.assertIn('VALIDATION_FAILED', self.finish().text)
        output = self.package / 'generation' / self.bundle
        self.assertEqual((output / 'rejected-candidate.txt').read_bytes(), b'{bad')
        self.assertTrue((output / 'response-body.bin').exists())
        self.assertEqual(json.loads((output / 'result.json').read_bytes())['usage'], {'total_tokens': 12})

    def test_scope_review_revoked_during_await_consumes_permit_without_selecting_candidate(self):
        def revoke(request):
            self.service.scope_reviewer = None
            fixture = (self.package / 'candidate/04-writer-output.json').read_text(encoding='utf-8')
            return httpx.Response(200, json={'model':'deepseek-flash', 'choices':[
                {'message':{'content':fixture}, 'finish_reason':'stop'}]})
        self.configure(revoke)
        self.client.post('/mvp/generate', data=self.generation_form())
        self.finish()
        self.assertEqual(self.executor.calls, 1)
        self.assertIsNotNone(self.ledger.read('WEB-TEST-MOCK')[7])
        self.assertFalse((self.package / 'generation/selected.json').exists())
        self.assertFalse(list(self.package.glob('generation/*/history.sqlite3')))
        result = json.loads((self.package / 'generation' / self.bundle / 'result.json').read_bytes())
        self.assertEqual(result['state'], 'INCOMPLETE')
        self.assertFalse(self.service.generation.view()['generation_allowed'])
        self.assertIsNone(self.service.generation.selected())

    def test_http_failure_retained_and_never_retried(self):
        self.configure(lambda r: httpx.Response(503, json={'error': 'offline fixture'}))
        form = self.generation_form()
        self.client.post('/mvp/generate', data=form)
        self.assertIn('REQUEST_FAILED', self.finish().text)
        self.assertTrue((self.package / 'generation' / self.bundle / 'response-body.bin').exists())
        self.client.post('/mvp/generate', data=form)
        self.assertEqual(self.executor.calls, 1)

    def test_timeout_is_unknown_and_restart_never_retries(self):
        def timeout(request):
            raise httpx.ReadTimeout('secret detail', request=request)
        self.configure(timeout)
        form = self.generation_form()
        self.client.post('/mvp/generate', data=form)
        page = self.finish()
        self.assertIn('data-generation-state="UNKNOWN"', page.text)
        self.assertNotIn('secret detail', page.text)
        self.service.generation = FrozenWebGeneration(self.service)
        self.client.post('/mvp/generate', data=form)
        self.assertEqual(self.executor.calls, 1)

    def test_missing_usage_does_not_invent_tokens(self):
        self.configure(lambda r: httpx.Response(200, json={'model': 'deepseek-flash', 'choices': [
            {'message': {'content': (self.package / 'candidate/04-writer-output.json').read_text(encoding='utf-8')},
             'finish_reason': 'stop'}]}))
        self.client.post('/mvp/generate', data=self.generation_form())
        page = self.finish()
        self.assertIn('SUCCEEDED', page.text)
        self.assertIn('未返回 usage', page.text)

    def test_concurrent_posts_and_independent_services_share_single_claim(self):
        import concurrent.futures
        self.configure()
        form = self.generation_form()
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _: self.client.post('/mvp/generate', data=form), range(4)))
        self.assertIn('SUCCEEDED', self.finish().text)
        self.assertEqual(self.executor.calls, 1)
        from scripts.web_deepseek_experiment import compose
        from fastapi.testclient import TestClient
        app = compose(self.package, self.bundle, self.ledger, 'WEB-TEST-MOCK', transport=self.executor.transport,
                      scope_reviewer=self.service.scope_reviewer)
        with TestClient(app, base_url='http://127.0.0.1') as client:
            token = re.search(r'name="csrf_token" value="([^"]*)"', client.get('/mvp/evidence').text).group(1)
            client.post('/mvp/generate', data={'csrf_token': token, 'binding_sha256': self.bundle})
            self.assertEqual(app.state.mvp_service.generation_executor.calls, 0)

    def test_stale_evidence_and_no_browser_mint_or_renew(self):
        self.configure()
        form = self.generation_form()
        for field in ('live', 'expires_at', 'permit', 'journal', 'model', 'request_sha256'):
            self.assertEqual(self.client.post('/mvp/generate', data={**form, field: 'forged'}).status_code, 422)
        self.client.post('/mvp/evidence', data={**self.form(), 'content': 'new version', 'source_label': 'changed'})
        self.assertEqual(self.client.post('/mvp/generate', data=form).status_code, 409)
        self.assertIsNone(self.ledger.read('WEB-TEST-MOCK')[7])
        self.assertEqual(self.executor.calls, 0)

    def test_result_retention_failure_is_incomplete_and_consumed(self):
        self.configure()
        original = __import__('foreign_trade_geo_agent.web.generation', fromlist=['save_bytes']).save_bytes
        def fail(path, raw):
            if path.name == 'result.json':
                raise OSError('private storage details')
            original(path, raw)
        form = self.generation_form()
        with patch('foreign_trade_geo_agent.web.generation.save_bytes', new=fail):
            self.client.post('/mvp/generate', data=form)
            self.assertIn('UNKNOWN', self.finish().text)
        self.client.post('/mvp/generate', data=form)
        self.assertEqual(self.executor.calls, 1)
        self.assertIsNone(self.service.generation.selected())
        output = self.package / 'generation' / self.bundle
        self.assertTrue((output / 'response-body.bin').exists())
        self.assertTrue((output / 'model-output.txt').exists())

    def test_expired_permit_code_request_and_plan_tampering_fail_closed(self):
        self.configure()
        form = self.generation_form()
        with patch('foreign_trade_geo_agent.web.experiment.code_hashes', return_value={}):
            self.assertEqual(self.client.post('/mvp/generate', data=form).status_code, 409)
        request = self.package / 'web-experiment/request.json'
        raw = request.read_bytes()
        request.write_bytes(raw + b' ')
        self.assertEqual(self.client.post('/mvp/generate', data=form).status_code, 409)
        request.write_bytes(raw)
        with patch('foreign_trade_geo_agent.storage.web_experiment.datetime') as clock:
            clock.now.return_value = self.expiry + timedelta(seconds=1)
            clock.fromisoformat.side_effect = datetime.fromisoformat
            self.assertEqual(self.client.post('/mvp/generate', data=form).status_code, 409)
        self.assertEqual(self.executor.calls, 0)
        self.assertIsNone(self.ledger.read('WEB-TEST-MOCK')[7])

    def test_claim_without_output_survives_restart_and_journal_copy_cannot_reuse(self):
        import shutil
        self.configure()
        form = self.generation_form()
        self.ledger.claim('WEB-TEST-MOCK', self.bundle, self.package, self.request_sha, 'MOCK')
        self.service.generation = FrozenWebGeneration(self.service)
        self.assertIn('UNKNOWN', self.client.get('/mvp/generate').text)
        self.client.post('/mvp/generate', data=form)
        self.assertEqual(self.executor.calls, 0)
        clone = self.root / 'other-journal-package'
        shutil.copytree(self.package, clone)
        with self.assertRaises(ValueError):
            self.ledger.validate('WEB-TEST-MOCK', self.bundle, clone, self.request_sha, 'MOCK')
        import sqlite3
        with self.assertRaises(sqlite3.IntegrityError):
            self.ledger.issue('WEB-TEST-NEW-ID', self.bundle, clone, self.request_sha, 'MOCK', self.expiry)

    def test_failed_claim_commit_and_missing_ledger_never_reach_transport(self):
        self.configure()
        form = self.generation_form()
        with patch.object(self.ledger, 'claim', side_effect=OSError('private disk error')):
            self.assertEqual(self.client.post('/mvp/generate', data=form).status_code, 409)
        self.assertEqual(self.executor.calls, 0)
        self.assertFalse((self.package / 'generation').exists())
        self.ledger.path.rename(self.root / 'unavailable-ledger.sqlite3')
        self.assertEqual(self.client.post('/mvp/generate', data=form).status_code, 409)
        self.assertEqual(self.executor.calls, 0)

    def test_task_plan_versions_and_changes_during_await_cannot_select_candidate(self):
        from dataclasses import replace
        self.configure()
        form = self.generation_form()
        session, _, store, _, _ = self.service._load()
        current = self.service._current(store, session)
        for changed in (replace(current, task=replace(current.task, task_version=2)),
                        replace(current, plan_version=current.plan_version + 1)):
            with patch.object(self.service, '_current', return_value=changed):
                # A deliberately inconsistent task can also make the error
                # page unavailable (503). Assert the actual admission error.
                from foreign_trade_geo_agent.web.mvp_application import MVPError
                with self.assertRaises(MVPError) as rejected:
                    self.service.generation.start(form['binding_sha256'], self.service.generation_ticket)
                self.assertEqual(rejected.exception.status, 409)
        self.assertEqual(self.executor.calls, 0)
        import asyncio
        import threading
        entered, release = threading.Event(), threading.Event()
        async def response(request):
            entered.set()
            while not release.is_set():
                await asyncio.sleep(.01)
            return httpx.Response(200, json={'model': 'deepseek-flash', 'choices': [{'message': {
                'content': (self.package / 'candidate/04-writer-output.json').read_text(encoding='utf-8')},
                'finish_reason': 'stop'}]})
        self.executor.transport = httpx.MockTransport(response)
        self.client.post('/mvp/generate', data=form)
        self.assertTrue(entered.wait(2))
        self.client.post('/mvp/evidence', data={**self.form(), 'content': 'changed during await', 'source_label': 'new'})
        release.set()
        output = self.package / 'generation' / self.bundle
        for _ in range(100):
            if (output / 'result.json').exists():
                break
            time.sleep(.02)
        self.assertEqual(json.loads((output / 'result.json').read_bytes())['state'], 'INCOMPLETE')
        self.assertFalse((self.package / 'generation/selected.json').exists())

    def test_live_branch_is_offline_simulated_and_credentials_transport_follow_claim(self):
        self.configure()
        ledger = WebExperimentLedger(self.root / 'simulated-live-ledger.sqlite3')
        ledger.initialize()
        ledger.issue('WEB-TEST-SIMULATED-LIVE', self.bundle, self.package, self.request_sha, 'LIVE', self.expiry)
        mock_transport = self.executor.transport
        # Existing respond closure asserts the Mock ledger claim; replace with
        # an independent handler that checks the simulated LIVE ledger instead.
        fixture = (self.package / 'candidate/04-writer-output.json').read_text(encoding='utf-8')
        def transport_factory(*args, **kwargs):
            self.assertIsNotNone(ledger.read('WEB-TEST-SIMULATED-LIVE')[7])
            self.assertEqual(kwargs, {'retries': 0, 'trust_env': False})
            return httpx.MockTransport(lambda r: httpx.Response(200, json={'model': 'deepseek-flash',
                'choices': [{'message': {'content': fixture}, 'finish_reason': 'stop'}]}))
        self.service.generation_executor = FrozenWebExecutor(self.package, self.bundle, ledger, 'WEB-TEST-SIMULATED-LIVE')
        import os
        with patch('scripts.local_env.load_api_keys') as keys, patch.dict(os.environ, {'DEEPSEEK_API_KEY': 'OFFLINE-SIMULATION'}), \
                patch('httpx.AsyncHTTPTransport', side_effect=transport_factory) as transport:
            self.assertFalse(keys.called)
            self.client.post('/mvp/generate', data=self.generation_form())
            self.assertIn('SUCCEEDED', self.finish().text)
            keys.assert_called_once()
            transport.assert_called_once()
            page = self.client.get('/mvp/article')
            self.assertIn('独立单次 DeepSeek 实验候选', page.text)
            self.assertNotIn('无真实模型请求。', page.text)


class LedgerProcessTests(unittest.TestCase):
    def test_independent_processes_one_claim_even_with_different_journal_names(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        import subprocess
        import sys
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            ledger = WebExperimentLedger(root / 'server.sqlite3')
            ledger.initialize()
            ledger.issue('WEB-TEST-PROCESS', 'a'*64, root, 'b'*64, 'MOCK', datetime.now(UTC) + timedelta(minutes=5))
            program = """
import sys
from foreign_trade_geo_agent.storage.web_experiment import WebExperimentLedger
try:
    WebExperimentLedger(sys.argv[1]).claim('WEB-TEST-PROCESS', 'a'*64, sys.argv[2], 'b'*64, 'MOCK')
    print('CLAIMED')
except ValueError:
    print('REJECTED')
"""
            processes = [subprocess.Popen([sys.executable, '-c', program, str(ledger.path), str(root), journal],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for journal in ('journal-a', 'journal-b')]
            results = [p.communicate(timeout=15) for p in processes]
            self.assertEqual(sorted(out.strip() for out, err in results), ['CLAIMED', 'REJECTED'])
            self.assertTrue(all(not err for out, err in results))
