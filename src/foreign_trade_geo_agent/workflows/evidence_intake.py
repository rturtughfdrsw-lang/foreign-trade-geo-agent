"""Local bounded customer supplement loop; no writer, LLM, fetcher or CMS."""
from dataclasses import replace
from datetime import datetime

from foreign_trade_geo_agent.core.content_draft import ContentDraftInput
from foreign_trade_geo_agent.core.evidence_intake import (
    CustomerContext, CustomerEvidenceRequest, CustomerSubmission, EvidenceGap, EvidenceIntakeStore,
    EvidenceRecord, EvidenceSemanticReviewer, EvidenceTask, IntakeCheck,
    IntakeSnapshot, IntakeStatus, ScopeConsent, SemanticAssessment, SupportVerdict,
    native_plan_error, require, snapshot_digest, validate_assessment,
    ClaimEvidenceReview, CustomerPlanningContext, IntakeChangePlanner, PlanningReviewCandidate,
    rebind_preserves_task,
    digest_valid,
)
from foreign_trade_geo_agent.core.evidence_sufficiency import aware_time


class EvidenceIntakeDraftAdmission:
    """Application-bound task scope checked at the actual ordinary Draft entry.

    This release has no customer-evidence Draft authorization purpose. Even
    a current, semantically reviewed candidate is refused. Composition must
    attach this boundary for an intake task. The shared production runtime also
    refuses unbound legacy calls; this port supplies version diagnostics only.
    """
    def __init__(self, store: EvidenceIntakeStore, project_id: str, task_id: str,
                 *, expected_snapshot_sha256: str | None = None):
        from foreign_trade_geo_agent.core.evidence_sufficiency import bounded_id
        require(bounded_id(project_id) and bounded_id(task_id)
                and (expected_snapshot_sha256 is None or digest_valid(expected_snapshot_sha256)))
        self._store, self._project_id, self._task_id = store, project_id, task_id
        self._expected = expected_snapshot_sha256

    def rejection_reason(self, value: ContentDraftInput) -> str:
        current = self._store.latest(self._project_id, self._task_id)
        if (type(current) is not IntakeSnapshot
            or current.task.project_id != self._project_id or current.task.task_id != self._task_id):
            return "INTAKE_TASK_BINDING_INVALID"
        if self._expected is None:
            return "INTAKE_BINDING_REQUIRED"
        if snapshot_digest(current) != self._expected:
            return "STALE_INTAKE_BINDING"
        if not current.plan_bound or value != current.planning_input:
            return "INTAKE_PLAN_BINDING_INVALID"
        return "CUSTOMER_EVIDENCE_DRAFT_AUTHORIZATION_REQUIRED"


