"""Review UI contract exercised through isolated HTTP requests and SQLite."""
import asyncio
from html.parser import HTMLParser
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from foreign_trade_geo_agent.commercial_preview_runtime import build_preview_runtime, ORIGIN
from foreign_trade_geo_agent.core.commercial_preview import digest, readiness
from foreign_trade_geo_agent.web.commercial_preview import create_preview_app
from tests.test_commercial_preview import Forms, SAMPLES


class Controls(HTMLParser):
    def __init__(self, raw):
        super().__init__()
        self.controls = []
        self.feed(raw)

    def handle_starttag(self, tag, attrs):
        self.controls.append((tag, dict(attrs)))


class ReviewUITests(unittest.TestCase):
    def setUp(self):
        directory = Path(self.enterContext(TemporaryDirectory()))
        self.flow = build_preview_runtime(directory)
        state = asyncio.run(self.flow.analyze(ORIGIN+'/'))
        state = self.flow.confirm_task(state['run_id'], state['revision'], digest(state),
            title='Aster enclosure facts', reader_question='What does Aster supply?',
            required_facts=('Describe the enclosure product.', 'Describe the fabrication capability.'),
            scope='Industrial equipment drawings.', limitations='Confirm project suitability separately.')
        for key, content in SAMPLES.items():
            state = self.flow.supplement(state['run_id'], state['revision'], digest(state),
                obligation_id=key, content=content, label='Local evidence', locator='fixture://'+key)
        state = self.flow.supplement(state['run_id'], state['revision'], digest(state),
            obligation_id='reader-question', content=SAMPLES['reader-question'],
            label='Second candidate', locator='fixture://second')
        self.run = state['run_id']
        self.url = '/runs/'+self.run
        self.client = self.enterContext(TestClient(create_preview_app(self.flow), base_url='http://127.0.0.1:8017'))

    def state(self):
        return self.flow.store.read(self.run)

    def submit(self, key='reader-question', verdict='SUPPORTED', **overrides):
        page = self.client.get(self.url)
        fields = Forms(page.text).forms[self.url+'/review']
        fields.update(obligation_id=key, verdict=verdict, note='已核对 <script> & 原文',
            review_ack='LOCAL_PREVIEW_REVIEW', span_id=[s['span_id'] for s in self.state()['spans'] if s['obligation_id']==key])
        fields.update(overrides)
        return self.client.post(self.url+'/review', data=fields, follow_redirects=False)

    def card(self, raw, key):
        return raw.split('id="review-'+key+'"', 1)[1].split('</section>', 1)[0]

    def test_saved_verdict_note_and_all_spans_restored(self):
        for verdict, label in [('SUPPORTED','已核对：证据支持这项写法'), ('CONFLICT','已核对：发现证据冲突'), ('UNRESOLVED','已核对：暂时无法判断')]:
            with self.subTest(verdict=verdict):
                before = self.state()['revision']
                response = self.submit(verdict=verdict)
                self.assertEqual(response.status_code, 303)
                self.assertEqual(self.state()['revision'], before+1)
                self.assertIn('#review-reader-question', response.headers['location'])
                page = self.client.get(response.headers['location'])
                self.assertIn('已保存本项核对。', page.text)
                card = self.card(page.text, 'reader-question')
                self.assertIn(label, card)
                controls = Controls(card).controls
                self.assertTrue(any(t=='option' and a.get('value')==verdict and 'selected' in a for t,a in controls))
                spans = [a for t,a in controls if a.get('name')=='span_id']
                self.assertEqual(len(spans), 2)
                self.assertTrue(all('checked' in a for a in spans))
                self.assertIn('已核对 &lt;script&gt; &amp; 原文', card)
                self.assertTrue(all('checked' not in a for t,a in controls if a.get('name')=='review_ack'))

    def test_unreviewed_has_no_selected_verdict_or_checked_spans(self):
        card = self.card(self.client.get(self.url).text, 'fact-1')
        self.assertIn('尚未核对', card)
        controls = Controls(card).controls
        self.assertFalse(any('checked' in a for t,a in controls))
        self.assertFalse(any(t=='option' and a.get('value') in {'SUPPORTED','CONFLICT','UNRESOLVED'} and 'selected' in a for t,a in controls))

    def test_all_five_are_independent_and_do_not_authorize_production(self):
        for count, key in enumerate(SAMPLES, 1):
            old_reviews = self.state()['reviews']
            response = self.submit(key)
            self.assertEqual(response.status_code, 303)
            state = self.state()
            self.assertEqual(len(state['reviews']), count)
            for review in old_reviews:
                self.assertIn(review, state['reviews'])
            self.assertIn('已核对 '+str(count)+'/5 项', self.client.get(self.url).text)
            self.assertFalse(state['production_authorized'])
            self.assertIsNone(state['confirmation'])
        self.assertEqual(readiness(self.state()), [])
        self.assertEqual(self.flow.writer.calls, 0)

    def test_failed_save_has_reason_and_no_success_or_snapshot(self):
        before = self.state()
        cases = [dict(span_id=[]), dict(review_ack=''), dict(state_digest='0'*64), dict(note=''), dict(note='x'*1001)]
        for fields in cases:
            with self.subTest(fields=fields):
                response = self.submit(**fields)
                self.assertEqual(response.status_code, 409)
                self.assertIn('未保存', response.text)
                self.assertNotIn('已保存本项核对。', response.text)
                self.assertEqual(self.state(), before)
        response = self.submit(csrf_token='wrong')
        self.assertEqual(response.status_code, 403)
        self.assertIn('请求未保存', response.text)
        self.assertNotIn('已保存本项核对。', response.text)
        self.assertEqual(self.state(), before)
        with patch.object(self.flow.store, 'save', side_effect=OSError('private detail')):
            response = self.submit()
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('已保存本项核对。', response.text)
        self.assertNotIn('private detail', response.text)

    def test_success_cannot_be_forged_or_reused_after_state_change(self):
        self.assertNotIn('已保存本项核对。', self.client.get(self.url+'?saved=reader-question').text)
        location = self.submit().headers['location']
        self.assertIn('已保存本项核对。', self.client.get(location).text)
        self.submit('fact-1')
        self.assertNotIn('已保存本项核对。', self.client.get(location).text)
        malformed = self.url+'?saved=reader-question&saved_revision='+str(self.state()['revision'])+'&receipt='+('汉'*64)
        response = self.client.get(malformed)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('已保存本项核对。', response.text)

    def test_traceability_collapsed_and_evidence_change_clears_ui(self):
        self.submit()
        page = self.client.get(self.url).text
        self.assertIn('技术详情', page)
        self.assertIn('查看完整原文', page)
        self.assertIn('共 2 条证据', page)
        self.assertIn(digest(self.state()), page)
        self.assertIn('LOCAL_PREVIEW_REVIEW', page)
        for tag, attrs in Controls(page).controls:
            if tag == 'details':
                self.assertNotIn('open', attrs)
        for span in self.state()['spans']:
            self.assertIn(span['span_id'], page)
        state = self.state()
        self.flow.supplement(self.run, state['revision'], digest(state), obligation_id='fact-1',
            content=SAMPLES['fact-1'], label='Additional evidence', locator='fixture://extra')
        card = self.card(self.client.get(self.url).text, 'reader-question')
        self.assertIn('尚未核对', card)
        self.assertFalse(any('checked' in a for t,a in Controls(card).controls))
