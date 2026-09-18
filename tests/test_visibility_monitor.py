from collections.abc import Mapping
from datetime import datetime, timezone
import unittest

from foreign_trade_geo_agent.core.visibility import (
    Citation,
    ProviderResponse,
    ResponseStatus,
)
from foreign_trade_geo_agent.core.visibility_monitor import (
    VisibilityMonitor,
    mentions_entity,
)


class FakeProvider:
    def __init__(self, responses: Mapping[str, ProviderResponse]) -> None:
        self._responses = responses
        self.prompts: list[str] = []

    async def generate(self, prompt: str) -> ProviderResponse:
        self.prompts.append(prompt)
        return self._responses[prompt]


def successful_response(
    text: str,
    *,
    provider: str = "fake",
    model: str = "fake-model",
    citations: tuple[Citation, ...] = (),
) -> ProviderResponse:
    return ProviderResponse(
        provider=provider,
        model=model,
        status=ResponseStatus.SUCCESS,
        text=text,
        citations=citations,
        error=None,
    )


def failed_response(
    error: str,
    *,
    provider: str = "fake",
    model: str = "fake-model",
) -> ProviderResponse:
    return ProviderResponse(
        provider=provider,
        model=model,
        status=ResponseStatus.FAILED,
        text=None,
        citations=(),
        error=error,
    )


class MentionMatchingTests(unittest.TestCase):
    def test_matches_brand_with_original_case(self) -> None:
        self.assertTrue(mentions_entity("OpenAI released a new model.", "OpenAI"))

    def test_matches_brand_case_insensitively(self) -> None:
        self.assertTrue(mentions_entity("OPENAI released a new model.", "openai"))

    def test_does_not_match_short_brand_inside_word(self) -> None:
        self.assertFalse(mentions_entity("The report said otherwise.", "AI"))

    def test_matches_short_brand_at_word_boundary(self) -> None:
        self.assertTrue(mentions_entity("AI tools are improving.", "AI"))

    def test_treats_hyphen_as_a_boundary(self) -> None:
        self.assertTrue(mentions_entity("ABC-Valve supplies this part.", "ABC"))

    def test_matches_brand_ending_with_special_characters(self) -> None:
        self.assertTrue(mentions_entity("C++ tools are widely available.", "C++"))

    def test_matches_brand_starting_with_special_characters(self) -> None:
        self.assertTrue(mentions_entity("Use .NET tools for this project.", ".NET"))

    def test_matches_brand_containing_spaces(self) -> None:
        self.assertTrue(mentions_entity("ABC Valve supplies this part.", "ABC Valve"))

    def test_trims_brand_whitespace(self) -> None:
        self.assertTrue(mentions_entity("OpenAI released a new model.", "  OpenAI  "))

    def test_rejects_empty_brand(self) -> None:
        with self.assertRaises(ValueError):
            mentions_entity("Any answer", "   ")


