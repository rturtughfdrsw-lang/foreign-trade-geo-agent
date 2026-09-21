import json
import os
import unittest
from unittest.mock import patch

import httpx

from foreign_trade_geo_agent.adapters.tavily_search import TavilySearchAdapter
from foreign_trade_geo_agent.core.search import SearchResult, SearchStatus


DUMMY_API_KEY = "unit-test-tavily-token"


def search_response(results: list[dict[str, object]]) -> dict[str, object]:
    return {
        "query": "industrial valve manufacturers",
        "answer": None,
        "images": [],
        "results": results,
        "response_time": 0.42,
        "request_id": "request-test",
    }


class TavilySearchAdapterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._environment = patch.dict(
            os.environ,
            {"TAVILY_API_KEY": DUMMY_API_KEY},
        )
        self._environment.start()

    def tearDown(self) -> None:
        self._environment.stop()

    async def test_maps_successful_search_result(self) -> None:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json=search_response(
                    [
                        {
                            "title": "Industrial valve suppliers",
                            "url": "https://example.com/valves",
                            "content": "A directory of industrial valve suppliers.",
                            "score": 0.91,
                            "raw_content": None,
                        }
                    ]
                ),
            )
        )

        response = await TavilySearchAdapter(transport=transport).search(
            "industrial valve manufacturers"
        )

        self.assertEqual(response.query, "industrial valve manufacturers")
        self.assertEqual(response.status, SearchStatus.SUCCESS)
        self.assertEqual(
            response.results,
            (
                SearchResult(
                    title="Industrial valve suppliers",
                    url="https://example.com/valves",
                    content="A directory of industrial valve suppliers.",
                    score=0.91,
                ),
            ),
        )
        self.assertIsNone(response.error)

    async def test_preserves_multiple_results_in_response_order(self) -> None:
        results = [
            {
                "title": "First",
                "url": "https://example.com/first",
                "content": "First result",
                "score": 0.9,
            },
            {
                "title": "Second",
                "url": "https://example.com/second",
                "content": "Second result",
                "score": 0.7,
            },
        ]
        transport = httpx.MockTransport(
            lambda request: httpx.Response(200, json=search_response(results))
        )

        response = await TavilySearchAdapter(transport=transport).search("suppliers")

        self.assertEqual([result.title for result in response.results], ["First", "Second"])

    async def test_empty_results_are_a_successful_search(self) -> None:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(200, json=search_response([]))
        )

        response = await TavilySearchAdapter(transport=transport).search("rare query")

        self.assertEqual(response.status, SearchStatus.SUCCESS)
        self.assertEqual(response.results, ())
        self.assertIsNone(response.error)

    async def test_missing_score_is_preserved_as_none(self) -> None:
        result = {
            "title": "Unscored result",
            "url": "https://example.com/unscored",
            "content": "No score was returned.",
        }
        transport = httpx.MockTransport(
            lambda request: httpx.Response(200, json=search_response([result]))
        )

        response = await TavilySearchAdapter(transport=transport).search("unscored")

        self.assertIsNone(response.results[0].score)

    async def test_missing_api_key_fails_without_sending_request(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.fail("No request should be sent without an API key.")

        with patch.dict(os.environ, {}, clear=True):
            response = await TavilySearchAdapter(
                transport=httpx.MockTransport(handler)
            ).search("suppliers")

        self.assertEqual(response.status, SearchStatus.FAILED)
        self.assertEqual(response.results, ())
        self.assertIn("TAVILY_API_KEY", response.error or "")

    async def test_401_is_a_failed_search(self) -> None:
        await self._assert_http_failure(401)

    async def test_403_is_a_failed_search(self) -> None:
        await self._assert_http_failure(403)

    async def test_429_is_a_failed_search(self) -> None:
        await self._assert_http_failure(429)

    async def test_5xx_is_a_failed_search(self) -> None:
        await self._assert_http_failure(503)

    async def test_timeout_is_a_failed_search(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("secret timeout detail", request=request)

        response = await TavilySearchAdapter(
            timeout=7.5,
            transport=httpx.MockTransport(handler),
        ).search("suppliers")

        self.assertEqual(response.status, SearchStatus.FAILED)
        self.assertEqual(response.results, ())
        self.assertEqual(response.error, "Tavily request timed out after 7.5 seconds.")
        self.assertNotIn(DUMMY_API_KEY, response.error or "")

    async def test_connection_failure_is_a_failed_search(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("secret connection detail", request=request)

        response = await TavilySearchAdapter(
            transport=httpx.MockTransport(handler)
        ).search("suppliers")

        self.assertEqual(response.status, SearchStatus.FAILED)
        self.assertEqual(response.results, ())
        self.assertEqual(response.error, "Tavily network error (ConnectError).")
        self.assertNotIn(DUMMY_API_KEY, response.error or "")

    async def test_invalid_json_is_a_failed_search(self) -> None:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                content=b"not-json",
                headers={"Content-Type": "application/json"},
            )
        )

        response = await TavilySearchAdapter(transport=transport).search("suppliers")

        self.assertEqual(response.status, SearchStatus.FAILED)
        self.assertEqual(response.results, ())
        self.assertEqual(response.error, "Tavily API returned invalid JSON.")

    async def test_missing_results_is_a_failed_search(self) -> None:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(200, json={"query": "suppliers"})
        )

        response = await TavilySearchAdapter(transport=transport).search("suppliers")

        self.assertEqual(response.status, SearchStatus.FAILED)
        self.assertEqual(response.results, ())
        self.assertEqual(response.error, "Tavily API returned an invalid response structure.")

    async def test_malformed_result_is_a_failed_search(self) -> None:
        malformed_result = {
            "title": "Missing URL",
            "content": "This result violates the Tavily response contract.",
            "score": 0.8,
        }
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json=search_response([malformed_result]),
            )
        )

        response = await TavilySearchAdapter(transport=transport).search("suppliers")

        self.assertEqual(response.status, SearchStatus.FAILED)
        self.assertEqual(response.results, ())
        self.assertEqual(response.error, "Tavily API returned an invalid response structure.")

    async def test_sends_expected_endpoint_headers_parameters_and_timeout(self) -> None:
        captured_url = ""
        captured_authorization = ""
        captured_payload: dict[str, object] = {}
        captured_timeout: dict[str, float] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal captured_url, captured_authorization, captured_payload
            captured_url = str(request.url)
            captured_authorization = request.headers.get("Authorization", "")
            captured_payload = json.loads(request.content)
            captured_timeout.update(request.extensions["timeout"])
            return httpx.Response(200, json=search_response([]))

        response = await TavilySearchAdapter(
            transport=httpx.MockTransport(handler)
        ).search("industrial valve manufacturers")

        self.assertEqual(response.status, SearchStatus.SUCCESS)
        self.assertEqual(captured_url, "https://api.tavily.com/search")
        self.assertEqual(captured_authorization, f"Bearer {DUMMY_API_KEY}")
        self.assertEqual(
            captured_payload,
            {
                "query": "industrial valve manufacturers",
                "search_depth": "basic",
                "topic": "general",
                "max_results": 5,
            },
        )
        self.assertEqual(
            captured_timeout,
            {"connect": 30.0, "read": 30.0, "write": 30.0, "pool": 30.0},
        )

    async def test_blank_query_fails_without_sending_request(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.fail("No request should be sent for a blank query.")

        response = await TavilySearchAdapter(
            transport=httpx.MockTransport(handler)
        ).search("   ")

        self.assertEqual(response.status, SearchStatus.FAILED)
        self.assertEqual(response.query, "   ")
        self.assertEqual(response.results, ())
        self.assertEqual(response.error, "Search query must not be empty.")

    async def _assert_http_failure(self, status_code: int) -> None:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                status_code,
                json={"detail": {"error": "sensitive upstream detail"}},
            )
        )

        response = await TavilySearchAdapter(transport=transport).search("suppliers")

        self.assertEqual(response.status, SearchStatus.FAILED)
        self.assertEqual(response.results, ())
        self.assertEqual(response.error, f"Tavily API returned HTTP {status_code}.")
        self.assertNotIn(DUMMY_API_KEY, response.error or "")
        self.assertNotIn("sensitive upstream detail", response.error or "")


if __name__ == "__main__":
    unittest.main()
