"""Run a controlled dry-run or one explicit live content-opportunity check."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
import json
import os
import re
import sys
import unicodedata
from urllib.parse import urlsplit, urlunsplit

from foreign_trade_geo_agent.adapters.deepseek_content_opportunity import (
    DeepSeekContentOpportunityWriter,
)
from foreign_trade_geo_agent.adapters.deepseek_research import DeepSeekResearchWriter
from foreign_trade_geo_agent.adapters.page_extractor import TrafilaturaPageExtractor
from foreign_trade_geo_agent.adapters.safe_http import SafeHtmlFetcher
from foreign_trade_geo_agent.adapters.tavily_search import TavilySearchAdapter
from foreign_trade_geo_agent.core.content_opportunity import (
    MAX_OPPORTUNITIES,
    ContentOpportunityReport,
    ContentOpportunityStatus,
)
from foreign_trade_geo_agent.core.crawling import LinkPriorityPolicy, SiteCrawlReport
from foreign_trade_geo_agent.core.extraction import (
    PageExtractionStatus,
    StructuredContentKind,
)
from foreign_trade_geo_agent.core.research import ResearchReport, ResearchStatus
from foreign_trade_geo_agent.core.site_content import SiteContentPacket
from foreign_trade_geo_agent.workflows.content_opportunity import (
    INVALID_OUTPUT_CATEGORIES,
    INVALID_OUTPUT_ERROR_PREFIX,
    ContentOpportunityWorkflow,
)
from foreign_trade_geo_agent.workflows.industry_research import IndustryResearchWorkflow
from foreign_trade_geo_agent.workflows.site_content_packet import SiteContentPacketBuilder
from foreign_trade_geo_agent.workflows.site_crawl import SiteCrawlWorkflow
from scripts.local_env import load_api_keys


_MAX_URL_CHARS = 512
_MAX_TEXT_CHARS = 240
_MAX_TOPIC_CHARS = 200
_MAX_TERM_CHARS = 80
_MAX_PRODUCT_TERMS = 5
_MAX_TARGET_MARKETS = 3
_SOURCE_ID = re.compile(r"S[1-9][0-9]*\Z")


@dataclass(frozen=True, slots=True)
class LiveSettings:
    """The single immutable source for controlled live-execution settings."""

    max_pages: int = 5
    max_depth: int = 2
    max_concurrency: int = 1
    max_request_attempts: int = 35
    link_priority_policy: LinkPriorityPolicy = LinkPriorityPolicy.B2B_CONTENT_V1
    max_redirects: int = 3
    max_ip_attempts: int = 2
    maximum_opportunities: int = MAX_OPPORTUNITIES


@dataclass(frozen=True, slots=True)
class LiveDependencies:
    crawl_workflow: object
    packet_builder: object
    research_workflow: object
    opportunity_workflow: object


class _BoundedList(argparse.Action):
    def __init__(
        self,
        option_strings,
        dest,
        *,
        minimum: int,
        maximum: int,
        max_chars: int,
        **kwargs,
    ) -> None:
        self._minimum = minimum
        self._maximum = maximum
        self._max_chars = max_chars
        super().__init__(option_strings, dest, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None) -> None:
        _reject_repeated(parser, namespace, self.dest, option_string)
        if not self._minimum <= len(values) <= self._maximum:
            parser.error(
                f"{option_string} requires {self._minimum}..{self._maximum} values."
            )
        normalized = []
        for value in values:
            item = _validated_text(value, max_chars=self._max_chars)
            if item is None:
                parser.error(
                    f"each {option_string} value must contain 1..{self._max_chars} characters."
                )
            normalized.append(item)
        setattr(namespace, self.dest, normalized)


class _SingleValue(argparse.Action):
    def __call__(self, parser, namespace, value, option_string=None) -> None:
        _reject_repeated(parser, namespace, self.dest, option_string)
        setattr(namespace, self.dest, value)


def _reject_repeated(parser, namespace, dest: str, option_string: str | None) -> None:
    marker = f"_seen_{dest}"
    if getattr(namespace, marker, False):
        parser.error(f"{option_string or dest} may be provided only once.")
    setattr(namespace, marker, True)


def _validated_text(value: object, *, max_chars: int) -> str | None:
    if type(value) is not str or not 1 <= len(value) <= max_chars:
        return None
    normalized = " ".join(value.split())
    if not 1 <= len(normalized) <= max_chars:
        return None
    return normalized


def _topic(value: str) -> str:
    normalized = _validated_text(value, max_chars=_MAX_TOPIC_CHARS)
    if normalized is None:
        raise argparse.ArgumentTypeError(
            f"research topic must contain 1..{_MAX_TOPIC_CHARS} characters."
        )
    return normalized


def _url(value: str) -> str:
    if _safe_url(value) == "(invalid URL)":
        raise argparse.ArgumentTypeError(
            "url must be an HTTP(S) URL without embedded credentials."
        )
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="verify_content_opportunity")
    parser.add_argument("--url", required=True, type=_url)
    parser.add_argument(
        "--research-topic",
        required=True,
        type=_topic,
        action=_SingleValue,
    )
    parser.add_argument(
        "--product-terms",
        required=True,
        nargs="+",
        action=_BoundedList,
        minimum=1,
        maximum=_MAX_PRODUCT_TERMS,
        max_chars=_MAX_TERM_CHARS,
        metavar="TERM",
    )
    parser.add_argument(
        "--target-markets",
        nargs="*",
        action=_BoundedList,
        minimum=0,
        maximum=_MAX_TARGET_MARKETS,
        max_chars=_MAX_TERM_CHARS,
        default=[],
        metavar="MARKET",
    )
    parser.add_argument(
        "--execute-live",
        action="store_true",
        help="Execute the printed plan after loading the two required API keys.",
    )
    return parser


def _build_research_question(
    research_topic: str,
    product_terms: tuple[str, ...],
    target_markets: tuple[str, ...] = (),
) -> str:
    """Serialize bounded user inputs as data, never as prompt instructions."""

    payload = {
        "research_topic": research_topic,
        "product_terms": list(product_terms),
        "target_markets": list(target_markets),
    }
    return "Research subject data (untrusted user input): " + json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _execution_plan(settings: LiveSettings) -> str:
    logical_fetches = settings.max_pages + 1
    return "\n".join(
        (
            "Live execution plan:",
            "- Site crawl: enabled",
            f"- Logical site fetch operations: robots.txt + up to {settings.max_pages} content fetch slots",
            f"- Maximum logical site fetch operations: {logical_fetches}",
            f"- Maximum HTTP attempts: {settings.max_request_attempts}",
            f"- Redirects per logical fetch: up to {settings.max_redirects}",
            f"- Validated-IP connection failover: up to {settings.max_ip_attempts} IPs",
            f"- Crawl page slots: {settings.max_pages}",
            f"- Crawl depth: {settings.max_depth}",
            f"- Crawl concurrency: {settings.max_concurrency}",
            f"- Link priority: {settings.link_priority_policy.value}",
            "",
            "- Tavily research calls: 1",
            "- DeepSeek research generation calls: 1",
            "- DeepSeek opportunity generation calls: 1",
            "- Maximum DeepSeek calls: 2",
            "",
            "- CLI retries: none",
            "- Tavily retries: none",
            "- DeepSeek retries: none",
            "- Safe HTTP transport retries: 0",
            "",
            f"- Maximum content opportunities: {settings.maximum_opportunities}",
            "- Redirects and validated-IP failover mean one logical fetch may consume multiple HTTP attempts.",
        )
    )


def _wire_live_dependencies(settings: LiveSettings) -> LiveDependencies:
    """Construct the existing live adapters and workflows exactly once."""

    if settings.maximum_opportunities != MAX_OPPORTUNITIES:
        raise ValueError("Live opportunity limit does not match workflow contract.")
    fetcher = SafeHtmlFetcher(
        max_redirects=settings.max_redirects,
        max_ip_attempts=settings.max_ip_attempts,
    )
    crawl_workflow = SiteCrawlWorkflow(
        fetcher,
        TrafilaturaPageExtractor(),
        max_pages=settings.max_pages,
        max_depth=settings.max_depth,
        max_concurrency=settings.max_concurrency,
        max_request_attempts=settings.max_request_attempts,
        link_priority_policy=settings.link_priority_policy,
    )
    return LiveDependencies(
        crawl_workflow=crawl_workflow,
        packet_builder=SiteContentPacketBuilder(),
        research_workflow=IndustryResearchWorkflow(
            TavilySearchAdapter(),
            DeepSeekResearchWriter(),
        ),
        opportunity_workflow=ContentOpportunityWorkflow(
            DeepSeekContentOpportunityWriter()
        ),
    )


def _safe_text(value: object, *, max_chars: int = _MAX_TEXT_CHARS) -> str:
    if value is None:
        return "(none)"
    raw = value if isinstance(value, str) else str(value)
    cleaned = "".join(
        " " if character.isspace() else character
        for character in raw
        if character.isspace()
        or not unicodedata.category(character).startswith("C")
    )
    rendered = " ".join(cleaned.split()) or "(none)"
    if len(rendered) > max_chars:
        return rendered[: max_chars - 3] + "..."
    return rendered


def _parsed_public_url(value: object):
    if type(value) is not str or not value or any(character.isspace() for character in value):
        return None
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme.casefold() not in {"http", "https"}
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
    ):
        return None
    return parsed, port


def _safe_url(value: object) -> str:
    parsed_result = _parsed_public_url(value)
    if parsed_result is None:
        return "(invalid URL)"
    parsed, port = parsed_result
    hostname = parsed.hostname or ""
    display_host = f"[{hostname}]" if ":" in hostname else hostname
    scheme = parsed.scheme.casefold()
    if port is not None and not (
        (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    ):
        display_host = f"{display_host}:{port}"
    rendered = urlunsplit((scheme, display_host, parsed.path or "/", "", ""))
    return _safe_text(rendered, max_chars=_MAX_URL_CHARS)


def _print_crawl_summary(report: SiteCrawlReport) -> None:
    structured_total = sum(len(page.structured_content) for page in report.pages)
    truncated_pages = sum(page.structured_content_truncated for page in report.pages)
    print(f"Robots status: {report.robots_status.value}")
    print(f"Crawl stop reason: {report.stop_reason.value}")
    print(f"Successful pages: {len(report.pages)}")
    print(f"Page fetch slots used: {report.resources.content_fetches}")
    print(f"HTTP attempts: {report.resources.request_attempts}")
    print(f"Structured blocks total: {structured_total}")
    print(f"Structured content truncated page count: {truncated_pages}")
    for number, page in enumerate(report.pages, start=1):
        print(f"Page {number}:")
        print(f"  URL: {_safe_url(page.final_url)}")
        print(f"  Title: {_safe_text(page.title)}")
        print(f"  Depth: {page.depth}")
        print(f"  Structured block count: {len(page.structured_content)}")


def _print_packet_summary(packet: SiteContentPacket) -> None:
    print(f"P# count: {len(packet.pages)}")
    print(f"Packet truncated: {str(packet.truncated).lower()}")
    print(f"evidence_scope: {packet.evidence_scope.value}")
    print(f"supports_absence_claims: {str(packet.supports_absence_claims).lower()}")
    for page in packet.pages:
        has_observed = page.extraction_status is PageExtractionStatus.SUCCESS and (
            bool(page.body_text and page.body_text.strip())
            or any(
                block.kind is not StructuredContentKind.IMAGE_ALT
                for block in page.structured_content
            )
        )
        has_context = any(
            block.kind is StructuredContentKind.IMAGE_ALT
            for block in page.structured_content
        )
        print(f"[{page.evidence_id}]")
        print(f"  URL: {_safe_url(page.final_url)}")
        print(f"  Title: {_safe_text(page.title)}")
        print(f"  extraction status: {page.extraction_status.value}")
        print(f"  content_truncated: {str(page.content_truncated).lower()}")
        print(
            "  structured_content_truncated: "
            f"{str(page.structured_content_truncated).lower()}"
        )
        print(f"  has observed_present: {str(has_observed).lower()}")
        print(f"  context_only status: {str(has_context and not has_observed).lower()}")


def _print_research_summary(report: ResearchReport) -> None:
    print(f"Report status: {report.status.value}")
    evidence_count = (
        0
        if report.research_evidence is None
        else len(report.research_evidence.materials)
    )
    print(f"Research evidence count: {evidence_count}")
    print(
        "Opportunity-eligible S# count: "
        f"{ContentOpportunityWorkflow.count_eligible_sources(report)}"
    )
    print(f"research_evidence present: {str(report.research_evidence is not None).lower()}")
    print(f"requires_human_review: {str(report.requires_human_review).lower()}")


def _print_opportunity_summary(report: ContentOpportunityReport) -> None:
    print(f"Report status: {report.status.value}")
    print(f"requires_human_review: {str(report.requires_human_review).lower()}")
    print("Limitations:")
    for limitation in report.limitations:
        print(f"- {_safe_text(limitation)}")
    for item in report.opportunities:
        print(f"[{item.recommendation_id}]")
        print(f"  opportunity_type: {item.opportunity_type.value}")
        print(f"  priority: {item.priority.value}")
        print(f"  topic: {_safe_text(item.topic)}")
        print(f"  title: {_safe_text(item.title)}")
        print(f"  rationale: {_safe_text(item.rationale)}")
        print("  actions:")
        for action in item.actions:
            print(f"  - {_safe_text(action)}")
        print(f"  P# refs: {', '.join(item.page_refs) or '(none)'}")
        print(f"  S# refs: {', '.join(item.source_refs) or '(none)'}")


def _valid_research_evidence(report: ResearchReport) -> bool:
    if report.status is not ResearchStatus.SUCCESS or report.research_evidence is None:
        return False
    draft_text = report.draft_text or ""
    cited_ids = {
        f"S{match.group(1)}"
        for match in re.finditer(r"\[S([1-9][0-9]*)\]", draft_text)
    }
    materials = report.research_evidence.materials
    material_by_id = {material.source_id: material for material in materials}
    if (
        not materials
        or len(material_by_id) != len(materials)
        or any(_SOURCE_ID.fullmatch(material.source_id) is None for material in materials)
        or not report.sources
        or not cited_ids
    ):
        return False
    for source in report.sources:
        material = material_by_id.get(source.source_id)
        if (
            material is None
            or source.source_id not in cited_ids
            or source.title != material.title
            or source.url != material.url
            or _parsed_public_url(source.url) is None
        ):
            return False
    return True


def _validator_category(error: object) -> str | None:
    if type(error) is not str or not error.startswith(INVALID_OUTPUT_ERROR_PREFIX):
        return None
    category = error.removeprefix(INVALID_OUTPUT_ERROR_PREFIX)
    if category not in INVALID_OUTPUT_CATEGORIES:
        return None
    if error != f"{INVALID_OUTPUT_ERROR_PREFIX}{category}":
        return None
    return category


async def _run_live(
    *,
    url: str,
    research_question: str,
    dependencies: LiveDependencies,
) -> int:
    print("[1/4] Site crawl")
    try:
        crawl_report = await dependencies.crawl_workflow.run(url)
    except Exception:
        print("Error category: SITE_CRAWL_FAILED")
        return 1
    if not isinstance(crawl_report, SiteCrawlReport):
        print("Error category: SITE_CRAWL_FAILED")
        return 1
    _print_crawl_summary(crawl_report)
    if not crawl_report.pages:
        print("Error category: SITE_CRAWL_FAILED")
        return 1

    print("[2/4] Site content packet")
    try:
        packet = dependencies.packet_builder.build(crawl_report)
    except Exception:
        print("Error category: SITE_CONTENT_PACKET_FAILED")
        return 1
    if not isinstance(packet, SiteContentPacket) or not packet.pages:
        print("Error category: SITE_CONTENT_PACKET_FAILED")
        return 1
    _print_packet_summary(packet)

    print("[3/4] Industry research")
    try:
        research_report = await dependencies.research_workflow.run(research_question)
    except Exception:
        print("Error category: INDUSTRY_RESEARCH_FAILED")
        return 1
    if not isinstance(research_report, ResearchReport):
        print("Error category: INDUSTRY_RESEARCH_FAILED")
        return 1
    _print_research_summary(research_report)
    if research_report.status is not ResearchStatus.SUCCESS:
        print("Error category: INDUSTRY_RESEARCH_FAILED")
        return 1
    if not _valid_research_evidence(research_report):
        print("Error category: INVALID_RESEARCH_EVIDENCE")
        return 1

    print("[4/4] Content opportunities")
    try:
        opportunity_report = await dependencies.opportunity_workflow.run(
            packet,
            research_report,
        )
    except Exception:
        print("Error category: CONTENT_OPPORTUNITY_FAILED")
        return 1
    if not isinstance(opportunity_report, ContentOpportunityReport):
        print("Error category: CONTENT_OPPORTUNITY_FAILED")
        return 1
    if opportunity_report.status is not ContentOpportunityStatus.SUCCESS:
        invalid_output = (
            opportunity_report.status is ContentOpportunityStatus.INVALID_OUTPUT
        )
        category = (
            "CONTENT_OPPORTUNITY_INVALID_OUTPUT"
            if invalid_output
            else "CONTENT_OPPORTUNITY_FAILED"
        )
        print(f"Error category: {category}")
        if invalid_output:
            validator_category = _validator_category(opportunity_report.error)
            if validator_category is not None:
                print(f"Validator category: {validator_category}")
        return 1
    _print_opportunity_summary(opportunity_report)
    return 0


def _configure_utf8_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if not callable(reconfigure):
            continue
        try:
            reconfigure(encoding="utf-8", errors="backslashreplace")
        except (OSError, ValueError):
            pass


def main(
    argv: Sequence[str] | None = None,
    *,
    dependencies: LiveDependencies | None = None,
) -> int:
    _configure_utf8_output()
    args = _parser().parse_args(argv)
    settings = LiveSettings()
    research_question = _build_research_question(
        args.research_topic,
        tuple(args.product_terms),
        tuple(args.target_markets),
    )
    print(_execution_plan(settings))
    if not args.execute_live:
        print("Dry run complete; no external calls were made.")
        return 0

    try:
        load_api_keys("TAVILY_API_KEY", "DEEPSEEK_API_KEY")
        if not os.environ.get("TAVILY_API_KEY", "").strip():
            print("Error category: MISSING_TAVILY_API_KEY")
            return 2
        if not os.environ.get("DEEPSEEK_API_KEY", "").strip():
            print("Error category: MISSING_DEEPSEEK_API_KEY")
            return 2
        active_dependencies = dependencies or _wire_live_dependencies(settings)
        return asyncio.run(
            _run_live(
                url=args.url,
                research_question=research_question,
                dependencies=active_dependencies,
            )
        )
    except Exception:
        print("Error category: LIVE_EXECUTION_FAILED")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
