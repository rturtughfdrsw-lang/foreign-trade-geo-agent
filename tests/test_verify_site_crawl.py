import asyncio
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
import io
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from foreign_trade_geo_agent.core.crawling import (
    CrawledPage,
    CrawlFailure,
    CrawlFailureKind,
    CrawlFailureStage,
    CrawlResourceStats,
    CrawlStopReason,
    LinkPriorityPolicy,
    RobotsStatus,
    SiteCrawlReport,
)
from foreign_trade_geo_agent.core.extraction import (
    PageExtractionResult,
    PageExtractionStatus,
    StructuredContentBlock,
    StructuredContentKind,
)
from foreign_trade_geo_agent.core.fetching import (
    FetchFailureKind,
    FetchStatus,
    FetchTimeoutKind,
    HtmlFetchResult,
    UrlOrigin,
)
from scripts.verify_site_crawl import _print_report, _run_once, main


ORIGIN = "https://example.com"


def _fetch_success(
    url: str,
    content: bytes,
    *,
    content_type: str = "text/html",
    attempts: int = 1,
) -> HtmlFetchResult:
    return HtmlFetchResult(
        requested_url=url,
        final_url=url,
        status=FetchStatus.SUCCESS,
        http_status=200,
        content_type=content_type,
        content=content,
        connected_ip="93.184.216.34",
        wire_bytes=len(content),
        decoded_bytes=len(content),
        request_attempts=attempts,
        redirect_chain=(url,),
        failure_kind=None,
        error=None,
    )


def _fetch_failure(
    url: str,
    kind: FetchFailureKind,
    *,
    attempts: int = 1,
    http_status: int | None = None,
) -> HtmlFetchResult:
    return HtmlFetchResult(
        requested_url=url,
        final_url=url,
        status=FetchStatus.FAILED,
        http_status=http_status,
        content_type=None,
        content=None,
        connected_ip=None,
        wire_bytes=0,
        decoded_bytes=0,
        request_attempts=attempts,
        redirect_chain=(url,),
        failure_kind=kind,
        error="Controlled fetch failure.",
    )


class _FakeFetcher:
    def __init__(
        self,
        pages: dict[str, HtmlFetchResult],
        *,
        robots: HtmlFetchResult | None = None,
    ) -> None:
        self.pages = pages
        self.robots = robots or _fetch_success(
            f"{ORIGIN}/robots.txt",
            b"User-agent: ForeignTradeGeoAgent\nAllow: /\n",
            content_type="text/plain",
        )
        self.fetch_calls: list[str] = []
        self.active = 0
        self.max_active = 0

    async def fetch_text(self, url: str, **_kwargs) -> HtmlFetchResult:
        return self.robots

    async def fetch(self, url: str, **_kwargs) -> HtmlFetchResult:
        self.fetch_calls.append(url)
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(0)
            if url not in self.pages:
                raise AssertionError(f"Unexpected page request: {url}")
            return self.pages[url]
        finally:
            self.active -= 1


class _FakeExtractor:
    def extract(self, html: bytes, final_url: str) -> PageExtractionResult:
        text = html.decode("utf-8", errors="replace")
        return PageExtractionResult(
            final_url=final_url,
            status=PageExtractionStatus.SUCCESS,
            title=f"Title {final_url}",
            description="Bounded description",
            canonical=None,
            h1=("Heading one",),
            h2=("Heading two",),
            body_text=text,
            published_date=None,
            failure_kind=None,
            error=None,
        )


def _empty_report(
    *,
    failures: tuple[CrawlFailure, ...] = (),
    robots_status: RobotsStatus = RobotsStatus.ALLOWED,
    stop_reason: CrawlStopReason = CrawlStopReason.COMPLETED,
    budget_exhausted: bool = False,
    link_priority_policy: LinkPriorityPolicy = LinkPriorityPolicy.DOCUMENT_ORDER,
) -> SiteCrawlReport:
    return SiteCrawlReport(
        seed_url=f"{ORIGIN}/",
        exact_origin=UrlOrigin("https", "example.com", 443),
        pages=(),
        failures=failures,
        resources=CrawlResourceStats(1, 0, 1, 0, 10, 10),
        robots_status=robots_status,
        crawl_delay=None,
        stop_reason=stop_reason,
        budget_exhausted=budget_exhausted,
        link_priority_policy=link_priority_policy,
    )


