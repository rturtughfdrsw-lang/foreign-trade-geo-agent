import socket
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from foreign_trade_geo_agent.core.audit import (
    AuditEvidence,
    AuditEvidenceCategory,
    AuditEvidenceOutcome,
)
from foreign_trade_geo_agent.core.optimization import (
    NumberedAuditEvidence,
    OptimizationRecommendation,
    OptimizationSource,
    OptimizationStatus,
    RecommendationKind,
    RecommendationPriority,
    SiteOptimizationReport,
)
from foreign_trade_geo_agent.core.research import (
    ResearchReport,
    ResearchSource,
    ResearchStatus,
)
from foreign_trade_geo_agent.reporting import (
    ReportRenderError,
    render_html,
    render_markdown,
    write_report,
)


def research_report(*, source_url: str = "https://source.example/report?q=valve&year=2026") -> ResearchReport:
    return ResearchReport(
        question="Industrial <valves> # outlook | 2026",
        status=ResearchStatus.SUCCESS,
        draft_text=(
            "# Model heading\n"
            "- Demand uses *special* parts [S1].\n"
            "| injected | table |\n"
            "~~~\n"
            "    indented code\n"
            "A literal `code` marker and <script>alert('draft')</script>."
        ),
        sources=(
            ResearchSource(
                source_id="S1",
                title="Buyer [guide] | <script>alert('title')</script>",
                url=source_url,
            ),
        ),
        error=None,
    )


def optimization_report(*, source_url: str = "https://source.example/guide") -> SiteOptimizationReport:
    evidence = AuditEvidence(
        category=AuditEvidenceCategory.META,
        check_key="meta.description.present",
        observed_value="<img src=x onerror=alert('evidence')>",
        outcome=AuditEvidenceOutcome.ABSENT,
        provider_field="page.meta.description",
        note="Review # entry | page",
    )
    recommendation = OptimizationRecommendation(
        recommendation_id="R1",
        kind=RecommendationKind.TECHNICAL_FIX,
        priority=RecommendationPriority.HIGH,
        target_category=AuditEvidenceCategory.META,
        site_gap_claimed=True,
        title="Add <script>alert('recommendation')</script> | metadata",
        rationale="The audited entry page lacks a useful description [A1].",
        actions=("Draft *specific* copy.", "Human review before publishing."),
        audit_refs=("A1",),
        source_refs=("S1",),
    )
    return SiteOptimizationReport(
        url="https://factory.example/products?line=pump&lang=en",
        status=OptimizationStatus.SUCCESS,
        recommendations=(recommendation,),
        audit_evidence=(NumberedAuditEvidence("A1", evidence),),
        sources=(
            OptimizationSource(
                source_id="S1",
                title="Industrial pump [buyer] guide",
                url=source_url,
            ),
        ),
        error=None,
        limitations=(
            "Entry URL only; not *all* pages.",
            "External research is not an official ranking | signal.",
        ),
    )


