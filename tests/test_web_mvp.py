"""Offline product flow, durable Intake and frozen native candidate boundaries."""
import ipaddress
import json
from pathlib import Path
import re
import socket
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient


class MVPWebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from scripts.prepare_web_mvp import prepare
        cls.fixture_temp = TemporaryDirectory()
        cls.addClassCleanup(cls.fixture_temp.cleanup)
        cls.fixture = Path(cls.fixture_temp.name) / "package"
        connect = socket.socket.connect
        def offline(sock, address):
            if not isinstance(address, tuple) or not ipaddress.ip_address(address[0]).is_loopback:
                raise AssertionError("external network forbidden")
            return connect(sock, address)
        with patch.object(socket.socket, "connect", new=offline):
            prepare(cls.fixture)

    def setUp(self):
        import shutil
        from foreign_trade_geo_agent.web.app import create_app
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.package = self.root / "package"
        shutil.copytree(self.fixture, self.package)
        self.app = create_app(db_path=self.root / "old-demo.db", live_db_path=self.root / "live.db",
                              mvp_dir=self.package)
        self.client = self.enterContext(TestClient(self.app, base_url="http://127.0.0.1"))

    def form(self):
        html = self.client.get("/mvp/evidence").text
        return {name: re.search(r'name="' + name + r'" value="([^"]*)"', html).group(1)
                for name in ("csrf_token", "expected_sha256")}

    def test_real_saved_analysis_and_url_lookup_never_connect(self):
        with patch.object(socket.socket, "connect", side_effect=AssertionError("network forbidden")):
            page = self.client.get("/mvp")
            self.assertEqual(page.status_code, 200)
            self.assertIn("NovaCNC", page.text)
            self.assertIn("Buyer considerations", page.text)
            self.assertIn("spindle performance", page.text)
            response = self.client.get("/mvp?website_url=https%3A%2F%2Funapproved.example%2F")
            self.assertIn("没有已保存的分析", response.text)

    def test_submit_recheck_refresh_restart_and_exact_native_export(self):
        from scripts.demo_seo_e_only import DOCUMENT, FACT
        from foreign_trade_geo_agent.web.mvp_application import MVPApplicationService
        initial = self.client.get("/mvp/evidence")
        self.assertIn("WAITING_FOR_EVIDENCE", initial.text)
        stale = self.form()
        response = self.client.post("/mvp/evidence", data={**stale, "content": DOCUMENT, "source_label": "合成 E1"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("RECHECK_REQUIRED", response.text)
        self.assertIn("合成 E1", response.text)
        self.assertIn("E1", response.text)
        conflict = self.client.post("/mvp/evidence", data={**stale, "content": DOCUMENT, "source_label": "duplicate"})
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(self.client.post("/mvp/recheck", data=self.form()).status_code, 200)
        self.assertIn("WAITING_FOR_HUMAN_REVIEW", self.client.get("/mvp/evidence").text)
        reopened = MVPApplicationService(self.package)
        self.assertEqual(reopened.evidence()["state"], "WAITING_FOR_HUMAN_REVIEW")
        draft = self.client.get("/mvp/article")
        for text in (FACT, "UNREVIEWED", "CL3", "E1", "离线合成 writer", "预先生成"):
            self.assertIn(text, draft.text)
        exported = self.client.get("/mvp/article.md")
        self.assertEqual(exported.content, reopened.markdown().encode("utf-8"))
        # Existing preparation writes native Markdown through Windows text I/O
        # (CRLF); HTTP uses the renderer's canonical LF UTF-8 representation.
        self.assertEqual(exported.content,
                         (self.package / "candidate/article-review.md").read_text(encoding="utf-8").encode("utf-8"))

    def test_input_security_and_no_approval_route(self):
        form = self.form()
        self.assertEqual(self.client.post("/mvp/evidence", data={**form, "csrf_token": "forged", "content": "x"}).status_code, 403)
        self.assertEqual(self.client.post("/mvp/evidence", data={**form, "csrf_token": "非ASCII", "content": "x"}).status_code, 403)
        self.assertEqual(self.client.post("/mvp/recheck", data=form, headers={"Host": "evil.example"}).status_code, 403)
        self.assertEqual(self.client.post("/mvp/evidence", data={**form, "content": " "}).status_code, 422)
        self.assertEqual(self.client.post("/mvp/evidence", data={**form, "content": "x" * 50000}).status_code, 413)
        self.assertEqual(self.client.post("/mvp/approve", data=form).status_code, 404)
        self.assertEqual(self.client.post("/mvp/deliver", data=form).status_code, 404)

    def test_modified_customer_text_does_not_modify_pre_generated_candidate(self):
        before = self.client.get("/mvp/article.md").content
        form = self.form()
        text = '<script>alert("x")</script> different synthetic facts'
        response = self.client.post("/mvp/evidence", data={**form, "content": text, "source_label": "changed"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('<script>alert("x")</script>', response.text)
        self.assertIn("&lt;script&gt;", response.text)
        self.assertEqual(self.client.get("/mvp/article.md").content, before)
        self.assertIn("不匹配", self.client.get("/mvp/article").text)

    def test_browser_crlf_submission_matches_lf_frozen_sample(self):
        from scripts.demo_seo_e_only import DOCUMENT
        response = self.client.post("/mvp/evidence", data={**self.form(),
            "content": DOCUMENT.replace("\n", "\r\n"), "source_label": "Browser textarea"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("当前文本与候选冻结的 E1 原文一致", self.client.get("/mvp/article").text)

    def test_maximum_cjk_text_is_accepted_and_native_candidate_stays_immutable(self):
        original = (self.package / "candidate/history.sqlite3").read_bytes()
        response = self.client.post("/mvp/evidence", data={**self.form(), "content": "中" * 16000,
                                                           "source_label": "中文文本"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.post("/mvp/recheck", data=self.form()).status_code, 200)
        self.assertEqual((self.package / "candidate/history.sqlite3").read_bytes(), original)

    def test_missing_frozen_candidate_does_not_block_interactive_intake(self):
        from uuid import uuid4
        session_path = self.package / "session.json"
        session = json.loads(session_path.read_text(encoding="utf-8"))
        session["candidate_run_id"] = str(uuid4())
        session_path.write_text(json.dumps(session), encoding="utf-8")
        response = self.client.get("/mvp/evidence")
        self.assertEqual(response.status_code, 200)
        self.assertIn("WAITING_FOR_EVIDENCE", response.text)
        self.assertEqual(self.client.post("/mvp/evidence", data={**self.form(), "content": "资料",
                                                               "source_label": "自有文本"}).status_code, 200)
        self.assertEqual(self.client.get("/mvp/article").status_code, 503)

    def test_malformed_utf8_and_oversized_chunked_body_create_no_revision(self):
        revision = self.app.state.mvp_service.evidence()["snapshot"].revision
        malformed = self.client.post("/mvp/evidence", content=b"content=%FF",
                                    headers={"Content-Type": "application/x-www-form-urlencoded"})
        self.assertEqual(malformed.status_code, 422)
        def chunks():
            yield b"content="
            yield b"x" * 201000
        oversized = self.client.post("/mvp/evidence", content=chunks(),
                                     headers={"Content-Type": "application/x-www-form-urlencoded"})
        self.assertEqual(oversized.status_code, 413)
        self.assertEqual(self.app.state.mvp_service.evidence()["snapshot"].revision, revision)

    def test_empty_and_corrupt_package_are_sanitized(self):
        from foreign_trade_geo_agent.web.mvp_application import MVPApplicationService
        self.assertFalse(MVPApplicationService(self.root / "missing").ready)
        (self.package / "session.json").write_text('{"bad": "secret"}', encoding="utf-8")
        response = self.client.get("/mvp")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("secret", response.text)


if __name__ == "__main__":
    unittest.main()
