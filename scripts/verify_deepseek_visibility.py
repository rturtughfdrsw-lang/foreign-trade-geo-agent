"""Run one explicit DeepSeek visibility provider smoke test."""

import asyncio
import os
from time import perf_counter

from foreign_trade_geo_agent.adapters.deepseek_visibility import (
    DeepSeekVisibilityProvider,
)
from scripts.local_env import load_api_keys


async def _verify() -> None:
    started_at = perf_counter()
    response = await DeepSeekVisibilityProvider().generate(
        "Say exactly: provider test successful"
    )
    elapsed = perf_counter() - started_at

    print(f"Status: {response.status.name}")
    print(f"Text: {response.text or ''}")
    print(f"Elapsed seconds: {elapsed:.3f}")


def main() -> int:
    load_api_keys("DEEPSEEK_API_KEY")
    if not os.environ.get("DEEPSEEK_API_KEY", "").strip():
        print("DEEPSEEK_API_KEY is not set; no request was sent.")
        return 2

    asyncio.run(_verify())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
