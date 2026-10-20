"""V1.1 offline site/model boundaries and complete local HTTP business path."""
import asyncio
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient

from foreign_trade_geo_agent.adapters.deepseek_preview import DeepSeekPreviewConfig, DeepSeekPreviewWriter
from foreign_trade_geo_agent.adapters.preview_site import PreviewSiteConfig, preview_url
from foreign_trade_geo_agent.adapters.safe_http import SafeHtmlFetcher
from foreign_trade_geo_agent.commercial_preview_runtime import build_preview_runtime, FIXTURES, ORIGIN
from foreign_trade_geo_agent.core.commercial_preview import ExecutionConfirmation, digest, material, readiness
from foreign_trade_geo_agent.storage.commercial_preview import feedback_binding
from foreign_trade_geo_agent.web.commercial_preview import create_preview_app
from tests.test_commercial_preview import Forms, SAMPLES

SITE = 'https://company.example'
WEBSITE_QUOTE = 'Aster Fabrication supplies stainless steel enclosures for industrial equipment projects.'
KEY = 'sk-offline-preview-test-placeholder'
CONFIG = DeepSeekPreviewConfig(True, 'deepseek-flash', 10, 2048, 16384, .05, 1, 3)


class Resolver:
    def __init__(self, address='93.184.216.34'):
        self.address = address

    async def resolve(self, host, port):
        return (self.address,)


class MockBoundaries:
    def __init__(self, model_error=None, output_error=None, site_error=None):
        self.site_requests, self.model_requests = [], []
        self.model_error, self.output_error, self.site_error = model_error, output_error, site_error
        self.on_model = None

    def site(self, request):
        self.site_requests.append(str(request.url))
        if request.url.path == '/robots.txt':
            if self.site_error == 'robots_redirect':
                return httpx.Response(302, headers={'Location': '/private-robots.txt'})
            return httpx.Response(200, text='User-agent: *\nDisallow: /\n' if self.site_error == 'robots' else
                                  'User-agent: *\nAllow: /\n', headers={'Content-Type': 'text/plain'})
        if self.site_error in {'redirect', 'cross_origin', 'private_redirect'}:
            target = {'redirect': SITE+'/unauthorized', 'cross_origin': 'https://evil.example/',
                      'private_redirect': 'https://127.0.0.1/'}[self.site_error]
            return httpx.Response(302, headers={'Location': target})
        content = (FIXTURES/'index.html').read_text(encoding='utf-8')
        content = content.replace('</main>', '<a href="/outside">Outside authorization</a><a href="/product">Product</a></main>')
        if self.site_error == 'large':
            content = 'x' * 5000
        return httpx.Response(200, text=content, headers={'Content-Type': 'text/html'})

    async def model(self, request):
        self.model_requests.append(json.loads(request.content))
        if self.on_model:
            await self.on_model()
        if self.model_error == 'timeout':
            raise httpx.ReadTimeout('secret error ' + KEY, request=request)
        if self.model_error == 'network':
            raise httpx.ConnectError('secret error ' + KEY, request=request)
        if type(self.model_error) is int:
            return httpx.Response(self.model_error, json={'error': {'message': 'provider failure ' + KEY}})
        request_material = json.loads(self.model_requests[-1]['messages'][1]['content'])
        paragraphs = [dict(heading='Reviewed evidence', text=s['quote'], source_ids=[s['source_id']],
                           obligation_ids=[s['obligation_id']]) for s in request_material['reviewed_fragments']]
        output = dict(schema_version=1, title=request_material['task']['title'], paragraphs=paragraphs)
        if self.output_error == 'citation':
            output['paragraphs'][0]['source_ids'] = ['invented']
        if self.output_error == 'quantity':
            output['paragraphs'][0]['text'] += ' Our factory delivers 9999 units per day.'
        if self.output_error == 'semantic':
            output['paragraphs'][0]['text'] += ' Ask for a scoped discussion before selecting a configuration.'
        raw = 'not JSON' if self.output_error == 'json' else json.dumps(output)
        if self.output_error == 'duplicate':
            raw = raw.replace('"schema_version": 1', '"schema_version": 1, "schema_version": 1')
        if self.output_error == 'oversize':
            return httpx.Response(200, content=b'x' * 100000)
        envelope = dict(choices=[dict(message={'content': raw}, finish_reason='length' if self.output_error == 'truncated' else 'stop')],
                        usage=dict(prompt_tokens=3000, completion_tokens=700, total_tokens=3700))
        if self.output_error == 'secret':
            envelope['diagnostics'] = dict(api_key=KEY, password='DO-NOT-PERSIST-THIS', authorization='Bearer '+KEY)
        return httpx.Response(200, json=envelope)

    def flow(self, directory, *, config=CONFIG, site_config=None, address='93.184.216.34'):
        writer = DeepSeekPreviewWriter(config, transport=httpx.MockTransport(self.model))
        fetcher = lambda: SafeHtmlFetcher(resolver=Resolver(address), max_ip_attempts=1,
            max_wire_bytes=1024 if self.site_error == 'large' else 2*1024*1024,
            _transport_factory=lambda *_: httpx.MockTransport(self.site))
        return build_preview_runtime(directory, writer=writer, fetcher_factory=fetcher,
            site_config=site_config or PreviewSiteConfig(True, (SITE+'/', SITE+'/product')))


