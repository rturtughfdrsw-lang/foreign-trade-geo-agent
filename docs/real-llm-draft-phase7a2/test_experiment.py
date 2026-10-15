"""Offline tests only; no credential load or live runner invocation."""
import unittest
from dataclasses import replace
from unittest.mock import patch
import httpx
import experiment as e


class ExperimentTests(unittest.TestCase):
    def test_persisted_ready_envelope_recomputed(self):
        value, result = e.load_admitted()
        self.assertEqual(result.status.value, 'READY')
        self.assertFalse(value.semantic_approved or value.production_authorized)
        self.assertEqual(e.admission.require_ready(value, result), result)

    def test_forged_receipt_and_changed_input_rejected(self):
        value, result = e.load_admitted()
        for request, receipt in ((value, replace(result, supported_claims=())),
            (replace(value, production_authorized=True), result),
            (replace(value, required_claims=()), result)):
            with self.assertRaises(ValueError):
                e.admission.require_ready(request, receipt)

    def test_json_rejections(self):
        for text in ('plain article', '```json\n{"article":"a"}\n```',
            '{"article":"a","extra":1}', '{"article":"a","article":"b"}',
            '{"article":NaN}', '[]', '{}'):
            self.assertEqual(e.draft_layers(text)['first_failed_layer'], 1)

    def test_draft_rejections(self):
        for article in ('', 1, [], 'body only', '# Title\n\n## One\n\nbody', 'a' * 65537,
            '# A\n\n# B\n\n## C\n\n## D\n\nbody', '# T\n\n## A\n\n## B\n\n\x00'):
            self.assertEqual(e.draft_layers(e.p.canonical({'article': article}))['first_failed_layer'], 2)

    def test_contract_pass_does_not_claim_evidence_or_semantic_pass(self):
        value = e.draft_layers(e.p.canonical({'article': e.p.CLEAN}))
        self.assertIsNone(value['first_failed_layer'])
        self.assertEqual(value['layers'][2]['status'], 'PENDING_RECORDED_EVIDENCE_AUDIT')
        self.assertEqual(value['layers'][3]['status'], 'NOT_RUN_PENDING_LAYER_3')

    def test_transport_accepts_only_one_exact_post(self):
        calls = []
        transport = e.OneShotTransport(httpx.MockTransport(
            lambda request: calls.append(request) or httpx.Response(200, json={})))
        with httpx.Client(transport=transport) as client:
            client.post(e.ENDPOINT, content=b'{}')
            with self.assertRaises(ValueError):
                client.post(e.ENDPOINT, content=b'{}')
        self.assertEqual(len(calls), 1)

    def test_wrong_endpoint_and_method_never_reach_inner(self):
        calls = []
        for method, url in (('GET', e.ENDPOINT), ('POST', 'https://example.invalid')):
            transport = e.OneShotTransport(httpx.MockTransport(
                lambda request: calls.append(request) or httpx.Response(200)))
            with httpx.Client(transport=transport) as client, self.assertRaises(ValueError):
                client.request(method, url)
            self.assertEqual(transport.calls, 0)
        self.assertEqual(calls, [])

    def test_transport_failure_consumes_attempt_without_retry(self):
        calls = []
        def failed(request):
            calls.append(request)
            raise httpx.ConnectError('synthetic offline failure')
        transport = e.OneShotTransport(httpx.MockTransport(failed))
        with httpx.Client(transport=transport) as client:
            with self.assertRaises(httpx.ConnectError):
                client.post(e.ENDPOINT)
            with self.assertRaises(ValueError):
                client.post(e.ENDPOINT)
        self.assertEqual(transport.calls, 1)
        self.assertEqual(len(calls), 1)

    def test_consumed_marker_blocks_before_credentials_or_transport(self):
        original = e.OUT
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(e, 'OUT', Path(folder)), patch.object(e, 'verify_frozen'), \
                patch.object(e, 'read_key') as key, patch.object(httpx, 'HTTPTransport') as transport:
                (e.OUT / 'attempt-consumed.json').write_text('{}')
                with self.assertRaisesRegex(ValueError, 'P7A2_ATTEMPT_ALREADY_CONSUMED'):
                    e.execute_once()
                key.assert_not_called()
                transport.assert_not_called()
        self.assertEqual(e.OUT, original)

    def test_baseline_does_not_read_historical_phase7a_request(self):
        from pathlib import Path
        original_read = Path.read_bytes
        forbidden = e.BASE / 'docs/real-llm-draft-phase7a/preflight/request.json'
        def read(path):
            self.assertNotEqual(path, forbidden)
            return original_read(path)
        with patch.object(Path, 'read_bytes', read):
            value = e.baseline()
        self.assertTrue(value['phase6']['excluded_historical_request_stat']['content_not_loaded'])


if __name__ == '__main__':
    unittest.main()
