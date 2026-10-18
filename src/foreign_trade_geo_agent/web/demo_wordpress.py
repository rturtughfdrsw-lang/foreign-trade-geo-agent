"""Deterministic, credential-safe WordPress sandbox for the local Demo."""

from __future__ import annotations

from dataclasses import dataclass
import json

import httpx


DEMO_WORDPRESS_USERNAME = "demo-user"
DEMO_WORDPRESS_APPLICATION_PASSWORD = "demo-application-password-not-a-secret"
DEMO_WORDPRESS_POST_ID = 41

_DEMO_WORDPRESS_HOST = "demo-wordpress"
_WORDPRESS_POSTS_PATH = "/wp-json/wp/v2/posts"


def demo_wordpress_origin(run_id: str) -> str:
    """Return a deterministic, credential-free per-run mock WordPress origin."""

    return f"https://{_DEMO_WORDPRESS_HOST}-{run_id}.example"


@dataclass(frozen=True, slots=True)
class DemoWordPressRequestObservation:
    """A sanitized record of one sandbox request without credentials."""

    method: str
    path: str
    requested_status: str | None
    remote_post_id: int | None


class DemoWordPressTransport:
    """Serve the WordPress REST subset without retaining credential headers."""

    def __init__(
        self,
        *,
        post_timeout: bool = False,
        post_status_code: int | None = None,
    ) -> None:
        self.post_timeout = post_timeout
        self.post_status_code = post_status_code
        self._observations: list[DemoWordPressRequestObservation] = []

    @property
    def observations(self) -> tuple[DemoWordPressRequestObservation, ...]:
        return tuple(self._observations)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        method = request.method
        path = request.url.path
        host = request.url.host
        port = request.url.port
        netloc = f"{host}:{port}" if port is not None else host
        origin = f"{request.url.scheme}://{netloc}"

        if method == "POST" and path == _WORDPRESS_POSTS_PATH:
            payload = _json_object(request.content)
            requested_status = payload.get("status") if payload is not None else None
            self._observations.append(
                DemoWordPressRequestObservation(method, path, requested_status, None)
            )
            if self.post_timeout:
                raise httpx.ReadTimeout("controlled demo timeout", request=request)
            if requested_status != "draft":
                raise AssertionError("Demo WordPress create must be draft-only.")
            if self.post_status_code is not None:
                return httpx.Response(
                    self.post_status_code,
                    json={"code": "demo_failure", "message": "controlled demo failure"},
                )
            return httpx.Response(
                201,
                json={
                    "id": DEMO_WORDPRESS_POST_ID,
                    "status": "draft",
                    "link": f"{origin}/?p={DEMO_WORDPRESS_POST_ID}",
                },
            )

        if method == "GET" and path == f"{_WORDPRESS_POSTS_PATH}/{DEMO_WORDPRESS_POST_ID}":
            self._observations.append(
                DemoWordPressRequestObservation(
                    method, path, None, DEMO_WORDPRESS_POST_ID
                )
            )
            return httpx.Response(
                200,
                json={
                    "id": DEMO_WORDPRESS_POST_ID,
                    "status": "draft",
                    "link": f"{origin}/?p={DEMO_WORDPRESS_POST_ID}",
                    "title": {"rendered": "NovaCNC demo draft"},
                    "content": {"rendered": "<p>Demo draft body</p>"},
                },
            )

        raise AssertionError(
            f"Unexpected Demo WordPress request: {method} {request.url}"
        )


def _json_object(content: bytes) -> dict[str, object] | None:
    try:
        payload = json.loads(content)
    except (ValueError, TypeError):
        return None
    return payload if isinstance(payload, dict) else None
