"""Read-only Crawl -> Packet -> Audit composition; no planning providers or history."""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

import httpx

from foreign_trade_geo_agent.adapters.page_extractor import TrafilaturaPageExtractor
from foreign_trade_geo_agent.adapters.safe_http import SafeHtmlFetcher
from foreign_trade_geo_agent.core.audit import AuditStatus
from foreign_trade_geo_agent.core.crawling import LinkPriorityPolicy, RobotsStatus
from foreign_trade_geo_agent.core.site_content import SiteContentPacketLimits
from foreign_trade_geo_agent.reporting.audit_package import PackageExporter, safe_url
from foreign_trade_geo_agent.workflows.crawl_seo_audit import CrawlSeoAuditor
from foreign_trade_geo_agent.workflows.site_content_packet import SiteContentPacketBuilder
from foreign_trade_geo_agent.workflows.site_crawl import SiteCrawlWorkflow


@dataclass(frozen=True)
class AuditBudgets:
    max_pages: int = 5
    max_depth: int = 1
    max_concurrency: int = 1
    max_request_attempts: int = 35
    max_total_wire_bytes: int = 25 * 1024 * 1024
    max_total_decoded_bytes: int = 50 * 1024 * 1024
    max_candidate_links_per_page: int = 200
    max_frontier: int = 250
    max_runtime: float = 120.0

    def __post_init__(self) -> None:
        ceilings = (5, 1, 1, 35, 25 * 1024 * 1024, 50 * 1024 * 1024, 200, 250, 120.0)
        for (name, value), ceiling in zip(asdict(self).items(), ceilings, strict=True):
            minimum = 0 if name == "max_depth" else 0.000001
            if type(value) not in {int, float} or not minimum <= value <= ceiling:
                raise ValueError("Audit budget is outside the bounded profile.")
            if name != "max_runtime" and type(value) is not int:
                raise ValueError("Integer audit budget required.")


def _seed(url: str):
    parsed = SiteCrawlWorkflow._normalize_url(url)
    if parsed is None or httpx.URL(parsed[0]).query:
        raise ValueError("A credential-free HTTP(S) seed without query is required.")
    return parsed


def _bounded_read(path: Path, limit: int) -> bytes:
    with Path(path).open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Local input exceeds its resource budget.")
    return data


def check_live_permission(path: Path, seed_url: str, budgets: AuditBudgets, *,
                          now: datetime | None = None) -> dict[str, object]:
    """Validate an operator's evidence record, not authenticate their authority.

    A new site-specific human authorization is required before invoking live.
    The record documents that decision; it never overrides robots or SSRF rules.
    """
    raw = _bounded_read(path, 16 * 1024)
    record = json.loads(raw)
    required = {
        "operator", "authority_basis", "authorization_reference", "seed_url",
        "exact_origin", "authorized_at", "expires_at", "purpose", "terms_url",
        "terms_reviewed_at", "retention_scope", "request_limits",
    }
    if type(record) is not dict or set(record) != required:
        raise ValueError("A complete live permission record is required.")
    for key in required - {"exact_origin", "request_limits"}:
        if type(record[key]) is not str or not 1 <= len(record[key]) <= 2048:
            raise ValueError("Permission evidence must contain bounded text.")
    normalized, origin = _seed(seed_url)
    if record["seed_url"] != normalized or record["exact_origin"] != asdict(origin):
        raise ValueError("Permission scope does not match the requested site.")
    if record["purpose"] != "readonly_seo_audit":
        raise ValueError("Permission purpose is not read-only SEO audit.")
    terms, terms_origin = _seed(record["terms_url"])
    if terms_origin != origin:
        raise ValueError("Terms reference must belong to the authorized origin.")
    del terms
    dates = {}
    for key in ("authorized_at", "expires_at", "terms_reviewed_at"):
        dates[key] = datetime.fromisoformat(record[key])
        if dates[key].tzinfo is None:
            raise ValueError("Permission timestamps require a timezone.")
    current = now or datetime.now(timezone.utc)
    if not dates["authorized_at"] <= current < dates["expires_at"]:
        raise ValueError("Permission is not currently valid.")
    if dates["terms_reviewed_at"] > current:
        raise ValueError("Terms review is in the future.")
    limits = record["request_limits"]
    if type(limits) is not dict or set(limits) != set(asdict(budgets)):
        raise ValueError("Permission must enumerate the complete resource profile.")
    # Also reject unbounded permission profiles, bools and non-finite values.
    AuditBudgets(**limits)
    if any(value > limits[key] for key, value in asdict(budgets).items()):
        raise ValueError("Requested budget exceeds permission.")
    return {
        "record_sha256": hashlib.sha256(raw).hexdigest(),
        "scope": "operator_declared_exact_origin_readonly",
        "authority_authenticated_by_software": False,
        "evidence_review": "Operator must verify the referenced grant and content retention terms before live invocation.",
    }


