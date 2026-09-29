import asyncio
import json
import socket
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from lxml import html as lxml_html

from foreign_trade_geo_agent.core.content_opportunity import (
    MAX_RESEARCH_SOURCES,
    ContentOpportunity,
    ContentOpportunityActionCode,
    ContentOpportunityGeneration,
    ContentOpportunityGenerationStatus,
    ContentOpportunityPage,
    ContentOpportunityPriority,
    ContentOpportunityReport,
    ContentOpportunitySource,
    ContentOpportunitySourceMaterial,
    ContentOpportunitySpecification,
    ContentOpportunityStatus,
    ContentOpportunityType,
    finalize_content_opportunity,
)
from foreign_trade_geo_agent.core.crawling import (
    CrawledPage,
    CrawlResourceStats,
    CrawlStopReason,
    LinkPriorityPolicy,
    RobotsStatus,
    SiteCrawlReport,
)
from foreign_trade_geo_agent.core.extraction import (
    PageExtractionStatus,
    StructuredContentBlock,
    StructuredContentKind,
)
from foreign_trade_geo_agent.core.fetching import UrlOrigin
from foreign_trade_geo_agent.core.research import (
    ResearchEvidenceClassification,
    ResearchEvidencePacket,
    ResearchMaterial,
    ResearchReport,
    ResearchSource,
    ResearchStatus,
)
from foreign_trade_geo_agent.core.site_content import (
    SiteContentEvidence,
    SiteContentPacket,
)
from foreign_trade_geo_agent.reporting.content_opportunity_client import (
    ContentOpportunityClientReportError,
    ContentOpportunityClientReportInput,
    build_content_opportunity_client_report_view,
)
from foreign_trade_geo_agent.reporting import (
    ReportRenderError,
    render_html,
    render_markdown,
    write_report,
)
from foreign_trade_geo_agent.workflows.content_opportunity import (
    ContentOpportunityWorkflow,
)


CLASSIFICATIONS = (
    ResearchEvidenceClassification.EXTERNAL_RESEARCH_CONTEXT,
    ResearchEvidenceClassification.UNVERIFIED_SEARCH_RESULT,
)
EXPECTED_LIMITATIONS = (
    "P evidence records observed page content only and never supports absence claims.",
    "S evidence is unverified external search context, not an authoritative or native AI-platform citation.",
    "Truncated inputs are incomplete and cannot establish that omitted content is absent.",
    "Opportunities do not guarantee rankings, AI mentions, or inquiries and require human review.",
)


def _markdown_section(rendered: str, number: int) -> str:
    start_marker = f"## {number}. "
    start = rendered.index(start_marker)
    if number == 7:
        return rendered[start:]
    end = rendered.index(f"## {number + 1}. ", start)
    return rendered[start:end]


def _markdown_entry(section: str, heading: str) -> str:
    start = section.index(heading)
    next_heading = section.find("\n### ", start + len(heading))
    if next_heading == -1:
        next_heading = section.find("\n## ", start + len(heading))
    return section[start:] if next_heading == -1 else section[start:next_heading]


def _html_text(element) -> str:
    return " ".join(" ".join(element.itertext()).split())


def _html_article(section, heading_tag: str, prefix: str):
    for article in section.xpath(".//article"):
        headings = article.xpath(f"./{heading_tag}")
        if headings and _html_text(headings[0]).startswith(prefix):
            return article
    raise AssertionError(f"Missing HTML entry: {prefix}")


class FakeContentOpportunityWriter:
    async def write_content_opportunities(self, prompt):
        return ContentOpportunityGeneration(
            provider="fake",
            model="fake-model",
            status=ContentOpportunityGenerationStatus.SUCCESS,
            text=json.dumps(
                {
                    "opportunities": [
                        {
                            "opportunity_type": "EXPAND_OBSERVED_CONTENT",
                            "priority": "HIGH",
                            "topic": "pump performance",
                            "action_codes": ["EXPAND_PAGE_SECTION"],
                            "page_refs": ["P1"],
                            "source_refs": ["S1"],
                        }
                    ]
                }
            ),
            error=None,
        )


class EmptyContentOpportunityWriter:
    async def write_content_opportunities(self, prompt):
        return ContentOpportunityGeneration(
            provider="fake",
            model="fake-model",
            status=ContentOpportunityGenerationStatus.SUCCESS,
            text=json.dumps({"opportunities": []}),
            error=None,
        )


def _crawl_page(index: int) -> CrawledPage:
    return CrawledPage(
        requested_url=f"https://example.com/p{index}",
        final_url=f"https://example.com/p{index}",
        depth=index - 1,
        http_status=200,
        content_type="text/html",
        title=f"Pump page {index}",
        description=f"Observed description {index}",
        canonical=None,
        h1=(f"Pump {index}",),
        h2=("Performance",),
        body_text=f"Observed pump performance {index}.",
        published_date=None,
        internal_links=(),
        extraction_status=PageExtractionStatus.SUCCESS,
        extraction_failure_kind=None,
        structured_content=(
            StructuredContentBlock(
                StructuredContentKind.TABLE,
                heading="Specifications",
                rows=(("Flow", "100"),),
            ),
        ),
        structured_content_truncated=index == 2,
    )


