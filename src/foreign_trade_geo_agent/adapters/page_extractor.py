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
    StructuredContentBlock,
    StructuredContentKind,
)


_DEFAULT_WORKER_MODULE = "foreign_trade_geo_agent.adapters._page_worker"
_MAX_INPUT_BYTES = 8 * 1024 * 1024
_MAX_WORKER_OUTPUT_BYTES = 4 * 1024 * 1024
_MAX_STRUCTURED_BLOCKS = 128
_MAX_TABLES = 16
_MAX_TABLE_ROWS = 64
_MAX_TABLE_CELLS = 16
_MAX_STRUCTURED_FIELD_CHARS = 512
_MAX_DEFINITION_BLOCKS = 16
_MAX_KEY_VALUE_BLOCKS = 16
_MAX_PAIRS_PER_BLOCK = 64
_MAX_LIST_BLOCKS = 32
_MAX_LIST_ITEMS = 64
_MAX_SECTIONS = 32
_MAX_SECTION_CHARS = 2_048
_MAX_IMAGE_ALTS = 64
_MAX_HEADING_CONTEXT_CHARS = 256
_MAX_STRUCTURED_CHARS = 50_000
_MAX_STRUCTURED_BYTES = 128 * 1024


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
        max_structured_blocks: int = _MAX_STRUCTURED_BLOCKS,
        max_tables: int = _MAX_TABLES,
        max_table_rows: int = _MAX_TABLE_ROWS,
        max_table_cells: int = _MAX_TABLE_CELLS,
        max_structured_field_chars: int = _MAX_STRUCTURED_FIELD_CHARS,
        max_definition_blocks: int = _MAX_DEFINITION_BLOCKS,
        max_key_value_blocks: int = _MAX_KEY_VALUE_BLOCKS,
        max_pairs_per_block: int = _MAX_PAIRS_PER_BLOCK,
        max_list_blocks: int = _MAX_LIST_BLOCKS,
        max_list_items: int = _MAX_LIST_ITEMS,
        max_sections: int = _MAX_SECTIONS,
        max_section_chars: int = _MAX_SECTION_CHARS,
        max_image_alts: int = _MAX_IMAGE_ALTS,
        max_heading_context_chars: int = _MAX_HEADING_CONTEXT_CHARS,
        max_structured_chars: int = _MAX_STRUCTURED_CHARS,
        max_structured_bytes: int = _MAX_STRUCTURED_BYTES,
        _worker_module: str = _DEFAULT_WORKER_MODULE,
    ) -> None:
        structured_limits = {
            "max_structured_blocks": (max_structured_blocks, _MAX_STRUCTURED_BLOCKS),
            "max_tables": (max_tables, _MAX_TABLES),
            "max_table_rows": (max_table_rows, _MAX_TABLE_ROWS),
            "max_table_cells": (max_table_cells, _MAX_TABLE_CELLS),
            "max_structured_field_chars": (
                max_structured_field_chars,
                _MAX_STRUCTURED_FIELD_CHARS,
            ),
            "max_definition_blocks": (
                max_definition_blocks,
                _MAX_DEFINITION_BLOCKS,
            ),
            "max_key_value_blocks": (
                max_key_value_blocks,
                _MAX_KEY_VALUE_BLOCKS,
            ),
            "max_pairs_per_block": (max_pairs_per_block, _MAX_PAIRS_PER_BLOCK),
            "max_list_blocks": (max_list_blocks, _MAX_LIST_BLOCKS),
            "max_list_items": (max_list_items, _MAX_LIST_ITEMS),
            "max_sections": (max_sections, _MAX_SECTIONS),
            "max_section_chars": (max_section_chars, _MAX_SECTION_CHARS),
            "max_image_alts": (max_image_alts, _MAX_IMAGE_ALTS),
            "max_heading_context_chars": (
                max_heading_context_chars,
                _MAX_HEADING_CONTEXT_CHARS,
            ),
            "max_structured_chars": (max_structured_chars, _MAX_STRUCTURED_CHARS),
            "max_structured_bytes": (max_structured_bytes, _MAX_STRUCTURED_BYTES),
        }
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
            or any(not 0 < value <= maximum for value, maximum in structured_limits.values())
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
        self._structured_limits = {
            name: value for name, (value, _maximum) in structured_limits.items()
        }
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
                **self._structured_limits,
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
                structured_content=self._structured_content(
                    page.get("structured_content", [])
                ),
                structured_content_truncated=self._required_bool(
                    page.get("structured_content_truncated", False)
                ),
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

    @classmethod
    def _structured_content(
        cls,
        value: object,
    ) -> tuple[StructuredContentBlock, ...]:
        if not isinstance(value, list):
            raise ValueError
        return tuple(cls._structured_block(item) for item in value)

    @classmethod
    def _structured_block(cls, value: object) -> StructuredContentBlock:
        if not isinstance(value, dict):
            raise ValueError
        kind = StructuredContentKind(value["kind"])
        heading = cls._optional_string(value.get("heading"))
        text = cls._optional_string(value.get("text"))
        rows = cls._nested_string_tuple(value.get("rows", []))
        pairs_raw = cls._nested_string_tuple(value.get("pairs", []))
        if any(len(pair) != 2 for pair in pairs_raw):
            raise ValueError
        items = cls._string_tuple(value.get("items", []))
        return StructuredContentBlock(
            kind=kind,
            heading=heading,
            rows=rows,
            pairs=tuple((pair[0], pair[1]) for pair in pairs_raw),
            items=items,
            text=text,
        )

    @staticmethod
    def _nested_string_tuple(value: object) -> tuple[tuple[str, ...], ...]:
        if not isinstance(value, list) or not all(
            isinstance(group, list)
            and group
            and all(isinstance(item, str) for item in group)
            for group in value
        ):
            raise ValueError
        return tuple(tuple(group) for group in value)

    @staticmethod
    def _required_bool(value: object) -> bool:
        if not isinstance(value, bool):
            raise ValueError
        return value

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
