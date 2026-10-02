"""Authenticated read-back adapter for persisted WordPress draft attempts."""

from __future__ import annotations

import json
import unittest

import httpx

from foreign_trade_geo_agent.adapters.wordpress_rest import WordPressRestDraftReader
from foreign_trade_geo_agent.core.history import (
    WordPressVerificationFailureKind,
)
from foreign_trade_geo_agent.core.wordpress_verification import (
    WordPressDraftReadOutcome,
    WordPressDraftReadRequest,
)


BASE_URL = "https://cms.example.com"
USERNAME = "editor"
PASSWORD = "application-password-secret"


class _FakeResolver:
    def __init__(self, addresses: tuple[str, ...]) -> None:
        self._addresses = addresses
        self.calls: list[tuple[str, int]] = []

    async def resolve(self, host: str, port: int) -> tuple[str, ...]:
        self.calls.append((host, port))
        return self._addresses


class _TransportFactory:
    def __init__(self, handler) -> None:
        self._handler = handler
        self.calls: list[tuple[str, int, str]] = []

    def __call__(self, host: str, port: int, address: str) -> httpx.AsyncBaseTransport:
        self.calls.append((host, port, address))
        return httpx.MockTransport(self._handler)


def _reader(handler, **overrides) -> WordPressRestDraftReader:
    values = {
        "base_url": BASE_URL,
        "username": USERNAME,
        "application_password": PASSWORD,
        "transport": httpx.MockTransport(handler),
    }
    values.update(overrides)
    return WordPressRestDraftReader(**values)


def _read_request(post_id: int = 41) -> WordPressDraftReadRequest:
    return WordPressDraftReadRequest(remote_post_id=post_id)


def _draft_body(post_id: int = 41, *, status: str = "draft") -> dict[str, object]:
    return {
        "id": post_id,
        "status": status,
        "link": f"https://cms.example.com/?p={post_id}",
        "title": {"rendered": "Buyer Guide"},
        "content": {"rendered": "<p>Safe body</p>"},
    }


