import json
import os
import unittest
from unittest.mock import patch

import httpx

from foreign_trade_geo_agent.adapters.wordpress_rest import WordPressRestDraftPublisher
from foreign_trade_geo_agent.core.wordpress_draft import (
    WordPressDraftFailureKind,
    WordPressDraftRequest,
    WordPressDraftStatus,
)


BASE_URL = "https://cms.example.com"
USERNAME = "editor"
PASSWORD = "application-password-secret"


def _request() -> WordPressDraftRequest:
    return WordPressDraftRequest("Buyer Guide", "<p>Safe body</p>")


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


def _publisher(handler, **overrides) -> WordPressRestDraftPublisher:
    values = {
        "base_url": BASE_URL,
        "username": USERNAME,
        "application_password": PASSWORD,
        "transport": httpx.MockTransport(handler),
    }
    values.update(overrides)
    return WordPressRestDraftPublisher(**values)


def _draft_response(post_id: int = 41, *, status: str = "draft") -> httpx.Response:
    return httpx.Response(
        200,
        json={"id": post_id, "status": status, "link": f"https://cms.example.com/?p={post_id}"},
    )


class WordPressRestDraftPublisherTests(unittest.IsolatedAsyncioTestCase):
    async def test_successful_create_uses_exact_endpoint_and_forces_draft(self) -> None:
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return _draft_response()

        result = await _publisher(handler).publish_draft(_request())

        self.assertEqual(result.status, WordPressDraftStatus.SUCCESS)
        self.assertEqual(result.remote_post_id, 41)
        self.assertEqual(result.remote_link, "https://cms.example.com/?p=41")
        self.assertTrue(result.created)
        self.assertEqual(len(requests), 1)
        sent = requests[0]
        self.assertEqual(sent.method, "POST")
        self.assertEqual(sent.url.path, "/wp-json/wp/v2/posts")
        self.assertEqual(
            json.loads(sent.content),
            {"title": "Buyer Guide", "content": "<p>Safe body</p>", "status": "draft"},
        )
        self.assertTrue(sent.headers["Authorization"].startswith("Basic "))
        self.assertNotIn(PASSWORD, sent.headers["Authorization"])

    async def test_non_draft_post_response_fails_closed(self) -> None:
        for remote_status in ("publish", "pending", "private", "future"):
            requests = []

            def handler(request: httpx.Request, status=remote_status) -> httpx.Response:
                requests.append(request)
                return _draft_response(9, status=status)

            with self.subTest(remote_status=remote_status):
                result = await _publisher(handler).publish_draft(_request())
                self.assertEqual(
                    result.failure_kind,
                    WordPressDraftFailureKind.RESPONSE_NOT_DRAFT,
                )
                self.assertFalse(result.created)
                self.assertEqual(len(requests), 1)
                self.assertEqual(requests[0].url.path, "/wp-json/wp/v2/posts")

    async def test_malformed_post_responses_fail_closed(self) -> None:
        responses = (
            httpx.Response(200, text="not json"),
            httpx.Response(200, json=[]),
            httpx.Response(200, json={"status": "draft", "link": "https://cms.example.com/1"}),
            httpx.Response(200, json={"id": True, "status": "draft", "link": "https://cms.example.com/1"}),
            httpx.Response(200, json={"id": 0, "status": "draft", "link": "https://cms.example.com/1"}),
            httpx.Response(200, json={"id": -1, "status": "draft", "link": "https://cms.example.com/1"}),
            httpx.Response(200, json={"id": 1, "link": "https://cms.example.com/1"}),
            httpx.Response(200, json={"id": 1, "status": "draft"}),
            httpx.Response(200, json={"id": 1, "status": "draft", "link": "http://cms.example.com/1"}),
            httpx.Response(200, json={"id": 1, "status": "draft", "link": "not-a-url"}),
        )
        for response in responses:
            with self.subTest(content=response.content):
                result = await _publisher(lambda request, value=response: value).publish_draft(
                    _request()
                )
                self.assertEqual(
                    result.failure_kind,
                    WordPressDraftFailureKind.MALFORMED_RESPONSE,
                )

    async def test_http_error_mapping_is_sanitized_and_never_retried(self) -> None:
        for status, expected in (
            (401, WordPressDraftFailureKind.AUTH_FAILED),
            (403, WordPressDraftFailureKind.AUTH_FAILED),
            (429, WordPressDraftFailureKind.HTTP_STATUS),
            (500, WordPressDraftFailureKind.HTTP_STATUS),
        ):
            calls = []

            def handler(request: httpx.Request, code=status) -> httpx.Response:
                calls.append(request)
                return httpx.Response(code, text=f"body {PASSWORD}")

            with self.subTest(status=status):
                result = await _publisher(handler).publish_draft(_request())
                self.assertEqual(result.failure_kind, expected)
                self.assertEqual(len(calls), 1)
                self.assertNotIn(PASSWORD, result.error or "")

    async def test_timeout_and_transport_failure_are_sanitized_and_not_retried(self) -> None:
        failures = (
            (
                httpx.ReadTimeout("request timed out"),
                WordPressDraftFailureKind.TIMEOUT,
            ),
            (
                httpx.ConnectError(f"could not connect with {PASSWORD}"),
                WordPressDraftFailureKind.REQUEST_FAILED,
            ),
        )
        for failure, expected in failures:
            calls = []

            def handler(request: httpx.Request, exc=failure) -> httpx.Response:
                calls.append(request)
                raise exc

            with self.subTest(expected=expected):
                result = await _publisher(handler).publish_draft(_request())
                self.assertEqual(result.failure_kind, expected)
                self.assertEqual(len(calls), 1)
                self.assertNotIn(PASSWORD, result.error or "")

    async def test_redirect_is_rejected_without_following(self) -> None:
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(302, headers={"Location": "https://evil.example/posts"})

        result = await _publisher(handler).publish_draft(_request())
        self.assertEqual(result.failure_kind, WordPressDraftFailureKind.REDIRECT_REJECTED)
        self.assertEqual(len(calls), 1)

    async def test_invalid_base_urls_are_rejected_before_http(self) -> None:
        urls = (
            "http://cms.example.com",
            "https://user:password@cms.example.com",
            "https://cms.example.com/bad path",
            "not-a-url",
        )
        for url in urls:
            calls = []

            def handler(request: httpx.Request) -> httpx.Response:
                calls.append(request)
                return _draft_response()

            with self.subTest(url=url):
                result = await _publisher(handler, base_url=url).publish_draft(_request())
                self.assertEqual(result.failure_kind, WordPressDraftFailureKind.INVALID_URL)
                self.assertEqual(calls, [])

    async def test_private_loopback_link_local_and_metadata_origins_are_denied(self) -> None:
        hosts = (
            "localhost",
            "127.0.0.1",
            "10.0.0.1",
            "192.168.1.1",
            "169.254.169.254",
            "[::1]",
            "[::ffff:8.8.8.8]",
            "metadata.google.internal",
        )
        for host in hosts:
            calls = []

            def handler(request: httpx.Request) -> httpx.Response:
                calls.append(request)
                return _draft_response()

            with self.subTest(host=host):
                result = await _publisher(
                    handler, base_url=f"https://{host}"
                ).publish_draft(_request())
                self.assertEqual(result.failure_kind, WordPressDraftFailureKind.ORIGIN_REJECTED)
                self.assertEqual(calls, [])

    async def test_production_resolver_policy_rejects_unsafe_addresses(self) -> None:
        unsafe_addresses = (
            "127.0.0.1",
            "::1",
            "10.0.0.1",
            "169.254.169.254",
            "::ffff:10.0.0.1",
            "64:ff9b::a9fe:a9fe",
            "fec0::1",
            "fec0::1234",
            "feff::1",
            "192.0.0.9",
            "192.88.99.1",
        )
        for address in unsafe_addresses:
            resolver = _FakeResolver((address,))
            transports = _TransportFactory(lambda _request: _draft_response())
            publisher = WordPressRestDraftPublisher(
                base_url=BASE_URL,
                username=USERNAME,
                application_password=PASSWORD,
                resolver=resolver,
                _transport_factory=transports,
            )

            with self.subTest(address=address):
                result = await publisher.publish_draft(_request())
                self.assertEqual(
                    result.failure_kind,
                    WordPressDraftFailureKind.ORIGIN_REJECTED,
                )
                self.assertEqual(transports.calls, [])

    async def test_production_resolver_policy_accepts_and_pins_public_address(self) -> None:
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return _draft_response()

        resolver = _FakeResolver(("93.184.216.34",))
        transports = _TransportFactory(handler)
        publisher = WordPressRestDraftPublisher(
            base_url=BASE_URL,
            username=USERNAME,
            application_password=PASSWORD,
            resolver=resolver,
            _transport_factory=transports,
        )

        result = await publisher.publish_draft(_request())

        self.assertEqual(result.status, WordPressDraftStatus.SUCCESS)
        self.assertEqual(resolver.calls, [("cms.example.com", 443)])
        self.assertEqual(
            transports.calls,
            [("cms.example.com", 443, "93.184.216.34")],
        )
        self.assertEqual(len(requests), 1)

    async def test_mixed_public_and_unsafe_dns_answer_rejects_entire_origin(self) -> None:
        resolver = _FakeResolver(("93.184.216.34", "169.254.169.254"))
        transports = _TransportFactory(lambda _request: _draft_response())
        publisher = WordPressRestDraftPublisher(
            base_url=BASE_URL,
            username=USERNAME,
            application_password=PASSWORD,
            resolver=resolver,
            _transport_factory=transports,
        )

        result = await publisher.publish_draft(_request())

        self.assertEqual(result.failure_kind, WordPressDraftFailureKind.ORIGIN_REJECTED)
        self.assertEqual(transports.calls, [])

    async def test_private_host_opt_in_allows_only_rfc1918_and_ipv6_ula(self) -> None:
        for address in (
            "10.0.0.1",
            "172.16.0.1",
            "192.168.1.1",
            "fc00::1",
            "fd00::1",
        ):
            resolver = _FakeResolver((address,))
            transports = _TransportFactory(lambda _request: _draft_response())
            publisher = WordPressRestDraftPublisher(
                base_url=BASE_URL,
                username=USERNAME,
                application_password=PASSWORD,
                allow_private_hosts=True,
                resolver=resolver,
                _transport_factory=transports,
            )

            with self.subTest(address=address):
                result = await publisher.publish_draft(_request())
                self.assertEqual(result.status, WordPressDraftStatus.SUCCESS)
                self.assertEqual(
                    transports.calls,
                    [("cms.example.com", 443, address)],
                )

    async def test_private_host_opt_in_keeps_unrelated_protections(self) -> None:
        unsafe_addresses = (
            "127.0.0.1",
            "::1",
            "169.254.169.254",
            "fe80::1",
            "::ffff:10.0.0.1",
            "64:ff9b::a9fe:a9fe",
            "fec0::1",
            "fec0::1234",
            "feff::1",
            "224.0.0.1",
            "ff02::1",
            "0.0.0.0",
            "::",
            "240.0.0.1",
            "192.0.0.9",
            "192.88.99.1",
            "100.64.0.1",
        )
        for address in unsafe_addresses:
            resolver = _FakeResolver((address,))
            transports = _TransportFactory(lambda _request: _draft_response())
            publisher = WordPressRestDraftPublisher(
                base_url=BASE_URL,
                username=USERNAME,
                application_password=PASSWORD,
                allow_private_hosts=True,
                resolver=resolver,
                _transport_factory=transports,
            )

            with self.subTest(address=address):
                result = await publisher.publish_draft(_request())
                self.assertEqual(
                    result.failure_kind,
                    WordPressDraftFailureKind.ORIGIN_REJECTED,
                )
                self.assertEqual(transports.calls, [])

    async def test_private_host_opt_in_still_rejects_localhost_alias(self) -> None:
        calls = []
        result = await _publisher(
            lambda request: calls.append(request) or _draft_response(),
            base_url="https://localhost",
            allow_private_hosts=True,
        ).publish_draft(_request())

        self.assertEqual(result.failure_kind, WordPressDraftFailureKind.ORIGIN_REJECTED)
        self.assertEqual(calls, [])

    async def test_missing_configuration_and_invalid_request_fail_before_http(self) -> None:
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return _draft_response()

        with patch.dict(os.environ, {}, clear=True):
            publisher = WordPressRestDraftPublisher(transport=httpx.MockTransport(handler))
            result = await publisher.publish_draft(_request())
        self.assertEqual(result.failure_kind, WordPressDraftFailureKind.INVALID_INPUT)
        invalid = await _publisher(handler).publish_draft(object())
        self.assertEqual(invalid.failure_kind, WordPressDraftFailureKind.INVALID_INPUT)
        self.assertEqual(calls, [])

    async def test_environment_fallback_works_without_exposing_credentials(self) -> None:
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return _draft_response()

        environment = {
            "WORDPRESS_BASE_URL": BASE_URL,
            "WORDPRESS_USERNAME": USERNAME,
            "WORDPRESS_APPLICATION_PASSWORD": PASSWORD,
        }
        with patch.dict(os.environ, environment, clear=True):
            publisher = WordPressRestDraftPublisher(transport=httpx.MockTransport(handler))
            representation = repr(publisher)
            result = await publisher.publish_draft(_request())
        self.assertEqual(result.status, WordPressDraftStatus.SUCCESS)
        self.assertNotIn(USERNAME, representation)
        self.assertNotIn(PASSWORD, representation)
        self.assertNotIn(PASSWORD, repr(result))
        self.assertEqual(len(calls), 1)

    def test_timeout_must_be_finite_positive_and_bounded(self) -> None:
        for timeout in (0, -1, float("inf"), float("nan"), 121, True):
            with self.subTest(timeout=timeout):
                with self.assertRaises(ValueError):
                    WordPressRestDraftPublisher(
                        base_url=BASE_URL,
                        username=USERNAME,
                        application_password=PASSWORD,
                        timeout=timeout,
                        transport=httpx.MockTransport(lambda request: _draft_response()),
                    )


if __name__ == "__main__":
    unittest.main()
