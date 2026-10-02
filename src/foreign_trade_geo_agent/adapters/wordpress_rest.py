"""WordPress REST adapter that creates drafts only."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import ipaddress
import json
import math
import os
import socket
from typing import Callable
from urllib.parse import urlsplit

import httpx

from foreign_trade_geo_agent.adapters.safe_http import (
    SystemHostResolver,
    _PinnedAsyncHTTPTransport,
    ip_address_is_permitted,
)
from foreign_trade_geo_agent.core.ports import HostResolver
from foreign_trade_geo_agent.core.history import site_key_from_url
from foreign_trade_geo_agent.core.wordpress_draft import (
    WordPressDraftFailureKind,
    WordPressDraftRequest,
    WordPressDraftResult,
    WordPressDraftRemoteOutcome,
    normalize_wordpress_https_url,
)
from foreign_trade_geo_agent.core.wordpress_verification import (
    WordPressDraftReadOutcome,
    WordPressDraftReadRequest,
    WordPressDraftReadResult,
    WordPressVerificationFailureKind,
)


_DEFAULT_TIMEOUT_SECONDS = 30.0
_MAX_TIMEOUT_SECONDS = 120.0
_MAX_READ_RESPONSE_BYTES = 256 * 1024
_REDIRECT_STATUSES = frozenset(range(300, 400))
_DENIED_HOSTNAMES = frozenset({"localhost", "metadata", "metadata.google.internal"})
_TransportFactory = Callable[[str, int, str], httpx.AsyncBaseTransport]
_PUBLISHER_FAILURE_KINDS = {
    "timeout": WordPressDraftFailureKind.TIMEOUT,
    "request_failed": WordPressDraftFailureKind.REQUEST_FAILED,
    "origin_rejected": WordPressDraftFailureKind.ORIGIN_REJECTED,
}
_READER_FAILURE_KINDS = {
    "timeout": WordPressVerificationFailureKind.TIMEOUT,
    "request_failed": WordPressVerificationFailureKind.REQUEST_FAILED,
    "origin_rejected": WordPressVerificationFailureKind.REQUEST_FAILED,
}


@dataclass(frozen=True, slots=True)
class _TransportFailure:
    kind: str
    message: str


async def _resolve_pinned_transport(
    *,
    host: str,
    port: int,
    timeout: float,
    resolver: HostResolver,
    allow_private_hosts: bool,
    transport_factory: _TransportFactory,
) -> tuple[httpx.AsyncBaseTransport | None, _TransportFailure | None]:
    """Resolve, validate, and pin one origin before any credentialed request."""

    try:
        try:
            literal = ipaddress.ip_address(host)
        except ValueError:
            async with asyncio.timeout(timeout):
                raw_addresses = await resolver.resolve(host, port)
        else:
            raw_addresses = (literal.compressed,)
    except TimeoutError:
        return None, _TransportFailure("timeout", "WordPress origin resolution timed out.")
    except (OSError, socket.gaierror):
        return None, _TransportFailure(
            "request_failed",
            "WordPress origin resolution failed.",
        )

    addresses: list[str] = []
    for raw_address in raw_addresses:
        try:
            address = ipaddress.ip_address(raw_address)
        except ValueError:
            return None, _TransportFailure(
                "request_failed",
                "WordPress origin resolution failed.",
            )
        if not ip_address_is_permitted(
            address,
            allow_private=allow_private_hosts,
        ):
            return None, _TransportFailure(
                "origin_rejected",
                "WordPress origin is not permitted.",
            )
        if address.compressed not in addresses:
            addresses.append(address.compressed)
    if not addresses:
        return None, _TransportFailure(
            "request_failed",
            "WordPress origin resolution failed.",
        )
    return transport_factory(host, port, addresses[0]), None


class WordPressRestDraftPublisher:
    """Create WordPress posts while hard-coding draft status."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        username: str | None = None,
        application_password: str | None = None,
        timeout: float = _DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,
        allow_private_hosts: bool = False,
        resolver: HostResolver | None = None,
        _transport_factory: _TransportFactory | None = None,
    ) -> None:
        if (
            type(timeout) not in {int, float}
            or not math.isfinite(timeout)
            or not 0 < timeout <= _MAX_TIMEOUT_SECONDS
        ):
            raise ValueError("timeout must be finite, positive, and bounded.")
        if type(allow_private_hosts) is not bool:
            raise ValueError("allow_private_hosts must be a boolean.")

        raw_base_url = _configuration_value(base_url, "WORDPRESS_BASE_URL")
        self._username = _configuration_value(username, "WORDPRESS_USERNAME")
        self._application_password = _configuration_value(
            application_password,
            "WORDPRESS_APPLICATION_PASSWORD",
        )
        self._timeout = float(timeout)
        self._transport = transport
        self._allow_private_hosts = allow_private_hosts
        self._resolver = resolver or SystemHostResolver()
        self._transport_factory = _transport_factory or self._new_pinned_transport
        self._base_url: str | None = None
        self._host: str | None = None
        self._port: int | None = None
        self._configuration_failure: tuple[WordPressDraftFailureKind, str] | None = None

        if not raw_base_url or not self._username or not self._application_password:
            self._configuration_failure = (
                WordPressDraftFailureKind.INVALID_INPUT,
                "WordPress configuration is incomplete.",
            )
            return
        normalized = normalize_wordpress_https_url(raw_base_url)
        if normalized is None or not _is_origin_base_url(raw_base_url):
            self._configuration_failure = (
                WordPressDraftFailureKind.INVALID_URL,
                "WordPress base URL is invalid.",
            )
            return
        split = urlsplit(normalized)
        assert split.hostname is not None
        self._host = split.hostname
        self._port = split.port or 443
        self._base_url = f"https://{split.netloc}"
        if _host_is_statically_denied(
            self._host,
            allow_private_hosts=allow_private_hosts,
        ):
            self._configuration_failure = (
                WordPressDraftFailureKind.ORIGIN_REJECTED,
                "WordPress origin is not permitted.",
            )

    def __repr__(self) -> str:
        configured = self._configuration_failure is None
        return (
            f"{type(self).__name__}(configured={configured}, "
            f"timeout={self._timeout!r}, allow_private_hosts={self._allow_private_hosts!r})"
        )

    async def publish_draft(
        self,
        request: WordPressDraftRequest,
    ) -> WordPressDraftResult:
        if not isinstance(request, WordPressDraftRequest):
            return self._failed(
                WordPressDraftFailureKind.INVALID_INPUT,
                "WordPress draft request is invalid.",
            )
        if self._configuration_failure is not None:
            return self._failed(*self._configuration_failure)

        transport, transport_failure = await self._request_transport()
        if transport_failure is not None:
            return transport_failure
        assert self._base_url is not None
        assert self._username is not None
        assert self._application_password is not None

        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                auth=httpx.BasicAuth(self._username, self._application_password),
                timeout=httpx.Timeout(self._timeout),
                transport=transport,
                trust_env=False,
                follow_redirects=False,
            ) as client:
                response = await client.post(
                    "/wp-json/wp/v2/posts",
                    json={
                        "title": request.title,
                        "content": request.content,
                        "status": "draft",
                    },
                )
        except httpx.TimeoutException:
            # WordPress has no generic idempotency key for this operation. A
            # timed-out create is never retried; future storage owns duplicate
            # mitigation and persistence of a returned remote post ID.
            return self._failed(
                WordPressDraftFailureKind.TIMEOUT,
                "WordPress request timed out.",
                outcome=WordPressDraftRemoteOutcome.UNKNOWN,
            )
        except httpx.RequestError as exc:
            return self._failed(
                WordPressDraftFailureKind.REQUEST_FAILED,
                f"WordPress request failed ({type(exc).__name__}).",
                outcome=WordPressDraftRemoteOutcome.UNKNOWN,
            )

        failure = self._response_status_failure(response)
        if failure is not None:
            return failure
        payload = _json_object(response)
        if payload is None or type(payload.get("status")) is not str:
            return self._failed(
                WordPressDraftFailureKind.MALFORMED_RESPONSE,
                "WordPress API returned a malformed response.",
                outcome=WordPressDraftRemoteOutcome.UNKNOWN,
            )
        if payload["status"] != "draft":
            return self._failed(
                WordPressDraftFailureKind.RESPONSE_NOT_DRAFT,
                "WordPress response did not confirm draft status.",
                outcome=WordPressDraftRemoteOutcome.UNKNOWN,
            )
        remote_post_id = payload.get("id")
        remote_link = payload.get("link")
        normalized_link = normalize_wordpress_https_url(remote_link)
        if (
            type(remote_post_id) is not int
            or remote_post_id <= 0
            or normalized_link is None
        ):
            return self._failed(
                WordPressDraftFailureKind.MALFORMED_RESPONSE,
                "WordPress API returned a malformed response.",
                outcome=WordPressDraftRemoteOutcome.UNKNOWN,
            )
        return WordPressDraftResult(
            outcome=WordPressDraftRemoteOutcome.SUCCESS,
            remote_post_id=remote_post_id,
            remote_link=normalized_link,
            created=True,
            failure_kind=None,
            error=None,
        )

    async def _request_transport(
        self,
    ) -> tuple[httpx.AsyncBaseTransport | None, WordPressDraftResult | None]:
        if self._transport is not None:
            return self._transport, None
        assert self._host is not None
        assert self._port is not None
        transport, failure = await _resolve_pinned_transport(
            host=self._host,
            port=self._port,
            timeout=self._timeout,
            resolver=self._resolver,
            allow_private_hosts=self._allow_private_hosts,
            transport_factory=self._transport_factory,
        )
        if failure is not None:
            return None, self._failed(
                _PUBLISHER_FAILURE_KINDS[failure.kind],
                failure.message,
            )
        return transport, None

    def _response_status_failure(
        self,
        response: httpx.Response,
    ) -> WordPressDraftResult | None:
        if response.status_code in _REDIRECT_STATUSES:
            return self._failed(
                WordPressDraftFailureKind.REDIRECT_REJECTED,
                "WordPress redirect response was rejected.",
                outcome=WordPressDraftRemoteOutcome.UNKNOWN,
            )
        if response.status_code in {401, 403}:
            return self._failed(
                WordPressDraftFailureKind.AUTH_FAILED,
                "WordPress authentication was rejected.",
            )
        if not response.is_success:
            definite = 400 <= response.status_code < 500 and response.status_code not in {408, 425, 429}
            return self._failed(
                WordPressDraftFailureKind.HTTP_STATUS,
                f"WordPress API returned HTTP {response.status_code}.",
                outcome=(
                    WordPressDraftRemoteOutcome.FAILED_DEFINITELY
                    if definite
                    else WordPressDraftRemoteOutcome.UNKNOWN
                ),
            )
        return None

    @staticmethod
    def _failed(
        failure_kind: WordPressDraftFailureKind,
        error: str,
        *,
        outcome: WordPressDraftRemoteOutcome = WordPressDraftRemoteOutcome.FAILED_DEFINITELY,
    ) -> WordPressDraftResult:
        return WordPressDraftResult(
            outcome=outcome,
            remote_post_id=None,
            remote_link=None,
            created=False,
            failure_kind=failure_kind,
            error=error,
        )

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


