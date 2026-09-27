"""Run one explicitly configured bounded site-crawl verification."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence
import sys
import unicodedata

from foreign_trade_geo_agent.adapters.page_extractor import (
    TrafilaturaPageExtractor,
)
from foreign_trade_geo_agent.adapters.safe_http import SafeHtmlFetcher
from foreign_trade_geo_agent.core.crawling import (
    LinkPriorityPolicy,
    SiteCrawlReport,
)
from foreign_trade_geo_agent.core.ports import CrawlFetcher, PageExtractor
from foreign_trade_geo_agent.workflows.site_crawl import SiteCrawlWorkflow


_DEFAULT_MAX_PAGES = 5
_DEFAULT_MAX_DEPTH = 1
_DEFAULT_MAX_REQUEST_ATTEMPTS = 35
_MAX_VALIDATION_PAGES = 5
_MAX_VALIDATION_DEPTH = 2
_MAX_URL_CHARS = 512
_MAX_SUMMARY_CHARS = 240
_MAX_DIAGNOSTIC_CHARS = 240


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        safe_message = _safe_text(message, max_chars=_MAX_DIAGNOSTIC_CHARS)
        self.exit(2, f"{self.prog}: error: {safe_message}\n")


def _bounded_integer(name: str, minimum: int, maximum: int):
    def parse(value: str) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise argparse.ArgumentTypeError(
                f"{name} must be an integer from {minimum} to {maximum}."
            ) from exc
        if not minimum <= parsed <= maximum:
            raise argparse.ArgumentTypeError(
                f"{name} must be from {minimum} to {maximum}."
            )
        return parsed

    return parse


def _parser() -> argparse.ArgumentParser:
    parser = _SafeArgumentParser(
        prog="verify_site_crawl",
        description=__doc__,
    )
    parser.add_argument("--url", required=True, help="Authorized HTTP(S) seed URL.")
    parser.add_argument(
        "--max-pages",
        type=_bounded_integer("max-pages", 1, _MAX_VALIDATION_PAGES),
        default=_DEFAULT_MAX_PAGES,
        help="Maximum content pages (1-5; default: 5).",
    )
    parser.add_argument(
        "--max-depth",
        type=_bounded_integer("max-depth", 0, _MAX_VALIDATION_DEPTH),
        default=_DEFAULT_MAX_DEPTH,
        help="Maximum BFS depth (0-2; default: 1).",
    )
    return parser


async def _run_once(
    url: str,
    *,
    max_pages: int = _DEFAULT_MAX_PAGES,
    max_depth: int = _DEFAULT_MAX_DEPTH,
    fetcher: CrawlFetcher | None = None,
    extractor: PageExtractor | None = None,
    workflow: SiteCrawlWorkflow | None = None,
) -> SiteCrawlReport:
    """Run one crawl while keeping every safety budget owned by the workflow."""

    if not 1 <= max_pages <= _MAX_VALIDATION_PAGES:
        raise ValueError("max_pages must be from 1 to 5.")
    if not 0 <= max_depth <= _MAX_VALIDATION_DEPTH:
        raise ValueError("max_depth must be from 0 to 2.")
    if workflow is not None and (fetcher is not None or extractor is not None):
        raise ValueError("Provide either a workflow or crawl boundaries, not both.")

    active_workflow = workflow
    if active_workflow is None:
        active_workflow = SiteCrawlWorkflow(
            fetcher or SafeHtmlFetcher(),
            extractor or TrafilaturaPageExtractor(),
            max_pages=max_pages,
            max_depth=max_depth,
            max_concurrency=1,
            max_request_attempts=_DEFAULT_MAX_REQUEST_ATTEMPTS,
            link_priority_policy=LinkPriorityPolicy.B2B_CONTENT_V1,
        )
    return await active_workflow.run(url)


def _safe_text(value: object, *, max_chars: int) -> str:
    if value is None:
        return "(none)"
    raw = value if isinstance(value, str) else str(value)
    cleaned: list[str] = []
    for character in raw:
        if character.isspace():
            cleaned.append(" ")
        elif not unicodedata.category(character).startswith("C"):
            cleaned.append(character)
    rendered = " ".join("".join(cleaned).split()) or "(none)"
    if len(rendered) > max_chars:
        return f"{rendered[: max_chars - 3]}..."
    return rendered


def _heading_summary(headings: tuple[str, ...]) -> str:
    return _safe_text(" | ".join(headings), max_chars=_MAX_SUMMARY_CHARS)


def _print_report(
    report: SiteCrawlReport,
    *,
    max_pages: int = _DEFAULT_MAX_PAGES,
    max_request_attempts: int = _DEFAULT_MAX_REQUEST_ATTEMPTS,
) -> int:
    """Print bounded crawl metadata without emitting fetched page bodies."""

    print(f"Robots status: {report.robots_status.value}")
    print(
        "Crawl-delay: "
        + ("(none)" if report.crawl_delay is None else str(report.crawl_delay))
    )
    print(f"Link priority policy: {report.link_priority_policy.value}")
    print(f"Stop reason: {report.stop_reason.value}")
    print(
        "Stopped by configured guardrail: "
        f"{str(report.budget_exhausted).lower()}"
    )
    print(f"Successful pages: {len(report.pages)}")
    print(
        "Page fetch slots used: "
        f"{report.resources.content_fetches} / {max_pages}"
    )
    print(
        "HTTP request attempts: "
        f"{report.resources.request_attempts} / {max_request_attempts}"
    )
    print(f"Wire bytes: {report.resources.wire_bytes}")
    print(f"Decoded bytes: {report.resources.decoded_bytes}")

    for number, page in enumerate(report.pages, start=1):
        print(f"Page {number}:")
        print(f"  Final URL: {_safe_text(page.final_url, max_chars=_MAX_URL_CHARS)}")
        print(f"  BFS depth: {page.depth}")
        print(f"  HTTP status: {page.http_status}")
        print(f"  Title: {_safe_text(page.title, max_chars=_MAX_SUMMARY_CHARS)}")
        print(
            "  Description: "
            f"{_safe_text(page.description, max_chars=_MAX_SUMMARY_CHARS)}"
        )
        print(f"  H1: {_heading_summary(page.h1)}")
        print(f"  H2: {_heading_summary(page.h2)}")
        print(f"  Body characters: {len(page.body_text or '')}")
        print(f"  Extraction status: {page.extraction_status.value}")
        print(f"  Internal links: {len(page.internal_links)}")

    for number, failure in enumerate(report.failures, start=1):
        print(f"Failure {number}:")
        print(f"  Failure category: {failure.kind.value}")
        print(f"  Failure stage: {failure.stage.value}")
        controlled_url = failure.final_url or failure.requested_url
        print(f"  URL: {_safe_text(controlled_url, max_chars=_MAX_URL_CHARS)}")
        if failure.fetch_failure_kind is not None:
            print(f"  Fetch category: {failure.fetch_failure_kind.value}")
        if failure.fetch_timeout_kind is not None:
            print(f"  Timeout diagnostic: {failure.fetch_timeout_kind.value}")
        if failure.extraction_failure_kind is not None:
            print(f"  Extraction category: {failure.extraction_failure_kind.value}")

    return 0 if report.pages else 1


def main(
    argv: Sequence[str] | None = None,
    *,
    workflow: SiteCrawlWorkflow | None = None,
) -> int:
    args = _parser().parse_args(argv)
    try:
        report = asyncio.run(
            _run_once(
                args.url,
                max_pages=args.max_pages,
                max_depth=args.max_depth,
                workflow=workflow,
            )
        )
    except Exception:
        print("Site crawl verification failed safely; no diagnostic details were emitted.")
        return 1
    return _print_report(
        report,
        max_pages=args.max_pages,
        max_request_attempts=_DEFAULT_MAX_REQUEST_ATTEMPTS,
    )


if __name__ == "__main__":
    raise SystemExit(main())
