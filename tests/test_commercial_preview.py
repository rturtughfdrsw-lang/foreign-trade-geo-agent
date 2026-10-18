"""Offline Preview admission, single execution, evidence output and durable Web flow."""
import asyncio
from dataclasses import asdict, replace
from html.parser import HTMLParser
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from foreign_trade_geo_agent.commercial_preview_runtime import build_preview_runtime, ORIGIN
from foreign_trade_geo_agent.core.commercial_preview import (
    ExecutionConfirmation, admit, digest, evidence_digest, readiness, request_digest,
)
from foreign_trade_geo_agent.storage.commercial_preview import SQLitePreviewStore, feedback_binding
from foreign_trade_geo_agent.web.commercial_preview import create_preview_app

SAMPLES = json.loads((Path(__file__).parent/'fixtures/commercial_preview.json').read_text(encoding='utf-8'))


class PreviewTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = self.enterContext(TemporaryDirectory())
        self.directory = Path(self.temp)
        self.flow = build_preview_runtime(self.directory)
        self.state = await self.flow.analyze(ORIGIN+'/')
        self.state = self.flow.confirm_task(*self.args(), title='Aster Stainless Steel Enclosures: A Factual Overview',
            reader_question='What does Aster supply and what must a buyer confirm?',
            required_facts=('Describe the enclosure product.', 'Describe the fabrication capability.'),
            scope='Aster stainless steel enclosure fabrication for reviewed industrial equipment drawings.',
            limitations='Project-specific suitability, ratings and delivery must be separately confirmed.')

    def args(self):
        return self.state['run_id'], self.state['revision'], digest(self.state)

    def reload(self):
        self.state = self.flow.store.read(self.state['run_id'])

    def supply(self, omit=None):
        for key, content in SAMPLES.items():
            if key != omit:
                self.state = self.flow.supplement(*self.args(), obligation_id=key, content=content,
                                                   label='SYNTHETIC test', locator='fixture://'+key)

    def review_all(self):
        for key in SAMPLES:
            spans = [s['span_id'] for s in self.state['spans'] if s['obligation_id'] == key]
            if spans:
                self.state = self.flow.review(*self.args(), obligation_id=key, span_ids=spans,
                                              verdict='SUPPORTED', note='Locally checked exact text and scope.')

    def confirm(self):
        self.state = self.flow.confirm_execution(*self.args())
        return ExecutionConfirmation(**self.state['confirmation'])

    async def ready(self):
        self.supply()
        self.review_all()
        return self.confirm()

    async def test_complete_article_sources_feedback_restart_and_idempotence(self):
        confirmation = await self.ready()
        self.assertEqual(readiness(self.state), [])
        result = await self.flow.execute(self.state['run_id'], confirmation)
        self.assertEqual(self.flow.writer.calls, 1)
        output = result['result']
        self.assertEqual(output['TECHNICAL'], 'SUCCEEDED')
        self.assertEqual(output['EVIDENCE'], 'NEEDS_REVIEW')
        self.assertEqual(output['EDITORIAL_REVIEW'], 'NEEDS_REVIEW')
        self.assertEqual(output['PRODUCTION_AUTHORIZATION'], 'NOT_AUTHORIZED')
        self.assertFalse(output['production_authorized'])
        self.assertTrue(300 <= output['word_count'] <= 500)
        self.assertEqual(len(output['article']['paragraphs']), 5)
        self.assertEqual({i for p in output['article']['paragraphs'] for i in p['source_ids']},
                         {s['source_id'] for s in self.state['sources']})
        binding = feedback_binding(self.state, self.flow.store.attempt(self.state['run_id']))
        self.flow.store.feedback(self.state['run_id'], *binding, str(uuid4()), 'Check the wording before use.')
        again = await self.flow.execute(self.state['run_id'], confirmation)
        self.assertEqual(result, again)
        self.assertEqual(self.flow.writer.calls, 1)
        restarted = build_preview_runtime(self.directory)
        self.assertEqual(restarted.result(self.state['run_id']), result)
        await restarted.execute(self.state['run_id'], confirmation)
        self.assertEqual(restarted.writer.calls, 0)
        self.assertEqual(len(restarted.store.list_feedback(self.state['run_id'])), 1)

    async def test_missing_exact_requirement_does_not_change_task_or_call_writer(self):
        self.supply(omit='limitations')
        self.review_all()
        before = self.state['task']
        self.assertTrue(any('limitations: 请补充' in gap for gap in readiness(self.state)))
        with self.assertRaises(ValueError):
            self.confirm()
        with self.assertRaises(ValueError):
            await self.flow.execute(self.state['run_id'], None)
        self.assertEqual(self.flow.store.read(self.state['run_id'])['task'], before)
        self.assertEqual(self.flow.writer.calls, 0)

    async def test_upload_and_supported_boolean_cannot_replace_human_review(self):
        self.supply()
        self.assertEqual(len(readiness(self.state)), 5)
        with self.assertRaises(ValueError):
            self.confirm()
        with self.assertRaises(ValueError):
            self.flow.review(*self.args(), obligation_id='fact-1', span_ids=[self.state['spans'][1]['span_id']],
                             verdict=True, note='supported=true')
        self.assertEqual(self.flow.writer.calls, 0)

    async def test_conflict_blocks_execution(self):
        self.supply()
        self.review_all()
        span = self.state['spans'][0]
        self.state = self.flow.review(*self.args(), obligation_id=span['obligation_id'], span_ids=[span['span_id']],
                                      verdict='CONFLICT', note='Scope conflict remains unresolved.')
        self.assertTrue(any('冲突' in gap for gap in readiness(self.state)))
        with self.assertRaises(ValueError):
            self.confirm()
        self.assertEqual(self.flow.writer.calls, 0)

    async def test_review_cannot_omit_an_additional_candidate_source(self):
        self.supply()
        old_span = self.state['spans'][1]['span_id']
        self.state = self.flow.supplement(*self.args(), obligation_id='fact-1', content='A competing synthetic record.',
                                          label='Second candidate', locator='fixture://second')
        with self.assertRaises(ValueError):
            self.flow.review(*self.args(), obligation_id='fact-1', span_ids=[old_span],
                             verdict='SUPPORTED', note='Only checked the first record.')
        self.assertEqual(self.flow.writer.calls, 0)

    async def test_confirmation_binding_matrix_and_no_confirmation(self):
        confirmation = await self.ready()
        for value in (None, replace(confirmation, task_version=2), replace(confirmation, task_id=str(uuid4())),
                      replace(confirmation, run_id=str(uuid4())), replace(confirmation, evidence_digest='0'*64),
                      replace(confirmation, request_digest='0'*64), replace(confirmation, confirmation_id=str(uuid4()))):
            with self.subTest(confirmation=value):
                with self.assertRaises(ValueError):
                    await self.flow.execute(self.state['run_id'], value)
        self.assertEqual(self.flow.writer.calls, 0)
        self.assertIsNone(self.flow.store.attempt(self.state['run_id']))

    async def test_evidence_change_invalidates_confirmation_and_precise_spans(self):
        confirmation = await self.ready()
        self.state = self.flow.supplement(*self.args(), obligation_id='fact-1', content='Additional synthetic fact.',
                                          label='Changed document', locator='fixture://changed')
        with self.assertRaises(ValueError):
            await self.flow.execute(self.state['run_id'], confirmation)
        self.assertEqual(self.flow.writer.calls, 0)
        bad = json.loads(json.dumps(self.state))
        bad['sources'][0]['content'] += 'tampering'
        with self.assertRaises(ValueError):
            readiness(bad)
        bad = json.loads(json.dumps(self.state))
        bad['spans'][0]['start'] = 1
        with self.assertRaises(ValueError):
            readiness(bad)

    async def test_cross_task_source_and_review_binding(self):
        await self.ready()
        for field in ('sources', 'reviews'):
            bad = json.loads(json.dumps(self.state))
            bad[field][0]['task_id'] = str(uuid4())
            with self.assertRaises(ValueError):
                admit(bad, ExecutionConfirmation(**self.state['confirmation']))
        self.assertEqual(self.flow.writer.calls, 0)

    async def test_old_task_version_and_removal_cannot_narrow_task(self):
        confirmation = await self.ready()
        task = self.state['task']
        with self.assertRaises(ValueError):
            self.flow.confirm_task(*self.args(), title=task['title'], reader_question=task['reader_question'],
                required_facts=(task['required_facts'][0],), scope=task['scope'], limitations=task['limitations'])
        self.state = self.flow.confirm_task(*self.args(), title=task['title'], reader_question=task['reader_question'],
            required_facts=task['required_facts'], scope=task['scope'], limitations=task['limitations'])
        self.assertEqual(self.state['task']['version'], 2)
        with self.assertRaises(ValueError):
            await self.flow.execute(self.state['run_id'], confirmation)
        self.assertEqual(self.flow.writer.calls, 0)

    async def test_bad_source_quantity_collection_and_missing_question_preserve_original(self):
        confirmation = await self.ready()
        original = await self.flow.writer.generate({k: self.state[k] for k in ('task','sources','spans','reviews')})
        self.flow.writer.calls = 0
        for kind in ('source', 'quantity', 'collection', 'question', 'approval', 'malformed'):
            with self.subTest(kind=kind):
                article = json.loads(original)
                if kind == 'source':
                    article['paragraphs'][0]['source_ids'] = [str(uuid4())]
                elif kind == 'quantity':
                    article['paragraphs'][0]['text'] += ' Aster delivers 9999 units per day.'
                elif kind == 'collection':
                    article['paragraphs'][0]['text'] += ' Aster offers two configurations.'
                elif kind == 'question':
                    article['paragraphs'].pop(0)
                elif kind == 'approval':
                    article['production_authorized'] = True
                raw = 'not json' if kind == 'malformed' else json.dumps(article)
                from foreign_trade_geo_agent.core.commercial_preview import parse_article
                if kind in {'approval', 'malformed'}:
                    with self.assertRaises(ValueError):
                        parse_article(raw, self.state)
                else:
                    result = parse_article(raw, self.state)
                    self.assertEqual(result['EVIDENCE'], 'REJECTED')
                    self.assertEqual(result['article'], article)
        class BadWriter:
            calls = 0
            async def generate(inner, request):
                inner.calls += 1
                return 'not json'
        self.flow.writer = BadWriter()
        result = await self.flow.execute(self.state['run_id'], confirmation)
        self.assertEqual(result['result']['raw'], 'not json')
        self.assertEqual(result['result']['TECHNICAL'], 'FAILED')

    async def test_change_during_generation_preserves_stale_result_and_blocks_repeat(self):
        confirmation = await self.ready()
        writer = self.flow.writer
        async def changing(request):
            self.state = self.flow.supplement(*self.args(), obligation_id='fact-1', content='Updated fact.',
                                              label='Update', locator='fixture://new')
            return await writer.generate(request)
        with patch.object(self.flow, 'writer') as delegate:
            delegate.generate = changing
            result = await self.flow.execute(self.state['run_id'], confirmation)
        self.assertEqual(result['freshness'], 'STALE')
        self.assertEqual(result['result']['TECHNICAL'], 'SUCCEEDED')
        self.assertEqual(len(result['material']['sources']), 5)
        with self.assertRaises(ValueError):
            await self.flow.execute(self.state['run_id'], confirmation)
        self.assertEqual(writer.calls, 1)

    async def test_invalid_model_source_is_saved_rejected_with_one_writer_call(self):
        confirmation = await self.ready()
        generate = self.flow.writer.generate
        async def bad_source(request):
            value = json.loads(await generate(request))
            value['paragraphs'][0]['source_ids'] = ['invented-source']
            return json.dumps(value)
        self.flow.writer.generate = bad_source
        result = await self.flow.execute(self.state['run_id'], confirmation)
        self.assertEqual(result['result']['EVIDENCE'], 'REJECTED')
        self.assertIn('invented-source', result['result']['raw'])
        self.assertEqual(self.flow.writer.calls, 1)
        await self.flow.execute(self.state['run_id'], confirmation)
        self.assertEqual(self.flow.writer.calls, 1)

    async def test_unsupported_model_quantity_is_saved_rejected_without_rewrite(self):
        confirmation = await self.ready()
        generate = self.flow.writer.generate
        async def bad_quantity(request):
            value = json.loads(await generate(request))
            value['paragraphs'][0]['text'] += ' Aster delivers 9999 units per day.'
            return json.dumps(value)
        self.flow.writer.generate = bad_quantity
        result = await self.flow.execute(self.state['run_id'], confirmation)
        self.assertEqual(result['result']['EVIDENCE'], 'REJECTED')
        self.assertIn('9999 units per day', result['result']['article']['paragraphs'][0]['text'])
        self.assertEqual(self.flow.writer.calls, 1)

    async def test_boolean_schema_and_preview_production_authority_are_rejected(self):
        confirmation = await self.ready()
        for mutate in ('schema', 'authority'):
            bad = json.loads(json.dumps(self.state))
            if mutate == 'schema':
                bad['task']['schema_version'] = True
            else:
                bad['production_authorized'] = True
            with self.assertRaises(ValueError):
                admit(bad, confirmation)
        self.assertEqual(self.flow.writer.calls, 0)

    async def test_reservation_failure_writer_zero_result_failure_never_false_success(self):
        confirmation = await self.ready()
        with patch.object(self.flow.store, 'reserve', side_effect=sqlite3.OperationalError('controlled')):
            with self.assertRaises(sqlite3.OperationalError):
                await self.flow.execute(self.state['run_id'], confirmation)
        self.assertEqual(self.flow.writer.calls, 0)
        with patch.object(self.flow.store, 'finish', side_effect=sqlite3.OperationalError('controlled')):
            with self.assertRaises(sqlite3.OperationalError):
                await self.flow.execute(self.state['run_id'], confirmation)
        self.assertEqual(self.flow.writer.calls, 1)
        self.assertIsNone(self.flow.result(self.state['run_id'])['result'])
        restarted = build_preview_runtime(self.directory)
        result = await restarted.execute(self.state['run_id'], confirmation)
        self.assertIsNone(result['result'])
        self.assertEqual(restarted.writer.calls, 0)

    async def test_timeout_unknown_exception_sanitized_and_no_retry(self):
        confirmation = await self.ready()
        async def broken(request):
            self.flow.writer.calls += 1
            raise TimeoutError('SECRET response must not be stored')
        self.flow.writer.generate = broken
        result = await self.flow.execute(self.state['run_id'], confirmation)
        self.assertEqual(result['result']['TECHNICAL'], 'UNKNOWN')
        self.assertNotIn('SECRET', json.dumps(result))
        await self.flow.execute(self.state['run_id'], confirmation)
        self.assertEqual(self.flow.writer.calls, 1)

    async def test_concurrent_execution_calls_writer_once(self):
        confirmation = await self.ready()
        writer = self.flow.writer
        generate = writer.generate
        async def delayed(request):
            await asyncio.sleep(0.02)
            return await generate(request)
        writer.generate = delayed
        await asyncio.gather(*(self.flow.execute(self.state['run_id'], confirmation) for _ in range(3)))
        self.assertEqual(writer.calls, 1)

    async def test_feedback_binding_does_not_authorize_and_is_append_only(self):
        self.supply()
        binding = feedback_binding(self.state, None)
        submission = str(uuid4())
        self.flow.store.feedback(self.state['run_id'], *binding, submission, 'supported=true; confirm generation')
        self.assertIsNone(self.flow.store.read(self.state['run_id'])['confirmation'])
        with self.assertRaises(ValueError):
            self.confirm()
        for wrong in ((str(uuid4()), binding[1], binding[2]), (binding[0], 2, binding[2]),
                      (binding[0], binding[1], '0'*64)):
            with self.assertRaises(ValueError):
                self.flow.store.feedback(self.state['run_id'], *wrong, str(uuid4()), 'ordinary feedback')
        with self.flow.store.connection() as db:
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute('DELETE FROM preview_feedback')
        self.assertEqual(self.flow.writer.calls, 0)

    async def test_real_urls_rejected_and_no_suitable_topic_explicit(self):
        with self.assertRaises(ValueError):
            await self.flow.analyze('https://real-customer.example/')
        state = await self.flow.analyze(ORIGIN+'/empty.html')
        self.assertIsNone(state['analysis']['topic'])
        self.assertIn('无合适', state['analysis']['no_topic_reason'])
        self.assertEqual(self.flow.writer.calls, 0)