class _FixtureResolver:
    """A fixed public test address; never calls DNS or creates a socket."""

    async def resolve(self, host, port):
        return ("93.184.216.34",)


def load_fixture(directory: Path, url: str | None = None):
    """Map local HTML files to paths; no domain-specific crawler or audit logic."""
    root = Path(directory).resolve(strict=True)
    if not (root / "manifest.json").resolve(strict=True).is_relative_to(root):
        raise ValueError("Fixture manifest escapes the fixture directory.")
    metadata = _bounded_read(root / "manifest.json", 16 * 1024)
    descriptor = json.loads(metadata)
    seed_url, origin = _seed(url or descriptor["display_url"])
    routes = {}
    inputs = {"manifest.json": hashlib.sha256(metadata).hexdigest()}
    total = len(metadata)
    files = [root / "robots.txt"]
    for candidate in root.rglob("*.html"):
        files.append(candidate)
        if len(files) > 250:
            raise ValueError("Too many fixture files.")
    for file in files:
        if not file.resolve(strict=True).is_relative_to(root):
            raise ValueError("Fixture file escapes the fixture directory.")
        data = _bounded_read(file, 4 * 1024 * 1024)
        total += len(data)
        if total > 25 * 1024 * 1024:
            raise ValueError("Fixture inputs exceed the resource budget.")
        relative = file.relative_to(root).as_posix()
        inputs[relative] = hashlib.sha256(data).hexdigest()
        route = "/" if relative == "index.html" else "/" + relative
        routes[route] = (data, "text/plain" if relative == "robots.txt" else "text/html")

    def handler(request):
        # SafeHtmlFetcher still enforces exact-origin, DNS and redirect policy.
        if request.method != "GET":
            raise AssertionError("Read-only fixture supports GET only.")
        data, media = routes.get(request.url.path, (b"Not in fixture", "text/plain"))
        return httpx.Response(200 if request.url.path in routes else 404,
                              content=data, headers={"content-type": media})

    return seed_url, {
        "kind": "synthetic_fixture", "network": "offline_mock_transport",
        "fixture_input_sha256": inputs,
        "fixture_input_bytes": total,
        "source_authenticity": "Synthetic local fixture; not a real website acceptance.",
    }, _FixtureResolver(), lambda *_: httpx.MockTransport(handler)


class _ObservedTransport(httpx.AsyncBaseTransport):
    def __init__(self, inner, events):
        self.inner, self.events = inner, events

    async def handle_async_request(self, request):
        event = {"url": safe_url(str(request.url)), "method": request.method,
                 "started_at": datetime.now(timezone.utc).isoformat(),
                 "http_status": None, "response_received": False}
        self.events.append(event)
        response = await self.inner.handle_async_request(request)
        event.update(http_status=response.status_code, response_received=True)
        return response

    async def aclose(self):
        await self.inner.aclose()