class ReportRendererTests(unittest.TestCase):
    def test_research_report_exports_markdown_with_source_and_review_marker(self) -> None:
        rendered = render_markdown(research_report())

        self.assertIn("# Industry Research Report", rendered)
        self.assertIn("Industrial \\<valves\\> \\# outlook \\| 2026", rendered)
        self.assertIn("[S1]", rendered)
        self.assertIn("https://source.example/report?q=valve&year=2026", rendered)
        self.assertIn("Requires human review: Yes", rendered)

    def test_site_optimization_exports_markdown_with_evidence_actions_and_limitations(self) -> None:
        rendered = render_markdown(optimization_report())

        self.assertIn("# Site Optimization Report", rendered)
        self.assertIn("HIGH", rendered)
        self.assertIn("A1", rendered)
        self.assertIn("S1", rendered)
        self.assertIn("Draft \\*specific\\* copy.", rendered)
        self.assertIn("Entry URL only; not \\*all\\* pages.", rendered)
        self.assertIn("Requires human review: Yes", rendered)

    def test_research_report_exports_html_and_escapes_untrusted_text(self) -> None:
        rendered = render_html(research_report())

        self.assertIn("<h1>Industry Research Report</h1>", rendered)
        self.assertIn("&lt;script&gt;alert(&#39;draft&#39;)&lt;/script&gt;", rendered)
        self.assertIn("&lt;script&gt;alert(&#39;title&#39;)&lt;/script&gt;", rendered)
        self.assertNotIn("<script>", rendered)
        self.assertNotIn("<img", rendered)
        self.assertNotIn("http://", rendered.split("<style>", 1)[0])

    def test_site_optimization_exports_html_with_refs_limitations_and_escaped_evidence(self) -> None:
        rendered = render_html(optimization_report())

        self.assertIn("<h1>Site Optimization Report</h1>", rendered)
        self.assertIn("A1", rendered)
        self.assertIn("S1", rendered)
        self.assertIn("Entry URL only; not *all* pages.", rendered)
        self.assertIn("&lt;img src=x onerror=alert", rendered)
        self.assertNotIn("<img", rendered)
        self.assertNotIn("<script>", rendered)

    def test_safe_source_urls_are_clickable_in_both_formats(self) -> None:
        html = render_html(research_report())
        markdown = render_markdown(research_report())

        self.assertIn(
            'href="https://source.example/report?q=valve&amp;year=2026"',
            html,
        )
        self.assertIn(
            "(https://source.example/report?q=valve&year=2026)",
            markdown,
        )

    def test_dangerous_source_url_is_plain_text_not_a_link(self) -> None:
        dangerous_url = "javascript:alert('source')"

        for report in (
            research_report(source_url=dangerous_url),
            optimization_report(source_url=dangerous_url),
        ):
            with self.subTest(report=type(report).__name__):
                html = render_html(report)
                markdown = render_markdown(report)
                self.assertIn("javascript:alert", html)
                self.assertNotIn('href="javascript:', html.casefold())
                self.assertIn("javascript:alert", markdown)
                self.assertNotIn("](javascript:", markdown.casefold())

    def test_unvalidated_identifiers_and_references_cannot_inject_markdown_links(self) -> None:
        injection = "X](javascript:alert(1))"
        research = replace(
            research_report(source_url="javascript:alert(2)"),
            sources=(
                ResearchSource(
                    source_id=injection,
                    title="source",
                    url="javascript:alert(2)",
                ),
            ),
        )
        optimization = optimization_report(source_url="javascript:alert(2)")
        optimization = replace(
            optimization,
            recommendations=(
                replace(
                    optimization.recommendations[0],
                    recommendation_id=injection,
                    audit_refs=(injection,),
                    source_refs=(injection,),
                ),
            ),
            sources=(
                OptimizationSource(
                    source_id=injection,
                    title="source",
                    url="javascript:alert(2)",
                ),
            ),
        )

        for report in (research, optimization):
            with self.subTest(report=type(report).__name__):
                rendered = render_markdown(report)
                self.assertIn("X\\]\\(javascript:alert\\(1\\)\\)", rendered)
                self.assertNotIn("](javascript:", rendered.casefold())

    def test_markdown_metacharacters_cannot_create_dynamic_structure(self) -> None:
        rendered = render_markdown(research_report())

        self.assertIn("\\# Model heading", rendered)
        self.assertIn("\\- Demand uses \\*special\\* parts \\[S1\\].", rendered)
        self.assertIn("\\| injected \\| table \\|", rendered)
        self.assertIn("\\~\\~\\~", rendered)
        self.assertIn("&#32;&#32;&#32;&#32;indented code", rendered)
        self.assertIn("A literal \\`code\\` marker", rendered)
        self.assertNotIn("\n# Model heading", rendered)
        self.assertNotIn("\n- Demand uses", rendered)
        self.assertNotIn("\n~~~", rendered)
        self.assertNotIn("\n    indented code", rendered)

    def test_unsuccessful_reports_are_rejected_without_changing_status(self) -> None:
        report = ResearchReport(
            question="topic",
            status=ResearchStatus.NO_RESULTS,
            draft_text=None,
            sources=(),
            error="No results.",
        )

        with self.assertRaises(ReportRenderError):
            render_html(report)

        self.assertIs(report.status, ResearchStatus.NO_RESULTS)
        self.assertEqual(report.error, "No results.")

    def test_missing_required_field_has_controlled_failure(self) -> None:
        malformed = object.__new__(ResearchReport)

        with self.assertRaises(ReportRenderError):
            render_markdown(malformed)

    def test_rendering_does_not_modify_original_report(self) -> None:
        report = optimization_report()
        before = repr(report)

        render_markdown(report)
        render_html(report)

        self.assertEqual(repr(report), before)

    def test_rendering_has_no_network_side_effect(self) -> None:
        with patch.object(
            socket.socket,
            "connect",
            side_effect=AssertionError("renderer attempted network access"),
        ):
            render_markdown(research_report())
            render_html(optimization_report())

    def test_write_report_atomically_writes_requested_format(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "client-report.html"

            returned = write_report(
                optimization_report(),
                target,
                output_format="html",
            )

            self.assertEqual(returned, target)
            self.assertIn("<h1>Site Optimization Report</h1>", target.read_text(encoding="utf-8"))
            self.assertEqual(list(Path(temp_dir).iterdir()), [target])

    def test_atomic_write_failure_preserves_existing_file_and_leaves_no_temporary_file(self) -> None:
        malformed = object.__new__(ResearchReport)
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "report.md"
            target.write_text("original", encoding="utf-8")

            with self.assertRaises(ReportRenderError):
                write_report(malformed, target, output_format="markdown")

            self.assertEqual(target.read_text(encoding="utf-8"), "original")
            self.assertEqual(list(Path(temp_dir).iterdir()), [target])

    def test_write_report_rejects_unknown_format_without_creating_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "report.txt"

            with self.assertRaises(ReportRenderError):
                write_report(research_report(), target, output_format="pdf")

            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
