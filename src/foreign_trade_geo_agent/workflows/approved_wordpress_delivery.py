"""Load one persisted D# and delegate one explicit WordPress draft delivery."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from foreign_trade_geo_agent.core.approved_wordpress_delivery import (
    ApprovedWordPressDraftDeliveryRequest,
    ApprovedWordPressDraftDeliveryValidationError,
)
from foreign_trade_geo_agent.core.history import (
    WordPressAttemptState,
    WordPressDraftAttempt,
)
from foreign_trade_geo_agent.core.ports import HistoryStore
from foreign_trade_geo_agent.workflows.content_draft_selection import (
    ContentDraftSelectionError,
    select_content_draft,
    validate_persisted_content_draft_report,
)
from foreign_trade_geo_agent.workflows.wordpress_delivery import (
    WordPressDeliveryResult,
    WordPressDeliveryWorkflow,
)


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
        try:
            report = validate_persisted_content_draft_report(
                artifact,
                planning_run_id=request.planning_run_id,
            )
        except ContentDraftSelectionError:
            raise ApprovedWordPressDraftDeliveryValidationError(
                "Persisted content draft artifact is invalid."
            ) from None
        try:
            selected_draft = select_content_draft(report, request.draft_id)
        except ContentDraftSelectionError:
            raise ApprovedWordPressDraftDeliveryValidationError(
                "Approved content draft selection is invalid."
            ) from None

        delivery_result = await self._wordpress_delivery.deliver(
            request.planning_run_id,
            request.content_draft_artifact_id,
            selected_draft,
            request.target_site_url,
            title_override=request.title_override,
        )
        return ApprovedWordPressDraftDeliveryResult(
            planning_run_id=request.planning_run_id,
            content_draft_artifact_id=request.content_draft_artifact_id,
            selected_draft_id=selected_draft.draft_id,
            delivery_result=delivery_result,
        )
