"""Run one explicit end-to-end AI visibility smoke test."""

import asyncio
import os

from foreign_trade_geo_agent.adapters.deepseek_visibility import (
    DeepSeekVisibilityProvider,
)
from foreign_trade_geo_agent.core.visibility import ResponseStatus
from foreign_trade_geo_agent.core.visibility_monitor import VisibilityMonitor
from scripts.local_env import load_api_keys


TARGET_BRAND = "Flowserve"
PROMPTS = (
    "Name several major global industrial valve manufacturers.",
    "Which companies are well known for industrial flow control and valve products?",
    "Recommend established suppliers of valves and flow-control equipment for industrial B2B buyers.",
)


async def _verify() -> None:
    report = await VisibilityMonitor().run(
        target_brand=TARGET_BRAND,
        competitor_names=(),
        prompts=PROMPTS,
        providers=(DeepSeekVisibilityProvider(),),
    )

    mention_rate = (
        f"{report.mention_rate:.4f}"
        if report.mention_rate is not None
        else "None"
    )
    print(f"Target: {report.target_brand}")
    print()
    print(f"Total attempts: {report.total_attempts}")
    print(f"Successful: {report.successful_observations}")
    print(f"Failed: {report.failed_observations}")
    print(f"Mentioned: {report.mentioned_count}")
    print(f"Mention rate: {mention_rate}")

    for index, observation in enumerate(report.observations, start=1):
        print()
        print(f"Prompt {index}")
        print(f"Prompt text: {observation.prompt}")
        print(f"Status: {observation.response.status.name}")
        print(f"Target mentioned: {observation.target_mentioned}")
        if observation.response.status is ResponseStatus.SUCCESS:
            print(f"Response: {observation.response.text or ''}")
        else:
            print(f"Error: {observation.response.error or 'Unknown provider error'}")


def main() -> int:
    load_api_keys("DEEPSEEK_API_KEY")
    if not os.environ.get("DEEPSEEK_API_KEY", "").strip():
        print("DEEPSEEK_API_KEY is not set; no requests were sent.")
        return 2

    asyncio.run(_verify())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
