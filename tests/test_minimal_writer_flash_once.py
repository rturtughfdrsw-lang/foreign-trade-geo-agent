"""No-network checks for the isolated one-attempt runner; no production changes."""
import asyncio
from datetime import UTC, datetime
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx
from scripts import run_minimal_writer_flash_once as runner
from foreign_trade_geo_agent.adapters.retained_deepseek import OneShotTransport, receive_candidate
from foreign_trade_geo_agent.core import content_draft as cd
from tests.minimal_flash_fixtures import isolated_flash_package


class MinimalFlashOnceTests(unittest.TestCase):
    def setUp(self):
        # Only the test package anchor changes; the exact request hash and all
        # production runner constants remain unchanged outside this test.
        anchor = self.enterContext(isolated_flash_package())
        self.enterContext(patch.object(runner, 'MANIFEST_HASH', anchor))

    def test_changed_frozen_bytes_rejected_before_transport_construction(self):
        path = runner.frozen.DEST / 'request.json'
        path.write_bytes(path.read_bytes() + b' ')
        with patch.object(httpx, 'AsyncHTTPTransport', side_effect=AssertionError('network constructed')):
            with self.assertRaisesRegex(ValueError, 'PREFLIGHT_FROZEN_BYTES'):
                runner.preflight()

    def test_original_frozen_request_unchanged(self):
        raw,_,checks=runner.preflight()
        self.assertEqual(runner.frozen.sha(raw),runner.REQUEST_HASH)
        self.assertEqual(checks['manifest_sha256'],runner.MANIFEST_HASH)
        self.assertEqual((checks['selected_facts'],checks['explanation_slots']),(25,12))

    def test_mock_dry_run_exact_bytes_and_second_send_rejected(self):
        raw,_,_=runner.preflight()
        result=asyncio.run(runner.dry_run(raw))
        self.assertTrue(result['exact_sent_bytes'])
        self.assertTrue(result['second_send_rejected'])
        self.assertEqual(result['real_api_calls'],0)
        self.assertEqual(result['request_sha256'],runner.REQUEST_HASH)

    def test_marker_exclusive_even_after_uncertain_attempt(self):
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp)
            runner.claim_attempt(directory)
            with self.assertRaises(FileExistsError): runner.claim_attempt(directory)
            marker=json.loads((directory/'attempt-started.json').read_bytes())
            self.assertFalse(marker['retry_allowed'])
            self.assertEqual(marker['maximum_attempts'],1)

    def test_existing_attempt_prevents_client_construction(self):
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp); runner.claim_attempt(directory)
            with patch.object(httpx,'AsyncHTTPTransport',side_effect=AssertionError('network constructed')):
                with self.assertRaisesRegex(ValueError,'NO_SECOND_ATTEMPT'):
                    asyncio.run(runner.execute(directory))

    def test_http_failure_consumes_attempt_and_never_retries(self):
        async def run():
            calls=[]
            async def handler(request):
                calls.append(request.content)
                raise httpx.ConnectError('Mock disconnected; do not log this raw message')
            raw=b'{}'
            guard=OneShotTransport(httpx.MockTransport(handler),raw)
            async with httpx.AsyncClient(transport=guard,follow_redirects=False) as client:
                with self.assertRaises(httpx.ConnectError): await client.post(runner.ENDPOINT,content=raw)
                with self.assertRaisesRegex(ValueError,'SINGLE_REQUEST_GUARD'):
                    await client.post(runner.ENDPOINT,content=raw)
            self.assertEqual((len(calls),guard.calls),(1,1))
        asyncio.run(run())

    def test_changed_bytes_and_wrong_endpoint_rejected_before_inner_transport(self):
        async def run():
            calls=[]
            async def handler(request):
                calls.append(request)
                return httpx.Response(200)
            for url,raw in ((runner.ENDPOINT,b'changed'),('https://example.invalid/',b'{}')):
                guard=OneShotTransport(httpx.MockTransport(handler),b'{}')
                async with httpx.AsyncClient(transport=guard) as client:
                    with self.assertRaisesRegex(ValueError,'SINGLE_REQUEST_GUARD'):
                        await client.post(url,content=raw)
                self.assertEqual(guard.calls,0)
            self.assertEqual(calls,[])
        asyncio.run(run())

    def test_peak_budget_under_authorized_ceiling(self):
        prices=dict(official_url=runner.PRICE_URL,verified=True,verified_at_utc=datetime.now(UTC).isoformat(),
            peak_usd_per_million=dict(input_cache_hit=0.006,input_cache_miss=0.3,output=1.2))
        result=runner.budget_check(prices,b'x'*16508)
        self.assertEqual(result['peak_all_cache_miss_planning_usd'],0.0393216)
        self.assertLess(result['peak_all_cache_miss_planning_usd'],0.05)
        prices['verified']=False
        with self.assertRaisesRegex(ValueError,'OFFICIAL_PRICE_REQUIRED'): runner.budget_check(prices,b'{}')

    def test_stale_price_or_changed_terms_rejected(self):
        prices=dict(official_url=runner.PRICE_URL,verified=True,verified_at_utc='2020-01-01T00:00:00+00:00',
            peak_usd_per_million=dict(input_cache_hit=0.006,input_cache_miss=0.3,output=1.2))
        with self.assertRaisesRegex(ValueError,'PRICE_VERIFICATION_STALE'): runner.budget_check(prices,b'{}')
        prices['verified_at_utc']=datetime.now(UTC).isoformat()
        prices['peak_usd_per_million']['output']=30
        with self.assertRaisesRegex(ValueError,'PRICE_TERMS_CHANGED'): runner.budget_check(prices,b'{}')

    def test_http_error_body_retained_no_native_validation(self):
        async def run(directory):
            raw=b'{}'; meta={}
            async def handler(request): return httpx.Response(500,json={'error':{'message':'Mock provider unavailable'}})
            guard=OneShotTransport(httpx.MockTransport(handler),raw,request_limit=cd.MAX_INPUT_ENVELOPE_BYTES)
            with self.assertRaisesRegex(ValueError,'PROVIDER_HTTP_FAILURE'):
                await receive_candidate(None,raw,guard,'MOCK-SECRET-ONLY',output=directory,metadata=meta,
                    validator=lambda *_:self.fail('Validator called for HTTP failure'),detail=lambda *_:None)
            self.assertEqual(guard.calls,1)
            self.assertEqual(meta['http_status'],500)
            self.assertTrue((directory/'response-body.bin').exists())
        with tempfile.TemporaryDirectory() as temp: asyncio.run(run(Path(temp)))

    def test_secret_echo_is_never_retained(self):
        async def run(directory):
            raw=b'{}'; key='MOCK-SENSITIVE-KEY'; meta={}
            async def handler(request): return httpx.Response(200,content=key.encode())
            guard=OneShotTransport(httpx.MockTransport(handler),raw)
            with self.assertRaisesRegex(ValueError,'SECRET_OUTPUT_REFUSED'):
                await receive_candidate(None,raw,guard,key,output=directory,metadata=meta,
                    validator=lambda *_:None,detail=lambda *_:None)
            self.assertFalse((directory/'response-body.bin').exists())
            self.assertEqual(guard.calls,1)
        with tempfile.TemporaryDirectory() as temp: asyncio.run(run(Path(temp)))

    def test_no_redirect_following(self):
        async def run():
            calls=[]
            async def handler(request):
                calls.append(str(request.url))
                return httpx.Response(307,headers={'location':'https://example.invalid/'})
            guard=OneShotTransport(httpx.MockTransport(handler),b'{}')
            async with httpx.AsyncClient(transport=guard,follow_redirects=False) as client:
                response=await client.post(runner.ENDPOINT,content=b'{}')
            self.assertEqual(response.status_code,307)
            self.assertEqual(calls,[runner.ENDPOINT])
            self.assertEqual(guard.calls,1)
        asyncio.run(run())


if __name__=='__main__': unittest.main()
