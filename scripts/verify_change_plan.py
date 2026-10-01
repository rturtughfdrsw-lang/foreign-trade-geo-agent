"""Run a synthetic dry-run or one controlled live Change Plan check."""

from __future__ import annotations

import sys
from pathlib import Path

# Make the project root importable when this file is executed directly, so the
# shared ``scripts.local_env`` helper and the installed package both resolve.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import argparse
import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, replace
import os
import unicodedata

import httpx

from foreign_trade_geo_agent.adapters.deepseek_change_plan import (
    DeepSeekChangePlanWriter,
)
from foreign_trade_geo_agent.core.change_plan import (
    ChangePlanGenerationStatus,
    ChangePlanInput,
    ChangePlanStatus,
    build_change_plan_prompt,
    validate_change_plan_input,
)
from foreign_trade_geo_agent.core.content_opportunity import (
    CONTENT_OPPORTUNITY_LIMITATIONS,
    ContentOpportunityActionCode,
    ContentOpportunityPage,
    ContentOpportunityPriority,
    ContentOpportunityReport,
    ContentOpportunitySource,
    ContentOpportunitySourceMaterial,
    ContentOpportunitySpecification,
    ContentOpportunityStatus,
    ContentOpportunityType,
    finalize_content_opportunity,
)
from foreign_trade_geo_agent.core.crawling import CrawlStopReason
from foreign_trade_geo_agent.core.extraction import PageExtractionStatus
from foreign_trade_geo_agent.core.research import ResearchEvidenceClassification
from foreign_trade_geo_agent.core.site_content import SiteContentEvidence, SiteContentPacket
from foreign_trade_geo_agent.workflows.change_plan import ChangePlanWorkflow
from scripts.local_env import load_api_keys


# Capture the production system prompt once at import time. This is the only public
# prompt material the smoke script needs for metrics, and it never requires a key,
# a writer instance, or any network access.
_SYSTEM_PROMPT = DeepSeekChangePlanWriter.build_system_prompt()


_SOURCE_CLASSIFICATIONS = (
    ResearchEvidenceClassification.EXTERNAL_RESEARCH_CONTEXT,
    ResearchEvidenceClassification.UNVERIFIED_SEARCH_RESULT,
)


@dataclass(frozen=True, slots=True)
class SyntheticFixture:
    """Bounded offline input for the smoke check."""

    site_content: SiteContentPacket
    opportunities: ContentOpportunityReport


@dataclass(frozen=True, slots=True)
class SmokeMetrics:
    """Measured prompt budgets that production public APIs expose."""

    system_chars: int
    system_bytes: int
    user_chars: int
    user_bytes: int
    envelope_chars: int | None = None
    envelope_bytes: int | None = None


@dataclass(frozen=True, slots=True)
class SmokeContext:
    """Validated prompt plus its budget measurements."""

    metrics: SmokeMetrics


class SingleRequestTransport(httpx.AsyncBaseTransport):
    """Count one request, pass it through untouched, and refuse a second."""

    def __init__(self, transport: httpx.AsyncBaseTransport) -> None:
        self._transport = transport
        self.request_count = 0

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if self.request_count > 0:
            raise httpx.TransportError(
                "Single-request transport refuses a second provider request."
            )
        self.request_count += 1
        return await self._transport.handle_async_request(request)


class ObservingChangePlanWriter:
    """Pass a generation through unchanged while recording safe public metrics."""

    def __init__(self, writer) -> None:
        self._writer = writer
        self.call_count = 0
        self.last_generation = None

    async def write_change_plan(self, prompt):
        self.call_count += 1
        generation = await self._writer.write_change_plan(prompt)
        self.last_generation = generation
        return generation

    @property
    def raw_text_chars(self) -> int | None:
        text = self.last_generation.text if self.last_generation is not None else None
        return None if text is None else len(text)

    @property
    def raw_text_bytes(self) -> int | None:
        text = self.last_generation.text if self.last_generation is not None else None
        return None if text is None else len(text.encode("utf-8"))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="verify_change_plan")
    parser.add_argument(
        "--execute-live",
        action="store_true",
        help=(
            "Execute exactly one controlled DeepSeek request through the production "
            "writer after loading DEEPSEEK_API_KEY."
        ),
    )
    return parser