def client_input(
    *,
    opportunities: tuple[ContentOpportunity, ...] | None = None,
    packet_truncated: bool = True,
) -> ContentOpportunityClientReportInput:
    crawl_pages = (_crawl_page(1), _crawl_page(2))
    crawl = SiteCrawlReport(
        seed_url="https://example.com/p1",
        exact_origin=UrlOrigin("https", "example.com", 443),
        pages=crawl_pages,
        failures=(),
        resources=CrawlResourceStats(3, 2, 3, 0, 1000, 2000),
        robots_status=RobotsStatus.ALLOWED,
        crawl_delay=None,
        stop_reason=CrawlStopReason.COMPLETED,
        budget_exhausted=False,
        link_priority_policy=LinkPriorityPolicy.B2B_CONTENT_V1,
    )
    packet_pages = tuple(
        SiteContentEvidence(
            evidence_id=f"P{index}",
            final_url=page.final_url,
            title=page.title,
            description=page.description,
            h1=page.h1,
            h2=page.h2,
            body_text=page.body_text,
            structured_content=page.structured_content,
            extraction_status=page.extraction_status,
            extraction_failure_kind=page.extraction_failure_kind,
            structured_content_truncated=page.structured_content_truncated,
            content_truncated=index == 1,
        )
        for index, page in enumerate(crawl_pages, start=1)
    )
    packet = SiteContentPacket(
        pages=packet_pages,
        source_page_count=2,
        crawl_stop_reason=CrawlStopReason.COMPLETED,
        crawl_budget_exhausted=False,
        truncated=packet_truncated,
    )
    materials = (
        ResearchMaterial(
            "S1",
            "Pump source 1",
            "https://source.example/1",
            "Pump performance and pump selection context one.",
        ),
        ResearchMaterial(
            "S2",
            "Pump source 2",
            "http://source.example/2",
            "Pump specifications and performance context two. " + "x" * 800,
        ),
    )
    research = ResearchReport(
        question="pump research",
        status=ResearchStatus.SUCCESS,
        draft_text="Internal draft must not render [S1] [S2].",
        sources=tuple(ResearchSource(item.source_id, item.title, item.url) for item in materials),
        error=None,
        research_evidence=ResearchEvidencePacket(materials),
    )
    selected = tuple(
        ContentOpportunitySourceMaterial(
            source_id=item.source_id,
            title=item.title,
            content=item.content[:750],
            content_truncated=index == 2,
        )
        for index, item in enumerate(materials, start=1)
    )
    if opportunities is None:
        opportunities = (
            ContentOpportunity(
                "R1",
                ContentOpportunityType.EXPAND_OBSERVED_CONTENT,
                ContentOpportunityPriority.HIGH,
                "pump performance",
                "Expand observed pump performance content",
                "Observed page evidence P1 contains content related to pump performance; external research context S1 is unverified and may be considered only after human review.",
                (
                    "Review P1 and S1, then consider expanding the observed section about pump performance.",
                ),
                ("P1",),
                ("S1",),
                (ContentOpportunityActionCode.EXPAND_PAGE_SECTION,),
            ),
            ContentOpportunity(
                "R2",
                ContentOpportunityType.REORGANIZE_OBSERVED_CONTENT,
                ContentOpportunityPriority.MEDIUM,
                "pump specifications",
                "Reorganize observed pump specifications content",
                "Observed page evidence P2 contains content related to pump specifications; external research context S2 is unverified and may inform a human-reviewed reorganization.",
                (
                    "Review P2 and S2, then consider reorganizing the observed material about pump specifications.",
                ),
                ("P2",),
                ("S2",),
                (ContentOpportunityActionCode.REORGANIZE_PAGE_SECTIONS,),
            ),
            ContentOpportunity(
                "R3",
                ContentOpportunityType.NEW_SUPPORTING_CONTENT,
                ContentOpportunityPriority.LOW,
                "pump selection",
                "Consider a supporting resource about pump selection",
                "External research context S1 discusses pump selection; it is unverified and may inform consideration of a supporting resource after human review.",
                ("Review S1, then consider a supporting resource about pump selection.",),
                (),
                ("S1",),
                (ContentOpportunityActionCode.CREATE_SUPPORTING_RESOURCE,),
            ),
        )
    opportunity = ContentOpportunityReport(
        status=ContentOpportunityStatus.SUCCESS,
        opportunities=opportunities,
        pages=tuple(ContentOpportunityPage(page.evidence_id, page.final_url, page.title) for page in packet_pages),
        sources=tuple(ContentOpportunitySource(item.source_id, item.title, item.url, CLASSIFICATIONS) for item in materials),
        limitations=EXPECTED_LIMITATIONS,
        error=None,
        source_materials=selected,
        research_sources_truncated=False,
    )
    return ContentOpportunityClientReportInput(crawl, packet, research, opportunity)


async def workflow_client_input(
    *,
    source_title: str = "Pump performance source",
    source_content: str = "Pump performance context.",
    source_count: int = 1,
) -> ContentOpportunityClientReportInput:
    base = client_input(opportunities=())
    materials = tuple(
        ResearchMaterial(
            f"S{index}",
            source_title if index == 1 else f"Pump performance source {index}",
            f"https://source.example/{index}",
            source_content
            if index == 1
            else f"Pump performance context {index}.",
        )
        for index in range(1, source_count + 1)
    )
    research = ResearchReport(
        question="pump research",
        status=ResearchStatus.SUCCESS,
        draft_text="Synthetic offline research draft [S1].",
        sources=tuple(
            ResearchSource(material.source_id, material.title, material.url)
            for material in materials
        ),
        error=None,
        research_evidence=ResearchEvidencePacket(materials),
    )
    opportunity = await ContentOpportunityWorkflow(
        FakeContentOpportunityWriter()
    ).run(base.site_content_packet, research)
    if opportunity.status is not ContentOpportunityStatus.SUCCESS:
        raise AssertionError(opportunity.error)
    return replace(
        base,
        research_report=research,
        opportunity_report=opportunity,
    )


