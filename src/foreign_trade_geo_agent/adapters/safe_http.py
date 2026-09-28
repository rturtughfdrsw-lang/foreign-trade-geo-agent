"""SSRF-resistant HTTP transport and one-page HTML fetching."""

import asyncio
from collections.abc import Iterable
from dataclasses import dataclass
import ipaddress
import socket
import ssl
from typing import Callable
from urllib.parse import urljoin, urlsplit
import zlib

import anyio
import httpcore
import httpx

from foreign_trade_geo_agent.core.fetching import (
    FetchFailureKind,
    FetchStatus,
    FetchTimeoutKind,
    FetchTimeoutOrigin,
    HtmlFetchResult,
    TextFetchResult,
    UrlOrigin,
)
from foreign_trade_geo_agent.core.ports import HostResolver


_SUPPORTED_HTTPX_VERSION = "0.28.1"
_SUPPORTED_HTTPCORE_VERSION = "1.0.9"
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_HTML_MEDIA_TYPES = frozenset({"text/html", "application/xhtml+xml"})
_TEXT_MEDIA_TYPES = frozenset({"text/plain"})
_STREAM_CHUNK_BYTES = 64 * 1024
_DEFAULT_USER_AGENT = "ForeignTradeGeoAgent/0.1 SafeHtmlFetcher"
_DENIED_IP_NETWORKS = (
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.88.99.0/24"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("::ffff:0:0/96"),
    ipaddress.ip_network("64:ff9b::/96"),
    ipaddress.ip_network("64:ff9b:1::/48"),
)


