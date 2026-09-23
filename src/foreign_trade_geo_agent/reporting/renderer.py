"""Render validated business reports with trusted package templates."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Literal
from urllib.parse import quote, urlsplit

from jinja2 import (
    Environment,
    PackageLoader,
    StrictUndefined,
    TemplateError,
    select_autoescape,
)

from foreign_trade_geo_agent.core.optimization import (
    OptimizationStatus,
    SiteOptimizationReport,
)
from foreign_trade_geo_agent.core.research import ResearchReport, ResearchStatus


Report = ResearchReport | SiteOptimizationReport
OutputFormat = Literal["markdown", "html"]


class ReportRenderError(RuntimeError):
    """A controlled report validation, rendering, or write failure."""


@dataclass(frozen=True, slots=True)
class _DisplayUrl:
    text: str
    href: str | None


_MARKDOWN_SPECIAL = re.compile(r"([\\`*{}\[\]()<>#+\-!|_~])")
_MARKDOWN_ORDERED_LIST = re.compile(r"^(\s*\d+)\.", re.MULTILINE)
_MARKDOWN_LEADING_SPACES = re.compile(r"^ +", re.MULTILINE)


def _escape_markdown(value: object) -> str:
    """Escape untrusted text so it cannot introduce Markdown structure."""

    text = str(value).replace("\r", " ").replace("\n", " ").replace("\t", "    ")
    text = _MARKDOWN_SPECIAL.sub(r"\\\1", text)
    text = _MARKDOWN_ORDERED_LIST.sub(r"\1\\.", text)
    text = _MARKDOWN_LEADING_SPACES.sub(
        lambda match: "&#32;" * len(match.group(0)),
        text,
    )
    return text


def _markdown_url(value: object) -> str:
    """Encode characters that can terminate a Markdown link destination."""

    return quote(str(value), safe=":/?#[]@!$&'*+,;=%")


def _display_url(value: object) -> _DisplayUrl:
    text = str(value)
    try:
        parsed = urlsplit(text)
        port = parsed.port
    except (TypeError, ValueError):
        return _DisplayUrl(text=text, href=None)
    safe = (
        parsed.scheme.casefold() in {"http", "https"}
        and parsed.hostname is not None
        and parsed.username is None
        and parsed.password is None
        and (port is None or 0 < port < 65_536)
        and not any(character.isspace() or ord(character) < 32 for character in text)
    )
    return _DisplayUrl(text=text, href=text if safe else None)


def _environment(*, html: bool) -> Environment:
    environment = Environment(
        loader=PackageLoader("foreign_trade_geo_agent.reporting", "templates"),
        autoescape=select_autoescape(enabled_extensions=("html.j2",)) if html else False,
        undefined=StrictUndefined,
        trim_blocks=html,
        lstrip_blocks=html,
        keep_trailing_newline=True,
    )
    if not html:
        environment.filters["md"] = _escape_markdown
        environment.filters["md_url"] = _markdown_url
    return environment


def _research_context(report: ResearchReport) -> dict[str, object]:
    if report.status is not ResearchStatus.SUCCESS:
        raise ReportRenderError("Only successful research reports can be rendered.")
    if report.draft_text is None:
        raise ReportRenderError("A successful research report requires draft text.")
    return {
        "question": report.question,
        "draft_lines": report.draft_text.splitlines(),
        "sources": tuple(
            {
                "source_id": source.source_id,
                "title": source.title,
                "url": _display_url(source.url),
            }
            for source in report.sources
        ),
        "requires_human_review": report.requires_human_review,
    }


def _optimization_context(report: SiteOptimizationReport) -> dict[str, object]:
    if report.status is not OptimizationStatus.SUCCESS:
        raise ReportRenderError("Only successful site optimization reports can be rendered.")
    return {
        "site_url": _display_url(report.url),
        "recommendations": tuple(
            {
                "recommendation_id": item.recommendation_id,
                "kind": item.kind.value,
                "priority": item.priority.value,
                "target_category": (
                    None if item.target_category is None else item.target_category.value
                ),
                "site_gap_claimed": item.site_gap_claimed,
                "title": item.title,
                "rationale": item.rationale,
                "actions": item.actions,
                "audit_refs": item.audit_refs,
                "source_refs": item.source_refs,
            }
            for item in report.recommendations
        ),
        "audit_evidence": tuple(
            {
                "evidence_id": item.evidence_id,
                "category": item.evidence.category.value,
                "check_key": item.evidence.check_key,
                "observed_value": json.dumps(
                    item.evidence.observed_value,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                "outcome": item.evidence.outcome.value,
                "provider_field": item.evidence.provider_field,
                "note": item.evidence.note,
            }
            for item in report.audit_evidence
        ),
        "sources": tuple(
            {
                "source_id": source.source_id,
                "title": source.title,
                "url": _display_url(source.url),
            }
            for source in report.sources
        ),
        "limitations": report.limitations,
        "requires_human_review": report.requires_human_review,
    }


def _template_and_context(report: Report, output_format: OutputFormat) -> tuple[str, dict[str, object]]:
    extension = "html.j2" if output_format == "html" else "md.j2"
    if isinstance(report, ResearchReport):
        return f"research_report.{extension}", _research_context(report)
    if isinstance(report, SiteOptimizationReport):
        return f"site_optimization_report.{extension}", _optimization_context(report)
    raise ReportRenderError(f"Unsupported report type: {type(report).__name__}.")


def _render(report: Report, output_format: OutputFormat) -> str:
    try:
        template_name, context = _template_and_context(report, output_format)
        template = _environment(html=output_format == "html").get_template(template_name)
        return template.render(**context)
    except ReportRenderError:
        raise
    except (AttributeError, TypeError, ValueError, TemplateError) as exc:
        raise ReportRenderError("The report could not be rendered safely.") from exc


def render_markdown(report: Report) -> str:
    """Render one successful report as safe Markdown text."""

    return _render(report, "markdown")


def render_html(report: Report) -> str:
    """Render one successful report as a self-contained HTML document."""

    return _render(report, "html")


def write_report(
    report: Report,
    target_path: str | Path,
    *,
    output_format: OutputFormat,
) -> Path:
    """Fully render, then atomically replace an explicitly named target file."""

    if output_format == "markdown":
        rendered = render_markdown(report)
    elif output_format == "html":
        rendered = render_html(report)
    else:
        raise ReportRenderError(f"Unsupported report format: {output_format!r}.")

    target = Path(target_path)
    temporary_path: Path | None = None
    try:
        if not target.parent.is_dir():
            raise ReportRenderError("The report output directory does not exist.")
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(rendered)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, target)
        temporary_path = None
        return target
    except ReportRenderError:
        raise
    except OSError as exc:
        raise ReportRenderError("The rendered report could not be written atomically.") from exc
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
