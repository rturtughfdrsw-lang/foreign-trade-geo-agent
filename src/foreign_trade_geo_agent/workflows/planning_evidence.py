"""Recover an existing planning run into the existing customer intake journal.

The journal key is (original run ID, original Plan artifact ID). No copy of
history is treated as a new run, and no intake state grants Draft permission.
"""
from datetime import datetime

from foreign_trade_geo_agent.core.content_draft import ContentDraftInput
from foreign_trade_geo_agent.core.evidence_intake import (
    EvidenceTask, native_plan_error, require, snapshot_digest,
)
from foreign_trade_geo_agent.core.history import ArtifactType, RunStatus
from foreign_trade_geo_agent.core.ports import HistoryReader
from foreign_trade_geo_agent.workflows.evidence_intake import EvidenceIntakeWorkflow


class PlanningEvidenceWorkflow:
    def __init__(self, history: HistoryReader, intake: EvidenceIntakeWorkflow):
        self.history, self.intake = history, intake

    def origin(self, run_id: str, plan_id: str):
        run = self.history.get_run(run_id)
        request = self.history.get_analysis_run_input(run_id)
        require(run is not None and request is not None
                and run.workflow_name == "end_to_end_planning_v1"
                and (run.status is RunStatus.SUCCEEDED or
                     run.status is RunStatus.FAILED
                     and run.failure_kind == "content_draft.invalid_input"))
        artifacts = self.history.list_artifacts(run_id)
        selected = {}
        for kind in (ArtifactType.SITE_CONTENT, ArtifactType.SITE_AUDIT,
                     ArtifactType.CONTENT_OPPORTUNITY, ArtifactType.CHANGE_PLAN):
            matches = [a for a in artifacts if a.artifact_type is kind]
            require(len(matches) == 1 and matches[0].run_id == run_id)
            selected[kind] = matches[0]
        require(selected[ArtifactType.CHANGE_PLAN].artifact_id == plan_id)
        value = ContentDraftInput(selected[ArtifactType.SITE_CONTENT].payload,
            selected[ArtifactType.CONTENT_OPPORTUNITY].payload,
            selected[ArtifactType.CHANGE_PLAN].payload, request.target_language)
        return request, value, {k.value: v.artifact_id for k, v in selected.items()}

    def register(self, run_id, plan_id, *, customer_id, requirements,
                 article_type=None, search_intent=None, reader_problem=None, section_briefs=()):
        request, value, _ = self.origin(run_id, plan_id)
        # Obligations must be analyst authored. Topic grounding is not a
        # semantic sufficiency detector; unsupported profiles fail closed.
        task = EvidenceTask(run_id, customer_id, plan_id, 1, request.seo_goal, requirements,
                            article_type, search_intent, reader_problem, section_briefs)
        return self.intake.register(task, value)

    def bound_origin(self, run_id, plan_id, original):
        request, value, refs = self.origin(run_id, plan_id)
        require(original.revision == 1 and original.planning_input == value
                and original.task.project_id == run_id and original.task.task_id == plan_id
                and original.task.goal == request.seo_goal)
        return refs

    async def recheck(self, run_id, plan_id, *, expected_sha256, current, planner, now: datetime):
        require(snapshot_digest(current) == expected_sha256)
        if not current.plan_bound:
            # Existing replan performs native validation, preserves task/P/S/A,
            # increments Plan version and uses a CAS append against this epoch.
            return await self.intake.replan(run_id, plan_id,
                expected_sha256=expected_sha256, planner=planner, now=now)
        require(native_plan_error(current.planning_input, current.point_subjects) is None)
        return self.intake.review_candidate(run_id, plan_id, now=now)
