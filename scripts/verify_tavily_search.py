"""Run one explicit Tavily Search API smoke test."""

import asyncio
import os
from time import perf_counter

from foreign_trade_geo_agent.adapters.tavily_search import TavilySearchAdapter
from foreign_trade_geo_agent.core.search import SearchStatus


async def _verify() -> SearchStatus:
    started_at = perf_counter()
    response = await TavilySearchAdapter().search(
        "leading industrial valve manufacturers"
    )
    elapsed = perf_counter() - started_at

    print(f"Status: {response.status.name}")
    print(f"Results: {len(response.results)}")
    for result in response.results:
        print(f"- {result.title}: {result.url}")
    if response.error:
        print(f"Error: {response.error}")
    print(f"Elapsed seconds: {elapsed:.3f}")
    return response.status


def main() -> int:
    if not os.environ.get("TAVILY_API_KEY", "").strip():
        print("TAVILY_API_KEY is not set; no request was sent.")
        return 2

    status = asyncio.run(_verify())
    return 0 if status is SearchStatus.SUCCESS else 1


if __name__ == "__main__":
    raise SystemExit(main())
