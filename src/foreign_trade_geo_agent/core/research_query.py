"""Deterministic research queries built from bounded crawl evidence."""

from __future__ import annotations

from urllib.parse import urlsplit

from .crawling import SiteCrawlReport
from .extraction import PageExtractionStatus


def build_research_query(
    crawl: SiteCrawlReport,
    seo_goal: str,
    *,
    max_chars: int = 300,
) -> str:
    """Build one bounded query without asking a model to interpret site text."""

    if not isinstance(crawl, SiteCrawlReport):
        raise TypeError("Research query requires a SiteCrawlReport.")
    if type(seo_goal) is not str:
        raise ValueError("SEO goal must be a string.")
    goal = " ".join(seo_goal.split())
    if not goal:
        raise ValueError("SEO goal must not be empty.")
    if type(max_chars) is not int or max_chars <= 0:
        raise ValueError("max_chars must be a positive integer.")

    hostname = (
        crawl.exact_origin.host
        if crawl.exact_origin is not None
        else urlsplit(crawl.seed_url).hostname
    )
    if not hostname:
        raise ValueError("Crawl report has no hostname identity.")

    parts = [hostname]
    first_success = next(
        (
            page
            for page in crawl.pages
            if page.extraction_status is PageExtractionStatus.SUCCESS
        ),
        None,
    )
    if first_success is not None:
        title = " ".join((first_success.title or "").split())
        if title:
            parts.append(f"title: {title}")
        if first_success.h1:
            h1 = " ".join(first_success.h1[0].split())
            if h1:
                parts.append(f"h1: {h1}")
    parts.append(f"goal: {goal}")
    return " | ".join(parts)[:max_chars].rstrip()