class ContentOpportunityClientReportWorkflowIntegrationTests(
    unittest.IsolatedAsyncioTestCase
):
    async def test_builder_uses_bounded_canonical_title_from_real_workflow(self) -> None:
        raw_title = "Pump performance " + "x" * 100_000
        value = await workflow_client_input(source_title=raw_title)

        view = build_content_opportunity_client_report_view(value)

        self.assertEqual(len(view.research_sources[0].title), 160)
        self.assertEqual(
            view.research_sources[0].title,
            value.opportunity_report.source_materials[0].title,
        )

    async def test_markdown_excludes_unbounded_raw_source_title(self) -> None:
        raw_title = "Pump performance " + "x" * 100_000
        value = await workflow_client_input(source_title=raw_title)

        rendered = render_markdown(value)

        self.assertNotIn(raw_title, rendered)
        self.assertIn(value.opportunity_report.source_materials[0].title, rendered)
        self.assertLess(len(rendered), len(raw_title))

    async def test_html_excludes_unbounded_raw_source_title(self) -> None:
        raw_title = "Pump performance " + "x" * 100_000
        value = await workflow_client_input(source_title=raw_title)

        rendered = render_html(value)

        self.assertNotIn(raw_title, rendered)
        self.assertIn(value.opportunity_report.source_materials[0].title, rendered)
        self.assertLess(len(rendered), len(raw_title))

    async def test_fake_provider_workflow_builds_and_renders_both_formats(self) -> None:
        value = await workflow_client_input()

        view = build_content_opportunity_client_report_view(value)
        markdown = render_markdown(value)
        html = render_html(value)

        self.assertEqual(view.summary.opportunity_count, 1)
        opportunity = view.existing_page_opportunities[0]
        self.assertIn(opportunity.title, markdown)
        self.assertIn(opportunity.title, html)
        self.assertIn("P1", markdown)
        self.assertIn("S1", html)

    async def test_ineligible_control_character_source_never_reaches_client_links(
        self,
    ) -> None:
        base = client_input(opportunities=())
        invalid_url = "https://source.example/del\x7fvalue"
        materials = (
            ResearchMaterial(
                "S1",
                "Invalid pump source",
                invalid_url,
                "Pump performance invalid context.",
            ),
            ResearchMaterial(
                "S2",
                "Valid pump source",
                "https://source.example/valid",
                "Pump performance valid context.",
            ),
        )
        research = ResearchReport(
            question="pump research",
            status=ResearchStatus.SUCCESS,
            draft_text="Synthetic offline research draft [S1] [S2].",
            sources=tuple(
                ResearchSource(item.source_id, item.title, item.url)
                for item in materials
            ),
            error=None,
            research_evidence=ResearchEvidencePacket(materials),
        )
        opportunity_report = await ContentOpportunityWorkflow(
            EmptyContentOpportunityWriter()
        ).run(base.site_content_packet, research)
        value = replace(
            base,
            research_report=research,
            opportunity_report=opportunity_report,
        )

        view = build_content_opportunity_client_report_view(value)
        markdown = render_markdown(value)
        html = render_html(value)

        self.assertEqual(
            [source.source_id for source in view.research_sources],
            ["S2"],
        )
        self.assertNotIn(invalid_url, markdown)
        self.assertNotIn("%7F", markdown)
        self.assertNotIn(invalid_url, html)
        self.assertNotIn("\x7f", html)

    async def test_real_workflow_source_whitespace_is_accepted_by_builder(self) -> None:
        cases = (
            ("  Pump performance source", "  Pump performance context."),
            ("Pump performance source  ", "Pump performance context.  "),
            (
                "Pump   performance source",
                "Pump   performance   context. " + "x" * 800,
            ),
        )

        for source_title, source_content in cases:
            with self.subTest(source_title=source_title, source_content=source_content[:40]):
                value = await workflow_client_input(
                    source_title=source_title,
                    source_content=source_content,
                )

                view = build_content_opportunity_client_report_view(value)

                self.assertEqual(
                    view.research_sources[0].title,
                    " ".join(source_title.split())[:160],
                )
                self.assertEqual(
                    view.research_sources[0].content,
                    " ".join(source_content.split())[:750],
                )

    async def test_expand_without_page_refs_is_rejected(self) -> None:
        value = await workflow_client_input()
        forged = replace(value.opportunity_report.opportunities[0], page_refs=())
        report = replace(value.opportunity_report, opportunities=(forged,))

        with self.assertRaises(ContentOpportunityClientReportError):
            build_content_opportunity_client_report_view(
                replace(value, opportunity_report=report)
            )

    async def test_expand_without_source_refs_is_rejected(self) -> None:
        value = await workflow_client_input()
        forged = replace(value.opportunity_report.opportunities[0], source_refs=())
        report = replace(value.opportunity_report, opportunities=(forged,))

        with self.assertRaises(ContentOpportunityClientReportError):
            build_content_opportunity_client_report_view(
                replace(value, opportunity_report=report)
            )

    async def test_reorganize_without_page_refs_is_rejected(self) -> None:
        value = await workflow_client_input()
        forged = replace(
            value.opportunity_report.opportunities[0],
            opportunity_type=ContentOpportunityType.REORGANIZE_OBSERVED_CONTENT,
            page_refs=(),
        )
        report = replace(value.opportunity_report, opportunities=(forged,))

        with self.assertRaises(ContentOpportunityClientReportError):
            build_content_opportunity_client_report_view(
                replace(value, opportunity_report=report)
            )

    async def test_new_content_without_source_refs_is_rejected(self) -> None:
        value = await workflow_client_input()
        forged = replace(
            value.opportunity_report.opportunities[0],
            opportunity_type=ContentOpportunityType.NEW_SUPPORTING_CONTENT,
            source_refs=(),
        )
        report = replace(value.opportunity_report, opportunities=(forged,))

        with self.assertRaises(ContentOpportunityClientReportError):
            build_content_opportunity_client_report_view(
                replace(value, opportunity_report=report)
            )

    async def test_incompatible_final_action_code_is_rejected(self) -> None:
        value = await workflow_client_input()
        forged = replace(
            value.opportunity_report.opportunities[0],
            action_codes=(ContentOpportunityActionCode.CREATE_SUPPORTING_RESOURCE,),
        )
        report = replace(value.opportunity_report, opportunities=(forged,))

        with self.assertRaises(ContentOpportunityClientReportError):
            build_content_opportunity_client_report_view(
                replace(value, opportunity_report=report)
            )

    async def test_valid_format_tampered_final_id_is_rejected(self) -> None:
        value = await workflow_client_input()
        forged = replace(
            value.opportunity_report.opportunities[0],
            recommendation_id="R7",
        )
        report = replace(value.opportunity_report, opportunities=(forged,))

        with self.assertRaises(ContentOpportunityClientReportError):
            build_content_opportunity_client_report_view(
                replace(value, opportunity_report=report)
            )

    async def test_valid_tampered_final_type_is_rejected(self) -> None:
        value = await workflow_client_input()
        forged = replace(
            value.opportunity_report.opportunities[0],
            opportunity_type=ContentOpportunityType.REORGANIZE_OBSERVED_CONTENT,
            action_codes=(
                ContentOpportunityActionCode.REORGANIZE_PAGE_SECTIONS,
            ),
        )
        report = replace(value.opportunity_report, opportunities=(forged,))

        with self.assertRaises(ContentOpportunityClientReportError):
            build_content_opportunity_client_report_view(
                replace(value, opportunity_report=report)
            )

    async def test_valid_priority_change_is_semantically_consistent(self) -> None:
        value = await workflow_client_input()
        forged = replace(
            value.opportunity_report.opportunities[0],
            priority=ContentOpportunityPriority.MEDIUM,
        )
        report = replace(value.opportunity_report, opportunities=(forged,))

        view = build_content_opportunity_client_report_view(
            replace(value, opportunity_report=report)
        )

        self.assertEqual(
            view.existing_page_opportunities[0].priority,
            "MEDIUM",
        )

    async def test_grounded_tampered_final_topic_is_rejected(self) -> None:
        value = await workflow_client_input()
        forged = replace(
            value.opportunity_report.opportunities[0],
            topic="performance context",
        )
        report = replace(value.opportunity_report, opportunities=(forged,))

        with self.assertRaises(ContentOpportunityClientReportError):
            build_content_opportunity_client_report_view(
                replace(value, opportunity_report=report)
            )

    async def test_known_tampered_final_page_refs_are_rejected(self) -> None:
        value = await workflow_client_input()
        forged = replace(
            value.opportunity_report.opportunities[0],
            page_refs=("P2",),
        )
        report = replace(value.opportunity_report, opportunities=(forged,))

        with self.assertRaises(ContentOpportunityClientReportError):
            build_content_opportunity_client_report_view(
                replace(value, opportunity_report=report)
            )

    async def test_known_tampered_final_source_refs_are_rejected(self) -> None:
        value = await workflow_client_input(source_count=2)
        forged = replace(
            value.opportunity_report.opportunities[0],
            source_refs=("S2",),
        )
        report = replace(value.opportunity_report, opportunities=(forged,))

        with self.assertRaises(ContentOpportunityClientReportError):
            build_content_opportunity_client_report_view(
                replace(value, opportunity_report=report)
            )

    async def test_compatible_tampered_final_action_codes_are_rejected(self) -> None:
        value = await workflow_client_input()
        forged = replace(
            value.opportunity_report.opportunities[0],
            action_codes=(ContentOpportunityActionCode.ADD_COMPARISON_TABLE,),
        )
        report = replace(value.opportunity_report, opportunities=(forged,))

        with self.assertRaises(ContentOpportunityClientReportError):
            build_content_opportunity_client_report_view(
                replace(value, opportunity_report=report)
            )

    async def test_ungrounded_final_topic_is_rejected(self) -> None:
        value = await workflow_client_input()
        forged = replace(
            value.opportunity_report.opportunities[0],
            topic="unrelated bearings",
        )
        report = replace(value.opportunity_report, opportunities=(forged,))

        with self.assertRaises(ContentOpportunityClientReportError):
            build_content_opportunity_client_report_view(
                replace(value, opportunity_report=report)
            )

    async def test_tampered_final_title_is_rejected(self) -> None:
        value = await workflow_client_input()
        forged = replace(value.opportunity_report.opportunities[0], title="Tampered")
        report = replace(value.opportunity_report, opportunities=(forged,))

        with self.assertRaises(ContentOpportunityClientReportError):
            build_content_opportunity_client_report_view(
                replace(value, opportunity_report=report)
            )

    async def test_tampered_final_rationale_is_rejected(self) -> None:
        value = await workflow_client_input()
        forged = replace(
            value.opportunity_report.opportunities[0],
            rationale="Tampered",
        )
        report = replace(value.opportunity_report, opportunities=(forged,))

        with self.assertRaises(ContentOpportunityClientReportError):
            build_content_opportunity_client_report_view(
                replace(value, opportunity_report=report)
            )

    async def test_tampered_final_actions_are_rejected(self) -> None:
        value = await workflow_client_input()
        forged = replace(
            value.opportunity_report.opportunities[0],
            actions=("Tampered",),
        )
        report = replace(value.opportunity_report, opportunities=(forged,))

        with self.assertRaises(ContentOpportunityClientReportError):
            build_content_opportunity_client_report_view(
                replace(value, opportunity_report=report)
            )