class _FakeWorkflow:
    def __init__(self, report: SiteCrawlReport | None = None, error: Exception | None = None):
        self.report = report or _empty_report()
        self.error = error
        self.urls: list[str] = []

    async def run(self, url: str) -> SiteCrawlReport:
        self.urls.append(url)
        if self.error is not None:
            raise self.error
        return self.report


class VerifySiteCrawlTests(unittest.TestCase):
    def test_script_path_help_starts_without_import_error(self) -> None:
        project_root = Path(__file__).resolve().parents[1]

        completed = subprocess.run(
            [
                sys.executable,
                str(project_root / "scripts" / "verify_site_crawl.py"),
                "--help",
            ],
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("verify_site_crawl", completed.stdout)

    def test_requires_url_before_starting_workflow(self) -> None:
        stderr = io.StringIO()
        with redirect_stderr(stderr), self.assertRaises(SystemExit) as raised:
            main([])

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("--url", stderr.getvalue())

    def test_rejects_page_and_depth_values_outside_validation_bounds(self) -> None:
        invalid = (
            ("--max-pages", "0"),
            ("--max-pages", "6"),
            ("--max-depth", "-1"),
            ("--max-depth", "3"),
        )
        for option, value in invalid:
            with self.subTest(option=option, value=value):
                stdout = io.StringIO()
                with (
                    redirect_stdout(stdout),
                    redirect_stderr(io.StringIO()),
                    self.assertRaises(SystemExit) as raised,
                ):
                    main(["--url", f"{ORIGIN}/", option, value])
                self.assertEqual(raised.exception.code, 2)
                self.assertEqual(stdout.getvalue(), "")

    def test_default_limits_are_five_pages_depth_one_and_serial(self) -> None:
        root_links = "".join(f'<a href="/p{index}">P</a>' for index in range(6))
        pages = {
            f"{ORIGIN}/": _fetch_success(f"{ORIGIN}/", root_links.encode()),
            **{
                f"{ORIGIN}/p{index}": _fetch_success(
                    f"{ORIGIN}/p{index}", b'<a href="/deep">Deep</a>'
                )
                for index in range(6)
            },
        }
        fetcher = _FakeFetcher(pages)

        report = asyncio.run(
            _run_once(f"{ORIGIN}/", fetcher=fetcher, extractor=_FakeExtractor())
        )

        self.assertEqual(len(report.pages), 5)
        self.assertEqual(len(fetcher.fetch_calls), 5)
        self.assertEqual(fetcher.max_active, 1)
        self.assertNotIn(f"{ORIGIN}/deep", fetcher.fetch_calls)
        self.assertEqual(report.stop_reason, CrawlStopReason.PAGE_LIMIT)
        self.assertEqual(
            report.link_priority_policy,
            LinkPriorityPolicy.B2B_CONTENT_V1,
        )

    def test_depth_two_is_allowed_for_explicit_product_detail_validation(self) -> None:
        fetcher = _FakeFetcher(
            {
                f"{ORIGIN}/": _fetch_success(
                    f"{ORIGIN}/", b'<a href="/product">Product</a>'
                ),
                f"{ORIGIN}/product": _fetch_success(
                    f"{ORIGIN}/product", b'<a href="/products/widget">Widget</a>'
                ),
                f"{ORIGIN}/products/widget": _fetch_success(
                    f"{ORIGIN}/products/widget", b"Widget"
                ),
            }
        )
        report = asyncio.run(
            _run_once(
                f"{ORIGIN}/",
                max_depth=2,
                fetcher=fetcher,
                extractor=_FakeExtractor(),
            )
        )

        self.assertEqual(
            fetcher.fetch_calls,
            [f"{ORIGIN}/", f"{ORIGIN}/product", f"{ORIGIN}/products/widget"],
        )
        self.assertEqual(report.link_priority_policy, LinkPriorityPolicy.B2B_CONTENT_V1)

    def test_smaller_user_limits_are_applied_without_changing_other_budgets(self) -> None:
        fetcher = _FakeFetcher(
            {
                f"{ORIGIN}/": _fetch_success(
                    f"{ORIGIN}/", b'<a href="/next">Next</a>'
                )
            }
        )

        report = asyncio.run(
            _run_once(
                f"{ORIGIN}/",
                max_pages=1,
                max_depth=0,
                fetcher=fetcher,
                extractor=_FakeExtractor(),
            )
        )

        self.assertEqual(len(report.pages), 1)
        self.assertEqual(fetcher.fetch_calls, [f"{ORIGIN}/"])

    def test_prints_bounded_page_summary_without_body_content(self) -> None:
        page = CrawledPage(
            requested_url=f"{ORIGIN}/",
            final_url=f"{ORIGIN}/page",
            depth=1,
            http_status=200,
            content_type="text/html",
            title="Safe title\x1b\n" + "T" * 400,
            description="D" * 500,
            canonical=None,
            h1=("H1 " + "A" * 300,),
            h2=("H2 " + "B" * 300,),
            body_text="DO_NOT_PRINT_BODY" * 100,
            published_date=None,
            internal_links=(f"{ORIGIN}/a", f"{ORIGIN}/b"),
            extraction_status=PageExtractionStatus.SUCCESS,
            extraction_failure_kind=None,
        )
        report = SiteCrawlReport(
            seed_url=f"{ORIGIN}/",
            exact_origin=UrlOrigin("https", "example.com", 443),
            pages=(page,),
            failures=(),
            resources=CrawlResourceStats(2, 1, 2, 0, 100, 200),
            robots_status=RobotsStatus.ALLOWED,
            crawl_delay=0.5,
            stop_reason=CrawlStopReason.COMPLETED,
            budget_exhausted=False,
        )
        output = io.StringIO()

        with redirect_stdout(output):
            exit_code = _print_report(report)

        rendered = output.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("Robots status: allowed", rendered)
        self.assertIn("Crawl-delay: 0.5", rendered)
        self.assertIn("Final URL: https://example.com/page", rendered)
        self.assertIn("Body characters: 1700", rendered)
        self.assertIn("Internal links: 2", rendered)
        self.assertNotIn("DO_NOT_PRINT_BODY", rendered)
        self.assertNotIn("\x1b", rendered)
        self.assertIn("Structured blocks: 0", rendered)
        self.assertIn("Structured content truncated: false", rendered)
        self.assertIn("Tables: 0", rendered)
        self.assertIn("Definition lists: 0", rendered)
        self.assertIn("Key-value blocks: 0", rendered)
        self.assertIn("Lists: 0", rendered)
        self.assertIn("Sections: 0", rendered)
        self.assertIn("Image alts: 0", rendered)
        self.assertLessEqual(max(map(len, rendered.splitlines())), 280)

    def test_legacy_crawled_page_constructor_defaults_to_empty_structure(self) -> None:
        page = CrawledPage(
            requested_url=f"{ORIGIN}/",
            final_url=f"{ORIGIN}/",
            depth=0,
            http_status=200,
            content_type="text/html",
            title=None,
            description=None,
            canonical=None,
            h1=(),
            h2=(),
            body_text="body",
            published_date=None,
            internal_links=(),
            extraction_status=PageExtractionStatus.SUCCESS,
            extraction_failure_kind=None,
        )

        self.assertEqual(page.structured_content, ())
        self.assertFalse(page.structured_content_truncated)

    def test_prints_bounded_structured_shapes_without_parameter_values(self) -> None:
        long_heading = "Specifications\x1b\n" + "H" * 200
        page = CrawledPage(
            requested_url=f"{ORIGIN}/",
            final_url=f"{ORIGIN}/product",
            depth=1,
            http_status=200,
            content_type="text/html",
            title="Product",
            description=None,
            canonical=None,
            h1=("Product",),
            h2=(),
            body_text="DO_NOT_PRINT_BODY",
            published_date=None,
            internal_links=(),
            extraction_status=PageExtractionStatus.SUCCESS,
            extraction_failure_kind=None,
            structured_content=(
                StructuredContentBlock(
                    kind=StructuredContentKind.TABLE,
                    heading=long_heading,
                    rows=(
                        ("Model", "Pressure", "Material"),
                        ("SECRET_MODEL", "SECRET_PRESSURE", "SECRET_MATERIAL"),
                    ),
                ),
                StructuredContentBlock(
                    kind=StructuredContentKind.DEFINITION_LIST,
                    heading="Technical data",
                    pairs=(("Inlet", "SECRET_INLET"),),
                ),
                StructuredContentBlock(
                    kind=StructuredContentKind.KEY_VALUE,
                    heading="Electrical",
                    pairs=(("Voltage", "SECRET_VOLTAGE"),),
                ),
                StructuredContentBlock(
                    kind=StructuredContentKind.LIST,
                    heading="Features",
                    items=("SECRET_FEATURE_ONE", "SECRET_FEATURE_TWO"),
                ),
                StructuredContentBlock(
                    kind=StructuredContentKind.SECTION,
                    heading="Performance",
                    text="SECRET_SECTION_BODY",
                ),
                StructuredContentBlock(
                    kind=StructuredContentKind.IMAGE_ALT,
                    heading="Media",
                    text="SECRET_IMAGE_ALT",
                ),
            ),
            structured_content_truncated=True,
        )
        report = SiteCrawlReport(
            seed_url=f"{ORIGIN}/",
            exact_origin=UrlOrigin("https", "example.com", 443),
            pages=(page,),
            failures=(),
            resources=CrawlResourceStats(2, 1, 2, 0, 100, 200),
            robots_status=RobotsStatus.ALLOWED,
            crawl_delay=None,
            stop_reason=CrawlStopReason.COMPLETED,
            budget_exhausted=False,
        )
        output = io.StringIO()

        with redirect_stdout(output):
            _print_report(report)

        rendered = output.getvalue()
        self.assertIn("Structured blocks: 6", rendered)
        self.assertIn("Structured content truncated: true", rendered)
        self.assertIn("Tables: 1", rendered)
        self.assertIn("Definition lists: 1", rendered)
        self.assertIn("Key-value blocks: 1", rendered)
        self.assertIn("Lists: 1", rendered)
        self.assertIn("Sections: 1", rendered)
        self.assertIn("Image alts: 1", rendered)
        self.assertIn("Table rows total: 2", rendered)
        self.assertIn("Table max cells: 3", rendered)
        self.assertIn("Definition/key-value pairs: 2", rendered)
        self.assertIn("List items: 2", rendered)
        self.assertIn(
            "TABLE heading=Specifications HHH",
            rendered,
        )
        self.assertIn("rows=2 max_cells=3", rendered)
        self.assertIn("DEFINITION_LIST heading=Technical data pairs=1", rendered)
        self.assertIn("KEY_VALUE heading=Electrical pairs=1", rendered)
        self.assertIn("LIST heading=Features items=2", rendered)
        self.assertIn("SECTION heading=Performance chars=19", rendered)
        self.assertIn("IMAGE_ALT heading=Media chars=16", rendered)
        self.assertNotIn("\x1b", rendered)
        self.assertNotIn("H" * 100, rendered)
        for secret in (
            "SECRET_MODEL",
            "SECRET_PRESSURE",
            "SECRET_MATERIAL",
            "SECRET_INLET",
            "SECRET_VOLTAGE",
            "SECRET_FEATURE_ONE",
            "SECRET_FEATURE_TWO",
            "SECRET_SECTION_BODY",
            "SECRET_IMAGE_ALT",
            "DO_NOT_PRINT_BODY",
        ):
            self.assertNotIn(secret, rendered)

    def test_prints_successes_separately_from_page_slots_and_request_limit(self) -> None:
        page = CrawledPage(
            requested_url=f"{ORIGIN}/",
            final_url=f"{ORIGIN}/",
            depth=0,
            http_status=200,
            content_type="text/html",
            title="Home",
            description=None,
            canonical=None,
            h1=(),
            h2=(),
            body_text="body",
            published_date=None,
            internal_links=(),
            extraction_status=PageExtractionStatus.SUCCESS,
            extraction_failure_kind=None,
        )
        failures = tuple(
            CrawlFailure(
                requested_url=f"{ORIGIN}/failed-{index}",
                final_url=f"{ORIGIN}/failed-{index}",
                depth=1,
                stage=CrawlFailureStage.FETCH,
                kind=CrawlFailureKind.PAGE_FETCH_FAILED,
                fetch_failure_kind=FetchFailureKind.TIMEOUT,
                error="Page fetch failed through the safe network boundary.",
            )
            for index in range(4)
        )
        report = SiteCrawlReport(
            seed_url=f"{ORIGIN}/",
            exact_origin=UrlOrigin("https", "example.com", 443),
            pages=(page,),
            failures=failures,
            resources=CrawlResourceStats(6, 5, 6, 0, 100, 200),
            robots_status=RobotsStatus.ALLOWED,
            crawl_delay=None,
            stop_reason=CrawlStopReason.PAGE_LIMIT,
            budget_exhausted=True,
        )
        output = io.StringIO()

        with redirect_stdout(output):
            _print_report(report)

        rendered = output.getvalue()
        self.assertIn("Successful pages: 1", rendered)
        self.assertIn("Page fetch slots used: 5 / 5", rendered)
        self.assertIn("HTTP request attempts: 6 / 35", rendered)
        self.assertIn("Stop reason: page_limit", rendered)
        self.assertIn("Stopped by configured guardrail: true", rendered)

    def test_prints_fixed_link_priority_policy_name(self) -> None:
        output = io.StringIO()

        with redirect_stdout(output):
            _print_report(
                _empty_report(
                    link_priority_policy=LinkPriorityPolicy.B2B_CONTENT_V1
                )
            )

        self.assertIn("Link priority policy: b2b_content_v1", output.getvalue())

    def test_failure_output_uses_fixed_categories_and_sanitized_bounded_text(self) -> None:
        failure = CrawlFailure(
            requested_url=f"{ORIGIN}/bad\x1b\npath",
            final_url=None,
            depth=0,
            stage=CrawlFailureStage.FETCH,
            kind=CrawlFailureKind.PAGE_FETCH_FAILED,
            fetch_failure_kind=FetchFailureKind.TIMEOUT,
            error="Timed\r\nout " + "X" * 500,
        )
        output = io.StringIO()

        with redirect_stdout(output):
            exit_code = _print_report(_empty_report(failures=(failure,)))

        rendered = output.getvalue()
        self.assertEqual(exit_code, 1)
        self.assertIn("Failure category: page_fetch_failed", rendered)
        self.assertIn("Fetch category: timeout", rendered)
        self.assertNotIn("\x1b", rendered)
        self.assertNotIn("\r", rendered)
        self.assertLessEqual(max(map(len, rendered.splitlines())), 550)

    def test_timeout_output_uses_only_fixed_diagnostic(self) -> None:
        failure = CrawlFailure(
            requested_url=f"{ORIGIN}/slow",
            final_url=None,
            depth=1,
            stage=CrawlFailureStage.FETCH,
            kind=CrawlFailureKind.PAGE_FETCH_FAILED,
            fetch_failure_kind=FetchFailureKind.TIMEOUT,
            fetch_timeout_kind=FetchTimeoutKind.REQUEST_TIMEOUT,
            error="UNTRUSTED_EXCEPTION_PAYLOAD\nTRACE_DETAIL",
        )
        output = io.StringIO()

        with redirect_stdout(output):
            _print_report(_empty_report(failures=(failure,)))

        rendered = output.getvalue()
        self.assertIn("Timeout diagnostic: request_timeout", rendered)
        self.assertNotIn("UNTRUSTED_EXCEPTION_PAYLOAD", rendered)
        self.assertNotIn("TRACE_DETAIL", rendered)

    def test_robots_timeout_output_uses_only_core_enum_diagnostics(self) -> None:
        failure = CrawlFailure(
            requested_url=f"{ORIGIN}/robots.txt",
            final_url=None,
            depth=None,
            stage=CrawlFailureStage.ROBOTS,
            kind=CrawlFailureKind.ROBOTS_UNAVAILABLE,
            fetch_failure_kind=FetchFailureKind.TIMEOUT,
            fetch_timeout_kind=FetchTimeoutKind.CONNECT_TIMEOUT,
            error=(
                "ConnectTimeout: TLS handshake failed at 203.0.113.42\n"
                "Traceback (most recent call last)"
            ),
        )
        report = replace(
            _empty_report(
                failures=(failure,),
                robots_status=RobotsStatus.FETCH_FAILED,
                stop_reason=CrawlStopReason.ROBOTS_POLICY,
            ),
            robots_fetch_failure_kind=FetchFailureKind.TIMEOUT,
            robots_fetch_timeout_kind=FetchTimeoutKind.CONNECT_TIMEOUT,
        )
        output = io.StringIO()

        with redirect_stdout(output):
            _print_report(report)

        rendered = output.getvalue()
        self.assertIn("Robots fetch failure: timeout", rendered)
        self.assertIn("Robots timeout kind: connect_timeout", rendered)
        for unsafe in ("ConnectTimeout", "TLS handshake", "203.0.113.42", "Traceback"):
            self.assertNotIn(unsafe, rendered)

    def test_robots_non_timeout_output_omits_timeout_kind(self) -> None:
        report = replace(
            _empty_report(
                robots_status=RobotsStatus.FETCH_FAILED,
                stop_reason=CrawlStopReason.ROBOTS_POLICY,
            ),
            robots_fetch_failure_kind=FetchFailureKind.HTTP_STATUS,
        )
        output = io.StringIO()

        with redirect_stdout(output):
            _print_report(report)

        rendered = output.getvalue()
        self.assertIn("Robots fetch failure: http_status", rendered)
        self.assertNotIn("Robots timeout kind:", rendered)

    def test_robots_disallow_stops_before_page_fetch(self) -> None:
        robots = _fetch_success(
            f"{ORIGIN}/robots.txt",
            b"User-agent: ForeignTradeGeoAgent\nDisallow: /\n",
            content_type="text/plain",
        )
        fetcher = _FakeFetcher({}, robots=robots)

        report = asyncio.run(
            _run_once(f"{ORIGIN}/", fetcher=fetcher, extractor=_FakeExtractor())
        )

        self.assertEqual(fetcher.fetch_calls, [])
        self.assertEqual(report.robots_status, RobotsStatus.DISALLOWED)
        self.assertEqual(report.stop_reason, CrawlStopReason.ROBOTS_POLICY)

    def test_request_budget_stop_does_not_retry_failed_page(self) -> None:
        fetcher = _FakeFetcher(
            {
                f"{ORIGIN}/": _fetch_failure(
                    f"{ORIGIN}/",
                    FetchFailureKind.REQUEST_BUDGET_EXCEEDED,
                    attempts=34,
                )
            }
        )

        report = asyncio.run(
            _run_once(f"{ORIGIN}/", fetcher=fetcher, extractor=_FakeExtractor())
        )

        self.assertEqual(fetcher.fetch_calls, [f"{ORIGIN}/"])
        self.assertEqual(report.stop_reason, CrawlStopReason.REQUEST_BUDGET)
        self.assertTrue(report.budget_exhausted)

    def test_valid_fake_run_needs_no_keys_and_has_no_network_side_effect(self) -> None:
        fetcher = _FakeFetcher(
            {f"{ORIGIN}/": _fetch_success(f"{ORIGIN}/", b"<main>Local</main>")}
        )
        with (
            patch.dict(os.environ, {}, clear=True),
            patch(
                "foreign_trade_geo_agent.adapters.safe_http.SystemHostResolver.resolve",
                side_effect=AssertionError("real DNS used"),
            ),
            patch(
                "foreign_trade_geo_agent.adapters.safe_http._PinnedNetworkBackend.connect_tcp",
                side_effect=AssertionError("network used"),
            ),
        ):
            report = asyncio.run(
                _run_once(f"{ORIGIN}/", fetcher=fetcher, extractor=_FakeExtractor())
            )

        self.assertEqual(len(report.pages), 1)

    def test_unexpected_exception_is_not_printed_or_retried(self) -> None:
        workflow = _FakeWorkflow(error=RuntimeError("SECRET_STACK_DETAIL"))
        output = io.StringIO()

        with redirect_stdout(output):
            exit_code = main(["--url", f"{ORIGIN}/"], workflow=workflow)

        self.assertEqual(exit_code, 1)
        self.assertEqual(workflow.urls, [f"{ORIGIN}/"])
        self.assertNotIn("SECRET_STACK_DETAIL", output.getvalue())
        self.assertIn("failed safely", output.getvalue().casefold())


if __name__ == "__main__":
    unittest.main()
