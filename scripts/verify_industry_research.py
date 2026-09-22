"""Run one explicit Tavily-to-DeepSeek industry research smoke test."""

import asyncio
from collections.abc import Callable
import os
from time import perf_counter

from foreign_trade_geo_agent.adapters.deepseek_research import (
    DeepSeekResearchWriter,
)
from foreign_trade_geo_agent.adapters.tavily_search import TavilySearchAdapter
from foreign_trade_geo_agent.core.research import ResearchReport, ResearchStatus
from foreign_trade_geo_agent.workflows.industry_research import (
    IndustryResearchWorkflow,
)
from scripts.local_env import load_api_keys


RESEARCH_QUESTION = (
    "对全球工业阀门市场进行初步研究：概述主要需求驱动因素、"
    "典型应用行业和主要供应商类型。"
)


async def _run_once(
    *,
    workflow: IndustryResearchWorkflow | None = None,
    clock: Callable[[], float] = perf_counter,
) -> tuple[ResearchReport, float]:
    """Run the fixed workflow exactly once and return its elapsed time."""

    active_workflow = workflow or IndustryResearchWorkflow(
        TavilySearchAdapter(),
        DeepSeekResearchWriter(),
    )
    started_at = clock()
    report = await active_workflow.run(RESEARCH_QUESTION)
    elapsed = clock() - started_at
    return report, elapsed


def _print_result(report: ResearchReport, elapsed: float) -> int:
    """Print a safe summary and return a process exit code."""

    print(f"Status: {report.status.name}")
    print(f"requires_human_review={report.requires_human_review}")
    print("注意：引用编号正确不等于事实已核实，本报告必须人工审核。")

    if report.status is ResearchStatus.SUCCESS:
        print("Report draft:")
        print(report.draft_text or "")
        print("Trusted sources:")
        for source in report.sources:
            print(f"[{source.source_id}] {source.url} — {source.title}")
        print(f"Elapsed seconds: {elapsed:.3f}")
        return 0

    safe_failure_reasons = {
        ResearchStatus.SEARCH_FAILED: "Search stage failed.",
        ResearchStatus.NO_RESULTS: "Search returned no usable results.",
        ResearchStatus.GENERATION_FAILED: "Report generation failed.",
        ResearchStatus.INVALID_OUTPUT: "Generated draft failed source validation.",
    }
    print(f"Failure: {safe_failure_reasons.get(report.status, 'Research workflow failed.')}")
    print(f"Elapsed seconds: {elapsed:.3f}")
    return 1


def main() -> int:
    load_api_keys("TAVILY_API_KEY", "DEEPSEEK_API_KEY")
    required_keys = ("TAVILY_API_KEY", "DEEPSEEK_API_KEY")
    missing_keys = [
        name for name in required_keys if not os.environ.get(name, "").strip()
    ]
    if missing_keys:
        print(
            "Missing required environment variables: "
            f"{', '.join(missing_keys)}; no request was sent."
        )
        return 2

    report, elapsed = asyncio.run(_run_once())
    return _print_result(report, elapsed)


if __name__ == "__main__":
    raise SystemExit(main())
