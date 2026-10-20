"""Offline behavioral checks; MockTransport is the only external boundary."""
import copy
from datetime import UTC, datetime, timedelta
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import httpx
from foreign_trade_geo_agent.core import content_draft as cd
from foreign_trade_geo_agent.storage.serialization import _decode

HERE = Path(__file__).resolve().parent
PRE = HERE.parent / 'seo-model-comparison-preflight-2026-10-11'
spec = importlib.util.spec_from_file_location('pro_experiment_runner', HERE / 'runner.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class RunnerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name)
        self.raw = (PRE / 'request-v4-pro.json').read_bytes()
        self.value = _decode(json.loads((PRE / 'baseline/native-input.json').read_bytes()), cd.ContentDraftInput)
        self.body = json.loads((PRE / 'baseline/response-body.bin').read_bytes())
        self.body['model'] = 'deepseek-v4-pro'
        self.deadline = datetime.now(UTC) + timedelta(seconds=120)
        self.calls = 0

    async def run_response(self, body=None, status=200, headers=None, deadline=None, timeout=60):
        def respond(request):
            self.calls += 1
            self.assertEqual(request.content, self.raw)
            self.assertEqual(str(request.url), 'https://api.deepseek.com/chat/completions')
            if isinstance(body, Exception):
                raise body
            content = json.dumps(self.body if body is None else body).encode()
            return httpx.Response(status, content=content, headers=headers)
        return await runner.execute(self.raw, self.value, httpx.MockTransport(respond), 'OFFLINE-KEY',
                                    self.output, deadline or self.deadline, timeout=timeout)

    async def test_success_retains_exact_candidate_and_native_article(self):
        result = await self.run_response()
        self.assertIsNotNone(result, 'isolated execution has not been implemented')
        self.assertEqual(result['state'], 'SUCCEEDED_TEST_ONLY')
        self.assertEqual(result['request_count'], 1)
        self.assertEqual((self.output / 'model-output.txt').read_text(), self.body['choices'][0]['message']['content'])
        self.assertEqual(json.loads((self.output / 'native-result.json').read_bytes())['parser'], 'PASS')
        self.assertTrue((self.output / 'article-body.md').is_file())

    async def test_expired_deadline_sends_nothing(self):
        result = await self.run_response(deadline=datetime.now(UTC) - timedelta(seconds=1))
        self.assertEqual(result['state'], 'FAILED_TEST_ONLY')
        self.assertEqual(self.calls, 0)

    async def test_changed_frozen_request_sends_nothing(self):
        self.raw = self.raw.replace(b'"temperature":0', b'"temperature":1')
        result = await self.run_response()
        self.assertEqual(result['state'], 'FAILED_TEST_ONLY')
        self.assertEqual(self.calls, 0)

    async def test_redirect_is_retained_without_following(self):
        result = await self.run_response(status=302, headers={'location': 'https://example.com/'})
        self.assertEqual(result['state'], 'FAILED_TEST_ONLY')
        self.assertEqual(self.calls, 1)
        self.assertTrue((self.output / 'response-body.bin').is_file())

    async def test_http_failure_does_not_retry(self):
        result = await self.run_response(status=503)
        self.assertEqual(result['state'], 'FAILED_TEST_ONLY')
        self.assertEqual(self.calls, 1)

    async def test_network_failure_does_not_retry(self):
        result = await self.run_response(body=httpx.ReadTimeout('fixture'))
        self.assertEqual(result['state'], 'FAILED_TEST_ONLY')
        self.assertEqual(self.calls, 1)

    async def test_truncation_retains_text_but_never_claims_native_success(self):
        self.body['choices'][0]['finish_reason'] = 'length'
        result = await self.run_response()
        self.assertEqual(result['state'], 'FAILED_TEST_ONLY')
        self.assertTrue((self.output / 'model-output.txt').is_file())
        self.assertFalse((self.output / 'article-body.md').exists())

    async def test_wrong_response_model_rejected(self):
        self.body['model'] = 'deepseek-flash'
        result = await self.run_response()
        self.assertEqual(result['state'], 'FAILED_TEST_ONLY')
        self.assertEqual(self.calls, 1)

    async def test_missing_text_still_preserves_finish_reason_and_usage(self):
        self.body['choices'][0]['message']['content'] = None
        result = await self.run_response()
        self.assertEqual(result['state'], 'FAILED_TEST_ONLY')
        self.assertEqual(result.get('finish_reason'), 'stop')
        self.assertEqual(result['usage']['total_tokens'], 3097)

    async def test_partial_disconnect_keeps_exact_prefix(self):
        class BrokenStream(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b'{"partial":'
                raise httpx.ReadError('fixture disconnect')
        def respond(request):
            self.calls += 1
            return httpx.Response(200, stream=BrokenStream())
        result = await runner.execute(self.raw, self.value, httpx.MockTransport(respond), 'OFFLINE-KEY',
                                      self.output, self.deadline)
        self.assertEqual(result['state'], 'FAILED_TEST_ONLY')
        self.assertFalse(result['response_complete'])
        self.assertEqual((self.output / 'response-body.bin').read_bytes(), b'{"partial":')
        self.assertEqual(self.calls, 1)

    async def test_encoded_response_is_withheld(self):
        result = await self.run_response(headers={'content-encoding': 'unknown'})
        self.assertEqual(result['state'], 'FAILED_TEST_ONLY')
        self.assertFalse((self.output / 'response-body.bin').exists())

    async def test_invalid_E_value_keeps_rejected_candidate_and_diagnostic(self):
        self.body['choices'][0]['message']['content'] = self.body['choices'][0]['message']['content'].replace('7200 rpm', '7300 rpm')
        result = await self.run_response()
        self.assertEqual(result['state'], 'FAILED_TEST_ONLY')
        self.assertEqual(result['native_error'], 'NUMERIC_NOT_GROUNDED')
        self.assertTrue((self.output / 'rejected-candidate.txt').is_file())
        self.assertFalse((self.output / 'article-body.md').exists())

    async def test_secret_response_never_persists_raw_or_model_text(self):
        self.body['choices'][0]['message']['content'] = 'OFFLINE-KEY'
        result = await self.run_response()
        self.assertEqual(result['state'], 'FAILED_TEST_ONLY')
        self.assertFalse((self.output / 'response-body.bin').exists())
        self.assertFalse((self.output / 'model-output.txt').exists())

    async def test_response_budget_failure_is_explicit(self):
        result = await self.run_response(body={'padding': 'x' * 70000})
        self.assertEqual(result['state'], 'FAILED_TEST_ONLY')
        self.assertFalse(result['response_complete'])
        self.assertLessEqual((self.output / 'response-body.bin').stat().st_size, 65536)

    async def test_total_timeout_cancels_pending_transport(self):
        import asyncio
        async def slow(request):
            self.calls += 1
            await asyncio.sleep(1)
            return httpx.Response(200, json=self.body)
        result = await runner.execute(self.raw, self.value, httpx.MockTransport(slow), 'OFFLINE-KEY',
                                      self.output, self.deadline, timeout=.02)
        self.assertEqual(result['state'], 'FAILED_TEST_ONLY')
        self.assertEqual(self.calls, 1)


if __name__ == '__main__':
    unittest.main()
