"""WordPress REST adapter that creates drafts only."""

from __future__ import annotations

import asyncio
import ipaddress
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
from foreign_trade_geo_agent.core.wordpress_draft import (
    WordPressDraftFailureKind,
    WordPressDraftRequest,
    WordPressDraftResult,
    WordPressDraftStatus,
    normalize_wordpress_https_url,
)


_DEFAULT_TIMEOUT_SECONDS = 30.0
_MAX_TIMEOUT_SECONDS = 120.0
_REDIRECT_STATUSES = frozenset(range(300, 400))
_DENIED_HOSTNAMES = frozenset({"localhost", "metadata", "metadata.google.internal"})
_TransportFactory = Callable[[str, int, str], httpx.AsyncBaseTransport]


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
            )
        except httpx.RequestError as exc:
            return self._failed(
                WordPressDraftFailureKind.REQUEST_FAILED,
                f"WordPress request failed ({type(exc).__name__}).",
            )

        failure = self._response_status_failure(response)
        if failure is not None:
            return failure
        payload = _json_object(response)
        if payload is None or type(payload.get("status")) is not str:
            return self._failed(
                WordPressDraftFailureKind.MALFORMED_RESPONSE,
                "WordPress API returned a malformed response.",
            )
        if payload["status"] != "draft":
            return self._failed(
                WordPressDraftFailureKind.RESPONSE_NOT_DRAFT,
                "WordPress response did not confirm draft status.",
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
            )
        return WordPressDraftResult(
            status=WordPressDraftStatus.SUCCESS,
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
        try:
            try:
                literal = ipaddress.ip_address(self._host)
            except ValueError:
                async with asyncio.timeout(self._timeout):
                    raw_addresses = await self._resolver.resolve(
                        self._host,
                        self._port,
                    )
            else:
                raw_addresses = (literal.compressed,)
        except TimeoutError:
            return None, self._failed(
                WordPressDraftFailureKind.TIMEOUT,
                "WordPress origin resolution timed out.",
            )
        except (OSError, socket.gaierror):
            return None, self._failed(
                WordPressDraftFailureKind.REQUEST_FAILED,
                "WordPress origin resolution failed.",
            )

        addresses: list[str] = []
        for raw_address in raw_addresses:
            try:
                address = ipaddress.ip_address(raw_address)
            except ValueError:
                return None, self._failed(
                    WordPressDraftFailureKind.REQUEST_FAILED,
                    "WordPress origin resolution failed.",
                )
            if not ip_address_is_permitted(
                address,
                allow_private=self._allow_private_hosts,
            ):
                return None, self._failed(
                    WordPressDraftFailureKind.ORIGIN_REJECTED,
                    "WordPress origin is not permitted.",
                )
            if address.compressed not in addresses:
                addresses.append(address.compressed)
        if not addresses:
            return None, self._failed(
                WordPressDraftFailureKind.REQUEST_FAILED,
                "WordPress origin resolution failed.",
            )
        return (
            self._transport_factory(self._host, self._port, addresses[0]),
            None,
        )

    def _response_status_failure(
        self,
        response: httpx.Response,
    ) -> WordPressDraftResult | None:
        if response.status_code in _REDIRECT_STATUSES:
            return self._failed(
                WordPressDraftFailureKind.REDIRECT_REJECTED,
                "WordPress redirect response was rejected.",
            )
        if response.status_code in {401, 403}:
            return self._failed(
                WordPressDraftFailureKind.AUTH_FAILED,
                "WordPress authentication was rejected.",
            )
        if not response.is_success:
            return self._failed(
                WordPressDraftFailureKind.HTTP_STATUS,
                f"WordPress API returned HTTP {response.status_code}.",
            )
        return None

    @staticmethod
    def _failed(
        failure_kind: WordPressDraftFailureKind,
        error: str,
    ) -> WordPressDraftResult:
        return WordPressDraftResult(
            status=WordPressDraftStatus.FAILED,
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