class WordPressRestDraftReaderTests(unittest.IsolatedAsyncioTestCase):
    def test_target_site_key_is_the_normalized_origin(self) -> None:
        reader = _reader(lambda request: httpx.Response(200, json=_draft_body()))

        self.assertEqual(reader.target_site_key, "https://cms.example.com:443")

    async def test_successful_read_uses_bounded_authenticated_get(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, json=_draft_body())

        result = await _reader(handler).read_draft(_read_request())

        self.assertEqual(result.outcome, WordPressDraftReadOutcome.FOUND)
        self.assertEqual(result.remote_post_id, 41)
        self.assertEqual(result.status, "draft")
        self.assertEqual(result.link, "https://cms.example.com/?p=41")
        self.assertTrue(result.has_title)
        self.assertTrue(result.has_content)
        self.assertIsNone(result.failure_kind)
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].method, "GET")
        self.assertEqual(requests[0].url.path, "/wp-json/wp/v2/posts/41")
        self.assertTrue(requests[0].headers["Authorization"].startswith("Basic "))
        self.assertNotIn(PASSWORD, requests[0].headers["Authorization"])

    async def test_missing_title_and_content_are_reported_as_absent(self) -> None:
        body = _draft_body()
        body.pop("title")
        body.pop("content")

        result = await _reader(lambda request: httpx.Response(200, json=body)).read_draft(
            _read_request()
        )

        self.assertEqual(result.outcome, WordPressDraftReadOutcome.FOUND)
        self.assertFalse(result.has_title)
        self.assertFalse(result.has_content)

    async def test_trusted_404_is_not_found(self) -> None:
        result = await _reader(
            lambda request: httpx.Response(404, json={"code": "rest_post_invalid_id"})
        ).read_draft(_read_request())

        self.assertEqual(result.outcome, WordPressDraftReadOutcome.NOT_FOUND)
        self.assertIsNone(result.failure_kind)
        self.assertIsNone(result.remote_post_id)

    async def test_redirects_are_rejected_without_following(self) -> None:
        calls: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(302, headers={"Location": "https://evil.example/"})

        result = await _reader(handler).read_draft(_read_request())

        self.assertEqual(result.outcome, WordPressDraftReadOutcome.FAILED)
        self.assertEqual(result.failure_kind, WordPressVerificationFailureKind.REDIRECT_REJECTED)
        self.assertEqual(len(calls), 1)

    async def test_auth_failures_and_server_errors_are_sanitized(self) -> None:
        cases = (
            (401, WordPressVerificationFailureKind.AUTH_FAILED),
            (403, WordPressVerificationFailureKind.AUTH_FAILED),
            (500, WordPressVerificationFailureKind.HTTP_STATUS),
            (429, WordPressVerificationFailureKind.HTTP_STATUS),
        )
        for status_code, expected_kind in cases:
            with self.subTest(status_code=status_code):
                leak = "SECRET_SERVER_BODY"

                def handler(request: httpx.Request, code=status_code) -> httpx.Response:
                    return httpx.Response(code, text=leak)

                result = await _reader(handler).read_draft(_read_request())

                self.assertEqual(result.outcome, WordPressDraftReadOutcome.FAILED)
                self.assertEqual(result.failure_kind, expected_kind)
                self.assertNotIn(leak, result.error or "")
                self.assertNotIn(PASSWORD, result.error or "")

    async def test_timeout_and_transport_failure_are_not_retried(self) -> None:
        cases = (
            (httpx.ReadTimeout("SECRET_TIMEOUT"), WordPressVerificationFailureKind.TIMEOUT),
            (httpx.ConnectError("SECRET_CONNECT"), WordPressVerificationFailureKind.REQUEST_FAILED),
        )
        for error, expected_kind in cases:
            calls: list[httpx.Request] = []

            def handler(request: httpx.Request, exc=error) -> httpx.Response:
                calls.append(request)
                raise exc

            with self.subTest(error=type(error).__name__):
                result = await _reader(handler).read_draft(_read_request())

                self.assertEqual(result.outcome, WordPressDraftReadOutcome.FAILED)
                self.assertEqual(result.failure_kind, expected_kind)
                self.assertEqual(len(calls), 1)
                self.assertNotIn("SECRET", result.error or "")

    async def test_oversized_response_body_is_rejected(self) -> None:
        huge = b"x" * (300 * 1024)

        result = await _reader(
            lambda request: httpx.Response(
                200,
                content=huge,
                headers={"Content-Type": "application/json"},
            )
        ).read_draft(_read_request())

        self.assertEqual(result.outcome, WordPressDraftReadOutcome.FAILED)
        self.assertEqual(
            result.failure_kind,
            WordPressVerificationFailureKind.RESPONSE_TOO_LARGE,
        )

    async def test_malformed_responses_fail_closed(self) -> None:
        responses = (
            httpx.Response(200, text="not json"),
            httpx.Response(200, json=[]),
            httpx.Response(200, json={"status": "draft", "link": "https://cms.example.com/1"}),
            httpx.Response(200, json={"id": True, "status": "draft"}),
            httpx.Response(200, json={"id": 41}),
            httpx.Response(200, json={"id": 41, "status": 7}),
        )
        for response in responses:
            with self.subTest(content=response.content):
                result = await _reader(
                    lambda request, value=response: value
                ).read_draft(_read_request())

                self.assertEqual(result.outcome, WordPressDraftReadOutcome.FAILED)
                self.assertEqual(
                    result.failure_kind,
                    WordPressVerificationFailureKind.MALFORMED_RESPONSE,
                )

    async def test_invalid_or_denied_origins_never_send_a_request(self) -> None:
        calls: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(200, json=_draft_body())

        cases = (
            {"base_url": "http://cms.example.com"},
            {"base_url": "https://cms.example.com/wordpress"},
            {"base_url": "https://127.0.0.1"},
            {"base_url": "https://metadata.google.internal"},
            {"username": ""},
            {"application_password": ""},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides):
                reader = _reader(handler, **overrides)
                result = await reader.read_draft(_read_request())

                self.assertEqual(result.outcome, WordPressDraftReadOutcome.FAILED)
                self.assertEqual(
                    result.failure_kind,
                    WordPressVerificationFailureKind.REQUEST_FAILED,
                )
        self.assertEqual(calls, [])

    async def test_production_resolver_pins_a_public_address(self) -> None:
        factory = _TransportFactory(lambda request: httpx.Response(200, json=_draft_body()))
        reader = WordPressRestDraftReader(
            base_url="https://cms.example.com",
            username=USERNAME,
            application_password=PASSWORD,
            resolver=_FakeResolver(("93.184.216.34",)),
            _transport_factory=factory,
        )

        result = await reader.read_draft(_read_request())

        self.assertEqual(result.outcome, WordPressDraftReadOutcome.FOUND)
        self.assertEqual(factory.calls, [("cms.example.com", 443, "93.184.216.34")])

    async def test_resolver_rejecting_private_answers_stops_before_http(self) -> None:
        calls: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(200, json=_draft_body())

        reader = WordPressRestDraftReader(
            base_url="https://cms.example.com",
            username=USERNAME,
            application_password=PASSWORD,
            resolver=_FakeResolver(("10.0.0.5",)),
            _transport_factory=_TransportFactory(handler),
        )

        result = await reader.read_draft(_read_request())

        self.assertEqual(result.outcome, WordPressDraftReadOutcome.FAILED)
        self.assertEqual(
            result.failure_kind,
            WordPressVerificationFailureKind.REQUEST_FAILED,
        )
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
