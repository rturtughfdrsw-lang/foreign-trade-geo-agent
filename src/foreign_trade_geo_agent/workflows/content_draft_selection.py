"""Shared loading of one persisted content draft and exact D# selection."""

from __future__ import annotations

from foreign_trade_geo_agent.core.content_draft import (
    ContentDraftReport,
    ContentDraftStatus,
    DraftItem,
)
from foreign_trade_geo_agent.core.history import ArtifactRecord, ArtifactType
from foreign_trade_geo_agent.core.ports import HistoryReader


SUPPORTED_CONTENT_DRAFT_PAYLOAD_VERSION = 1


class ContentDraftSelectionError(ValueError):
    """A persisted content-draft artifact or one D# selection is unusable."""


def validate_persisted_content_draft_report(
    artifact: ArtifactRecord | None,
    *,
    planning_run_id: str,
) -> ContentDraftReport:
    """Validate one already-loaded CONTENT_DRAFT artifact for a run."""

    if (
        not isinstance(artifact, ArtifactRecord)
        or artifact.run_id != planning_run_id
        or artifact.artifact_type is not ArtifactType.CONTENT_DRAFT
        or artifact.payload_version
        != SUPPORTED_CONTENT_DRAFT_PAYLOAD_VERSION
        or not isinstance(artifact.payload, ContentDraftReport)
    ):
        raise ContentDraftSelectionError(
            "Persisted content draft artifact is invalid."
        )
    payload = artifact.payload
    try:
        report = ContentDraftReport(
            status=payload.status,
            drafts=payload.drafts,
            limitations=payload.limitations,
            error=payload.error,
            requires_human_review=payload.requires_human_review,
        )
    except (AttributeError, TypeError, ValueError):
        raise ContentDraftSelectionError(
            "Persisted content draft artifact is invalid."
        ) from None
    if report.status is not ContentDraftStatus.SUCCESS:
        raise ContentDraftSelectionError(
            "Persisted content draft report is not successful."
        )
    if not all(isinstance(draft, DraftItem) for draft in report.drafts):
        raise ContentDraftSelectionError(
            "Persisted content draft artifact is invalid."
        )
    return report


def load_persisted_content_draft_report(
    history_reader: HistoryReader,
    *,
    planning_run_id: str,
    content_draft_artifact_id: str,
) -> ContentDraftReport:
    """Load and validate one persisted CONTENT_DRAFT artifact fail-closed."""

    artifact = history_reader.get_artifact(content_draft_artifact_id)
    return validate_persisted_content_draft_report(
        artifact,
        planning_run_id=planning_run_id,
    )


def select_content_draft(report: ContentDraftReport, draft_id: str) -> DraftItem:
    """Select exactly one D# by exact identifier; never guess or fall back."""

    selected = tuple(
        draft
        for draft in report.drafts
        if getattr(draft, "draft_id", None) == draft_id
    )
    if len(selected) != 1:
        raise ContentDraftSelectionError("Content draft selection is invalid.")
    return selected[0]
