"""Isolated, offline Trafilatura worker. Invoked only as a subprocess."""

from __future__ import annotations

import base64
from datetime import date
import json
import logging
import socket
import sys
from typing import Any


_ABSOLUTE_REQUEST_LIMIT = 12 * 1024 * 1024


class _NetworkDisabledSocket(socket.socket):
    def connect(self, address: object) -> None:
        raise OSError("Network access is disabled in the page extraction worker.")

    def connect_ex(self, address: object) -> int:
        raise OSError("Network access is disabled in the page extraction worker.")


def _disable_network() -> None:
    def denied(*_args: object, **_kwargs: object) -> object:
        raise OSError("Network access is disabled in the page extraction worker.")

    socket.socket = _NetworkDisabledSocket
    socket.create_connection = denied
    socket.getaddrinfo = denied


def _failure(kind: str, error: str) -> dict[str, object]:
    return {"kind": "failure", "failure_kind": kind, "error": error}


def _clean_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split())
    return cleaned or None


def _published_date(value: object) -> str | None:
    cleaned = _clean_text(value)
    if cleaned is None or len(cleaned) != 10:
        return None
    try:
        date.fromisoformat(cleaned)
    except ValueError:
        return None
    return cleaned


def _decode_html(html_bytes: bytes) -> str:
    """Decode HTML bytes without performing implicit decompression."""

    if html_bytes.startswith(b"\x1f\x8b"):
        raise ValueError("Nested compressed input is not HTML.")
    try:
        return html_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        from charset_normalizer import from_bytes

        match = from_bytes(html_bytes[: 64 * 1024]).best()
        encoding = None if match is None else match.encoding
        if not encoding:
            return html_bytes.decode("utf-8", errors="replace")
        try:
            return html_bytes.decode(encoding, errors="replace")
        except LookupError:
            return html_bytes.decode("utf-8", errors="replace")


def _extract_static_fields(tree: Any) -> tuple[str | None, tuple[str, ...], tuple[str, ...]]:
    canonical_values = tree.xpath(
        "//link[contains(concat(' ', normalize-space(translate(@rel, "
        "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')), ' '), "
        "' canonical ')][1]/@href"
    )
    canonical = _clean_text(canonical_values[0]) if canonical_values else None

    headings: dict[str, list[str]] = {"h1": [], "h2": []}
    for element in tree.xpath("//h1 | //h2"):
        text = _clean_text(" ".join(element.itertext()))
        if text is not None:
            headings[element.tag.lower()].append(text)
    return canonical, tuple(headings["h1"]), tuple(headings["h2"])


def _metadata_too_large(
    values: tuple[str | None, ...],
    headings: tuple[tuple[str, ...], ...],
    *,
    max_chars: int,
    max_headings: int,
) -> bool:
    if any(value is not None and len(value) > max_chars for value in values):
        return True
    all_headings = tuple(item for group in headings for item in group)
    return len(all_headings) > max_headings or any(
        len(item) > max_chars for item in all_headings
    )


def _extract(request: dict[str, Any]) -> dict[str, object]:
    from lxml import etree
    from lxml import html as lxml_html
    from trafilatura import bare_extraction

    limits = request["limits"]
    html_bytes = base64.b64decode(request["html_base64"], validate=True)
    try:
        html_text = _decode_html(html_bytes)
    except ValueError:
        return _failure("extraction_failed", "HTML could not be decoded safely.")
    if len(html_text) > limits["max_decoded_chars"]:
        return _failure("input_too_large", "Decoded HTML exceeded the configured limit.")

    parser = lxml_html.HTMLParser(
        encoding="utf-8",
        recover=True,
        no_network=True,
        huge_tree=False,
    )
    try:
        tree = lxml_html.fromstring(html_text, parser=parser)
    except (etree.ParserError, TypeError, ValueError, UnicodeError):
        return _failure("extraction_failed", "HTML could not be parsed safely.")

    node_count = 0
    for _element in tree.iter():
        node_count += 1
        if node_count > limits["max_nodes"]:
            return _failure("input_too_large", "HTML node count exceeded the configured limit.")

    canonical, h1, h2 = _extract_static_fields(tree)
    try:
        document = bare_extraction(
            html_text,
            url=request["final_url"],
            fast=False,
            include_comments=False,
            include_tables=False,
            include_images=False,
            include_links=False,
            with_metadata=True,
            output_format="python",
            date_extraction_params={
                "extensive_search": False,
                "original_date": True,
            },
        )
    except Exception:
        return _failure("extraction_failed", "HTML content extraction failed.")

    if document is None or not isinstance(document.text, str) or not document.text.strip():
        return _failure("empty_content", "No extractable page content was found.")

    body_text = document.text.strip()
    title = _clean_text(document.title)
    description = _clean_text(document.description)
    published_date = _published_date(document.date)
    if len(body_text) > limits["max_body_chars"]:
        return _failure("output_too_large", "Extracted page body exceeded the configured limit.")
    if _metadata_too_large(
        (title, description, canonical, published_date),
        (h1, h2),
        max_chars=limits["max_metadata_chars"],
        max_headings=limits["max_headings"],
    ):
        return _failure("output_too_large", "Extracted page metadata exceeded the configured limit.")

    return {
        "kind": "success",
        "page": {
            "final_url": request["final_url"],
            "title": title,
            "description": description,
            "canonical": canonical,
            "h1": list(h1),
            "h2": list(h2),
            "body_text": body_text,
            "published_date": published_date,
        },
    }


def main() -> None:
    logging.disable(logging.CRITICAL)
    _disable_network()
    raw_request = sys.stdin.buffer.read(_ABSOLUTE_REQUEST_LIMIT + 1)
    if len(raw_request) > _ABSOLUTE_REQUEST_LIMIT:
        response = _failure("input_too_large", "Worker request exceeded the absolute limit.")
    else:
        try:
            request = json.loads(raw_request.decode("utf-8"))
            response = _extract(request)
        except (KeyError, TypeError, ValueError, UnicodeError):
            response = _failure("extraction_failed", "Worker input could not be processed safely.")

    max_output = 0
    try:
        max_output = int(request["limits"]["max_worker_output_bytes"])
    except (KeyError, NameError, TypeError, ValueError):
        pass
    output = json.dumps(response, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if max_output > 0 and len(output) > max_output:
        output = json.dumps(
            _failure("output_too_large", "Worker output exceeded the configured limit."),
            separators=(",", ":"),
        ).encode("utf-8")
    sys.stdout.buffer.write(output)
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()
