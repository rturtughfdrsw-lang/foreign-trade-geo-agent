"""Provider-independent results for bounded, security-checked HTML fetches."""

from dataclasses import dataclass
from enum import Enum
import ipaddress

import idna


class FetchStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"


class FetchFailureKind(str, Enum):
    INVALID_URL = "invalid_url"
    ORIGIN_REJECTED = "origin_rejected"
    SAFETY_POLICY_REJECTED = "safety_policy_rejected"
    DNS_FAILED = "dns_failed"
    TIMEOUT = "timeout"
    REQUEST_FAILED = "request_failed"
    TLS_VERIFICATION_FAILED = "tls_verification_failed"
    HTTP_STATUS = "http_status"
    TOO_MANY_REDIRECTS = "too_many_redirects"
    NON_HTML = "non_html"
    UNSUPPORTED_CONTENT_ENCODING = "unsupported_content_encoding"
    RESOURCE_LIMIT_EXCEEDED = "resource_limit_exceeded"
    REQUEST_BUDGET_EXCEEDED = "request_budget_exceeded"
    REDIRECT_POLICY_REJECTED = "redirect_policy_rejected"
    TOTAL_WIRE_BUDGET_EXCEEDED = "total_wire_budget_exceeded"
    TOTAL_DECODED_BUDGET_EXCEEDED = "total_decoded_budget_exceeded"


@dataclass(frozen=True, slots=True)
class UrlOrigin:
    scheme: str
    host: str
    port: int

    def __post_init__(self) -> None:
        scheme = self.scheme.casefold()
        host = self.host.rstrip(".").lower()
        if scheme not in {"http", "https"} or not host or not 0 < self.port < 65_536:
            raise ValueError("URL origin is invalid.")
        try:
            host = ipaddress.ip_address(host).compressed
        except ValueError:
            try:
                host = idna.encode(host).decode("ascii")
            except idna.IDNAError as exc:
                raise ValueError("URL origin host is invalid.") from exc
        object.__setattr__(self, "scheme", scheme)
        object.__setattr__(self, "host", host)


@dataclass(frozen=True, slots=True)
class HtmlFetchResult:
    requested_url: str
    final_url: str
    status: FetchStatus
    http_status: int | None
    content_type: str | None
    content: bytes | None
    connected_ip: str | None
    wire_bytes: int
    decoded_bytes: int
    request_attempts: int
    redirect_chain: tuple[str, ...]
    failure_kind: FetchFailureKind | None
    error: str | None

    def __post_init__(self) -> None:
        if self.status is FetchStatus.SUCCESS:
            if (
                self.http_status is None
                or self.content is None
                or self.connected_ip is None
                or self.failure_kind is not None
                or self.error is not None
            ):
                raise ValueError("Successful HTML fetch result is inconsistent.")
        elif self.content is not None or self.failure_kind is None or not self.error:
            raise ValueError("Failed HTML fetch result is inconsistent.")


TextFetchResult = HtmlFetchResult
