"""Run one explicit Perplexity search-grounded provider smoke test."""

import asyncio
import os
from time import perf_counter

from foreign_trade_geo_agent.adapters.perplexity_visibility import (
    PerplexityVisibilityProvider,
)


async def _verify() -> None:
    started_at = perf_counter()
    response = await PerplexityVisibilityProvider().generate(
        "What notable industrial valve manufacturer news was published this month?"
    )
    elapsed = perf_counter() - started_at

    print(f"Status: {response.status.name}")
    if response.text:
        summary = response.text[:500]
        if len(response.text) > len(summary):
            summary += "..."
        print(f"Answer: {summary}")
    elif response.error:
        print(f"Error: {response.error}")

    print(f"Citations: {len(response.citations)}")
    for citation in response.citations:
        print(f"- {citation.title or '(untitled)'}: {citation.url}")
    print(f"Elapsed seconds: {elapsed:.3f}")


def main() -> int:
    if not os.environ.get("PERPLEXITY_API_KEY", "").strip():
        print("PERPLEXITY_API_KEY is not set; no request was sent.")
        return 2

    asyncio.run(_verify())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
