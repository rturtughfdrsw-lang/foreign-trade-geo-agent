"""Safe, offline rendering for successful customer reports."""

from .content_opportunity_client import (
    ClientEvidenceIndexView,
    ClientOpportunityIndexView,
    ClientOpportunityView,
    ClientPageEvidenceView,
    ClientReportSummaryView,
    ClientResearchEvidenceView,
    ClientStructuredBlockView,
    ContentOpportunityClientReportError,
    ContentOpportunityClientReportInput,
    ContentOpportunityClientReportView,
    build_content_opportunity_client_report_view,
)

from .renderer import (
    ReportRenderError,
    render_html,
    render_markdown,
    write_report,
)

__all__ = [
    "ClientEvidenceIndexView",
    "ClientOpportunityIndexView",
    "ClientOpportunityView",
    "ClientPageEvidenceView",
    "ClientReportSummaryView",
    "ClientResearchEvidenceView",
    "ClientStructuredBlockView",
    "ContentOpportunityClientReportError",
    "ContentOpportunityClientReportInput",
    "ContentOpportunityClientReportView",
    "ReportRenderError",
    "build_content_opportunity_client_report_view",
    "render_html",
    "render_markdown",
    "write_report",
]