def _build_page() -> SiteContentEvidence:
    return SiteContentEvidence(
        evidence_id="P1",
        final_url="https://example.com/p1",
        title="Industrial Pumps",
        description="Pump application guide",
        h1=("Industrial Pumps",),
        h2=("Technical Specifications", "Maintenance"),
        body_text=(
            "Chemical compatibility, material selection, port size, application, "
            "and AODD pump maintenance are observed topics."
        ),
        structured_content=(),
        extraction_status=PageExtractionStatus.SUCCESS,
        extraction_failure_kind=None,
        structured_content_truncated=False,
        content_truncated=False,
    )


def _build_packet(page: SiteContentEvidence) -> SiteContentPacket:
    return SiteContentPacket(
        pages=(page,),
        source_page_count=1,
        crawl_stop_reason=CrawlStopReason.COMPLETED,
        crawl_budget_exhausted=False,
        truncated=False,
    )


def _build_opportunity(
    recommendation_id: str,
    *,
    action_codes: tuple[ContentOpportunityActionCode, ...],
    page_refs: tuple[str, ...],
    source_refs: tuple[str, ...],
):
    if ContentOpportunityActionCode.REORGANIZE_PAGE_SECTIONS in action_codes:
        opportunity_type = ContentOpportunityType.REORGANIZE_OBSERVED_CONTENT
    elif any(
        action in action_codes
        for action in (
            ContentOpportunityActionCode.CREATE_SUPPORTING_RESOURCE,
            ContentOpportunityActionCode.ADD_BUYER_GUIDANCE,
            ContentOpportunityActionCode.ADD_TECHNICAL_DOCUMENTATION,
        )
    ):
        opportunity_type = ContentOpportunityType.NEW_SUPPORTING_CONTENT
    else:
        opportunity_type = ContentOpportunityType.EXPAND_OBSERVED_CONTENT
    number = int(recommendation_id[1:])
    finalized = finalize_content_opportunity(
        number,
        ContentOpportunitySpecification(
            opportunity_type=opportunity_type,
            priority=ContentOpportunityPriority.HIGH,
            topic="chemical compatibility",
            action_codes=action_codes,
            page_refs=page_refs,
            source_refs=source_refs,
        ),
    )
    return replace(finalized, recommendation_id=recommendation_id)


def _build_report(items) -> ContentOpportunityReport:
    source_ids = tuple(dict.fromkeys(ref for item in items for ref in item.source_refs))
    source_text = (
        "Technical Specifications and AODD pump maintenance are documented for "
        "chemical compatibility, material selection, port size, and application."
    )
    materials = tuple(
        ContentOpportunitySourceMaterial(
            source_id=source_id,
            title="Chemical compatibility pump guide",
            content=" ".join(source_text.split()),
            content_truncated=False,
        )
        for source_id in source_ids
    )
    sources = tuple(
        ContentOpportunitySource(
            source_id=source_id,
            title="Chemical compatibility pump guide",
            url=f"https://source.example/{source_id.casefold()}",
            classifications=_SOURCE_CLASSIFICATIONS,
        )
        for source_id in source_ids
    )
    page_ids = tuple(dict.fromkeys(ref for item in items for ref in item.page_refs))
    return ContentOpportunityReport(
        status=ContentOpportunityStatus.SUCCESS,
        opportunities=items,
        pages=tuple(
            ContentOpportunityPage(ref, f"https://example.com/{ref.casefold()}", "Pump")
            for ref in page_ids
        ),
        sources=sources,
        limitations=CONTENT_OPPORTUNITY_LIMITATIONS,
        error=None,
        source_materials=materials,
    )


