"""Isolated, offline Trafilatura worker. Invoked only as a subprocess."""

from __future__ import annotations

import base64
from datetime import date
import json
import logging
import re
import socket
import sys
from typing import Any


_ABSOLUTE_REQUEST_LIMIT = 12 * 1024 * 1024
_EXCLUDED_STRUCTURE_TAGS = frozenset(
    {
        "nav",
        "header",
        "footer",
        "aside",
        "form",
        "script",
        "style",
        "template",
        "noscript",
        "svg",
    }
)
_CONTENT_LIKE_TOKENS = frozenset(
    {
        "article",
        "content",
        "description",
        "detail",
        "details",
        "main",
        "product",
        "specification",
        "specifications",
    }
)
_CONTENT_TOKEN_PATTERN = re.compile(r"[a-z0-9]+", flags=re.ASCII)
_HEADING_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})


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


def _tag_name(element: Any) -> str:
    tag = getattr(element, "tag", None)
    return tag.casefold() if isinstance(tag, str) else ""


def _is_visible(element: Any) -> bool:
    current = element
    while current is not None:
        if _tag_name(current) in _EXCLUDED_STRUCTURE_TAGS:
            return False
        attributes = getattr(current, "attrib", {})
        if "hidden" in attributes:
            return False
        if str(attributes.get("aria-hidden", "")).strip().casefold() == "true":
            return False
        style = "".join(str(attributes.get("style", "")).casefold().split())
        if "display:none" in style or "visibility:hidden" in style:
            return False
        current = current.getparent()
    return True


def _visible_text(element: Any) -> str | None:
    parts: list[str] = []
    for text_node in element.xpath(".//text()"):
        parent = text_node.getparent()
        if parent is not None and _is_visible(parent):
            cleaned = _clean_text(str(text_node))
            if cleaned is not None:
                parts.append(cleaned)
    return _clean_text(" ".join(parts))


def _is_content_container(element: Any) -> bool:
    if _tag_name(element) in {"main", "article"}:
        return True
    attributes = getattr(element, "attrib", {})
    tokens = set(
        _CONTENT_TOKEN_PATTERN.findall(
            f"{attributes.get('id', '')} {attributes.get('class', '')}".casefold()
        )
    )
    return bool(tokens & _CONTENT_LIKE_TOKENS)


def _content_root(element: Any) -> Any | None:
    lineage = [element, *element.iterancestors()]
    for candidate in reversed(lineage):
        if _is_content_container(candidate) and _is_visible(candidate):
            return candidate
    return None


class _StructuredCollector:
    def __init__(self, limits: dict[str, int]) -> None:
        self.limits = limits
        self.blocks: list[dict[str, object]] = []
        self.truncated = False
        self._seen: set[str] = set()
        self._text_chars = 0
        self._text_bytes = 0

    def limit_text(self, value: object, maximum: int) -> str | None:
        cleaned = _clean_text(value)
        if cleaned is None:
            return None
        if len(cleaned) > maximum:
            self.truncated = True
            return cleaned[:maximum]
        return cleaned

    def add(self, block: dict[str, object]) -> bool:
        fingerprint = self._fingerprint(block)
        if fingerprint in self._seen:
            return False
        self._seen.add(fingerprint)
        if len(self.blocks) >= self.limits["max_structured_blocks"]:
            self.truncated = True
            return False

        strings = tuple(_block_strings(block))
        added_chars = sum(len(value) for value in strings)
        added_bytes = sum(len(value.encode("utf-8")) for value in strings)
        if (
            self._text_chars + added_chars > self.limits["max_structured_chars"]
            or self._text_bytes + added_bytes > self.limits["max_structured_bytes"]
        ):
            self.truncated = True
            return False
        self._text_chars += added_chars
        self._text_bytes += added_bytes
        self.blocks.append(block)
        return True

    def contains(self, block: dict[str, object]) -> bool:
        return self._fingerprint(block) in self._seen

    @staticmethod
    def _fingerprint(block: dict[str, object]) -> str:
        return json.dumps(
            block,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )


def _block_strings(value: object):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _block_strings(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            if key != "kind":
                yield from _block_strings(item)


def _heading_context(element: Any, collector: _StructuredCollector) -> str | None:
    root = _content_root(element)
    if root is None:
        return None
    candidates = element.xpath("preceding::h1 | preceding::h2 | preceding::h3 | preceding::h4 | preceding::h5 | preceding::h6")
    for candidate in reversed(candidates):
        if _content_root(candidate) is root and _is_visible(candidate):
            return collector.limit_text(
                _visible_text(candidate),
                collector.limits["max_heading_context_chars"],
            )
    return None


def _extract_tables(tree: Any, collector: _StructuredCollector) -> None:
    table_count = 0
    for table in tree.xpath("//table"):
        if not _is_visible(table):
            continue
        rows: list[list[str]] = []
        row_elements = table.xpath("./tr | ./thead/tr | ./tbody/tr | ./tfoot/tr")
        for row_element in row_elements:
            cells: list[str] = []
            for cell_element in row_element.xpath("./th | ./td"):
                if len(cells) >= collector.limits["max_table_cells"]:
                    collector.truncated = True
                    break
                visible_cell = _visible_text(cell_element)
                cell = (
                    ""
                    if visible_cell is None
                    else collector.limit_text(
                        visible_cell,
                        collector.limits["max_structured_field_chars"],
                    )
                )
                cells.append(cell or "")
            if not cells or not any(cells):
                continue
            if len(rows) >= collector.limits["max_table_rows"]:
                collector.truncated = True
                break
            rows.append(cells)
        if not rows:
            continue
        block = {
            "kind": "table",
            "heading": _heading_context(table, collector),
            "rows": rows,
        }
        if collector.contains(block):
            continue
        if table_count >= collector.limits["max_tables"]:
            collector.truncated = True
            continue
        table_count += 1
        collector.add(block)


def _extract_definition_lists(tree: Any, collector: _StructuredCollector) -> None:
    block_count = 0
    for definition_list in tree.xpath("//dl"):
        if not _is_visible(definition_list):
            continue
        pairs: list[list[str]] = []
        current_term: str | None = None
        for child in definition_list.xpath("./dt | ./dd"):
            text = collector.limit_text(
                _visible_text(child),
                collector.limits["max_structured_field_chars"],
            )
            if _tag_name(child) == "dt":
                current_term = text
            elif current_term is not None and text is not None:
                if len(pairs) >= collector.limits["max_pairs_per_block"]:
                    collector.truncated = True
                    break
                pairs.append([current_term, text])
        if not pairs:
            continue
        block = {
            "kind": "definition_list",
            "heading": _heading_context(definition_list, collector),
            "pairs": pairs,
        }
        if collector.contains(block):
            continue
        if block_count >= collector.limits["max_definition_blocks"]:
            collector.truncated = True
            continue
        block_count += 1
        collector.add(block)


def _extract_key_values(tree: Any, collector: _StructuredCollector) -> None:
    block_count = 0
    for element in tree.xpath("//p[strong or b]"):
        if not _is_visible(element) or _content_root(element) is None or len(element) == 0:
            continue
        label_element = element[0]
        if _tag_name(label_element) not in {"strong", "b"}:
            continue
        raw_label = _visible_text(label_element)
        if raw_label is None or not raw_label.endswith((":", "：")):
            continue
        full_text = _visible_text(element)
        if full_text is None or not full_text.startswith(raw_label):
            continue
        label = collector.limit_text(
            raw_label[:-1],
            collector.limits["max_structured_field_chars"],
        )
        value = collector.limit_text(
            full_text[len(raw_label) :],
            collector.limits["max_structured_field_chars"],
        )
        if label is None or value is None:
            continue
        block = {
            "kind": "key_value",
            "heading": _heading_context(element, collector),
            "pairs": [[label, value]],
        }
        if collector.contains(block):
            continue
        if block_count >= collector.limits["max_key_value_blocks"]:
            collector.truncated = True
            continue
        block_count += 1
        collector.add(block)


def _extract_lists(tree: Any, collector: _StructuredCollector) -> None:
    block_count = 0
    for list_element in tree.xpath("//ul | //ol"):
        if (
            not _is_visible(list_element)
            or _content_root(list_element) is None
            or list_element.xpath("ancestor::ul | ancestor::ol")
        ):
            continue
        items: list[str] = []
        seen_items: set[str] = set()
        for item_element in list_element.xpath("./li"):
            item = collector.limit_text(
                _visible_text(item_element),
                collector.limits["max_structured_field_chars"],
            )
            if item is None or item in seen_items:
                continue
            if len(items) >= collector.limits["max_list_items"]:
                collector.truncated = True
                break
            seen_items.add(item)
            items.append(item)
        if not items:
            continue
        block = {
            "kind": "list",
            "heading": _heading_context(list_element, collector),
            "items": items,
        }
        if collector.contains(block):
            continue
        if block_count >= collector.limits["max_list_blocks"]:
            collector.truncated = True
            continue
        block_count += 1
        collector.add(block)


def _section_text(heading: Any) -> str | None:
    root = _content_root(heading)
    if root is None:
        return None
    elements = list(root.iter())
    try:
        start = elements.index(heading)
    except ValueError:
        return None
    heading_level = int(_tag_name(heading)[1])
    parts: list[str] = []
    seen: set[str] = set()
    for element in elements[start + 1 :]:
        tag = _tag_name(element)
        if tag in _HEADING_TAGS:
            if int(tag[1]) <= heading_level:
                break
            continue
        if not _is_visible(element):
            continue
        if tag == "p":
            pass
        elif tag == "div":
            if element.xpath(".//p | .//table | .//dl | .//ul | .//ol | .//h1 | .//h2 | .//h3 | .//h4 | .//h5 | .//h6"):
                continue
        else:
            continue
        text = _visible_text(element)
        if text is not None and text not in seen:
            seen.add(text)
            parts.append(text)
    return _clean_text(" ".join(parts))


def _extract_sections(tree: Any, collector: _StructuredCollector) -> None:
    section_count = 0
    for heading_element in tree.xpath("//h1 | //h2 | //h3 | //h4 | //h5 | //h6"):
        if not _is_visible(heading_element) or _content_root(heading_element) is None:
            continue
        heading = collector.limit_text(
            _visible_text(heading_element),
            collector.limits["max_heading_context_chars"],
        )
        text = collector.limit_text(
            _section_text(heading_element),
            collector.limits["max_section_chars"],
        )
        if heading is None or text is None:
            continue
        block = {
            "kind": "section",
            "heading": heading,
            "text": text,
        }
        if collector.contains(block):
            continue
        if section_count >= collector.limits["max_sections"]:
            collector.truncated = True
            continue
        section_count += 1
        collector.add(block)


def _extract_image_alts(tree: Any, collector: _StructuredCollector) -> None:
    alt_count = 0
    seen: set[tuple[str | None, str]] = set()
    for image in tree.xpath("//img[@alt]"):
        if not _is_visible(image) or _content_root(image) is None:
            continue
        alt = collector.limit_text(
            image.attrib.get("alt"),
            collector.limits["max_structured_field_chars"],
        )
        if alt is None:
            continue
        heading = _heading_context(image, collector)
        key = (heading, alt)
        if key in seen:
            continue
        seen.add(key)
        if alt_count >= collector.limits["max_image_alts"]:
            collector.truncated = True
            continue
        alt_count += 1
        collector.add({"kind": "image_alt", "heading": heading, "text": alt})


def _extract_structured_content(
    tree: Any,
    limits: dict[str, int],
) -> tuple[list[dict[str, object]], bool]:
    collector = _StructuredCollector(limits)
    _extract_tables(tree, collector)
    _extract_definition_lists(tree, collector)
    _extract_key_values(tree, collector)
    _extract_lists(tree, collector)
    _extract_sections(tree, collector)
    _extract_image_alts(tree, collector)
    return collector.blocks, collector.truncated


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

    try:
        structured_content, structured_content_truncated = _extract_structured_content(
            tree,
            limits,
        )
    except Exception:
        structured_content = []
        structured_content_truncated = True

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
            "structured_content": structured_content,
            "structured_content_truncated": structured_content_truncated,
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
