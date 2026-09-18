import json
import os
import unittest
from unittest.mock import patch

import httpx

from foreign_trade_geo_agent.adapters.perplexity_visibility import (
    PerplexityVisibilityProvider,
)
from foreign_trade_geo_agent.core.visibility import Citation, ResponseStatus
from foreign_trade_geo_agent.core.visibility_monitor import VisibilityMonitor


DUMMY_API_KEY = "unit-test-perplexity-token"


def agent_response(
    text: str = "Flowserve is a major valve manufacturer.[web:1]",
    *,
    annotations: list[dict[str, object]] | None = None,
    search_results: list[dict[str, object]] | None = None,
    status: str = "completed",
) -> dict[str, object]:
    return {
        "id": "resp_test",
        "object": "response",
        "status": status,
        "model": "openai/gpt-5.6-luna",
        "error": None,
        "output": [
            {
                "id": "search_test",
                "type": "search_results",
                "status": "completed",
                "results": search_results
                if search_results is not None
                else [
                    {
                        "id": 1,
                        "title": "Flowserve company profile",
                        "url": "https://example.com/flowserve",
                        "snippet": "Flowserve makes industrial flow-control products.",
                        "source": "web",
                    }
                ],
            },
            {
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [
                    {
                        "type": "output_text",
                        "text": text,
                        "annotations": annotations or [],
                        "logprobs": [],
                    }
                ],
            },
        ],
    }


class PerplexityVisibilityProviderTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._environment = patch.dict(
            os.environ,
            {"PERPLEXITY_API_KEY": DUMMY_API_KEY},
        )
        self._environment.start()

    def tearDown(self) -> None:
        self._environment.stop()

    async def test_maps_search_grounded_response_to_provider_response(self) -> None:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(200, json=agent_response())
        )

        result = await PerplexityVisibilityProvider(transport=transport).generate(
            "Name an industrial valve manufacturer."
        )

        self.assertEqual(result.status, ResponseStatus.SUCCESS)
        self.assertEqual(result.provider, "perplexity")
        self.assertEqual(result.model, "openai/gpt-5.6-luna")
        self.assertEqual(
            result.text,
            "Flowserve is a major valve manufacturer.[web:1]",
        )
        self.assertEqual(
            result.citations,
            (
                Citation(
                    url="https://example.com/flowserve",
                    title="Flowserve company profile",
                ),
            ),
        )
        self.assertIsNone(result.error)

    async def test_extracts_all_final_output_text_parts_in_order(self) -> None:
        payload = agent_response("First paragraph.")
        message = payload["output"][1]
        message["content"].append(
            {
                "type": "output_text",
                "text": "Second paragraph.",
                "annotations": [],
                "logprobs": [],
            }
        )
        transport = httpx.MockTransport(
            lambda request: httpx.Response(200, json=payload)
        )

        result = await PerplexityVisibilityProvider(transport=transport).generate(
            "test prompt"
        )

        self.assertEqual(result.text, "First paragraph.\nSecond paragraph.")

    async def test_maps_explicit_url_annotation_to_citation(self) -> None:
        annotation = {
            "type": "url_citation",
            "url": "https://example.com/annotated",
            "title": "Annotated source",
            "start_index": 0,
            "end_index": 8,
        }
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json=agent_response(
                    "Grounded answer.",
                    annotations=[annotation],
                    search_results=[],
                ),
            )
        )

        result = await PerplexityVisibilityProvider(transport=transport).generate(
            "test prompt"
        )

        self.assertEqual(
            result.citations,
            (Citation(url="https://example.com/annotated", title="Annotated source"),),
        )

    async def test_maps_multiple_confirmed_citations(self) -> None:
        results = [
            {"id": 1, "url": "https://example.com/one", "title": "One"},
            {"id": 2, "url": "https://example.com/two", "title": "Two"},
        ]
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json=agent_response(
                    "First claim.[web:1] Second claim.[web:2]",
                    search_results=results,
                ),
            )
        )

        result = await PerplexityVisibilityProvider(transport=transport).generate(
            "test prompt"
        )

        self.assertEqual(
            result.citations,
            (
                Citation(url="https://example.com/one", title="One"),
                Citation(url="https://example.com/two", title="Two"),
            ),
        )

    async def test_does_not_treat_unreferenced_search_result_as_citation(self) -> None:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json=agent_response("Answer without a reference."),
            )
        )

        result = await PerplexityVisibilityProvider(transport=transport).generate(
            "test prompt"
        )

        self.assertEqual(result.citations, ())

    async def test_deduplicates_annotation_and_inline_reference_by_url(self) -> None:
        annotations = [
            {
                "type": "url_citation",
                "url": "https://example.com/shared",
                "title": "Annotation title",
            },
            {
                "type": "url_citation",
                "url": "https://example.com/other",
                "title": "Other source",
            },
        ]
        results = [
            {"id": 1, "url": "https://example.com/shared", "title": "Search title"}
        ]
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json=agent_response(
                    "Grounded answer.[web:1]",
                    annotations=annotations,
                    search_results=results,
                ),
            )
        )

        result = await PerplexityVisibilityProvider(transport=transport).generate(
            "test prompt"
        )

        self.assertEqual(
            result.citations,
            (
                Citation(
                    url="https://example.com/shared",
                    title="Annotation title",
                ),
                Citation(url="https://example.com/other", title="Other source"),
            ),
        )

    async def test_default_request_uses_fast_preset_and_web_search(self) -> None:
        captured_url = ""
        captured_payload: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal captured_url, captured_payload
            captured_url = str(request.url)
            captured_payload = json.loads(request.content)
            return httpx.Response(200, json=agent_response())

        await PerplexityVisibilityProvider(
            transport=httpx.MockTransport(handler)
        ).generate("current valve manufacturers")

        self.assertEqual(captured_url, "https://api.perplexity.ai/v1/agent")
        self.assertEqual(
            captured_payload,
            {
                "preset": "fast",
                "input": "current valve manufacturers",
                "tools": [{"type": "web_search"}],
            },
        )

    async def test_explicit_model_replaces_preset(self) -> None:
        captured_payload: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal captured_payload
            captured_payload = json.loads(request.content)
            return httpx.Response(200, json=agent_response())

        await PerplexityVisibilityProvider(
            model="openai/gpt-5.6-luna",
            transport=httpx.MockTransport(handler),
        ).generate("test prompt")

        self.assertEqual(captured_payload["model"], "openai/gpt-5.6-luna")
        self.assertNotIn("preset", captured_payload)
        self.assertEqual(captured_payload["tools"], [{"type": "web_search"}])

    async def test_sends_bearer_authentication_without_exposing_key(self) -> None:
        captured_authorization: str | None = None

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal captured_authorization
            captured_authorization = request.headers.get("Authorization")
            return httpx.Response(200, json=agent_response())

        result = await PerplexityVisibilityProvider(
            transport=httpx.MockTransport(handler)
        ).generate("test prompt")

        self.assertEqual(captured_authorization, f"Bearer {DUMMY_API_KEY}")
        self.assertNotIn(DUMMY_API_KEY, result.error or "")

    async def test_converts_401_to_failed_response(self) -> None:
        await self._assert_http_failure(401)

    async def test_converts_429_to_failed_response(self) -> None:
        await self._assert_http_failure(429)

    async def test_converts_500_to_failed_response(self) -> None:
        await self._assert_http_failure(500)

    async def test_converts_timeout_to_failed_response(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("timed out", request=request)

        result = await PerplexityVisibilityProvider(
            timeout=7.5,
            transport=httpx.MockTransport(handler),
        ).generate("test prompt")

        self.assertEqual(result.status, ResponseStatus.FAILED)
        self.assertIn("timed out", result.error or "")
        self.assertNotIn(DUMMY_API_KEY, result.error or "")

    async def test_converts_connection_error_to_failed_response(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection failed", request=request)

        result = await PerplexityVisibilityProvider(
            transport=httpx.MockTransport(handler)
        ).generate("test prompt")

        self.assertEqual(result.status, ResponseStatus.FAILED)
        self.assertIn("network", (result.error or "").lower())

    async def test_converts_invalid_json_to_failed_response(self) -> None:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                content=b"not-json",
                headers={"Content-Type": "application/json"},
            )
        )

        result = await PerplexityVisibilityProvider(transport=transport).generate(
            "test prompt"
        )

        self.assertEqual(result.status, ResponseStatus.FAILED)
        self.assertIn("JSON", result.error or "")

    async def test_converts_non_completed_response_to_failed_response(self) -> None:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json=agent_response(status="incomplete"),
            )
        )

        result = await PerplexityVisibilityProvider(transport=transport).generate(
            "test prompt"
        )

        self.assertEqual(result.status, ResponseStatus.FAILED)
        self.assertIn("incomplete", result.error or "")

    async def test_converts_missing_final_text_to_failed_response(self) -> None:
        payload = agent_response()
        payload["output"] = [payload["output"][0]]
        transport = httpx.MockTransport(
            lambda request: httpx.Response(200, json=payload)
        )

        result = await PerplexityVisibilityProvider(transport=transport).generate(
            "test prompt"
        )

        self.assertEqual(result.status, ResponseStatus.FAILED)
        self.assertIn("answer text", result.error or "")

    async def test_missing_api_key_fails_without_sending_request(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.fail("No HTTP request should be sent without an API key.")

        with patch.dict(os.environ, {}, clear=True):
            result = await PerplexityVisibilityProvider(
                transport=httpx.MockTransport(handler)
            ).generate("test prompt")

        self.assertEqual(result.status, ResponseStatus.FAILED)
        self.assertIn("PERPLEXITY_API_KEY", result.error or "")

    async def test_successful_response_is_consumed_by_visibility_monitor(self) -> None:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json=agent_response("Flowserve is a recommended supplier.[web:1]"),
            )
        )
        provider = PerplexityVisibilityProvider(transport=transport)

        report = await VisibilityMonitor().run(
            target_brand="Flowserve",
            competitor_names=(),
            prompts=("Which valve supplier is recommended?",),
            providers=(provider,),
        )

        self.assertEqual(report.successful_observations, 1)
        self.assertEqual(report.failed_observations, 0)
        self.assertEqual(report.mentioned_count, 1)
        self.assertEqual(report.mention_rate, 1.0)
        self.assertEqual(report.citation_count, 1)

    async def _assert_http_failure(self, status_code: int) -> None:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                status_code,
                json={"error": {"message": "sensitive upstream detail"}},
            )
        )

        result = await PerplexityVisibilityProvider(transport=transport).generate(
            "test prompt"
        )

        self.assertEqual(result.status, ResponseStatus.FAILED)
        self.assertEqual(
            result.error,
            f"Perplexity API returned HTTP {status_code}.",
        )
        self.assertNotIn(DUMMY_API_KEY, result.error or "")
        self.assertNotIn("sensitive upstream detail", result.error or "")


if __name__ == "__main__":
    unittest.main()
