import asyncio
from contextlib import ExitStack, redirect_stdout
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

import httpx

from foreign_trade_geo_agent.audit_cli import main
from foreign_trade_geo_agent.audit_runtime import (
    AuditBudgets, check_live_permission, export_audit, load_fixture,
)
from foreign_trade_geo_agent.adapters.page_extractor import TrafilaturaPageExtractor
from foreign_trade_geo_agent.reporting.audit_package import PackageExporter, verify_package


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "src/foreign_trade_geo_agent/web/fixtures/novacnc"
URL = "https://novacnc.example/"


class ReadonlySeoAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name) / "audit"
        self.url, self.provenance, self.resolver, self.factory = load_fixture(FIXTURE)

    def run_audit(self, *, handler=None, budgets=None, resolver=None, extractor=None, url=URL):
        return asyncio.run(export_audit(
            url, self.output, provenance=self.provenance,
            resolver=resolver or self.resolver,
            transport_factory=(lambda *_: httpx.MockTransport(handler)) if handler else self.factory,
            budgets=budgets, extractor=extractor,
        ))

    def read(self, name):
        return json.loads((self.output / name).read_bytes())

    @staticmethod
    def normal_handler(request):
        path = request.url.path
        name = "index.html" if path == "/" else path.lstrip("/")
        return httpx.Response(200, content=(FIXTURE / name).read_bytes(),
                              headers={"content-type": "text/plain" if path == "/robots.txt" else "text/html"})

    def test_native_chain_zero_provider_construction_dns_sockets_and_wordpress(self):
        # Fail if any optional planning/CMS module is even imported by this entry.
        import builtins
        original = builtins.__import__

        provider_constructors = (
            "foreign_trade_geo_agent.adapters.deepseek_research.DeepSeekResearchWriter.__init__",
            "foreign_trade_geo_agent.adapters.deepseek_change_plan.DeepSeekChangePlanWriter.__init__",
            "foreign_trade_geo_agent.adapters.deepseek_content_opportunity.DeepSeekContentOpportunityWriter.__init__",
            "foreign_trade_geo_agent.adapters.deepseek_content_draft.DeepSeekContentDraftWriter.__init__",
            "foreign_trade_geo_agent.adapters.tavily_search.TavilySearchAdapter.__init__",
            "foreign_trade_geo_agent.adapters.wordpress_rest.WordPressRestDraftPublisher.__init__",
        )

        def guarded(name, *args, **kwargs):
            if any(word in name for word in ("deepseek", "tavily", "wordpress", "industry_research", "change_plan", "content_draft")):
                raise AssertionError("Forbidden provider dependency")
            return original(name, *args, **kwargs)

        async def run_guarded():
            # Windows asyncio creates a loopback self-pipe while making the loop.
            # Install the outbound tripwires after loop initialization.
            with patch("builtins.__import__", side_effect=guarded), \
                    patch.object(socket, "getaddrinfo", side_effect=AssertionError("DNS forbidden")), \
                    patch.object(socket.socket, "connect", side_effect=AssertionError("Network forbidden")):
                return await export_audit(self.url, self.output, provenance=self.provenance,
                                          resolver=self.resolver, transport_factory=self.factory)
        with ExitStack() as stack:
            for target in provider_constructors:
                stack.enter_context(patch(target, side_effect=AssertionError("Forbidden provider constructed")))
            self.assertEqual(asyncio.run(run_guarded()), 0)
        manifest = verify_package(self.output)
        self.assertEqual(manifest["outcome"], "sample_complete")
        self.assertEqual(manifest["output_summary"]["crawl_pages"], 2)
        self.assertEqual(manifest["output_summary"]["packet_pages"], 2)
        self.assertEqual(manifest["provenance"]["kind"], "synthetic_fixture")
        self.assertFalse(manifest["full_site_audit"])
        self.assertEqual([r["method"] for r in self.read("requests.json")], ["GET"] * 3)
        self.assertEqual(self.read("audit.json")["source"], "crawl-seo-audit")
        self.assertIn("meta.title.coverage", manifest["audit_coverage"])
        self.assertEqual(manifest["resources"]["request_attempts"], 3)
        self.assertEqual(self.read("packet.json")["pages"][0]["evidence_id"], "P1")

    def test_cli_actual_fixture_and_integrity_commands(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(["fixture", "--fixture-dir", str(FIXTURE),
                                   "--output-dir", str(self.output)]), 0)
            self.assertEqual(main(["verify", str(self.output)]), 0)

    def test_generic_seed_not_hardcoded_to_novacnc(self):
        self.assertEqual(self.run_audit(url="https://industrial.example/"), 0)
        self.assertEqual(self.read("manifest.json")["exact_origin"]["host"], "industrial.example")
        # NovaCNC canonical is merely observed as out-of-origin, never followed.
        self.assertTrue(all("industrial.example" in u for u in self.read("manifest.json")["http_attempt_urls"]))
        checks = {e["check_key"]: e for e in self.read("audit.json")["evidence"]}
        self.assertEqual(checks["meta.canonical.valid_exact_origin"]["outcome"], "warning")

    def test_files_read_back_hash_and_summary_consistency(self):
        self.run_audit()
        manifest = verify_package(self.output)
        for name, item in manifest["files"].items():
            data = (self.output / name).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), item["sha256"])
            self.assertEqual(len(data), item["bytes"])
        self.assertEqual(manifest["input_summary"]["sha256"], manifest["files"]["input.json"]["sha256"])
        self.assertEqual(manifest["output_summary"]["score"], self.read("audit.json")["score"])
        self.assertFalse((self.output / "INCOMPLETE.json").exists())
        (self.output / "packet.json").write_text("{}", encoding="utf-8")
        with self.assertRaises(ValueError):
            verify_package(self.output)

    def test_no_overwrite_or_network_when_output_already_exists(self):
        self.run_audit()
        before = {p.name: p.read_bytes() for p in self.output.iterdir()}
        with self.assertRaises(FileExistsError):
            self.run_audit(handler=lambda request: self.fail("Must not request"))
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.output.iterdir()})

    def test_export_interruption_keeps_incomplete_marker(self):
        original = PackageExporter._write

        def fail_during_export(exporter, name, data):
            if name == "packet.json":
                raise OSError("secret-token-must-not-be-exported")
            original(exporter, name, data)

        with patch.object(PackageExporter, "_write", fail_during_export), self.assertRaises(OSError):
            self.run_audit()
        self.assertTrue((self.output / "INCOMPLETE.json").exists())
        with self.assertRaises(ValueError):
            verify_package(self.output)
        self.assertNotIn("secret-token", "".join(p.read_text(encoding="utf-8") for p in self.output.iterdir()))

    def test_manifest_present_but_marker_still_blocks(self):
        self.run_audit()
        (self.output / "INCOMPLETE.json").write_text("{}")
        with self.assertRaises(ValueError):
            verify_package(self.output)

    def test_manifest_summary_mismatch_rejected(self):
        self.run_audit()
        manifest = self.read("manifest.json")
        manifest["output_summary"]["crawl_pages"] = 5
        (self.output / "manifest.json").write_text(json.dumps(manifest))
        with self.assertRaises(ValueError):
            verify_package(self.output)

    def test_runtime_live_cannot_bypass_permission_with_provenance_boolean(self):
        with patch("foreign_trade_geo_agent.audit_runtime.SafeHtmlFetcher") as fetcher:
            with self.assertRaises(ValueError):
                asyncio.run(export_audit(URL, self.output, provenance={"authorized": True}))
            fetcher.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_robots_unknown_is_not_allow(self):
        def handler(request):
            self.assertEqual(request.url.path, "/robots.txt")
            raise httpx.ConnectError("secret-key-do-not-store")
        self.assertEqual(self.run_audit(handler=handler), 1)
        manifest = verify_package(self.output)
        self.assertEqual(manifest["robots_status"], "fetch_failed")
        self.assertFalse(manifest["sample_complete"])
        self.assertEqual(self.read("audit.json")["status"], "failed")
        self.assertNotIn("secret-key", "".join(p.read_text(encoding="utf-8") for p in self.output.iterdir()))

    def test_robots_disallow_stops_content_requests(self):
        def handler(request):
            self.assertEqual(request.url.path, "/robots.txt")
            return httpx.Response(200, text="User-agent: *\nDisallow: /\n", headers={"content-type": "text/plain"})
        self.assertEqual(self.run_audit(handler=handler), 1)
        self.assertEqual(self.read("manifest.json")["robots_status"], "disallowed")
        self.assertEqual(len(self.read("requests.json")), 1)

    def test_dns_private_address_rejected_before_transport(self):
        class PrivateResolver:
            async def resolve(self, host, port):
                return ("127.0.0.1",)
        self.assertEqual(self.run_audit(resolver=PrivateResolver(), handler=lambda r: self.fail("Network attempted")), 1)
        self.assertEqual(self.read("requests.json"), [])
        self.assertEqual(self.read("crawl.json")["robots_fetch_failure_kind"], "safety_policy_rejected")

    def test_cross_origin_redirect_not_visited(self):
        def handler(request):
            if request.url.path == "/robots.txt":
                return self.normal_handler(request)
            return httpx.Response(302, headers={"location": "https://other.example/private?token=secret"})
        self.assertEqual(self.run_audit(handler=handler), 1)
        manifest = self.read("manifest.json")
        self.assertEqual(len(manifest["http_attempt_urls"]), 2)
        self.assertNotIn("other.example", str(manifest["http_attempt_urls"]))
        self.assertEqual(self.read("crawl.json")["failures"][0]["fetch_failure_kind"], "origin_rejected")
        self.assertNotIn("token=secret", str(manifest))

    def test_redirect_denied_by_robots_is_never_visited(self):
        def handler(request):
            if request.url.path == "/robots.txt":
                return httpx.Response(200, text="User-agent: *\nDisallow: /private\n", headers={"content-type": "text/plain"})
            self.assertEqual(request.url.path, "/")
            return httpx.Response(302, headers={"location": "/private"})
        self.assertEqual(self.run_audit(handler=handler), 1)
        self.assertEqual(len(self.read("requests.json")), 2)
        self.assertEqual(self.read("crawl.json")["failures"][0]["fetch_failure_kind"], "redirect_policy_rejected")

    def test_same_origin_redirect_records_actual_http_hops(self):
        def handler(request):
            if request.url.path == "/":
                return httpx.Response(302, headers={"location": "/machines.html"})
            return self.normal_handler(request)
        self.assertEqual(self.run_audit(handler=handler), 0)
        manifest = self.read("manifest.json")
        self.assertEqual(manifest["visited_pages"][0]["requested_url"], URL)
        self.assertEqual(manifest["visited_pages"][0]["final_url"], URL + "machines.html")
        self.assertEqual([r["http_status"] for r in self.read("requests.json")], [200, 302, 200])

    def test_request_budget_stops_before_content(self):
        self.assertEqual(self.run_audit(budgets=AuditBudgets(max_request_attempts=1)), 1)
        self.assertEqual(self.read("manifest.json")["outcome"], "budget_exhausted")
        self.assertEqual(self.read("manifest.json")["stop_reason"], "request_budget")

    def test_wire_budget_stops_with_explicit_failed_audit(self):
        self.assertEqual(self.run_audit(budgets=AuditBudgets(max_total_wire_bytes=10)), 1)
        self.assertEqual(self.read("manifest.json")["stop_reason"], "total_wire_budget")
        self.assertEqual(self.read("audit.json")["status"], "failed")

    def test_decoded_budget_stops_with_explicit_failed_audit(self):
        self.assertEqual(self.run_audit(budgets=AuditBudgets(max_total_decoded_bytes=10)), 1)
        self.assertEqual(self.read("manifest.json")["stop_reason"], "total_decoded_budget")
        self.assertEqual(self.read("audit.json")["status"], "failed")

    def test_page_budget_preserves_sample_but_returns_nonzero(self):
        self.assertEqual(self.run_audit(budgets=AuditBudgets(max_pages=1)), 3)
        manifest = self.read("manifest.json")
        self.assertEqual(manifest["outcome"], "budget_exhausted")
        self.assertEqual(manifest["output_summary"]["crawl_pages"], 1)
        self.assertFalse(manifest["sample_complete"])

    def test_runtime_budget_stops_and_reports_failure(self):
        async def handler(request):
            await asyncio.sleep(0.1)
            return self.normal_handler(request)
        self.assertEqual(self.run_audit(handler=handler, budgets=AuditBudgets(max_runtime=0.01)), 1)
        self.assertEqual(self.read("manifest.json")["stop_reason"], "time_limit")

    def test_partial_page_failure_not_success_acceptance(self):
        def handler(request):
            if request.url.path == "/machines.html":
                return httpx.Response(503)
            return self.normal_handler(request)
        self.assertEqual(self.run_audit(handler=handler), 3)
        manifest = self.read("manifest.json")
        self.assertEqual(manifest["outcome"], "partial")
        self.assertEqual(len(manifest["failures"]), 1)
        self.assertEqual(manifest["output_summary"]["crawl_pages"], 1)
        self.assertEqual(manifest["output_summary"]["audit_status"], "success")

    def test_packet_text_and_structure_truncation_retained(self):
        def handler(request):
            if request.url.path == "/robots.txt":
                return self.normal_handler(request)
            body = "<html><head><title>Long sample title</title></head><body><main><h1>Sample</h1>"
            body += "<p>" + "industrial production machining content " * 300 + "</p>"
            body += "".join(f"<h2>Section {i}</h2><p>Section content {i}</p>" for i in range(40))
            body += "</main></body></html>"
            return httpx.Response(200, text=body, headers={"content-type": "text/html"})
        self.assertEqual(self.run_audit(handler=handler, extractor=TrafilaturaPageExtractor(max_sections=1)), 0)
        manifest = self.read("manifest.json")
        self.assertTrue(manifest["truncation"]["packet_truncated"])
        self.assertTrue(manifest["truncation"]["packet_content_truncated_ids"])
        self.assertTrue(manifest["truncation"]["crawl_structured_truncated_urls"])
        self.assertTrue(self.read("packet.json")["pages"][0]["structured_content_truncated"])

    def test_live_permission_boolean_or_wrong_scope_rejected_without_network(self):
        path = Path(self.temp.name) / "permission.json"
        path.write_text('{"authorized": true}')
        with redirect_stdout(io.StringIO()), patch("foreign_trade_geo_agent.audit_cli.export_audit") as export:
            self.assertEqual(main(["live", "--url", URL, "--permission-record", str(path),
                                   "--output-dir", str(self.output)]), 1)
            export.assert_not_called()
        self.assertFalse(self.output.exists())

    def permission(self):
        now = datetime.now(timezone.utc)
        return {
            "operator": "offline test operator", "authority_basis": "Synthetic unit test only",
            "authorization_reference": "local-test-record-no-real-permission", "seed_url": URL,
            "exact_origin": {"scheme": "https", "host": "novacnc.example", "port": 443},
            "authorized_at": (now - timedelta(hours=1)).isoformat(),
            "expires_at": (now + timedelta(hours=1)).isoformat(),
            "purpose": "readonly_seo_audit", "terms_url": URL + "terms",
            "terms_reviewed_at": (now - timedelta(hours=1)).isoformat(),
            "retention_scope": "Local test only", "request_limits": asdict(AuditBudgets()),
        }

    def test_permission_preflight_hash_is_evidence_not_authentication(self):
        path = Path(self.temp.name) / "permission.json"
        path.write_text(json.dumps(self.permission()))
        evidence = check_live_permission(path, URL, AuditBudgets())
        self.assertEqual(evidence["record_sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertFalse(evidence["authority_authenticated_by_software"])
        # No live call occurs in this test.

    def test_future_live_composition_uses_permission_and_native_safety_offline(self):
        path = Path(self.temp.name) / "permission.json"
        path.write_text(json.dumps(self.permission()))
        # Exercise the real-transport branch with its transport replaced by a
        # MockTransport and DNS replaced by the offline resolver. No live crawl.
        with patch("foreign_trade_geo_agent.audit_runtime.SafeHtmlFetcher._new_pinned_transport",
                   side_effect=lambda *_: httpx.MockTransport(self.normal_handler)):
            result = asyncio.run(export_audit(URL, self.output, provenance={},
                                              permission_record=path, resolver=self.resolver))
        self.assertEqual(result, 0)
        evidence = self.read("manifest.json")["provenance"]["permission_preflight"]
        self.assertFalse(evidence["authority_authenticated_by_software"])
        self.assertEqual(evidence["record_sha256"], hashlib.sha256(path.read_bytes()).hexdigest())

    def test_permission_preflight_rejects_expired_scope_and_budget_mismatch(self):
        path = Path(self.temp.name) / "permission.json"
        for change in (
            {"seed_url": "https://other.example/"},
            {"expires_at": "2000-01-01T00:00:00+00:00"},
            {"purpose": "publish"},
            {"request_limits": asdict(AuditBudgets(max_pages=1))},
            {"authorized_at": "2020-01-01T00:00:00"},
        ):
            with self.subTest(change=change):
                record = self.permission() | change
                path.write_text(json.dumps(record))
                with self.assertRaises(ValueError):
                    check_live_permission(path, URL, AuditBudgets())

    def test_seed_credentials_query_and_expanded_budgets_rejected(self):
        for url in ("https://user:secret@example.com/", "https://example.com/?token=secret"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                self.run_audit(url=url)
        for value in ({"max_pages": 6}, {"max_depth": 2}, {"max_runtime": float("nan")}, {"max_concurrency": True}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                AuditBudgets(**value)

    def test_safe_cli_errors_do_not_echo_raw_exception_or_secret(self):
        with patch("foreign_trade_geo_agent.audit_cli.load_fixture", side_effect=ValueError("API_KEY=do-not-print")):
            output = io.StringIO()
            with redirect_stdout(output):
                result = main(["fixture", "--fixture-dir", str(FIXTURE), "--output-dir", str(self.output)])
            self.assertEqual(result, 1)
            self.assertNotIn("do-not-print", output.getvalue())


if __name__ == "__main__":
    unittest.main()
