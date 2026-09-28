"""Shared safe rendering for crawl verification diagnostics."""

from foreign_trade_geo_agent.core.crawling import RobotsStatus, SiteCrawlReport
from foreign_trade_geo_agent.core.fetching import (
    FetchFailureKind,
    FetchHardDeadlinePhase,
    FetchTimeoutKind,
    FetchTimeoutOrigin,
)


def print_robots_fetch_diagnostics(report: SiteCrawlReport) -> None:
    """Print only allowlisted enum values for a failed robots fetch."""

    failure_kind = report.robots_fetch_failure_kind
    if (
        report.robots_status is not RobotsStatus.FETCH_FAILED
        or not isinstance(failure_kind, FetchFailureKind)
    ):
        return
    print(f"Robots fetch failure: {failure_kind.value}")

    timeout_kind = report.robots_fetch_timeout_kind
    if failure_kind is FetchFailureKind.TIMEOUT and isinstance(
        timeout_kind, FetchTimeoutKind
    ):
        print(f"Robots timeout kind: {timeout_kind.value}")

    timeout_origin = report.robots_fetch_timeout_origin
    if failure_kind is FetchFailureKind.TIMEOUT and isinstance(
        timeout_origin, FetchTimeoutOrigin
    ):
        print(f"Robots timeout origin: {timeout_origin.value}")

    hard_deadline_phase = report.robots_fetch_hard_deadline_phase
    if (
        failure_kind is FetchFailureKind.TIMEOUT
        and timeout_kind is FetchTimeoutKind.TIMEOUT
        and timeout_origin is FetchTimeoutOrigin.FETCHER_HARD_DEADLINE
        and isinstance(hard_deadline_phase, FetchHardDeadlinePhase)
    ):
        print(f"Robots timeout phase: {hard_deadline_phase.value}")