class WordPressRestDraftReader:
    """Read one WordPress draft by ID without creating or modifying anything."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        username: str | None = None,
        application_password: str | None = None,
        timeout: float = _DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,
        allow_private_hosts: bool = False,
        resolver: HostResolver | None = None,
        _transport_factory: _TransportFactory | None = None,
    ) -> None:
        if (
            type(timeout) not in {int, float}
            or not math.isfinite(timeout)
            or not 0 < timeout <= _MAX_TIMEOUT_SECONDS
        ):
            raise ValueError("timeout must be finite, positive, and bounded.")
        if type(allow_private_hosts) is not bool:
            raise ValueError("allow_private_hosts must be a boolean.")

        raw_base_url = _configuration_value(base_url, "WORDPRESS_BASE_URL")
        self._username = _configuration_value(username, "WORDPRESS_USERNAME")
        self._application_password = _configuration_value(
            application_password,
            "WORDPRESS_APPLICATION_PASSWORD",
        )
        self._timeout = float(timeout)
        self._transport = transport
        self._allow_private_hosts = allow_private_hosts
        self._resolver = resolver or SystemHostResolver()
        self._transport_factory = _transport_factory or self._new_pinned_transport
        self._base_url: str | None = None
        self._host: str | None = None
        self._port: int | None = None
        self._target_site_key = ""
        self._configuration_failure: tuple[WordPressVerificationFailureKind, str] | None = None

        if not raw_base_url or not self._username or not self._application_password:
            self._configuration_failure = (
                WordPressVerificationFailureKind.REQUEST_FAILED,
                "WordPress read configuration is incomplete.",
            )
            return
        normalized = normalize_wordpress_https_url(raw_base_url)
        if normalized is None or not _is_origin_base_url(raw_base_url):
            self._configuration_failure = (
                WordPressVerificationFailureKind.REQUEST_FAILED,
                "WordPress base URL is invalid.",
            )
            return
        split = urlsplit(normalized)
        assert split.hostname is not None
        self._host = split.hostname
        self._port = split.port or 443
        self._base_url = f"https://{split.netloc}"
        self._target_site_key = site_key_from_url(self._base_url)
        if _host_is_statically_denied(
            self._host,
            allow_private_hosts=allow_private_hosts,
        ):
            self._configuration_failure = (
                WordPressVerificationFailureKind.REQUEST_FAILED,
                "WordPress origin is not permitted.",
            )

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(configured="
            f"{self._configuration_failure is None}, timeout={self._timeout!r})"
        )

    @property
    def target_site_key(self) -> str:
        return self._target_site_key

    async def read_draft(
        self,
        request: WordPressDraftReadRequest,
    ) -> WordPressDraftReadResult:
        if not isinstance(request, WordPressDraftReadRequest):
            return self._failed(
                WordPressVerificationFailureKind.REQUEST_FAILED,
                "WordPress draft read request is invalid.",
            )
        if self._configuration_failure is not None:
            return self._failed(*self._configuration_failure)

        transport, failure = await self._request_transport()
        if failure is not None:
            return self._failed(*failure)
        assert self._base_url is not None
        assert self._username is not None
        assert self._application_password is not None

        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                auth=httpx.BasicAuth(self._username, self._application_password),
                timeout=httpx.Timeout(self._timeout),
                transport=transport,
                trust_env=False,
                follow_redirects=False,
            ) as client:
                async with client.stream(
                    "GET",
                    f"/wp-json/wp/v2/posts/{request.remote_post_id}",
                ) as response:
                    status_code = response.status_code
                    if status_code in _REDIRECT_STATUSES:
                        return self._failed(
                            WordPressVerificationFailureKind.REDIRECT_REJECTED,
                            "WordPress redirect response was rejected.",
                        )
                    if status_code in {401, 403}:
                        return self._failed(
                            WordPressVerificationFailureKind.AUTH_FAILED,
                            "WordPress authentication was rejected.",
                        )
                    if status_code == 404:
                        return self._not_found()
                    if not response.is_success:
                        return self._failed(
                            WordPressVerificationFailureKind.HTTP_STATUS,
                            f"WordPress API returned HTTP {status_code}.",
                        )
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > _MAX_READ_RESPONSE_BYTES:
                            return self._failed(
                                WordPressVerificationFailureKind.RESPONSE_TOO_LARGE,
                                "WordPress response exceeded the read limit.",
                            )
        except httpx.TimeoutException:
            return self._failed(
                WordPressVerificationFailureKind.TIMEOUT,
                "WordPress draft read timed out.",
            )
        except httpx.RequestError as exc:
            return self._failed(
                WordPressVerificationFailureKind.REQUEST_FAILED,
                f"WordPress draft read failed ({type(exc).__name__}).",
            )

        try:
            payload = json.loads(bytes(body))
        except ValueError:
            return self._failed(
                WordPressVerificationFailureKind.MALFORMED_RESPONSE,
                "WordPress API returned a malformed response.",
            )
        if not isinstance(payload, dict):
            return self._failed(
                WordPressVerificationFailureKind.MALFORMED_RESPONSE,
                "WordPress API returned a malformed response.",
            )
        remote_post_id = payload.get("id")
        remote_status = payload.get("status")
        if (
            type(remote_post_id) is not int
            or remote_post_id <= 0
            or type(remote_status) is not str
            or not remote_status.strip()
        ):
            return self._failed(
                WordPressVerificationFailureKind.MALFORMED_RESPONSE,
                "WordPress API returned a malformed response.",
            )
        return WordPressDraftReadResult(
            outcome=WordPressDraftReadOutcome.FOUND,
            remote_post_id=remote_post_id,
            status=remote_status,
            link=normalize_wordpress_https_url(payload.get("link")),
            has_title=_rendered_text_present(payload.get("title")),
            has_content=_rendered_text_present(payload.get("content")),
            failure_kind=None,
            error=None,
        )

    async def _request_transport(
        self,
    ) -> tuple[
        httpx.AsyncBaseTransport | None,
        tuple[WordPressVerificationFailureKind, str] | None,
    ]:
        if self._transport is not None:
            return self._transport, None
        assert self._host is not None
        assert self._port is not None
        transport, failure = await _resolve_pinned_transport(
            host=self._host,
            port=self._port,
            timeout=self._timeout,
            resolver=self._resolver,
            allow_private_hosts=self._allow_private_hosts,
            transport_factory=self._transport_factory,
        )
        if failure is not None:
            return None, (_READER_FAILURE_KINDS[failure.kind], failure.message)
        return transport, None

    @staticmethod
    def _not_found() -> WordPressDraftReadResult:
        return WordPressDraftReadResult(
            outcome=WordPressDraftReadOutcome.NOT_FOUND,
            remote_post_id=None,
            status=None,
            link=None,
            has_title=False,
            has_content=False,
            failure_kind=None,
            error=None,
        )

    @staticmethod
    def _failed(
        failure_kind: WordPressVerificationFailureKind,
        error: str,
    ) -> WordPressDraftReadResult:
        return WordPressDraftReadResult(
            outcome=WordPressDraftReadOutcome.FAILED,
            remote_post_id=None,
            status=None,
            link=None,
            has_title=False,
            has_content=False,
            failure_kind=failure_kind,
            error=error,
        )

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


def _configuration_value(explicit: str | None, environment_name: str) -> str:
    value = explicit if explicit is not None else os.environ.get(environment_name, "")
    return value.strip() if type(value) is str else ""


def _is_origin_base_url(value: str) -> bool:
    try:
        split = urlsplit(value)
        _ = split.port
    except ValueError:
        return False
    return split.path in {"", "/"} and not split.query and not split.fragment


def _host_is_statically_denied(
    host: str,
    *,
    allow_private_hosts: bool,
) -> bool:
    normalized = host.rstrip(".").casefold()
    if (
        normalized in _DENIED_HOSTNAMES
        or normalized.endswith(".localhost")
        or normalized.endswith(".local")
    ):
        return True
    try:
        return not ip_address_is_permitted(
            ipaddress.ip_address(normalized),
            allow_private=allow_private_hosts,
        )
    except ValueError:
        return False


def _json_object(response: httpx.Response) -> dict[str, object] | None:
    try:
        payload = response.json()
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None


def _rendered_text_present(value: object) -> bool:
    """Report whether a WordPress ``{rendered: ...}`` field carries text."""

    if not isinstance(value, dict):
        return False
    rendered = value.get("rendered")
    return type(rendered) is str and bool(rendered.strip())