class EvidenceIntakeWorkflow:
    def __init__(self, store: EvidenceIntakeStore, *, reviewer: EvidenceSemanticReviewer | None = None):
        self._store = store
        self._reviewer = reviewer

    def register(self, task: EvidenceTask, planning_input: ContentDraftInput) -> IntakeSnapshot:
        """Analyst-authored obligations are required, never inferred from counts."""
        try:
            subjects = tuple(p.subject for p in planning_input.change_plan_report.operations[0].content_points)
            require(native_plan_error(planning_input, subjects) is None)
            require(task.task_version == 1)
            snapshot = IntakeSnapshot(1, task, 1, 1, planning_input, True, subjects)
            self._store.create_snapshot(snapshot)
            return snapshot
        except Exception:
            raise ValueError("INTAKE_REGISTRATION_REJECTED") from None

    def submit(self, project_id: str, task_id: str, submission: CustomerSubmission,
               *, customer: CustomerContext) -> IntakeSnapshot:
        """Authorized local customer boundary. JSON cannot supply actor/time."""
        try:
            require(type(submission) is CustomerSubmission and type(customer) is CustomerContext)
            current = self._store.latest(project_id, task_id)
            digest = snapshot_digest(current)
            require(submission.expected_snapshot_sha256 == digest
                    and customer.customer_id == current.task.customer_id
                    and submission.submission_id not in current.submission_ids)
            task, subjects = current.task, current.point_subjects
            consents = current.scope_consents
            adjustment = submission.scope_adjustment
            if adjustment is not None:
                require(adjustment.customer_consents is True)
                retained = tuple(r for r in task.requirements if r.requirement_id in adjustment.retained_requirement_ids)
                require(tuple(r.requirement_id for r in retained) == adjustment.retained_requirement_ids)
                indexes = tuple(dict.fromkeys(r.point_index for r in retained))
                # Delete whole task points only. No hidden weakening of one
                # fact obligation while keeping the same explanation promise.
                require(tuple(r for r in task.requirements if r.point_index in indexes) == retained)
                require(indexes == tuple(sorted(indexes)))
                mapping = {old: new for new, old in enumerate(indexes)}
                task = replace(task, task_version=task.task_version + 1, goal=adjustment.new_goal,
                               requirements=tuple(replace(r, point_index=mapping[r.point_index]) for r in retained))
                subjects = tuple(subjects[i] for i in indexes)
                consents += (ScopeConsent(digest, submission.submission_id, adjustment, customer),)
            requirements = {r.requirement_id: r for r in task.requirements}
            existing = {e.supplement.evidence_id: e.supplement for e in current.active_evidence}
            all_ids = {e.supplement.evidence_id for e in current.evidence}
            records = []
            ev = current.evidence_version + bool(submission.supplements)
            for supplement in submission.supplements:
                require(supplement.evidence_id not in all_ids
                        and all(r in requirements and supplement.method in requirements[r].allowed_methods
                                for r in supplement.requirement_ids))
                if supplement.supersedes is not None:
                    previous = existing.pop(supplement.supersedes, None)
                    require(previous is not None and previous.requirement_ids == supplement.requirement_ids)
                records.append(EvidenceRecord(supplement, ev, submission.submission_id,
                                              customer.customer_id, customer.actor_id, customer.recorded_at))
            updated = replace(current, revision=current.revision + 1, task=task,
                              evidence_version=ev, plan_bound=False, point_subjects=subjects,
                              evidence=(*current.evidence, *records), scope_consents=consents,
                              submission_ids=(*current.submission_ids, submission.submission_id))
            self._store.append(digest, updated)
            return updated
        except Exception:
            raise ValueError("CUSTOMER_SUBMISSION_REJECTED") from None

    def rebind_plan(self, project_id: str, task_id: str, *, expected_sha256: str,
                    planning_input: ContentDraftInput) -> IntakeSnapshot:
        """Fresh native structural validation and a NEW binding, never old sufficiency.

        Reusing the operation wording is allowed after revalidation. Retained
        point subjects and EXPLAIN intent cannot change without customer consent.
        Customer facts are not silently injected into the legacy source catalogs.
        """
        try:
            current = self._store.latest(project_id, task_id)
            require(snapshot_digest(current) == expected_sha256 and not current.plan_bound
                    and native_plan_error(planning_input, current.point_subjects) is None
                    and rebind_preserves_task(current, planning_input))
            updated = replace(current, revision=current.revision + 1, plan_version=current.plan_version + 1,
                              planning_input=planning_input, plan_bound=True)
            self._store.append(expected_sha256, updated)
            return updated
        except Exception:
            raise ValueError("PLAN_REBIND_REJECTED") from None

    async def replan(self, project_id: str, task_id: str, *, expected_sha256: str,
                     planner: IntakeChangePlanner, now: datetime) -> PlanningReviewCandidate:
        """Run native Change Planning against exact attributed supplements.

        Revalidate the unchanged Opportunity and its P/S/A catalog using the
        native planner. Re-crawl/research is a separate new task, not an intake
        substitution. CAS rejects concurrent submissions during planning.
        """
        try:
            require(aware_time(now))
            current = self._store.latest(project_id, task_id)
            require(snapshot_digest(current) == expected_sha256 and not current.plan_bound)
            original = current.planning_input
            report = await planner.run(original.site_content, original.opportunity_report,
                task_id=task_id, customer_context=CustomerPlanningContext(current))
            value = replace(original, change_plan_report=report)
            bound = self.rebind_plan(project_id, task_id, expected_sha256=expected_sha256, planning_input=value)
            candidate = self.review_candidate(project_id, task_id, now=now)
            require(candidate.check.snapshot_sha256 == snapshot_digest(bound))
            return candidate
        except Exception:
            raise ValueError("INTAKE_REPLANNING_REJECTED") from None

    def review_candidate(self, project_id: str, task_id: str, *, now: datetime) -> PlanningReviewCandidate:
        """Missing/rejected evidence returns to intake; unreviewed materials await HUMAN review."""
        try:
            result = self.check(project_id, task_id, now=now)
            current = self._store.latest(project_id, task_id)
            require(current.plan_bound and snapshot_digest(current) == result.snapshot_sha256)
            decisions = {} if result.assessment is None else {d.requirement_id: d for d in result.assessment.decisions}
            claims = tuple(ClaimEvidenceReview(r, current.point_subjects[r.point_index],
                tuple(e for e in current.active_evidence if r.requirement_id in e.supplement.requirement_ids),
                decisions.get(r.requirement_id)) for r in current.task.requirements)
            return PlanningReviewCandidate(current, result, claims)
        except Exception:
            raise ValueError("INTAKE_REVIEW_CANDIDATE_REJECTED") from None

    def check(self, project_id: str, task_id: str, *, now: datetime) -> IntakeCheck:
        """Always reload/review current versions. Results are not execution tokens."""
        try:
            require(aware_time(now))
            snapshot = self._store.latest(project_id, task_id)
            digest = snapshot_digest(snapshot)
            native_error = native_plan_error(snapshot.planning_input, snapshot.point_subjects) if snapshot.plan_bound else "PLAN_REBIND_REQUIRED"
            assessment = None
            decisions = {}
            review_error = "HUMAN_SEMANTIC_REVIEW_REQUIRED"
            if self._reviewer is not None:
                try:
                    assessment = self._reviewer.assess(snapshot, now=now)
                    validate_assessment(snapshot, assessment, now)
                    require(snapshot_digest(snapshot) == digest)
                    decisions = {d.requirement_id: d for d in assessment.decisions}
                    review_error = None
                except Exception:
                    assessment = None
                    review_error = "HUMAN_SEMANTIC_REVIEW_REQUIRED"
            gaps = []
            for requirement in snapshot.task.requirements:
                materials = tuple(e for e in snapshot.active_evidence
                                  if requirement.requirement_id in e.supplement.requirement_ids)
                decision = decisions.get(requirement.requirement_id)
                if not materials:
                    code, reason = "MISSING_CUSTOMER_EVIDENCE", None
                elif decision is None:
                    code, reason = "HUMAN_SEMANTIC_REVIEW_REQUIRED", None
                elif decision.verdict is not SupportVerdict.SUPPORTED:
                    code, reason = decision.verdict.value, decision.reason
                else:
                    continue
                gaps.append(EvidenceGap(requirement, "C1", snapshot.point_subjects[requirement.point_index], code, reason))
            status = IntakeStatus.BLOCKED if gaps or native_error or review_error else IntakeStatus.CANDIDATE_FOR_REVIEW
            result = IntakeCheck(digest, status, tuple(gaps),
                                 native_error or ("EVIDENCE_GAPS_REMAIN" if gaps else review_error), assessment)
            # Atomic persistence rejects a customer update during review. No
            # old candidate survives a version change or an unavailable store.
            self._store.append_check(project_id, task_id, result)
            return result
        except Exception:
            raise ValueError("INTAKE_CHECK_REJECTED") from None

    def customer_request(self, project_id: str, task_id: str, *, now: datetime) -> CustomerEvidenceRequest:
        result = self.check(project_id, task_id, now=now)
        try:
            snapshot = self._store.latest(project_id, task_id)
            require(snapshot_digest(snapshot) == result.snapshot_sha256)
            return CustomerEvidenceRequest(project_id, snapshot.task.customer_id, task_id,
                snapshot.task.task_version, snapshot.plan_version, snapshot.evidence_version, snapshot.revision,
                result.snapshot_sha256, snapshot.task.goal, result.gaps, result.reason)
        except Exception:
            raise ValueError("CUSTOMER_REQUEST_REJECTED") from None
