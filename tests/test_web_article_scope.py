"""Local HTTP scope request, stale consent and generation bypass regression."""
import html
import re
import unittest

from tests import test_web_mvp as base


class WebArticleScopeTests(unittest.TestCase):
    setUpClass = classmethod(base.MVPWebTests.setUpClass.__func__)
    setUp = base.MVPWebTests.setUp
    form = base.MVPWebTests.form

    def test_scope_request_is_pending_and_does_not_mutate_old_task(self):
        before = self.app.state.mvp_service.evidence()['snapshot']
        response = self.client.post('/mvp/scope', data={**self.form(), 'goal': 'Explain the supplied test conditions only',
                                                     'reason': 'The broader purchasing decisions have no evidence.'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('待重新规划和确认', response.text)
        self.assertEqual(self.app.state.mvp_service.evidence()['snapshot'], before)
        self.assertFalse(self.app.state.mvp_service.evidence()['scope_request']['customer_consented'])

    def test_generation_post_cannot_bypass_missing_scope_review(self):
        from scripts.demo_seo_e_only import DOCUMENT
        from scripts.web_generation_demo import build_mock_executor
        executor = build_mock_executor(self.package)
        self.app.state.mvp_service.generation_executor = executor
        self.client.post('/mvp/evidence', data={**self.form(), 'content': DOCUMENT, 'source_label': 'E1'})
        self.client.post('/mvp/recheck', data=self.form())
        response = self.client.post('/mvp/generate', data={'csrf_token': self.form()['csrf_token'], 'binding_sha256': '0'*64})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(executor.calls, 0)
        self.assertFalse((self.package / 'generation').exists())
        self.assertIn('范围一致性', self.client.get('/mvp/generate').text)

    def test_test_confirmation_is_explicit_and_not_enabled_by_customer_fields(self):
        response = self.client.post('/mvp/scope/test-confirm', data={**self.form(), 'confirmed': 'yes'})
        self.assertEqual(response.status_code, 422)
        forged = self.client.post('/mvp/scope', data={**self.form(), 'goal': 'short', 'reason': 'test', 'approved': 'true'})
        self.assertEqual(forged.status_code, 422)
