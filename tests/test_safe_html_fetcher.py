import asyncio
import gzip
import os
import socket
import ssl
import unittest
from unittest.mock import patch

import httpx

from foreign_trade_geo_agent.adapters.safe_http import SafeHtmlFetcher
from foreign_trade_geo_agent.core.fetching import (
    FetchFailureKind,
    FetchStatus,
    UrlOrigin,
)


PUBLIC_V4 = "93.184.216.34"
PUBLIC_V6 = "2606:4700:4700::1111"


class _FakeResolver:
    def __init__(self, *answers: tuple[str, ...] | Exception) -> None:
        self.answers = list(answers)
        self.calls: list[tuple[str, int]] = []

    async def resolve(self, host: str, port: int) -> tuple[str, ...]:
        self.calls.append((host, port))
        if not self.answers:
            raise AssertionError("Unexpected DNS resolution.")
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


class _TransportFactory:
    def __init__(self, handler) -> None:
        self.handler = handler
        self.calls: list[tuple[str, int, str]] = []

    def __call__(
        self,
        logical_host: str,
        logical_port: int,
        validated_ip: str,
    ) -> httpx.AsyncBaseTransport:
        self.calls.append((logical_host, logical_port, validated_ip))
        return httpx.MockTransport(self.handler)


class _TrackingStream(httpx.AsyncByteStream):
    def __init__(self, *chunks: bytes) -> None:
        self.chunks = chunks
        self.closed = False

    async def __aiter__(self):
        for chunk in self.chunks:
            yield chunk

    async def aclose(self) -> None:
        self.closed = True


class _SlowTrackingStream(_TrackingStream):
    async def __aiter__(self):
        await asyncio.sleep(0.1)
        async for chunk in super().__aiter__():
            yield chunk


