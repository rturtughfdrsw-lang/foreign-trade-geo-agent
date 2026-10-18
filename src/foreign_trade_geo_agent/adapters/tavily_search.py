"""Async Tavily adapter for normalized web search results."""

import json
import os

import httpx

from foreign_trade_geo_agent.core.search import (
    SearchResponse,
    SearchResult,
    SearchStatus,
)


class TavilySearchAdapter:
    """Run one web search through Tavily's Search API."""

    base_url = "https://api.tavily.com"
    endpoint = "/search"
    max_results = 5

    def __init__(
        self,
        *,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = os.environ.get("TAVILY_API_KEY", "").strip()
        self._timeout = timeout
        self._transport = transport

    async def search(self, query: str) -> SearchResponse:
        """Return normalized results for one query."""

        if not query.strip():
            return self._failed(query, "Search query must not be empty.")
        if not self._api_key:
            return self._failed(query, "TAVILY_API_KEY is not configured.")

        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self._timeout,
                transport=self._transport,
                headers={"Authorization": f"Bearer {self._api_key}"},
            ) as client:
                response = await client.post(
                    self.endpoint,
                    json={
                        "query": query,
                        "search_depth": "basic",
                        "topic": "general",
                        "max_results": self.max_results,
                    },
                )
        except httpx.TimeoutException:
            return self._failed(
                query,
                f"Tavily request timed out after {self._timeout:g} seconds.",
            )
        except httpx.RequestError as exc:
            return self._failed(query, f"Tavily network error ({type(exc).__name__}).")

        if not response.is_success:
            return self._failed(
                query,
                f"Tavily API returned HTTP {response.status_code}.",
            )

        try:
            payload = response.json()
        except json.JSONDecodeError:
            return self._failed(query, "Tavily API returned invalid JSON.")

        results = self._extract_results(payload)
        if results is None:
            return self._failed(
                query,
                "Tavily API returned an invalid response structure.",
            )

        return SearchResponse(
            query=query,
            status=SearchStatus.SUCCESS,
            results=results,
            error=None,
        )

    @staticmethod
    def _extract_results(payload: object) -> tuple[SearchResult, ...] | None:
        if not isinstance(payload, dict):
            return None

        raw_results = payload.get("results")
        if not isinstance(raw_results, list):
            return None

        results: list[SearchResult] = []
        for raw_result in raw_results:
            if not isinstance(raw_result, dict):
                return None

            title = raw_result.get("title")
            url = raw_result.get("url")
            content = raw_result.get("content")
            score = raw_result.get("score")
            if (
                not isinstance(title, str)
                or not isinstance(url, str)
                or not url.strip()
                or not isinstance(content, str)
                or isinstance(score, bool)
                or (score is not None and not isinstance(score, (int, float)))
            ):
                return None

            results.append(
                SearchResult(
                    title=title,
                    url=url,
                    content=content,
                    score=float(score) if score is not None else None,
                )
            )

        return tuple(results)

    @staticmethod
    def _failed(query: str, error: str) -> SearchResponse:
        return SearchResponse(
            query=query,
            status=SearchStatus.FAILED,
            results=(),
            error=error,
        )
