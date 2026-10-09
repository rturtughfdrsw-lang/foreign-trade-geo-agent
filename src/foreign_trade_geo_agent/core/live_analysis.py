"""Validated inputs for the public-site Live planning profile."""

from __future__ import annotations

from dataclasses import dataclass, field
import ipaddress
from urllib.parse import urlsplit, urlunsplit

from .fetching import UrlOrigin


DEFAULT_LIVE_SEO_GOAL = "Improve organic search visibility and content coverage"
MAX_LIVE_WEBSITE_URL_CHARS = 2_048
MAX_LIVE_SEO_GOAL_CHARS = 300


def normalize_live_website_url(value: str) -> str:
    """Return one credential-free normalized public HTTPS seed URL."""

    if type(value) is not str or not value:
        raise ValueError("Website URL is invalid.")
    if "\\" in value or any(
        character.isspace() or ord(character) < 32 or ord(character) == 127
        for character in value
    ):
        raise ValueError("Website URL is invalid.")

    try:
        parsed = urlsplit(value)
        if parsed.scheme.casefold() != "https" or parsed.hostname is None:
            raise ValueError
        if parsed.username is not None or parsed.password is not None:
            raise ValueError
        port = parsed.port if parsed.port is not None else 443
        origin = UrlOrigin("https", parsed.hostname, port)
    except (TypeError, ValueError) as exc:
        raise ValueError("Website URL is invalid.") from exc

    if origin.host == "localhost" or origin.host.endswith(".localhost"):
        raise ValueError("Website URL is invalid.")
    try:
        address = ipaddress.ip_address(origin.host)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise ValueError("Website URL is invalid.")

    host = f"[{origin.host}]" if ":" in origin.host else origin.host
    netloc = host if origin.port == 443 else f"{host}:{origin.port}"
    normalized = urlunsplit(
        (
            "https",
            netloc,
            parsed.path or "/",
            parsed.query,
            "",
        )
    )
    if len(normalized) > MAX_LIVE_WEBSITE_URL_CHARS:
        raise ValueError("Website URL is invalid.")
    return normalized


@dataclass(frozen=True, slots=True)
class LiveAnalysisInput:
    website_url: str
    seo_goal: str = DEFAULT_LIVE_SEO_GOAL
    target_language: str = "en"
    display_identity: str = field(init=False)

    def __post_init__(self) -> None:
        website_url = normalize_live_website_url(self.website_url)
        if type(self.seo_goal) is not str:
            raise ValueError("SEO goal is invalid.")
        seo_goal = " ".join(self.seo_goal.split())
        if not seo_goal or len(seo_goal) > MAX_LIVE_SEO_GOAL_CHARS:
            raise ValueError("SEO goal is invalid.")
        if self.target_language != "en":
            raise ValueError("Target language is unsupported.")

        hostname = urlsplit(website_url).hostname
        if hostname is None:  # pragma: no cover - normalization guarantees this
            raise ValueError("Website URL is invalid.")
        object.__setattr__(self, "website_url", website_url)
        object.__setattr__(self, "seo_goal", seo_goal)
        object.__setattr__(self, "display_identity", hostname)
