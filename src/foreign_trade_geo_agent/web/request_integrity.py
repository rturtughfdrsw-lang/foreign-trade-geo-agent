"""Process-local integrity checks for loopback Web mutations."""

from __future__ import annotations

import secrets
from urllib.parse import urlsplit


class RequestIntegrityError(RuntimeError):
    """A fixed failure for a non-local or forged mutation request."""


def validate_local_mutation(
    host_header: str | None,
    submitted_token: str | None,
    expected_token: str,
) -> None:
    """Fail closed unless Host and process-local CSRF token both match."""

    if not _allowed_local_host(host_header):
        raise RequestIntegrityError("Invalid local request.")
    if (
        type(submitted_token) is not str
        or not submitted_token
        or not secrets.compare_digest(submitted_token, expected_token)
    ):
        raise RequestIntegrityError("Invalid local request.")


def _allowed_local_host(value: str | None) -> bool:
    if type(value) is not str or not value or any(character.isspace() for character in value):
        return False
    try:
        parsed = urlsplit(f"http://{value}")
        port = parsed.port
    except ValueError:
        return False
    if (
        parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or parsed.hostname not in {"127.0.0.1", "localhost"}
    ):
        return False
    return port is None or 1 <= port <= 65_535