class SystemHostResolver:
    """Resolve hostnames with the operating system resolver."""

    async def resolve(self, host: str, port: int) -> tuple[str, ...]:
        loop = asyncio.get_running_loop()
        records = await loop.getaddrinfo(
            host,
            port,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
        return tuple(record[4][0] for record in records)


class _PinnedNetworkBackend(httpcore.AsyncNetworkBackend):
    """Connect one logical origin to one previously validated IP address."""

    def __init__(
        self,
        *,
        logical_host: str,
        logical_port: int,
        validated_ip: str,
        delegate: httpcore.AsyncNetworkBackend | None = None,
    ) -> None:
        self._logical_host = logical_host.casefold()
        self._logical_port = logical_port
        self._validated_ip = validated_ip
        self._delegate = delegate or httpcore.AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        if host.casefold() != self._logical_host or port != self._logical_port:
            raise httpcore.ConnectError("Pinned transport received an unexpected origin.")
        stream = await self._delegate.connect_tcp(
            self._validated_ip,
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )
        return _CancellationSafeNetworkStream(stream)

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        raise httpcore.ConnectError("Unix sockets are not supported.")

    async def sleep(self, seconds: float) -> None:
        await self._delegate.sleep(seconds)


class _CancellationSafeNetworkStream(httpcore.AsyncNetworkStream):
    """Close a connected socket if TLS setup is cancelled by an outer timeout."""

    def __init__(self, delegate: httpcore.AsyncNetworkStream) -> None:
        self._delegate = delegate

    async def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        return await self._delegate.read(max_bytes, timeout)

    async def write(self, buffer: bytes, timeout: float | None = None) -> None:
        await self._delegate.write(buffer, timeout)

    async def aclose(self) -> None:
        await self._delegate.aclose()

    async def start_tls(
        self,
        ssl_context: ssl.SSLContext,
        server_hostname: str | None = None,
        timeout: float | None = None,
    ) -> httpcore.AsyncNetworkStream:
        try:
            upgraded = await self._delegate.start_tls(
                ssl_context,
                server_hostname,
                timeout,
            )
        except BaseException:
            with anyio.move_on_after(0.2, shield=True):
                await self._delegate.aclose()
            raise
        return _CancellationSafeNetworkStream(upgraded)

    def get_extra_info(self, info: str) -> object:
        return self._delegate.get_extra_info(info)


class _PinnedAsyncHTTPTransport(httpx.AsyncHTTPTransport):
    """HTTPX transport whose TCP backend receives only a validated IP.

    HTTPX/httpcore keep the request URL's original origin, so HTTP Host,
    HTTPS SNI, and TLS hostname verification continue to use the logical host.
    Only ``connect_tcp`` is redirected to the already validated address.

    This class intentionally depends on ``AsyncHTTPTransport._pool`` in the
    exact HTTPX/httpcore versions guarded below.  The public httpcore network
    backend API is used for the actual connection substitution.
    """

    def __init__(
        self,
        *,
        logical_host: str,
        logical_port: int,
        validated_ip: str,
        ssl_context: ssl.SSLContext | None = None,
        network_backend: httpcore.AsyncNetworkBackend | None = None,
    ) -> None:
        if (
            httpx.__version__ != _SUPPORTED_HTTPX_VERSION
            or httpcore.__version__ != _SUPPORTED_HTTPCORE_VERSION
        ):
            raise RuntimeError(
                "Pinned transport requires audited HTTPX/httpcore versions."
            )
        context = ssl_context or httpx.create_ssl_context(
            verify=True,
            trust_env=False,
        )
        if context.verify_mode != ssl.CERT_REQUIRED or not context.check_hostname:
            raise ValueError("Pinned HTTPS transport requires certificate verification.")

        super().__init__(
            verify=context,
            trust_env=False,
            http1=True,
            http2=False,
            limits=httpx.Limits(
                max_connections=1,
                max_keepalive_connections=0,
            ),
            proxy=None,
            retries=0,
        )
        backend = _PinnedNetworkBackend(
            logical_host=logical_host,
            logical_port=logical_port,
            validated_ip=validated_ip,
            delegate=network_backend,
        )
        self._pool = httpcore.AsyncConnectionPool(
            ssl_context=context,
            max_connections=1,
            max_keepalive_connections=0,
            http1=True,
            http2=False,
            retries=0,
            network_backend=backend,
        )


class _ResourceLimitExceeded(Exception):
    def __init__(self, dimension: str) -> None:
        self.dimension = dimension
        super().__init__(dimension)


class _UnsupportedContentEncoding(Exception):
    pass


class _DecodeFailed(Exception):
    pass


class _BoundedContentDecoder:
    def __init__(self, encoding: str, limit: int) -> None:
        self._encoding = encoding
        self._limit = limit
        self._size = 0
        self._first_chunk = True
        if encoding == "identity":
            self._decoder = None
        elif encoding == "gzip":
            self._decoder = zlib.decompressobj(zlib.MAX_WBITS | 16)
        elif encoding == "deflate":
            self._decoder = zlib.decompressobj()
        else:
            raise _UnsupportedContentEncoding

    @property
    def size(self) -> int:
        return self._size

    def decode(self, data: bytes) -> bytes:
        if self._decoder is None:
            self._add_size(len(data))
            return data
        try:
            output = self._decode_limited(data)
        except zlib.error as exc:
            if self._encoding != "deflate" or not self._first_chunk:
                raise _DecodeFailed from exc
            self._decoder = zlib.decompressobj(-zlib.MAX_WBITS)
            try:
                output = self._decode_limited(data)
            except zlib.error as raw_exc:
                raise _DecodeFailed from raw_exc
        finally:
            self._first_chunk = False
        return output

    def finish(self) -> bytes:
        if self._decoder is None:
            return b""
        remaining = self._limit - self._size
        try:
            output = self._decoder.flush(remaining + 1)
        except zlib.error as exc:
            raise _DecodeFailed from exc
        self._add_size(len(output))
        if not self._decoder.eof or self._decoder.unused_data:
            raise _DecodeFailed
        return output

    def _decode_limited(self, data: bytes) -> bytes:
        chunks: list[bytes] = []
        pending = data
        while pending:
            remaining = self._limit - self._size
            output = self._decoder.decompress(pending, remaining + 1)
            self._add_size(len(output))
            chunks.append(output)
            if self._decoder.unused_data:
                raise _DecodeFailed
            next_pending = self._decoder.unconsumed_tail
            if not next_pending or next_pending == pending:
                break
            pending = next_pending
        return b"".join(chunks)

    def _add_size(self, amount: int) -> None:
        self._size += amount
        if self._size > self._limit:
            raise _ResourceLimitExceeded("decoded")


@dataclass(slots=True)
class _AttemptResult:
    kind: str
    status_code: int | None = None
    content_type: str | None = None
    content: bytes | None = None
    location: str | None = None
    wire_bytes: int = 0
    decoded_bytes: int = 0
    failure_kind: FetchFailureKind | None = None
    error: str | None = None
    timeout_kind: FetchTimeoutKind | None = None
    timeout_origin: FetchTimeoutOrigin | None = None


@dataclass(frozen=True, slots=True)
class _ResolutionFailure:
    kind: FetchFailureKind
    error: str
    timeout_kind: FetchTimeoutKind | None = None


_TransportFactory = Callable[[str, int, str], httpx.AsyncBaseTransport]


class SafeHtmlFetcher:
    """Fetch one same-origin HTML resource using DNS-validated IP pinning."""

    def __init__(
        self,
        *,
        resolver: HostResolver | None = None,
        timeout: float = 15.0,
        max_redirects: int = 3,
        max_ip_attempts: int = 2,
        max_wire_bytes: int = 2 * 1024 * 1024,
        max_decoded_bytes: int = 4 * 1024 * 1024,
        user_agent: str = _DEFAULT_USER_AGENT,
        _transport_factory: _TransportFactory | None = None,
    ) -> None:
        if (
            timeout <= 0
            or max_redirects < 0
            or max_ip_attempts <= 0
            or max_wire_bytes <= 0
            or max_decoded_bytes <= 0
            or not user_agent.strip()
        ):
            raise ValueError("Safe HTML fetcher limits must be positive.")
        self._resolver = resolver or SystemHostResolver()
        self._timeout = timeout
        self._max_redirects = max_redirects
        self._max_ip_attempts = max_ip_attempts
        self._max_wire_bytes = max_wire_bytes
        self._max_decoded_bytes = max_decoded_bytes
        self._user_agent = user_agent.strip()
        self._transport_factory = _transport_factory or self._new_pinned_transport

    async def fetch(
        self,
        url: str,
        *,
        expected_origin: UrlOrigin | None = None,
        max_request_attempts: int | None = None,
        max_total_wire_bytes: int | None = None,
        max_total_decoded_bytes: int | None = None,
        redirect_policy: Callable[[str], bool] | None = None,
    ) -> HtmlFetchResult:
        return await self._fetch(
            url,
            expected_origin=expected_origin,
            max_request_attempts=max_request_attempts,
            max_total_wire_bytes=max_total_wire_bytes,
            max_total_decoded_bytes=max_total_decoded_bytes,
            redirect_policy=redirect_policy,
            accepted_media_types=_HTML_MEDIA_TYPES,
            accept_header="text/html, application/xhtml+xml",
            resource_name="HTML",
        )

    async def fetch_text(
        self,
        url: str,
        *,
        expected_origin: UrlOrigin | None = None,
        max_request_attempts: int | None = None,
        max_total_wire_bytes: int | None = None,
        max_total_decoded_bytes: int | None = None,
        redirect_policy: Callable[[str], bool] | None = None,
    ) -> TextFetchResult:
        """Fetch bounded plain text through the same pinned safety path."""

        return await self._fetch(
            url,
            expected_origin=expected_origin,
            max_request_attempts=max_request_attempts,
            max_total_wire_bytes=max_total_wire_bytes,
            max_total_decoded_bytes=max_total_decoded_bytes,
            redirect_policy=redirect_policy,
            accepted_media_types=_TEXT_MEDIA_TYPES,
            accept_header="text/plain",
            resource_name="Text",
        )

    async def _fetch(
        self,
        url: str,
        *,
        expected_origin: UrlOrigin | None,
        max_request_attempts: int | None,
        max_total_wire_bytes: int | None,
        max_total_decoded_bytes: int | None,
        redirect_policy: Callable[[str], bool] | None,
        accepted_media_types: frozenset[str],
        accept_header: str,
        resource_name: str,
    ) -> HtmlFetchResult:
        if (
            (max_request_attempts is not None and max_request_attempts <= 0)
            or (max_total_wire_bytes is not None and max_total_wire_bytes <= 0)
            or (max_total_decoded_bytes is not None and max_total_decoded_bytes <= 0)
        ):
            raise ValueError("Per-call request and byte limits must be positive.")
        requested_url = url if isinstance(url, str) else ""
        parsed = self._parse_url(url)
        if parsed is None:
            return self._failed(
                requested_url,
                requested_url,
                (),
                FetchFailureKind.INVALID_URL,
                "URL must be a valid HTTP(S) URL without credentials.",
            )
        current_url, origin = parsed
        required_origin = expected_origin or origin
        chain = [current_url]
        if origin != required_origin:
            return self._failed(
                requested_url,
                current_url,
                tuple(chain),
                FetchFailureKind.ORIGIN_REJECTED,
                "URL is outside the permitted exact origin.",
            )

        redirects = 0
        request_attempts = 0
        total_wire_bytes = 0
        total_decoded_bytes = 0
        while True:
            addresses_or_failure = await self._resolve_public_addresses(origin)
            if isinstance(addresses_or_failure, _ResolutionFailure):
                return self._failed(
                    requested_url,
                    current_url,
                    tuple(chain),
                    addresses_or_failure.kind,
                    addresses_or_failure.error,
                    wire_bytes=total_wire_bytes,
                    decoded_bytes=total_decoded_bytes,
                    request_attempts=request_attempts,
                    timeout_kind=addresses_or_failure.timeout_kind,
                )
            addresses = addresses_or_failure

            attempt: _AttemptResult | None = None
            connected_ip: str | None = None
            for address in addresses[: self._max_ip_attempts]:
                if (
                    max_request_attempts is not None
                    and request_attempts >= max_request_attempts
                ):
                    return self._failed(
                        requested_url,
                        current_url,
                        tuple(chain),
                        FetchFailureKind.REQUEST_BUDGET_EXCEEDED,
                        "HTTP request attempt budget was exhausted.",
                        wire_bytes=total_wire_bytes,
                        decoded_bytes=total_decoded_bytes,
                        request_attempts=request_attempts,
                        connected_ip=connected_ip,
                    )
                wire_limit = self._attempt_byte_limit(
                    max_total_wire_bytes,
                    total_wire_bytes,
                    self._max_wire_bytes,
                )
                if wire_limit is None:
                    return self._failed(
                        requested_url,
                        current_url,
                        tuple(chain),
                        FetchFailureKind.TOTAL_WIRE_BUDGET_EXCEEDED,
                        "Total wire byte budget was exhausted.",
                        wire_bytes=total_wire_bytes,
                        decoded_bytes=total_decoded_bytes,
                        request_attempts=request_attempts,
                    )
                decoded_limit = self._attempt_byte_limit(
                    max_total_decoded_bytes,
                    total_decoded_bytes,
                    self._max_decoded_bytes,
                )
                if decoded_limit is None:
                    return self._failed(
                        requested_url,
                        current_url,
                        tuple(chain),
                        FetchFailureKind.TOTAL_DECODED_BUDGET_EXCEEDED,
                        "Total decoded byte budget was exhausted.",
                        wire_bytes=total_wire_bytes,
                        decoded_bytes=total_decoded_bytes,
                        request_attempts=request_attempts,
                    )
                connected_ip = address
                request_attempts += 1
                attempt = await self._request_once(
                    current_url,
                    origin,
                    address,
                    accepted_media_types=accepted_media_types,
                    accept_header=accept_header,
                    resource_name=resource_name,
                    max_wire_bytes=wire_limit[0],
                    max_decoded_bytes=decoded_limit[0],
                    wire_budget_limited=wire_limit[1],
                    decoded_budget_limited=decoded_limit[1],
                )
                total_wire_bytes += attempt.wire_bytes
                total_decoded_bytes += attempt.decoded_bytes
                if attempt.kind != "connect_failure":
                    break
            assert attempt is not None

            if attempt.kind == "redirect":
                if redirects >= self._max_redirects:
                    return self._failed(
                        requested_url,
                        current_url,
                        tuple(chain),
                        FetchFailureKind.TOO_MANY_REDIRECTS,
                        "Redirect limit exceeded.",
                        http_status=attempt.status_code,
                        wire_bytes=total_wire_bytes,
                        decoded_bytes=total_decoded_bytes,
                        request_attempts=request_attempts,
                    )
                try:
                    redirect_url = urljoin(current_url, attempt.location or "")
                except ValueError:
                    return self._failed(
                        requested_url,
                        current_url,
                        tuple(chain),
                        FetchFailureKind.INVALID_URL,
                        "Redirect target is not a valid safe URL.",
                        http_status=attempt.status_code,
                        wire_bytes=total_wire_bytes,
                        decoded_bytes=total_decoded_bytes,
                        request_attempts=request_attempts,
                    )
                redirect_parsed = self._parse_url(redirect_url)
                if redirect_parsed is None:
                    return self._failed(
                        requested_url,
                        redirect_url,
                        tuple(chain),
                        FetchFailureKind.INVALID_URL,
                        "Redirect target is not a valid safe URL.",
                        http_status=attempt.status_code,
                        wire_bytes=total_wire_bytes,
                        decoded_bytes=total_decoded_bytes,
                        request_attempts=request_attempts,
                    )
                next_url, next_origin = redirect_parsed
                if next_origin != required_origin:
                    return self._failed(
                        requested_url,
                        next_url,
                        tuple(chain),
                        FetchFailureKind.ORIGIN_REJECTED,
                        "Redirect target is outside the permitted exact origin.",
                        http_status=attempt.status_code,
                        wire_bytes=total_wire_bytes,
                        decoded_bytes=total_decoded_bytes,
                        request_attempts=request_attempts,
                    )
                if redirect_policy is not None:
                    try:
                        redirect_allowed = redirect_policy(next_url)
                    except Exception:
                        redirect_allowed = False
                    if not redirect_allowed:
                        return self._failed(
                            requested_url,
                            next_url,
                            tuple(chain),
                            FetchFailureKind.REDIRECT_POLICY_REJECTED,
                            "Redirect target was rejected by the caller policy.",
                            http_status=attempt.status_code,
                            wire_bytes=total_wire_bytes,
                            decoded_bytes=total_decoded_bytes,
                            request_attempts=request_attempts,
                        )
                redirects += 1
                current_url = next_url
                origin = next_origin
                chain.append(current_url)
                continue

            if attempt.kind == "success":
                return HtmlFetchResult(
                    requested_url=requested_url,
                    final_url=current_url,
                    status=FetchStatus.SUCCESS,
                    http_status=attempt.status_code,
                    content_type=attempt.content_type,
                    content=attempt.content,
                    connected_ip=connected_ip,
                    wire_bytes=total_wire_bytes,
                    decoded_bytes=total_decoded_bytes,
                    request_attempts=request_attempts,
                    redirect_chain=tuple(chain),
                    failure_kind=None,
                    error=None,
                )

            return self._failed(
                requested_url,
                current_url,
                tuple(chain),
                attempt.failure_kind or FetchFailureKind.REQUEST_FAILED,
                attempt.error or f"{resource_name} request failed.",
                http_status=attempt.status_code,
                content_type=attempt.content_type,
                wire_bytes=total_wire_bytes,
                decoded_bytes=total_decoded_bytes,
                request_attempts=request_attempts,
                connected_ip=connected_ip,
                timeout_kind=attempt.timeout_kind,
                timeout_origin=attempt.timeout_origin,
            )

    async def _resolve_public_addresses(
        self,
        origin: UrlOrigin,
    ) -> tuple[str, ...] | _ResolutionFailure:
        try:
            literal = ipaddress.ip_address(origin.host)
        except ValueError:
            try:
                async with asyncio.timeout(self._timeout):
                    raw_addresses = await self._resolver.resolve(origin.host, origin.port)
            except TimeoutError:
                return _ResolutionFailure(
                    FetchFailureKind.TIMEOUT,
                    "DNS resolution timed out.",
                    FetchTimeoutKind.DNS_TIMEOUT,
                )
            except (OSError, socket.gaierror):
                return _ResolutionFailure(
                    FetchFailureKind.DNS_FAILED,
                    "DNS resolution failed.",
                )
        else:
            raw_addresses = (literal.compressed,)

        if not raw_addresses:
            return _ResolutionFailure(
                FetchFailureKind.DNS_FAILED,
                "DNS resolution returned no addresses.",
            )

        addresses: list[str] = []
        for raw_address in raw_addresses:
            try:
                address = ipaddress.ip_address(raw_address)
            except ValueError:
                return _ResolutionFailure(
                    FetchFailureKind.DNS_FAILED,
                    "DNS resolution returned an invalid address.",
                )
            explicitly_denied = any(address in network for network in _DENIED_IP_NETWORKS)
            if (
                explicitly_denied
                or address.is_multicast
                or address.is_reserved
                or not address.is_global
                or (
                isinstance(address, ipaddress.IPv6Address)
                and address.ipv4_mapped is not None
                )
            ):
                return _ResolutionFailure(
                    FetchFailureKind.SAFETY_POLICY_REJECTED,
                    "DNS resolution included a non-public address.",
                )
            normalized = address.compressed
            if normalized not in addresses:
                addresses.append(normalized)
        return tuple(addresses)

    async def _request_once(
        self,
        url: str,
        origin: UrlOrigin,
        address: str,
        *,
        accepted_media_types: frozenset[str],
        accept_header: str,
        resource_name: str,
        max_wire_bytes: int,
        max_decoded_bytes: int,
        wire_budget_limited: bool,
        decoded_budget_limited: bool,
    ) -> _AttemptResult:
        transport = self._transport_factory(origin.host, origin.port, address)
        wire_bytes = 0
        decoder: _BoundedContentDecoder | None = None
        timeout_cm = asyncio.timeout(self._timeout)
        try:
            async with timeout_cm:
                async with httpx.AsyncClient(
                    transport=transport,
                    trust_env=False,
                    follow_redirects=False,
                    timeout=httpx.Timeout(self._timeout),
                    headers={
                        "Accept": accept_header,
                        "Accept-Encoding": "gzip, deflate",
                        "User-Agent": self._user_agent,
                    },
                ) as client:
                    async with client.stream("GET", url) as response:
                        media_type = response.headers.get("content-type", "").split(";", 1)[0].strip().casefold()
                        content_length = response.headers.get("content-length")
                        if content_length is not None:
                            try:
                                if int(content_length) > max_wire_bytes:
                                    return _AttemptResult(
                                        kind="failure",
                                        status_code=response.status_code,
                                        content_type=media_type or None,
                                        failure_kind=(
                                            FetchFailureKind.TOTAL_WIRE_BUDGET_EXCEEDED
                                            if wire_budget_limited
                                            else FetchFailureKind.RESOURCE_LIMIT_EXCEEDED
                                        ),
                                        error=f"{resource_name} response exceeded the configured byte limit.",
                                    )
                            except ValueError:
                                pass

                        encoding = response.headers.get("content-encoding", "identity").strip().casefold()
                        try:
                            decoder = _BoundedContentDecoder(
                                encoding or "identity",
                                max_decoded_bytes,
                            )
                        except _UnsupportedContentEncoding:
                            return _AttemptResult(
                                kind="failure",
                                status_code=response.status_code,
                                content_type=media_type,
                                failure_kind=FetchFailureKind.UNSUPPORTED_CONTENT_ENCODING,
                                error="Response content encoding is not supported.",
                            )
                        chunks: list[bytes] = []

                        def consume_raw_chunk(raw_chunk: bytes) -> None:
                            nonlocal wire_bytes
                            wire_bytes += len(raw_chunk)
                            if wire_bytes > max_wire_bytes:
                                raise _ResourceLimitExceeded("wire")
                            decoded_chunk = decoder.decode(raw_chunk)
                            if decoded_chunk:
                                chunks.append(decoded_chunk)

                        try:
                            if response.is_stream_consumed:
                                consume_raw_chunk(response.content)
                            else:
                                async for raw_chunk in response.aiter_raw(
                                    chunk_size=_STREAM_CHUNK_BYTES
                                ):
                                    consume_raw_chunk(raw_chunk)
                            final_chunk = decoder.finish()
                            if final_chunk:
                                chunks.append(final_chunk)
                        except _ResourceLimitExceeded as exc:
                            if exc.dimension == "wire" and wire_budget_limited:
                                failure_kind = FetchFailureKind.TOTAL_WIRE_BUDGET_EXCEEDED
                            elif exc.dimension == "decoded" and decoded_budget_limited:
                                failure_kind = FetchFailureKind.TOTAL_DECODED_BUDGET_EXCEEDED
                            else:
                                failure_kind = FetchFailureKind.RESOURCE_LIMIT_EXCEEDED
                            return _AttemptResult(
                                kind="failure",
                                status_code=response.status_code,
                                content_type=media_type,
                                wire_bytes=wire_bytes,
                                decoded_bytes=decoder.size,
                                failure_kind=failure_kind,
                                error=f"{resource_name} response exceeded the configured byte limit.",
                            )
                        except _UnsupportedContentEncoding:
                            return _AttemptResult(
                                kind="failure",
                                status_code=response.status_code,
                                content_type=media_type,
                                failure_kind=FetchFailureKind.UNSUPPORTED_CONTENT_ENCODING,
                                error="Response content encoding is not supported.",
                            )
                        except (_DecodeFailed, httpx.DecodingError):
                            return _AttemptResult(
                                kind="failure",
                                status_code=response.status_code,
                                content_type=media_type,
                                wire_bytes=wire_bytes,
                                decoded_bytes=decoder.size,
                                failure_kind=FetchFailureKind.REQUEST_FAILED,
                                error="Response content could not be decoded safely.",
                            )
                        common = {
                            "status_code": response.status_code,
                            "content_type": media_type or None,
                            "wire_bytes": wire_bytes,
                            "decoded_bytes": decoder.size,
                        }
                        if response.status_code in _REDIRECT_STATUSES:
                            location = response.headers.get("location")
                            if not location:
                                return _AttemptResult(
                                    kind="failure",
                                    failure_kind=FetchFailureKind.REQUEST_FAILED,
                                    error="Redirect response did not include Location.",
                                    **common,
                                )
                            return _AttemptResult(
                                kind="redirect",
                                location=location,
                                **common,
                            )
                        if not response.is_success:
                            return _AttemptResult(
                                kind="failure",
                                failure_kind=FetchFailureKind.HTTP_STATUS,
                                error=f"{resource_name} request returned HTTP {response.status_code}.",
                                **common,
                            )
                        if media_type not in accepted_media_types:
                            return _AttemptResult(
                                kind="failure",
                                failure_kind=FetchFailureKind.NON_HTML,
                                error=f"Response is not an accepted {resource_name.lower()} resource.",
                                **common,
                            )
                        return _AttemptResult(
                            kind="success",
                            content=b"".join(chunks),
                            **common,
                        )
        except httpx.ConnectTimeout:
            return _AttemptResult(
                kind="connect_failure",
                wire_bytes=wire_bytes,
                decoded_bytes=decoder.size if decoder is not None else 0,
                failure_kind=FetchFailureKind.TIMEOUT,
                error=f"{resource_name} connection timed out.",
                timeout_kind=FetchTimeoutKind.CONNECT_TIMEOUT,
            )
        except httpx.TimeoutException:
            return _AttemptResult(
                kind="failure",
                wire_bytes=wire_bytes,
                decoded_bytes=decoder.size if decoder is not None else 0,
                failure_kind=FetchFailureKind.TIMEOUT,
                error=f"{resource_name} request timed out.",
                timeout_kind=FetchTimeoutKind.REQUEST_TIMEOUT,
            )
        except TimeoutError:
            return _AttemptResult(
                kind="failure",
                wire_bytes=wire_bytes,
                decoded_bytes=decoder.size if decoder is not None else 0,
                failure_kind=FetchFailureKind.TIMEOUT,
                error=f"{resource_name} request timed out.",
                timeout_kind=FetchTimeoutKind.TIMEOUT,
                timeout_origin=(
                    FetchTimeoutOrigin.FETCHER_HARD_DEADLINE
                    if timeout_cm.expired()
                    else None
                ),
            )
        except httpx.ConnectError as exc:
            if self._is_certificate_error(exc):
                return _AttemptResult(
                    kind="failure",
                    wire_bytes=wire_bytes,
                    decoded_bytes=decoder.size if decoder is not None else 0,
                    failure_kind=FetchFailureKind.TLS_VERIFICATION_FAILED,
                    error="TLS certificate verification failed.",
                )
            return _AttemptResult(
                kind="connect_failure",
                wire_bytes=wire_bytes,
                decoded_bytes=decoder.size if decoder is not None else 0,
                failure_kind=FetchFailureKind.REQUEST_FAILED,
                error=f"{resource_name} connection failed.",
            )
        except httpx.RequestError:
            return _AttemptResult(
                kind="failure",
                wire_bytes=wire_bytes,
                decoded_bytes=decoder.size if decoder is not None else 0,
                failure_kind=FetchFailureKind.REQUEST_FAILED,
                error=f"{resource_name} request failed.",
            )

    @staticmethod
    def _attempt_byte_limit(
        total_limit: int | None,
        consumed: int,
        response_limit: int,
    ) -> tuple[int, bool] | None:
        if total_limit is None:
            return response_limit, False
        remaining = total_limit - consumed
        # A raw iterator chunk is counted before an over-limit response can be
        # aborted. Reserve one maximum chunk so even that observed chunk stays
        # inside the caller's whole-fetch hard limit.
        if remaining <= _STREAM_CHUNK_BYTES:
            return None
        available = remaining - _STREAM_CHUNK_BYTES
        return min(response_limit, available), available < response_limit

    @staticmethod
    def _is_certificate_error(exc: BaseException) -> bool:
        current: BaseException | None = exc
        visited: set[int] = set()
        while current is not None and id(current) not in visited:
            if isinstance(current, ssl.SSLCertVerificationError):
                return True
            visited.add(id(current))
            current = current.__cause__ or current.__context__
        return False

    @staticmethod
    def _parse_url(value: object) -> tuple[str, UrlOrigin] | None:
        if type(value) is not str or not value or len(value) > 2_048:
            return None
        if any(character.isspace() for character in value) or "\\" in value:
            return None
        try:
            split = urlsplit(value)
            _ = split.port
            parsed = httpx.URL(value)
        except (ValueError, httpx.InvalidURL):
            return None
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.host
            or split.username is not None
            or split.password is not None
        ):
            return None
        try:
            origin_port = (
                parsed.port
                if parsed.port is not None
                else 443 if parsed.scheme == "https" else 80
            )
            origin = UrlOrigin(
                parsed.scheme,
                parsed.raw_host.decode("ascii"),
                origin_port,
            )
        except (UnicodeDecodeError, ValueError):
            return None
        normalized = parsed.copy_with(host=origin.host, fragment=None)
        return str(normalized), origin

    @staticmethod
    def _new_pinned_transport(
        logical_host: str,
        logical_port: int,
        validated_ip: str,
    ) -> httpx.AsyncBaseTransport:
        return _PinnedAsyncHTTPTransport(
            logical_host=logical_host,
            logical_port=logical_port,
            validated_ip=validated_ip,
        )

    @staticmethod
    def _failed(
        requested_url: str,
        final_url: str,
        redirect_chain: tuple[str, ...],
        failure_kind: FetchFailureKind,
        error: str,
        *,
        http_status: int | None = None,
        content_type: str | None = None,
        wire_bytes: int = 0,
        decoded_bytes: int = 0,
        request_attempts: int = 0,
        connected_ip: str | None = None,
        timeout_kind: FetchTimeoutKind | None = None,
        timeout_origin: FetchTimeoutOrigin | None = None,
    ) -> HtmlFetchResult:
        return HtmlFetchResult(
            requested_url=requested_url,
            final_url=final_url,
            status=FetchStatus.FAILED,
            http_status=http_status,
            content_type=content_type,
            content=None,
            connected_ip=connected_ip,
            wire_bytes=wire_bytes,
            decoded_bytes=decoded_bytes,
            request_attempts=request_attempts,
            redirect_chain=redirect_chain,
            failure_kind=failure_kind,
            error=error,
            timeout_kind=timeout_kind,
            timeout_origin=timeout_origin,
        )
