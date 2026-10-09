from unittest.mock import patch
import unittest

from foreign_trade_geo_agent.core.audit import (
    AuditEvidenceOutcome,
    AuditStatus,
)
from foreign_trade_geo_agent.core.crawling import (
    CrawledPage,
    CrawlFailure,
    CrawlFailureKind,
    CrawlFailureStage,
    CrawlResourceStats,
    CrawlStopReason,
    LinkPriorityPolicy,
    RobotsStatus,
    SiteCrawlReport,
)
from foreign_trade_geo_agent.core.extraction import (
    PageExtractionFailureKind,
    PageExtractionStatus,
)
from foreign_trade_geo_agent.core.fetching import UrlOrigin
from foreign_trade_geo_agent.workflows.crawl_seo_audit import CrawlSeoAuditor


def page(
    path: str,
    *,
    title: str | None = "Industrial Pump Selection Guide",
    description: str | None = (
        "A practical industrial pump selection guide for international buyers."
    ),
    canonical: str | None = None,
    h1: tuple[str, ...] = ("Industrial Pump Selection",),
    h2: tuple[str, ...] = ("Selection criteria",),
    body_text: str | None = None,
    internal_links: tuple[str, ...] = ("https://example.com/contact",),
    extraction_status: PageExtractionStatus = PageExtractionStatus.SUCCESS,
) -> CrawledPage:
    url = f"https://example.com{path}"
    return CrawledPage(
        requested_url=url,
        final_url=url,
        depth=0,
        http_status=200,
        content_type="text/html",
        title=title,
        description=description,
        canonical=url if canonical is None else canonical,
        h1=h1,
        h2=h2,
        body_text=("word " * 120).strip() if body_text is None else body_text,
        published_date=None,
        internal_links=internal_links,
        extraction_status=extraction_status,
        extraction_failure_kind=(
            None
            if extraction_status is PageExtractionStatus.SUCCESS
            else PageExtractionFailureKind.EXTRACTION_FAILED
        ),
    )


def report(*pages: CrawledPage, failures: tuple[CrawlFailure, ...] = ()) -> SiteCrawlReport:
    return SiteCrawlReport(
        seed_url="https://example.com/",
        exact_origin=UrlOrigin("https", "example.com", 443),
        pages=tuple(pages),
        failures=failures,
        resources=CrawlResourceStats(1, len(pages), len(pages) + 1, 0, 500, 500),
        robots_status=RobotsStatus.ALLOWED,
        crawl_delay=None,
        stop_reason=CrawlStopReason.COMPLETED,
        budget_exhausted=False,
        link_priority_policy=LinkPriorityPolicy.B2B_CONTENT_V1,
    )


def evidence_by_key(result: object, key: str):
    return next(item for item in result.evidence if item.check_key == key)


class CrawlSeoAuditorTests(unittest.TestCase):
    def test_scores_only_fields_present_in_successful_crawl_pages(self) -> None:
        failed = page(
            "/failed",
            title=None,
            description=None,
            canonical="",
            h1=(),
            h2=(),
            body_text=None,
            internal_links=(),
            extraction_status=PageExtractionStatus.FAILED,
        )

        result = CrawlSeoAuditor().audit_crawl(report(page("/"), failed))

        self.assertEqual(result.status, AuditStatus.SUCCESS)
        self.assertEqual(
            evidence_by_key(result, "meta.title.coverage").outcome,
            AuditEvidenceOutcome.PRESENT,
        )
        self.assertEqual(
            evidence_by_key(result, "meta.description.coverage").outcome,
            AuditEvidenceOutcome.PRESENT,
        )

    def test_failed_extraction_is_not_reported_as_missing_metadata(self) -> None:
        failed = page(
            "/failed",
            title=None,
            description=None,
            body_text=None,
            extraction_status=PageExtractionStatus.FAILED,
        )

        result = CrawlSeoAuditor().audit_crawl(report(page("/"), failed))

        self.assertEqual(
            evidence_by_key(result, "crawl.extraction.success_count").observed_value,
            1,
        )
        self.assertFalse(
            any(
                item.outcome is AuditEvidenceOutcome.ABSENT
                and item.check_key.startswith("meta.")
                for item in result.evidence
            )
        )

    def test_detects_duplicate_title_description_and_canonical_in_bounded_sample(self) -> None:
        first = page("/", canonical="https://example.com/canonical")
        second = page("/products", canonical="https://example.com/canonical")

        result = CrawlSeoAuditor().audit_crawl(report(first, second))

        for key in (
            "meta.title.unique",
            "meta.description.unique",
            "meta.canonical.unique",
        ):
            self.assertEqual(
                evidence_by_key(result, key).outcome,
                AuditEvidenceOutcome.WARNING,
            )

    def test_canonical_is_checked_for_syntax_and_exact_origin(self) -> None:
        invalid = page("/invalid", canonical="not a url")
        external = page("/external", canonical="https://other.example/page")

        result = CrawlSeoAuditor().audit_crawl(report(invalid, external))

        self.assertEqual(
            evidence_by_key(result, "meta.canonical.valid_exact_origin").outcome,
            AuditEvidenceOutcome.WARNING,
        )
        self.assertEqual(
            evidence_by_key(result, "meta.canonical.valid_exact_origin").observed_value,
            0,
        )

    def test_word_count_uses_extracted_body_only(self) -> None:
        crawled = page(
            "/",
            h1=("heading words are not body words",),
            body_text="one two three four",
        )

        result = CrawlSeoAuditor().audit_crawl(report(crawled))

        self.assertEqual(
            evidence_by_key(result, "content.minimum_extracted_word_count").observed_value,
            4,
        )

    def test_internal_link_check_uses_crawled_page_links(self) -> None:
        crawled = page(
            "/",
            internal_links=(
                "https://example.com/a",
                "https://example.com/b",
            ),
        )

        result = CrawlSeoAuditor().audit_crawl(report(crawled))

        self.assertEqual(
            evidence_by_key(result, "content.internal_link_count").observed_value,
            2,
        )

    def test_evidence_and_breakdown_sum_to_transparent_score(self) -> None:
        result = CrawlSeoAuditor().audit_crawl(report(page("/")))

        self.assertEqual(result.score_breakdown, {
            "crawlability": 20,
            "fetch_extraction_health": 20,
            "title": 15,
            "meta_description": 15,
            "headings": 10,
            "canonical": 10,
            "content_internal_links": 10,
        })
        self.assertEqual(result.score, sum(result.score_breakdown.values()))
        self.assertEqual(result.score, 100)
        self.assertEqual(result.band, "good")
        self.assertTrue(
            all(
                item.provider_field.startswith("site_crawl_report.")
                for item in result.evidence
            )
        )

    def test_does_not_claim_schema_open_graph_noindex_noai_or_llms(self) -> None:
        result = CrawlSeoAuditor().audit_crawl(report(page("/")))

        serialized_keys = " ".join(item.check_key for item in result.evidence).lower()
        for unsupported in ("schema", "open_graph", "noindex", "noai", "llms"):
            self.assertNotIn(unsupported, serialized_keys)

    def test_audit_performs_no_network_access(self) -> None:
        with patch("socket.getaddrinfo", side_effect=AssertionError("network")):
            result = CrawlSeoAuditor().audit_crawl(report(page("/")))

        self.assertEqual(result.status, AuditStatus.SUCCESS)


if __name__ == "__main__":
    unittest.main()
