"""Deterministic SEO audit over already-fetched crawl evidence."""

from __future__ import annotations

from urllib.parse import urlsplit

from foreign_trade_geo_agent.core.audit import (
    AuditEvidence,
    AuditEvidenceCategory,
    AuditEvidenceOutcome,
    AuditStatus,
    SiteAuditResult,
)
from foreign_trade_geo_agent.core.crawling import (
    RobotsStatus,
    SiteCrawlReport,
)
from foreign_trade_geo_agent.core.extraction import PageExtractionStatus
from foreign_trade_geo_agent.core.fetching import UrlOrigin


class CrawlSeoAuditor:
    """Score the bounded crawl sample without fetching any additional data."""

    source = "crawl-seo-audit"
    source_version = "1"

    def audit_crawl(self, report: SiteCrawlReport) -> SiteAuditResult:
        if not isinstance(report, SiteCrawlReport):
            raise TypeError("CrawlSeoAuditor requires a SiteCrawlReport.")
        successful_pages = tuple(
            page
            for page in report.pages
            if page.extraction_status is PageExtractionStatus.SUCCESS
            and page.body_text is not None
        )
        if not successful_pages:
            return SiteAuditResult(
                url=report.seed_url,
                status=AuditStatus.FAILED,
                score=None,
                band=None,
                score_breakdown={},
                recommendations=(),
                error="crawl_has_no_usable_pages",
                source=self.source,
                source_version=self.source_version,
            )

        evidence: list[AuditEvidence] = []
        failed_keys: list[str] = []

        def observe(
            category: AuditEvidenceCategory,
            key: str,
            value: bool | int | float | str | None | tuple[str, ...],
            passed: bool,
            provider_field: str,
            *,
            absent: bool = False,
        ) -> None:
            outcome = (
                AuditEvidenceOutcome.PRESENT
                if passed
                else AuditEvidenceOutcome.ABSENT
                if absent
                else AuditEvidenceOutcome.WARNING
            )
            evidence.append(
                AuditEvidence(
                    category=category,
                    check_key=key,
                    observed_value=value,
                    outcome=outcome,
                    provider_field=provider_field,
                )
            )
            if not passed:
                failed_keys.append(key)

        robots_ok = report.robots_status in {
            RobotsStatus.ALLOWED,
            RobotsStatus.NOT_FOUND,
        }
        observe(
            AuditEvidenceCategory.CRAWL,
            "crawl.robots.allowed",
            report.robots_status.value,
            robots_ok,
            "site_crawl_report.robots_status",
        )

        successful_count = len(successful_pages)
        page_count = len(report.pages)
        health_points = round(20 * successful_count / max(1, page_count))
        observe(
            AuditEvidenceCategory.CRAWL,
            "crawl.extraction.success_count",
            successful_count,
            successful_count == page_count,
            "site_crawl_report.pages.extraction_status",
        )

        titles = tuple(page.title for page in successful_pages if page.title)
        title_coverage = len(titles) == successful_count
        title_lengths_ok = title_coverage and all(10 <= len(value) <= 60 for value in titles)
        titles_unique = len({value.casefold() for value in titles}) == len(titles)
        observe(
            AuditEvidenceCategory.META,
            "meta.title.coverage",
            len(titles),
            title_coverage,
            "site_crawl_report.pages.title",
            absent=True,
        )
        observe(
            AuditEvidenceCategory.META,
            "meta.title.length",
            sum(title_lengths_ok for _ in (0,)),
            title_lengths_ok,
            "site_crawl_report.pages.title",
        )
        observe(
            AuditEvidenceCategory.META,
            "meta.title.unique",
            titles_unique,
            titles_unique,
            "site_crawl_report.pages.title",
        )

        descriptions = tuple(
            page.description for page in successful_pages if page.description
        )
        description_coverage = len(descriptions) == successful_count
        description_lengths_ok = description_coverage and all(
            50 <= len(value) <= 160 for value in descriptions
        )
        descriptions_unique = (
            len({value.casefold() for value in descriptions}) == len(descriptions)
        )
        observe(
            AuditEvidenceCategory.META,
            "meta.description.coverage",
            len(descriptions),
            description_coverage,
            "site_crawl_report.pages.description",
            absent=True,
        )
        observe(
            AuditEvidenceCategory.META,
            "meta.description.length",
            description_lengths_ok,
            description_lengths_ok,
            "site_crawl_report.pages.description",
        )
        observe(
            AuditEvidenceCategory.META,
            "meta.description.unique",
            descriptions_unique,
            descriptions_unique,
            "site_crawl_report.pages.description",
        )

        h1_ok = all(len(page.h1) == 1 for page in successful_pages)
        h2_ok = all(bool(page.h2) for page in successful_pages)
        observe(
            AuditEvidenceCategory.CONTENT,
            "content.h1.exactly_one",
            h1_ok,
            h1_ok,
            "site_crawl_report.pages.h1",
        )
        observe(
            AuditEvidenceCategory.CONTENT,
            "content.h2.present",
            h2_ok,
            h2_ok,
            "site_crawl_report.pages.h2",
            absent=True,
        )

        canonicals = tuple(
            page.canonical for page in successful_pages if page.canonical
        )
        canonical_coverage = len(canonicals) == successful_count
        valid_canonicals = sum(
            self._canonical_has_exact_origin(value, report.exact_origin)
            for value in canonicals
        )
        canonical_valid = canonical_coverage and valid_canonicals == successful_count
        canonical_unique = (
            len({value.casefold() for value in canonicals}) == len(canonicals)
        )
        observe(
            AuditEvidenceCategory.META,
            "meta.canonical.coverage",
            len(canonicals),
            canonical_coverage,
            "site_crawl_report.pages.canonical",
            absent=True,
        )
        observe(
            AuditEvidenceCategory.META,
            "meta.canonical.valid_exact_origin",
            valid_canonicals,
            canonical_valid,
            "site_crawl_report.pages.canonical",
        )
        observe(
            AuditEvidenceCategory.META,
            "meta.canonical.unique",
            canonical_unique,
            canonical_unique,
            "site_crawl_report.pages.canonical",
        )

        word_counts = tuple(len(page.body_text.split()) for page in successful_pages)
        minimum_word_count = min(word_counts)
        content_ok = minimum_word_count >= 100
        internal_link_count = sum(len(page.internal_links) for page in successful_pages)
        internal_links_ok = internal_link_count > 0
        observe(
            AuditEvidenceCategory.CONTENT,
            "content.minimum_extracted_word_count",
            minimum_word_count,
            content_ok,
            "site_crawl_report.pages.body_text",
        )
        observe(
            AuditEvidenceCategory.CONTENT,
            "content.internal_link_count",
            internal_link_count,
            internal_links_ok,
            "site_crawl_report.pages.internal_links",
            absent=True,
        )

        breakdown = {
            "crawlability": 20 if robots_ok else 0,
            "fetch_extraction_health": health_points,
            "title": (6 if title_coverage else 0)
            + (5 if title_lengths_ok else 0)
            + (4 if titles_unique else 0),
            "meta_description": (6 if description_coverage else 0)
            + (5 if description_lengths_ok else 0)
            + (4 if descriptions_unique else 0),
            "headings": (6 if h1_ok else 0) + (4 if h2_ok else 0),
            "canonical": (3 if canonical_coverage else 0)
            + (4 if canonical_valid else 0)
            + (3 if canonical_unique else 0),
            "content_internal_links": (5 if content_ok else 0)
            + (5 if internal_links_ok else 0),
        }
        score = sum(breakdown.values())
        band = "good" if score >= 80 else "needs_improvement" if score >= 50 else "poor"
        recommendations = tuple(
            self._recommendation_for(key)
            for key in dict.fromkeys(failed_keys)
        )
        return SiteAuditResult(
            url=report.seed_url,
            status=AuditStatus.SUCCESS,
            score=score,
            band=band,
            score_breakdown=breakdown,
            recommendations=recommendations,
            error=None,
            source=self.source,
            source_version=self.source_version,
            evidence=tuple(evidence),
        )

    @staticmethod
    def _canonical_has_exact_origin(
        value: str,
        exact_origin: UrlOrigin | None,
    ) -> bool:
        if exact_origin is None or type(value) is not str:
            return False
        try:
            parsed = urlsplit(value)
            if (
                parsed.hostname is None
                or parsed.username is not None
                or parsed.password is not None
            ):
                return False
            scheme = parsed.scheme.casefold()
            port = parsed.port if parsed.port is not None else (
                443 if scheme == "https" else 80 if scheme == "http" else 0
            )
            return UrlOrigin(scheme, parsed.hostname, port) == exact_origin
        except ValueError:
            return False

    @staticmethod
    def _recommendation_for(check_key: str) -> str:
        return {
            "crawl.robots.allowed": "Review the site's robots policy for public crawling.",
            "crawl.extraction.success_count": "Resolve fetch or extraction failures in the crawl sample.",
            "meta.title.coverage": "Add an observed HTML title to each sampled page.",
            "meta.title.length": "Keep sampled HTML titles between 10 and 60 characters.",
            "meta.title.unique": "Use a distinct HTML title for each sampled page.",
            "meta.description.coverage": "Add a meta description to each sampled page.",
            "meta.description.length": "Keep sampled meta descriptions between 50 and 160 characters.",
            "meta.description.unique": "Use a distinct meta description for each sampled page.",
            "content.h1.exactly_one": "Use exactly one observed H1 on each sampled page.",
            "content.h2.present": "Add an observed H2 structure where appropriate.",
            "meta.canonical.coverage": "Add a canonical URL to each sampled page.",
            "meta.canonical.valid_exact_origin": "Use valid same-origin canonical URLs.",
            "meta.canonical.unique": "Avoid duplicate canonical URLs in the crawl sample.",
            "content.minimum_extracted_word_count": "Expand thin extracted page content.",
            "content.internal_link_count": "Add relevant static same-origin internal links.",
        }[check_key]
