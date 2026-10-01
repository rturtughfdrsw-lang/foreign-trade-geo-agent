"""Load one persisted D# and delegate one explicit WordPress draft delivery."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from foreign_trade_geo_agent.core.approved_wordpress_delivery import (
    ApprovedWordPressDraftDeliveryRequest,
    ApprovedWordPressDraftDeliveryValidationError,
)
from foreign_trade_geo_agent.core.content_draft import (
    ContentDraftReport,
    ContentDraftStatus,
    DraftItem,
)
from foreign_trade_geo_agent.core.history import (
    ArtifactRecord,
    ArtifactType,
    WordPressAttemptState,
    WordPressDraftAttempt,
)
from foreign_trade_geo_agent.core.ports import HistoryStore
from foreign_trade_geo_agent.workflows.wordpress_delivery import (
    WordPressDeliveryResult,
    WordPressDeliveryWorkflow,
)


_SUPPORTED_CONTENT_DRAFT_PAYLOAD_VERSION = 1


@dataclass(frozen=True, slots=True)
class ApprovedWordPressDraftDeliveryResult:
    planning_run_id: str
    content_draft_artifact_id: str
    selected_draft_id: str
    delivery_result: WordPressDeliveryResult

    @property
    def attempt(self) -> WordPressDraftAttempt:
        return self.delivery_result.attempt

    @property
    def reconciliation_required(self) -> bool:
        return self.attempt.outcome in {
            WordPressAttemptState.PENDING,
            WordPressAttemptState.UNKNOWN,
        }


class ApprovedWordPressDraftDeliveryWorkflow:
    """Deliver exactly one caller-selected draft from persisted evidence."""

    def __init__(
        self,
        *,
        history_store: HistoryStore,
        wordpress_delivery: WordPressDeliveryWorkflow,
    ) -> None:
        self._history_store = history_store
        self._wordpress_delivery = wordpress_delivery

    async def deliver(
        self,
        request: ApprovedWordPressDraftDeliveryRequest,
    ) -> ApprovedWordPressDraftDeliveryResult:
        if not isinstance(request, ApprovedWordPressDraftDeliveryRequest):
            raise TypeError(
                "Approved WordPress delivery requires its stable request model."
            )
        artifact = await asyncio.to_thread(
            self._history_store.get_artifact,
            request.content_draft_artifact_id,
        )
        report = self._validated_report(artifact, request)
        selected = tuple(
            draft for draft in report.drafts if draft.draft_id == request.draft_id
        )
        if len(selected) != 1:
            raise ApprovedWordPressDraftDeliveryValidationError(
                "Approved content draft selection is invalid."
            )

        delivery_result = await self._wordpress_delivery.deliver(
            request.planning_run_id,
            request.content_draft_artifact_id,
            selected[0],
            request.target_site_url,
            title_override=request.title_override,
        )
        return ApprovedWordPressDraftDeliveryResult(
            planning_run_id=request.planning_run_id,
            content_draft_artifact_id=request.content_draft_artifact_id,
            selected_draft_id=selected[0].draft_id,
            delivery_result=delivery_result,
        )

    @staticmethod
    def _validated_report(
        artifact: ArtifactRecord | None,
        request: ApprovedWordPressDraftDeliveryRequest,
    ) -> ContentDraftReport:
        if (
            not isinstance(artifact, ArtifactRecord)
            or artifact.run_id != request.planning_run_id
            or artifact.artifact_type is not ArtifactType.CONTENT_DRAFT
            or artifact.payload_version != _SUPPORTED_CONTENT_DRAFT_PAYLOAD_VERSION
            or not isinstance(artifact.payload, ContentDraftReport)
        ):
            raise ApprovedWordPressDraftDeliveryValidationError(
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
            raise ApprovedWordPressDraftDeliveryValidationError(
                "Persisted content draft artifact is invalid."
            ) from None
        if report.status is not ContentDraftStatus.SUCCESS:
            raise ApprovedWordPressDraftDeliveryValidationError(
                "Persisted content draft report is not successful."
            )
        if not all(isinstance(draft, DraftItem) for draft in report.drafts):
            raise ApprovedWordPressDraftDeliveryValidationError(
                "Persisted content draft artifact is invalid."
            )
        return report
