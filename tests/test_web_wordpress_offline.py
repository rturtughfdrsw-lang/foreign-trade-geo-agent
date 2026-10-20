"""WordPress offline acceptance: no production authority or network capability."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
import html
import json
import re
import socket
import sqlite3
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from tests import test_web_mvp as base
from foreign_trade_geo_agent.web.wordpress_delivery import SAMPLES, TARGET, PATH, digest


class OfflineWordPressTests(unittest.TestCase):
    setUpClass = classmethod(base.MVPWebTests.setUpClass.__func__)
    setUp = base.MVPWebTests.setUp

    def form(self, sample='success'):
        response = self.client.get('/mvp/delivery/test?sample=' + sample)
        self.assertEqual(response.status_code, 200)
        return {name: html.unescape(re.search(r'name="' + name + r'" value="([^"]*)"',
                                             response.text).group(1))
                for name in ('csrf_token', 'sample', 'binding_sha256')}

    def test_real_article_preview_blocked_before_publisher_or_claim(self):
        page = self.client.get('/mvp/delivery?version=0')
        self.assertEqual(page.status_code, 200)
        for label in ('QUALITY_NOT_APPROVED', 'TRUSTED_SIGNOFF_REQUIRED', 'P1_GLOBAL_CONSUMPTION_BLOCKED',
                      'TEST_ONLY_EVIDENCE', 'TARGET_NOT_AUTHORIZED', '最终草稿内容预览', '创建 WordPress 草稿（未授权）'):
            self.assertIn(label, page.text)
        service = self.app.state.mvp_service
        preview = service.delivery.preview('0')
        self.assertIn(html.escape(service.article('0')['local_body'].split('\n\n')[-1], quote=True),
                      preview['preview_html'])
        with patch('foreign_trade_geo_agent.web.wordpress_delivery.WordPressRestDraftPublisher',
                   side_effect=AssertionError('production publisher forbidden')):
            response = self.client.post('/mvp/delivery', data=dict(csrf_token=self.app.state.csrf_token,
                version='0', binding_sha256=preview['binding_sha256']))
        self.assertEqual(response.status_code, 409)
        self.assertFalse(service.delivery.journal.path.exists())

    def test_live_candidate_quality_remains_blocked(self):
        service = self.app.state.mvp_service
        article = service.article('0')
        with patch.object(service, 'article', return_value=dict(article, candidate_mode='LIVE')):
            preview = service.delivery.preview('0')
        self.assertFalse(preview['delivery_allowed'])
        self.assertTrue(any('QUALITY_NEEDS_REVISION' in reason for reason in preview['blockers']))

    def test_mock_create_exact_payload_and_native_attempt_persist(self):
        form = self.form()
        with patch.object(socket.socket, 'connect', side_effect=AssertionError('network forbidden')):
            response = self.client.post('/mvp/delivery/test?sample=success', data=form)
        self.assertEqual(response.status_code, 200)
        self.assertIn('已有交付结果 · success', response.text)
        record = self.app.state.mvp_service.delivery.test_preview()['record']
        exchange, claim, result = record['exchange'], record['claim'], record['result']
        self.assertEqual(exchange['method'], 'POST')
        self.assertEqual(exchange['url'], TARGET + PATH)
        self.assertEqual(exchange['body'], SAMPLES['success'].binding()['request'])
        self.assertEqual(set(exchange['body']), {'title', 'content', 'status'})
        self.assertEqual(exchange['body']['status'], 'draft')
        self.assertEqual(exchange['response_status'], 201)
        self.assertEqual(exchange['response']['status'], 'draft')
        self.assertEqual(claim['body_sha256'], SAMPLES['success'].binding()['body_sha256'])
        self.assertEqual(result['attempt']['content_draft_artifact_id'], self._native_artifact_id(claim))
        self.assertEqual(result['attempt']['remote_post_id'], 701)
        self.assertEqual(result['real_network_requests'], 0)

    def _native_artifact_id(self, claim):
        path = self.app.state.mvp_service.delivery.root / claim['binding_sha256'] / 'history.sqlite3'
        with closing(sqlite3.connect(path)) as db:
            return db.execute("SELECT artifact_id FROM artifacts WHERE artifact_type='content_draft'").fetchone()[0]

    def test_failure_timeout_and_repeated_submits_never_retry(self):
        for key, status, code in (('failure', 'failed_definitely', 401), ('timeout', 'unknown', None)):
            with self.subTest(key=key):
                form = self.form(key)
                first = self.client.post('/mvp/delivery/test?sample=' + key, data=form)
                self.assertEqual(first.status_code, 200)
                record = self.app.state.mvp_service.delivery.test_preview(key)['record']
                self.assertEqual(record['result']['status'], status)
                self.assertEqual(record['exchange']['response_status'], code)
                second = self.client.post('/mvp/delivery/test?sample=' + key, data=form)
                self.assertIn('重复提交已阻断', second.text)
                self.assertEqual(self.app.state.mvp_service.delivery.test_preview(key)['record'], record)

    def test_success_duplicate_and_app_restart_return_existing_record(self):
        form = self.form()
        self.client.post('/mvp/delivery/test', data=form)
        service = self.app.state.mvp_service
        before = service.delivery.test_preview()['record']
        from foreign_trade_geo_agent.web.app import create_app
        app = create_app(db_path=self.root / 'restart-demo.db', live_db_path=self.root / 'restart-live.db',
                         mvp_dir=self.package)
        with TestClient(app, base_url='http://127.0.0.1') as client:
            form['csrf_token'] = app.state.csrf_token
            response = client.post('/mvp/delivery/test', data=form)
            self.assertIn('重复提交已阻断', response.text)
            self.assertEqual(app.state.mvp_service.delivery.test_preview()['record'], before)
        with closing(sqlite3.connect(service.delivery.journal.path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM claims').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT count(*) FROM events').fetchone()[0], 2)

    def test_changed_body_evidence_target_and_summary_cannot_inherit_test_decision(self):
        for key in ('revised', 'evidence-changed'):
            form = self.form(key)
            response = self.client.post('/mvp/delivery/test?sample=' + key, data=form)
            self.assertEqual(response.status_code, 409)
            self.assertIn('旧 TEST-only 批准失效', response.text)
        service = self.app.state.mvp_service
        original = SAMPLES['success']
        for changed in (replace(original, body=original.body + ' Changed.'),
                        replace(original, evidence=original.evidence + ' Changed.'),
                        replace(original, version=2)):
            with patch('foreign_trade_geo_agent.web.wordpress_delivery.SAMPLES', {'success': changed}):
                view = service.delivery.test_preview()
                self.assertFalse(view['test_approved'])
                with self.assertRaisesRegex(ValueError, '旧 TEST-only 批准失效'):
                    asyncio.run(service.delivery.deliver_mock('success', view['binding_sha256']))
        with patch('foreign_trade_geo_agent.web.wordpress_delivery.TARGET', 'https://other.example'):
            self.assertFalse(service.delivery.test_preview()['test_approved'])
        response = self.client.post('/mvp/delivery/test', data={**self.form(), 'binding_sha256': '0' * 64})
        self.assertEqual(response.status_code, 409)
        self.assertFalse(service.delivery.journal.path.exists())

    def test_forged_privileges_target_content_or_real_article_cannot_enter_mock(self):
        form = self.form()
        for field in ('approval', 'signature', 'permission', 'target', 'status', 'body', 'article_version'):
            with self.subTest(field=field):
                response = self.client.post('/mvp/delivery/test', data={**form, field: 'forged'})
                self.assertEqual(response.status_code, 422)
        self.assertEqual(self.client.post('/mvp/delivery/test', data={**form, 'sample': 'real-DeepSeek'}).status_code, 422)
        self.assertEqual(self.client.post('/mvp/delivery/test', data={**form, 'csrf_token': 'forged'}).status_code, 403)
        self.assertFalse(self.app.state.mvp_service.delivery.journal.path.exists())

    def test_forged_production_form_privileges_are_rejected(self):
        preview = self.app.state.mvp_service.delivery.preview('0')
        form = dict(csrf_token=self.app.state.csrf_token, version='0', binding_sha256=preview['binding_sha256'])
        for field in ('approval', 'signature', 'permission', 'target'):
            self.assertEqual(self.client.post('/mvp/delivery', data={**form, field: 'forged'}).status_code, 422)

    def test_preclaim_storage_failure_sends_zero_mock_requests(self):
        service = self.app.state.mvp_service.delivery
        form = self.form()
        with patch.object(service.journal, 'claim', side_effect=OSError('sensitive error')):
            response = self.client.post('/mvp/delivery/test', data=form)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('sensitive error', response.text)
        self.assertFalse(service.root.exists())

    def test_result_storage_failure_consumes_and_cannot_retry(self):
        service = self.app.state.mvp_service.delivery
        form = self.form()
        append = service.journal.append
        def fail_result(binding, kind, payload):
            if kind == 'result':
                raise OSError('sensitive error')
            return append(binding, kind, payload)
        with patch.object(service.journal, 'append', side_effect=fail_result):
            response = self.client.post('/mvp/delivery/test', data=form)
        self.assertEqual(response.status_code, 503)
        record = service.test_preview()['record']
        self.assertIn('exchange', record)
        self.assertNotIn('result', record)
        response = self.client.post('/mvp/delivery/test', data=form)
        self.assertIn('重复提交已阻断', response.text)
        self.assertIn('需核对', response.text)
        self.assertEqual(service.test_preview()['record'], record)

    def test_concurrent_journal_claim_is_atomic(self):
        service = self.app.state.mvp_service.delivery
        view = service.test_preview()
        payload = dict(view['binding'], binding_sha256=view['binding_sha256'])
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: service.journal.claim(view['binding_sha256'], payload), range(4)))
        self.assertEqual(results.count(True), 1)
        # An interrupted claim is visible and blocks delivery after restart.
        response = self.client.post('/mvp/delivery/test', data=self.form())
        self.assertIn('重复提交已阻断', response.text)
        self.assertNotIn('exchange', service.test_preview()['record'])

    def test_no_credentials_from_environment_headers_or_logs(self):
        form = self.form()
        sentinel = 'PRODUCTION_CREDENTIAL_SENTINEL_a918fb'
        import logging
        with patch.dict('os.environ', {'WORDPRESS_BASE_URL': 'https://real.example',
                                      'WORDPRESS_USERNAME': sentinel, 'WORDPRESS_APPLICATION_PASSWORD': sentinel}), \
             self.assertLogs('httpx', level=logging.INFO) as logs:
            response = self.client.post('/mvp/delivery/test', data=form)
        record = self.app.state.mvp_service.delivery.test_preview()['record']
        serialized = json.dumps(record)
        for text in (response.text, serialized, '\n'.join(logs.output)):
            self.assertNotIn(sentinel, text)
            self.assertNotIn('Authorization', text)
            self.assertNotIn('OFFLINE-PLACEHOLDER', text)
        self.assertEqual(record['exchange']['url'], TARGET + PATH)

    def test_journal_is_append_only(self):
        self.client.post('/mvp/delivery/test', data=self.form())
        with closing(sqlite3.connect(self.app.state.mvp_service.delivery.journal.path)) as db:
            for table in ('claims', 'events'):
                for command in (f'DELETE FROM {table}', f'UPDATE {table} SET payload=payload'):
                    with self.assertRaises(sqlite3.IntegrityError):
                        db.execute(command)

    def test_saved_body_and_evidence_change_invalidate_real_preview(self):
        service = self.app.state.mvp_service
        before = service.delivery.preview('0')
        article = service.article()
        service.save_article(expected_version='0', origin_sha256=article['origin_sha256'],
            expected_evidence_sha256=article['expected_evidence_sha256'],
            body_text=article['local_body'] + '\n\nChanged body.', note='TEST change', status='LOCAL_REVIEW_COMPLETE')
        after = service.delivery.preview('1')
        self.assertEqual(after['article']['local_status'], 'PENDING_REVIEW')
        self.assertIn('REVALIDATION_REQUIRED', after['blockers'][0])
        self.assertNotEqual(after['binding_sha256'], before['binding_sha256'])
        with self.assertRaisesRegex(ValueError, '预览失效'):
            service.delivery.block_real('0', before['binding_sha256'])
        original = after['binding_sha256']
        service.submit(expected_sha256=service.evidence()['expected_sha256'], content='Changed evidence.', source_label='TEST')
        self.assertNotEqual(service.delivery.preview('1')['binding_sha256'], original)

    def test_html_preview_escapes_saved_script(self):
        service = self.app.state.mvp_service
        article = service.article()
        service.save_article(expected_version='0', origin_sha256=article['origin_sha256'],
            expected_evidence_sha256=article['expected_evidence_sha256'],
            body_text='<script>alert(1)</script>', note='XSS test', status='PENDING_REVIEW')
        response = self.client.get('/mvp/delivery?version=1')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('<script>alert(1)</script>', response.text)
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;', response.text)

    def test_offline_launcher_denies_generation_and_reads_retained_selection(self):
        from scripts.web_wordpress_offline import compose
        from foreign_trade_geo_agent.web.saved_article import SavedArticleGeneration
        app = compose(self.package)
        service = app.state.mvp_service
        self.assertIsInstance(service.generation, SavedArticleGeneration)
        self.assertIsNone(service.generation_executor)
        self.assertIsNone(service.generation.selected())
        with TestClient(app, base_url='http://127.0.0.1') as client:
            with patch.object(socket.socket, 'connect', side_effect=AssertionError('network forbidden')):
                response = client.post('/mvp/generate', data=dict(csrf_token=app.state.csrf_token,
                    binding_sha256='0' * 64))
            self.assertEqual(response.status_code, 409)
            self.assertIn('不允许模型请求', response.text)
            self.assertEqual(client.get('/mvp/article').status_code, 200)
        root = service.generation.root
        root.mkdir()
        key = 'a' * 64
        (root / key).mkdir()
        (root / 'selected.json').write_text(json.dumps({'binding_sha256': key}), encoding='utf-8')
        result = dict(state='SUCCEEDED', mode='LIVE', binding_sha256=key, production_authorized=False)
        (root / key / 'result.json').write_text(json.dumps(result), encoding='utf-8')
        self.assertEqual(service.generation.selected(), (root / key / 'history.sqlite3', result))
        result['production_authorized'] = True
        (root / key / 'result.json').write_text(json.dumps(result), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'LOCAL_RECORD_INVALID'):
            service.generation.selected()
        self.assertFalse(service.generation.view()['generation_allowed'])
