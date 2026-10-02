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
from .content_draft_review import (
    APPROVAL_RECORD_STATE,
    REVIEW_ACTION,
    content_draft_review_payload,
    delivery_handoff,
    render_content_draft_review_text,
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
    "APPROVAL_RECORD_STATE",
    "REVIEW_ACTION",
    "build_content_opportunity_client_report_view",
    "content_draft_review_payload",
    "delivery_handoff",
    "render_html",
    "render_content_draft_review_text",
    "render_markdown",
    "write_report",
]
