"""Thin application service used by every Demo route."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from foreign_trade_geo_agent.core.approved_wordpress_delivery import (
    ApprovedWordPressDraftDeliveryRequest,
)
from foreign_trade_geo_agent.core.audit import AuditStatus, SiteAuditResult
from foreign_trade_geo_agent.core.change_plan import ChangePlanReport, ChangePlanStatus
from foreign_trade_geo_agent.core.content_draft import ContentDraftReport, ContentDraftStatus
from foreign_trade_geo_agent.core.content_draft_review import ContentDraftReviewRequest
from foreign_trade_geo_agent.core.content_opportunity import (
    ContentOpportunityReport,
    ContentOpportunityStatus,
)
from foreign_trade_geo_agent.core.history import (
    ArtifactRecord,
    ArtifactType,
    RunStatus,
    WordPressAttemptState,
    WordPressDraftAttempt,
    WordPressVerification,
)
from foreign_trade_geo_agent.core.orchestration import (
    EndToEndProgressEventKind,
    EndToEndRunRequest,
    EndToEndStage,
)
from foreign_trade_geo_agent.core.site_content import SiteContentPacket
from foreign_trade_geo_agent.core.wordpress_verification import (
    WordPressVerificationRequest,
)
from foreign_trade_geo_agent.web.composition import DemoComposition
from foreign_trade_geo_agent.web.demo_boundaries import (
    DEMO_RESEARCH_QUESTION,
    DEMO_SITE_URL,
    DEMO_TARGET_LANGUAGE,
)
from foreign_trade_geo_agent.web.demo_wordpress import demo_wordpress_origin
from foreign_trade_geo_agent.web.jobs import LocalJobRegistry, LocalJobSnapshot
from foreign_trade_geo_agent.web.presenters import (
    DemoChangePlanView,
    DemoDraftReviewView,
    DemoNavigationView,
    DemoProgressStageView,
    DemoProgressView,
    DemoResultsView,
    DemoStartResult,
    present_change_plan,
    present_draft_review,
    present_navigation,
    present_results,
)


_STAGES = (
    (EndToEndStage.CRAWL, "Website Crawl"),
    (EndToEndStage.SITE_AUDIT, "SEO Audit"),
    (EndToEndStage.INDUSTRY_RESEARCH, "Industry Research"),
    (EndToEndStage.CONTENT_OPPORTUNITY, "Content Opportunities"),
    (EndToEndStage.CHANGE_PLAN, "Change Plan"),
    (EndToEndStage.CONTENT_DRAFT, "Content Draft"),
)
_ARTIFACT_STAGE = {
    ArtifactType.SITE_CONTENT: EndToEndStage.CRAWL,
    ArtifactType.SITE_AUDIT: EndToEndStage.SITE_AUDIT,
    ArtifactType.INDUSTRY_RESEARCH: EndToEndStage.INDUSTRY_RESEARCH,
    ArtifactType.CONTENT_OPPORTUNITY: EndToEndStage.CONTENT_OPPORTUNITY,
    ArtifactType.CHANGE_PLAN: EndToEndStage.CHANGE_PLAN,
    ArtifactType.CONTENT_DRAFT: EndToEndStage.CONTENT_DRAFT,
}


class DemoApplicationError(RuntimeError):
    """A sanitized failure suitable for an HTTP error response."""


@dataclass(frozen=True, slots=True)
class DeliverySetupState:
    run_id: str
    draft_id: str
    content_draft_artifact_id: str
    draft_title: str
    change_context: str
    target_site_url: str
    existing_attempt_id: str | None


@dataclass(frozen=True, slots=True)
class VerificationState:
    attempt: WordPressDraftAttempt
    verification: WordPressVerification | None


class DemoApplicationService:
    def __init__(
        self,
        composition: DemoComposition,
        jobs: LocalJobRegistry,
    ) -> None:
        self._composition = composition
        self._jobs = jobs

    def start_demo_analysis(self) -> DemoStartResult:
        job_id = self._jobs.create_job()
        observer = self._jobs.observer_for(job_id)
        workflow = self._composition.planning_workflow(observer)
        request = EndToEndRunRequest(
            site_url=DEMO_SITE_URL,
            research_question=DEMO_RESEARCH_QUESTION,
            target_language=DEMO_TARGET_LANGUAGE,
        )
        task = asyncio.create_task(workflow.run(request))
        self._jobs.attach_task(job_id, task)
        return DemoStartResult(job_id=job_id)

    def navigation(
        self,
        *,
        current_step: str,
        run_id: str | None = None,
    ) -> DemoNavigationView:
        destinations: dict[str, str | None] = {
            "start": "/",
            "progress": None,
            "results": None,
            "changes": None,
            "draft": None,
            "delivery": None,
            "verification": None,
        }
        if run_id is None:
            return present_navigation(
                current_step=current_step,
                destinations=destinations,
            )
        try:
            run = self._composition.history_reader.get_run(run_id)
            artifacts = self._composition.history_reader.list_artifacts(run_id)
        except Exception:
            run = None
            artifacts = ()
        if run is not None:
            destinations["progress"] = f"/runs/{run_id}/progress"
        if run is None or run.status is not RunStatus.SUCCEEDED:
            return present_navigation(
                current_step=current_step,
                destinations=destinations,
            )

        unique: dict[ArtifactType, ArtifactRecord] = {}
        for artifact_type in ArtifactType:
            matches = tuple(
                artifact
                for artifact in artifacts
                if artifact.artifact_type is artifact_type
                and artifact.payload_version == 1
            )
            if len(matches) == 1:
                unique[artifact_type] = matches[0]

        results_required = {
            ArtifactType.SITE_CONTENT,
            ArtifactType.SITE_AUDIT,
            ArtifactType.CONTENT_OPPORTUNITY,
        }
        if results_required <= unique.keys():
            destinations["results"] = f"/runs/{run_id}/results"

        change_artifact = unique.get(ArtifactType.CHANGE_PLAN)
        if (
            change_artifact is not None
            and isinstance(change_artifact.payload, ChangePlanReport)
            and change_artifact.payload.status is ChangePlanStatus.SUCCESS
        ):
            destinations["changes"] = f"/runs/{run_id}/changes"

        draft_artifact = unique.get(ArtifactType.CONTENT_DRAFT)
        draft_id: str | None = None
        if (
            draft_artifact is not None
            and isinstance(draft_artifact.payload, ContentDraftReport)
            and draft_artifact.payload.status is ContentDraftStatus.SUCCESS
            and draft_artifact.payload.drafts
        ):
            draft_id = draft_artifact.payload.drafts[0].draft_id
            destinations["draft"] = f"/runs/{run_id}/drafts/{draft_id}"
        if draft_id is not None:
            assert draft_artifact is not None
            latest = self._latest_attempt(draft_artifact.artifact_id, draft_id)
            if (
                latest is None
                or latest.outcome is WordPressAttemptState.FAILED_DEFINITELY
            ):
                destinations["delivery"] = (
                    f"/runs/{run_id}/drafts/{draft_id}/delivery"
                )
            else:
                destinations["delivery"] = (
                    f"/runs/{run_id}/deliveries/{latest.attempt_id}"
                )
            if (
                latest is not None
                and latest.outcome is not WordPressAttemptState.FAILED_DEFINITELY
            ):
                destinations["verification"] = (
                    f"/runs/{run_id}/deliveries/{latest.attempt_id}/verification"
                )
        return present_navigation(
            current_step=current_step,
            destinations=destinations,
        )

    def get_progress(
        self,
        *,
        job_id: str | None = None,
        run_id: str | None = None,
    ) -> DemoProgressView:
        if (job_id is None) == (run_id is None):
            raise DemoApplicationError("Exactly one progress identifier is required.")
        job = self._job(job_id, run_id)
        resolved_run_id = run_id if run_id is not None else job.run_id
        if resolved_run_id is None:
            return self._job_only_progress(job)

        try:
            run = self._composition.history_reader.get_run(resolved_run_id)
        except Exception:
            raise DemoApplicationError("The planning run could not be read.") from None
        if run is None:
            if job is not None and job.active:
                return self._event_progress(job, resolved_run_id)
            raise DemoApplicationError("The planning run was not found.")
        if run.status is RunStatus.RUNNING:
            if job is None or not job.active:
                return DemoProgressView(
                    location=f"/runs/{resolved_run_id}/progress",
                    run_id=resolved_run_id,
                    stages=self._persisted_stages(resolved_run_id, failed=False),
                    terminal=True,
                    polling=False,
                    interrupted=True,
                    message="Interrupted — operator check required",
                )
            return self._event_progress(job, resolved_run_id)
        return DemoProgressView(
            location=f"/runs/{resolved_run_id}/progress",
            run_id=resolved_run_id,
            stages=self._persisted_stages(
                resolved_run_id,
                failed=run.status is not RunStatus.SUCCEEDED,
            ),
            terminal=True,
            polling=False,
            interrupted=False,
            message=run.sanitized_error,
        )

    def load_results(self, run_id: str) -> DemoResultsView:
        try:
            required = self._required_artifacts(
                run_id,
                (
                    ArtifactType.SITE_CONTENT,
                    ArtifactType.SITE_AUDIT,
                    ArtifactType.CONTENT_OPPORTUNITY,
                ),
            )
            packet = required[ArtifactType.SITE_CONTENT].payload
            audit = required[ArtifactType.SITE_AUDIT].payload
            opportunities = required[ArtifactType.CONTENT_OPPORTUNITY].payload
            if (
                not isinstance(packet, SiteContentPacket)
                or not isinstance(audit, SiteAuditResult)
                or audit.status is not AuditStatus.SUCCESS
                or not isinstance(opportunities, ContentOpportunityReport)
                or opportunities.status is not ContentOpportunityStatus.SUCCESS
            ):
                raise ValueError("invalid planning payload")
            return present_results(
                run_id=run_id,
                audit=audit,
                packet=packet,
                opportunities=opportunities,
            )
        except Exception:
            raise DemoApplicationError(
                "The persisted planning results are unavailable or invalid."
            ) from None

    def load_change_plan(self, run_id: str) -> DemoChangePlanView:
        try:
            required = self._required_artifacts(
                run_id,
                (
                    ArtifactType.SITE_CONTENT,
                    ArtifactType.CONTENT_OPPORTUNITY,
                    ArtifactType.CHANGE_PLAN,
                ),
            )
            packet = required[ArtifactType.SITE_CONTENT].payload
            opportunities = required[ArtifactType.CONTENT_OPPORTUNITY].payload
            change_plan = required[ArtifactType.CHANGE_PLAN].payload
            if (
                not isinstance(packet, SiteContentPacket)
                or not isinstance(opportunities, ContentOpportunityReport)
                or opportunities.status is not ContentOpportunityStatus.SUCCESS
                or not isinstance(change_plan, ChangePlanReport)
                or change_plan.status is not ChangePlanStatus.SUCCESS
            ):
                raise ValueError("invalid change-plan payload")
            return present_change_plan(
                run_id=run_id,
                packet=packet,
                opportunities=opportunities,
                change_plan=change_plan,
                draft_id=self._available_draft_id(run_id),
            )
        except Exception:
            raise DemoApplicationError(
                "The persisted change plan is unavailable or invalid."
            ) from None

    def review_draft(self, run_id: str, draft_id: str) -> DemoDraftReviewView:
        try:
            required = self._required_artifacts(
                run_id,
                (ArtifactType.CONTENT_DRAFT,),
            )
            artifact = required[ArtifactType.CONTENT_DRAFT]
            review = self._composition.review_workflow.review(
                ContentDraftReviewRequest(
                    planning_run_id=run_id,
                    content_draft_artifact_id=artifact.artifact_id,
                    draft_id=draft_id,
                )
            )
            return present_draft_review(review)
        except Exception:
            raise DemoApplicationError(
                "The persisted content draft review is unavailable or invalid."
            ) from None

    def _required_artifacts(
        self,
        run_id: str,
        artifact_types: tuple[ArtifactType, ...],
    ) -> dict[ArtifactType, ArtifactRecord]:
        run = self._composition.history_reader.get_run(run_id)
        if run is None or run.status is not RunStatus.SUCCEEDED:
            raise ValueError("planning run is not complete")
        artifacts = self._composition.history_reader.list_artifacts(run_id)
        selected: dict[ArtifactType, ArtifactRecord] = {}
        for artifact_type in artifact_types:
            matches = tuple(
                item for item in artifacts if item.artifact_type is artifact_type
            )
            if len(matches) != 1 or matches[0].payload_version != 1:
                raise ValueError("planning artifacts are unavailable or ambiguous")
            selected[artifact_type] = matches[0]
        return selected

    def _available_draft_id(self, run_id: str) -> str | None:
        try:
            artifacts = self._composition.history_reader.list_artifacts(run_id)
        except Exception:
            return None
        matches = tuple(
            item
            for item in artifacts
            if item.artifact_type is ArtifactType.CONTENT_DRAFT
            and item.payload_version == 1
        )
        if len(matches) != 1:
            return None
        report = matches[0].payload
        if (
            not isinstance(report, ContentDraftReport)
            or report.status is not ContentDraftStatus.SUCCESS
            or not report.drafts
        ):
            return None
        return report.drafts[0].draft_id

    def _job(
        self,
        job_id: str | None,
        run_id: str | None,
    ) -> LocalJobSnapshot | None:
        if job_id is not None:
            job = self._jobs.get_job(job_id)
            if job is None:
                raise DemoApplicationError("The analysis job was not found.")
            return job
        assert run_id is not None
        return self._jobs.get_job_for_run(run_id)

    def _job_only_progress(self, job: LocalJobSnapshot | None) -> DemoProgressView:
        assert job is not None
        terminal = not job.active
        return DemoProgressView(
            location=f"/jobs/{job.job_id}",
            run_id=None,
            stages=self._event_stages(job),
            terminal=terminal,
            polling=not terminal,
            interrupted=False,
            message=job.failure_message,
        )

    def _event_progress(
        self,
        job: LocalJobSnapshot,
        run_id: str,
    ) -> DemoProgressView:
        terminal = not job.active
        return DemoProgressView(
            location=f"/runs/{run_id}/progress",
            run_id=run_id,
            stages=self._event_stages(job),
            terminal=terminal,
            polling=not terminal,
            interrupted=False,
            message=job.failure_message,
        )

    @staticmethod
    def _event_stages(job: LocalJobSnapshot) -> tuple[DemoProgressStageView, ...]:
        states = {stage: "Waiting" for stage, _label in _STAGES}
        for event in job.events:
            if event.stage is None:
                continue
            if event.kind is EndToEndProgressEventKind.STAGE_STARTED:
                states[event.stage] = "Running"
            elif event.kind is EndToEndProgressEventKind.STAGE_COMPLETED:
                states[event.stage] = "Complete"
            elif event.kind is EndToEndProgressEventKind.STAGE_FAILED:
                states[event.stage] = "Failed"
        return tuple(
            DemoProgressStageView(stage.value, label, states[stage])
            for stage, label in _STAGES
        )

    def _persisted_stages(
        self,
        run_id: str,
        *,
        failed: bool,
    ) -> tuple[DemoProgressStageView, ...]:
        try:
            artifacts = self._composition.history_reader.list_artifacts(run_id)
        except Exception:
            raise DemoApplicationError("The planning artifacts could not be read.") from None
        complete = {
            _ARTIFACT_STAGE[item.artifact_type]
            for item in artifacts
            if item.artifact_type in _ARTIFACT_STAGE
        }
        states = {stage: "Complete" if stage in complete else "Waiting" for stage, _ in _STAGES}
        if failed:
            for stage, _label in _STAGES:
                if states[stage] == "Waiting":
                    states[stage] = "Failed"
                    break
        return tuple(
            DemoProgressStageView(stage.value, label, states[stage])
            for stage, label in _STAGES
        )

    def load_delivery_setup(
        self,
        run_id: str,
        draft_id: str,
    ) -> DeliverySetupState:
        view = self.review_draft(run_id, draft_id)
        artifact_id = view.review.content_draft_artifact_id
        latest = self._latest_attempt(artifact_id, draft_id)
        existing_attempt_id = (
            None
            if latest is None
            or latest.outcome is WordPressAttemptState.FAILED_DEFINITELY
            else latest.attempt_id
        )
        return DeliverySetupState(
            run_id=run_id,
            draft_id=draft_id,
            content_draft_artifact_id=artifact_id,
            draft_title=view.draft_title,
            change_context=view.review.change.change_id,
            target_site_url=demo_wordpress_origin(run_id),
            existing_attempt_id=existing_attempt_id,
        )

    async def create_wordpress_draft(
        self,
        run_id: str,
        draft_id: str,
        *,
        intent_confirmed: bool,
    ) -> str:
        if not intent_confirmed:
            raise DemoApplicationError("Explicit delivery intent is required.")
        view = self.review_draft(run_id, draft_id)
        artifact_id = view.review.content_draft_artifact_id
        target = demo_wordpress_origin(run_id)
        request = ApprovedWordPressDraftDeliveryRequest(
            planning_run_id=run_id,
            content_draft_artifact_id=artifact_id,
            draft_id=draft_id,
            target_site_url=target,
            title_override=view.draft_title,
        )
        result = await self._composition.delivery_workflow(target).deliver(request)
        return result.attempt.attempt_id

    def load_delivery_result(
        self,
        run_id: str,
        attempt_id: str,
    ) -> WordPressDraftAttempt:
        return self._owned_attempt(run_id, attempt_id)

    async def verify_wordpress_draft(
        self,
        run_id: str,
        attempt_id: str,
    ) -> None:
        self._owned_attempt(run_id, attempt_id)
        await self._composition.verification_workflow().verify(
            WordPressVerificationRequest(attempt_id)
        )

    def load_verification_result(
        self,
        run_id: str,
        attempt_id: str,
    ) -> VerificationState:
        attempt = self._owned_attempt(run_id, attempt_id)
        return VerificationState(
            attempt=attempt,
            verification=self._latest_verification(attempt_id),
        )

    def _owned_attempt(
        self,
        run_id: str,
        attempt_id: str,
    ) -> WordPressDraftAttempt:
        try:
            attempt = self._composition.history_store.get_wordpress_attempt(
                attempt_id
            )
        except Exception:
            raise DemoApplicationError(
                "The delivery attempt could not be read."
            ) from None
        if attempt is None or attempt.run_id != run_id:
            raise DemoApplicationError("The delivery attempt was not found.")
        return attempt

    def _latest_attempt(
        self,
        content_draft_artifact_id: str,
        draft_item_id: str,
    ) -> WordPressDraftAttempt | None:
        attempts = self._composition.history_store.list_wordpress_attempts_for_draft(
            content_draft_artifact_id,
            draft_item_id,
        )
        if not attempts:
            return None
        return max(
            attempts,
            key=lambda attempt: (attempt.attempted_at, attempt.attempt_id),
        )

    def _latest_verification(
        self,
        attempt_id: str,
    ) -> WordPressVerification | None:
        verifications = self._composition.history_store.list_wordpress_verifications(
            attempt_id
        )
        if not verifications:
            return None
        return max(
            verifications,
            key=lambda verification: (
                verification.verified_at,
                verification.verification_id,
            ),
        )
