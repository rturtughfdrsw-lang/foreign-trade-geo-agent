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
    article_scope_error,
)
from foreign_trade_geo_agent.core.evidence_sufficiency import aware_time


def reviewed_draft_input(snapshot: IntakeSnapshot, assessment: SemanticAssessment, *, now: datetime, propose_interpretations: bool = False) -> ContentDraftInput:
    """Lossless bounded projection of a current review; NEVER Draft permission.

    E facts retain document identity, hashes and exact offsets. Only interpretations
    explicitly approved by the trusted reviewer enter the inference allowlist.
    The native E execution profile remains TEST-only.
    """
    from foreign_trade_geo_agent.core.content_draft import ArticleWritingBrief, MAX_CLAIMS_PER_DRAFT
    from foreign_trade_geo_agent.core.draft_customer_evidence import (
        DraftCustomerEvidence, DraftCustomerSource, DraftCustomerFact, DraftInterpretation, native_scope_digest,
    )
    import hashlib
    validate_assessment(snapshot, assessment, now)
    require(snapshot.plan_bound and article_scope_error(assessment) is None
            and all(d.verdict is SupportVerdict.SUPPORTED for d in assessment.decisions)
            and snapshot.task.section_briefs
            and snapshot.planning_input.change_plan_report.operations[0].new_resource_spec.section_briefs
                == CustomerPlanningContext(snapshot).section_briefs())
    spans = tuple(dict.fromkeys(s for d in assessment.decisions for s in d.spans))
    for brief in snapshot.planning_input.change_plan_report.operations[0].new_resource_spec.section_briefs:
        options = tuple(i for i in assessment.interpretations
                        if brief.limitations in i.text and brief.procurement_action in i.text
                        and {s.evidence_id for s in i.spans} <= set(brief.supporting_evidence))
        require(propose_interpretations or (bool(options) and all(any(set(d.spans) & set(i.spans) for i in options)
            for d in assessment.decisions if d.requirement_id in brief.requirement_ids)))
    interpreted = {s for i in assessment.interpretations for s in i.spans}
    # Conservative feasible envelope: direct facts + one interpretation and one
    # direct example per section + CTA. Reject impossible briefs before a call.
    require(propose_interpretations or len(set(spans) - interpreted) + 2 * len(snapshot.task.section_briefs) + 1 <= MAX_CLAIMS_PER_DRAFT)
    sources, refs = [], {}
    for record in snapshot.active_evidence:
        s = record.supplement
        selected = tuple(p for p in spans if p.evidence_id == s.evidence_id)
        require(bool(selected))
        facts = tuple(DraftCustomerFact(f'{s.evidence_id}.F{i:02d}', p.start, p.end, p.quote,
                          tuple(d.requirement_id for d in assessment.decisions if p in d.spans))
                      for i, p in enumerate(selected, 1))
        refs.update(zip(selected, (f.fact_ref for f in facts)))
        first = selected[0]
        sources.append(DraftCustomerSource(s.evidence_id, record.evidence_version, s.requirement_ids,
            s.source_label, s.source_locator, s.content, hashlib.sha256(s.content.encode()).hexdigest(),
            first.start, first.end, first.quote, facts))
    value = snapshot.planning_input
    bundle = DraftCustomerEvidence(snapshot.task.project_id, snapshot.task.customer_id, snapshot.task.task_id,
        snapshot.task.task_version, snapshot.plan_version, snapshot.evidence_version, snapshot.revision,
        snapshot_digest(snapshot), native_scope_digest(value.site_content, value.opportunity_report,
            value.change_plan_report.operations[0]), 'C1', assessment.reviewer_id, assessment.reviewed_at,
        'TEST_ONLY_SUPPORTED_NOT_HUMAN_SIGNOFF', tuple(sources), tuple(DraftInterpretation(
            i.text, tuple(refs[p] for p in i.spans), i.limitation, i.procurement_action, i.proposal) for i in assessment.interpretations if not propose_interpretations))
    brief = ArticleWritingBrief(snapshot_digest(snapshot), snapshot.task.goal, snapshot.task.search_intent,
        ('Answer every reader question using the section evidence map; distinguish facts, reviewed interpretations and unknowns.',
         'Keep background concise. Explain purchasing implications and end with a concrete RFQ or verification CTA.'),
        snapshot.task.article_type, snapshot.task.reader_problem)
    return replace(value, customer_evidence=bundle, writing_brief=brief, propose_interpretations=propose_interpretations)


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
        result = EvidenceIntakeWorkflow(self._store).check(self._project_id, self._task_id, now=datetime.now().astimezone())
        if result.reason in {"ARTICLE_SCOPE_REVIEW_REQUIRED", "ARTICLE_SCOPE_MISMATCH"}:
            return result.reason
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
                # A structured article needs a freshly reviewed scope map;
                # legacy whole-point deletion cannot silently carry stale questions.
                require(not task.section_briefs)
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
            scope_error = article_scope_error(assessment)
            if (snapshot.task.section_briefs and (snapshot.planning_input.change_plan_report.operations[0].new_resource_spec is None
                    or snapshot.planning_input.change_plan_report.operations[0].new_resource_spec.section_briefs
                       != CustomerPlanningContext(snapshot).section_briefs())):
                scope_error = 'ARTICLE_SCOPE_MISMATCH'
            if assessment is not None and assessment.scope_coverage is not None:
                for requirement in assessment.scope_coverage.missing_requirements:
                    gaps.append(EvidenceGap(requirement, "C1", snapshot.point_subjects[requirement.point_index],
                        "ARTICLE_SCOPE_REQUIREMENT_MISSING", assessment.scope_coverage.reason))
            status = IntakeStatus.BLOCKED if gaps or native_error or review_error or scope_error else IntakeStatus.CANDIDATE_FOR_REVIEW
            result = IntakeCheck(digest, status, tuple(gaps),
                                 native_error or (scope_error if assessment is not None else None)
                                 or ("EVIDENCE_GAPS_REMAIN" if gaps else scope_error or review_error), assessment)
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
