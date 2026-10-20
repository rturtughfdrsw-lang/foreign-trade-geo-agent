"""Offline Web generation: native Draft, one-shot reservation and existing Review."""
import html
import re
import time
import unittest
from unittest.mock import patch

from tests import test_web_mvp as base


class WebGenerationTests(unittest.TestCase):
    setUpClass = classmethod(base.MVPWebTests.setUpClass.__func__)
    setUp = base.MVPWebTests.setUp
    form = base.MVPWebTests.form
    def test_generation_disabled_by_default_and_unknown_authority_rejected(self):
        page = self.client.get('/mvp/generate')
        self.assertEqual(page.status_code, 200)
        self.assertIn('真实 DeepSeek 调用已禁用', page.text)
        self.assertIn('未配置隔离 Mock 执行器', page.text)

    def configure(self, handler=None):
        from tests.scope_fixtures import ExplicitTestScopeReviewer
        self.app.state.mvp_service.scope_reviewer = ExplicitTestScopeReviewer()
        from scripts.web_generation_demo import build_mock_executor
        self.app.state.mvp_service.generation_executor = build_mock_executor(self.package, handler=handler)
        from scripts.demo_seo_e_only import DOCUMENT
        self.client.post('/mvp/evidence', data={**self.form(), 'content': DOCUMENT, 'source_label': 'Web E1'})
        self.client.post('/mvp/recheck', data=self.form())

    def generation_form(self):
        page = self.client.get('/mvp/generate')
        self.assertEqual(page.status_code, 200)
        return {name: html.unescape(re.search(r'name="' + name + r'" value="([^"]*)"', page.text).group(1))
                for name in ('csrf_token', 'binding_sha256')}

    def finish(self):
        for _ in range(100):
            page = self.client.get('/mvp/generate')
            if 'data-generation-state="RUNNING"' not in page.text:
                return page
            time.sleep(.02)
        self.fail('Mock generation did not finish')

    def test_new_generation_persists_recovers_citations_and_edits(self):
        self.configure()
        executor = self.app.state.mvp_service.generation_executor
        form = self.generation_form()
        with patch('httpx.AsyncHTTPTransport', side_effect=AssertionError('NO LIVE')):
            response = self.client.post('/mvp/generate', data=form)
            self.assertEqual(response.status_code, 200)
            page = self.finish()
        self.assertIn('data-generation-state="SUCCEEDED"', page.text)
        self.assertIn('未返回 usage', page.text)
        self.assertEqual(executor.calls, 1)
        self.client.post('/mvp/generate', data=form)
        self.client.get('/mvp/generate')
        self.assertEqual(executor.calls, 1)
        article = self.app.state.mvp_service.article()
        self.assertEqual(article['candidate_mode'], 'MOCK')
        self.assertTrue(article['version_matches'])
        self.assertTrue(article['generated_from_web'])
        from foreign_trade_geo_agent.web.mvp_application import MVPApplicationService
        self.assertEqual(MVPApplicationService(self.package).article()['origin_sha256'], article['origin_sha256'])
        page = self.client.get('/mvp/article')
        self.assertIn('E1 → CL3', page.text)
        fields = {n: html.unescape(re.search(r'name="' + n + r'" value="([^"]*)"', page.text).group(1))
                  for n in ('csrf_token', 'expected_version', 'origin_sha256', 'expected_evidence_sha256')}
        response = self.client.post('/mvp/article', data={**fields, 'body_text': article['local_body'] + '\n\nReview this enquiry.',
                                                       'note': 'Browser generation revision', 'status': 'LOCAL_REVIEW_COMPLETE'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('PENDING_REVALIDATION', response.text)
        self.assertEqual(self.app.state.mvp_service.article()['local_status'], 'PENDING_REVIEW')

    def test_missing_evidence_stale_and_forged_fields_never_execute(self):
        from scripts.web_generation_demo import build_mock_executor
        executor = build_mock_executor(self.package)
        self.app.state.mvp_service.generation_executor = executor
        self.assertIn('证据不足', self.client.get('/mvp/generate').text)
        token = self.form()['csrf_token']
        self.assertEqual(self.client.post('/mvp/generate', data={'csrf_token': token, 'binding_sha256': '0'*64}).status_code, 409)
        self.configure()
        executor = self.app.state.mvp_service.generation_executor
        form = self.generation_form()
        self.assertEqual(self.client.post('/mvp/generate', data={**form, 'live': 'true'}).status_code, 422)
        self.client.post('/mvp/evidence', data={**self.form(), 'content': 'changed', 'source_label': 'changed'})
        self.assertEqual(self.client.post('/mvp/generate', data=form).status_code, 409)
        self.assertEqual(executor.calls, 0)

    def test_scope_review_revoked_during_await_cannot_select_candidate(self):
        import json
        import httpx
        def revoke(request):
            self.app.state.mvp_service.scope_reviewer = None
            fixture = (self.package / 'candidate/04-writer-output.json').read_text(encoding='utf-8')
            return httpx.Response(200, json={'model':'deepseek-flash', 'choices':[
                {'message':{'content':fixture}, 'finish_reason':'stop'}]})
        self.configure(revoke)
        self.client.post('/mvp/generate', data=self.generation_form())
        self.finish()
        service = self.app.state.mvp_service
        self.assertEqual(service.generation_executor.calls, 1)
        self.assertFalse((self.package / 'generation/selected.json').exists())
        self.assertFalse(list(self.package.glob('generation/*/history.sqlite3')))
        result = json.loads(next(self.package.glob('generation/*/result.json')).read_bytes())
        self.assertNotEqual(result['state'], 'SUCCEEDED')
        self.assertFalse(service.generation.view()['generation_allowed'])

    def test_request_failure_and_validator_rejection_retain_without_success(self):
        import httpx
        for kind in ('request', 'validator'):
            with self.subTest(kind=kind):
                if kind == 'request':
                    def handler(request):
                        raise httpx.ReadTimeout('secret provider response', request=request)
                else:
                    def handler(request):
                        return httpx.Response(200, json={'model': 'deepseek-flash', 'usage': {'total_tokens': 123},
                            'choices': [{'message': {'content': '{bad candidate'}, 'finish_reason': 'stop'}]})
                self.configure(handler)
                self.client.post('/mvp/generate', data=self.generation_form())
                page = self.finish()
                self.assertIn('REQUEST_FAILED' if kind == 'request' else 'VALIDATION_FAILED', page.text)
                self.assertNotIn('secret provider response', page.text)
                self.assertEqual(self.app.state.mvp_service.generation_executor.calls, 1)
                if kind == 'validator':
                    self.assertIn('123', page.text)
                    self.assertEqual(len(list(self.package.glob('generation/*/rejected-candidate.txt'))), 1)
                # New evidence epoch is necessary even for a deliberate new Mock test.
                if kind == 'request':
                    from scripts.demo_seo_e_only import DOCUMENT
                    self.client.post('/mvp/evidence', data={**self.form(), 'content': DOCUMENT, 'source_label': 'next epoch'})
                    self.client.post('/mvp/recheck', data=self.form())

    def test_parallel_duplicate_submissions_and_restart_never_reexecute(self):
        import concurrent.futures
        import threading
        import httpx
        started, release = threading.Event(), threading.Event()
        async def handler(request):
            import asyncio
            started.set()
            while not release.is_set():
                await asyncio.sleep(.01)
            return httpx.Response(503, json={'error': 'fixture'})
        self.configure(handler)
        form = self.generation_form()
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            responses = list(pool.map(lambda _: self.client.post('/mvp/generate', data=form), range(4)))
        self.assertTrue(started.wait(2))
        self.assertTrue(all(r.status_code == 200 for r in responses))
        self.assertIn('data-generation-state="RUNNING"', self.client.get('/mvp/generate').text)
        self.assertEqual(self.app.state.mvp_service.generation_executor.calls, 1)
        release.set()
        self.assertIn('REQUEST_FAILED', self.finish().text)
        from foreign_trade_geo_agent.web.mvp_application import MVPApplicationService
        reopened = MVPApplicationService(self.package)
        reopened.generation_executor = self.app.state.mvp_service.generation_executor
        reopened.scope_reviewer = self.app.state.mvp_service.scope_reviewer
        reopened.generation.start(form['binding_sha256'], None)
        self.assertEqual(reopened.generation_executor.calls, 1)

    def test_expired_page_task_and_plan_changes_block_without_calls(self):
        from datetime import UTC, datetime, timedelta
        from dataclasses import replace
        from foreign_trade_geo_agent.core.evidence_intake import snapshot_digest
        self.configure()
        service = self.app.state.mvp_service
        form = self.generation_form()
        service.generation_ticket = (form['binding_sha256'], datetime.now(UTC) - timedelta(seconds=1))
        self.assertEqual(self.client.post('/mvp/generate', data=form).status_code, 409)
        _, _, store, _, _ = service._load()
        current = store.latest(service.generation_executor.task.project_id, service.generation_executor.task.task_id)
        for changed in (replace(current, task=replace(current.task, task_version=2)),
                        replace(current, plan_bound=False), replace(current, evidence_version=current.evidence_version+1)):
            with self.subTest(version=snapshot_digest(changed)), patch.object(service, '_current', return_value=changed):
                from foreign_trade_geo_agent.web.mvp_application import MVPError
                with self.assertRaises(MVPError) as failure:
                    service.generation.start(form['binding_sha256'], service.generation_ticket)
                self.assertEqual(failure.exception.status, 409)
        self.assertEqual(service.generation_executor.calls, 0)

    def test_evidence_changed_during_request_never_exports_a_successful_candidate(self):
        import httpx
        import asyncio
        import threading
        started, release = threading.Event(), threading.Event()
        async def handler(request):
            import json
            started.set()
            while not release.is_set():
                await asyncio.sleep(.01)
            fixture = json.loads((self.package / 'candidate/04-writer-output.json').read_text(encoding='utf-8'))
            return httpx.Response(200, json={'model':'deepseek-flash', 'choices':[
                {'message': {'content': json.dumps(fixture)}, 'finish_reason': 'stop'}]})
        self.configure(handler)
        self.client.post('/mvp/generate', data=self.generation_form())
        self.assertTrue(started.wait(2))
        self.client.post('/mvp/evidence', data={**self.form(), 'content':'changed during request', 'source_label':'new'})
        release.set()
        for _ in range(100):
            if list(self.package.glob('generation/*/result.json')):
                break
            time.sleep(.02)
        import json
        result = json.loads(next(self.package.glob('generation/*/result.json')).read_bytes())
        self.assertEqual(result['state'], 'REQUEST_FAILED')
        self.assertFalse((self.package / 'generation/selected.json').exists())
        self.assertFalse(list(self.package.glob('generation/*/history.sqlite3')))

    def test_secret_output_is_withheld_and_no_candidate_is_selected(self):
        import httpx
        secret = 'sk-' + 'A'*20
        self.configure(lambda request: httpx.Response(200, json={'model': 'deepseek-flash',
            'choices': [{'message': {'content': secret}, 'finish_reason': 'stop'}]}))
        self.client.post('/mvp/generate', data=self.generation_form())
        page = self.finish()
        self.assertIn('WITHHELD_SECRET', page.text)
        self.assertNotIn(secret, page.text)
        self.assertFalse(list(self.package.glob('generation/*/response-body.bin')))
        self.assertFalse((self.package / 'generation/selected.json').exists())

    def test_selection_write_failure_is_not_shown_as_success(self):
        self.configure()
        original = __import__('pathlib').Path.replace
        def fail(path, target):
            if path.name == 'selected.pending':
                raise OSError('private storage details')
            return original(path, target)
        with patch('pathlib.Path.replace', new=fail):
            self.client.post('/mvp/generate', data=self.generation_form())
            page = self.finish()
        self.assertIn('data-generation-state="REQUEST_FAILED"', page.text)
        self.assertNotIn('private storage details', page.text)
        self.assertFalse(self.app.state.mvp_service.article()['generated_from_web'])

    def test_generation_mutations_require_csrf_loopback_and_exact_fields(self):
        self.configure()
        form = self.generation_form()
        for changed, code in (({'csrf_token':'forged'},403), ({'csrf_token':'非ASCII'},403),
                              ({'production_authorized':'true'},422), ({'model':'paid-model'},422),
                              ({'binding_sha256':'0'*64},409)):
            with self.subTest(fields=list(changed)):
                self.assertEqual(self.client.post('/mvp/generate', data={**form, **changed}).status_code, code)
        self.assertEqual(self.client.post('/mvp/generate', data=form, headers={'Host':'unapproved.example'}).status_code,403)
        self.assertEqual(self.app.state.mvp_service.generation_executor.calls,0)
        self.assertFalse((self.package / 'generation').exists())

    def test_incomplete_reservation_is_consumed_after_restart(self):
        from foreign_trade_geo_agent.web.generation import canonical
        from foreign_trade_geo_agent.web.mvp_application import MVPApplicationService
        self.configure()
        form = self.generation_form()
        output = self.package / 'generation' / form['binding_sha256']
        output.mkdir(parents=True)
        (output / 'started.json').write_bytes(canonical({'binding_sha256':form['binding_sha256'], 'state':'RUNNING'}))
        reopened = MVPApplicationService(self.package)
        reopened.generation_executor = self.app.state.mvp_service.generation_executor
        reopened.scope_reviewer = self.app.state.mvp_service.scope_reviewer
        self.assertEqual(reopened.generation.view()['generation_state'],'REQUEST_FAILED')
        reopened.generation.start(form['binding_sha256'],None)
        self.assertEqual(reopened.generation_executor.calls,0)
