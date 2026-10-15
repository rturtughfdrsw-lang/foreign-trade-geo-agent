"""One frozen synthetic article request; all HTTP uses MockTransport."""
import asyncio
from contextlib import redirect_stdout
from datetime import UTC, datetime, timedelta
from io import StringIO
import ipaddress
import json
from pathlib import Path
import shutil
import socket
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpx

from scripts import prepare_seo_article_experiment as exp
from foreign_trade_geo_agent.adapters.deepseek_content_draft import DeepSeekContentDraftWriter
from foreign_trade_geo_agent.cli import main as cli_main
from foreign_trade_geo_agent.core import content_draft as cd
from foreign_trade_geo_agent.core.history import ArtifactType
from foreign_trade_geo_agent.storage.sqlite import SQLiteHistoryReader, SQLiteHistoryStore
from foreign_trade_geo_agent.workflows.content_draft import ContentDraftWorkflow


class SEOArticleExperimentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.frozen = Path(cls.temp.name) / "frozen"
        connect = socket.socket.connect

        def offline_connect(sock, address):
            if not isinstance(address, tuple) or not ipaddress.ip_address(address[0]).is_loopback:
                raise AssertionError("NO EXTERNAL SOCKET")
            return connect(sock, address)

        cls.network = patch("socket.socket.connect", new=offline_connect)
        cls.network.start()
        cls.addClassCleanup(cls.network.stop)
        with patch("httpx.AsyncHTTPTransport", side_effect=AssertionError("NO REAL TRANSPORT")), patch(
                "scripts.local_env.load_api_keys", side_effect=AssertionError("NO ENV LOAD")):
            cls.summary = exp.prepare(cls.frozen)
        cls.digest = cls.summary["bundle_sha256"]
        cls.value, cls.raw_request = exp.load_frozen(cls.frozen, cls.digest)
        cls.native_text = asyncio.run(exp.fixture.FixedArticleWriter().write_content_draft(
            cd.build_content_draft_prompt(cls.value, "C1"))).text

    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name) / "frozen"
        shutil.copytree(self.frozen, self.directory)
        self.requests = []

    def envelope(self, text=None, finish="stop", **extra):
        return {"model": "deepseek-flash", "choices": [{"message": {
            "content": text if text is not None else self.native_text}, "finish_reason": finish}], **extra}

    def run_response(self, response=None, *, callback=None):
        def handler(request):
            self.requests.append(request)
            return callback(request) if callback else response or httpx.Response(200, json=self.envelope())
        with patch("httpx.AsyncHTTPTransport", side_effect=AssertionError("NO REAL TRANSPORT")), patch(
                "scripts.local_env.load_api_keys", side_effect=AssertionError("NO ENV LOAD")):
            return asyncio.run(exp.run_once(self.directory, self.digest, mock_transport=httpx.MockTransport(handler)))

    def assert_failed_isolated(self, result):
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(result["request_count"], 1)
        self.assertEqual(result["real_requests"], 0)
        output = Path(result["output"])
        expected = {"started.json", "diagnostics.json"}
        if result["response_saved"]:
            expected.add("response-body.bin")
            self.assertEqual(exp.sha((output / "response-body.bin").read_bytes()), result["response_sha256"])
        if "model_text_sha256" in result:
            expected.add("model-output.txt")
            self.assertEqual(exp.sha((output / "model-output.txt").read_bytes()), result["model_text_sha256"])
        if result["failure_stage"] == "native_validation":
            expected.add("rejected-candidate.txt")
            self.assertEqual((output / "rejected-candidate.txt").read_bytes(), (output / "model-output.txt").read_bytes())
        self.assertEqual({p.name for p in output.iterdir()}, expected)
        self.assertFalse((output / "content-draft.json").exists())
        self.assertFalse((output / "history.sqlite3").exists())
        self.assertFalse((self.directory / "live-attempt").exists())

    def test_default_prepare_freezes_complete_native_request_and_all_qualifiers(self):
        payload = json.loads(self.raw_request)
        self.assertEqual(payload["model"], "deepseek-flash")
        self.assertEqual(payload["max_tokens"], 3000)
        self.assertEqual(payload["thinking"], {"type": "disabled"})
        self.assertEqual(payload["temperature"], 0)
        self.assertLessEqual(len(self.raw_request), 16000)
        self.assertEqual(payload["messages"][0]["content"],
                         (self.frozen / "system-prompt.txt").read_text(encoding="utf-8"))
        self.assertEqual(payload["messages"][1]["content"].encode(),
                         (self.frozen / "user-material.json").read_bytes())
        self.assertEqual(self.summary["real_requests"], 0)
        self.assertEqual(self.summary["production_writer_calls"], 0)
        self.assertFalse(self.summary["production_authorized"])
        self.assertEqual(self.summary["automatic_retries"], 0)
        native = (self.frozen / "native-material.json").read_text(encoding="utf-8")
        for fact in exp.fixture.FACTS:
            self.assertIn(fact, native)
        self.assertNotIn("customer:E", payload["messages"][1]["content"])
        self.assertEqual(self.summary["outline"], ["spindle performance", "machining tolerance"])

    def test_mock_exact_request_native_save_reopen_markdown_and_no_wordpress(self):
        result = self.run_response()
        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(len(self.requests), 1)
        request = self.requests[0]
        self.assertEqual(str(request.url), exp.ENDPOINT)
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.content, self.raw_request)
        self.assertEqual(request.extensions["timeout"], dict(connect=60., read=60., write=60., pool=60.))
        output = Path(result["output"])
        reader = SQLiteHistoryReader(output / "history.sqlite3")
        report = reader.get_artifact(result["artifact_id"]).payload
        self.assertEqual(report, exp.validate_candidate(self.value, self.native_text))
        self.assertEqual(SQLiteHistoryStore(output / "history.sqlite3").list_wordpress_attempts(result["run_id"]), ())
        self.assertTrue(report.requires_human_review)
        rendered = (output / "article-preview.md").read_text(encoding="utf-8")
        self.assertIn("NOT a real model article", rendered)
        self.assertFalse(result["model_generated"])
        for fact in exp.fixture.FACTS:
            self.assertIn(fact, rendered)
        self.assertIn("UNREVIEWED", rendered)
        self.assertIn("## machining tolerance", rendered)
        before = exp.sha((output / "history.sqlite3").read_bytes())
        stdout = StringIO()
        with redirect_stdout(stdout), patch("foreign_trade_geo_agent.cli.load_runtime_environment",
                side_effect=AssertionError("NO ENV LOAD")):
            exit_code = cli_main(["review", "--db", str(output / "history.sqlite3"), "--run-id", result["run_id"],
                                  "--artifact-id", result["artifact_id"], "--draft-id", "D1", "--format", "markdown"])
        self.assertEqual(exit_code, 0)
        self.assertIn("# NovaCNC machining center buyer guide", stdout.getvalue())
        self.assertEqual(exp.sha((output / "history.sqlite3").read_bytes()), before)
        self.assertEqual(result["real_requests"], 0)
        self.assertFalse((self.directory / "live-attempt").exists())

    def test_http_failure_stops_and_does_not_save_raw_secret_error(self):
        result = self.run_response(httpx.Response(429, json={"error": exp.OFFLINE_KEY}))
        self.assert_failed_isolated(result)
        self.assertEqual(result["error"], "SECRET_OUTPUT_REFUSED")
        self.assertEqual(result["http_status"], 429)
        self.assertEqual(result["response_state"], "WITHHELD_SECRET")

    def test_timeout_stops_one_attempt_without_retry(self):
        def timeout(request):
            raise httpx.ReadTimeout("sensitive provider exception", request=request)
        result = self.run_response(callback=timeout)
        self.assert_failed_isolated(result)
        self.assertNotIn("sensitive", json.dumps(result))

    def test_total_deadline_stops_even_mock_stream_without_retry(self):
        async def handler(request):
            self.requests.append(request)
            await asyncio.sleep(1)
        with patch.object(exp, "TIMEOUT_SECONDS", 0.01):
            result = asyncio.run(exp.run_once(self.directory, self.digest, mock_transport=httpx.MockTransport(handler)))
        self.assert_failed_isolated(result)

    def test_redirect_not_followed(self):
        result = self.run_response(httpx.Response(307, headers={"Location": "https://elsewhere.example/"}))
        self.assert_failed_isolated(result)

    def test_invalid_envelope_and_incomplete_output_stop(self):
        for body in ({"model": "other", "choices": []}, self.envelope(finish="length"),
                     self.envelope(finish="tool_calls"), {**self.envelope(), "choices": [1, 2]}):
            with self.subTest(body=str(body)[:30]):
                self.requests = []
                self.assert_failed_isolated(self.run_response(httpx.Response(200, json=body)))

    def test_bad_json_does_not_repair(self):
        result = self.run_response(httpx.Response(200, json=self.envelope("not-json")))
        self.assert_failed_isolated(result)
        self.assertEqual(result["error"], "JSON_FORMAT")

    def test_native_validator_rejects_wrong_change_unknown_refs_numbers_and_promotion(self):
        for category, mutate in (
            ("UNKNOWN_CHANGE_REFERENCE", lambda draft: draft.update(change_ref="C999")),
            ("UNKNOWN_PAGE_REFERENCE", lambda draft: draft["sections"][0]["blocks"][0]["claims"][1].update(page_refs=["P999"])),
            ("NUMERIC_NOT_GROUNDED", lambda draft: draft["sections"][0]["blocks"][0]["claims"][1].update(text=exp.fixture.FACTS[0].replace("8000 rpm", "9000 rpm"))),
            ("UNSUPPORTED_PROMOTIONAL_CLAIM", lambda draft: draft["sections"][0]["blocks"][0]["claims"][1].update(text="Our spindle is the best.")),
        ):
            with self.subTest(category=category):
                self.requests = []
                body = json.loads(self.native_text)
                mutate(body["draft"])
                result = self.run_response(httpx.Response(200, json=self.envelope(json.dumps(body))))
                self.assert_failed_isolated(result)
                self.assertEqual(result["error"], category)

    def test_native_validator_rejects_wrong_outline_and_excess_claims(self):
        for mode in ("outline", "claims"):
            with self.subTest(mode=mode):
                self.requests = []
                body = json.loads(self.native_text)
                if mode == "outline":
                    body["draft"]["sections"][0]["outline_heading"] = "Changed heading"
                else:
                    claim = body["draft"]["sections"][0]["blocks"][0]["claims"][0]
                    body["draft"]["sections"][0]["blocks"][0]["claims"] += [claim] * 5
                result = self.run_response(httpx.Response(200, json=self.envelope(json.dumps(body))))
                self.assert_failed_isolated(result)

    def test_secret_echo_never_saved(self):
        for text in (exp.OFFLINE_KEY, "password: do-not-save-this", 'authorization="secret"'):
            self.requests = []
            result = self.run_response(httpx.Response(200, json=self.envelope(text)))
            self.assert_failed_isolated(result)
            self.assertEqual(result["error"], "SECRET_OUTPUT_REFUSED")
            self.assertNotIn(text, (Path(result["output"]) / "diagnostics.json").read_text())

    def test_response_and_native_output_bounds(self):
        for response in (httpx.Response(200, content=b"x" * (exp.MAX_RESPONSE_BYTES + 1)),
                         httpx.Response(200, json=self.envelope("x" * (cd.MAX_RAW_OUTPUT_CHARS + 1)))):
            self.requests = []
            result = self.run_response(response)
            self.assert_failed_isolated(result)
            self.assertIn(result["error"], {"RESPONSE_BUDGET_EXCEEDED", "OUTPUT_TOO_LARGE"})

    def test_frozen_file_change_blocks_before_any_request(self):
        (self.directory / "user-material.json").write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "FROZEN_INPUT_CHANGED"):
            self.run_response()
        self.assertEqual(self.requests, [])

    def test_frozen_change_during_request_prevents_candidate_export(self):
        def change(request):
            (self.directory / "quality-checklist.json").write_text("changed", encoding="utf-8")
            return httpx.Response(200, json=self.envelope())
        result = self.run_response(callback=change)
        self.assert_failed_isolated(result)
        self.assertEqual(result["error"], "FROZEN_INPUT_CHANGED")

    def test_code_change_or_wrong_bundle_digest_blocks(self):
        for digest, code in (("0" * 64, exp.code_hashes()), (self.digest, {})):
            with self.subTest(digest=digest), patch.object(exp, "code_hashes", return_value=code):
                with self.assertRaises(ValueError):
                    asyncio.run(exp.run_once(self.directory, digest, mock_transport=httpx.MockTransport(lambda r: None)))

    def test_one_shot_guard_rejects_mutated_body_endpoint_method_and_second_request(self):
        async def probe():
            calls = []
            def handler(request):
                calls.append(request)
                return httpx.Response(200)
            guard = exp.OneShotTransport(httpx.MockTransport(handler), self.raw_request)
            for method, url, body in (("GET", exp.ENDPOINT, self.raw_request),
                                      ("POST", "https://elsewhere.example/", self.raw_request),
                                      ("POST", exp.ENDPOINT, self.raw_request + b" ")):
                with self.assertRaisesRegex(ValueError, "SINGLE_REQUEST_GUARD"):
                    await guard.handle_async_request(httpx.Request(method, url, content=body))
            self.assertEqual(len(calls), 0)
            await guard.handle_async_request(httpx.Request("POST", exp.ENDPOINT, content=self.raw_request))
            with self.assertRaisesRegex(ValueError, "SINGLE_REQUEST_GUARD"):
                await guard.handle_async_request(httpx.Request("POST", exp.ENDPOINT, content=self.raw_request))
            self.assertEqual(len(calls), 1)
        asyncio.run(probe())

    def test_mock_mode_refuses_other_transport_and_live_requires_unexpired_binding(self):
        with self.assertRaisesRegex(ValueError, "MOCK_TRANSPORT_REQUIRED"):
            asyncio.run(exp.run_once(self.directory, self.digest, mock_transport=object()))
        for expiry in (None, datetime.now(), datetime.now(UTC) - timedelta(seconds=1)):
            with self.assertRaisesRegex(ValueError, "LIVE_AUTHORIZATION_EXPIRED_OR_MISSING"):
                asyncio.run(exp.run_once(self.directory, self.digest, expires_at=expiry))
        self.assertFalse((self.directory / "live-attempt").exists())

    def test_live_branch_with_fake_network_reserves_once_and_configures_no_retry(self):
        # Exercise the otherwise unexecuted branch with a MOCK replacing the
        # real transport constructor. There is no paid/network request here.
        expiry = datetime.now(UTC) + timedelta(minutes=5)
        def handler(request):
            self.requests.append(request)
            return httpx.Response(503, json={"error": "not persisted"})
        with patch("scripts.local_env.load_api_keys"), patch.dict("os.environ", {"DEEPSEEK_API_KEY": "fake-live-key"}), patch(
                "httpx.AsyncHTTPTransport", return_value=httpx.MockTransport(handler)) as factory:
            result = asyncio.run(exp.run_once(self.directory, self.digest, expires_at=expiry))
            factory.assert_called_once_with(retries=0, trust_env=False)
            self.assertEqual(result["status"], "FAILED")
            self.assertEqual(len(self.requests), 1)
            self.assertTrue((self.directory / "live-attempt/started.json").exists())
            with self.assertRaises(FileExistsError):
                asyncio.run(exp.run_once(self.directory, self.digest, expires_at=expiry))
            factory.assert_called_once()

    def test_production_adapter_and_gate_still_reject(self):
        prompt = cd.build_content_draft_prompt(self.value, "C1")
        result = asyncio.run(DeepSeekContentDraftWriter().write_content_draft(prompt))
        self.assertEqual(result.error, "DRAFT_EXECUTION_AUTHORIZATION_REQUIRED")
        class TestAdmission:
            def rejection_reason(self, value):
                return None  # Even permissive TEST/legacy admission is refused.
        never = exp.fixture.NeverDraft()
        report = asyncio.run(ContentDraftWorkflow(never, intake_admission=TestAdmission()).run(self.value))
        self.assertEqual(report.error, "INTAKE_EXECUTION_BLOCKED")
        self.assertEqual(never.calls, 0)

    def test_quality_review_is_pending_and_missing_fact_is_not_silently_accepted_as_quality(self):
        checklist = exp.quality_checklist()
        self.assertIn("PENDING", checklist["decision"])
        self.assertEqual(len(checklist["required_facts"]), 3)
        self.assertTrue(all(item["decision"] == "UNREVIEWED" for item in checklist["checks"]))
        # Native validity does not guarantee semantic coverage. The independent
        # ledger remains necessary even if a syntactically valid claim is lost.
        body = json.loads(self.native_text)
        body["draft"]["sections"][1]["blocks"][1]["claims"] = body["draft"]["sections"][1]["blocks"][1]["claims"][1:]
        report = exp.validate_candidate(self.value, json.dumps(body))
        self.assertTrue(report.requires_human_review)
        self.assertIn("UNREVIEWED", json.dumps(checklist))

    def test_prepare_never_overwrites_existing_bundle(self):
        with self.assertRaisesRegex(ValueError, "OUTPUT_MUST_BE_NEW"):
            exp.prepare(self.directory)

    def test_budget_conflict_stops_preparation_without_deleting_facts_or_increasing_cap(self):
        output = Path(self.temporary.name) / "over-budget"
        with patch.object(exp, "EXPERIMENT_INSTRUCTIONS", "x" * 9000):
            with self.assertRaisesRegex(ValueError, "INPUT_BUDGET_CONFLICT"):
                exp.prepare(output)
        self.assertFalse(output.exists())
        self.assertEqual(exp.request_for(self.value)[0]["max_tokens"], 3000)
        self.assertEqual(len(exp.requirements()["mandatory_facts_and_qualifiers"]), 3)

    def test_missing_credentials_consume_live_reservation_without_http(self):
        with patch("scripts.local_env.load_api_keys"), patch.dict("os.environ", {"DEEPSEEK_API_KEY": ""}), patch(
                "httpx.AsyncHTTPTransport", side_effect=AssertionError("NO TRANSPORT")):
            result = asyncio.run(exp.run_once(self.directory, self.digest,
                                             expires_at=datetime.now(UTC) + timedelta(minutes=1)))
        self.assertEqual(result["error"], "CREDENTIALS_UNAVAILABLE")
        self.assertEqual(result["real_requests"], 0)
        self.assertTrue((self.directory / "live-attempt/started.json").exists())

    def test_transport_checks_expiry_immediately_before_delegation(self):
        async def probe():
            guard = exp.OneShotTransport(httpx.MockTransport(lambda r: self.fail("NO HTTP")),
                self.raw_request, expires_at=datetime.now(UTC) - timedelta(seconds=1))
            with self.assertRaisesRegex(ValueError, "LIVE_AUTHORIZATION_EXPIRED_OR_MISSING"):
                await guard.handle_async_request(httpx.Request("POST", exp.ENDPOINT, content=self.raw_request))
            self.assertEqual(guard.calls, 0)
        asyncio.run(probe())


if __name__ == "__main__":
    unittest.main()
