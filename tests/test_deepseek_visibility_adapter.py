import json
import os
import unittest
from unittest.mock import patch

import httpx

from foreign_trade_geo_agent.adapters.deepseek_visibility import (
    DeepSeekVisibilityProvider,
)
from foreign_trade_geo_agent.core.visibility import ResponseStatus
from foreign_trade_geo_agent.core.visibility_monitor import VisibilityMonitor


DUMMY_API_KEY = "unit-test-token"


def chat_completion(content: str) -> dict[str, object]:
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 1_700_000_000,
        "model": "deepseek-flash",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 3,
            "completion_tokens": 4,
            "total_tokens": 7,
        },
    }


class DeepSeekVisibilityProviderTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._environment = patch.dict(
            os.environ,
            {"DEEPSEEK_API_KEY": DUMMY_API_KEY},
        )
        self._environment.start()

    def tearDown(self) -> None:
        self._environment.stop()

    async def test_maps_successful_completion_to_provider_response(self) -> None:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json=chat_completion("provider test successful"),
            )
        )

        result = await DeepSeekVisibilityProvider(transport=transport).generate(
            "Say exactly: provider test successful"
        )

        self.assertEqual(result.status, ResponseStatus.SUCCESS)
        self.assertEqual(result.provider, "deepseek")
        self.assertEqual(result.model, "deepseek-flash")
        self.assertEqual(result.text, "provider test successful")
        self.assertEqual(result.citations, ())
        self.assertIsNone(result.error)

    async def test_sends_bearer_authentication_without_exposing_key_in_result(self) -> None:
        captured_authorization: str | None = None

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal captured_authorization
            captured_authorization = request.headers.get("Authorization")
            return httpx.Response(200, json=chat_completion("ok"))

        result = await DeepSeekVisibilityProvider(
            transport=httpx.MockTransport(handler)
        ).generate("test prompt")

        self.assertEqual(captured_authorization, f"Bearer {DUMMY_API_KEY}")
        self.assertNotIn(DUMMY_API_KEY, result.error or "")

    async def test_sends_expected_endpoint_model_and_single_user_message(self) -> None:
        captured_url = ""
        captured_payload: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal captured_url, captured_payload
            captured_url = str(request.url)
            captured_payload = json.loads(request.content)
            return httpx.Response(200, json=chat_completion("ok"))

        await DeepSeekVisibilityProvider(
            transport=httpx.MockTransport(handler)
        ).generate("Which supplier is recommended?")

        self.assertEqual(captured_url, "https://api.deepseek.com/chat/completions")
        self.assertEqual(
            captured_payload,
            {
                "model": "deepseek-flash",
                "messages": [
                    {"role": "user", "content": "Which supplier is recommended?"}
                ],
                "thinking": {"type": "disabled"},
            },
        )

    async def test_converts_401_to_failed_response(self) -> None:
        await self._assert_http_failure(401)

    async def test_converts_429_to_failed_response(self) -> None:
        await self._assert_http_failure(429)

    async def test_converts_500_to_failed_response(self) -> None:
        await self._assert_http_failure(500)

    async def test_converts_timeout_to_failed_response(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("timed out", request=request)

        result = await DeepSeekVisibilityProvider(
            transport=httpx.MockTransport(handler)
        ).generate("test prompt")

        self.assertEqual(result.status, ResponseStatus.FAILED)
        self.assertIn("timed out", result.error or "")
        self.assertNotIn(DUMMY_API_KEY, result.error or "")

    async def test_converts_network_connection_error_to_failed_response(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection failed", request=request)

        result = await DeepSeekVisibilityProvider(
            transport=httpx.MockTransport(handler)
        ).generate("test prompt")

        self.assertEqual(result.status, ResponseStatus.FAILED)
        self.assertIn("network", (result.error or "").lower())
        self.assertNotIn(DUMMY_API_KEY, result.error or "")

    async def test_converts_invalid_json_to_failed_response(self) -> None:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                content=b"not-json",
                headers={"Content-Type": "application/json"},
            )
        )

        result = await DeepSeekVisibilityProvider(transport=transport).generate(
            "test prompt"
        )

        self.assertEqual(result.status, ResponseStatus.FAILED)
        self.assertIn("JSON", result.error or "")
        self.assertNotIn(DUMMY_API_KEY, result.error or "")

    async def test_converts_missing_choices_to_failed_response(self) -> None:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(200, json={"model": "deepseek-flash"})
        )

        result = await DeepSeekVisibilityProvider(transport=transport).generate(
            "test prompt"
        )

        self.assertEqual(result.status, ResponseStatus.FAILED)
        self.assertIn("model text", result.error or "")

    async def test_converts_missing_message_content_to_failed_response(self) -> None:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={"choices": [{"message": {"role": "assistant"}}]},
            )
        )

        result = await DeepSeekVisibilityProvider(transport=transport).generate(
            "test prompt"
        )

        self.assertEqual(result.status, ResponseStatus.FAILED)
        self.assertIn("model text", result.error or "")

    async def test_missing_api_key_fails_without_sending_request(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.fail("No HTTP request should be sent without an API key.")

        with patch.dict(os.environ, {}, clear=True):
            result = await DeepSeekVisibilityProvider(
                transport=httpx.MockTransport(handler)
            ).generate("test prompt")

        self.assertEqual(result.status, ResponseStatus.FAILED)
        self.assertIn("DEEPSEEK_API_KEY", result.error or "")

    async def test_timeout_can_be_overridden(self) -> None:
        captured_timeout: dict[str, float] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured_timeout.update(request.extensions["timeout"])
            return httpx.Response(200, json=chat_completion("ok"))

        await DeepSeekVisibilityProvider(
            timeout=7.5,
            transport=httpx.MockTransport(handler),
        ).generate("test prompt")

        self.assertEqual(
            captured_timeout,
            {"connect": 7.5, "read": 7.5, "write": 7.5, "pool": 7.5},
        )

    async def test_successful_response_is_consumed_by_visibility_monitor(self) -> None:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json=chat_completion("Acme is a recommended supplier."),
            )
        )
        provider = DeepSeekVisibilityProvider(transport=transport)

        report = await VisibilityMonitor().run(
            target_brand="Acme",
            competitor_names=(),
            prompts=("Which supplier is recommended?",),
            providers=(provider,),
        )

        self.assertEqual(report.successful_observations, 1)
        self.assertEqual(report.failed_observations, 0)
        self.assertEqual(report.mentioned_count, 1)
        self.assertEqual(report.mention_rate, 1.0)

    async def _assert_http_failure(self, status_code: int) -> None:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                status_code,
                json={"error": {"message": "sensitive upstream detail"}},
            )
        )

        result = await DeepSeekVisibilityProvider(transport=transport).generate(
            "test prompt"
        )

        self.assertEqual(result.status, ResponseStatus.FAILED)
        self.assertEqual(result.error, f"DeepSeek API returned HTTP {status_code}.")
        self.assertNotIn(DUMMY_API_KEY, result.error or "")
        self.assertNotIn("sensitive upstream detail", result.error or "")


if __name__ == "__main__":
    unittest.main()