class ContentOpportunityClientReportBuilderTests(unittest.TestCase):
    def test_minimal_valid_input_builds_one_immutable_shared_view(self) -> None:
        view = build_content_opportunity_client_report_view(client_input())

        self.assertEqual(view.summary.site_url, "https://example.com/p1")
        self.assertEqual(view.summary.report_status, "Success")
        self.assertEqual(view.summary.crawled_page_count, 2)
        self.assertEqual(view.summary.page_evidence_count, 2)
        self.assertEqual(view.summary.eligible_source_count, 2)
        self.assertEqual(view.summary.opportunity_count, 3)
        self.assertTrue(view.summary.requires_human_review)
        self.assertEqual([page.evidence_id for page in view.pages], ["P1", "P2"])
        self.assertEqual([source.source_id for source in view.research_sources], ["S1", "S2"])

    def test_builder_precomputes_classification_counts_and_evidence_index(self) -> None:
        view = build_content_opportunity_client_report_view(client_input())

        self.assertEqual([item.recommendation_id for item in view.opportunity_index], ["R1", "R2", "R3"])
        self.assertEqual([item.recommendation_id for item in view.existing_page_opportunities], ["R1", "R2"])
        self.assertEqual([item.recommendation_id for item in view.new_supporting_content_opportunities], ["R3"])
        self.assertEqual(view.summary.opportunity_type_counts, (
            ("EXPAND_OBSERVED_CONTENT", 1),
            ("REORGANIZE_OBSERVED_CONTENT", 1),
            ("NEW_SUPPORTING_CONTENT", 1),
        ))
        self.assertEqual(view.summary.priority_counts, (("HIGH", 1), ("MEDIUM", 1), ("LOW", 1)))
        self.assertEqual(view.evidence_index.recommendations[1].page_refs, ("P2",))
        self.assertEqual(view.evidence_index.recommendations[2].source_refs, ("S1",))

    def test_zero_opportunities_preserves_empty_deterministic_sections(self) -> None:
        view = build_content_opportunity_client_report_view(client_input(opportunities=()))

        self.assertEqual(view.summary.opportunity_count, 0)
        self.assertEqual(view.opportunity_index, ())
        self.assertEqual(view.existing_page_opportunities, ())
        self.assertEqual(view.new_supporting_content_opportunities, ())
        self.assertEqual(view.evidence_index.recommendations, ())

    def test_site_url_length_boundary_is_fail_closed_without_truncation(self) -> None:
        value = client_input()
        prefix = "https://example.com/"
        at_limit = prefix + "a" * (2_048 - len(prefix))
        over_limit = prefix + "b" * (2_049 - len(prefix))
        huge = prefix + "c" * 100_000

        accepted = replace(
            value,
            site_crawl_report=replace(value.site_crawl_report, seed_url=at_limit),
        )
        rejected = replace(
            value,
            site_crawl_report=replace(value.site_crawl_report, seed_url=over_limit),
        )

        self.assertEqual(
            build_content_opportunity_client_report_view(accepted).summary.site_url,
            at_limit,
        )
        for case in (
            rejected,
            replace(
                value,
                site_crawl_report=replace(value.site_crawl_report, seed_url=huge),
            ),
        ):
            with self.subTest(length=len(case.site_crawl_report.seed_url)), self.assertRaises(
                ContentOpportunityClientReportError
            ):
                build_content_opportunity_client_report_view(case)

    def test_site_url_rejects_controls_credentials_and_unsupported_scheme(self) -> None:
        value = client_input()
        cases = (
            "https://example.com/nul\x00value",
            "https://example.com/del\x7fvalue",
            "https://user:password@example.com/p1",
            "ftp://example.com/p1",
        )

        for seed_url in cases:
            with self.subTest(seed_url=repr(seed_url)), self.assertRaises(
                ContentOpportunityClientReportError
            ):
                build_content_opportunity_client_report_view(
                    replace(
                        value,
                        site_crawl_report=replace(
                            value.site_crawl_report,
                            seed_url=seed_url,
                        ),
                    )
                )

    def test_limitations_must_match_the_deterministic_contract_exactly(self) -> None:
        value = client_input()
        cases = (
            ("Changed limitation.",) + EXPECTED_LIMITATIONS[1:],
            EXPECTED_LIMITATIONS + ("Extra limitation.",),
            EXPECTED_LIMITATIONS[:-1],
            ("x" * 100_000,),
        )

        self.assertEqual(
            build_content_opportunity_client_report_view(value).limitations,
            EXPECTED_LIMITATIONS,
        )
        for limitations in cases:
            with self.subTest(length=len(limitations)), self.assertRaises(
                ContentOpportunityClientReportError
            ):
                build_content_opportunity_client_report_view(
                    replace(
                        value,
                        opportunity_report=replace(
                            value.opportunity_report,
                            limitations=limitations,
                        ),
                    )
                )

    def test_legacy_rendered_actions_without_action_codes_are_rejected(self) -> None:
        value = client_input()
        legacy = replace(
            value.opportunity_report.opportunities[0],
            action_codes=(),
        )
        report = replace(
            value.opportunity_report,
            opportunities=(legacy,) + value.opportunity_report.opportunities[1:],
        )

        with self.assertRaises(ContentOpportunityClientReportError):
            build_content_opportunity_client_report_view(
                replace(value, opportunity_report=report)
            )

    def test_unbounded_source_identifier_is_rejected_by_upstream_packet_budget(self) -> None:
        value = client_input(opportunities=())
        source_id = "S" + "1" * 100_000
        research_material = replace(
            value.research_report.research_evidence.materials[0],
            source_id=source_id,
        )
        research = replace(
            value.research_report,
            sources=(
                replace(value.research_report.sources[0], source_id=source_id),
                value.research_report.sources[1],
            ),
            research_evidence=ResearchEvidencePacket(
                (research_material, value.research_report.research_evidence.materials[1])
            ),
        )
        source_material = replace(
            value.opportunity_report.source_materials[0],
            source_id=source_id,
        )
        display_source = replace(
            value.opportunity_report.sources[0],
            source_id=source_id,
        )
        report = replace(
            value.opportunity_report,
            source_materials=(source_material, value.opportunity_report.source_materials[1]),
            sources=(display_source, value.opportunity_report.sources[1]),
        )

        with self.assertRaises(ContentOpportunityClientReportError):
            build_content_opportunity_client_report_view(
                replace(
                    value,
                    research_report=research,
                    opportunity_report=report,
                )
            )

    def test_builder_is_deterministic_and_has_no_network_or_clock_dependency(self) -> None:
        value = client_input()
        with (
            patch.object(socket.socket, "connect", side_effect=AssertionError("network used")),
            patch.object(time, "time", side_effect=AssertionError("clock used")),
        ):
            first = build_content_opportunity_client_report_view(value)
            second = build_content_opportunity_client_report_view(value)
        self.assertEqual(first, second)

    def test_inconsistent_crawl_packet_is_rejected(self) -> None:
        value = client_input()
        broken_page = replace(value.site_content_packet.pages[0], final_url="https://example.com/other")
        broken_packet = replace(value.site_content_packet, pages=(broken_page, value.site_content_packet.pages[1]))

        with self.assertRaises(ContentOpportunityClientReportError):
            build_content_opportunity_client_report_view(replace(value, site_content_packet=broken_packet))

    def test_unknown_page_and_source_refs_are_rejected(self) -> None:
        value = client_input()
        for field, refs in (("page_refs", ("P9",)), ("source_refs", ("S9",))):
            broken_item = replace(value.opportunity_report.opportunities[0], **{field: refs})
            broken_report = replace(value.opportunity_report, opportunities=(broken_item,) + value.opportunity_report.opportunities[1:])
            with self.subTest(field=field), self.assertRaises(ContentOpportunityClientReportError):
                build_content_opportunity_client_report_view(replace(value, opportunity_report=broken_report))

    def test_duplicate_or_malformed_ids_are_rejected(self) -> None:
        value = client_input()
        duplicate_page = replace(value.site_content_packet.pages[1], evidence_id="P1")
        malformed_opportunity = replace(value.opportunity_report.opportunities[0], recommendation_id="recommendation-1")
        cases = (
            replace(value, site_content_packet=replace(value.site_content_packet, pages=(value.site_content_packet.pages[0], duplicate_page))),
            replace(value, opportunity_report=replace(value.opportunity_report, opportunities=(malformed_opportunity,) + value.opportunity_report.opportunities[1:])),
        )
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ContentOpportunityClientReportError):
                build_content_opportunity_client_report_view(case)

    def test_duplicate_opportunity_page_ids_are_rejected_before_lookup(self) -> None:
        value = client_input()
        duplicate = replace(value.opportunity_report.pages[1], evidence_id="P1")
        report = replace(
            value.opportunity_report,
            pages=(value.opportunity_report.pages[0], duplicate),
        )

        with self.assertRaises(ContentOpportunityClientReportError):
            build_content_opportunity_client_report_view(
                replace(value, opportunity_report=report)
            )

    def test_forged_opportunity_enum_is_a_controlled_validation_failure(self) -> None:
        value = client_input()
        forged = replace(
            value.opportunity_report.opportunities[0],
            opportunity_type="EXPAND_OBSERVED_CONTENT",  # type: ignore[arg-type]
        )
        report = replace(
            value.opportunity_report,
            opportunities=(forged,) + value.opportunity_report.opportunities[1:],
        )

        with self.assertRaises(ContentOpportunityClientReportError):
            build_content_opportunity_client_report_view(
                replace(value, opportunity_report=report)
            )

    def test_packet_omitting_crawl_pages_must_expose_truncation(self) -> None:
        value = client_input()
        packet = replace(
            value.site_content_packet,
            pages=(value.site_content_packet.pages[0],),
            truncated=False,
        )
        report = replace(
            value.opportunity_report,
            opportunities=(),
            pages=(value.opportunity_report.pages[0],),
        )

        with self.assertRaises(ContentOpportunityClientReportError):
            build_content_opportunity_client_report_view(
                replace(
                    value,
                    site_content_packet=packet,
                    opportunity_report=report,
                )
            )

    def test_legacy_report_missing_exact_materials_is_rejected(self) -> None:
        value = client_input()
        legacy = replace(
            value.opportunity_report,
            source_materials=(),
            research_sources_truncated=False,
        )

        with self.assertRaises(ContentOpportunityClientReportError):
            build_content_opportunity_client_report_view(replace(value, opportunity_report=legacy))

    def test_report_source_material_research_mismatch_is_rejected(self) -> None:
        value = client_input()
        mismatched = replace(value.opportunity_report.source_materials[0], content="Different context.")
        report = replace(value.opportunity_report, source_materials=(mismatched,) + value.opportunity_report.source_materials[1:])

        with self.assertRaises(ContentOpportunityClientReportError):
            build_content_opportunity_client_report_view(replace(value, opportunity_report=report))

    def test_report_source_material_title_mismatch_is_rejected(self) -> None:
        value = client_input()
        mismatched = replace(
            value.opportunity_report.source_materials[0],
            title="Different source title",
        )
        report = replace(
            value.opportunity_report,
            source_materials=(mismatched,)
            + value.opportunity_report.source_materials[1:],
        )

        with self.assertRaises(ContentOpportunityClientReportError):
            build_content_opportunity_client_report_view(
                replace(value, opportunity_report=report)
            )

    def test_report_source_selection_truncation_mismatch_is_rejected(self) -> None:
        value = client_input()
        report = replace(
            value.opportunity_report,
            research_sources_truncated=True,
        )

        with self.assertRaises(ContentOpportunityClientReportError):
            build_content_opportunity_client_report_view(
                replace(value, opportunity_report=report)
            )

    def test_cross_object_opportunity_page_and_source_metadata_mismatch_is_rejected(self) -> None:
        value = client_input()
        cases = (
            replace(value.opportunity_report, pages=(replace(value.opportunity_report.pages[0], final_url="https://example.com/wrong"),) + value.opportunity_report.pages[1:]),
            replace(value.opportunity_report, sources=(replace(value.opportunity_report.sources[0], title="Different bounded title"),) + value.opportunity_report.sources[1:]),
            replace(value.opportunity_report, sources=(replace(value.opportunity_report.sources[0], url="https://source.example/wrong"),) + value.opportunity_report.sources[1:]),
        )
        for report in cases:
            with self.subTest(report=report), self.assertRaises(ContentOpportunityClientReportError):
                build_content_opportunity_client_report_view(replace(value, opportunity_report=report))

    def test_unsuccessful_required_workflow_objects_are_rejected(self) -> None:
        value = client_input()
        failed_research = ResearchReport("q", ResearchStatus.NO_RESULTS, None, (), "No results.")
        failed_opportunity = ContentOpportunityReport(ContentOpportunityStatus.GENERATION_FAILED, (), (), (), (), "failed")
        for case in (
            replace(value, research_report=failed_research),
            replace(value, opportunity_report=failed_opportunity),
        ):
            with self.subTest(case=case), self.assertRaises(ContentOpportunityClientReportError):
                build_content_opportunity_client_report_view(case)

    def test_upstream_budget_violation_is_rejected_without_report_truncation(self) -> None:
        value = client_input()
        too_many = tuple(value.opportunity_report.source_materials[0] for _ in range(MAX_RESEARCH_SOURCES + 1))
        report = replace(value.opportunity_report, source_materials=too_many)

        with self.assertRaises(ContentOpportunityClientReportError):
            build_content_opportunity_client_report_view(replace(value, opportunity_report=report))

    def test_zero_eligible_sources_is_rejected(self) -> None:
        value = client_input(opportunities=())
        report = replace(
            value.opportunity_report,
            source_materials=(),
            research_sources_truncated=False,
        )

        with self.assertRaises(ContentOpportunityClientReportError):
            build_content_opportunity_client_report_view(replace(value, opportunity_report=report))

    def test_unsafe_or_cross_origin_urls_are_rejected(self) -> None:
        value = client_input()
        cases = (
            replace(value.site_crawl_report, seed_url="javascript:alert(1)"),
            replace(value.site_crawl_report, seed_url="https://user:pass@example.com/p1"),
            replace(value.site_crawl_report, seed_url="https://example.com/control\nchar"),
            replace(value.site_crawl_report, seed_url="https://example.com:bad/p1"),
            replace(value.site_content_packet.pages[0], final_url="https://other.example/p1"),
        )
        for case in cases[:4]:
            with self.subTest(case=case), self.assertRaises(ContentOpportunityClientReportError):
                build_content_opportunity_client_report_view(replace(value, site_crawl_report=case))
        packet = replace(value.site_content_packet, pages=(cases[4], value.site_content_packet.pages[1]))
        with self.assertRaises(ContentOpportunityClientReportError):
            build_content_opportunity_client_report_view(replace(value, site_content_packet=packet))

    def test_raw_or_duplicate_source_inputs_are_rejected(self) -> None:
        with self.assertRaises(ContentOpportunityClientReportError):
            build_content_opportunity_client_report_view({"raw": "provider output"})  # type: ignore[arg-type]

        value = client_input()
        duplicate_materials = (value.opportunity_report.source_materials[0],) * 2
        duplicate_sources = (value.opportunity_report.sources[0],) * 2
        report = replace(
            value.opportunity_report,
            source_materials=duplicate_materials,
            sources=duplicate_sources,
        )
        with self.assertRaises(ContentOpportunityClientReportError):
            build_content_opportunity_client_report_view(replace(value, opportunity_report=report))


