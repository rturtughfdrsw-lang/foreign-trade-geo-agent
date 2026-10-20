"""Fixed orchestration for one persisted end-to-end planning run."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from foreign_trade_geo_agent.core.change_plan import ChangePlanReport, ChangePlanStatus
from foreign_trade_geo_agent.core.audit import AuditStatus, SiteAuditResult
from foreign_trade_geo_agent.core.content_draft import (
    ContentDraftInput,
    ContentDraftReport,
    ContentDraftStatus,
    ContentDraftValidationCategory,
)
from foreign_trade_geo_agent.core.content_opportunity import (
    ContentOpportunityReport,
    ContentOpportunityStatus,
)
from foreign_trade_geo_agent.core.crawling import CrawlStopReason, SiteCrawlReport
from foreign_trade_geo_agent.core.extraction import PageExtractionStatus
from foreign_trade_geo_agent.core.history import (
    AnalysisRunInput,
    ArtifactRecord,
    ArtifactType,
    HistoryStoreError,
    PlanningValidationCategory,
    RunStatus,
    WorkflowRun,
    site_key_from_url,
)
from foreign_trade_geo_agent.core.orchestration import (
    ArtifactRef,
    EndToEndProgressEvent,
    EndToEndProgressEventKind,
    EndToEndProgressObserver,
    EndToEndRunRequest,
    EndToEndRunResult,
    EndToEndStage,
    TerminalReport,
)
from foreign_trade_geo_agent.core.live_analysis import LiveAnalysisInput
from foreign_trade_geo_agent.core.ports import HistoryStore, PlanningSiteAuditor
from foreign_trade_geo_agent.core.research import ResearchReport, ResearchStatus
from foreign_trade_geo_agent.core.research_query import build_research_query
from foreign_trade_geo_agent.workflows.change_plan import ChangePlanWorkflow
from foreign_trade_geo_agent.workflows.content_draft import ContentDraftWorkflow
from foreign_trade_geo_agent.workflows.content_opportunity import (
    ContentOpportunityWorkflow,
)
from foreign_trade_geo_agent.workflows.industry_research import (
    IndustryResearchWorkflow,
)
from foreign_trade_geo_agent.workflows.planning_failures import (
    classify_crawl_failure,
)
from foreign_trade_geo_agent.workflows.run_diagnostics import RunDiagnosticContext
from foreign_trade_geo_agent.workflows.site_content_packet import (
    SiteContentPacketBuilder,
)
from foreign_trade_geo_agent.workflows.site_crawl import SiteCrawlWorkflow


_WORKFLOW_NAME = "end_to_end_planning_v1"
_PAYLOAD_VERSION = 1


@dataclass(frozen=True, slots=True)
class _PlanningOutcome:
    artifacts: tuple[ArtifactRef, ...]
    crawl_report: SiteCrawlReport
    terminal_report: TerminalReport | None
    stopped_stage: EndToEndStage | None
    failure_kind: str | None
    sanitized_error: str | None
    final_validation_category: PlanningValidationCategory | None = None
    writer_attempt_count: int | None = None


class _AppendFailure(Exception):
    def __init__(self, error: HistoryStoreError) -> None:
        super().__init__("Artifact persistence failed.")
        self.error = error


class EndToEndWorkflow:
    """Run the fixed planning chain and stop before any delivery side effect."""

    def __init__(
        self,
        *,
        site_crawl: SiteCrawlWorkflow,
        packet_builder: SiteContentPacketBuilder,
        planning_site_auditor: PlanningSiteAuditor,
        industry_research: IndustryResearchWorkflow,
        content_opportunity: ContentOpportunityWorkflow,
        change_plan: ChangePlanWorkflow,
        content_draft: ContentDraftWorkflow,
        history_store: HistoryStore,
        id_factory: Callable[[], str] | None = None,
        clock: Callable[[], datetime] | None = None,
        progress_observer: EndToEndProgressObserver | None = None,
    ) -> None:
        self._site_crawl = site_crawl
        self._packet_builder = packet_builder
        self._planning_site_auditor = planning_site_auditor
        self._industry_research = industry_research
        self._content_opportunity = content_opportunity
        self._change_plan = change_plan
        self._content_draft = content_draft
        self._history_store = history_store
        self._id_factory = id_factory or (lambda: str(uuid4()))
        self._clock = clock or (lambda: datetime.now(UTC))
        self._progress_observer = progress_observer
        change_plan_diagnostics = getattr(change_plan, "run_diagnostics", None)
        self._run_diagnostics = (
            change_plan_diagnostics
            if isinstance(change_plan_diagnostics, RunDiagnosticContext)
            else RunDiagnosticContext()
        )

    @property
    def run_diagnostics(self) -> RunDiagnosticContext:
        """Return transient diagnostics available only in this process."""

        return self._run_diagnostics

    async def run(self, request: EndToEndRunRequest) -> EndToEndRunResult:
        if not isinstance(request, EndToEndRunRequest):
            raise TypeError("End-to-end workflow requires EndToEndRunRequest.")
        self._run_diagnostics.clear()
        run_id = self._id_factory()
        running = WorkflowRun(
            run_id=run_id,
            site_key=site_key_from_url(request.site_url),
            workflow_name=_WORKFLOW_NAME,
            started_at=self._clock(),
            completed_at=None,
            status=RunStatus.RUNNING,
            failure_kind=None,
            sanitized_error=None,
        )
        live_input = LiveAnalysisInput(
            website_url=request.site_url,
            seo_goal=request.research_question,
            target_language=request.target_language,
        )
        analysis_input = AnalysisRunInput(
            run_id=run_id,
            website_url=live_input.website_url,
            seo_goal=live_input.seo_goal,
            target_language=live_input.target_language,
            display_identity=live_input.display_identity,
        )
        await asyncio.to_thread(
            self._history_store.create_analysis_run,
            running,
            analysis_input,
        )
        self._notify(
            EndToEndProgressEventKind.RUN_STARTED,
            run_id,
        )

        try:
            return await self._run_created(run_id, request)
        finally:
            self._notify(
                EndToEndProgressEventKind.RUN_FINISHED,
                run_id,
            )

    async def _run_created(
        self,
        run_id: str,
        request: EndToEndRunRequest,
    ) -> EndToEndRunResult:

        try:
            outcome = await self._run_stages(run_id, request)
        except asyncio.CancelledError:
            await self._best_effort_finish(
                run_id,
                failure_kind="cancelled",
                sanitized_error="Planning workflow was cancelled.",
            )
            raise
        except _AppendFailure as failure:
            await self._best_effort_finish(
                run_id,
                failure_kind="history.append_failed",
                sanitized_error="Artifact persistence failed.",
            )
            raise failure.error.with_traceback(failure.error.__traceback__)
        except Exception:
            await self._best_effort_finish(
                run_id,
                failure_kind="internal_error",
                sanitized_error="Planning workflow failed unexpectedly.",
            )
            raise

        if outcome.stopped_stage is not None:
            assert outcome.failure_kind is not None
            assert outcome.sanitized_error is not None
            try:
                terminal = await self._finish(
                    run_id,
                    status=RunStatus.FAILED,
                    failure_kind=outcome.failure_kind,
                    sanitized_error=outcome.sanitized_error,
                    final_validation_category=outcome.final_validation_category,
                    writer_attempt_count=outcome.writer_attempt_count,
                )
            except HistoryStoreError:
                raise
            except asyncio.CancelledError:
                await self._best_effort_finish(
                    run_id,
                    failure_kind="cancelled",
                    sanitized_error="Planning workflow was cancelled.",
                )
                raise
            except Exception:
                await self._best_effort_finish(
                    run_id,
                    failure_kind="internal_error",
                    sanitized_error="Planning workflow failed unexpectedly.",
                )
                raise
            return EndToEndRunResult(
                run=terminal,
                artifacts=outcome.artifacts,
                stopped_stage=outcome.stopped_stage,
                crawl_report=outcome.crawl_report,
                terminal_report=outcome.terminal_report,
                requires_human_review=False,
            )

        assert isinstance(outcome.terminal_report, ContentDraftReport)
        try:
            completed_at = self._clock()
        except Exception:
            await self._best_effort_finish(
                run_id,
                failure_kind="internal_error",
                sanitized_error="Planning workflow failed unexpectedly.",
            )
            raise
        try:
            terminal = await asyncio.to_thread(
                self._history_store.finish_run,
                run_id,
                status=RunStatus.SUCCEEDED,
                completed_at=completed_at,
            )
        except asyncio.CancelledError:
            await self._best_effort_finish(
                run_id,
                failure_kind="cancelled",
                sanitized_error="Planning workflow was cancelled.",
            )
            raise
        return EndToEndRunResult(
            run=terminal,
            artifacts=outcome.artifacts,
            stopped_stage=None,
            crawl_report=outcome.crawl_report,
            terminal_report=outcome.terminal_report,
            requires_human_review=True,
        )

    def _notify(
        self,
        kind: EndToEndProgressEventKind,
        run_id: str,
        stage: EndToEndStage | None = None,
    ) -> None:
        if self._progress_observer is None:
            return
        try:
            self._progress_observer(
                EndToEndProgressEvent(
                    kind=kind,
                    run_id=run_id,
                    stage=stage,
                )
            )
        except Exception:
            return

    def _stage_completed(self, run_id: str, stage: EndToEndStage) -> None:
        self._notify(EndToEndProgressEventKind.STAGE_COMPLETED, run_id, stage)

    async def _run_stages(
        self,
        run_id: str,
        request: EndToEndRunRequest,
    ) -> _PlanningOutcome:
        artifacts: list[ArtifactRef] = []
        self._notify(
            EndToEndProgressEventKind.STAGE_STARTED,
            run_id,
            EndToEndStage.CRAWL,
        )
        crawl = await self._site_crawl.run(request.site_url)
        if not isinstance(crawl, SiteCrawlReport):
            raise TypeError("Site crawl returned an invalid report.")
        if not self._usable_crawl(crawl):
            planning_failure = classify_crawl_failure(crawl)
            return self._failure(
                run_id,
                artifacts,
                crawl,
                stage=EndToEndStage.CRAWL,
                failure_kind="site_crawl.no_usable_pages",
                sanitized_error=planning_failure.sanitized_error,
            )

        packet = self._packet_builder.build(crawl)
        artifacts.append(
            await self._append(run_id, ArtifactType.SITE_CONTENT, packet)
        )
        self._stage_completed(run_id, EndToEndStage.CRAWL)

        self._notify(
            EndToEndProgressEventKind.STAGE_STARTED,
            run_id,
            EndToEndStage.SITE_AUDIT,
        )
        try:
            audit = self._planning_site_auditor.audit_crawl(crawl)
        except Exception:
            return self._failure(
                run_id,
                artifacts,
                crawl,
                stage=EndToEndStage.SITE_AUDIT,
                failure_kind="site_audit.exception",
                sanitized_error="Site audit stage failed.",
            )
        if not isinstance(audit, SiteAuditResult):
            return self._failure(
                run_id,
                artifacts,
                crawl,
                stage=EndToEndStage.SITE_AUDIT,
                failure_kind="site_audit.invalid_result",
                sanitized_error="Site audit returned an invalid result.",
            )
        if audit.status is not AuditStatus.SUCCESS:
            return self._failure(
                run_id,
                artifacts,
                crawl,
                stage=EndToEndStage.SITE_AUDIT,
                terminal_report=audit,
                failure_kind="site_audit.failed",
                sanitized_error="Site audit stage failed.",
            )
        artifacts.append(await self._append(run_id, ArtifactType.SITE_AUDIT, audit))
        self._stage_completed(run_id, EndToEndStage.SITE_AUDIT)

        self._notify(
            EndToEndProgressEventKind.STAGE_STARTED,
            run_id,
            EndToEndStage.INDUSTRY_RESEARCH,
        )
        research_query = build_research_query(crawl, request.research_question)
        research = await self._industry_research.run(
            research_query,
            request.target_language,
        )
        if not isinstance(research, ResearchReport):
            raise TypeError("Industry research returned an invalid report.")
        if research.status is not ResearchStatus.SUCCESS:
            return self._failure(
                run_id,
                artifacts,
                crawl,
                stage=EndToEndStage.INDUSTRY_RESEARCH,
                terminal_report=research,
                failure_kind=f"industry_research.{research.status.value}",
                sanitized_error="Industry research stage failed.",
            )
        artifacts.append(
            await self._append(run_id, ArtifactType.INDUSTRY_RESEARCH, research)
        )
        self._stage_completed(run_id, EndToEndStage.INDUSTRY_RESEARCH)

        self._notify(
            EndToEndProgressEventKind.STAGE_STARTED,
            run_id,
            EndToEndStage.CONTENT_OPPORTUNITY,
        )
        opportunity = await self._content_opportunity.run(packet, research, audit)
        if not isinstance(opportunity, ContentOpportunityReport):
            raise TypeError("Content opportunity returned an invalid report.")
        if opportunity.status is not ContentOpportunityStatus.SUCCESS:
            return self._failure(
                run_id,
                artifacts,
                crawl,
                stage=EndToEndStage.CONTENT_OPPORTUNITY,
                terminal_report=opportunity,
                failure_kind=f"content_opportunity.{opportunity.status.value}",
                sanitized_error="Content opportunity stage failed.",
                final_validation_category=opportunity.final_validation_category,
                writer_attempt_count=opportunity.writer_attempt_count,
            )
        artifacts.append(
            await self._append(
                run_id,
                ArtifactType.CONTENT_OPPORTUNITY,
                opportunity,
            )
        )
        self._stage_completed(run_id, EndToEndStage.CONTENT_OPPORTUNITY)

        self._notify(
            EndToEndProgressEventKind.STAGE_STARTED,
            run_id,
            EndToEndStage.CHANGE_PLAN,
        )
        change_plan = await self._change_plan.run(packet, opportunity)
        if not isinstance(change_plan, ChangePlanReport):
            raise TypeError("Change plan returned an invalid report.")
        if change_plan.status is not ChangePlanStatus.SUCCESS:
            return self._failure(
                run_id,
                artifacts,
                crawl,
                stage=EndToEndStage.CHANGE_PLAN,
                terminal_report=change_plan,
                failure_kind=f"change_plan.{change_plan.status.value}",
                sanitized_error="Change plan stage failed.",
                final_validation_category=change_plan.final_validation_category,
                writer_attempt_count=change_plan.writer_attempt_count,
            )
        artifacts.append(
            await self._append(run_id, ArtifactType.CHANGE_PLAN, change_plan)
        )
        self._stage_completed(run_id, EndToEndStage.CHANGE_PLAN)

        self._notify(
            EndToEndProgressEventKind.STAGE_STARTED,
            run_id,
            EndToEndStage.CONTENT_DRAFT,
        )
        draft = await self._content_draft.run(
            ContentDraftInput(
                site_content=packet,
                opportunity_report=opportunity,
                change_plan_report=change_plan,
                target_language=request.target_language,
            )
        )
        if not isinstance(draft, ContentDraftReport):
            raise TypeError("Content draft returned an invalid report.")
        if draft.error == ContentDraftValidationCategory.NUMERIC_NOT_GROUNDED.value:
            self._run_diagnostics.numeric_grounding_violation = getattr(
                self._content_draft, "last_numeric_grounding_violation", None
            )
        if draft.error == ContentDraftValidationCategory.CLAIM_TYPE_CONTRACT.value:
            self._run_diagnostics.claim_type_violation = getattr(
                self._content_draft, "last_claim_type_violation", None
            )
        if draft.error == ContentDraftValidationCategory.BLOCK_BUDGET.value:
            self._run_diagnostics.block_budget_violation = getattr(
                self._content_draft, "last_block_budget_violation", None
            )
        if draft.error == ContentDraftValidationCategory.COMPETITOR_MENTION.value:
            self._run_diagnostics.competitor_mention_violation = getattr(
                self._content_draft, "last_competitor_mention_violation", None
            )
        if draft.status is not ContentDraftStatus.SUCCESS:
            return self._failure(
                run_id,
                artifacts,
                crawl,
                stage=EndToEndStage.CONTENT_DRAFT,
                terminal_report=draft,
                failure_kind=f"content_draft.{draft.status.value}",
                sanitized_error="Content draft stage failed.",
            )
        artifacts.append(
            await self._append(run_id, ArtifactType.CONTENT_DRAFT, draft)
        )
        self._stage_completed(run_id, EndToEndStage.CONTENT_DRAFT)
        return _PlanningOutcome(
            artifacts=tuple(artifacts),
            crawl_report=crawl,
            terminal_report=draft,
            stopped_stage=None,
            failure_kind=None,
            sanitized_error=None,
        )

    async def _append(
        self,
        run_id: str,
        artifact_type: ArtifactType,
        payload: object,
    ) -> ArtifactRef:
        artifact = ArtifactRecord(
            artifact_id=self._id_factory(),
            run_id=run_id,
            artifact_type=artifact_type,
            payload_version=_PAYLOAD_VERSION,
            created_at=self._clock(),
            payload=payload,
        )
        try:
            await asyncio.to_thread(self._history_store.append_artifact, artifact)
        except HistoryStoreError as exc:
            raise _AppendFailure(exc) from exc
        return ArtifactRef(
            artifact_id=artifact.artifact_id,
            artifact_type=artifact.artifact_type,
            payload_version=artifact.payload_version,
        )

    async def _finish(
        self,
        run_id: str,
        *,
        status: RunStatus,
        failure_kind: str,
        sanitized_error: str,
        final_validation_category: PlanningValidationCategory | None = None,
        writer_attempt_count: int | None = None,
    ) -> WorkflowRun:
        return await asyncio.to_thread(
            self._history_store.finish_run,
            run_id,
            status=status,
            completed_at=self._clock(),
            failure_kind=failure_kind,
            sanitized_error=sanitized_error,
            final_validation_category=final_validation_category,
            writer_attempt_count=writer_attempt_count,
        )

    async def _best_effort_finish(
        self,
        run_id: str,
        *,
        failure_kind: str,
        sanitized_error: str,
    ) -> None:
        try:
            await asyncio.shield(
                self._finish(
                    run_id,
                    status=RunStatus.FAILED,
                    failure_kind=failure_kind,
                    sanitized_error=sanitized_error,
                )
            )
        except Exception:
            return

    def _failure(
        self,
        run_id: str,
        artifacts: list[ArtifactRef],
        crawl_report: SiteCrawlReport,
        *,
        stage: EndToEndStage,
        failure_kind: str,
        sanitized_error: str,
        terminal_report: TerminalReport | None = None,
        final_validation_category: PlanningValidationCategory | None = None,
        writer_attempt_count: int | None = None,
    ) -> _PlanningOutcome:
        self._notify(EndToEndProgressEventKind.STAGE_FAILED, run_id, stage)
        return _PlanningOutcome(
            artifacts=tuple(artifacts),
            crawl_report=crawl_report,
            terminal_report=terminal_report,
            stopped_stage=stage,
            failure_kind=failure_kind,
            sanitized_error=sanitized_error,
            final_validation_category=final_validation_category,
            writer_attempt_count=writer_attempt_count,
        )

    @staticmethod
    def _usable_crawl(report: SiteCrawlReport) -> bool:
        return (
            isinstance(report, SiteCrawlReport)
            and report.exact_origin is not None
            and any(
                page.extraction_status is PageExtractionStatus.SUCCESS
                and isinstance(page.body_text, str)
                and bool(page.body_text.strip())
                for page in report.pages
            )
            and report.stop_reason
            not in {
                CrawlStopReason.INVALID_SEED,
                CrawlStopReason.ROBOTS_POLICY,
            }
        )
