"""Version-specific local revalidation must never inherit stale authority."""
from dataclasses import replace
import html
import re
import sqlite3
from contextlib import closing
import unittest
from unittest.mock import patch

from tests import test_web_article_review as article_tests


class RevalidationTests(unittest.TestCase):
    setUpClass = article_tests.ArticleReviewTests.__dict__['setUpClass']
    setUp = article_tests.ArticleReviewTests.setUp
    form = article_tests.ArticleReviewTests.form
    save = article_tests.ArticleReviewTests.save

    def validation_form(self, version='1'):
        page = self.client.get('/mvp/article?version=' + version + '&revalidate=1')
        self.assertEqual(page.status_code, 200)
        form = {}
        for name in ('csrf_token', 'version', 'origin_sha256', 'body_sha256',
                     'expected_evidence_sha256', 'report_sha256'):
            match = re.search(r'name="' + name + r'" value="([^"]*)"', page.text)
            self.assertIsNotNone(match, 'missing revalidation field ' + name)
            form[name] = html.unescape(match.group(1))
        return {**form, 'note': 'Reviewed full text, source and scope; CTA only asks a question.', 'confirmed': 'yes', 'decision': 'CONFIRMED'}

    def test_manual_rejection_overrides_prior_local_complete_without_inventing_native_failure(self):
        self.save(note='one')
        form = self.validation_form()
        self.assertEqual(self.client.post('/mvp/article/validation', data=form).status_code, 200)
        self.assertEqual(self.app.state.mvp_service.article()['validation_state'], 'LOCAL_REVALIDATION_COMPLETE')
        rejected = self.client.post('/mvp/article/validation', data={**form, 'decision': 'ISSUES_FOUND', 'note': 'Scope needs specialist review.'})
        self.assertEqual(rejected.status_code, 200)
        article = self.app.state.mvp_service.article()
        self.assertEqual(article['validation_state'], 'PENDING_REVALIDATION')
        self.assertEqual(article['revalidation_report'].native_state, 'PASSED')
        self.assertEqual(len(article['revalidation_records']), 2)

    def test_cta_revision_native_replay_manual_record_and_version_isolation(self):
        original = self.form()['body_text']
        article = self.app.state.mvp_service.article()
        cta = article['review'].draft.claims[-1].text
        self.save(body_text=original[:-len(cta)] + 'Ask the supplier how the stated test applies to your planned cutting cycle.')
        form = self.validation_form()
        self.assertEqual(self.app.state.mvp_service.article('1')['validation_state'], 'PENDING_REVALIDATION')
        response = self.client.post('/mvp/article/validation', data=form)
        self.assertEqual(response.status_code, 200)
        result = self.app.state.mvp_service.article('1')
        self.assertEqual(result['validation_state'], 'LOCAL_REVALIDATION_COMPLETE')
        self.assertEqual(result['revalidation_report'].native_state, 'PASSED')
        e = next(r for r in result['revalidation_report'].items if r.claim_id == 'CL3')
        self.assertEqual(e.refs, ('E1',))
        self.assertEqual(result['revalidation_report'].items[-1].revision_text,
                         'Ask the supplier how the stated test applies to your planned cutting cycle.')
        self.assertIn('LOCAL_REVALIDATION_COMPLETE', self.client.get('/mvp/article.md?version=1').text)
        self.save(note='new version, same body')
        self.assertEqual(self.app.state.mvp_service.article()['validation_state'], 'PENDING_REVALIDATION')
        self.assertEqual(self.app.state.mvp_service.article('1')['validation_state'], 'LOCAL_REVALIDATION_COMPLETE')

    def test_native_rejects_numeric_cta_and_unknown_edit_is_not_semantic_proof(self):
        original = self.form()['body_text']
        cta = self.app.state.mvp_service.article()['review'].draft.claims[-1].text
        for replacement in ('Ask the supplier to confirm a rating of 12000 rpm.',
                            'Prepare an enquiry. All machines meet the requirement.',
                            'The test applies to every machining center.'):
            with self.subTest(replacement=replacement):
                self.save(body_text=original[:-len(cta)] + replacement)
                version = str(self.app.state.mvp_service.article()['selected_version'])
                self.assertEqual(self.client.post('/mvp/article/validation', data=self.validation_form(version)).status_code, 200)
                result = self.app.state.mvp_service.article(version)
                self.assertEqual(result['validation_state'], 'PENDING_REVALIDATION')
                self.assertEqual(result['revalidation_report'].items[-1].refs, ())
                if '12000' in replacement:
                    self.assertEqual(result['revalidation_report'].native_state, 'BLOCKED')

    def test_changed_facts_and_new_assertions_remain_pending_without_binding(self):
        original = self.form()['body_text']
        for body in (original.replace('7200 rpm', '12000 rpm'),
                     original.replace(' on an unloaded bench', ''),
                     original.replace('applies only to NCX7', 'applies to all models'),
                     original + '\n\nAll models have the same rating.'):
            with self.subTest(body=body[-80:]):
                self.save(body_text=body)
                version = str(self.app.state.mvp_service.article()['selected_version'])
                response = self.client.post('/mvp/article/validation', data=self.validation_form(version))
                self.assertEqual(response.status_code, 200)
                result = self.app.state.mvp_service.article(version)
                self.assertEqual(result['validation_state'], 'PENDING_REVALIDATION')
                self.assertFalse(result['revalidation_report'].eligible)
                if '12000' in body or ' on an unloaded bench' not in body or 'all models' in body:
                    self.assertEqual(next(r for r in result['revalidation_report'].items if r.claim_id == 'CL3').refs, ())

    def test_manual_review_required_stale_form_and_later_body_edit(self):
        self.save(note='one')
        form = self.validation_form()
        for changes in ({'note': ''}, {'confirmed': ''}, {'production_authorized': 'true'}, {'report_sha256': '0' * 64}):
            self.assertIn(self.client.post('/mvp/article/validation', data={**form, **changes}).status_code, (409, 422))
        self.save(body_text=self.form()['body_text'] + '\n\nMore text.')
        self.assertEqual(self.client.post('/mvp/article/validation', data=form).status_code, 409)
        self.assertEqual(self.app.state.mvp_service.article()['validation_state'], 'PENDING_REVALIDATION')

    def test_evidence_replacement_invalidates_completed_record_and_stale_submit(self):
        from tests.test_web_mvp import MVPWebTests
        self.save(note='one')
        form = self.validation_form()
        self.assertEqual(self.client.post('/mvp/article/validation', data=form).status_code, 200)
        self.assertEqual(self.app.state.mvp_service.article()['validation_state'], 'LOCAL_REVALIDATION_COMPLETE')
        evidence = MVPWebTests.form(self)
        self.client.post('/mvp/evidence', data={**evidence, 'content': 'replacement source', 'source_label': 'replacement'})
        self.assertEqual(self.app.state.mvp_service.article()['validation_state'], 'PENDING_REVALIDATION')
        self.assertEqual(self.client.post('/mvp/article/validation', data=form).status_code, 409)

    def test_e_to_p_s_forgery_and_locator_or_version_changes_fail_closed(self):
        from foreign_trade_geo_agent.core.draft_revalidation import revalidate_revision
        self.save(note='one')
        service = self.app.state.mvp_service
        article = service.article()
        session, reader, store, _, _ = service._load()
        current = service._current(store, session)
        draft = reader.get_artifact(session['candidate_artifact_id']).payload.drafts[0]
        review = article['review']
        claims = tuple(replace(c, customer_refs=(), page_refs=('P1',), source_refs=('S1',)) if c.claim_id == 'CL3' else c for c in review.draft.claims)
        forged = replace(review, draft=replace(review.draft, claims=claims))
        result = revalidate_revision(forged, article['selected_revision'], current, draft)
        self.assertFalse(result.eligible)
        self.assertEqual(next(r for r in result.items if r.claim_id == 'CL3').refs, ())
        for record in (replace(current.active_evidence[0], evidence_version=1),
                       replace(current.active_evidence[0], supplement=replace(current.active_evidence[0].supplement, source_locator='local:other'))):
            result = revalidate_revision(review, article['selected_revision'], replace(current, evidence=(record,)), draft)
            self.assertFalse(result.eligible)
            self.assertEqual(next(r for r in result.items if r.claim_id == 'CL3').refs, ())
        revoked = revalidate_revision(review, article['selected_revision'], replace(current, evidence=()), draft)
        self.assertFalse(revoked.eligible)
        self.assertEqual(next(r for r in revoked.items if r.claim_id == 'CL3').refs, ())

    def test_record_reopens_append_only_and_bad_csrf_rejected(self):
        from foreign_trade_geo_agent.web.mvp_application import MVPApplicationService
        self.save(note='one')
        form = self.validation_form()
        self.assertEqual(self.client.post('/mvp/article/validation', data={**form, 'csrf_token': 'bad'}).status_code, 403)
        self.assertEqual(self.client.post('/mvp/article/validation', data=form).status_code, 200)
        self.assertEqual(MVPApplicationService(self.package).article()['validation_state'], 'LOCAL_REVALIDATION_COMPLETE')
        with closing(sqlite3.connect(self.package / 'local-draft-revalidation.sqlite3')) as db:
            for action in ('DELETE FROM local_draft_revalidations', 'UPDATE local_draft_revalidations SET payload="{}"'):
                with self.assertRaises(sqlite3.DatabaseError):
                    db.execute(action)

    def test_changed_section_scope_does_not_keep_e1_binding(self):
        body = self.form()['body_text'].replace('## spindle performance', '## spindle performance for all NovaCNC models')
        self.save(body_text=body)
        self.client.post('/mvp/article/validation', data=self.validation_form())
        article = self.app.state.mvp_service.article()
        self.assertEqual(article['validation_state'], 'PENDING_REVALIDATION')
        self.assertEqual(next(r for r in article['revalidation_report'].items if r.claim_id == 'CL3').refs, ())

    def test_intake_cannot_change_between_report_check_and_record_append(self):
        from foreign_trade_geo_agent.storage.content_draft_review import SQLiteLocalRevalidationStore
        from foreign_trade_geo_agent.web.mvp_application import MVPError
        self.save(note='one')
        form = self.validation_form()
        service = self.app.state.mvp_service
        append = SQLiteLocalRevalidationStore.append
        evidence_changed = []
        def concurrent_submit(journal, record):
            try:
                service.submit(expected_sha256=form['expected_evidence_sha256'], content='replaced during save', source_label='race')
            except MVPError:
                pass
            else:
                evidence_changed.append(True)
            return append(journal, record)
        with patch.object(SQLiteLocalRevalidationStore, 'append', new=concurrent_submit):
            response = self.client.post('/mvp/article/validation', data=form)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(evidence_changed, [])
        self.assertEqual(service.article()['validation_state'], 'LOCAL_REVALIDATION_COMPLETE')


if __name__ == '__main__':
    unittest.main()