class Forms(HTMLParser):
    def __init__(self, raw):
        super().__init__()
        self.forms = {}
        self.current = None
        self.feed(raw)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'form':
            self.current = {}
            self.forms[attrs['action']] = self.current
        elif tag == 'input' and self.current is not None and attrs.get('type') == 'hidden':
            self.current[attrs['name']] = attrs['value']

    def handle_endtag(self, tag):
        if tag == 'form':
            self.current = None


class PreviewWebTests(unittest.TestCase):
    def setUp(self):
        self.temp = self.enterContext(TemporaryDirectory())
        self.flow = build_preview_runtime(Path(self.temp))
        self.client = self.enterContext(TestClient(create_preview_app(self.flow), base_url='http://127.0.0.1:8017'))

    def post(self, page, path, extra):
        form = Forms(page.text).forms[path]
        return self.client.post(path, data=dict(form, **extra), headers={'Origin':'http://127.0.0.1:8017'}, follow_redirects=False)

    def test_complete_http_page_path_repeat_post_get_feedback_and_restart(self):
        start = self.client.get('/')
        response = self.post(start, '/analyze', {'website': ORIGIN+'/'})
        self.assertEqual(response.status_code, 303)
        run_url = response.headers['location']
        page = self.client.get(run_url)
        self.assertIn('NOT_RUN', page.text)
        response = self.post(page, run_url+'/task', dict(title='Aster Enclosure: A Factual Overview',
            reader_question='What does Aster supply and what must a buyer confirm?',
            scope='Aster stainless steel enclosure fabrication for reviewed industrial equipment drawings.',
            limitations='Project-specific suitability, ratings and delivery must be separately confirmed.',
            fact_0='Describe the enclosure product.', fact_1='Describe the fabrication capability.', task_ack='yes'))
        self.assertEqual(response.status_code, 303)
        page = self.client.get(run_url)
        self.assertIn('limitations: 请补充', page.text)
        self.assertNotIn('执行已确认的单次预览', page.text)
        for key, content in SAMPLES.items():
            response = self.post(page, run_url+'/evidence', dict(obligation_id=key, content=content,
                label='SYNTHETIC local document', locator='fixture://'+key))
            self.assertEqual(response.status_code, 303)
            page = self.client.get(run_url)
        run_id = run_url.split('/')[-1]
        for key in SAMPLES:
            state = self.flow.store.read(run_id)
            spans = [s['span_id'] for s in state['spans'] if s['obligation_id'] == key]
            response = self.post(page, run_url+'/review', dict(obligation_id=key, span_id=spans,
                verdict='SUPPORTED', note='I checked the precise text and scope.', review_ack='LOCAL_PREVIEW_REVIEW'))
            self.assertEqual(response.status_code, 303)
            page = self.client.get(run_url)
        self.assertEqual(self.flow.writer.calls, 0)
        response = self.post(page, run_url+'/confirm', {'execution_ack':'yes'})
        self.assertEqual(response.status_code, 303)
        page = self.client.get(run_url)
        form = Forms(page.text).forms[run_url+'/generate']
        for _ in range(2):
            response = self.client.post(run_url+'/generate', data=form, follow_redirects=False)
            self.assertEqual(response.status_code, 303)
        page = self.client.get(run_url)
        self.assertIn('<article>', page.text)
        self.assertIn('NEEDS_REVIEW', page.text)
        self.assertIn('NOT_AUTHORIZED', page.text)
        self.assertEqual(self.flow.writer.calls, 1)
        self.assertEqual(self.post(page, run_url+'/feedback', {'note':'Browser-style HTTP feedback.'}).status_code, 303)
        self.assertIn('Browser-style HTTP feedback.', self.client.get(run_url).text)
        restarted = build_preview_runtime(Path(self.temp))
        with TestClient(create_preview_app(restarted), base_url='http://127.0.0.1:8017') as client:
            self.assertIn('<article>', client.get(run_url).text)
            self.assertIn('Browser-style HTTP feedback.', client.get(run_url).text)
            self.assertEqual(restarted.writer.calls, 0)

    def test_request_integrity_and_payload_bound(self):
        page = self.client.get('/')
        fields = Forms(page.text).forms['/analyze']
        for origin in ('null', 'https://evil.example', 'http://127.0.0.1:8003'):
            result = self.client.post('/analyze', data=dict(fields, website=ORIGIN+'/'), headers={'Origin':origin})
            self.assertEqual(result.status_code, 403)
        self.assertEqual(self.client.post('/analyze', data=dict(fields, website=ORIGIN+'/', csrf_token='wrong')).status_code, 403)
        self.assertEqual(self.client.post('/analyze', content='x'*100001,
            headers={'Content-Type':'application/x-www-form-urlencoded'}).status_code, 413)
        self.assertEqual(self.flow.store.list_runs(), [])
        self.assertEqual(self.flow.writer.calls, 0)


if __name__ == '__main__':
    unittest.main()
