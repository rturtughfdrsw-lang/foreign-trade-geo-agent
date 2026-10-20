"""Local developer opinions never mutate source history or grant authority."""
from contextlib import closing
import hashlib
import html
from html.parser import HTMLParser
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4

from fastapi.testclient import TestClient
from foreign_trade_geo_agent.core.history import ArtifactRecord, ArtifactType, RunStatus
from foreign_trade_geo_agent.core.content_draft_review import render_draft_body_text
from foreign_trade_geo_agent.core.content_draft import ContentDraftReport, ContentDraftStatus
from foreign_trade_geo_agent.storage.sqlite import SQLiteHistoryStore
from foreign_trade_geo_agent.web.commercial_inspector import create_commercial_app
from tests.test_sqlite_history_store import running_run, audit, NOW
from tests.review_fixtures import (persist_review_fixture, RUN_ID, SITE_CONTENT_ARTIFACT_ID,
                                   CONTENT_DRAFT_ARTIFACT_ID, PAGE_EXCERPT_SENTINEL)


class Inputs(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.values = {}
        self.forms = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'form':
            self.forms.append(attrs)
        if tag == 'input' and attrs.get('type') == 'hidden':
            self.values[attrs['name']] = attrs['value']


class CommercialFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory()))
        self.db = self.root/'.data/seo-mvp/candidate/history.sqlite3'
        self.db.parent.mkdir(parents=True)
        self.store = SQLiteHistoryStore(self.db)
        self.run, self.other, self.artifact = (str(uuid4()) for _ in range(3))
        for run in (self.run, self.other):
            self.store.create_run(running_run(run))
        self.store.append_artifact(ArtifactRecord(self.artifact, self.run, ArtifactType.SITE_AUDIT, 1, NOW, audit()))
        self.before = hashlib.sha256(self.db.read_bytes()).hexdigest()
        self.feedback_db = self.root/'.data/commercial-feedback/feedback.sqlite3'
        self.client = self.make_client()
        self.url = f'/runs/candidate/{self.run}/review/{self.artifact}'

    def make_client(self):
        return self.enterContext(TestClient(create_commercial_app(self.root), base_url='http://127.0.0.1:8003',
                                            client=('127.0.0.1', 12345)))

    def form(self, url=None):
        response = self.client.get(url or self.url)
        self.assertEqual(response.status_code, 200)
        values = Inputs(response.text).values
        self.assertIn('digest', values)
        return dict(values, note='需要核对证据范围', marked_text='待核对内容', disposition='needs_revision')

    def submit(self, form=None, url=None, **kwargs):
        return self.client.post(url or self.url, data=form or self.form(), follow_redirects=False, **kwargs)

    def test_real_run_links_and_bound_artifact(self):
        self.assertIn(self.run, self.client.get('/history').text)
        response = self.client.get(f'/runs/candidate/{self.run}')
        self.assertIn(self.url, response.text)
        self.assertIn('Draft NOT_AVAILABLE', response.text)
        self.assertIn('DRAFT_EXECUTION_AUTHORIZATION_REQUIRED', response.text)
        self.assertIn('site_audit', self.client.get(self.url).text)
        self.assertFalse(self.feedback_db.exists(), 'GET must not initialize storage')

    def test_saved_source_evidence_and_draft_are_read_from_selected_run(self):
        fixture = persist_review_fixture(self.db)
        before = hashlib.sha256(self.db.read_bytes()).hexdigest()
        page = self.client.get(f'/runs/candidate/{RUN_ID}')
        self.assertEqual(page.status_code, 200)
        self.assertIn(html.escape(render_draft_body_text(fixture.domain.content_draft.drafts[0])), page.text)
        self.assertIn(SITE_CONTENT_ARTIFACT_ID, page.text)
        source_url = f'/runs/candidate/{RUN_ID}/review/{SITE_CONTENT_ARTIFACT_ID}'
        source = self.client.get(source_url)
        self.assertIn(PAGE_EXCERPT_SENTINEL, source.text)
        self.assertIn('site_content', source.text)
        draft_url = f'/runs/candidate/{RUN_ID}/review/{CONTENT_DRAFT_ARTIFACT_ID}'
        self.assertEqual(self.submit(self.form(draft_url), draft_url).status_code, 303)
        self.assertIn('需要核对证据范围', self.client.get(draft_url).text)
        self.assertNotIn('需要核对证据范围', self.client.get(source_url).text)
        self.assertEqual(hashlib.sha256(self.db.read_bytes()).hexdigest(), before)

    def test_failed_draft_report_shows_saved_failure_without_article(self):
        artifact_id = str(uuid4())
        report = ContentDraftReport(ContentDraftStatus.GENERATION_FAILED, (), (), None)
        self.store.append_artifact(ArtifactRecord(artifact_id,self.run,ArtifactType.CONTENT_DRAFT,1,NOW,report))
        page = self.client.get(f'/runs/candidate/{self.run}')
        self.assertEqual(page.status_code,200)
        self.assertIn('generation_failed',page.text)
        self.assertIn('Draft NOT_AVAILABLE',page.text)
        self.assertNotIn('已保存 Draft（不构成可信批准）',page.text)

    def test_post_redirect_persistence_restart_and_no_refresh_write(self):
        form = self.form()
        self.assertEqual(self.submit(form).status_code, 303)
        for _ in range(2):
            self.assertIn('需要核对证据范围', self.client.get(self.url).text)
        self.assertIn('LOCAL_DEVELOPER_FEEDBACK', self.make_client().get(self.url).text)
        self.assertIn('需要核对证据范围', self.make_client().get(self.url).text)
        self.assertEqual(self.submit(form).status_code, 303, 'same submission is idempotent')
        with closing(sqlite3.connect(self.feedback_db)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM developer_feedback').fetchone()[0], 1)
        self.assertEqual(hashlib.sha256(self.db.read_bytes()).hexdigest(), self.before)

    def test_browser_form_preserves_same_origin_submission_metadata(self):
        page = self.client.get(self.url)
        # Chromium sends Origin: null on POST under no-referrer, even same-origin.
        # Same-origin preserves browser integrity metadata without leaking to other sites.
        self.assertEqual(page.headers['referrer-policy'], 'same-origin')
        forms = Inputs(page.text).forms
        self.assertEqual(len(forms), 1)
        self.assertEqual(forms[0]['method'], 'post')
        self.assertEqual(forms[0]['action'], self.url)
        response = self.submit(headers={'Origin': 'http://127.0.0.1:8003',
                                        'Referer': 'http://127.0.0.1:8003'+self.url,
                                        'Sec-Fetch-Site': 'same-origin'})
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers['location'], self.url)
        self.assertIn('需要核对证据范围', self.client.get(response.headers['location']).text)

    def test_chrome_same_origin_with_full_root_or_absent_referer(self):
        for referer in ('http://127.0.0.1:8003'+self.url, 'http://127.0.0.1:8003/', None):
            with self.subTest(referer=referer):
                headers = {'Origin': 'http://127.0.0.1:8003', 'Sec-Fetch-Site': 'same-origin'}
                if referer is not None:
                    headers['Referer'] = referer
                self.assertEqual(self.submit(headers=headers).status_code, 303)
        with closing(sqlite3.connect(self.feedback_db)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM developer_feedback').fetchone()[0], 3)

    def test_untrusted_or_opaque_origin_never_writes_even_with_local_referer(self):
        form = self.form()
        for origin in ('null', '', 'https://evil.example', 'http://localhost:8003',
                       'http://127.0.0.1:8002', 'https://127.0.0.1:8003',
                       'http://127.0.0.1:8003.evil.example'):
            with self.subTest(origin=origin):
                response = self.submit(form, headers={'Origin': origin,
                    'Referer': 'http://127.0.0.1:8003'+self.url,
                    'Sec-Fetch-Site': 'cross-site'})
                self.assertEqual(response.status_code, 403)
        self.assertFalse(self.feedback_db.exists())

    def test_missing_origin_still_requires_local_host_and_csrf(self):
        # Non-browser clients may omit Origin; they still need the local secret
        # and a signed, object-bound form. Referer is never a CSRF substitute.
        form = self.form()
        headers = {'Referer': 'http://127.0.0.1:8003'+self.url}
        self.assertEqual(self.submit(dict(form, csrf_token='wrong'), headers=headers).status_code, 403)
        self.assertEqual(self.submit(dict(form, csrf_token=''), headers=headers).status_code, 403)
        self.assertEqual(self.submit(form, headers={'Host': 'evil.example'}).status_code, 400)
        self.assertFalse(self.feedback_db.exists())
        self.assertEqual(self.submit(form, headers=headers).status_code, 303)

    def test_same_origin_csrf_failure_never_writes(self):
        form = self.form()
        for token in ('', 'wrong', '中文'):
            with self.subTest(token=token):
                self.assertEqual(self.submit(dict(form, csrf_token=token), headers={
                    'Origin': 'http://127.0.0.1:8003', 'Sec-Fetch-Site': 'same-origin'}).status_code, 403)
        self.assertFalse(self.feedback_db.exists())

    def test_saved_feedback_is_isolated_between_runs(self):
        other_url = f'/runs/candidate/{self.other}/review/run'
        self.assertEqual(self.submit(dict(self.form(), note='first-run-test-only')).status_code, 303)
        self.assertEqual(self.submit(dict(self.form(other_url), note='other-run-test-only'), other_url).status_code, 303)
        first, other = self.client.get(self.url).text, self.client.get(other_url).text
        self.assertIn('first-run-test-only', first)
        self.assertNotIn('other-run-test-only', first)
        self.assertIn('other-run-test-only', other)
        self.assertNotIn('first-run-test-only', other)

    def test_append_only_multiple_opinions_and_database_triggers(self):
        self.assertEqual(self.submit().status_code, 303)
        self.assertEqual(self.submit(dict(self.form(), note='第二条意见')).status_code, 303)
        page = self.client.get(self.url).text
        self.assertIn('需要核对证据范围', page)
        self.assertIn('第二条意见', page)
        with closing(sqlite3.connect(self.feedback_db)) as db:
            for sql in ('UPDATE developer_feedback SET note="changed"', 'DELETE FROM developer_feedback'):
                with self.assertRaises(sqlite3.IntegrityError):
                    db.execute(sql)

    def test_cross_run_object_and_ticket_rejected(self):
        form = self.form()
        wrong = f'/runs/candidate/{self.other}/review/{self.artifact}'
        self.assertEqual(self.client.get(wrong).status_code, 404)
        self.assertEqual(self.submit(form, wrong).status_code, 404)
        other_run = f'/runs/candidate/{self.other}/review/run'
        self.assertEqual(self.submit(form, other_run).status_code, 409)
        self.assertFalse(self.feedback_db.exists())

    def test_wrong_version_digest_and_stale_run_rejected(self):
        form = self.form()
        for field, value in [('version', '999'), ('digest', '0'*64), ('ticket', 'bad')]:
            self.assertEqual(self.submit(dict(form, **{field: value})).status_code, 409)
        run_url = f'/runs/candidate/{self.run}/review/run'
        form = self.form(run_url)
        # A genuine run state transition invalidates its observed digest.
        self.store.finish_run(self.run, completed_at=NOW, status=RunStatus.SUCCEEDED,
                              failure_kind=None, sanitized_error=None)
        self.assertEqual(self.submit(form, run_url).status_code, 409)
        self.assertFalse(self.feedback_db.exists())

    def test_host_csrf_origin_and_nonlocal_client(self):
        form = self.form()
        self.assertEqual(self.submit(form, headers={'Host':'evil.example'}).status_code, 400)
        self.assertEqual(self.submit(dict(form, csrf_token='wrong')).status_code, 403)
        self.assertEqual(self.submit(dict(form, csrf_token='中文')).status_code, 403)
        self.assertEqual(self.submit(form, headers={'Origin':'https://evil.example'}).status_code, 403)
        remote = self.enterContext(TestClient(create_commercial_app(self.root), base_url='http://127.0.0.1',
                                              client=('203.0.113.1', 12345)))
        remote_form = dict(Inputs(remote.get(self.url).text).values, note='test', marked_text='', disposition='observation')
        self.assertEqual(remote.post(self.url, data=remote_form).status_code, 403)
        self.assertFalse(self.feedback_db.exists())

    def test_xss_validation_and_payload_budget(self):
        form = self.form()
        script = '<script>alert(1)</script>'
        self.assertEqual(self.submit(dict(form, note=script, marked_text=script)).status_code, 303)
        page = self.client.get(self.url)
        self.assertIn('&lt;script&gt;', page.text)
        self.assertNotIn(script, page.text)
        self.assertIn("form-action 'self'", page.headers['content-security-policy'])
        for note in ('', 'x'*2001):
            self.assertEqual(self.submit(dict(self.form(), note=note)).status_code, 422)
        self.assertEqual(self.client.post(self.url, content=b'x'*70000,
                          headers={'Content-Type':'application/x-www-form-urlencoded'}).status_code, 413)

    def test_feedback_cannot_unlock_gate_or_change_old_history(self):
        self.assertEqual(self.submit(dict(self.form(), disposition='approved')).status_code, 422)
        self.assertEqual(self.submit().status_code, 303)
        self.assertIn('DRAFT_EXECUTION_AUTHORIZATION_REQUIRED', self.client.get('/').text)
        self.assertIn('不构成', self.client.get(self.url).text)
        self.assertEqual(hashlib.sha256(self.db.read_bytes()).hexdigest(), self.before)
        self.assertFalse((self.root/'.data/phase8-mvp/history.sqlite3').exists())

    def test_readonly_failure_is_not_success(self):
        form = self.form()
        self.feedback_db.parent.mkdir(parents=True)
        self.feedback_db.mkdir()  # unusable path; no fallback to history/VDemo database
        self.assertEqual(self.submit(form).status_code, 503)
        self.assertEqual(hashlib.sha256(self.db.read_bytes()).hexdigest(), self.before)


if __name__ == '__main__':
    unittest.main()
