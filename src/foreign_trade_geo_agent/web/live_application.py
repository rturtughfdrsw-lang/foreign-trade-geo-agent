"""Thin process-local application service for Live planning starts."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from threading import Lock

from foreign_trade_geo_agent.core.live_analysis import LiveAnalysisInput
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
from foreign_trade_geo_agent.web.composition import LiveComposition
from foreign_trade_geo_agent.web.jobs import LocalJobRegistry, LocalJobSnapshot
from foreign_trade_geo_agent.web.presenters import (
    AnalysisContextView,
    DemoChangePlanView,
    DemoDraftReviewView,
    DemoNavigationView,
    DemoProgressStageView,
    DemoProgressView,
    DemoResultsView,
    present_change_plan,
    present_draft_review,
    present_live_navigation,
    present_results,
)
from foreign_trade_geo_agent.core.site_content import SiteContentPacket


_UNAVAILABLE_MESSAGE = (
    "Live analysis is unavailable because provider configuration is incomplete."
)
_ACTIVE_MESSAGE = "A Live analysis is already running."
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


class LiveApplicationError(RuntimeError):
    """A fixed, sanitized Live application failure."""


class LiveApplicationNotFoundError(LiveApplicationError):
    """A Live resource is absent from the profile-scoped history."""


@dataclass(frozen=True, slots=True)
class LiveStartResult:
    job_id: str


class LiveApplicationService:
    """Schedule validated Live work while allowing one active job per service."""

    def __init__(
        self,
        composition: LiveComposition,
        jobs: LocalJobRegistry,
    ) -> None:
        self._composition = composition
        self._jobs = jobs
        self._start_lock = Lock()
        self._active_job_id: str | None = None

    @property
    def providers_ready(self) -> bool:
        return self._composition.providers_ready

    def start_live_analysis(
        self,
        analysis_input: LiveAnalysisInput,
    ) -> LiveStartResult:
        if not self._composition.providers_ready:
            raise LiveApplicationError(_UNAVAILABLE_MESSAGE)
        if not isinstance(analysis_input, LiveAnalysisInput):
            raise LiveApplicationError("Live analysis input is invalid.")

        with self._start_lock:
            if self._active_job_id is not None:
                current = self._jobs.get_job(self._active_job_id)
                if current is not None and current.active:
                    raise LiveApplicationError(_ACTIVE_MESSAGE)
                self._active_job_id = None

            job_id = self._jobs.create_job()
            observer = self._jobs.observer_for(job_id)
            try:
                workflow = self._composition.planning_workflow(observer)
                task = asyncio.create_task(
                    workflow.run(
                        EndToEndRunRequest(
                            site_url=analysis_input.website_url,
                            research_question=analysis_input.seo_goal,
                            target_language=analysis_input.target_language,
                        )
                    )
                )
                self._jobs.attach_task(job_id, task)
            except Exception:
                raise LiveApplicationError(
                    "Live analysis could not be started."
                ) from None
            self._active_job_id = job_id

            def release_slot(_finished: asyncio.Task[object]) -> None:
                with self._start_lock:
                    if self._active_job_id == job_id:
                        self._active_job_id = None

            task.add_done_callback(release_slot)
            return LiveStartResult(job_id=job_id)

    def navigation(
        self,
        *,
        current_step: str,
        run_id: str | None = None,
    ) -> DemoNavigationView:
        destinations: dict[str, str | None] = {
            "start": "/live/start",
            "progress": None,
            "results": None,
            "changes": None,
            "draft": None,
        }
        if run_id is not None:
            destinations["progress"] = f"/live/runs/{run_id}/progress"
            try:
                run = self._composition.history_reader.get_run(run_id)
                analysis_input = (
                    self._composition.history_reader.get_analysis_run_input(run_id)
                )
            except Exception:
                run = None
                analysis_input = None
            if run is not None and analysis_input is None:
                raise LiveApplicationError("Live analysis history is incomplete.")
            if run is not None and self._planning_readable(run):
                try:
                    artifacts = self._composition.history_reader.list_artifacts(run_id)
                except Exception:
                    artifacts = ()
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
                if {
                    ArtifactType.SITE_CONTENT,
                    ArtifactType.SITE_AUDIT,
                    ArtifactType.CONTENT_OPPORTUNITY,
                } <= unique.keys():
                    destinations["results"] = f"/live/runs/{run_id}/results"
                change_artifact = unique.get(ArtifactType.CHANGE_PLAN)
                if (
                    change_artifact is not None
                    and isinstance(change_artifact.payload, ChangePlanReport)
                    and change_artifact.payload.status is ChangePlanStatus.SUCCESS
                ):
                    destinations["changes"] = f"/live/runs/{run_id}/changes"
                draft_artifact = unique.get(ArtifactType.CONTENT_DRAFT)
                if (
                    run.status is RunStatus.SUCCEEDED
                    and draft_artifact is not None
                    and isinstance(draft_artifact.payload, ContentDraftReport)
                    and draft_artifact.payload.status is ContentDraftStatus.SUCCESS
                    and draft_artifact.payload.drafts
                ):
                    draft_id = draft_artifact.payload.drafts[0].draft_id
                    destinations["draft"] = (
                        f"/live/runs/{run_id}/drafts/{draft_id}"
                    )
        return present_live_navigation(
            current_step=current_step,
            destinations=destinations,
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
                context=self._analysis_context(run_id),
                run_id=run_id,
                audit=audit,
                packet=packet,
                opportunities=opportunities,
            )
        except LiveApplicationError:
            raise
        except Exception:
            raise LiveApplicationError(
                "The persisted Live planning results are unavailable or invalid."
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
                context=self._analysis_context(run_id),
                run_id=run_id,
                packet=packet,
                opportunities=opportunities,
                change_plan=change_plan,
                draft_id=self._available_draft_id(run_id),
            )
        except LiveApplicationError:
            raise
        except Exception:
            raise LiveApplicationError(
                "The persisted Live change plan is unavailable or invalid."
            ) from None

    def review_draft(self, run_id: str, draft_id: str) -> DemoDraftReviewView:
        try:
            artifact = self._required_artifacts(
                run_id,
                (ArtifactType.CONTENT_DRAFT,),
            )[ArtifactType.CONTENT_DRAFT]
            review = self._composition.review_workflow.review(
                ContentDraftReviewRequest(
                    planning_run_id=run_id,
                    content_draft_artifact_id=artifact.artifact_id,
                    draft_id=draft_id,
                )
            )
            return present_draft_review(
                review,
                context=self._analysis_context(run_id),
            )
        except LiveApplicationError:
            raise
        except Exception:
            raise LiveApplicationError(
                "The persisted Live content draft review is unavailable or invalid."
            ) from None

    def _required_artifacts(
        self,
        run_id: str,
        artifact_types: tuple[ArtifactType, ...],
    ) -> dict[ArtifactType, ArtifactRecord]:
        run = self._composition.history_reader.get_run(run_id)
        if run is None:
            raise LiveApplicationNotFoundError(
                "The Live planning run was not found."
            )
        if not self._planning_readable(run) or (
            run.status is not RunStatus.SUCCEEDED and ArtifactType.CONTENT_DRAFT in artifact_types
        ):
            raise ValueError("planning run is not complete")
        if self._composition.history_reader.get_analysis_run_input(run_id) is None:
            raise LiveApplicationError("Live analysis history is incomplete.")
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

    @staticmethod
    def _planning_readable(run) -> bool:
        """Keep native planning reviewable when Draft admission stops the run.

        This only grants read access to validated planning artifacts, never a
        successful run, Draft output, semantic approval or delivery permission.
        """
        return run.status is RunStatus.SUCCEEDED or (
            run.status is RunStatus.FAILED and run.failure_kind == "content_draft.invalid_input"
        )

    def _analysis_context(self, run_id: str) -> AnalysisContextView:
        analysis_input = self._composition.history_reader.get_analysis_run_input(run_id)
        if analysis_input is None:
            raise LiveApplicationError("Live analysis history is incomplete.")
        return AnalysisContextView(
            display_identity=analysis_input.display_identity,
            website_url=analysis_input.website_url,
            seo_goal=analysis_input.seo_goal,
            target_language=analysis_input.target_language,
            live=True,
        )

    def _available_draft_id(self, run_id: str) -> str | None:
        matches = tuple(
            item
            for item in self._composition.history_reader.list_artifacts(run_id)
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

    def get_progress(
        self,
        *,
        job_id: str | None = None,
        run_id: str | None = None,
    ) -> DemoProgressView:
        if (job_id is None) == (run_id is None):
            raise LiveApplicationError("Exactly one progress identifier is required.")
        job = self._job(job_id, run_id)
        resolved_run_id = run_id if run_id is not None else job.run_id
        if resolved_run_id is None:
            return self._job_only_progress(job)

        try:
            run = self._composition.history_reader.get_run(resolved_run_id)
        except Exception:
            raise LiveApplicationError("The Live planning run could not be read.") from None
        if run is None:
            if job is not None and job.active:
                return self._event_progress(job, resolved_run_id)
            raise LiveApplicationError("The Live planning run was not found.")
        try:
            analysis_input = self._composition.history_reader.get_analysis_run_input(
                resolved_run_id
            )
        except Exception:
            raise LiveApplicationError("Live analysis history is incomplete.") from None
        if analysis_input is None:
            raise LiveApplicationError("Live analysis history is incomplete.")

        if run.status is RunStatus.RUNNING:
            if job is None or not job.active:
                return DemoProgressView(
                    location=f"/live/runs/{resolved_run_id}/progress",
                    run_id=resolved_run_id,
                    stages=self._persisted_stages(resolved_run_id, failed=False),
                    terminal=True,
                    polling=False,
                    interrupted=True,
                    message="Interrupted — operator check required",
                )
            return self._event_progress(job, resolved_run_id)
        return DemoProgressView(
            location=f"/live/runs/{resolved_run_id}/progress",
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

    def _job(
        self,
        job_id: str | None,
        run_id: str | None,
    ) -> LocalJobSnapshot | None:
        if job_id is not None:
            job = self._jobs.get_job(job_id)
            if job is None:
                raise LiveApplicationError("The Live analysis job was not found.")
            return job
        assert run_id is not None
        return self._jobs.get_job_for_run(run_id)

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

    def _job_only_progress(self, job: LocalJobSnapshot | None) -> DemoProgressView:
        assert job is not None
        terminal = not job.active
        return DemoProgressView(
            location=f"/live/jobs/{job.job_id}",
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
            location=f"/live/runs/{run_id}/progress",
            run_id=run_id,
            stages=self._event_stages(job),
            terminal=terminal,
            polling=not terminal,
            interrupted=False,
            message=job.failure_message,
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
            raise LiveApplicationError(
                "The Live planning artifacts could not be read."
            ) from None
        complete = {
            _ARTIFACT_STAGE[item.artifact_type]
            for item in artifacts
            if item.artifact_type in _ARTIFACT_STAGE
        }
        states = {
            stage: "Complete" if stage in complete else "Waiting"
            for stage, _label in _STAGES
        }
        if failed:
            for stage, _label in _STAGES:
                if states[stage] == "Waiting":
                    states[stage] = "Failed"
                    break
        return tuple(
            DemoProgressStageView(stage.value, label, states[stage])
            for stage, label in _STAGES
        )