def build_synthetic_fixture() -> SyntheticFixture:
    """Build a stable, contract-valid R/P/S fixture without any external access."""

    packet = _build_packet(_build_page())
    opportunities = (
        _build_opportunity(
            "R1",
            action_codes=(ContentOpportunityActionCode.EXPAND_PAGE_SECTION,),
            page_refs=("P1",),
            source_refs=("S1",),
        ),
        _build_opportunity(
            "R2",
            action_codes=(ContentOpportunityActionCode.ADD_TECHNICAL_DOCUMENTATION,),
            page_refs=("P1",),
            source_refs=("S2",),
        ),
    )
    return SyntheticFixture(
        site_content=packet,
        opportunities=_build_report(opportunities),
    )


def prepare_smoke_context(fixture: SyntheticFixture) -> SmokeContext:
    """Validate the fixture and measure the prompt budgets production exposes."""

    change_input = ChangePlanInput(fixture.site_content, fixture.opportunities)
    error = validate_change_plan_input(change_input)
    if error is not None:
        raise ValueError(f"Synthetic fixture failed validation: {error}")
    material = build_change_plan_prompt(change_input).material_json()
    return SmokeContext(
        metrics=SmokeMetrics(
            system_chars=len(_SYSTEM_PROMPT),
            system_bytes=len(_SYSTEM_PROMPT.encode("utf-8")),
            user_chars=len(material),
            user_bytes=len(material.encode("utf-8")),
            envelope_chars=None,
            envelope_bytes=None,
        )
    )


def _safe_text(value: object, *, max_chars: int = 200) -> str:
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


def _print_operation_summary(operation) -> None:
    print(f"[{operation.change_id}]")
    print(f"  opportunity_ref: {operation.opportunity_ref}")
    print(f"  source_action_code: {operation.source_action_code.value}")
    print(f"  operation_type: {operation.operation_type.value}")
    print(f"  target_kind: {operation.target_kind.value}")
    locator = operation.locator
    print(f"  locator_kind: {locator.locator_kind.value}")
    print(f"  locator_page_ref: {locator.page_ref or '(none)'}")
    print(f"  locator_observed_heading: {locator.observed_heading or '(none)'}")
    if locator.observed_heading_kind is not None:
        print(f"  locator_observed_heading_kind: {locator.observed_heading_kind.value}")
    if locator.observed_context:
        print(f"  locator_observed_context: {_safe_text(locator.observed_context)}")
    if operation.proposed_heading:
        print(f"  proposed_heading: {_safe_text(operation.proposed_heading)}")
    if operation.content_points:
        print("  content_points:")
        for point in operation.content_points:
            print(f"    - {point.intent.value}: {_safe_text(point.subject)}")
    if operation.ordered_headings:
        print("  ordered_headings:")
        for heading in operation.ordered_headings:
            print(f"    - {_safe_text(heading)}")
    if operation.section_purpose is not None:
        print(f"  section_purpose: {operation.section_purpose.value}")
    if operation.comparison_table_spec is not None:
        table = operation.comparison_table_spec
        print(f"  table_column_headers: {', '.join(table.column_headers)}")
        print(f"  table_row_dimensions: {', '.join(table.row_dimensions)}")
    if operation.internal_link_spec is not None:
        link = operation.internal_link_spec
        print(f"  internal_link: {link.source_page_ref} -> {link.target_page_ref}")
        print(f"  anchor_intent: {_safe_text(link.anchor_intent)}")
    if operation.new_resource_spec is not None:
        resource = operation.new_resource_spec
        print(f"  resource_purpose: {resource.resource_purpose.value}")
        print(f"  proposed_title: {_safe_text(resource.proposed_title)}")
        if resource.outline_headings:
            print(f"  outline_headings: {', '.join(resource.outline_headings)}")
        if resource.suggested_source_page_refs:
            print(
                "  suggested_source_page_refs: "
                + ", ".join(resource.suggested_source_page_refs)
            )
    print(f"  P refs: {', '.join(operation.page_refs) or '(none)'}")
    print(f"  S refs: {', '.join(operation.source_refs) or '(none)'}")
    print(f"  requires_human_review: {str(operation.requires_human_review).lower()}")