class _ObservedFetcher:
    """Record native port outcomes and byte hashes, never raw HTTP payloads."""

    def __init__(self, inner, records):
        self.inner, self.records = inner, records

    async def _call(self, method, url, kwargs):
        record = {"kind": method, "requested_url": safe_url(url),
                  "started_at": datetime.now(timezone.utc).isoformat(), "completed": False}
        self.records.append(record)
        result = await getattr(self.inner, method)(url, **kwargs)
        record.update(
            completed=True, final_url=safe_url(result.final_url),
            status=result.status.value, http_status=result.http_status,
            failure_kind=result.failure_kind.value if result.failure_kind else None,
            # Chain may include a rejected target; requests.json records actual attempts.
            redirect_candidates=[safe_url(candidate) for candidate in result.redirect_chain],
            wire_bytes=result.wire_bytes, decoded_bytes=result.decoded_bytes,
            request_attempts=result.request_attempts,
            content_sha256=hashlib.sha256(result.content).hexdigest() if result.content is not None else None,
            finished_at=datetime.now(timezone.utc).isoformat(),
        )
        return result

    async def fetch(self, url, **kwargs):
        return await self._call("fetch", url, kwargs)

    async def fetch_text(self, url, **kwargs):
        return await self._call("fetch_text", url, kwargs)


async def export_audit(seed_url: str, output_directory: Path, *, provenance: dict,
                       budgets: AuditBudgets | None = None,
                       resolver=None, transport_factory=None, extractor=None,
                       permission_record: Path | None = None) -> int:
    """Compose only the native crawl, packet and audit; export failed runs too.

    Injection is for offline tests. Real transport always requires permission
    evidence here as well as at the CLI boundary, before constructing I/O.
    """
    budgets = budgets or AuditBudgets()
    seed_url, origin = _seed(seed_url)
    if transport_factory is None:
        if permission_record is None:
            raise ValueError("Live transport requires a site-specific permission record.")
        permission = check_live_permission(permission_record, seed_url, budgets)
        provenance = {"kind": "public_web_observation", "network": "live_safe_http",
                      "permission_preflight": permission,
                      "source_authenticity": "Public observation only; customer facts unconfirmed."}
    exporter = PackageExporter(output_directory)  # Exclusive reservation before I/O.
    start = time.monotonic()
    started = datetime.now(timezone.utc).isoformat()
    events = []
    fetches = []
    factory = transport_factory or SafeHtmlFetcher._new_pinned_transport
    fetcher = _ObservedFetcher(SafeHtmlFetcher(
        resolver=resolver,
        _transport_factory=lambda *args: _ObservedTransport(factory(*args), events),
    ), fetches)
    workflow = SiteCrawlWorkflow(
        fetcher, extractor or TrafilaturaPageExtractor(),
        **asdict(budgets), link_priority_policy=LinkPriorityPolicy.B2B_CONTENT_V1,
    )
    crawl = await workflow.run(seed_url)
    packet = SiteContentPacketBuilder().build(crawl)
    audit = CrawlSeoAuditor().audit_crawl(crawl)
    if crawl.budget_exhausted:
        outcome = "budget_exhausted"
    elif crawl.robots_status in {RobotsStatus.DISALLOWED, RobotsStatus.FETCH_FAILED,
                                RobotsStatus.PARSE_FAILED, RobotsStatus.NOT_REQUESTED}:
        outcome = "blocked_robots_or_safety"
    elif audit.status is not AuditStatus.SUCCESS:
        outcome = "failed_no_usable_pages"
    elif crawl.failures:
        outcome = "partial"
    else:
        outcome = "sample_complete"
    # Any exception or cancellation preserves INCOMPLETE.json automatically.
    exporter.finish(
        crawl=crawl, packet=packet, audit=audit, requests=events, fetches=fetches,
        inputs={"seed_url": seed_url, "exact_origin": asdict(origin),
                "crawl_budgets": asdict(budgets),
                "packet_limits": asdict(SiteContentPacketLimits()),
                "provenance": provenance},
        outcome=outcome, started_at=started, duration_seconds=time.monotonic() - start,
    )
    return 0 if outcome == "sample_complete" else 3 if audit.status is AuditStatus.SUCCESS else 1
