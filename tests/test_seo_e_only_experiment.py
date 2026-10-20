"""Isolated E-only request and local MVP bridge; no external transport."""
import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from scripts import demo_seo_e_only as fixture
from scripts import prepare_seo_article_experiment as shared
from foreign_trade_geo_agent.core import content_draft as cd
from foreign_trade_geo_agent.core.history import ArtifactType
from foreign_trade_geo_agent.storage.sqlite import SQLiteHistoryReader, SQLiteHistoryStore


class EOnlyExperimentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        from scripts import prepare_seo_e_only_experiment as exp
        cls.exp = exp
        cls.frozen = Path(cls.temp.name) / "frozen"
        with patch("httpx.AsyncHTTPTransport", side_effect=AssertionError("NO LIVE")), patch(
                "scripts.local_env.load_api_keys", side_effect=AssertionError("NO SECRETS")):
            cls.summary = exp.prepare(cls.frozen)
        cls.digest = cls.summary["bundle_sha256"]
        cls.value, cls.request = exp.load_frozen(cls.frozen, cls.digest)
        cls.text = asyncio.run(fixture.FixedEOnlyWriter().write_content_draft(
            cd.build_content_draft_prompt(cls.value, "C1"))).text

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / "frozen"
        shutil.copytree(self.frozen, self.directory)

    def run_mock(self, text=None, handler=None, finish="stop"):
        def respond(request):
            self.assertEqual(request.content, self.request)
            if handler:
                return handler(request)
            return httpx.Response(200, json={"model": "deepseek-flash", "choices": [{
                "message": {"content": self.text if text is None else text}, "finish_reason": finish}]})
        with patch("httpx.AsyncHTTPTransport", side_effect=AssertionError("NO LIVE")), patch(
                "scripts.local_env.load_api_keys", side_effect=AssertionError("NO SECRETS")):
            return asyncio.run(self.exp.run_once(self.directory, self.digest,
                mock_transport=httpx.MockTransport(respond)))

    def test_frozen_e1_only_fact_exact_request_and_version_binding(self):
        payload = json.loads(self.request)
        material = json.loads(payload["messages"][1]["content"])
        self.assertEqual(material["contract"]["customer_refs"], ["E1"])
        self.assertEqual(material["customer_evidence"]["sources"][0]["quote"], fixture.FACT)
        ps = json.dumps([material["pages"], material["sources"]])
        for exclusive in ("7200 rpm", "NCX7", "NOVA-TEST-7"):
            self.assertNotIn(exclusive, ps)
        self.assertIn("E INPUT RULE", payload["messages"][0]["content"])
        self.assertNotIn("fictional NovaCNC P/S material", payload["messages"][0]["content"])
        self.assertEqual(payload["max_tokens"], 3000)
        self.assertLessEqual(len(self.request), 16000)
        self.assertEqual(self.summary["production_gate"], "INTAKE_EXECUTION_BLOCKED")
        frozen_input = json.loads((self.directory / "native-input.json").read_text(encoding="utf-8"))
        binding = frozen_input["customer_evidence"]
        self.assertEqual(binding["evidence_version"], 2)
        self.assertEqual(binding["plan_version"], 2)
        self.assertEqual(self.summary["request_sha256"], shared.sha(self.request))

    def test_mock_native_persistence_review_and_existing_web_pages(self):
        result = self.run_mock()
        self.assertEqual(result["status"], "SUCCESS", result)
        self.assertEqual(result["request_count"], 1)
        self.assertEqual(result["real_requests"], 0)
        output = Path(result["output"])
        reader = SQLiteHistoryReader(output / "history.sqlite3")
        report = reader.get_artifact(result["artifact_id"]).payload
        claim = next(c for b in report.drafts[0].blocks for c in b.claims if c.customer_refs)
        self.assertEqual(claim.customer_refs, ("E1",))
        self.assertEqual(claim.page_refs, ())
        self.assertEqual(claim.text, fixture.FACT)
        self.assertEqual(report.drafts[0].customer_evidence.snapshot_sha256,
                         self.value.customer_evidence.snapshot_sha256)
        self.assertEqual(SQLiteHistoryStore(output / "history.sqlite3").list_wordpress_attempts(result["run_id"]), ())
        self.assertIn("MOCK", (output / "article-preview.md").read_text(encoding="utf-8"))
        self.assertTrue((output / "execution-review.json").is_file())
        assessment = json.loads((output / "execution-review.json").read_bytes())
        self.assertEqual(assessment["before"]["snapshot_sha256"], assessment["after"]["snapshot_sha256"])
        self.assertFalse(assessment["human_signoff"])
        web = Path(self.temp.name) / "web"
        self.exp.prepare_web_preview(self.directory, self.digest, result, web)
        from foreign_trade_geo_agent.web.app import create_app
        from foreign_trade_geo_agent.web.mvp_application import MVPApplicationService
        service = MVPApplicationService(web)
        with TestClient(create_app(db_path=Path(self.temp.name) / "demo.db",
                live_db_path=Path(self.temp.name) / "live.db", mvp_dir=web), base_url="http://127.0.0.1") as client:
            for path in ("/mvp", "/mvp/evidence", "/mvp/article", "/mvp/article.md"):
                page = client.get(path)
                self.assertEqual(page.status_code, 200, page.text)
            html = client.get("/mvp/article").text
            for expected in (fixture.FACT, "MockTransport", "UNREVIEWED", "版本一致"):
                self.assertIn(expected, html)
            self.assertEqual(client.get("/mvp/article.md").content, service.markdown().encode())
            self.assertIn("MockTransport", client.get("/mvp/article.md").text)
            # Web integration now exists, but this preview has no injected executor.
            self.assertEqual(client.post("/mvp/generate").status_code, 422)
            self.assertIn('未配置隔离 Mock 执行器', client.get('/mvp/generate').text)
            self.assertIsNone(client.app.state.mvp_service.generation_executor)
            self.assertFalse((web / 'generation').exists())
        self.assertTrue(service.article()["version_matches"])
        current = service.evidence()
        service.submit(expected_sha256=current["expected_sha256"], content=fixture.DOCUMENT, source_label="same text new revision")
        self.assertFalse(service.article()["version_matches"])

    def test_native_e_errors_stop_without_candidate_or_retry(self):
        original = json.loads(self.text)
        for mutation in ("missing", "wrong_ref", "number", "qualifier"):
            raw = json.loads(self.text)
            claims = raw["draft"]["sections"][0]["blocks"][1]["claims"]
            fact = claims[0]
            if mutation == "missing":
                claims.pop(0)
            elif mutation == "wrong_ref":
                fact["customer_refs"] = ["E999"]
            elif mutation == "number":
                fact["text"] = fact["text"].replace("7200 rpm", "7300 rpm")
            else:
                fact["text"] = fact["text"].replace(" continuously", "")
            with self.subTest(mutation=mutation):
                result = self.run_mock(json.dumps(raw))
                self.assertEqual(result["status"], "FAILED")
                self.assertEqual(result["request_count"], 1)
                output = Path(result["output"])
                self.assertEqual({p.name for p in output.iterdir()}, {
                    "started.json", "diagnostics.json", "response-body.bin", "model-output.txt", "rejected-candidate.txt"})
                self.assertEqual((output / "rejected-candidate.txt").read_bytes(), json.dumps(raw).encode())
                self.assertEqual(shared.sha((output / "response-body.bin").read_bytes()), result["response_sha256"])
                self.assertFalse((output / "history.sqlite3").exists())
                self.assertFalse((output / "content-draft.json").exists())
        self.assertEqual(json.loads(self.text), original)

    def test_changed_freeze_before_request_and_after_await_rejected(self):
        with (self.directory / "customer-E1.txt").open("ab") as stream:
            stream.write(b" changed")
        with self.assertRaisesRegex(ValueError, "FROZEN_INPUT_CHANGED"):
            self.run_mock()
        shutil.copyfile(self.frozen / "customer-E1.txt", self.directory / "customer-E1.txt")
        def mutate(request):
            (self.directory / "task.json").write_text("{}", encoding="utf-8")
            return httpx.Response(200, json={"model": "deepseek-flash", "choices": [{
                "message": {"content": self.text}, "finish_reason": "stop"}]})
        result = self.run_mock(handler=mutate)
        self.assertEqual(result["error"], "FROZEN_INPUT_CHANGED")
        self.assertFalse((Path(result["output"]) / "history.sqlite3").exists())

    def test_fresh_test_assessment_and_revocation_without_freeze_mutation(self):
        before = shared.sha((self.directory / "intake.sqlite3").read_bytes())
        later = datetime.now(UTC) + timedelta(days=1)
        value, request = self.exp.load_frozen(self.directory, self.digest, now=later)
        self.assertEqual(value.customer_evidence.reviewed_at, later)
        self.assertTrue(value.customer_evidence.fresh_at(later))
        self.assertEqual(request, self.request)
        self.assertEqual(shared.sha((self.directory / "intake.sqlite3").read_bytes()), before)
        with patch.object(fixture.SyntheticEOnlyReviewer, "assess", side_effect=ValueError("REVOKED")):
            with self.assertRaises(ValueError):
                self.exp.load_frozen(self.directory, self.digest)

    def test_live_missing_authorization_does_not_reserve_attempt(self):
        with self.assertRaisesRegex(ValueError, "LIVE_AUTHORIZATION_EXPIRED_OR_MISSING"):
            asyncio.run(self.exp.run_once(self.directory, self.digest))
        self.assertFalse((self.directory / "live-attempt").exists())

    def test_e_prompt_through_existing_deepseek_adapter_mock(self):
        from foreign_trade_geo_agent.adapters.deepseek_content_draft import DeepSeekContentDraftWriter
        def handler(request):
            body = json.loads(request.content)
            material = json.loads(body["messages"][1]["content"])
            self.assertEqual(material["contract"]["customer_refs"], ["E1"])
            self.assertIn("E INPUT RULE", body["messages"][0]["content"])
            return httpx.Response(200, json={"choices": [{"message": {"content": self.text}, "finish_reason": "stop"}]})
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": shared.OFFLINE_KEY}):
            writer = DeepSeekContentDraftWriter(transport=httpx.MockTransport(handler))
            generation = asyncio.run(writer.write_content_draft(cd.build_content_draft_prompt(self.value, "C1")))
        self.assertEqual(generation.status, cd.ContentDraftGenerationStatus.SUCCESS)
        self.assertEqual(self.exp.validate_candidate(self.value, generation.text).status, cd.ContentDraftStatus.SUCCESS)

    def test_review_revoked_during_model_response_discards_candidate(self):
        def handler(request):
            patcher = patch.object(fixture.SyntheticEOnlyReviewer, "assess", side_effect=ValueError("REVOKED"))
            patcher.start()
            self.addCleanup(patcher.stop)
            return httpx.Response(200, json={"model": "deepseek-flash", "choices": [{
                "message": {"content": self.text}, "finish_reason": "stop"}]})
        result = self.run_mock(handler=handler)
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["request_count"], 1)
        self.assertEqual({p.name for p in Path(result["output"]).iterdir()}, {
            "started.json", "diagnostics.json", "response-body.bin", "model-output.txt"})
        self.assertFalse((Path(result["output"]) / "history.sqlite3").exists())

    def test_changed_plan_or_request_and_code_rejected_before_network(self):
        for name in ("change-plan.json", "request.json", "native-input.json", "intake.sqlite3"):
            with self.subTest(name=name):
                original = (self.directory / name).read_bytes()
                (self.directory / name).write_bytes(original + b" ")
                with self.assertRaisesRegex(ValueError, "FROZEN_INPUT_CHANGED"):
                    self.run_mock()
                (self.directory / name).write_bytes(original)
        with patch.object(self.exp, "code_hashes", return_value={}):
            with self.assertRaisesRegex(ValueError, "EXPERIMENT_CODE_CHANGED"):
                self.run_mock()
        self.assertEqual(list(self.directory.glob("mock-*")), [])

    def test_expired_execution_assessment_cannot_be_persisted(self):
        expired = replace(self.value, customer_evidence=replace(self.value.customer_evidence,
            reviewed_at=datetime.now(UTC) - timedelta(minutes=6)))
        with self.assertRaisesRegex(ValueError, "CUSTOMER_EVIDENCE_INVALID"):
            self.exp.revalidate_execution(expired, self.value)

    def test_incomplete_provider_result_creates_no_candidate(self):
        result = self.run_mock(finish="length")
        self.assertEqual(result["error"], "OUTPUT_INCOMPLETE")
        self.assertEqual(result["request_count"], 1)
        self.assertFalse((Path(result["output"]) / "history.sqlite3").exists())


if __name__ == "__main__":
    unittest.main()