def _html_response(
    body: bytes = b"<html><body>ok</body></html>",
    *,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    response_headers = {"Content-Type": "text/html; charset=utf-8"}
    if headers:
        response_headers.update(headers)
    return httpx.Response(200, stream=_TrackingStream(body), headers=response_headers)


class SafeHtmlFetcherPolicyTests(unittest.IsolatedAsyncioTestCase):
    async def test_accepts_public_ipv4_and_ipv6_answers(self) -> None:
        for address in (PUBLIC_V4, PUBLIC_V6):
            with self.subTest(address=address):
                resolver = _FakeResolver((address,))
                transports = _TransportFactory(lambda _request: _html_response())
                result = await SafeHtmlFetcher(
                    resolver=resolver,
                    _transport_factory=transports,
                ).fetch("https://example.com/page")

                self.assertEqual(result.status, FetchStatus.SUCCESS)
                self.assertEqual(result.connected_ip, address)
                self.assertEqual(
                    transports.calls,
                    [("example.com", 443, address)],
                )

    async def test_rejects_every_non_public_address_class_before_transport(self) -> None:
        unsafe_addresses = (
            "10.0.0.1",
            "127.0.0.1",
            "169.254.10.20",
            "240.0.0.1",
            "100.64.0.1",
            "169.254.169.254",
            "192.0.0.9",
            "198.18.0.1",
            "224.0.0.1",
            "::1",
            "fe80::1",
            "fc00::1",
            "ff02::1",
            "::ffff:8.8.8.8",
            "64:ff9b::a00:1",
            "64:ff9b:1::a00:1",
            "4000::1",
        )
        for address in unsafe_addresses:
            with self.subTest(address=address):
                resolver = _FakeResolver((address,))
                transports = _TransportFactory(lambda _request: _html_response())
                result = await SafeHtmlFetcher(
                    resolver=resolver,
                    _transport_factory=transports,
                ).fetch("https://example.com/")

                self.assertEqual(result.status, FetchStatus.FAILED)
                self.assertEqual(
                    result.failure_kind,
                    FetchFailureKind.SAFETY_POLICY_REJECTED,
                )
                self.assertEqual(transports.calls, [])

    async def test_rejects_mixed_public_and_private_dns_answer(self) -> None:
        resolver = _FakeResolver((PUBLIC_V4, "127.0.0.1"))
        transports = _TransportFactory(lambda _request: _html_response())

        result = await SafeHtmlFetcher(
            resolver=resolver,
            _transport_factory=transports,
        ).fetch("https://example.com/")

        self.assertEqual(result.failure_kind, FetchFailureKind.SAFETY_POLICY_REJECTED)
        self.assertEqual(transports.calls, [])

    async def test_rejects_non_http_and_credentialed_urls_without_dns(self) -> None:
        for url in (
            "ftp://example.com/file",
            "https://user@example.com/",
            "https://:secret@example.com/",
            "https://example.com:0/",
        ):
            with self.subTest(url=url):
                resolver = _FakeResolver()
                result = await SafeHtmlFetcher(resolver=resolver).fetch(url)
                self.assertEqual(result.failure_kind, FetchFailureKind.INVALID_URL)
                self.assertEqual(resolver.calls, [])

    async def test_rejects_initial_url_outside_expected_exact_origin(self) -> None:
        for url in (
            "https://shop.example.com/",
            "http://example.com/",
            "https://example.com:444/",
        ):
            with self.subTest(url=url):
                resolver = _FakeResolver()
                result = await SafeHtmlFetcher(resolver=resolver).fetch(
                    url,
                    expected_origin=UrlOrigin("https", "example.com", 443),
                )

                self.assertEqual(result.failure_kind, FetchFailureKind.ORIGIN_REJECTED)
                self.assertEqual(resolver.calls, [])

    async def test_dns_rebinding_is_rejected_before_second_connection(self) -> None:
        resolver = _FakeResolver((PUBLIC_V4,), ("127.0.0.1",))

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(302, headers={"Location": "/after-redirect"})

        transports = _TransportFactory(handler)
        result = await SafeHtmlFetcher(
            resolver=resolver,
            _transport_factory=transports,
        ).fetch("https://example.com/")

        self.assertEqual(result.failure_kind, FetchFailureKind.SAFETY_POLICY_REJECTED)
        self.assertEqual(len(transports.calls), 1)
        self.assertEqual(resolver.calls, [("example.com", 443), ("example.com", 443)])

    async def test_fake_resolver_never_falls_through_to_system_dns(self) -> None:
        resolver = _FakeResolver((PUBLIC_V4,))
        transports = _TransportFactory(lambda _request: _html_response())
        with patch("socket.getaddrinfo", side_effect=AssertionError("real DNS used")):
            result = await SafeHtmlFetcher(
                resolver=resolver,
                _transport_factory=transports,
            ).fetch("https://example.com/")

        self.assertEqual(result.status, FetchStatus.SUCCESS)

    async def test_unicode_and_punycode_hosts_share_idna2008_origin(self) -> None:
        for url in ("https://faß.de/", "https://xn--fa-hia.de/"):
            with self.subTest(url=url):
                resolver = _FakeResolver((PUBLIC_V4,))
                transports = _TransportFactory(lambda _request: _html_response())
                result = await SafeHtmlFetcher(
                    resolver=resolver,
                    _transport_factory=transports,
                ).fetch(
                    url,
                    expected_origin=UrlOrigin("https", "xn--fa-hia.de", 443),
                )

                self.assertEqual(result.status, FetchStatus.SUCCESS)
                self.assertEqual(result.final_url, "https://xn--fa-hia.de/")
                self.assertEqual(resolver.calls, [("xn--fa-hia.de", 443)])
                self.assertEqual(
                    transports.calls,
                    [("xn--fa-hia.de", 443, PUBLIC_V4)],
                )

    async def test_idna2008_host_does_not_collapse_to_a_different_ascii_host(self) -> None:
        resolver = _FakeResolver()
        result = await SafeHtmlFetcher(resolver=resolver).fetch(
            "https://fass.de/",
            expected_origin=UrlOrigin("https", "faß.de", 443),
        )

        self.assertEqual(result.failure_kind, FetchFailureKind.ORIGIN_REJECTED)
        self.assertEqual(resolver.calls, [])


class SafeHtmlFetcherResponseTests(unittest.IsolatedAsyncioTestCase):
    async def test_returns_bounded_html_and_preserves_logical_final_url(self) -> None:
        transports = _TransportFactory(
            lambda _request: _html_response(b"<html>customer</html>")
        )
        result = await SafeHtmlFetcher(
            resolver=_FakeResolver((PUBLIC_V4,)),
            _transport_factory=transports,
        ).fetch("https://example.com/start#fragment")

        self.assertEqual(result.status, FetchStatus.SUCCESS)
        self.assertEqual(result.final_url, "https://example.com/start")
        self.assertEqual(result.content, b"<html>customer</html>")
        self.assertEqual(result.content_type, "text/html")
        self.assertEqual(result.wire_bytes, len(result.content))
        self.assertEqual(result.decoded_bytes, len(result.content))

    async def test_accepts_xhtml(self) -> None:
        transports = _TransportFactory(
            lambda _request: httpx.Response(
                200,
                stream=_TrackingStream(b"<html/>"),
                headers={"Content-Type": "application/xhtml+xml"},
            )
        )
        result = await SafeHtmlFetcher(
            resolver=_FakeResolver((PUBLIC_V4,)),
            _transport_factory=transports,
        ).fetch("https://example.com/")

        self.assertEqual(result.status, FetchStatus.SUCCESS)

    async def test_follows_only_same_origin_redirects_and_revalidates_each_hop(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/start":
                return httpx.Response(302, headers={"Location": "/final"})
            return _html_response(b"<html>final</html>")

        resolver = _FakeResolver((PUBLIC_V4,), (PUBLIC_V4,))
        transports = _TransportFactory(handler)
        result = await SafeHtmlFetcher(
            resolver=resolver,
            _transport_factory=transports,
        ).fetch("https://example.com/start")

        self.assertEqual(result.status, FetchStatus.SUCCESS)
        self.assertEqual(result.final_url, "https://example.com/final")
        self.assertEqual(
            result.redirect_chain,
            ("https://example.com/start", "https://example.com/final"),
        )
        self.assertEqual(len(transports.calls), 2)

    async def test_rejects_cross_origin_redirect_before_dns(self) -> None:
        transports = _TransportFactory(
            lambda _request: httpx.Response(
                302,
                headers={"Location": "https://other.example/final"},
            )
        )
        resolver = _FakeResolver((PUBLIC_V4,))
        result = await SafeHtmlFetcher(
            resolver=resolver,
            _transport_factory=transports,
        ).fetch("https://example.com/start")

        self.assertEqual(result.failure_kind, FetchFailureKind.ORIGIN_REJECTED)
        self.assertEqual(len(resolver.calls), 1)

    async def test_malformed_redirect_location_is_a_bounded_failure(self) -> None:
        transports = _TransportFactory(
            lambda _request: httpx.Response(
                302,
                headers={"Location": "http://["},
            )
        )
        result = await SafeHtmlFetcher(
            resolver=_FakeResolver((PUBLIC_V4,)),
            _transport_factory=transports,
        ).fetch("https://example.com/start")

        self.assertEqual(result.failure_kind, FetchFailureKind.INVALID_URL)

    async def test_enforces_redirect_limit_without_automatic_redirects(self) -> None:
        transports = _TransportFactory(
            lambda _request: httpx.Response(302, headers={"Location": "/again"})
        )
        result = await SafeHtmlFetcher(
            resolver=_FakeResolver((PUBLIC_V4,), (PUBLIC_V4,)),
            max_redirects=1,
            _transport_factory=transports,
        ).fetch("https://example.com/start")

        self.assertEqual(result.failure_kind, FetchFailureKind.TOO_MANY_REDIRECTS)
        self.assertEqual(len(transports.calls), 2)

    async def test_rejects_non_html_without_consuming_or_leaking_response(self) -> None:
        stream = _TrackingStream(b"binary payload")
        transports = _TransportFactory(
            lambda _request: httpx.Response(
                200,
                headers={"Content-Type": "application/pdf"},
                stream=stream,
            )
        )
        result = await SafeHtmlFetcher(
            resolver=_FakeResolver((PUBLIC_V4,)),
            _transport_factory=transports,
        ).fetch("https://example.com/file")

        self.assertEqual(result.failure_kind, FetchFailureKind.NON_HTML)
        self.assertTrue(stream.closed)

    async def test_enforces_wire_limit_and_closes_stream(self) -> None:
        stream = _TrackingStream(b"x" * 60, b"y" * 60)
        transports = _TransportFactory(
            lambda _request: httpx.Response(
                200,
                headers={"Content-Type": "text/html"},
                stream=stream,
            )
        )
        result = await SafeHtmlFetcher(
            resolver=_FakeResolver((PUBLIC_V4,)),
            max_wire_bytes=100,
            max_decoded_bytes=1_000,
            _transport_factory=transports,
        ).fetch("https://example.com/")

        self.assertEqual(result.failure_kind, FetchFailureKind.RESOURCE_LIMIT_EXCEEDED)
        self.assertTrue(stream.closed)

    async def test_rejects_declared_oversize_body_and_closes_without_reading(self) -> None:
        stream = _TrackingStream(b"not read")
        transports = _TransportFactory(
            lambda _request: httpx.Response(
                200,
                headers={
                    "Content-Type": "text/html",
                    "Content-Length": "101",
                },
                stream=stream,
            )
        )
        result = await SafeHtmlFetcher(
            resolver=_FakeResolver((PUBLIC_V4,)),
            max_wire_bytes=100,
            _transport_factory=transports,
        ).fetch("https://example.com/")

        self.assertEqual(result.failure_kind, FetchFailureKind.RESOURCE_LIMIT_EXCEEDED)
        self.assertTrue(stream.closed)

    async def test_enforces_decompressed_limit_for_gzip(self) -> None:
        compressed = gzip.compress(b"<html>" + b"x" * 1_000 + b"</html>")
        transports = _TransportFactory(
            lambda _request: _html_response(
                compressed,
                headers={"Content-Encoding": "gzip"},
            )
        )
        result = await SafeHtmlFetcher(
            resolver=_FakeResolver((PUBLIC_V4,)),
            max_wire_bytes=1_000,
            max_decoded_bytes=100,
            _transport_factory=transports,
        ).fetch("https://example.com/")

        self.assertLess(len(compressed), 100)
        self.assertEqual(result.failure_kind, FetchFailureKind.RESOURCE_LIMIT_EXCEEDED)

    async def test_rejects_unsupported_content_encoding_and_closes_stream(self) -> None:
        stream = _TrackingStream(b"encoded")
        transports = _TransportFactory(
            lambda _request: httpx.Response(
                200,
                headers={
                    "Content-Type": "text/html",
                    "Content-Encoding": "br",
                },
                stream=stream,
            )
        )
        result = await SafeHtmlFetcher(
            resolver=_FakeResolver((PUBLIC_V4,)),
            _transport_factory=transports,
        ).fetch("https://example.com/")

        self.assertEqual(
            result.failure_kind,
            FetchFailureKind.UNSUPPORTED_CONTENT_ENCODING,
        )
        self.assertTrue(stream.closed)

    async def test_rejects_truncated_and_concatenated_gzip_streams(self) -> None:
        valid = gzip.compress(b"<html>one</html>")
        invalid_bodies = (
            valid[:-5],
            valid + gzip.compress(b"<html>two</html>"),
        )
        for body in invalid_bodies:
            with self.subTest(size=len(body)):
                transports = _TransportFactory(
                    lambda _request, body=body: _html_response(
                        body,
                        headers={"Content-Encoding": "gzip"},
                    )
                )
                result = await SafeHtmlFetcher(
                    resolver=_FakeResolver((PUBLIC_V4,)),
                    _transport_factory=transports,
                ).fetch("https://example.com/")

                self.assertEqual(result.failure_kind, FetchFailureKind.REQUEST_FAILED)

    async def test_timeout_is_bounded_and_classified(self) -> None:
        async def handler(_request: httpx.Request) -> httpx.Response:
            await asyncio.sleep(0.1)
            return _html_response()

        result = await SafeHtmlFetcher(
            resolver=_FakeResolver((PUBLIC_V4,)),
            timeout=0.01,
            _transport_factory=_TransportFactory(handler),
        ).fetch("https://example.com/")

        self.assertEqual(result.failure_kind, FetchFailureKind.TIMEOUT)

    async def test_read_timeout_closes_an_open_response(self) -> None:
        stream = _SlowTrackingStream(b"<html>late</html>")
        transports = _TransportFactory(
            lambda _request: httpx.Response(
                200,
                headers={"Content-Type": "text/html"},
                stream=stream,
            )
        )
        result = await SafeHtmlFetcher(
            resolver=_FakeResolver((PUBLIC_V4,)),
            timeout=0.01,
            _transport_factory=transports,
        ).fetch("https://example.com/")

        self.assertEqual(result.failure_kind, FetchFailureKind.TIMEOUT)
        self.assertTrue(stream.closed)

    async def test_tls_verification_failure_is_classified_without_ip_failover(self) -> None:
        calls: list[str] = []

        def factory(host: str, port: int, address: str) -> httpx.AsyncBaseTransport:
            calls.append(address)

            def handler(request: httpx.Request) -> httpx.Response:
                try:
                    raise ssl.SSLCertVerificationError(1, "wrong host")
                except ssl.SSLCertVerificationError as exc:
                    raise httpx.ConnectError("TLS failed", request=request) from exc

            return httpx.MockTransport(handler)

        result = await SafeHtmlFetcher(
            resolver=_FakeResolver((PUBLIC_V4, PUBLIC_V6)),
            max_ip_attempts=2,
            _transport_factory=factory,
        ).fetch("https://example.com/")

        self.assertEqual(
            result.failure_kind,
            FetchFailureKind.TLS_VERIFICATION_FAILED,
        )
        self.assertEqual(calls, [PUBLIC_V4])

    async def test_connection_failure_uses_only_validated_ip_failover_set(self) -> None:
        attempts: list[str] = []

        def factory(host: str, port: int, address: str) -> httpx.AsyncBaseTransport:
            attempts.append(address)

            def handler(request: httpx.Request) -> httpx.Response:
                if address == PUBLIC_V4:
                    raise httpx.ConnectError("failed", request=request)
                return _html_response()

            return httpx.MockTransport(handler)

        result = await SafeHtmlFetcher(
            resolver=_FakeResolver((PUBLIC_V4, PUBLIC_V6)),
            max_ip_attempts=2,
            _transport_factory=factory,
        ).fetch("https://example.com/")

        self.assertEqual(result.status, FetchStatus.SUCCESS)
        self.assertEqual(attempts, [PUBLIC_V4, PUBLIC_V6])
        self.assertEqual(result.connected_ip, PUBLIC_V6)

    async def test_connect_timeout_can_fail_over_to_second_validated_ip(self) -> None:
        attempts: list[str] = []

        def factory(host: str, port: int, address: str) -> httpx.AsyncBaseTransport:
            attempts.append(address)

            def handler(request: httpx.Request) -> httpx.Response:
                if address == PUBLIC_V4:
                    raise httpx.ConnectTimeout("timed out", request=request)
                return _html_response()

            return httpx.MockTransport(handler)

        result = await SafeHtmlFetcher(
            resolver=_FakeResolver((PUBLIC_V4, PUBLIC_V6)),
            max_ip_attempts=2,
            _transport_factory=factory,
        ).fetch("https://example.com/")

        self.assertEqual(result.status, FetchStatus.SUCCESS)
        self.assertEqual(attempts, [PUBLIC_V4, PUBLIC_V6])

    async def test_proxy_environment_variables_do_not_change_fetch_path(self) -> None:
        transports = _TransportFactory(lambda _request: _html_response())
        with patch.dict(
            os.environ,
            {
                "HTTP_PROXY": "http://127.0.0.1:1",
                "HTTPS_PROXY": "http://127.0.0.1:1",
                "ALL_PROXY": "http://127.0.0.1:1",
            },
        ):
            result = await SafeHtmlFetcher(
                resolver=_FakeResolver((PUBLIC_V4,)),
                _transport_factory=transports,
            ).fetch("https://example.com/")

        self.assertEqual(result.status, FetchStatus.SUCCESS)
        self.assertEqual(len(transports.calls), 1)

    async def test_no_real_network_is_used_with_injected_resolver_and_transport(self) -> None:
        transports = _TransportFactory(lambda _request: _html_response())
        with (
            patch("socket.getaddrinfo", side_effect=AssertionError("real DNS used")),
            patch.object(socket.socket, "connect", side_effect=AssertionError("network used")),
        ):
            result = await SafeHtmlFetcher(
                resolver=_FakeResolver((PUBLIC_V4,)),
                _transport_factory=transports,
            ).fetch("https://example.com/")

        self.assertEqual(result.status, FetchStatus.SUCCESS)


if __name__ == "__main__":
    unittest.main()