class ContentOpportunityClientReportRendererTests(unittest.TestCase):
    def test_public_renderer_rejects_manually_constructed_view(self) -> None:
        view = build_content_opportunity_client_report_view(
            asyncio.run(workflow_client_input())
        )

        for render in (render_markdown, render_html):
            with self.subTest(render=render.__name__), self.assertRaises(
                ReportRenderError
            ):
                render(view)  # type: ignore[arg-type]

    def test_public_renderer_rejects_forged_failed_view(self) -> None:
        view = build_content_opportunity_client_report_view(
            asyncio.run(workflow_client_input())
        )
        forged = replace(view, summary=replace(view.summary, report_status="Failure"))

        with self.assertRaises(ReportRenderError):
            render_markdown(forged)  # type: ignore[arg-type]

    def test_public_renderer_rejects_unbounded_view(self) -> None:
        view = build_content_opportunity_client_report_view(
            asyncio.run(workflow_client_input())
        )
        unbounded_source = replace(view.research_sources[0], content="x" * 100_000)
        forged = replace(view, research_sources=(unbounded_source,))

        with self.assertRaises(ReportRenderError):
            render_html(forged)  # type: ignore[arg-type]

    def test_zero_opportunity_report_renders_without_fabricating_recommendations(self) -> None:
        value = client_input(opportunities=())

        markdown = render_markdown(value)
        html = render_html(value)

        self.assertIn("No validated opportunities", markdown)
        self.assertIn("No validated opportunities", html)
        self.assertNotIn("#### R1", markdown)
        self.assertNotIn("<h4>R1", html)

    def test_markdown_renders_all_seven_sections_and_workflow_fields_once(self) -> None:
        rendered = render_markdown(client_input())

        for heading in (
            "## 1. Executive Summary",
            "## 2. Scope and Method",
            "## 3. Website Content Observed",
            "## 4. External Research Context",
            "## 5. Content Opportunities",
            "## 6. Evidence Index",
            "## 7. Limitations and Human Review",
        ):
            self.assertIn(heading, rendered)
        self.assertIn(r"R1 / EXPAND\_OBSERVED\_CONTENT / HIGH / pump performance", rendered)
        self.assertEqual(rendered.count("### R1 — Expand observed pump performance content"), 1)
        self.assertIn(EXPECTED_LIMITATIONS[0], rendered)
        self.assertIn("Report status: Success", rendered)
        self.assertIn("Requires human review: Yes", rendered)
        self.assertNotIn("Internal draft must not render", rendered)

    def test_markdown_escapes_hostile_unicode_text_and_dynamic_urls(self) -> None:
        hostile = "# 标题 `code` [x](javascript:alert(1)) <script> | pipe\nnext"
        hostile_page_title = " ".join(hostile.split())
        value = client_input()
        crawl_page = replace(value.site_crawl_report.pages[0], title=hostile_page_title)
        crawl = replace(value.site_crawl_report, pages=(crawl_page,) + value.site_crawl_report.pages[1:])
        packet_page = replace(value.site_content_packet.pages[0], title=hostile_page_title, body_text=hostile)
        packet = replace(value.site_content_packet, pages=(packet_page,) + value.site_content_packet.pages[1:])
        opportunity_page = replace(value.opportunity_report.pages[0], title=hostile_page_title)
        report = replace(
            value.opportunity_report,
            pages=(opportunity_page,) + value.opportunity_report.pages[1:],
            limitations=EXPECTED_LIMITATIONS,
        )
        hostile_input = replace(value, site_crawl_report=crawl, site_content_packet=packet, opportunity_report=report)

        rendered = render_markdown(hostile_input)

        self.assertIn("\\# 标题 \\`code\\` \\[x\\]\\(javascript:alert\\(1\\)\\) \\<script\\> \\| pipe next", rendered)
        self.assertNotIn("\n# 标题", rendered)
        self.assertNotIn("](javascript:", rendered)

    def test_html_renders_all_sections_autoescapes_and_has_no_remote_resources_or_script(self) -> None:
        hostile = "<script>alert('x')</script><img src=x onerror=alert(1)> 中文"
        value = asyncio.run(
            workflow_client_input(
                source_title=f"Pump performance {hostile}",
                source_content=f"Pump performance context {hostile}",
            )
        )
        rendered = render_html(value)

        for number in range(1, 8):
            self.assertIn(f'<section id="section-{number}">', rendered)
        self.assertIn("&lt;script&gt;alert(&#39;x&#39;)&lt;/script&gt;", rendered)
        self.assertNotIn("<script", rendered.casefold())
        self.assertNotIn("<img", rendered.casefold())
        self.assertNotIn("@import", rendered.casefold())
        self.assertNotIn("https://fonts", rendered.casefold())
        self.assertNotIn("<link", rendered.casefold())
        self.assertIn('rel="noopener noreferrer"', rendered)

    def test_truncation_indicators_are_customer_visible_in_both_formats(self) -> None:
        value = asyncio.run(
            workflow_client_input(
                source_content="Pump performance " + "x" * 800,
                source_count=5,
            )
        )

        for rendered in (render_markdown(value), render_html(value)):
            self.assertIn("Site content packet selection was truncated", rendered)
            self.assertIn("Page content was truncated", rendered)
            self.assertIn("Structured content was truncated", rendered)
            self.assertIn("Research source selection was truncated", rendered)
            self.assertIn("Source content was truncated", rendered)

    def test_markdown_and_html_share_all_semantic_fields_from_real_workflow_input(self) -> None:
        value = asyncio.run(
            workflow_client_input(
                source_content="Pump performance " + "x" * 800,
                source_count=5,
            )
        )
        view = build_content_opportunity_client_report_view(value)
        markdown = render_markdown(value)
        html = render_html(value)
        markdown = (
            markdown.replace("\\_", "_")
            .replace("\\-", "-")
            .replace("\\#", "#")
        )
        markdown_sections = {
            number: _markdown_section(markdown, number)
            for number in range(1, 8)
        }
        document = lxml_html.fromstring(html)
        html_sections = {
            number: document.get_element_by_id(f"section-{number}")
            for number in range(1, 8)
        }

        summary_values = (
            (
                f"Crawled page count: {view.summary.crawled_page_count}",
                f"Crawled page count {view.summary.crawled_page_count}",
            ),
            (
                f"P# evidence count: {view.summary.page_evidence_count}",
                f"P# evidence count {view.summary.page_evidence_count}",
            ),
            (
                f"Eligible S# count: {view.summary.eligible_source_count}",
                f"Eligible S# count {view.summary.eligible_source_count}",
            ),
            (
                f"R# opportunity count: {view.summary.opportunity_count}",
                f"R# opportunity count {view.summary.opportunity_count}",
            ),
            ("Requires human review: Yes", "Requires human review Yes"),
            *(
                (f"{label}: {count}", f"{label}: {count}")
                for label, count in view.summary.opportunity_type_counts
            ),
            *(
                (f"{label}: {count}", f"{label}: {count}")
                for label, count in view.summary.priority_counts
            ),
        )
        html_summary = _html_text(html_sections[1])
        for markdown_expected, html_expected in summary_values:
            with self.subTest(section="summary", expected=markdown_expected):
                self.assertIn(markdown_expected, markdown_sections[1])
                self.assertIn(html_expected, html_summary)

        self.assertIn(view.summary.site_url, markdown_sections[1])
        self.assertIn(
            view.summary.site_url,
            html_sections[1].xpath(".//a/@href"),
        )

        for page in view.pages:
            title = page.title or "Untitled page"
            markdown_entry = _markdown_entry(
                markdown_sections[3],
                f"### {page.evidence_id} — {title}",
            )
            html_entry = _html_article(
                html_sections[3],
                "h3",
                f"{page.evidence_id} — {title}",
            )
            html_entry_text = _html_text(html_entry)
            for expected in (page.evidence_id, title, page.url):
                self.assertIn(expected, markdown_entry)
                self.assertIn(expected, html_entry_text)
            self.assertIn(page.url, html_entry.xpath(".//a/@href"))
            if page.content_truncated:
                self.assertIn("Page content was truncated upstream", markdown_entry)
                self.assertIn("Page content was truncated upstream", html_entry_text)
            if page.structured_content_truncated:
                self.assertIn("Structured content was truncated upstream", markdown_entry)
                self.assertIn("Structured content was truncated upstream", html_entry_text)

        self.assertIn(
            "Site content packet selection was truncated upstream",
            markdown_sections[3],
        )
        self.assertIn(
            "Site content packet selection was truncated upstream",
            _html_text(html_sections[3]),
        )

        for source in view.research_sources:
            markdown_entry = _markdown_entry(
                markdown_sections[4],
                f"### {source.source_id} — {source.title}",
            )
            html_entry = _html_article(
                html_sections[4],
                "h3",
                f"{source.source_id} — {source.title}",
            )
            html_entry_text = _html_text(html_entry)
            for expected in (
                source.source_id,
                source.title,
                source.url,
                source.content,
                *source.classifications,
            ):
                self.assertIn(expected, markdown_entry)
                self.assertIn(expected, html_entry_text)
            self.assertIn(source.url, html_entry.xpath(".//a/@href"))
            if source.content_truncated:
                self.assertIn("Source content was truncated upstream", markdown_entry)
                self.assertIn("Source content was truncated upstream", html_entry_text)

        self.assertIn(
            "Research source selection was truncated upstream",
            markdown_sections[4],
        )
        self.assertIn(
            "Research source selection was truncated upstream",
            _html_text(html_sections[4]),
        )

        opportunities = (
            *view.existing_page_opportunities,
            *view.new_supporting_content_opportunities,
        )
        for item in opportunities:
            markdown_entry = _markdown_entry(
                markdown_sections[5],
                f"#### {item.recommendation_id} — {item.title}",
            )
            html_entry = _html_article(
                html_sections[5],
                "h4",
                f"{item.recommendation_id} — {item.title}",
            )
            html_entry_text = _html_text(html_entry)
            for expected in (
                item.recommendation_id,
                item.topic,
                item.title,
                item.rationale,
                *item.actions,
                *item.page_refs,
                *item.source_refs,
            ):
                self.assertIn(expected, markdown_entry)
                self.assertIn(expected, html_entry_text)

        evidence_markdown = markdown_sections[6]
        evidence_html = _html_text(html_sections[6])
        for page in view.evidence_index.pages:
            expected = f"{page.evidence_id} — {page.title or 'Untitled page'}"
            self.assertIn(expected, evidence_markdown)
            self.assertIn(expected, evidence_html)
            self.assertIn(page.url, evidence_markdown)
            self.assertIn(page.url, html_sections[6].xpath(".//a/@href"))
        for source in view.evidence_index.sources:
            expected = f"{source.source_id} — {source.title}"
            self.assertIn(expected, evidence_markdown)
            self.assertIn(expected, evidence_html)
            self.assertIn(source.url, evidence_markdown)
            self.assertIn(source.url, html_sections[6].xpath(".//a/@href"))
        for item in view.evidence_index.recommendations:
            expected = (
                f"{item.recommendation_id} — P# refs: "
                f"{', '.join(item.page_refs) or 'None'}; S# refs: "
                f"{', '.join(item.source_refs) or 'None'}"
            )
            self.assertIn(expected, evidence_markdown)
            self.assertIn(expected, evidence_html)

        limitations_html = _html_text(html_sections[7])
        for limitation in view.limitations:
            self.assertIn(limitation, markdown_sections[7])
            self.assertIn(limitation, limitations_html)
        self.assertIn("Requires human review: Yes", markdown_sections[7])
        self.assertIn("Requires human review: Yes", limitations_html)

    def test_renderer_rejects_unsafe_input_url_and_does_not_use_network(self) -> None:
        value = client_input()
        unsafe = replace(
            value,
            site_crawl_report=replace(
                value.site_crawl_report,
                seed_url="data:text/html,unsafe",
            ),
        )
        with patch.object(socket.socket, "connect", side_effect=AssertionError("network used")):
            with self.assertRaises(ReportRenderError):
                render_html(unsafe)
            with self.assertRaises(ReportRenderError):
                render_markdown(unsafe)

    def test_client_urls_are_safely_encoded_in_both_formats(self) -> None:
        value = client_input()
        crawl = replace(value.site_crawl_report, seed_url="https://example.com/p1?q=pump&lang=中文")
        value = replace(value, site_crawl_report=crawl)

        markdown = render_markdown(value)
        html = render_html(value)

        self.assertIn("(https://example.com/p1?q=pump&lang=%E4%B8%AD%E6%96%87)", markdown)
        self.assertIn('href="https://example.com/p1?q=pump&amp;lang=中文"', html)

    def test_rendering_is_deterministic_for_valid_input(self) -> None:
        value = client_input()

        with (
            patch.object(socket.socket, "connect", side_effect=AssertionError("network used")),
            patch.object(time, "time", side_effect=AssertionError("clock used")),
        ):
            self.assertEqual(render_markdown(value), render_markdown(value))
            self.assertEqual(render_html(value), render_html(value))

    def test_write_report_uses_utf8_lf_and_atomic_explicit_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "客户报告.md"
            target.write_text("old", encoding="utf-8")

            returned = write_report(client_input(), target, output_format="markdown")
            raw = target.read_bytes()

            self.assertEqual(returned, target)
            self.assertTrue(raw.startswith(b"# https://example.com/p1 Content Opportunity Report"))
            self.assertIn(EXPECTED_LIMITATIONS[0].encode("utf-8"), raw)
            self.assertNotIn(b"\r\n", raw)
            self.assertEqual(list(Path(temp_dir).iterdir()), [target])

    def test_worst_case_upstream_bounded_input_has_stable_output_ceiling(self) -> None:
        base = client_input()
        crawl_pages = tuple(
            replace(
                _crawl_page(index),
                body_text=(f"Observed page {index} " + "页" * 580),
            )
            for index in range(1, 6)
        )
        crawl = replace(base.site_crawl_report, pages=crawl_pages)
        packet_pages = tuple(
            SiteContentEvidence(
                evidence_id=f"P{index}",
                final_url=page.final_url,
                title=page.title,
                description=page.description,
                h1=page.h1,
                h2=page.h2,
                body_text=page.body_text,
                structured_content=page.structured_content,
                extraction_status=page.extraction_status,
                extraction_failure_kind=page.extraction_failure_kind,
                structured_content_truncated=page.structured_content_truncated,
                content_truncated=True,
            )
            for index, page in enumerate(crawl_pages, start=1)
        )
        packet = replace(base.site_content_packet, pages=packet_pages, source_page_count=5)
        materials = tuple(
            ResearchMaterial(
                f"S{index}",
                f"Source {index}",
                f"https://source.example/{index}",
                "pump performance " + chr(96 + index) * 733,
            )
            for index in range(1, 5)
        )
        research = replace(
            base.research_report,
            sources=tuple(ResearchSource(item.source_id, item.title, item.url) for item in materials),
            research_evidence=ResearchEvidencePacket(materials),
        )
        selected = tuple(ContentOpportunitySourceMaterial(item.source_id, item.title, item.content, False) for item in materials)
        recommendations = tuple(
            finalize_content_opportunity(
                index,
                ContentOpportunitySpecification(
                    opportunity_type=ContentOpportunityType.EXPAND_OBSERVED_CONTENT,
                    priority=ContentOpportunityPriority.HIGH,
                    topic="pump performance",
                    action_codes=(ContentOpportunityActionCode.EXPAND_PAGE_SECTION,),
                    page_refs=(f"P{index}",),
                    source_refs=(f"S{index}",),
                ),
            )
            for index in range(1, 5)
        )
        report = replace(
            base.opportunity_report,
            pages=tuple(ContentOpportunityPage(page.evidence_id, page.final_url, page.title) for page in packet_pages),
            sources=tuple(ContentOpportunitySource(item.source_id, item.title, item.url, CLASSIFICATIONS) for item in materials),
            source_materials=selected,
            opportunities=recommendations,
        )
        value = ContentOpportunityClientReportInput(crawl, packet, research, report)

        markdown = render_markdown(value)
        html = render_html(value)

        self.assertLess(len(markdown.encode("utf-8")), 100_000)
        self.assertLess(len(html.encode("utf-8")), 120_000)
        self.assertEqual(markdown, render_markdown(value))
        self.assertEqual(html, render_html(value))
        for marker in ("P5", "S4", "R4", "d" * 100):
            self.assertIn(marker, markdown)
            self.assertIn(marker, html)


if __name__ == "__main__":
    unittest.main()