def args(state):
    return state['run_id'], state['revision'], digest(state)


def task(flow, state):
    return flow.confirm_task(*args(state), title='Aster Stainless Steel Enclosures: A Factual Overview',
        reader_question='What does Aster supply and what must a buyer confirm?',
        required_facts=('Describe the enclosure product.', 'Describe the fabrication capability.'),
        scope='Aster stainless steel enclosure fabrication for reviewed industrial equipment drawings.',
        limitations='Project-specific suitability, ratings and delivery must be separately confirmed.')


def evidence(flow, state, *, omit=None, reviews=True):
    for key, content in SAMPLES.items():
        if key != omit:
            state = flow.supplement(*args(state), obligation_id=key, content=content,
                                   label='Owner supplied evidence', locator='local://'+key)
    if reviews:
        for key in SAMPLES:
            spans = [s['span_id'] for s in state['spans'] if s['obligation_id'] == key]
            if spans:
                state = flow.review(*args(state), obligation_id=key, span_ids=spans,
                                    verdict='SUPPORTED', note='Reviewed exact text and applicable scope locally.')
    return state


class ModelTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = Path(self.enterContext(TemporaryDirectory()))
        self.enterContext(patch.dict('os.environ', {'DEEPSEEK_API_KEY': KEY}))
        self.mock = MockBoundaries()
        self.flow = self.mock.flow(self.directory)
        self.state = task(self.flow, await self.flow.analyze(ORIGIN+'/'))

    def ready(self):
        self.state = evidence(self.flow, self.state)
        self.state = self.flow.confirm_execution(*args(self.state))
        return ExecutionConfirmation(**self.state['confirmation'])

    async def test_nonthinking_request_matches_confirmed_policy(self):
        confirmation = self.ready()
        result = await self.flow.execute(self.state['run_id'], confirmation)
        self.assertEqual(result['result']['TECHNICAL'], 'SUCCEEDED')
        self.assertEqual(len(self.mock.model_requests), 1)
        sent = self.mock.model_requests[0]
        policy = self.state['execution_policy']
        self.assertEqual(sent.get('thinking'), {'type': 'disabled'})
        self.assertEqual(sent.get('temperature'), 0)
        self.assertEqual(policy.get('thinking'), sent['thinking'])
        self.assertEqual(policy.get('temperature'), sent['temperature'])
        self.assertEqual(result['result']['provider']['policy'], policy)

    async def test_legacy_unspecified_thinking_policy_requires_new_confirmation(self):
        legacy = self.flow.writer.policy()
        legacy.pop('thinking', None)
        legacy.pop('temperature', None)
        with patch.object(self.flow.writer, 'policy', return_value=legacy):
            self.state = task(self.flow, self.state)
            self.ready()
        with self.assertRaisesRegex(ValueError, 'PREVIEW_MODEL_POLICY_BINDING'):
            self.flow.confirm_execution(*args(self.state))
        self.assertEqual(self.mock.model_requests, [])

    async def test_mock_deepseek_complete_article_once_feedback_and_restart(self):
        confirmation = self.ready()
        result = await self.flow.execute(self.state['run_id'], confirmation)
        output = result['result']
        self.assertEqual(output['TECHNICAL'], 'SUCCEEDED')
        self.assertEqual(output['EVIDENCE'], 'NEEDS_REVIEW')
        self.assertTrue(300 <= output['word_count'] <= 500)
        self.assertEqual(output['provider']['usage']['total_tokens'], 3700)
        self.assertEqual(output['provider']['cost'], 'UNKNOWN')
        self.assertGreaterEqual(output['provider']['elapsed_seconds'], 0)
        self.assertIsNotNone(output['provider']['raw_response'])
        self.assertFalse(output['production_authorized'])
        await self.flow.execute(self.state['run_id'], confirmation)
        self.flow.store.feedback(self.state['run_id'], *feedback_binding(self.state, self.flow.store.attempt(self.state['run_id'])),
                                 str(uuid4()), 'Review before any production use.')
        restarted = self.mock.flow(self.directory)
        self.assertEqual(restarted.result(self.state['run_id']), result)
        await restarted.execute(self.state['run_id'], confirmation)
        self.assertEqual(len(self.mock.model_requests), 1)
        self.assertEqual(restarted.writer.calls, 0)
        self.assertEqual(len(restarted.store.list_feedback(self.state['run_id'])), 1)
        sent = json.loads(self.mock.model_requests[0]['messages'][1]['content'])
        self.assertEqual(sent['task'], self.state['task'])
        self.assertEqual(sent['request_digest'], confirmation.request_digest)
        self.assertNotIn(KEY, json.dumps(result))

    async def test_missing_evidence_no_http(self):
        self.state = evidence(self.flow, self.state, omit='limitations')
        with self.assertRaises(ValueError):
            self.flow.confirm_execution(*args(self.state))
        with self.assertRaises(ValueError):
            await self.flow.execute(self.state['run_id'], None)
        self.assertEqual(len(self.mock.model_requests), 0)

    async def test_unreviewed_no_http(self):
        self.state = evidence(self.flow, self.state, reviews=False)
        with self.assertRaises(ValueError):
            self.flow.confirm_execution(*args(self.state))
        self.assertEqual(len(self.mock.model_requests), 0)

    async def test_no_confirmation_cross_task_version_and_digests_no_http(self):
        confirmation = self.ready()
        for bad in (None, replace(confirmation, task_version=2), replace(confirmation, task_id=str(uuid4())),
                    replace(confirmation, run_id=str(uuid4())), replace(confirmation, evidence_digest='0'*64),
                    replace(confirmation, request_digest='0'*64)):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                await self.flow.execute(self.state['run_id'], bad)
        self.assertEqual(len(self.mock.model_requests), 0)

    async def test_corrupt_cross_task_evidence_or_review_no_http(self):
        confirmation = self.ready()
        for group, field, value in (('sources', 'task_id', str(uuid4())), ('reviews', 'task_version', 2),
                                     ('sources', 'content_sha256', '0'*64)):
            original = self.flow.store.read(self.state['run_id'])
            changed = json.loads(json.dumps(original))
            changed[group][0][field] = value
            with patch.object(self.flow.store, 'read', return_value=changed), self.assertRaises(ValueError):
                await self.flow.execute(self.state['run_id'], confirmation)
        self.assertEqual(len(self.mock.model_requests), 0)

    async def test_adapter_requires_preview_profile_confirmation_and_current_digests(self):
        self.ready()
        request = dict(material(self.state), confirmation=self.state['confirmation'])
        for field, value in (('profile', 'PRODUCTION'), ('confirmation', None), ('task_digest', '0'*64),
                              ('evidence_digest', '0'*64), ('execution_policy', {})):
            bad = dict(request, **{field: value})
            with self.subTest(field=field), self.assertRaises((ValueError, TypeError)):
                await self.flow.writer.generate(bad)
        self.assertEqual(len(self.mock.model_requests), 0)

    async def test_model_config_change_invalidates_old_confirmation(self):
        confirmation = self.ready()
        self.flow.writer = DeepSeekPreviewWriter(replace(CONFIG, max_output_tokens=1024), transport=httpx.MockTransport(self.mock.model))
        result = await self.flow.execute(self.state['run_id'], confirmation)
        self.assertNotEqual(result['result']['TECHNICAL'], 'SUCCEEDED')
        self.assertEqual(len(self.mock.model_requests), 0)

    async def test_disabled_or_missing_key_blocks_confirmation(self):
        self.state = evidence(self.flow, self.state)
        for enabled, key in ((False, KEY), (True, '')):
            with patch.dict('os.environ', {'DEEPSEEK_API_KEY': key}):
                mock = MockBoundaries()
                flow = mock.flow(self.directory, config=replace(CONFIG, enabled=enabled))
                state = flow.store.read(self.state['run_id'])
                state = task(flow, state)
                state = evidence(flow, state)
                with self.assertRaises(ValueError):
                    flow.confirm_execution(*args(state))
                self.assertEqual(len(mock.model_requests), 0)

    async def test_input_budget_prevents_http(self):
        self.flow.writer = DeepSeekPreviewWriter(replace(CONFIG, max_input_tokens=1024), transport=httpx.MockTransport(self.mock.model))
        self.state = task(self.flow, self.state)
        confirmation = self.ready()
        result = await self.flow.execute(self.state['run_id'], confirmation)
        self.assertNotEqual(result['result']['TECHNICAL'], 'SUCCEEDED')
        self.assertEqual(len(self.mock.model_requests), 0)

    async def test_unknown_timeout_and_network_never_retry(self):
        for error in ('timeout', 'network'):
            with self.subTest(error=error), TemporaryDirectory() as directory:
                mock = MockBoundaries(model_error=error)
                flow = mock.flow(Path(directory))
                state = evidence(flow, task(flow, await flow.analyze(ORIGIN+'/')))
                state = flow.confirm_execution(*args(state))
                confirmation = ExecutionConfirmation(**state['confirmation'])
                first = await flow.execute(state['run_id'], confirmation)
                self.assertEqual(first['result']['TECHNICAL'], 'UNKNOWN')
                self.assertIn(error.upper(), first['result']['failure'])
                await flow.execute(state['run_id'], confirmation)
                self.assertEqual(len(mock.model_requests), 1)
                self.assertNotIn(KEY, json.dumps(first))

    async def test_402_429_failures_have_real_http_status_and_no_retry(self):
        for error in (402, 429):
            with self.subTest(error=error), TemporaryDirectory() as directory:
                mock = MockBoundaries(model_error=error)
                flow = mock.flow(Path(directory))
                state = evidence(flow, task(flow, await flow.analyze(ORIGIN+'/')))
                state = flow.confirm_execution(*args(state))
                confirmation = ExecutionConfirmation(**state['confirmation'])
                first = await flow.execute(state['run_id'], confirmation)
                self.assertEqual(first['result']['TECHNICAL'], 'FAILED')
                self.assertEqual(first['result']['provider']['http_status'], error)
                await flow.execute(state['run_id'], confirmation)
                self.assertEqual(len(mock.model_requests), 1)
                self.assertNotIn(KEY, json.dumps(first))

    async def test_invalid_json_citations_quantities_and_semantic_uncertainty(self):
        for error in ('json', 'duplicate', 'citation', 'quantity', 'semantic', 'truncated', 'oversize'):
            with self.subTest(error=error), TemporaryDirectory() as directory:
                mock = MockBoundaries(output_error=error)
                flow = mock.flow(Path(directory))
                state = evidence(flow, task(flow, await flow.analyze(ORIGIN+'/')))
                state = flow.confirm_execution(*args(state))
                first = await flow.execute(state['run_id'], ExecutionConfirmation(**state['confirmation']))
                output = first['result']
                self.assertNotEqual(output['EVIDENCE'], 'PASS')
                self.assertEqual(output['EDITORIAL_REVIEW'], 'NEEDS_REVIEW')
                if error in {'citation', 'quantity'}:
                    self.assertEqual(output['EVIDENCE'], 'REJECTED')
                    self.assertIn('article', output)
                elif error == 'semantic':
                    self.assertEqual(output['EVIDENCE'], 'NEEDS_REVIEW')
                else:
                    self.assertEqual(output['TECHNICAL'], 'FAILED')
                self.assertEqual(len(mock.model_requests), 1)

    async def test_response_credentials_are_redacted(self):
        self.mock.output_error = 'secret'
        result = await self.flow.execute(self.state['run_id'], self.ready())
        self.assertNotIn(KEY, json.dumps(result))
        self.assertNotIn('DO-NOT-PERSIST-THIS', json.dumps(result))
        self.assertIn('[REDACTED]', result['result']['provider']['raw_response'])

    async def test_reservation_and_result_save_failures_never_false_success(self):
        confirmation = self.ready()
        with patch.object(self.flow.store, 'reserve', side_effect=sqlite3.OperationalError('controlled')):
            with self.assertRaises(sqlite3.OperationalError):
                await self.flow.execute(self.state['run_id'], confirmation)
        self.assertEqual(len(self.mock.model_requests), 0)
        with patch.object(self.flow.store, 'finish', side_effect=sqlite3.OperationalError('controlled')):
            with self.assertRaises(sqlite3.OperationalError):
                await self.flow.execute(self.state['run_id'], confirmation)
        self.assertIsNone(self.flow.result(self.state['run_id'])['result'])
        restarted = self.mock.flow(self.directory)
        self.assertIsNone((await restarted.execute(self.state['run_id'], confirmation))['result'])
        self.assertEqual(len(self.mock.model_requests), 1)

    async def test_evidence_change_during_model_keeps_stale_original(self):
        confirmation = self.ready()
        async def changed():
            self.state = self.flow.supplement(*args(self.state), obligation_id='fact-1', content='Additional fact.',
                                              label='Changed', locator='local://changed')
        self.mock.on_model = changed
        result = await self.flow.execute(self.state['run_id'], confirmation)
        self.assertEqual(result['freshness'], 'STALE')
        self.assertEqual(result['result']['TECHNICAL'], 'SUCCEEDED')
        with self.assertRaises(ValueError):
            await self.flow.execute(self.state['run_id'], confirmation)
        self.assertEqual(len(self.mock.model_requests), 1)

    async def test_concurrent_duplicate_requests_issue_one_http_call(self):
        confirmation = self.ready()
        self.mock.on_model = lambda: asyncio.sleep(.02)
        await asyncio.gather(*(self.flow.execute(self.state['run_id'], confirmation) for _ in range(3)))
        self.assertEqual(len(self.mock.model_requests), 1)


class SiteTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = Path(self.enterContext(TemporaryDirectory()))
        self.enterContext(patch.dict('os.environ', {'DEEPSEEK_API_KEY': KEY}))
        self.mock = MockBoundaries()
        self.flow = self.mock.flow(self.directory)

    async def analyze(self, **options):
        return await self.flow.analyze(SITE+'/', mode='REAL_SITE', allowed_urls=[SITE+'/', SITE+'/product'],
                                       site_authorized=True, **options)

    async def test_safe_real_site_packet_audit_topic_and_exact_source_binding(self):
        state = await self.analyze()
        self.assertEqual(state['analysis']['data_kind'], 'REAL')
        self.assertIsNotNone(state['analysis']['topic'])
        self.assertIn('audit', state['analysis'])
        self.assertEqual(set(self.mock.site_requests), {SITE+'/robots.txt', SITE+'/', SITE+'/product'})
        state = task(self.flow, state)
        source = state['sources'][0]
        self.assertEqual(source['source_type'], 'WEBSITE_SAMPLE')
        self.assertEqual(source['task_id'], state['task']['task_id'])
        self.assertEqual(len(source['page_digest']), 64)
        state = self.flow.bind_page(*args(state), source_id=source['source_id'], obligation_id='fact-1', quote=WEBSITE_QUOTE)
        self.assertEqual(state['spans'][0]['quote'], WEBSITE_QUOTE)
        self.assertTrue(readiness(state))
        with self.assertRaises(ValueError):
            self.flow.bind_page(*args(state), source_id=source['source_id'], obligation_id='fact-1', quote='invented quote')
        self.assertEqual(len(self.mock.model_requests), 0)

    async def test_site_disabled_unauthorized_and_out_of_grant_zero_http(self):
        for config, urls, ack in ((PreviewSiteConfig(), [SITE+'/'], True),
                                  (PreviewSiteConfig(True), [SITE+'/'], True),
                                  (PreviewSiteConfig(True, (SITE+'/',)), [SITE+'/'], False),
                                  (PreviewSiteConfig(True, (SITE+'/',)), [SITE+'/', SITE+'/outside'], True)):
            self.flow = self.mock.flow(self.directory, site_config=config)
            with self.subTest(config=config), self.assertRaises(ValueError):
                await self.flow.analyze(SITE+'/', mode='REAL_SITE', allowed_urls=urls, site_authorized=ack)
        self.assertEqual(self.mock.site_requests, [])

    async def test_invalid_https_and_private_addresses_zero_http(self):
        for url in ('http://company.example/', 'https://127.0.0.1/', 'https://10.0.0.1/', 'https://[::1]/',
                    'https://localhost/', 'https://u:p@company.example/', SITE+'/?key=secret',
                    SITE+'/#fragment', SITE+'/../private', SITE+'/%2fprivate'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                preview_url(url)
        self.assertEqual(self.mock.site_requests, [])

    async def test_private_dns_is_blocked_before_http(self):
        self.flow = self.mock.flow(self.directory, address='127.0.0.1')
        state = await self.analyze()
        self.assertIsNone(state['analysis']['topic'])
        self.assertEqual(self.mock.site_requests, [])

    async def test_robots_and_redirects_and_resource_limits_cannot_be_bypassed(self):
        for error in ('robots', 'robots_redirect', 'redirect', 'cross_origin', 'private_redirect', 'large'):
            with self.subTest(error=error), TemporaryDirectory() as directory:
                mock = MockBoundaries(site_error=error)
                flow = mock.flow(Path(directory))
                state = await flow.analyze(SITE+'/', mode='REAL_SITE', allowed_urls=[SITE+'/'], site_authorized=True)
                self.assertIsNone(state['analysis']['topic'])
                self.assertTrue(state['analysis']['crawl']['failures'])
                self.assertTrue(set(mock.site_requests) <= {SITE+'/robots.txt', SITE+'/'})
                if error in {'robots', 'robots_redirect'}:
                    self.assertEqual(mock.site_requests, [SITE+'/robots.txt'])

    async def test_cross_origin_grant_rejected_before_http(self):
        config = PreviewSiteConfig(True, (SITE+'/', 'https://other.example/'))
        self.flow = self.mock.flow(self.directory, site_config=config)
        with self.assertRaises(ValueError):
            await self.flow.analyze(SITE+'/', mode='REAL_SITE', allowed_urls=list(config.allowed_urls), site_authorized=True)
        self.assertEqual(self.mock.site_requests, [])


class ConfigTests(unittest.TestCase):
    def test_nonfinite_boolean_and_over_budget_configuration_rejected(self):
        for updates in ({'timeout_seconds': float('nan')}, {'budget_usd': float('inf')}, {'max_output_tokens': True},
                        {'input_usd_per_million_cap': -1}, {'budget_usd': .00001}, {'model': ''}):
            with self.subTest(updates=updates), self.assertRaises(ValueError):
                replace(CONFIG, **updates)


class WebTests(unittest.TestCase):
    def test_real_site_to_mock_deepseek_http_flow_and_restarted_read(self):
        with TemporaryDirectory() as directory, patch.dict('os.environ', {'DEEPSEEK_API_KEY': KEY}):
            mock = MockBoundaries()
            flow = mock.flow(Path(directory))
            with TestClient(create_preview_app(flow), base_url='http://127.0.0.1:8019') as client:
                def post(page, path, extra):
                    return client.post(path, data=dict(Forms(page.text).forms[path], **extra), follow_redirects=False)
                page = client.get('/')
                response = post(page, '/analyze', dict(website=SITE+'/', mode='REAL_SITE',
                    allowed_urls=SITE+'/', site_ack='yes'))
                self.assertEqual(response.status_code, 303)
                url = response.headers['location']
                page = client.get(url)
                self.assertIn('REAL', page.text)
                response = post(page, url+'/task', dict(title='Aster Stainless Steel Enclosures: A Factual Overview',
                    reader_question='What does Aster supply and what must a buyer confirm?',
                    fact_0='Describe the enclosure product.', fact_1='Describe the fabrication capability.',
                    scope='Aster stainless steel enclosure fabrication for reviewed industrial equipment drawings.',
                    limitations='Project-specific suitability, ratings and delivery must be separately confirmed.', task_ack='yes'))
                self.assertEqual(response.status_code, 303)
                page = client.get(url)
                run = url.split('/')[-1]
                source = flow.store.read(run)['sources'][0]
                response = post(page, url+'/bind-page', dict(source_id=source['source_id'], obligation_id='fact-1', quote=WEBSITE_QUOTE))
                self.assertEqual(response.status_code, 303)
                page = client.get(url)
                for key, value in SAMPLES.items():
                    self.assertEqual(post(page, url+'/evidence', dict(obligation_id=key, content=value,
                        label='Owner local document', locator='local://'+key)).status_code, 303)
                    page = client.get(url)
                for key in SAMPLES:
                    state = flow.store.read(run)
                    spans = [s['span_id'] for s in state['spans'] if s['obligation_id'] == key]
                    self.assertEqual(post(page, url+'/review', dict(obligation_id=key, span_id=spans, verdict='SUPPORTED',
                        note='Exact fragments checked locally.', review_ack='LOCAL_PREVIEW_REVIEW')).status_code, 303)
                    page = client.get(url)
                self.assertEqual(len(mock.model_requests), 0)
                self.assertEqual(post(page, url+'/confirm', dict(execution_ack='yes')).status_code, 303)
                page = client.get(url)
                fields = Forms(page.text).forms[url+'/generate']
                for _ in range(2):
                    self.assertEqual(client.post(url+'/generate', data=fields, follow_redirects=False).status_code, 303)
                page = client.get(url)
                self.assertIn('<article>', page.text)
                self.assertIn('NEEDS_REVIEW', page.text)
                self.assertIn('UNKNOWN', page.text)
                self.assertEqual(post(page, url+'/feedback', dict(note='V1.1 local HTTP acceptance feedback.')).status_code, 303)
                self.assertIn('V1.1 local HTTP acceptance feedback.', client.get(url).text)
                self.assertEqual(len(mock.model_requests), 1)
            restarted = mock.flow(Path(directory))
            with TestClient(create_preview_app(restarted), base_url='http://127.0.0.1:8019') as client:
                self.assertIn('<article>', client.get(url).text)
                self.assertIn('V1.1 local HTTP acceptance feedback.', client.get(url).text)
                self.assertEqual(restarted.writer.calls, 0)

    def test_web_disabled_states_and_unauthorized_real_site_no_http(self):
        with TemporaryDirectory() as directory, patch.dict('os.environ', {'DEEPSEEK_API_KEY': KEY}):
            mock = MockBoundaries()
            flow = mock.flow(Path(directory), config=replace(CONFIG, enabled=False), site_config=PreviewSiteConfig())
            with TestClient(create_preview_app(flow), base_url='http://127.0.0.1:8019') as client:
                self.assertIn('NOT_ENABLED', client.get('/').text)
                page = client.get('/')
                fields = dict(Forms(page.text).forms['/analyze'], website=SITE+'/', mode='REAL_SITE', allowed_urls=SITE+'/', site_ack='yes')
                response = client.post('/analyze', data=fields)
                self.assertEqual(response.status_code, 409)
                self.assertIn('NOT_ENABLED', response.text)
                self.assertEqual(mock.site_requests, [])
                self.assertEqual(mock.model_requests, [])


if __name__ == '__main__':
    unittest.main()
