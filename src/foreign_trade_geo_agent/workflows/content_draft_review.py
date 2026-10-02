"""Read-only assembly of one content-draft review view from persisted history."""

from __future__ import annotations

from foreign_trade_geo_agent.core.change_plan import (
    ChangeOperation,
    ChangePlanReport,
    ChangePlanStatus,
)
from foreign_trade_geo_agent.core.content_draft import DraftItem
from foreign_trade_geo_agent.core.content_draft_review import (
    ContentDraftReviewRequest,
    ContentDraftReviewView,
    build_content_draft_review_view,
)
from foreign_trade_geo_agent.core.content_opportunity import (
    ContentOpportunity,
    ContentOpportunityReport,
    ContentOpportunitySource,
    ContentOpportunitySourceMaterial,
    ContentOpportunityStatus,
)
from foreign_trade_geo_agent.core.history import ArtifactRecord, ArtifactType
from foreign_trade_geo_agent.core.ports import HistoryReader
from foreign_trade_geo_agent.core.site_content import SiteContentPacket
from foreign_trade_geo_agent.workflows.content_draft_selection import (
    validate_persisted_content_draft_report,
    select_content_draft,
)


_REQUIRED_ARTIFACT_TYPES = (
    ArtifactType.SITE_CONTENT,
    ArtifactType.CONTENT_OPPORTUNITY,
    ArtifactType.CHANGE_PLAN,
)
_SUPPORTED_PAYLOAD_VERSION = 1


class ContentDraftReviewError(RuntimeError):
    """A sanitized, fail-closed read-only review failure."""


def _single_match(items: tuple[object, ...], attribute: str, value: str) -> object:
    matched = tuple(
        item for item in items if getattr(item, attribute, None) == value
    )
    if len(matched) != 1:
        raise ContentDraftReviewError(
            "The referenced planning evidence could not be resolved."
        )
    return matched[0]


class ContentDraftReviewWorkflow:
    """Load one persisted D# and its provenance without any write path."""

    def __init__(self, *, history_reader: HistoryReader) -> None:
        self._history_reader = history_reader

    def review(self, request: ContentDraftReviewRequest) -> ContentDraftReviewView:
        if not isinstance(request, ContentDraftReviewRequest):
            raise TypeError(
                "Content draft review requires its stable request model."
            )
        try:
            run = self._history_reader.get_run(request.planning_run_id)
        except Exception:
            raise ContentDraftReviewError(
                "The planning run could not be read."
            ) from None
        if run is None:
            raise ContentDraftReviewError("The planning run was not found.")
        try:
            artifact = self._history_reader.get_artifact(
                request.content_draft_artifact_id
            )
            report = validate_persisted_content_draft_report(
                artifact,
                planning_run_id=request.planning_run_id,
            )
            draft = select_content_draft(report, request.draft_id)
        except Exception:
            raise ContentDraftReviewError(
                "The persisted content draft could not be selected."
            ) from None
        assert isinstance(artifact, ArtifactRecord)

        try:
            artifacts = self._history_reader.list_artifacts(
                request.planning_run_id
            )
        except Exception:
            raise ContentDraftReviewError(
                "The planning artifacts could not be read."
            ) from None
        grouped: dict[ArtifactType, list[ArtifactRecord]] = {}
        for item in artifacts:
            grouped.setdefault(item.artifact_type, []).append(item)
        required: dict[ArtifactType, ArtifactRecord] = {}
        for artifact_type in _REQUIRED_ARTIFACT_TYPES:
            group = grouped.get(artifact_type, [])
            if len(group) != 1 or group[0].payload_version != _SUPPORTED_PAYLOAD_VERSION:
                raise ContentDraftReviewError(
                    "The persisted planning evidence is unavailable or ambiguous."
                )
            required[artifact_type] = group[0]

        packet = required[ArtifactType.SITE_CONTENT].payload
        opportunity_report = required[ArtifactType.CONTENT_OPPORTUNITY].payload
        change_plan = required[ArtifactType.CHANGE_PLAN].payload
        if (
            not isinstance(packet, SiteContentPacket)
            or not isinstance(opportunity_report, ContentOpportunityReport)
            or opportunity_report.status is not ContentOpportunityStatus.SUCCESS
            or not isinstance(change_plan, ChangePlanReport)
            or change_plan.status is not ChangePlanStatus.SUCCESS
        ):
            raise ContentDraftReviewError(
                "The persisted planning evidence is invalid."
            )

        operation = _single_match(
            change_plan.operations,
            "change_id",
            draft.change_ref,
        )
        opportunity = _single_match(
            opportunity_report.opportunities,
            "recommendation_id",
            draft.opportunity_ref,
        )
        assert isinstance(operation, ChangeOperation)
        assert isinstance(opportunity, ContentOpportunity)
        if operation.audit_refs != opportunity.audit_refs:
            raise ContentDraftReviewError(
                "The draft audit provenance is inconsistent."
            )

        audit_by_id = {
            item.evidence_id: item for item in opportunity_report.audit_evidence
        }
        audit_evidence = []
        for reference in operation.audit_refs:
            item = audit_by_id.get(reference)
            if item is None:
                raise ContentDraftReviewError(
                    "The referenced audit evidence could not be resolved."
                )
            audit_evidence.append(item)

        page_by_id = {page.evidence_id: page for page in packet.pages}
        page_evidence = []
        for reference in draft.page_refs:
            page = page_by_id.get(reference)
            if page is None:
                raise ContentDraftReviewError(
                    "The referenced page evidence could not be resolved."
                )
            page_evidence.append(page)

        material_by_id = {
            material.source_id: material
            for material in opportunity_report.source_materials
        }
        source_by_id = {
            source.source_id: source for source in opportunity_report.sources
        }
        materials: list[ContentOpportunitySourceMaterial] = []
        sources: list[ContentOpportunitySource] = []
        for reference in draft.source_refs:
            material = material_by_id.get(reference)
            source = source_by_id.get(reference)
            if material is None or source is None:
                raise ContentDraftReviewError(
                    "The referenced external research could not be resolved."
                )
            materials.append(material)
            sources.append(source)

        return build_content_draft_review_view(
            planning_run_id=request.planning_run_id,
            content_draft_artifact_id=request.content_draft_artifact_id,
            payload_version=artifact.payload_version,
            draft=draft,
            change=operation,
            opportunity=opportunity,
            audit_evidence=tuple(audit_evidence),
            pages=tuple(page_evidence),
            materials=tuple(materials),
            sources=tuple(sources),
            limitations=report.limitations,
        )
