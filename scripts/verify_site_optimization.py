"""Run one explicitly configured site-optimization integration check."""

import asyncio
from collections.abc import Callable
import json
import os
import sys
from time import perf_counter

from foreign_trade_geo_agent.adapters.deepseek_optimization import (
    DeepSeekOptimizationWriter,
)
from foreign_trade_geo_agent.adapters.geo_optimizer import GeoOptimizerAdapter
from foreign_trade_geo_agent.adapters.tavily_search import TavilySearchAdapter
from foreign_trade_geo_agent.core.optimization import (
    OptimizationStatus,
    SiteOptimizationReport,
    SiteOptimizationRequest,
)
from foreign_trade_geo_agent.workflows.site_optimization import (
    INVALID_OUTPUT_ERRORS,
    INVALID_OUTPUT_ERROR_PREFIX,
    SiteOptimizationWorkflow,
)


async def _run_once(
    request: SiteOptimizationRequest,
    *,
    workflow: SiteOptimizationWorkflow | None = None,
    clock: Callable[[], float] = perf_counter,
) -> tuple[SiteOptimizationReport, float]:
    """Run exactly one top-level workflow and return elapsed seconds."""

    active_workflow = workflow or SiteOptimizationWorkflow(
        GeoOptimizerAdapter(),
        TavilySearchAdapter(),
        DeepSeekOptimizationWriter(),
    )
    started_at = clock()
    report = await active_workflow.run(request)
    return report, clock() - started_at


def _configure_utf8_output() -> None:
    """Use UTF-8 for standard text streams when the runtime supports it."""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if not callable(reconfigure):
            continue
        try:
            reconfigure(encoding="utf-8", errors="backslashreplace")
        except (OSError, ValueError):
            # Redirected or already-detached streams may not be reconfigurable.
            continue


def _format_observed_value(value: object, *, max_chars: int = 512) -> str:
    """Render one approved evidence value without emitting markup or large text."""

    rendered = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    rendered = rendered.replace("<", "\\u003c").replace(">", "\\u003e")
    if len(rendered) > max_chars:
        return f"{rendered[: max_chars - 3]}..."
    return rendered


def _print_result(report: SiteOptimizationReport, elapsed: float) -> int:
    """Print only trusted identifiers, metadata, and bounded draft fields."""

    print(f"Status: {report.status.name}")
    print(f"Elapsed seconds: {elapsed:.3f}")
    if report.status is not OptimizationStatus.SUCCESS:
        if (
            report.status is OptimizationStatus.INVALID_OUTPUT
            and report.error in INVALID_OUTPUT_ERRORS
        ):
            diagnostic = report.error.removeprefix(INVALID_OUTPUT_ERROR_PREFIX)
            category, separator, recommendation = diagnostic.partition(":")
            print(f"Failure category: {category}")
            if separator:
                print(f"Recommendation: {recommendation}")
        else:
            print("Workflow did not produce a successful optimization draft.")
        return 1

    print(f"requires_human_review={report.requires_human_review}")
    print(f"Audit evidence count: {len(report.audit_evidence)}")
    print("Audit evidence:")
    for numbered in report.audit_evidence:
        item = numbered.evidence
        print(
            f"[{numbered.evidence_id}] category={item.category.value} "
            f"check_key={item.check_key} outcome={item.outcome.value} "
            f"observed_value={_format_observed_value(item.observed_value)}"
        )
    print(f"External source count: {len(report.sources)}")
    print("Trusted external sources:")
    for source in report.sources:
        print(f"[{source.source_id}] {source.title} | {source.url}")
    print("Recommendations:")
    for item in report.recommendations:
        print(
            f"[{item.recommendation_id}] {item.priority.value} "
            f"{item.kind.value}: {item.title}"
        )
        print(f"  Rationale: {item.rationale}")
        for action_number, action in enumerate(item.actions, start=1):
            print(f"  Action {action_number}: {action}")
        print(f"  audit_refs: {', '.join(item.audit_refs) or '(none)'}")
        print(f"  source_refs: {', '.join(item.source_refs) or '(none)'}")
    print("Limitations:")
    for limitation in report.limitations:
        print(f"- {limitation}")
    print("This draft requires human review.")
    return 0


def _configured_request() -> SiteOptimizationRequest:
    products = tuple(
        item.strip()
        for item in os.environ["SITE_PRODUCT_TERMS"].split(",")
        if item.strip()
    )
    markets = tuple(
        item.strip()
        for item in os.environ.get("SITE_TARGET_MARKETS", "").split(",")
        if item.strip()
    )
    return SiteOptimizationRequest(
        url=os.environ["SITE_OPTIMIZATION_URL"],
        research_topic=os.environ["SITE_RESEARCH_TOPIC"],
        product_terms=products,
        target_markets=markets,
    )


def main() -> int:
    _configure_utf8_output()
    required = (
        "SITE_OPTIMIZATION_URL",
        "SITE_RESEARCH_TOPIC",
        "SITE_PRODUCT_TERMS",
        "TAVILY_API_KEY",
        "DEEPSEEK_API_KEY",
    )
    missing = [name for name in required if not os.environ.get(name, "").strip()]
    if missing:
        print(
            "Missing required environment variables: "
            f"{', '.join(missing)}; no workflow was started."
        )
        return 2
    try:
        request = _configured_request()
    except ValueError as exc:
        print(f"Invalid site optimization configuration: {exc}")
        return 2

    report, elapsed = asyncio.run(_run_once(request))
    return _print_result(report, elapsed)


if __name__ == "__main__":
    raise SystemExit(main())
