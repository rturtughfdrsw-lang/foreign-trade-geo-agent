import json
import os
import unittest
from unittest.mock import patch

import httpx

from foreign_trade_geo_agent.adapters.deepseek_content_opportunity import (
    DeepSeekContentOpportunityWriter,
)
from foreign_trade_geo_agent.core.content_opportunity import (
    MAX_INPUT_ENVELOPE_BYTES,
    MAX_INPUT_ENVELOPE_CHARS,
    MAX_SYSTEM_PROMPT_BYTES,
    MAX_SYSTEM_PROMPT_CHARS,
    ContentOpportunityGenerationStatus,
    ContentOpportunityPrompt,
    ContentOpportunitySourceMaterial,
    OpportunityEvidenceCatalog,
    OpportunityPageEvidence,
    OpportunitySourceEvidence,
)
from foreign_trade_geo_agent.core.crawling import CrawlStopReason
from foreign_trade_geo_agent.core.extraction import PageExtractionStatus
from foreign_trade_geo_agent.core.research import ResearchEvidenceClassification
from foreign_trade_geo_agent.core.site_content import (
    SiteContentEvidence,
    SiteContentEvidenceScope,
    SiteContentPacket,
)


DUMMY_API_KEY = "test-key-never-send"


def prompt(*, body_text: str = "Observed pump performance.") -> ContentOpportunityPrompt:
    page = SiteContentEvidence(
        evidence_id="P1",
        final_url="https://example.com/pump",
        title="Pump",
        description=None,
        h1=("Pump",),
        h2=(),
        body_text=body_text,
        structured_content=(),
        extraction_status=PageExtractionStatus.SUCCESS,
        extraction_failure_kind=None,
        structured_content_truncated=False,
        content_truncated=False,
    )
    packet = SiteContentPacket(
        pages=(page,),
        source_page_count=1,
        crawl_stop_reason=CrawlStopReason.COMPLETED,
        crawl_budget_exhausted=False,
        truncated=False,
    )
    classifications = (
        ResearchEvidenceClassification.EXTERNAL_RESEARCH_CONTEXT,
        ResearchEvidenceClassification.UNVERIFIED_SEARCH_RESULT,
    )
    source = ContentOpportunitySourceMaterial(
        source_id="S1",
        title="Pump performance",
        content="Pump performance evidence.",
        content_truncated=False,
    )
    catalog = OpportunityEvidenceCatalog(
        pages=(
            OpportunityPageEvidence(
                evidence_id="P1",
                extraction_status=PageExtractionStatus.SUCCESS,
                content_truncated=False,
                structured_content_truncated=False,
                evidence_scope=SiteContentEvidenceScope.OBSERVED_PRESENT_ONLY,
                supports_absence_claims=False,
                has_observed_present=True,
                context_only_only=False,
            ),
        ),
        sources=(OpportunitySourceEvidence("S1", False, classifications),),
    )
    return ContentOpportunityPrompt(packet, catalog, (source,), False)


def completion(content: str, finish_reason: str = "stop") -> dict[str, object]:
    return {
        "choices": [
            {
                "message": {"content": content},
                "finish_reason": finish_reason,
            }
        ]
    }


class DeepSeekContentOpportunityWriterTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_key_fails_without_http_call(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(200, json=completion('{"opportunities":[]}'))

        with patch.dict(os.environ, {}, clear=True):
            result = await DeepSeekContentOpportunityWriter(
                transport=httpx.MockTransport(handler)
            ).write_content_opportunities(prompt())

        self.assertEqual(result.status, ContentOpportunityGenerationStatus.FAILED)
        self.assertEqual(calls, 0)

    async def test_sends_one_bounded_request_with_fixed_contract(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, json=completion('{"opportunities":[]}'))

        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": DUMMY_API_KEY}, clear=True):
            result = await DeepSeekContentOpportunityWriter(
                transport=httpx.MockTransport(handler)
            ).write_content_opportunities(prompt())

        self.assertEqual(result.status, ContentOpportunityGenerationStatus.SUCCESS)
        self.assertEqual(len(requests), 1)
        payload = json.loads(requests[0].content)
        self.assertEqual(payload["model"], "deepseek-flash")
        self.assertEqual(payload["max_tokens"], 1_500)
        self.assertEqual(payload["thinking"], {"type": "disabled"})
        self.assertEqual(len(payload["messages"]), 2)
        self.assertLessEqual(len(payload["messages"][0]["content"]), MAX_SYSTEM_PROMPT_CHARS)
        self.assertLessEqual(
            len(payload["messages"][0]["content"].encode("utf-8")),
            MAX_SYSTEM_PROMPT_BYTES,
        )
        self.assertIn("observed_present_only", payload["messages"][1]["content"])
        self.assertEqual(requests[0].headers["Authorization"], f"Bearer {DUMMY_API_KEY}")

    async def test_final_serialized_envelope_stays_within_hard_limits(self) -> None:
        captured: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured.update(json.loads(request.content))
            return httpx.Response(200, json=completion('{"opportunities":[]}'))

        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": DUMMY_API_KEY}, clear=True):
            result = await DeepSeekContentOpportunityWriter(
                transport=httpx.MockTransport(handler)
            ).write_content_opportunities(prompt())

        envelope = json.dumps(captured, ensure_ascii=False, separators=(",", ":"))
        self.assertEqual(result.status, ContentOpportunityGenerationStatus.SUCCESS)
        self.assertLessEqual(len(envelope), MAX_INPUT_ENVELOPE_CHARS)
        self.assertLessEqual(len(envelope.encode("utf-8")), MAX_INPUT_ENVELOPE_BYTES)

    async def test_oversized_user_material_or_envelope_fails_before_http(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(200, json=completion('{"opportunities":[]}'))

        oversized = prompt(body_text="x" * 25_000)
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": DUMMY_API_KEY}, clear=True):
            result = await DeepSeekContentOpportunityWriter(
                transport=httpx.MockTransport(handler)
            ).write_content_opportunities(oversized)

        self.assertEqual(result.status, ContentOpportunityGenerationStatus.FAILED)
        self.assertEqual(calls, 0)

    async def test_raw_output_character_and_utf8_byte_limits_are_enforced(self) -> None:
        outputs = ("x" * 12_001, "泵" * 8_193)
        for output in outputs:
            with self.subTest(chars=len(output), bytes=len(output.encode("utf-8"))):
                with patch.dict(os.environ, {"DEEPSEEK_API_KEY": DUMMY_API_KEY}, clear=True):
                    result = await DeepSeekContentOpportunityWriter(
                        transport=httpx.MockTransport(
                            lambda request, value=output: httpx.Response(
                                200, json=completion(value)
                            )
                        )
                    ).write_content_opportunities(prompt())
                self.assertEqual(result.status, ContentOpportunityGenerationStatus.FAILED)

    async def test_length_finish_reason_fails_without_parsing_partial_json(self) -> None:
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": DUMMY_API_KEY}, clear=True):
            result = await DeepSeekContentOpportunityWriter(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(
                        200,
                        json=completion('{"opportunities":[', finish_reason="length"),
                    )
                )
            ).write_content_opportunities(prompt())
        self.assertEqual(result.status, ContentOpportunityGenerationStatus.FAILED)
        self.assertIn("truncated", (result.error or "").casefold())

    async def test_http_and_network_failures_are_sanitized_and_single_call(self) -> None:
        cases: tuple[object, ...] = (
            401,
            httpx.ReadTimeout("secret timeout"),
            httpx.ConnectError("secret connection"),
        )
        for failure in cases:
            calls = 0

            def handler(request: httpx.Request) -> httpx.Response:
                nonlocal calls
                calls += 1
                if isinstance(failure, int):
                    return httpx.Response(failure, json={"error": DUMMY_API_KEY})
                failure.request = request
                raise failure

            with self.subTest(failure=type(failure).__name__):
                with patch.dict(os.environ, {"DEEPSEEK_API_KEY": DUMMY_API_KEY}, clear=True):
                    result = await DeepSeekContentOpportunityWriter(
                        transport=httpx.MockTransport(handler)
                    ).write_content_opportunities(prompt())
                self.assertEqual(result.status, ContentOpportunityGenerationStatus.FAILED)
                self.assertEqual(calls, 1)
                self.assertNotIn("secret", (result.error or "").casefold())
                self.assertNotIn(DUMMY_API_KEY, result.error or "")

    async def test_invalid_provider_payloads_fail_safely(self) -> None:
        responses = (
            httpx.Response(200, content=b"not-json", headers={"Content-Type": "application/json"}),
            httpx.Response(200, json={"choices": []}),
            httpx.Response(200, json=completion("   ")),
        )
        for response in responses:
            with self.subTest(content=response.content):
                with patch.dict(os.environ, {"DEEPSEEK_API_KEY": DUMMY_API_KEY}, clear=True):
                    result = await DeepSeekContentOpportunityWriter(
                        transport=httpx.MockTransport(lambda request, value=response: value)
                    ).write_content_opportunities(prompt())
                self.assertEqual(result.status, ContentOpportunityGenerationStatus.FAILED)


if __name__ == "__main__":
    unittest.main()
