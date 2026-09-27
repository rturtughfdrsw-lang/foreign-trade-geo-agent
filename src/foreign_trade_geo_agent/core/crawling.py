"""Provider-independent models for bounded exact-origin site crawls."""

from dataclasses import dataclass
from enum import Enum

from .extraction import (
    PageExtractionFailureKind,
    PageExtractionStatus,
    StructuredContentBlock,
)
from .fetching import FetchFailureKind, FetchTimeoutKind, UrlOrigin


class CrawlFailureKind(str, Enum):
    INVALID_SEED = "invalid_seed"
    ROBOTS_DISALLOWED = "robots_disallowed"
    ROBOTS_UNAVAILABLE = "robots_unavailable"
    ROBOTS_PARSE_FAILED = "robots_parse_failed"
    PAGE_FETCH_FAILED = "page_fetch_failed"
    EXTRACTION_FAILED = "extraction_failed"
    CANDIDATE_LIMIT_REACHED = "candidate_limit_reached"
    FRONTIER_LIMIT_REACHED = "frontier_limit_reached"
    REQUEST_BUDGET_EXCEEDED = "request_budget_exceeded"
    TOTAL_WIRE_BUDGET_EXCEEDED = "total_wire_budget_exceeded"
    TOTAL_DECODED_BUDGET_EXCEEDED = "total_decoded_budget_exceeded"
    TIME_LIMIT_EXCEEDED = "time_limit_exceeded"


class CrawlFailureStage(str, Enum):
    ROBOTS = "robots"
    FETCH = "fetch"
    EXTRACTION = "extraction"
    DISCOVERY = "discovery"
    WORKFLOW = "workflow"


class RobotsStatus(str, Enum):
    NOT_REQUESTED = "not_requested"
    ALLOWED = "allowed"
    NOT_FOUND = "not_found"
    DISALLOWED = "disallowed"
    FETCH_FAILED = "fetch_failed"
    PARSE_FAILED = "parse_failed"


class CrawlStopReason(str, Enum):
    COMPLETED = "completed"
    INVALID_SEED = "invalid_seed"
    ROBOTS_POLICY = "robots_policy"
    PAGE_LIMIT = "page_limit"
    FRONTIER_LIMIT = "frontier_limit"
    REQUEST_BUDGET = "request_budget"
    TOTAL_WIRE_BUDGET = "total_wire_budget"
    TOTAL_DECODED_BUDGET = "total_decoded_budget"
    TIME_LIMIT = "time_limit"


class LinkPriorityPolicy(str, Enum):
    DOCUMENT_ORDER = "document_order"
    B2B_CONTENT_V1 = "b2b_content_v1"


@dataclass(frozen=True, slots=True)
class CrawledPage:
    requested_url: str
    final_url: str
    depth: int
    http_status: int
    content_type: str
    title: str | None
    description: str | None
    canonical: str | None
    h1: tuple[str, ...]
    h2: tuple[str, ...]
    body_text: str | None
    published_date: str | None
    internal_links: tuple[str, ...]
    extraction_status: PageExtractionStatus
    extraction_failure_kind: PageExtractionFailureKind | None
    structured_content: tuple[StructuredContentBlock, ...] = ()
    structured_content_truncated: bool = False


@dataclass(frozen=True, slots=True)
class CrawlFailure:
    requested_url: str
    final_url: str | None
    depth: int | None
    stage: CrawlFailureStage
    kind: CrawlFailureKind
    http_status: int | None = None
    fetch_failure_kind: FetchFailureKind | None = None
    extraction_failure_kind: PageExtractionFailureKind | None = None
    error: str | None = None
    fetch_timeout_kind: FetchTimeoutKind | None = None


@dataclass(frozen=True, slots=True)
class CrawlResourceStats:
    fetch_operations: int
    content_fetches: int
    request_attempts: int
    redirects: int
    wire_bytes: int
    decoded_bytes: int


@dataclass(frozen=True, slots=True)
class SiteCrawlReport:
    seed_url: str
    exact_origin: UrlOrigin | None
    pages: tuple[CrawledPage, ...]
    failures: tuple[CrawlFailure, ...]
    resources: CrawlResourceStats
    robots_status: RobotsStatus
    crawl_delay: float | None
    stop_reason: CrawlStopReason
    budget_exhausted: bool
    link_priority_policy: LinkPriorityPolicy = LinkPriorityPolicy.DOCUMENT_ORDER
