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
)
from foreign_trade_geo_agent.core.content_opportunity import (
    ContentOpportunityReport,
    ContentOpportunityStatus,
)
from foreign_trade_geo_agent.core.crawling import CrawlStopReason, SiteCrawlReport
from foreign_trade_geo_agent.core.extraction import PageExtractionStatus
from foreign_trade_geo_agent.core.history import (
    ArtifactRecord,
    ArtifactType,
    HistoryStoreError,
    RunStatus,
    WorkflowRun,
    site_key_from_url,
)
from foreign_trade_geo_agent.core.orchestration import (
    ArtifactRef,
    EndToEndRunRequest,
    EndToEndRunResult,
    EndToEndStage,
    TerminalReport,
)
from foreign_trade_geo_agent.core.ports import HistoryStore, SiteAuditor
from foreign_trade_geo_agent.core.research import ResearchReport, ResearchStatus
from foreign_trade_geo_agent.workflows.change_plan import ChangePlanWorkflow
from foreign_trade_geo_agent.workflows.content_draft import ContentDraftWorkflow
from foreign_trade_geo_agent.workflows.content_opportunity import (
    ContentOpportunityWorkflow,
)
from foreign_trade_geo_agent.workflows.industry_research import (
    IndustryResearchWorkflow,
)
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
        site_auditor: SiteAuditor,
        industry_research: IndustryResearchWorkflow,
        content_opportunity: ContentOpportunityWorkflow,
        change_plan: ChangePlanWorkflow,
        content_draft: ContentDraftWorkflow,
        history_store: HistoryStore,
        id_factory: Callable[[], str] | None = None,
        clock: Callable[[], datetime] | None = None,
        audit_timeout: float = 60.0,
    ) -> None:
        self._site_crawl = site_crawl
        self._packet_builder = packet_builder
        self._site_auditor = site_auditor
        self._industry_research = industry_research
        self._content_opportunity = content_opportunity
        self._change_plan = change_plan
        self._content_draft = content_draft
        self._history_store = history_store
        self._id_factory = id_factory or (lambda: str(uuid4()))
        self._clock = clock or (lambda: datetime.now(UTC))
        if type(audit_timeout) not in {int, float} or audit_timeout <= 0:
            raise ValueError("audit_timeout must be positive.")
        self._audit_timeout = float(audit_timeout)

    async def run(self, request: EndToEndRunRequest) -> EndToEndRunResult:
        if not isinstance(request, EndToEndRunRequest):
            raise TypeError("End-to-end workflow requires EndToEndRunRequest.")
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
        await asyncio.to_thread(self._history_store.create_run, running)

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

    async def _run_stages(
        self,
        run_id: str,
        request: EndToEndRunRequest,
    ) -> _PlanningOutcome:
        artifacts: list[ArtifactRef] = []
        crawl = await self._site_crawl.run(request.site_url)
        if not isinstance(crawl, SiteCrawlReport):
            raise TypeError("Site crawl returned an invalid report.")
        if not self._usable_crawl(crawl):
            return self._failure(
                artifacts,
                crawl,
                stage=EndToEndStage.CRAWL,
                failure_kind="site_crawl.no_usable_pages",
                sanitized_error="Site crawl produced no usable evidence.",
            )

        packet = self._packet_builder.build(crawl)
        artifacts.append(
            await self._append(run_id, ArtifactType.SITE_CONTENT, packet)
        )

        try:
            audit = await asyncio.wait_for(
                asyncio.to_thread(self._site_auditor.audit_site, request.site_url),
                timeout=self._audit_timeout,
            )
        except (TimeoutError, asyncio.TimeoutError):
            return self._failure(
                artifacts,
                crawl,
                stage=EndToEndStage.SITE_AUDIT,
                failure_kind="site_audit.timeout",
                sanitized_error="Site audit stage timed out.",
            )
        except Exception:
            return self._failure(
                artifacts,
                crawl,
                stage=EndToEndStage.SITE_AUDIT,
                failure_kind="site_audit.exception",
                sanitized_error="Site audit stage failed.",
            )
        if not isinstance(audit, SiteAuditResult):
            return self._failure(
                artifacts,
                crawl,
                stage=EndToEndStage.SITE_AUDIT,
                failure_kind="site_audit.invalid_result",
                sanitized_error="Site audit returned an invalid result.",
            )
        if audit.status is not AuditStatus.SUCCESS:
            return self._failure(
                artifacts,
                crawl,
                stage=EndToEndStage.SITE_AUDIT,
                terminal_report=audit,
                failure_kind="site_audit.failed",
                sanitized_error="Site audit stage failed.",
            )
        artifacts.append(await self._append(run_id, ArtifactType.SITE_AUDIT, audit))

        research = await self._industry_research.run(request.research_question)
        if not isinstance(research, ResearchReport):
            raise TypeError("Industry research returned an invalid report.")
        if research.status is not ResearchStatus.SUCCESS:
            return self._failure(
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

        opportunity = await self._content_opportunity.run(packet, research, audit)
        if not isinstance(opportunity, ContentOpportunityReport):
            raise TypeError("Content opportunity returned an invalid report.")
        if opportunity.status is not ContentOpportunityStatus.SUCCESS:
            return self._failure(
                artifacts,
                crawl,
                stage=EndToEndStage.CONTENT_OPPORTUNITY,
                terminal_report=opportunity,
                failure_kind=f"content_opportunity.{opportunity.status.value}",
                sanitized_error="Content opportunity stage failed.",
            )
        artifacts.append(
            await self._append(
                run_id,
                ArtifactType.CONTENT_OPPORTUNITY,
                opportunity,
            )
        )

        change_plan = await self._change_plan.run(packet, opportunity)
        if not isinstance(change_plan, ChangePlanReport):
            raise TypeError("Change plan returned an invalid report.")
        if change_plan.status is not ChangePlanStatus.SUCCESS:
            return self._failure(
                artifacts,
                crawl,
                stage=EndToEndStage.CHANGE_PLAN,
                terminal_report=change_plan,
                failure_kind=f"change_plan.{change_plan.status.value}",
                sanitized_error="Change plan stage failed.",
            )
        artifacts.append(
            await self._append(run_id, ArtifactType.CHANGE_PLAN, change_plan)
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
        if draft.status is not ContentDraftStatus.SUCCESS:
            return self._failure(
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
    ) -> WorkflowRun:
        return await asyncio.to_thread(
            self._history_store.finish_run,
            run_id,
            status=status,
            completed_at=self._clock(),
            failure_kind=failure_kind,
            sanitized_error=sanitized_error,
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

    @staticmethod
    def _failure(
        artifacts: list[ArtifactRef],
        crawl_report: SiteCrawlReport,
        *,
        stage: EndToEndStage,
        failure_kind: str,
        sanitized_error: str,
        terminal_report: TerminalReport | None = None,
    ) -> _PlanningOutcome:
        return _PlanningOutcome(
            artifacts=tuple(artifacts),
            crawl_report=crawl_report,
            terminal_report=terminal_report,
            stopped_stage=stage,
            failure_kind=failure_kind,
            sanitized_error=sanitized_error,
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
