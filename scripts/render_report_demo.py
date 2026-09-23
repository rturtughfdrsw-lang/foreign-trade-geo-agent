"""Generate offline Markdown and HTML reports from one fixed fake report."""

import argparse
from pathlib import Path
from collections.abc import Sequence

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
from foreign_trade_geo_agent.reporting import write_report


def _fake_report() -> SiteOptimizationReport:
    evidence = AuditEvidence(
        category=AuditEvidenceCategory.META,
        check_key="meta.description.present",
        observed_value=False,
        outcome=AuditEvidenceOutcome.ABSENT,
        provider_field="page.meta.description",
        note="The configured entry page was checked.",
    )
    return SiteOptimizationReport(
        url="https://factory.example/industrial-pumps",
        status=OptimizationStatus.SUCCESS,
        recommendations=(
            OptimizationRecommendation(
                recommendation_id="R1",
                kind=RecommendationKind.TECHNICAL_FIX,
                priority=RecommendationPriority.HIGH,
                target_category=AuditEvidenceCategory.META,
                site_gap_claimed=True,
                title="Add a specific meta description",
                rationale="The audited entry page has no meta description.",
                actions=(
                    "Draft concise copy describing the industrial pump range.",
                    "Have a human reviewer approve it before publishing.",
                ),
                audit_refs=("A1",),
                source_refs=("S1",),
            ),
        ),
        audit_evidence=(NumberedAuditEvidence("A1", evidence),),
        sources=(
            OptimizationSource(
                source_id="S1",
                title="Industrial pump buyer guide",
                url="https://source.example/industrial-pump-guide",
            ),
        ),
        error=None,
        limitations=(
            "The audit covers the configured entry URL, not every product page.",
            "External sources are research references, not official ranking signals.",
        ),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path, help="Explicit output directory")
    arguments = parser.parse_args(argv)
    arguments.output_dir.mkdir(parents=True, exist_ok=True)

    report = _fake_report()
    write_report(report, arguments.output_dir / "report.md", output_format="markdown")
    write_report(report, arguments.output_dir / "report.html", output_format="html")
    print(f"Generated {arguments.output_dir / 'report.md'}")
    print(f"Generated {arguments.output_dir / 'report.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