class VisibilityMonitorTests(unittest.IsolatedAsyncioTestCase):
    async def test_successful_response_records_target_mention(self) -> None:
        provider = FakeProvider(
            {"best supplier": successful_response("Acme is a strong supplier.")}
        )

        report = await VisibilityMonitor().run(
            target_brand="Acme",
            competitor_names=(),
            prompts=("best supplier",),
            providers=(provider,),
        )

        observation = report.observations[0]
        self.assertEqual(observation.prompt, "best supplier")
        self.assertTrue(observation.target_mentioned)
        self.assertEqual(observation.response.status, ResponseStatus.SUCCESS)
        self.assertEqual(report.total_attempts, 1)
        self.assertEqual(report.successful_observations, 1)
        self.assertEqual(report.failed_observations, 0)
        self.assertEqual(report.mentioned_count, 1)
        self.assertEqual(report.mention_rate, 1.0)
        self.assertEqual(observation.timestamp.tzinfo, timezone.utc)

    async def test_successful_response_can_record_no_target_mention(self) -> None:
        provider = FakeProvider(
            {"best supplier": successful_response("Another supplier is recommended.")}
        )

        report = await VisibilityMonitor().run(
            target_brand="Acme",
            competitor_names=(),
            prompts=("best supplier",),
            providers=(provider,),
        )

        self.assertFalse(report.observations[0].target_mentioned)
        self.assertEqual(report.mentioned_count, 0)
        self.assertEqual(report.mention_rate, 0.0)

    async def test_records_competitors_and_structured_citations(self) -> None:
        citation = Citation(url="https://example.com/report", title="Industry report")
        provider = FakeProvider(
            {
                "compare suppliers": successful_response(
                    "Acme, Bravo and CHARLIE are established suppliers.",
                    citations=(citation,),
                )
            }
        )

        report = await VisibilityMonitor().run(
            target_brand="Acme",
            competitor_names=("Bravo", "Charlie", "Delta"),
            prompts=("compare suppliers",),
            providers=(provider,),
        )

        observation = report.observations[0]
        self.assertEqual(observation.mentioned_competitors, ("Bravo", "Charlie"))
        self.assertEqual(observation.response.citations, (citation,))
        self.assertEqual(
            report.competitor_mention_counts,
            {"Bravo": 1, "Charlie": 1, "Delta": 0},
        )
        self.assertEqual(
            report.competitor_mention_rates,
            {"Bravo": 1.0, "Charlie": 1.0, "Delta": 0.0},
        )
        self.assertEqual(report.citation_count, 1)

    async def test_failed_provider_response_is_not_a_negative_mention(self) -> None:
        provider = FakeProvider({"best supplier": failed_response("provider timeout")})

        report = await VisibilityMonitor().run(
            target_brand="Acme",
            competitor_names=("Bravo",),
            prompts=("best supplier",),
            providers=(provider,),
        )

        observation = report.observations[0]
        self.assertEqual(observation.response.status, ResponseStatus.FAILED)
        self.assertIsNone(observation.target_mentioned)
        self.assertEqual(observation.mentioned_competitors, ())
        self.assertEqual(report.successful_observations, 0)
        self.assertEqual(report.failed_observations, 1)
        self.assertEqual(report.mentioned_count, 0)
        self.assertIsNone(report.mention_rate)
        self.assertIsNone(report.competitor_mention_rates["Bravo"])

    async def test_multiple_prompts_and_providers_use_only_successes_as_denominator(self) -> None:
        prompts = ("first", "second")
        provider_one = FakeProvider(
            {
                "first": successful_response(
                    "Acme and Bravo are options.", provider="one", model="model-one"
                ),
                "second": failed_response(
                    "rate limited", provider="one", model="model-one"
                ),
            }
        )
        provider_two = FakeProvider(
            {
                "first": successful_response(
                    "Acme is an option.", provider="two", model="model-two"
                ),
                "second": successful_response(
                    "Charlie is an option.", provider="two", model="model-two"
                ),
            }
        )

        report = await VisibilityMonitor().run(
            target_brand="Acme",
            competitor_names=("Bravo", "Charlie"),
            prompts=prompts,
            providers=(provider_one, provider_two),
        )

        self.assertEqual(report.total_attempts, 4)
        self.assertEqual(report.successful_observations, 3)
        self.assertEqual(report.failed_observations, 1)
        self.assertEqual(report.mentioned_count, 2)
        self.assertEqual(
            report.total_attempts,
            report.successful_observations + report.failed_observations,
        )
        self.assertLessEqual(report.mentioned_count, report.successful_observations)
        self.assertAlmostEqual(report.mention_rate or 0.0, 2 / 3)
        self.assertEqual(report.competitor_mention_counts, {"Bravo": 1, "Charlie": 1})
        self.assertEqual(
            report.competitor_mention_rates,
            {"Bravo": 1 / 3, "Charlie": 1 / 3},
        )
        self.assertEqual(provider_one.prompts, ["first", "second"])
        self.assertEqual(provider_two.prompts, ["first", "second"])

    async def test_all_failures_produce_no_visibility_rate(self) -> None:
        provider = FakeProvider(
            {
                "first": failed_response("timeout"),
                "second": failed_response("rate limited"),
            }
        )

        report = await VisibilityMonitor().run(
            target_brand="Acme",
            competitor_names=(),
            prompts=("first", "second"),
            providers=(provider,),
        )

        self.assertEqual(report.total_attempts, 2)
        self.assertEqual(report.successful_observations, 0)
        self.assertEqual(report.failed_observations, 2)
        self.assertIsNone(report.mention_rate)

    async def test_rejects_empty_target_brand(self) -> None:
        with self.assertRaises(ValueError):
            await VisibilityMonitor().run(
                target_brand="   ",
                competitor_names=(),
                prompts=(),
                providers=(),
            )


class ProviderResponseContractTests(unittest.TestCase):
    def test_success_requires_text_and_no_error(self) -> None:
        with self.assertRaises(ValueError):
            ProviderResponse(
                provider="fake",
                model="fake-model",
                status=ResponseStatus.SUCCESS,
                text=None,
                citations=(),
                error=None,
            )

    def test_failure_requires_error_and_no_success_payload(self) -> None:
        with self.assertRaises(ValueError):
            ProviderResponse(
                provider="fake",
                model="fake-model",
                status=ResponseStatus.FAILED,
                text="partial answer",
                citations=(),
                error="timeout",
            )


if __name__ == "__main__":
    unittest.main()
