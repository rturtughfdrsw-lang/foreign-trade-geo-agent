"""Stable, process-local classification for unusable crawl reports."""

from __future__ import annotations

from dataclasses import dataclass

from foreign_trade_geo_agent.core.crawling import (
    CrawlStopReason,
    RobotsStatus,
    SiteCrawlReport,
)
from foreign_trade_geo_agent.core.extraction import PageExtractionStatus
from foreign_trade_geo_agent.core.fetching import FetchFailureKind


@dataclass(frozen=True, slots=True)
class PlanningFailure:
    """A bounded classification used while mapping a planning-stage failure."""

    failure_kind: str
    sanitized_error: str


_SAFETY_FAILURES = frozenset(
    {
        FetchFailureKind.INVALID_URL,
        FetchFailureKind.ORIGIN_REJECTED,
        FetchFailureKind.SAFETY_POLICY_REJECTED,
        FetchFailureKind.REDIRECT_POLICY_REJECTED,
    }
)
_RESOURCE_FAILURES = frozenset(
    {
        FetchFailureKind.RESOURCE_LIMIT_EXCEEDED,
        FetchFailureKind.REQUEST_BUDGET_EXCEEDED,
        FetchFailureKind.TOTAL_WIRE_BUDGET_EXCEEDED,
        FetchFailureKind.TOTAL_DECODED_BUDGET_EXCEEDED,
    }
)


def classify_crawl_failure(report: SiteCrawlReport) -> PlanningFailure:
    """Classify a crawl without copying provider, transport, or page errors."""

    if not isinstance(report, SiteCrawlReport):
        raise TypeError("Crawl failure classification requires a SiteCrawlReport.")
    usable = any(
        page.extraction_status is PageExtractionStatus.SUCCESS
        and isinstance(page.body_text, str)
        and bool(page.body_text.strip())
        for page in report.pages
    )
    if usable and report.stop_reason not in {
        CrawlStopReason.INVALID_SEED,
        CrawlStopReason.ROBOTS_POLICY,
    }:
        return PlanningFailure("usable_crawl", "")
    if report.stop_reason is CrawlStopReason.INVALID_SEED:
        return PlanningFailure(
            "invalid_seed",
            "The website URL could not be crawled safely.",
        )
    if report.stop_reason is CrawlStopReason.ROBOTS_POLICY:
        if report.robots_status is RobotsStatus.DISALLOWED:
            return PlanningFailure(
                "robots_disallowed",
                "The website robots policy does not allow this crawl.",
            )
        return PlanningFailure(
            "robots_unavailable",
            "The website robots policy could not be verified safely.",
        )

    fetch_failures = frozenset(
        failure.fetch_failure_kind
        for failure in report.failures
        if failure.fetch_failure_kind is not None
    )
    if fetch_failures & _SAFETY_FAILURES:
        return PlanningFailure(
            "network_safety_policy",
            "The site crawl was blocked by the network safety policy.",
        )
    if fetch_failures & _RESOURCE_FAILURES or report.stop_reason in {
        CrawlStopReason.PAGE_LIMIT,
        CrawlStopReason.FRONTIER_LIMIT,
        CrawlStopReason.REQUEST_BUDGET,
        CrawlStopReason.TOTAL_WIRE_BUDGET,
        CrawlStopReason.TOTAL_DECODED_BUDGET,
        CrawlStopReason.TIME_LIMIT,
    }:
        return PlanningFailure(
            "resource_limit",
            "The site crawl reached a bounded resource limit before usable evidence was found.",
        )
    if FetchFailureKind.TIMEOUT in fetch_failures:
        return PlanningFailure(
            "timeout",
            "The site crawl timed out before usable evidence was found.",
        )
    return PlanningFailure(
        "no_usable_pages",
        "Site crawl produced no usable evidence.",
    )
