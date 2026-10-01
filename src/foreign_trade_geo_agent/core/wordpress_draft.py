"""Provider-independent WordPress draft requests and results."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from html import escape
from urllib.parse import urlsplit, urlunsplit

from .content_draft import (
    BulletListBlock,
    ComparisonTableBlock,
    DraftBlockKind,
    DraftClaim,
    DraftItem,
    InternalLinkBlock,
    ParagraphBlock,
    TableCell,
)
from .fetching import UrlOrigin


class WordPressDraftStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"


class WordPressDraftFailureKind(str, Enum):
    INVALID_INPUT = "invalid_input"
    INVALID_URL = "invalid_url"
    ORIGIN_REJECTED = "origin_rejected"
    REDIRECT_REJECTED = "redirect_rejected"
    AUTH_FAILED = "auth_failed"
    HTTP_STATUS = "http_status"
    MALFORMED_RESPONSE = "malformed_response"
    RESPONSE_NOT_DRAFT = "response_not_draft"
    TIMEOUT = "timeout"
    REQUEST_FAILED = "request_failed"


class WordPressDraftValidationError(ValueError):
    """A deterministic, sanitized failure while building a draft request."""


def normalize_wordpress_https_url(value: object) -> str | None:
    """Return one normalized credential-free HTTPS URL or ``None``."""

    if type(value) is not str or not value or len(value) > 2_048:
        return None
    if "\\" in value or any(
        character.isspace() or ord(character) == 127 for character in value
    ):
        return None
    try:
        split = urlsplit(value)
        port = split.port
    except ValueError:
        return None
    if (
        split.scheme.casefold() != "https"
        or not split.hostname
        or split.username is not None
        or split.password is not None
    ):
        return None
    try:
        origin = UrlOrigin("https", split.hostname, port or 443)
    except ValueError:
        return None
    host = f"[{origin.host}]" if ":" in origin.host else origin.host
    netloc = host if origin.port == 443 and port is None else f"{host}:{origin.port}"
    return urlunsplit(("https", netloc, split.path, split.query, ""))


@dataclass(frozen=True, slots=True)
class WordPressDraftRequest:
    title: str
    content: str

    def __post_init__(self) -> None:
        if type(self.title) is not str or not self.title.strip():
            raise ValueError("WordPress draft title is required.")
        if type(self.content) is not str or not self.content.strip():
            raise ValueError("WordPress draft content is required.")


@dataclass(frozen=True, slots=True)
class WordPressDraftResult:
    status: WordPressDraftStatus
    remote_post_id: int | None
    remote_link: str | None
    created: bool
    failure_kind: WordPressDraftFailureKind | None
    error: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.status, WordPressDraftStatus) or type(self.created) is not bool:
            raise ValueError("WordPress draft result status is invalid.")
        if self.status is WordPressDraftStatus.SUCCESS:
            if (
                type(self.remote_post_id) is not int
                or self.remote_post_id <= 0
                or normalize_wordpress_https_url(self.remote_link) is None
                or not self.created
                or self.failure_kind is not None
                or self.error is not None
            ):
                raise ValueError("Successful WordPress draft result is invalid.")
            return
        if (
            self.remote_post_id is not None
            or self.remote_link is not None
            or self.created
            or not isinstance(self.failure_kind, WordPressDraftFailureKind)
            or type(self.error) is not str
            or not self.error.strip()
            or len(self.error) > 512
            or any(ord(character) < 32 or ord(character) == 127 for character in self.error)
        ):
            raise ValueError("Failed WordPress draft result is invalid.")


def build_wordpress_draft_request(
    draft: DraftItem,
    *,
    title_override: str | None = None,
) -> WordPressDraftRequest:
    """Convert a validated content draft into deterministic, escaped HTML."""

    if not isinstance(draft, DraftItem):
        raise WordPressDraftValidationError("Content draft item is invalid.")
    title = draft.heading if _non_empty_text(draft.heading) else title_override
    if not _non_empty_text(title):
        raise WordPressDraftValidationError("WordPress draft title is required.")
    rendered = tuple(_render_block(block) for block in draft.blocks)
    content = "\n".join(rendered)
    if not content:
        raise WordPressDraftValidationError("WordPress draft content is required.")
    return WordPressDraftRequest(
        title=escape(title, quote=True),
        content=content,
    )


def _render_block(block: object) -> str:
    if isinstance(block, ParagraphBlock):
        if block.kind is not DraftBlockKind.PARAGRAPH or not block.claims:
            raise WordPressDraftValidationError("Paragraph block is invalid.")
        return f"<p>{' '.join(_escaped_claim(claim) for claim in block.claims)}</p>"
    if isinstance(block, BulletListBlock):
        if block.kind is not DraftBlockKind.BULLET_LIST or not block.items:
            raise WordPressDraftValidationError("Bullet list block is invalid.")
        items = "".join(f"<li>{_escaped_claim(item)}</li>" for item in block.items)
        return f"<ul>{items}</ul>"
    if isinstance(block, ComparisonTableBlock):
        if block.kind is not DraftBlockKind.COMPARISON_TABLE:
            raise WordPressDraftValidationError("Comparison table is invalid.")
        return _render_table(block.cells)
    if isinstance(block, InternalLinkBlock):
        if block.kind is not DraftBlockKind.INTERNAL_LINK:
            raise WordPressDraftValidationError("Internal link block is invalid.")
        return _render_internal_link(block)
    raise WordPressDraftValidationError("WordPress draft block is invalid.")


def _escaped_claim(claim: object) -> str:
    if not isinstance(claim, DraftClaim) or not _non_empty_text(claim.text):
        raise WordPressDraftValidationError("WordPress draft claim is invalid.")
    return escape(claim.text, quote=True)


def _render_table(cells: tuple[TableCell, ...]) -> str:
    if not isinstance(cells, tuple) or not cells:
        raise WordPressDraftValidationError("Comparison table is invalid.")
    rows: list[str] = []
    columns: list[str] = []
    values: dict[tuple[str, str], str] = {}
    for cell in cells:
        if (
            not isinstance(cell, TableCell)
            or not _non_empty_text(cell.row_dimension)
            or not _non_empty_text(cell.column)
            or not _non_empty_text(cell.text)
        ):
            raise WordPressDraftValidationError("Comparison table is invalid.")
        key = (cell.row_dimension, cell.column)
        if key in values:
            raise WordPressDraftValidationError("Comparison table is invalid.")
        if cell.row_dimension not in rows:
            rows.append(cell.row_dimension)
        if cell.column not in columns:
            columns.append(cell.column)
        values[key] = cell.text
    if any((row, column) not in values for row in rows for column in columns):
        raise WordPressDraftValidationError("Comparison table is invalid.")

    header = '<thead><tr><th scope="col">Dimension</th>' + "".join(
        f'<th scope="col">{escape(column, quote=True)}</th>' for column in columns
    ) + "</tr></thead>"
    body = "<tbody>" + "".join(
        f'<tr><th scope="row">{escape(row, quote=True)}</th>'
        + "".join(
            f"<td>{escape(values[(row, column)], quote=True)}</td>"
            for column in columns
        )
        + "</tr>"
        for row in rows
    ) + "</tbody>"
    return f"<table>{header}{body}</table>"


def _render_internal_link(block: InternalLinkBlock) -> str:
    if not _non_empty_text(block.anchor_text):
        raise WordPressDraftValidationError("Internal link anchor is invalid.")
    target = normalize_wordpress_https_url(block.target_url)
    if target is None:
        raise WordPressDraftValidationError("Internal link target URL is invalid.")
    claims = " ".join(_escaped_claim(claim) for claim in block.insertion_claims)
    prefix = f"{claims} " if claims else ""
    return (
        f'<p>{prefix}<a href="{escape(target, quote=True)}">'
        f"{escape(block.anchor_text, quote=True)}</a></p>"
    )


def _non_empty_text(value: object) -> bool:
    return type(value) is str and bool(value.strip())
