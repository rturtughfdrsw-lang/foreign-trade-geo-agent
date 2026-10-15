"""Real isolated entry point, native validator, disk files; HTTP is always mocked."""
import asyncio
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpx

from scripts import demo_seo_e_only as fixture
from scripts import prepare_seo_e_only_experiment as exp
from scripts import prepare_seo_article_experiment as shared
from foreign_trade_geo_agent.core import content_draft as cd


class EOnlyRetentionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.frozen = Path(cls.temp.name) / "frozen"
        cls.digest = exp.prepare(cls.frozen)["bundle_sha256"]
        cls.value, cls.request = exp.load_frozen(cls.frozen, cls.digest)
        cls.text = asyncio.run(fixture.FixedEOnlyWriter().write_content_draft(
            cd.build_content_draft_prompt(cls.value, "C1"))).text

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / "frozen"
        shutil.copytree(self.frozen, self.directory)
        self.calls = 0
        self.before = {p.name: p.read_bytes() for p in self.directory.iterdir() if p.is_file()}

    def envelope(self, text=None, finish="stop"):
        # Noncanonical whitespace/Unicode deliberately exercise byte preservation.
        return json.dumps({"model": "deepseek-flash", "choices": [{"message": {
            "content": self.text if text is None else text}, "finish_reason": finish}],
            "usage": {"prompt_tokens": 2400, "completion_tokens": 800, "total_tokens": 3200}},
            ensure_ascii=False, indent=2).encode("utf-8")

    def run_mock(self, raw=None, status=200, handler=None):
        def respond(request):
            self.calls += 1
            self.assertEqual(request.content, self.request)
            self.assertEqual(request.extensions["timeout"]["read"], 60.)
            if handler:
                return handler(request)
            return httpx.Response(status, content=self.envelope() if raw is None else raw,
                headers={"Set-Cookie": "session=never-save-me", "Authorization": "never-save-me"})
        with patch("httpx.AsyncHTTPTransport", side_effect=AssertionError("NO LIVE")), patch(
                "scripts.local_env.load_api_keys", side_effect=AssertionError("NO SECRETS")):
            return asyncio.run(exp.run_once(self.directory, self.digest,
                mock_transport=httpx.MockTransport(respond)))

    def assert_retained(self, result, raw, *, status="FAILED", http_status=200):
        self.assertEqual(result["status"], status, result)
        self.assertEqual(result["request_count"], 1)
        self.assertEqual(self.calls, 1)
        self.assertEqual(result["real_requests"], 0)
        self.assertFalse(result["production_authorized"])
        output = Path(result["output"])
        self.assertEqual((output / "response-body.bin").read_bytes(), raw)
        self.assertEqual(result["response_sha256"], shared.sha(raw))
        self.assertEqual(result["http_status"], http_status)
        self.assertEqual(json.loads((output / "diagnostics.json").read_bytes()), result)
        for name, content in self.before.items():
            self.assertEqual((self.directory / name).read_bytes(), content)
        for file in output.iterdir():
            if file.is_file():
                self.assertNotIn(b"never-save-me", file.read_bytes())
        if status != "SUCCESS":
            self.assertFalse((output / "content-draft.json").exists())
            self.assertFalse((output / "history.sqlite3").exists())
        return output

    def test_success_saves_exact_body_before_validator_and_usage(self):
        raw = self.envelope(self.text + "\r\n")
        validator = exp.validate_candidate
        def inspect(value, text):
            bodies = list(self.directory.glob("mock-*/response-body.bin"))
            self.assertEqual(len(bodies), 1)
            self.assertEqual(bodies[0].read_bytes(), raw)
            return validator(value, text)
        with patch.object(exp, "validate_candidate", side_effect=inspect):
            result = self.run_mock(raw)
        output = self.assert_retained(result, raw, status="SUCCESS")
        self.assertEqual(result["usage"]["total_tokens"], 3200)
        self.assertEqual(result["finish_reason"], "stop")
        self.assertEqual((output / "model-output.txt").read_bytes(), (self.text + "\r\n").encode())

    def test_body_is_on_disk_before_provider_json_parser_runs(self):
        raw = self.envelope()
        original = json.loads
        def inspect(value, *args, **kwargs):
            if value == raw:
                bodies = list(self.directory.glob("mock-*/response-body.bin"))
                self.assertEqual(len(bodies), 1, "provider JSON parsed before raw retention")
                self.assertEqual(bodies[0].read_bytes(), raw)
            return original(value, *args, **kwargs)
        with patch.object(json, "loads", side_effect=inspect):
            result = self.run_mock(raw)
        self.assert_retained(result, raw, status="SUCCESS")

    def test_invalid_http_json_retained_and_diagnosed_without_usage_invention(self):
        raw = b'{"choices": [broken\r\n'
        result = self.run_mock(raw)
        self.assert_retained(result, raw)
        self.assertEqual(result["error"], "PROVIDER_JSON_FORMAT")
        self.assertIsNone(result["usage"])
        self.assertGreater(result["json_error"]["column"], 0)

    def test_invalid_draft_json_keeps_model_text_and_usage(self):
        text = '{"draft": broken\r\n'
        raw = self.envelope(text)
        result = self.run_mock(raw)
        output = self.assert_retained(result, raw)
        self.assertEqual(result["error"], "JSON_FORMAT")
        self.assertEqual(result["usage"]["completion_tokens"], 800)
        self.assertEqual((output / "model-output.txt").read_bytes(), text.encode())

    def reject_mutation(self, mutate, category):
        body = json.loads(self.text)
        mutate(body["draft"])
        text = json.dumps(body, ensure_ascii=False, indent=3) + "\r\n"
        raw = self.envelope(text)
        result = self.run_mock(raw)
        output = self.assert_retained(result, raw)
        self.assertEqual(result["error"], category)
        self.assertEqual(result["failure_stage"], "native_validation")
        self.assertEqual(result["usage"]["total_tokens"], 3200)
        self.assertEqual((output / "rejected-candidate.txt").read_bytes(), text.encode())
        self.assertEqual((output / "model-output.txt").read_bytes(), text.encode())
        self.assertTrue(result["validation_detail"])
        return result

    def test_validator_rejection_keeps_unmodified_candidate(self):
        self.reject_mutation(lambda d: d["sections"][0].update(outline_heading="wrong"), "NEW_RESOURCE_INVALID")

    def test_invalid_e_reference_keeps_unmodified_candidate(self):
        self.reject_mutation(lambda d: d["sections"][0]["blocks"][1]["claims"][0].update(
            customer_refs=["E999"]), "UNKNOWN_CUSTOMER_REFERENCE")

    def test_claim_budget_keeps_count_and_rejected_candidate(self):
        def exceed(draft):
            claims = draft["sections"][0]["blocks"][0]["claims"]
            claims.extend([claims[0]] * 17)
        result = self.reject_mutation(exceed, "CLAIM_BUDGET")
        self.assertGreater(result["validation_detail"]["claim_count"], 16)

    def test_numeric_validation_keeps_rejected_candidate(self):
        self.reject_mutation(lambda d: d["sections"][0]["blocks"][1]["claims"][0].update(
            text=fixture.FACT.replace("7200 rpm", "7300 rpm")), "NUMERIC_NOT_GROUNDED")

    def test_length_finish_retains_text_usage_without_valid_draft(self):
        raw = self.envelope(self.text[:150], finish="length")
        result = self.run_mock(raw)
        output = self.assert_retained(result, raw)
        self.assertEqual(result["error"], "OUTPUT_INCOMPLETE")
        self.assertEqual(result["finish_reason"], "length")
        self.assertEqual(result["usage"]["total_tokens"], 3200)
        self.assertEqual((output / "model-output.txt").read_bytes(), self.text[:150].encode())

    def test_http_error_retains_body_and_status(self):
        raw = b'{"error":{"code":"rate_limit"}}'
        result = self.run_mock(raw, status=429)
        self.assert_retained(result, raw, http_status=429)
        self.assertEqual(result["error"], "PROVIDER_HTTP_FAILURE")

    def test_timeout_or_disconnect_has_no_response_or_usage_and_one_attempt(self):
        for error, category in ((httpx.ReadTimeout, "REQUEST_TIMEOUT"),
                                (httpx.ConnectError, "REQUEST_DISCONNECTED")):
            with self.subTest(error=error):
                self.calls = 0
                def fail(request):
                    raise error("SECRET EXCEPTION", request=request)
                result = self.run_mock(handler=fail)
                self.assertEqual(result["error"], category)
                self.assertEqual(result["request_count"], 1)
                self.assertEqual(self.calls, 1)
                self.assertEqual(result["response_state"], "NO_RESPONSE")
                self.assertIsNone(result["http_status"])
                self.assertIsNone(result["usage"])
                self.assertEqual({p.name for p in Path(result["output"]).iterdir()},
                                 {"started.json", "diagnostics.json"})
                self.assertNotIn("SECRET EXCEPTION", json.dumps(result))

    def test_partial_stream_disconnect_retains_exact_prefix(self):
        class BrokenStream(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b'{"choices": ['
                raise httpx.ReadError("SECRET EXCEPTION")
        result = self.run_mock(handler=lambda r: httpx.Response(200, stream=BrokenStream()))
        self.assert_retained(result, b'{"choices": [')
        self.assertEqual(result["response_state"], "PARTIAL_RESPONSE")
        self.assertIsNone(result["usage"])

    def test_body_write_failure_is_incomplete_and_never_validates_or_retries(self):
        original = Path.open
        def fail(path, *args, **kwargs):
            if path.name == "response-body.bin":
                raise OSError("SECRET DISK ERROR")
            return original(path, *args, **kwargs)
        with patch.object(Path, "open", new=fail), patch.object(exp, "validate_candidate",
                side_effect=AssertionError("MUST NOT VALIDATE")):
            result = self.run_mock()
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertEqual(result["error"], "PERSISTENCE_FAILED")
        self.assertEqual(result["request_count"], 1)
        self.assertEqual(self.calls, 1)
        self.assertNotIn("SECRET DISK ERROR", json.dumps(result))
        self.assertFalse((Path(result["output"]) / "content-draft.json").exists())

    def test_diagnostics_write_failure_returns_incomplete(self):
        original = shared.write_json
        def fail(path, value):
            if path.name == "diagnostics.json":
                raise OSError("disk full")
            return original(path, value)
        with patch.object(shared, "write_json", side_effect=fail):
            result = self.run_mock(b"invalid")
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertEqual(result["request_count"], 1)
        self.assertEqual(self.calls, 1)

    def test_success_diagnostics_failure_does_not_leave_valid_draft(self):
        original = shared.write_json
        def fail(path, value):
            if path.name == "diagnostics.json":
                raise OSError("disk full")
            return original(path, value)
        with patch.object(shared, "write_json", side_effect=fail):
            result = self.run_mock()
        self.assertEqual(result["status"], "INCOMPLETE")
        output = Path(result["output"])
        self.assertFalse((output / "content-draft.json").exists())
        self.assertFalse((output / "history.sqlite3").exists())
        self.assertNotIn("artifact_id", result)

    def test_secret_body_is_explicitly_withheld_without_redacted_fake_original(self):
        for secret in (shared.OFFLINE_KEY, "Cookie: private-cookie", "sk-123456789secret",
                       "Authorization: do-not-save", "API Key: do-not-save"):
            with self.subTest(secret_type=secret.split(":")[0]):
                self.calls = 0
                result = self.run_mock(self.envelope(secret))
                self.assertEqual(result["error"], "SECRET_OUTPUT_REFUSED")
                self.assertEqual(result["response_state"], "WITHHELD_SECRET")
                self.assertFalse(result["response_saved"])
                self.assertEqual(self.calls, 1)
                for file in Path(result["output"]).iterdir():
                    self.assertNotIn(secret.encode(), file.read_bytes())

    def test_encoded_secret_body_is_not_saved_before_inspection(self):
        import gzip
        class EncodedStream(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield gzip.compress(self_raw)
        self_raw = self.envelope(shared.OFFLINE_KEY)
        result = self.run_mock(handler=lambda r: httpx.Response(200, stream=EncodedStream(),
            headers={"Content-Encoding": "gzip"}))
        self.assertEqual(result["error"], "ENCODED_RESPONSE_REFUSED")
        self.assertEqual(result["response_state"], "WITHHELD_UNINSPECTABLE")
        self.assertFalse((Path(result["output"]) / "response-body.bin").exists())

    def test_output_budget_keeps_exact_bounded_prefix_and_marks_partial(self):
        raw = b"x" * (shared.MAX_RESPONSE_BYTES + 1)
        result = self.run_mock(raw)
        output = self.assert_retained(result, raw[:65536])
        self.assertEqual(result["error"], "RESPONSE_BUDGET_EXCEEDED")
        self.assertEqual(result["response_state"], "PARTIAL_RESPONSE")
        self.assertTrue(result["response_budget_exceeded"])
        self.assertEqual((output / "response-body.bin").stat().st_size, 65536)

    def test_start_record_write_failure_makes_zero_requests(self):
        with patch.object(shared, "write_json", side_effect=OSError("disk full")):
            result = self.run_mock()
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertEqual(result["request_count"], 0)
        self.assertEqual(self.calls, 0)

    def test_candidate_export_write_failure_keeps_raw_but_no_valid_draft(self):
        original = Path.open
        def fail(path, *args, **kwargs):
            if path.name.startswith("quality-review.json"):
                raise OSError("disk full")
            return original(path, *args, **kwargs)
        raw = self.envelope()
        with patch.object(Path, "open", new=fail):
            result = self.run_mock(raw)
        self.assert_retained(result, raw, status="INCOMPLETE")
        self.assertEqual(result["error"], "PERSISTENCE_FAILED")

    def test_missing_text_still_preserves_finish_reason_and_usage(self):
        raw = self.envelope()
        body = json.loads(raw)
        body["choices"][0]["message"]["content"] = ""
        body["choices"][0]["finish_reason"] = "length"
        raw = json.dumps(body).encode()
        result = self.run_mock(raw)
        self.assert_retained(result, raw)
        self.assertEqual(result["finish_reason"], "length")
        self.assertEqual(result["usage"]["total_tokens"], 3200)

    def test_existing_attempt_directory_is_never_overwritten(self):
        with patch.object(shared, "uuid4") as identifier:
            identifier.return_value.hex = "reserved"
            output = self.directory / "mock-reserved"
            output.mkdir()
            (output / "sentinel").write_bytes(b"keep")
            with self.assertRaises(FileExistsError):
                self.run_mock()
        self.assertEqual(self.calls, 0)
        self.assertEqual((output / "sentinel").read_bytes(), b"keep")

    def test_refreeze_preserves_every_original_input_byte_and_rejects_overwrite(self):
        old = json.loads((self.directory / "bundle.json").read_bytes())
        old["code"] = {"previous-version": "0" * 64}
        shared.write_json(self.directory / "bundle.json", old)
        digest = shared.sha((self.directory / "bundle.json").read_bytes())
        target = Path(self.temp.name) / "refrozen"
        result = exp.refreeze(self.directory, digest, target)
        new = json.loads((target / "bundle.json").read_bytes())
        self.assertEqual(new["files"], old["files"])
        for name in old["files"]:
            self.assertEqual((target / name).read_bytes(), (self.directory / name).read_bytes())
        self.assertEqual(exp.load_frozen(target, result["bundle_sha256"])[1], self.request)
        with self.assertRaisesRegex(ValueError, "OUTPUT_MUST_BE_NEW"):
            exp.refreeze(self.directory, digest, target)

    def test_refreeze_refuses_changed_historical_input(self):
        (self.directory / "customer-E1.txt").write_bytes(b"changed")
        target = Path(self.temp.name) / "refrozen"
        with self.assertRaisesRegex(ValueError, "FROZEN_INPUT_CHANGED"):
            exp.refreeze(self.directory, self.digest, target)
        self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
