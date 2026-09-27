"""Bounded exact-origin BFS crawl composed from existing safe adapters."""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass
import math
import time
from typing import Awaitable, Callable
from urllib import robotparser
from urllib.parse import urljoin, urlsplit

import httpx
from lxml import etree
from lxml import html as lxml_html

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
from foreign_trade_geo_agent.core.extraction import PageExtractionStatus
from foreign_trade_geo_agent.core.fetching import (
    FetchFailureKind,
    FetchStatus,
    HtmlFetchResult,
    UrlOrigin,
)
from foreign_trade_geo_agent.core.ports import CrawlFetcher, PageExtractor


_ROBOTS_USER_AGENT = "ForeignTradeGeoAgent"
_DEFAULT_TOTAL_WIRE_BYTES = 25 * 1024 * 1024
_DEFAULT_TOTAL_DECODED_BYTES = 50 * 1024 * 1024


class _TimeLimitReached(Exception):
    pass


@dataclass(slots=True)
class _MutableResources:
    fetch_operations: int = 0
    content_fetches: int = 0
    request_attempts: int = 0
    redirects: int = 0
    wire_bytes: int = 0
    decoded_bytes: int = 0

    def add(self, result: HtmlFetchResult, *, content: bool) -> None:
        self.fetch_operations += 1
        if content:
            self.content_fetches += 1
        self.request_attempts += result.request_attempts
        self.redirects += max(0, len(result.redirect_chain) - 1)
        self.wire_bytes += result.wire_bytes
        self.decoded_bytes += result.decoded_bytes

    def freeze(self) -> CrawlResourceStats:
        return CrawlResourceStats(
            fetch_operations=self.fetch_operations,
            content_fetches=self.content_fetches,
            request_attempts=self.request_attempts,
            redirects=self.redirects,
            wire_bytes=self.wire_bytes,
            decoded_bytes=self.decoded_bytes,
        )


class _RequestStartGate:
    def __init__(
        self,
        delay: float,
        *,
        last_started: float,
        deadline: float,
        clock: Callable[[], float],
        sleep: Callable[[float], Awaitable[None]],
    ) -> None:
        self._delay = delay
        self._last_started = last_started
        self._deadline = deadline
        self._clock = clock
        self._sleep = sleep
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            wait_seconds = max(0.0, self._last_started + self._delay - self._clock())
            if self._clock() + wait_seconds > self._deadline:
                raise _TimeLimitReached
            if wait_seconds:
                await self._sleep(wait_seconds)
            self._last_started = self._clock()