async def _run_live(
    fixture: SyntheticFixture,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> int:
    """Run the full production pipeline with exactly one guarded provider request."""

    inner = transport if transport is not None else httpx.AsyncHTTPTransport()
    single = SingleRequestTransport(inner)
    production_writer = DeepSeekChangePlanWriter(transport=single)
    observer = ObservingChangePlanWriter(production_writer)
    workflow = ChangePlanWorkflow(observer)
    report = await workflow.run(fixture.site_content, fixture.opportunities)

    generation = observer.last_generation
    if (
        generation is not None
        and generation.status is ChangePlanGenerationStatus.SUCCESS
    ):
        generation_status = "success"
        finish_result = "accepted_stop"
    else:
        generation_status = "failed"
        finish_result = "rejected_or_unavailable"

    raw_chars = observer.raw_text_chars
    raw_bytes = observer.raw_text_bytes
    print(f"Request count: {single.request_count}")
    print(f"Generation status: {generation_status}")
    print(
        "Raw response chars: "
        + ("unavailable" if raw_chars is None else str(raw_chars))
    )
    print(
        "Raw response bytes: "
        + ("unavailable" if raw_bytes is None else str(raw_bytes))
    )
    print(f"Finish result: {finish_result}")
    print("Retry occurred: false")
    print(f"ChangePlanStatus: {report.status.value}")
    if report.error:
        print(f"Validation category: {report.error}")

    if report.status is not ChangePlanStatus.SUCCESS:
        return 1
    print(f"Operations count: {len(report.operations)}")
    for operation in report.operations:
        _print_operation_summary(operation)
    if report.operations:
        print("LIVE_CHANGE_PLAN_VERIFIED")
    else:
        print("LIVE_CHANGE_PLAN_NEEDS_REVIEW")
    return 0


def _print_metrics(metrics: SmokeMetrics) -> None:
    print(f"System prompt chars: {metrics.system_chars}")
    print(f"System prompt bytes: {metrics.system_bytes}")
    print(f"User material chars: {metrics.user_chars}")
    print(f"User material bytes: {metrics.user_bytes}")
    print(
        "Envelope chars: "
        + ("unavailable" if metrics.envelope_chars is None else str(metrics.envelope_chars))
    )
    print(
        "Envelope bytes: "
        + ("unavailable" if metrics.envelope_bytes is None else str(metrics.envelope_bytes))
    )


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
    transport: httpx.AsyncBaseTransport | None = None,
) -> int:
    _configure_utf8_output()
    args = _parser().parse_args(argv)
    fixture = build_synthetic_fixture()

    print(f"Mode: {'LIVE' if args.execute_live else 'DRY RUN'}")
    print(f"Synthetic fixture: {str(fixture is not None).lower()}")
    print(
        "Opportunities: "
        + ", ".join(
            item.recommendation_id for item in fixture.opportunities.opportunities
        )
    )
    print(
        "Pages: "
        + ", ".join(page.evidence_id for page in fixture.site_content.pages)
    )
    print(
        "Sources: "
        + ", ".join(
            material.source_id for material in fixture.opportunities.source_materials
        )
    )
    print("Expected maximum provider requests: 1")
    print("Tavily accessed: false")
    print("Crawler accessed: false")
    print("WordPress accessed: false")

    if not args.execute_live:
        print("Request count: 0")
        _print_metrics(prepare_smoke_context(fixture).metrics)
        return 0

    load_api_keys("DEEPSEEK_API_KEY")
    if not os.environ.get("DEEPSEEK_API_KEY", "").strip():
        print("DEEPSEEK_API_KEY: unavailable")
        print("Request count: 0")
        return 2

    print("DEEPSEEK_API_KEY: available")
    return asyncio.run(_run_live(fixture, transport=transport))


if __name__ == "__main__":
    raise SystemExit(main())
