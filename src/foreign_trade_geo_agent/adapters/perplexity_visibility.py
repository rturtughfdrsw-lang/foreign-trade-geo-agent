"""Async Perplexity Agent API adapter for search-grounded visibility."""

import json
import os
import re

import httpx

from foreign_trade_geo_agent.core.visibility import (
    Citation,
    ProviderResponse,
    ResponseStatus,
)


_WEB_REFERENCE = re.compile(r"\[web:([^\]]+)]", re.IGNORECASE)


class PerplexityVisibilityProvider:
    """Generate one web-grounded response through the Perplexity Agent API.

    The dynamic ``fast`` preset is the default for this PoC. Perplexity may
    update its underlying model and configuration over time, so callers that
    need a specific model can provide one explicitly instead.
    """

    provider_name = "perplexity"
    base_url = "https://api.perplexity.ai"
    endpoint = "/v1/agent"
    default_preset = "fast"

    def __init__(
        self,
        *,
        model: str | None = None,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        configured_model = model.strip() if model is not None else None
        if model is not None and not configured_model:
            raise ValueError("Perplexity model must not be empty.")

        self.model = configured_model or f"preset:{self.default_preset}"
        self._configured_model = configured_model
        self._api_key = os.environ.get("PERPLEXITY_API_KEY", "").strip()
        self._timeout = timeout
        self._transport = transport

    async def generate(self, prompt: str) -> ProviderResponse:
        """Return a normalized response for one search-grounded prompt."""

        if not self._api_key:
            return self._failed("PERPLEXITY_API_KEY is not configured.")

        request_payload: dict[str, object] = {
            "input": prompt,
            "tools": [{"type": "web_search"}],
        }
        if self._configured_model is None:
            request_payload["preset"] = self.default_preset
        else:
            request_payload["model"] = self._configured_model

        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self._timeout,
                transport=self._transport,
                headers={"Authorization": f"Bearer {self._api_key}"},
            ) as client:
                response = await client.post(self.endpoint, json=request_payload)
        except httpx.TimeoutException:
            return self._failed(
                f"Perplexity request timed out after {self._timeout:g} seconds."
            )
        except httpx.RequestError as exc:
            return self._failed(
                f"Perplexity network error ({type(exc).__name__})."
            )

        if not response.is_success:
            return self._failed(
                f"Perplexity API returned HTTP {response.status_code}."
            )

        try:
            payload = response.json()
        except json.JSONDecodeError:
            return self._failed("Perplexity API returned invalid JSON.")

        if not isinstance(payload, dict):
            return self._failed("Perplexity API returned an invalid response structure.")

        response_status = payload.get("status")
        if response_status != "completed":
            status_label = response_status if isinstance(response_status, str) else "missing"
            return self._failed(
                f"Perplexity response status was {status_label}, not completed."
            )

        text_parts = self._extract_text_parts(payload)
        if not text_parts:
            return self._failed("Perplexity API response is missing final answer text.")

        response_model = payload.get("model")
        model = (
            response_model.strip()
            if isinstance(response_model, str) and response_model.strip()
            else self.model
        )
        text = "\n".join(part[0] for part in text_parts)
        citations = self._extract_citations(payload, text_parts)

        return ProviderResponse(
            provider=self.provider_name,
            model=model,
            status=ResponseStatus.SUCCESS,
            text=text,
            citations=citations,
            error=None,
        )

    def _failed(self, error: str) -> ProviderResponse:
        return ProviderResponse(
            provider=self.provider_name,
            model=self.model,
            status=ResponseStatus.FAILED,
            text=None,
            citations=(),
            error=error,
        )

    @staticmethod
    def _extract_text_parts(
        payload: dict[object, object],
    ) -> tuple[tuple[str, tuple[dict[object, object], ...]], ...]:
        output = payload.get("output")
        if not isinstance(output, list):
            return ()

        parts: list[tuple[str, tuple[dict[object, object], ...]]] = []
        for item in output:
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "output_text":
                    continue
                text = block.get("text")
                if not isinstance(text, str) or not text.strip():
                    continue
                raw_annotations = block.get("annotations")
                annotations = (
                    tuple(
                        annotation
                        for annotation in raw_annotations
                        if isinstance(annotation, dict)
                    )
                    if isinstance(raw_annotations, list)
                    else ()
                )
                parts.append((text, annotations))
        return tuple(parts)

    @classmethod
    def _extract_citations(
        cls,
        payload: dict[object, object],
        text_parts: tuple[tuple[str, tuple[dict[object, object], ...]], ...],
    ) -> tuple[Citation, ...]:
        candidates: list[Citation] = []

        for _, annotations in text_parts:
            for annotation in annotations:
                citation = cls._citation_from_mapping(annotation)
                if citation is not None:
                    candidates.append(citation)

        search_results = cls._search_results_by_id(payload)
        for text, _ in text_parts:
            for reference in _WEB_REFERENCE.finditer(text):
                result = search_results.get(reference.group(1))
                if result is None:
                    continue
                citation = cls._citation_from_mapping(result)
                if citation is not None:
                    candidates.append(citation)

        unique: list[Citation] = []
        seen_urls: set[str] = set()
        for citation in candidates:
            if citation.url in seen_urls:
                continue
            seen_urls.add(citation.url)
            unique.append(citation)
        return tuple(unique)

    @staticmethod
    def _search_results_by_id(
        payload: dict[object, object],
    ) -> dict[str, dict[object, object]]:
        output = payload.get("output")
        if not isinstance(output, list):
            return {}

        indexed: dict[str, dict[object, object]] = {}
        for item in output:
            if not isinstance(item, dict) or item.get("type") != "search_results":
                continue
            raw_results = item.get("results")
            if not isinstance(raw_results, list):
                raw_results = item.get("contents")
            if not isinstance(raw_results, list):
                continue
            for result in raw_results:
                if not isinstance(result, dict):
                    continue
                result_id = result.get("id")
                if isinstance(result_id, (str, int)):
                    indexed[str(result_id)] = result
        return indexed

    @staticmethod
    def _citation_from_mapping(
        value: dict[object, object],
    ) -> Citation | None:
        url = value.get("url")
        if not isinstance(url, str) or not url.strip():
            return None

        raw_title = value.get("title")
        title = (
            raw_title.strip()
            if isinstance(raw_title, str) and raw_title.strip()
            else None
        )
        return Citation(url=url.strip(), title=title)
