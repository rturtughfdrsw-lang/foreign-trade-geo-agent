"""Async DeepSeek adapter for AI visibility observations."""

import json
import os

import httpx

from foreign_trade_geo_agent.core.visibility import ProviderResponse, ResponseStatus


class DeepSeekVisibilityProvider:
    """Generate one text response through DeepSeek Chat Completions."""

    provider_name = "deepseek"
    model = "deepseek-flash"
    base_url = "https://api.deepseek.com"
    endpoint = "/chat/completions"

    def __init__(
        self,
        *,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        self._timeout = timeout
        self._transport = transport

    async def generate(self, prompt: str) -> ProviderResponse:
        """Return a normalized response for one prompt."""

        if not self._api_key:
            return self._failed("DEEPSEEK_API_KEY is not configured.")

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
                        "model": self.model,
                        "messages": [{"role": "user", "content": prompt}],
                        "thinking": {"type": "disabled"},
                    },
                )
        except httpx.TimeoutException:
            return self._failed(
                f"DeepSeek request timed out after {self._timeout:g} seconds."
            )
        except httpx.RequestError as exc:
            return self._failed(
                f"DeepSeek network error ({type(exc).__name__})."
            )

        if not response.is_success:
            return self._failed(
                f"DeepSeek API returned HTTP {response.status_code}."
            )

        try:
            payload = response.json()
        except json.JSONDecodeError:
            return self._failed("DeepSeek API returned invalid JSON.")

        text = self._extract_model_text(payload)
        if text is None:
            return self._failed("DeepSeek API response is missing model text.")

        return ProviderResponse(
            provider=self.provider_name,
            model=self.model,
            status=ResponseStatus.SUCCESS,
            text=text,
            citations=(),
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
    def _extract_model_text(payload: object) -> str | None:
        if not isinstance(payload, dict):
            return None

        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            return None

        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            return None

        message = first_choice.get("message")
        if not isinstance(message, dict):
            return None

        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            return None
        return content