class SiteCrawlWorkflow:
    """Crawl a bounded exact-origin HTML graph without AI or hidden downloads."""

    def __init__(
        self,
        fetcher: CrawlFetcher,
        extractor: PageExtractor,
        *,
        max_pages: int = 25,
        max_depth: int = 2,
        max_concurrency: int = 2,
        max_request_attempts: int = 35,
        max_total_wire_bytes: int = _DEFAULT_TOTAL_WIRE_BYTES,
        max_total_decoded_bytes: int = _DEFAULT_TOTAL_DECODED_BYTES,
        max_candidate_links_per_page: int = 200,
        max_frontier: int = 250,
        max_runtime: float = 120.0,
        robots_user_agent: str = _ROBOTS_USER_AGENT,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if (
            max_pages <= 0
            or max_depth < 0
            or max_concurrency <= 0
            or max_request_attempts <= 0
            or max_total_wire_bytes <= 0
            or max_total_decoded_bytes <= 0
            or max_candidate_links_per_page <= 0
            or max_frontier <= 0
            or max_runtime <= 0
            or not robots_user_agent.strip()
        ):
            raise ValueError("Site crawl limits must be positive and bounded.")
        self._fetcher = fetcher
        self._extractor = extractor
        self._max_pages = max_pages
        self._max_depth = max_depth
        self._max_concurrency = max_concurrency
        self._max_request_attempts = max_request_attempts
        self._max_total_wire_bytes = max_total_wire_bytes
        self._max_total_decoded_bytes = max_total_decoded_bytes
        self._max_candidate_links = max_candidate_links_per_page
        self._max_frontier = max_frontier
        self._max_runtime = max_runtime
        self._robots_user_agent = robots_user_agent.strip()
        self._clock = clock
        self._sleep = sleep

    async def run(self, seed_url: str) -> SiteCrawlReport:
        resources = _MutableResources()
        pages: list[CrawledPage] = []
        failures: list[CrawlFailure] = []
        parsed_seed = self._normalize_url(seed_url)
        if parsed_seed is None:
            failures.append(
                CrawlFailure(
                    requested_url=seed_url if isinstance(seed_url, str) else "",
                    final_url=None,
                    depth=None,
                    stage=CrawlFailureStage.WORKFLOW,
                    kind=CrawlFailureKind.INVALID_SEED,
                    error="Seed URL is not a valid public HTTP(S) crawl target.",
                )
            )
            return self._report(
                seed_url,
                None,
                pages,
                failures,
                resources,
                RobotsStatus.NOT_REQUESTED,
                None,
                CrawlStopReason.INVALID_SEED,
                False,
            )

        normalized_seed, origin = parsed_seed
        start = self._clock()
        deadline = start + self._max_runtime
        robots_url = self._robots_url(normalized_seed)
        robots_started = self._clock()
        try:
            robots_result = await self._within_deadline(
                self._fetcher.fetch_text(
                    robots_url,
                    expected_origin=origin,
                    max_request_attempts=self._max_request_attempts,
                    max_total_wire_bytes=self._max_total_wire_bytes,
                    max_total_decoded_bytes=self._max_total_decoded_bytes,
                ),
                deadline,
            )
        except _TimeLimitReached:
            failures.append(self._time_failure(robots_url, None, CrawlFailureStage.ROBOTS))
            return self._report(
                normalized_seed,
                origin,
                pages,
                failures,
                resources,
                RobotsStatus.FETCH_FAILED,
                None,
                CrawlStopReason.TIME_LIMIT,
                True,
            )
        resources.add(robots_result, content=False)

        robots_byte_stop = self._byte_stop_reason(
            resources,
            robots_result,
            include_result_failure=True,
        )
        if robots_byte_stop is not None:
            failures.append(self._byte_budget_failure(robots_url, None, robots_byte_stop))
            return self._report(
                normalized_seed,
                origin,
                pages,
                failures,
                resources,
                RobotsStatus.FETCH_FAILED,
                None,
                robots_byte_stop,
                True,
            )

        robots_status, rules, crawl_delay = self._robots_policy(
            robots_result,
            robots_url,
            failures,
        )
        if robots_status not in {RobotsStatus.ALLOWED, RobotsStatus.NOT_FOUND}:
            return self._report(
                normalized_seed,
                origin,
                pages,
                failures,
                resources,
                robots_status,
                crawl_delay,
                CrawlStopReason.ROBOTS_POLICY,
                False,
            )
        if resources.request_attempts >= self._max_request_attempts:
            failures.append(self._budget_failure(normalized_seed, 0))
            return self._report(
                normalized_seed,
                origin,
                pages,
                failures,
                resources,
                robots_status,
                crawl_delay,
                CrawlStopReason.REQUEST_BUDGET,
                True,
            )
        if rules is not None and not rules.can_fetch(self._robots_user_agent, normalized_seed):
            failures.append(self._robots_disallowed(normalized_seed, 0))
            return self._report(
                normalized_seed,
                origin,
                pages,
                failures,
                resources,
                RobotsStatus.DISALLOWED,
                crawl_delay,
                CrawlStopReason.ROBOTS_POLICY,
                False,
            )

        gate = _RequestStartGate(
            crawl_delay or 0.0,
            last_started=robots_started,
            deadline=deadline,
            clock=self._clock,
            sleep=self._sleep,
        )
        frontier: deque[tuple[str, int]] = deque([(normalized_seed, 0)])
        seen = {normalized_seed}
        completed_urls: set[str] = set()
        stop_reason = CrawlStopReason.COMPLETED
        budget_exhausted = False

        while frontier:
            while frontier and frontier[0][0] in completed_urls:
                frontier.popleft()
            if not frontier:
                break
            if self._clock() >= deadline:
                stop_reason = CrawlStopReason.TIME_LIMIT
                budget_exhausted = True
                failures.append(self._time_failure(frontier[0][0], frontier[0][1], CrawlFailureStage.WORKFLOW))
                break
            remaining_attempts = self._max_request_attempts - resources.request_attempts
            if remaining_attempts <= 0:
                stop_reason = CrawlStopReason.REQUEST_BUDGET
                budget_exhausted = True
                failures.append(self._budget_failure(frontier[0][0], frontier[0][1]))
                break
            remaining_wire = self._max_total_wire_bytes - resources.wire_bytes
            if remaining_wire <= 0:
                stop_reason = CrawlStopReason.TOTAL_WIRE_BUDGET
                budget_exhausted = True
                failures.append(self._byte_budget_failure(frontier[0][0], frontier[0][1], stop_reason))
                break
            remaining_decoded = self._max_total_decoded_bytes - resources.decoded_bytes
            if remaining_decoded <= 0:
                stop_reason = CrawlStopReason.TOTAL_DECODED_BUDGET
                budget_exhausted = True
                failures.append(self._byte_budget_failure(frontier[0][0], frontier[0][1], stop_reason))
                break
            remaining_pages = self._max_pages - resources.content_fetches
            if remaining_pages <= 0:
                stop_reason = CrawlStopReason.PAGE_LIMIT
                budget_exhausted = True
                break

            depth = frontier[0][1]
            batch: list[tuple[str, int]] = []
            while (
                frontier
                and frontier[0][1] == depth
                and len(batch) < self._max_concurrency
                and len(batch) < remaining_pages
                and len(batch) < remaining_attempts
                and len(batch) < remaining_wire
                and len(batch) < remaining_decoded
            ):
                item = frontier.popleft()
                if item[0] not in completed_urls:
                    batch.append(item)
            if not batch:
                continue
            allocations = self._allocate_attempts(remaining_attempts, len(batch))
            wire_allocations = self._allocate_attempts(remaining_wire, len(batch))
            decoded_allocations = self._allocate_attempts(remaining_decoded, len(batch))
            redirect_policy = (
                None
                if rules is None
                else lambda target: rules.can_fetch(self._robots_user_agent, target)
            )
            tasks = [
                asyncio.create_task(
                    self._fetch_page(
                        url,
                        origin,
                        allocation,
                        gate,
                        deadline,
                        redirect_policy,
                        wire_allocation,
                        decoded_allocation,
                    )
                )
                for (url, _item_depth), allocation, wire_allocation, decoded_allocation in zip(
                    batch,
                    allocations,
                    wire_allocations,
                    decoded_allocations,
                    strict=True,
                )
            ]
            timeout = max(0.0, deadline - self._clock())
            done, pending = await asyncio.wait(tasks, timeout=timeout)
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

            frontier_limit_hit = False
            time_limit_hit = bool(pending)
            for (requested_url, item_depth), task in zip(batch, tasks, strict=True):
                if task not in done:
                    continue
                try:
                    result = task.result()
                except _TimeLimitReached:
                    time_limit_hit = True
                    failures.append(self._time_failure(requested_url, item_depth, CrawlFailureStage.FETCH))
                    continue
                resources.add(result, content=True)
                completed_urls.add(requested_url)
                normalized_final = self._normalize_url(result.final_url)
                if normalized_final is not None and normalized_final[1] == origin:
                    completed_urls.add(normalized_final[0])

                if result.status is FetchStatus.FAILED:
                    if (
                        result.failure_kind is FetchFailureKind.REQUEST_BUDGET_EXCEEDED
                        and resources.request_attempts >= self._max_request_attempts
                    ):
                        stop_reason = CrawlStopReason.REQUEST_BUDGET
                        budget_exhausted = True
                    byte_stop = self._byte_stop_reason(
                        resources,
                        result,
                        include_result_failure=True,
                    )
                    if byte_stop is not None:
                        stop_reason = byte_stop
                        budget_exhausted = True
                    failures.append(
                        CrawlFailure(
                            requested_url=requested_url,
                            final_url=result.final_url,
                            depth=item_depth,
                            stage=CrawlFailureStage.FETCH,
                            kind=CrawlFailureKind.PAGE_FETCH_FAILED,
                            http_status=result.http_status,
                            fetch_failure_kind=result.failure_kind,
                            error="Page fetch failed through the safe network boundary.",
                            fetch_timeout_kind=result.timeout_kind,
                        )
                    )
                    continue

                assert result.content is not None
                internal_links, candidate_limit_hit = self._discover_links(
                    result.content,
                    result.final_url,
                    origin,
                )
                if candidate_limit_hit:
                    failures.append(
                        CrawlFailure(
                            requested_url=requested_url,
                            final_url=result.final_url,
                            depth=item_depth,
                            stage=CrawlFailureStage.DISCOVERY,
                            kind=CrawlFailureKind.CANDIDATE_LIMIT_REACHED,
                            error="Per-page candidate link limit was reached.",
                        )
                    )

                extraction = await self._extract(result.content, result.final_url, deadline)
                if extraction is None:
                    time_limit_hit = True
                    failures.append(self._time_failure(requested_url, item_depth, CrawlFailureStage.EXTRACTION))
                    extraction_status = PageExtractionStatus.FAILED
                    extraction_failure_kind = None
                    title = description = canonical = body_text = published_date = None
                    h1: tuple[str, ...] = ()
                    h2: tuple[str, ...] = ()
                else:
                    extraction_status = extraction.status
                    extraction_failure_kind = extraction.failure_kind
                    title = extraction.title
                    description = extraction.description
                    canonical = extraction.canonical
                    body_text = extraction.body_text
                    published_date = extraction.published_date
                    h1 = extraction.h1
                    h2 = extraction.h2
                    if extraction.status is PageExtractionStatus.FAILED:
                        failures.append(
                            CrawlFailure(
                                requested_url=requested_url,
                                final_url=result.final_url,
                                depth=item_depth,
                                stage=CrawlFailureStage.EXTRACTION,
                                kind=CrawlFailureKind.EXTRACTION_FAILED,
                                http_status=result.http_status,
                                extraction_failure_kind=extraction.failure_kind,
                                error="Offline page extraction failed.",
                            )
                        )
                pages.append(
                    CrawledPage(
                        requested_url=requested_url,
                        final_url=result.final_url,
                        depth=item_depth,
                        http_status=result.http_status or 200,
                        content_type=result.content_type or "text/html",
                        title=title,
                        description=description,
                        canonical=canonical,
                        h1=h1,
                        h2=h2,
                        body_text=body_text,
                        published_date=published_date,
                        internal_links=internal_links,
                        extraction_status=extraction_status,
                        extraction_failure_kind=extraction_failure_kind,
                    )
                )

                if item_depth < self._max_depth:
                    for link in internal_links:
                        if link in seen:
                            continue
                        if rules is not None and not rules.can_fetch(self._robots_user_agent, link):
                            failures.append(self._robots_disallowed(link, item_depth + 1))
                            seen.add(link)
                            continue
                        if len(seen) >= self._max_frontier:
                            frontier_limit_hit = True
                            failures.append(
                                CrawlFailure(
                                    requested_url=link,
                                    final_url=None,
                                    depth=item_depth + 1,
                                    stage=CrawlFailureStage.DISCOVERY,
                                    kind=CrawlFailureKind.FRONTIER_LIMIT_REACHED,
                                    error="Overall crawl frontier limit was reached.",
                                )
                            )
                            break
                        seen.add(link)
                        frontier.append((link, item_depth + 1))
                if frontier_limit_hit:
                    break

            if time_limit_hit:
                stop_reason = CrawlStopReason.TIME_LIMIT
                budget_exhausted = True
                break
            if frontier_limit_hit:
                stop_reason = CrawlStopReason.FRONTIER_LIMIT
                budget_exhausted = True
                break
            if stop_reason is CrawlStopReason.REQUEST_BUDGET:
                break
            if stop_reason in {
                CrawlStopReason.TOTAL_WIRE_BUDGET,
                CrawlStopReason.TOTAL_DECODED_BUDGET,
            }:
                break
            byte_stop = self._byte_stop_reason(resources, None)
            if byte_stop is not None:
                stop_reason = byte_stop
                budget_exhausted = True
                break

        if (
            stop_reason is CrawlStopReason.COMPLETED
            and frontier
            and resources.content_fetches >= self._max_pages
        ):
            stop_reason = CrawlStopReason.PAGE_LIMIT
            budget_exhausted = True
        return self._report(
            normalized_seed,
            origin,
            pages,
            failures,
            resources,
            robots_status,
            crawl_delay,
            stop_reason,
            budget_exhausted,
        )

    async def _fetch_page(
        self,
        url: str,
        origin: UrlOrigin,
        attempt_budget: int,
        gate: _RequestStartGate,
        deadline: float,
        redirect_policy: Callable[[str], bool] | None,
        wire_budget: int,
        decoded_budget: int,
    ) -> HtmlFetchResult:
        await gate.wait()
        return await self._within_deadline(
            self._fetcher.fetch(
                url,
                expected_origin=origin,
                max_request_attempts=attempt_budget,
                max_total_wire_bytes=wire_budget,
                max_total_decoded_bytes=decoded_budget,
                redirect_policy=redirect_policy,
            ),
            deadline,
        )

    async def _extract(self, content: bytes, final_url: str, deadline: float):
        remaining = deadline - self._clock()
        if remaining <= 0:
            return None
        try:
            async with asyncio.timeout(remaining):
                return await asyncio.to_thread(self._extractor.extract, content, final_url)
        except TimeoutError:
            return None

    async def _within_deadline(self, operation, deadline: float):
        remaining = deadline - self._clock()
        if remaining <= 0:
            operation.close()
            raise _TimeLimitReached
        try:
            async with asyncio.timeout(remaining):
                return await operation
        except TimeoutError as exc:
            raise _TimeLimitReached from exc

    def _robots_policy(
        self,
        result: HtmlFetchResult,
        robots_url: str,
        failures: list[CrawlFailure],
    ) -> tuple[RobotsStatus, robotparser.RobotFileParser | None, float | None]:
        if result.status is FetchStatus.FAILED:
            if result.failure_kind is FetchFailureKind.HTTP_STATUS and result.http_status in {404, 410}:
                return RobotsStatus.NOT_FOUND, None, None
            status = RobotsStatus.DISALLOWED if result.http_status in {401, 403} else RobotsStatus.FETCH_FAILED
            failures.append(
                CrawlFailure(
                    requested_url=robots_url,
                    final_url=result.final_url,
                    depth=None,
                    stage=CrawlFailureStage.ROBOTS,
                    kind=(
                        CrawlFailureKind.ROBOTS_DISALLOWED
                        if status is RobotsStatus.DISALLOWED
                        else CrawlFailureKind.ROBOTS_UNAVAILABLE
                    ),
                    http_status=result.http_status,
                    fetch_failure_kind=result.failure_kind,
                    error="Robots policy could not be safely obtained.",
                    fetch_timeout_kind=result.timeout_kind,
                )
            )
            return status, None, None
        assert result.content is not None
        try:
            text = result.content.decode("utf-8-sig", errors="strict")
            if "\x00" in text or any(len(line) > 8_192 for line in text.splitlines()):
                raise ValueError
            rules = robotparser.RobotFileParser()
            rules.set_url(result.final_url)
            rules.parse(text.splitlines())
            crawl_delay = self._applicable_crawl_delay(text)
        except (UnicodeError, ValueError, TypeError):
            failures.append(
                CrawlFailure(
                    requested_url=robots_url,
                    final_url=result.final_url,
                    depth=None,
                    stage=CrawlFailureStage.ROBOTS,
                    kind=CrawlFailureKind.ROBOTS_PARSE_FAILED,
                    http_status=result.http_status,
                    error="Robots policy could not be parsed safely.",
                )
            )
            return RobotsStatus.PARSE_FAILED, None, None
        return RobotsStatus.ALLOWED, rules, crawl_delay

    def _applicable_crawl_delay(self, text: str) -> float | None:
        groups: list[tuple[tuple[str, ...], tuple[str, ...]]] = []
        agents: list[str] = []
        delays: list[str] = []
        has_directives = False

        def finish_group() -> None:
            nonlocal agents, delays, has_directives
            if agents:
                groups.append((tuple(agents), tuple(delays)))
            agents = []
            delays = []
            has_directives = False

        for raw_line in text.splitlines():
            line = raw_line.split("#", 1)[0].strip()
            if not line or ":" not in line:
                continue
            field, value = (part.strip() for part in line.split(":", 1))
            field = field.casefold()
            if field == "user-agent":
                if has_directives:
                    finish_group()
                if value:
                    agents.append(value.casefold())
                continue
            if not agents:
                continue
            has_directives = True
            if field == "crawl-delay":
                delays.append(value)
        finish_group()

        user_agent = self._robots_user_agent.casefold()
        exact = [delay for group_agents, delay in groups if user_agent in group_agents]
        selected = exact or [delay for group_agents, delay in groups if "*" in group_agents]
        values = [value for group_delays in selected for value in group_delays]
        if not values:
            return None
        parsed: list[float] = []
        for value in values:
            delay = float(value)
            if not math.isfinite(delay) or delay < 0:
                raise ValueError
            parsed.append(delay)
        return max(parsed)

    def _discover_links(
        self,
        content: bytes,
        base_url: str,
        origin: UrlOrigin,
    ) -> tuple[tuple[str, ...], bool]:
        parser = lxml_html.HTMLParser(recover=True, no_network=True, huge_tree=False)
        try:
            tree = lxml_html.fromstring(content, parser=parser)
        except (etree.ParserError, TypeError, ValueError, UnicodeError):
            return (), False
        links: list[str] = []
        candidate_count = 0
        limit_hit = False
        for element in tree.iter("a"):
            raw_href = element.get("href")
            if raw_href is None:
                continue
            candidate_count += 1
            if candidate_count > self._max_candidate_links:
                limit_hit = True
                break
            if not isinstance(raw_href, str) or not raw_href.strip():
                continue
            try:
                absolute = urljoin(base_url, raw_href.strip())
            except ValueError:
                continue
            parsed = self._normalize_url(absolute)
            if parsed is None:
                continue
            normalized, link_origin = parsed
            if link_origin != origin or urlsplit(normalized).query:
                continue
            if normalized not in links:
                links.append(normalized)
        return tuple(links), limit_hit

    @staticmethod
    def _normalize_url(value: object) -> tuple[str, UrlOrigin] | None:
        if type(value) is not str or not value or len(value) > 2_048:
            return None
        if any(character.isspace() for character in value) or "\\" in value:
            return None
        try:
            split = urlsplit(value)
            _ = split.port
            parsed = httpx.URL(value)
        except (ValueError, httpx.InvalidURL):
            return None
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.host
            or split.username is not None
            or split.password is not None
        ):
            return None
        try:
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            origin = UrlOrigin(parsed.scheme, parsed.raw_host.decode("ascii"), port)
        except (UnicodeDecodeError, ValueError):
            return None
        normalized = parsed.copy_with(host=origin.host, fragment=None)
        return str(normalized), origin

    @staticmethod
    def _robots_url(seed_url: str) -> str:
        return str(httpx.URL(seed_url).copy_with(path="/robots.txt", query=None, fragment=None))

    @staticmethod
    def _allocate_attempts(remaining: int, count: int) -> tuple[int, ...]:
        count = min(count, remaining)
        base, extra = divmod(remaining, count)
        return tuple(base + (1 if index < extra else 0) for index in range(count))

    @staticmethod
    def _robots_disallowed(url: str, depth: int) -> CrawlFailure:
        return CrawlFailure(
            requested_url=url,
            final_url=None,
            depth=depth,
            stage=CrawlFailureStage.ROBOTS,
            kind=CrawlFailureKind.ROBOTS_DISALLOWED,
            error="Robots policy disallows this URL.",
        )

    @staticmethod
    def _budget_failure(url: str, depth: int) -> CrawlFailure:
        return CrawlFailure(
            requested_url=url,
            final_url=None,
            depth=depth,
            stage=CrawlFailureStage.WORKFLOW,
            kind=CrawlFailureKind.REQUEST_BUDGET_EXCEEDED,
            error="HTTP request attempt budget was exhausted.",
        )

    @staticmethod
    def _byte_budget_failure(
        url: str,
        depth: int | None,
        reason: CrawlStopReason,
    ) -> CrawlFailure:
        wire = reason is CrawlStopReason.TOTAL_WIRE_BUDGET
        return CrawlFailure(
            requested_url=url,
            final_url=None,
            depth=depth,
            stage=CrawlFailureStage.WORKFLOW,
            kind=(
                CrawlFailureKind.TOTAL_WIRE_BUDGET_EXCEEDED
                if wire
                else CrawlFailureKind.TOTAL_DECODED_BUDGET_EXCEEDED
            ),
            error=(
                "Total wire byte budget was exhausted."
                if wire
                else "Total decoded byte budget was exhausted."
            ),
        )

    def _byte_stop_reason(
        self,
        resources: _MutableResources,
        result: HtmlFetchResult | None,
        *,
        include_result_failure: bool = False,
    ) -> CrawlStopReason | None:
        if resources.wire_bytes >= self._max_total_wire_bytes or (
            include_result_failure
            and result is not None
            and result.failure_kind is FetchFailureKind.TOTAL_WIRE_BUDGET_EXCEEDED
        ):
            return CrawlStopReason.TOTAL_WIRE_BUDGET
        if resources.decoded_bytes >= self._max_total_decoded_bytes or (
            include_result_failure
            and result is not None
            and result.failure_kind is FetchFailureKind.TOTAL_DECODED_BUDGET_EXCEEDED
        ):
            return CrawlStopReason.TOTAL_DECODED_BUDGET
        return None

    @staticmethod
    def _time_failure(url: str, depth: int | None, stage: CrawlFailureStage) -> CrawlFailure:
        return CrawlFailure(
            requested_url=url,
            final_url=None,
            depth=depth,
            stage=stage,
            kind=CrawlFailureKind.TIME_LIMIT_EXCEEDED,
            error="Overall crawl time limit was reached.",
        )

    @staticmethod
    def _report(
        seed_url: str,
        origin: UrlOrigin | None,
        pages: list[CrawledPage],
        failures: list[CrawlFailure],
        resources: _MutableResources,
        robots_status: RobotsStatus,
        crawl_delay: float | None,
        stop_reason: CrawlStopReason,
        budget_exhausted: bool,
    ) -> SiteCrawlReport:
        return SiteCrawlReport(
            seed_url=seed_url,
            exact_origin=origin,
            pages=tuple(pages),
            failures=tuple(failures),
            resources=resources.freeze(),
            robots_status=robots_status,
            crawl_delay=crawl_delay,
            stop_reason=stop_reason,
            budget_exhausted=budget_exhausted,
        )
