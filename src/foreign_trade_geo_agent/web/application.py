"""Thin application service used by every Demo route."""

from __future__ import annotations

import asyncio

from foreign_trade_geo_agent.core.audit import AuditStatus, SiteAuditResult
from foreign_trade_geo_agent.core.change_plan import ChangePlanReport, ChangePlanStatus
from foreign_trade_geo_agent.core.content_draft import ContentDraftReport, ContentDraftStatus
from foreign_trade_geo_agent.core.content_draft_review import ContentDraftReviewRequest
from foreign_trade_geo_agent.core.content_opportunity import (
    ContentOpportunityReport,
    ContentOpportunityStatus,
)
from foreign_trade_geo_agent.core.history import ArtifactRecord, ArtifactType, RunStatus
from foreign_trade_geo_agent.core.orchestration import (
    EndToEndProgressEventKind,
    EndToEndRunRequest,
    EndToEndStage,
)
from foreign_trade_geo_agent.core.site_content import SiteContentPacket
from foreign_trade_geo_agent.web.composition import DemoComposition
from foreign_trade_geo_agent.web.demo_boundaries import (
    DEMO_RESEARCH_QUESTION,
    DEMO_SITE_URL,
    DEMO_TARGET_LANGUAGE,
)
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
        if (
            draft_artifact is not None
            and isinstance(draft_artifact.payload, ContentDraftReport)
            and draft_artifact.payload.status is ContentDraftStatus.SUCCESS
            and draft_artifact.payload.drafts
        ):
            draft_id = draft_artifact.payload.drafts[0].draft_id
            destinations["draft"] = f"/runs/{run_id}/drafts/{draft_id}"
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
