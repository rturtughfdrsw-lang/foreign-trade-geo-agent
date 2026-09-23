"""Bounded offline page extraction using an isolated Trafilatura worker."""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
from urllib.parse import urlsplit

from foreign_trade_geo_agent.core.extraction import (
    PageExtractionFailureKind,
    PageExtractionResult,
    PageExtractionStatus,
)


_DEFAULT_WORKER_MODULE = "foreign_trade_geo_agent.adapters._page_worker"
_MAX_INPUT_BYTES = 8 * 1024 * 1024
_MAX_WORKER_OUTPUT_BYTES = 4 * 1024 * 1024


class TrafilaturaPageExtractor:
    """Extract one already downloaded HTML page without network access."""

    def __init__(
        self,
        *,
        timeout: float = 5.0,
        termination_grace: float = 1.0,
        max_input_bytes: int = 4 * 1024 * 1024,
        max_decoded_chars: int = 4_000_000,
        max_nodes: int = 50_000,
        max_body_chars: int = 200_000,
        max_metadata_chars: int = 2_048,
        max_headings: int = 200,
        max_worker_output_bytes: int = 1024 * 1024,
        _worker_module: str = _DEFAULT_WORKER_MODULE,
    ) -> None:
        if (
            timeout <= 0
            or termination_grace <= 0
            or not 0 < max_input_bytes <= _MAX_INPUT_BYTES
            or max_decoded_chars <= 0
            or max_nodes <= 0
            or max_body_chars <= 0
            or max_metadata_chars <= 0
            or max_headings <= 0
            or not 128 <= max_worker_output_bytes <= _MAX_WORKER_OUTPUT_BYTES
            or not _worker_module
        ):
            raise ValueError("Page extraction limits must be positive and bounded.")
        self._timeout = timeout
        self._termination_grace = termination_grace
        self._max_input_bytes = max_input_bytes
        self._max_decoded_chars = max_decoded_chars
        self._max_nodes = max_nodes
        self._max_body_chars = max_body_chars
        self._max_metadata_chars = max_metadata_chars
        self._max_headings = max_headings
        self._max_worker_output_bytes = max_worker_output_bytes
        self._worker_module = _worker_module
        self._last_process: subprocess.Popen[bytes] | None = None

    def extract(self, html: bytes, final_url: str) -> PageExtractionResult:
        if type(html) is not bytes or not self._valid_url(final_url):
            return self._failed(
                final_url if isinstance(final_url, str) else "",
                PageExtractionFailureKind.INVALID_INPUT,
                "Page extraction requires HTML bytes and a valid HTTP(S) URL.",
            )
        if not html:
            return self._failed(
                final_url,
                PageExtractionFailureKind.EMPTY_CONTENT,
                "No HTML content was supplied for extraction.",
            )
        if len(html) > self._max_input_bytes:
            return self._failed(
                final_url,
                PageExtractionFailureKind.INPUT_TOO_LARGE,
                "HTML input exceeded the configured byte limit.",
            )

        request = {
            "final_url": final_url,
            "html_base64": base64.b64encode(html).decode("ascii"),
            "limits": {
                "max_decoded_chars": self._max_decoded_chars,
                "max_nodes": self._max_nodes,
                "max_body_chars": self._max_body_chars,
                "max_metadata_chars": self._max_metadata_chars,
                "max_headings": self._max_headings,
                "max_worker_output_bytes": self._max_worker_output_bytes,
            },
        }
        request_bytes = json.dumps(request, separators=(",", ":")).encode("utf-8")
        command = [sys.executable]
        if self._worker_module == _DEFAULT_WORKER_MODULE:
            command.append("-I")
        command.extend(("-m", self._worker_module))
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                env=self._worker_environment(),
                close_fds=True,
                creationflags=creationflags,
            )
        except OSError:
            return self._failed(
                final_url,
                PageExtractionFailureKind.WORKER_FAILED,
                "Page extraction worker could not be started.",
            )
        self._last_process = process

        try:
            output, _stderr = process.communicate(
                input=request_bytes,
                timeout=self._timeout,
            )
        except subprocess.TimeoutExpired:
            self._terminate_and_reap(process)
            return self._failed(
                final_url,
                PageExtractionFailureKind.EXTRACTION_TIMEOUT,
                "Page extraction exceeded the configured time limit.",
            )

        if len(output) > self._max_worker_output_bytes:
            return self._failed(
                final_url,
                PageExtractionFailureKind.OUTPUT_TOO_LARGE,
                "Page extraction worker output exceeded the configured limit.",
            )
        if process.returncode != 0 or not output:
            return self._failed(
                final_url,
                PageExtractionFailureKind.WORKER_FAILED,
                "Page extraction worker exited unexpectedly.",
            )
        return self._decode_result(output, final_url)

    def _terminate_and_reap(self, process: subprocess.Popen[bytes]) -> None:
        process.terminate()
        try:
            process.communicate(timeout=self._termination_grace)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()

    def _decode_result(self, output: bytes, final_url: str) -> PageExtractionResult:
        try:
            response = json.loads(output.decode("utf-8"))
            if response.get("kind") == "failure":
                failure_kind = PageExtractionFailureKind(response["failure_kind"])
                error = response["error"]
                if not isinstance(error, str) or not error:
                    raise ValueError
                return self._failed(final_url, failure_kind, error)
            if response.get("kind") != "success":
                raise ValueError
            page = response["page"]
            if page["final_url"] != final_url:
                raise ValueError
            return PageExtractionResult(
                final_url=final_url,
                status=PageExtractionStatus.SUCCESS,
                title=self._optional_string(page["title"]),
                description=self._optional_string(page["description"]),
                canonical=self._optional_string(page["canonical"]),
                h1=self._string_tuple(page["h1"]),
                h2=self._string_tuple(page["h2"]),
                body_text=self._required_string(page["body_text"]),
                published_date=self._optional_string(page["published_date"]),
                failure_kind=None,
                error=None,
            )
        except (KeyError, TypeError, ValueError, UnicodeError, json.JSONDecodeError):
            return self._failed(
                final_url,
                PageExtractionFailureKind.WORKER_FAILED,
                "Page extraction worker returned an invalid result.",
            )

    @staticmethod
    def _required_string(value: object) -> str:
        if not isinstance(value, str) or not value:
            raise ValueError
        return value

    @staticmethod
    def _optional_string(value: object) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError
        return value

    @staticmethod
    def _string_tuple(value: object) -> tuple[str, ...]:
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ValueError
        return tuple(value)

    @staticmethod
    def _worker_environment() -> dict[str, str]:
        environment = {
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "TZ": "UTC",
        }
        for name in ("SYSTEMROOT", "WINDIR", "TEMP", "TMP"):
            value = os.environ.get(name)
            if value:
                environment[name] = value
        return environment

    @staticmethod
    def _valid_url(value: object) -> bool:
        if type(value) is not str or not value or len(value) > 2_048:
            return False
        try:
            parsed = urlsplit(value)
            port = parsed.port
        except ValueError:
            return False
        return (
            parsed.scheme.casefold() in {"http", "https"}
            and parsed.hostname is not None
            and parsed.username is None
            and parsed.password is None
            and (port is None or 0 < port < 65_536)
            and not any(character.isspace() or ord(character) < 32 for character in value)
        )

    @staticmethod
    def _failed(
        final_url: str,
        kind: PageExtractionFailureKind,
        error: str,
    ) -> PageExtractionResult:
        return PageExtractionResult(
            final_url=final_url,
            status=PageExtractionStatus.FAILED,
            title=None,
            description=None,
            canonical=None,
            h1=(),
            h2=(),
            body_text=None,
            published_date=None,
            failure_kind=kind,
            error=error,
        )
