"""Local edits must persist without changing native evidence or delivery authority."""
import html
from contextlib import closing
import re
import socket
import sqlite3
import unittest
from unittest.mock import patch

from tests import test_web_mvp as base


class ArticleReviewTests(unittest.TestCase):
    setUpClass = classmethod(base.MVPWebTests.setUpClass.__func__)

    def setUp(self):
        import shutil
        base.MVPWebTests.setUp(self)
        shutil.copyfile(self.package / 'candidate/intake.sqlite3', self.package / 'interactive-intake.sqlite3')

    def form(self):
        page = self.client.get('/mvp/article')
        self.assertEqual(page.status_code, 200)
        result = {}
        for name in ('csrf_token', 'expected_version', 'origin_sha256', 'expected_evidence_sha256'):
            match = re.search(r'name="' + name + r'" value="([^"]*)"', page.text)
            self.assertIsNotNone(match, 'article editor missing ' + name)
            result[name] = html.unescape(match.group(1))
        match = re.search(r'<textarea[^>]*name="body_text"[^>]*>(.*?)</textarea>', page.text, re.S)
        self.assertIsNotNone(match)
        result.update(body_text=html.unescape(match.group(1)), note='', status='PENDING_REVIEW')
        return result

    def save(self, **changes):
        return self.client.post('/mvp/article', data={**self.form(), **changes})

    def test_comment_status_restart_and_original_immutable(self):
        from foreign_trade_geo_agent.web.mvp_application import MVPApplicationService
        frozen = (self.package / 'candidate/history.sqlite3').read_bytes()
        original = self.client.get('/mvp/article.md?version=0').content
        response = self.save(note='Keep all test conditions; improve buyer explanation.', status='CHANGES_REQUESTED')
        self.assertEqual(response.status_code, 200)
        self.assertIn('需要修改', response.text)
        self.assertIn('Keep all test conditions', response.text)
        reopened = MVPApplicationService(self.package).article()
        self.assertEqual(reopened['selected_version'], 1)
        self.assertEqual(reopened['local_status'], 'CHANGES_REQUESTED')
        self.assertEqual(self.client.get('/mvp/article.md?version=0').content, original)
        self.assertEqual((self.package / 'candidate/history.sqlite3').read_bytes(), frozen)

    def test_content_edit_resets_review_and_does_not_reuse_citations(self):
        self.assertEqual(self.save(status='LOCAL_REVIEW_COMPLETE', note='Local only').status_code, 200)
        body = self.form()['body_text'].replace('7200', '9000')
        response = self.save(body_text=body, status='LOCAL_REVIEW_COMPLETE', note='Changed parameter for negative test')
        self.assertEqual(response.status_code, 200)
        article = self.app.state.mvp_service.article()
        self.assertEqual(article['local_status'], 'PENDING_REVIEW')
        self.assertEqual(article['validation_state'], 'PENDING_REVALIDATION')
        self.assertIn('旧引用映射仅对应原始正文', response.text)
        # Even a later local completion cannot validate facts or authorize delivery.
        self.save(status='LOCAL_REVIEW_COMPLETE', note='Local completion with unresolved facts')
        self.assertEqual(self.app.state.mvp_service.article()['validation_state'], 'PENDING_REVALIDATION')
        exported = self.client.get('/mvp/article.md').text
        self.assertIn('9000', exported)
        self.assertIn('PENDING_REVALIDATION', exported)
        self.assertIn('production_authorized=false', exported)
        self.assertNotIn('9000 rpm [CL3', exported)
        self.assertEqual(self.client.post('/mvp/approve', data=self.form()).status_code, 404)
        self.assertEqual(self.client.post('/mvp/deliver', data=self.form()).status_code, 404)

    def test_history_selection_exports_exact_selected_body_and_notes(self):
        first = self.form()['body_text'] + '\n\nFirst buyer question.'
        self.save(body_text=first, note='first')
        self.save(body_text=first + '\n\nSecond buyer question.', note='second')
        old = self.client.get('/mvp/article?version=1')
        self.assertEqual(old.status_code, 200)
        self.assertIn('First buyer question.', old.text)
        self.assertNotIn('Second buyer question.', old.text)
        md = self.client.get('/mvp/article.md?version=1')
        self.assertIn(first, md.text)
        self.assertNotIn('Second buyer question.', md.text)
        self.assertIn('version-1', md.headers['content-disposition'])
        for bad in ('-1', '1.5', '999', 'abc', '9' * 1000):
            self.assertIn(self.client.get('/mvp/article?version=' + bad).status_code, (404, 422))

    def test_stale_tab_and_evidence_changes_reject_without_losing_input(self):
        stale = self.form()
        self.save(note='first')
        response = self.client.post('/mvp/article', data={**stale, 'note': 'unsaved note'})
        self.assertEqual(response.status_code, 409)
        self.assertIn('unsaved note', response.text)
        fresh = self.form()
        evidence_form = base.MVPWebTests.form(self)
        self.client.post('/mvp/evidence', data={**evidence_form, 'content': 'changed source', 'source_label': 'new'})
        response = self.client.post('/mvp/article', data=fresh)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.app.state.mvp_service.article()['selected_version'], 1)
        self.assertEqual(self.app.state.mvp_service.article()['validation_state'], 'PENDING_REVALIDATION')

    def test_security_bounds_and_xss_no_network(self):
        form = self.form()
        for change, expected in (({'csrf_token': 'fake'}, 403), ({'status': 'APPROVED'}, 422),
                ({'note': 'x' * 2001}, 422), ({'body_text': ' '}, 422),
                ({'body_text': 'x' * 64001}, 413), ({'production_authorized': 'true'}, 422),
                ({'origin_sha256': '0' * 64}, 409)):
            with self.subTest(change=list(change)):
                self.assertEqual(self.client.post('/mvp/article', data={**form, **change}).status_code, expected)
        self.assertEqual(self.client.post('/mvp/article', data=form, headers={'Host': 'evil.example'}).status_code, 403)
        body = form['body_text'] + '\n\n<script>alert("x")</script>'
        with patch.object(socket.socket, 'connect', side_effect=AssertionError('network forbidden')):
            response = self.save(body_text=body, note='<img src=x onerror=alert(1)>')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('<script>alert', response.text)
        self.assertIn('&lt;script&gt;', response.text)

    def test_lf_normalization_and_revert_still_require_revalidation(self):
        original = self.form()['body_text']
        self.save(body_text=original.replace('\n', '\r\n'), note='unchanged')
        self.assertEqual(self.app.state.mvp_service.article()['validation_state'], 'HISTORICAL_NATIVE_VALIDATION')
        self.save(body_text=original + '\n\nNew wording.')
        self.save(body_text=original, status='LOCAL_REVIEW_COMPLETE')
        self.assertEqual(self.app.state.mvp_service.article()['validation_state'], 'PENDING_REVALIDATION')
        self.assertEqual(self.app.state.mvp_service.article()['local_status'], 'PENDING_REVIEW')

    def test_journal_is_append_only_and_tampering_fails_closed(self):
        self.save(note='one')
        path = self.package / 'local-draft-review.sqlite3'
        with closing(sqlite3.connect(path)) as db:
            for sql in ('UPDATE local_draft_revisions SET note="overwrite"', 'DELETE FROM local_draft_revisions'):
                with self.assertRaises(sqlite3.DatabaseError):
                    db.execute(sql)
        path.write_bytes(b'corrupt journal secret')
        response = self.client.get('/mvp/article')
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('corrupt journal secret', response.text)

    def test_failed_first_save_does_not_poison_journal(self):
        form = self.form()
        response = self.client.post('/mvp/article', data={**form, 'expected_version': '1'})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.client.get('/mvp/article').status_code, 200)
        self.assertEqual(self.save(note='recovered first save').status_code, 200)
        self.assertEqual(self.app.state.mvp_service.article()['selected_version'], 1)

    def test_maximum_four_byte_utf8_body_and_note_fit_form_budget(self):
        response = self.save(body_text='😀' * 16000, note='😀' * 2000)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.app.state.mvp_service.article()['local_body'], '😀' * 16000)

    def test_model_conditions_and_limitations_edits_all_invalidate_old_review(self):
        original = self.form()['body_text']
        for old, new in (('NCX7', 'NCX9'), ('unloaded bench', 'cutting load'),
                         ('not a cutting-load or production guarantee', 'a production guarantee')):
            with self.subTest(old=old):
                self.save(status='LOCAL_REVIEW_COMPLETE')
                response = self.save(body_text=original.replace(old, new), status='LOCAL_REVIEW_COMPLETE')
                self.assertEqual(response.status_code, 200)
                article = self.app.state.mvp_service.article()
                self.assertEqual(article['local_status'], 'PENDING_REVIEW')
                self.assertEqual(article['validation_state'], 'PENDING_REVALIDATION')

    def test_maximum_utf8_text_and_revision_limit_preserve_last_valid_record(self):
        from datetime import UTC, datetime
        from foreign_trade_geo_agent.storage.content_draft_review import SQLiteLocalDraftReviewStore
        from foreign_trade_geo_agent.core.history import HistoryConflictError
        body = '中' * 16000
        self.assertEqual(self.save(body_text=body, note='文' * 2000).status_code, 200)
        article = self.app.state.mvp_service.article()
        journal = SQLiteLocalDraftReviewStore(self.package / 'local-draft-review.sqlite3')
        args = dict(origin_sha256=article['origin_sha256'], original_body=article['review'].draft.body_text,
            body_text=body, note='', status='PENDING_REVIEW',
            frozen_evidence_sha256=article['review'].customer_evidence.snapshot_sha256,
            observed_evidence_sha256=article['expected_evidence_sha256'], saved_at=datetime.now(UTC))
        for version in range(1, 100):
            journal.append(expected_version=version, **args)
        with self.assertRaises(HistoryConflictError):
            journal.append(expected_version=100, **args)
        self.assertEqual(self.app.state.mvp_service.article()['selected_version'], 100)
        self.assertEqual(self.client.get('/mvp/article.md?version=100').text.count(body), 1)


if __name__ == '__main__':
    unittest.main()
