import asyncio
from contextlib import redirect_stderr, redirect_stdout
import io
import os
import unittest
from unittest.mock import patch

from foreign_trade_geo_agent.core.crawling import (
    CrawledPage,
    CrawlFailure,
    CrawlFailureKind,
    CrawlFailureStage,
    CrawlResourceStats,
    CrawlStopReason,
    RobotsStatus,
    SiteCrawlReport,
)
from foreign_trade_geo_agent.core.extraction import (
    PageExtractionResult,
    PageExtractionStatus,
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
            ("--max-depth", "2"),
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
        self.assertLessEqual(max(map(len, rendered.splitlines())), 280)

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
