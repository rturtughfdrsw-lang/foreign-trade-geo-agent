"""Customer evidence collection, never semantic truth or Draft authorization.

V1 binds analyst-authored fact obligations to every point of one native
EXPLAIN expansion or new supporting resource. Customer evidence is separate
planning context, never observed P or external S evidence. No keyword/count
sufficiency heuristic.
"""
from __future__ import annotations

from .draft_customer_evidence import InterpretationProposal, MAX_INTERPRETATION_CHARS, MAX_INTERPRETATIONS
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from enum import Enum
import hashlib
import json
from typing import Protocol

from . import change_plan as cp
from .content_draft import ContentDraftInput, stable_content_draft_input_error
from .content_opportunity import ContentOpportunityReport
from .site_content import SiteContentPacket
from .evidence_sufficiency import aware_time, bounded_id

MAX_REQUIREMENTS = 32
MAX_EVIDENCE = 100
MAX_TEXT = 16_000
MAX_SNAPSHOT_BYTES = 1_500_000


def text(value: object, maximum: int = 1000) -> bool:
    return (type(value) is str and bool(value.strip()) and len(value) <= maximum
            and not any(ord(c) < 32 and c not in "\n\r\t" for c in value))


def version(value: object) -> bool:
    return type(value) is int and 1 <= value <= 1000


def require(condition: bool) -> None:
    if not condition:
        raise ValueError("EVIDENCE_INTAKE_INVALID")


class SupplementMethod(str, Enum):
    CUSTOMER_FACT = "CUSTOMER_FACT"
    TEXT_DOCUMENT = "TEXT_DOCUMENT"


@dataclass(frozen=True, slots=True)
class EvidenceRequirement:
    requirement_id: str
    point_index: int
    required_fact: str
    intended_use: str
    existing_material_insufficiency: str
    allowed_methods: tuple[SupplementMethod, ...]

    def __post_init__(self):
        require(bounded_id(self.requirement_id) and type(self.point_index) is int
                and 0 <= self.point_index < cp.MAX_CONTENT_POINTS_PER_OPERATION
                and all(text(v) for v in (self.required_fact, self.intended_use,
                                          self.existing_material_insufficiency))
                and type(self.allowed_methods) is tuple and bool(self.allowed_methods)
                and len(set(self.allowed_methods)) == len(self.allowed_methods)
                and all(type(m) is SupplementMethod for m in self.allowed_methods))


@dataclass(frozen=True, slots=True)
class EvidenceTask:
    project_id: str
    customer_id: str
    task_id: str
    task_version: int
    goal: str
    requirements: tuple[EvidenceRequirement, ...]
    article_type: str | None = None
    search_intent: str | None = None
    reader_problem: str | None = None
    section_briefs: tuple[cp.ArticleSectionBrief, ...] = ()

    def __post_init__(self):
        require(type(self.section_briefs) is tuple and len(self.section_briefs) <= cp.MAX_OUTLINE_HEADINGS)
        if self.section_briefs:
            require(len(self.section_briefs) >= cp.MIN_OUTLINE_HEADINGS
                    and all(text(v) for v in (self.article_type, self.search_intent, self.reader_problem))
                    and all(type(b) is cp.ArticleSectionBrief and not b.supporting_evidence for b in self.section_briefs)
                    and len({b.heading for b in self.section_briefs}) == len(self.section_briefs)
                    and {r for b in self.section_briefs for r in b.requirement_ids}
                        == {r.requirement_id for r in self.requirements})
        else:
            require(self.article_type is None and self.search_intent is None and self.reader_problem is None)
        require(all(bounded_id(v) for v in (self.project_id, self.customer_id, self.task_id))
                and version(self.task_version) and text(self.goal)
                and type(self.requirements) is tuple and 1 <= len(self.requirements) <= MAX_REQUIREMENTS
                and all(type(r) is EvidenceRequirement for r in self.requirements)
                and len({r.requirement_id for r in self.requirements}) == len(self.requirements))


@dataclass(frozen=True, slots=True)
class CustomerContext:
    """Authenticated by the integrating application, NEVER decoded from submission JSON.

    This local workflow does not implement customer login or signoff. Its
    composition boundary is trusted; declared source ownership is not verified.
    """
    customer_id: str
    actor_id: str
    recorded_at: datetime

    def __post_init__(self):
        require(bounded_id(self.customer_id) and bounded_id(self.actor_id) and aware_time(self.recorded_at))


@dataclass(frozen=True, slots=True)
class Supplement:
    evidence_id: str
    requirement_ids: tuple[str, ...]
    method: SupplementMethod
    content: str
    source_label: str
    source_locator: str
    declared_source_owner: str
    file_sha256: str | None = None
    supersedes: str | None = None

    def __post_init__(self):
        require(bounded_id(self.evidence_id) and type(self.requirement_ids) is tuple
                and 1 <= len(self.requirement_ids) <= MAX_REQUIREMENTS
                and all(bounded_id(v) for v in self.requirement_ids)
                and len(set(self.requirement_ids)) == len(self.requirement_ids)
                and type(self.method) is SupplementMethod and text(self.content, MAX_TEXT)
                and all(text(v) for v in (self.source_label, self.source_locator, self.declared_source_owner))
                and (self.supersedes is None or bounded_id(self.supersedes)))
        # Only lossless UTF-8 text uploads are supported by V1. No path fetching,
        # binary parsing or customer assertion that a file proves its claims.
        expected = hashlib.sha256(self.content.encode("utf-8")).hexdigest()
        require(self.file_sha256 == (expected if self.method is SupplementMethod.TEXT_DOCUMENT else None))


@dataclass(frozen=True, slots=True)
class ScopeAdjustment:
    new_goal: str
    retained_requirement_ids: tuple[str, ...]
    reason: str
    customer_consents: bool

    def __post_init__(self):
        require(text(self.new_goal) and text(self.reason)
                and type(self.retained_requirement_ids) is tuple
                and 1 <= len(self.retained_requirement_ids) <= MAX_REQUIREMENTS
                and all(bounded_id(v) for v in self.retained_requirement_ids)
                and len(set(self.retained_requirement_ids)) == len(self.retained_requirement_ids)
                and type(self.customer_consents) is bool)


@dataclass(frozen=True, slots=True)
class CustomerSubmission:
    submission_id: str
    expected_snapshot_sha256: str
    supplements: tuple[Supplement, ...] = ()
    scope_adjustment: ScopeAdjustment | None = None

    def __post_init__(self):
        require(bounded_id(self.submission_id) and digest_valid(self.expected_snapshot_sha256)
                and type(self.supplements) is tuple and len(self.supplements) <= 20
                and all(type(s) is Supplement for s in self.supplements)
                and len({s.evidence_id for s in self.supplements}) == len(self.supplements)
                and (self.scope_adjustment is None or type(self.scope_adjustment) is ScopeAdjustment)
                and bool(self.supplements or self.scope_adjustment))


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    supplement: Supplement
    evidence_version: int
    submission_id: str
    customer_id: str
    actor_id: str
    recorded_at: datetime

    def __post_init__(self):
        require(type(self.supplement) is Supplement and version(self.evidence_version)
                and all(bounded_id(v) for v in (self.submission_id, self.customer_id, self.actor_id))
                and aware_time(self.recorded_at))


@dataclass(frozen=True, slots=True)
class ScopeConsent:
    previous_snapshot_sha256: str
    submission_id: str
    adjustment: ScopeAdjustment
    context: CustomerContext

    def __post_init__(self):
        require(digest_valid(self.previous_snapshot_sha256) and bounded_id(self.submission_id)
                and type(self.adjustment) is ScopeAdjustment and self.adjustment.customer_consents is True
                and type(self.context) is CustomerContext)


@dataclass(frozen=True, slots=True)
class IntakeSnapshot:
    revision: int
    task: EvidenceTask
    evidence_version: int
    plan_version: int
    planning_input: ContentDraftInput
    plan_bound: bool
    point_subjects: tuple[str, ...]
    evidence: tuple[EvidenceRecord, ...] = ()
    scope_consents: tuple[ScopeConsent, ...] = ()
    submission_ids: tuple[str, ...] = ()

    def __post_init__(self):
        require(version(self.revision) and type(self.task) is EvidenceTask
                and version(self.evidence_version) and version(self.plan_version)
                and type(self.planning_input) is ContentDraftInput and type(self.plan_bound) is bool
                and type(self.point_subjects) is tuple and 1 <= len(self.point_subjects) <= cp.MAX_CONTENT_POINTS_PER_OPERATION
                and all(text(s, cp.MAX_CONTENT_POINT_SUBJECT_CHARS) for s in self.point_subjects)
                and {r.point_index for r in self.task.requirements} == set(range(len(self.point_subjects)))
                and type(self.evidence) is tuple and len(self.evidence) <= MAX_EVIDENCE
                and all(type(e) is EvidenceRecord and e.customer_id == self.task.customer_id
                        and e.evidence_version <= self.evidence_version for e in self.evidence)
                and len({e.supplement.evidence_id for e in self.evidence}) == len(self.evidence)
                and type(self.scope_consents) is tuple and len(self.scope_consents) <= 100
                and all(type(c) is ScopeConsent and c.context.customer_id == self.task.customer_id for c in self.scope_consents)
                and type(self.submission_ids) is tuple and len(self.submission_ids) <= 100
                and all(bounded_id(s) for s in self.submission_ids)
                and len(set(self.submission_ids)) == len(self.submission_ids))
        previous = {}
        for record in self.evidence:
            s = record.supplement
            require(record.submission_id in self.submission_ids)
            if s.supersedes is not None:
                old = previous.get(s.supersedes)
                require(old is not None and old.requirement_ids == s.requirement_ids
                        and s.supersedes not in {e.supplement.supersedes for e in self.evidence
                                                if e.supplement.evidence_id in previous})
            previous[s.evidence_id] = s

    @property
    def active_evidence(self) -> tuple[EvidenceRecord, ...]:
        replaced = {e.supplement.supersedes for e in self.evidence}
        return tuple(e for e in self.evidence if e.supplement.evidence_id not in replaced)


def digest_valid(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def snapshot_digest(snapshot: IntakeSnapshot) -> str:
    def encode(value):
        if isinstance(value, datetime):
            return value.astimezone(UTC).isoformat()
        if isinstance(value, Enum):
            return value.value
        raise TypeError("EVIDENCE_INTAKE_INVALID")
    payload = asdict(snapshot)
    def legacy_defaults(item):
        if isinstance(item, dict):
            if item.get('propose_interpretations') is False:
                item.pop('propose_interpretations')
            for key in ('article_type', 'search_intent', 'reader_problem', 'section_briefs', 'facts', 'interpretations'):
                if key in item and item[key] in (None, ()):
                    item.pop(key)
            for value in item.values():
                legacy_defaults(value)
        elif isinstance(item, (tuple, list)):
            for value in item:
                legacy_defaults(value)
    legacy_defaults(payload)
    # Preserve pre-E-input V1 journal digests, including append/CAS checks.
    if payload["planning_input"].get("customer_evidence") is None:
        payload["planning_input"].pop("customer_evidence", None)
    if payload["planning_input"].get("writing_brief") is None:
        payload["planning_input"].pop("writing_brief", None)
    raw = json.dumps(payload, default=encode, ensure_ascii=False, allow_nan=False,
                     sort_keys=True, separators=(",", ":")).encode("utf-8")
    require(len(raw) <= MAX_SNAPSHOT_BYTES)
    return hashlib.sha256(raw).hexdigest()


def native_plan_error(value: ContentDraftInput, subjects: tuple[str, ...]) -> str | None:
    """Structural admission only; calls existing Planning validators, no inference."""
    try:
        error = stable_content_draft_input_error(value)
        if error:
            return error
        operations = value.change_plan_report.operations
        if (len(operations) != 1 or operations[0].operation_type not in {
                cp.ChangeOperationType.EXPAND_SECTION, cp.ChangeOperationType.CREATE_NEW_RESOURCE}
                or tuple(p.subject for p in operations[0].content_points) != subjects
                or any(p.intent is not cp.ContentPointIntent.EXPLAIN for p in operations[0].content_points)):
            return "EXPLAIN_EXPANSION_PROFILE_REQUIRED"
        op = operations[0]
        prompt = cp.build_change_plan_prompt(cp.ChangePlanInput(value.site_content, value.opportunity_report))
        catalog = prompt.catalog
        points = []
        for point in op.content_points:
            origins = tuple((ref, cp.page_evidence_text(catalog.page_by_id()[ref])) for ref in op.page_refs)
            origins += tuple((ref, (catalog.source_by_id()[ref].content,)) for ref in op.source_refs)
            origin = next((ref for ref, material in origins if cp.phrase_is_grounded(point.subject, material)), None)
            if origin is None:
                return "NATIVE_PLANNING_INVALID"
            points.append(cp.ContentPointSpecification(point.intent, point.subject, origin))
        common = (op.opportunity_ref, op.source_action_code, op.operation_type,
            op.page_refs, op.source_refs, cp.SectionLocatorSpecification(op.locator.locator_kind,
            op.locator.page_ref, op.locator.observed_heading))
        if op.operation_type is cp.ChangeOperationType.CREATE_NEW_RESOURCE:
            resource = op.new_resource_spec
            if resource is None or resource.comparison_table_spec is not None:
                return "NATIVE_PLANNING_INVALID"
            spec = cp.CreateNewResourceSpecification(*common, cp.NewResourceSpecification(
                resource.resource_purpose, resource.proposed_title, resource.outline_headings,
                tuple(points), resource.suggested_source_page_refs, None, resource.section_briefs))
        else:
            spec = cp.ExpandSectionSpecification(*common, tuple(points))
        rebuilt, error = cp.validate_and_finalize_specification(1, spec, catalog)
        return None if error is None and rebuilt == op else "NATIVE_PLANNING_INVALID"
    except (AttributeError, TypeError, ValueError, KeyError, StopIteration):
        return "NATIVE_PLANNING_INVALID"


def rebind_preserves_task(current: IntakeSnapshot, value: ContentDraftInput) -> bool:
    """Supplementing cannot replace the crawl/research/audit or move the task.

    Point deletion is permitted only via the existing whole-point consent
    transition. Its subjects are validated separately by native_plan_error.
    """
    try:
        old = current.planning_input
        left, right = old.change_plan_report.operations[0], value.change_plan_report.operations[0]
        return (value.site_content == old.site_content
                and value.opportunity_report == old.opportunity_report
                and value.target_language == old.target_language
                and all(getattr(left, field) == getattr(right, field) for field in (
                    "operation_type", "opportunity_ref", "source_action_code", "page_refs",
                    "source_refs", "audit_refs", "locator"))
                and (left.new_resource_spec is None and right.new_resource_spec is None
                     or left.new_resource_spec is not None and right.new_resource_spec is not None
                     and all(getattr(left.new_resource_spec, field) == getattr(right.new_resource_spec, field)
                             for field in ("resource_purpose", "proposed_title",
                                           "suggested_source_page_refs", "comparison_table_spec"))
                     and (right.new_resource_spec.outline_headings == left.new_resource_spec.outline_headings
                          and right.new_resource_spec.section_briefs == left.new_resource_spec.section_briefs
                          if not current.task.section_briefs else
                          right.new_resource_spec.section_briefs == CustomerPlanningContext(current).section_briefs())))
    except (AttributeError, IndexError, TypeError):
        return False


@dataclass(frozen=True, slots=True)
class CustomerPlanningContext:
    """Exact intake projection consumed by the EXISTING native planner.

    A customer locator is an attributed string, not a verified PDF page or
    web reference. No E entry can be used as a P/S grounding origin. Inputs
    exceeding the native planner's existing envelope fail without truncation.
    """
    snapshot: IntakeSnapshot

    def __post_init__(self):
        require(type(self.snapshot) is IntakeSnapshot)
        snapshot_digest(self.snapshot)

    def validate_input(self, packet: SiteContentPacket, opportunities: ContentOpportunityReport, task_id: str | None):
        original = self.snapshot.planning_input
        require(packet == original.site_content and opportunities == original.opportunity_report
                and task_id == self.snapshot.task.task_id)

    def section_briefs(self) -> tuple[cp.ArticleSectionBrief, ...]:
        return tuple(replace(b, supporting_evidence=tuple(e.supplement.evidence_id
            for e in self.snapshot.active_evidence
            if set(e.supplement.requirement_ids) & set(b.requirement_ids)))
            for b in self.snapshot.task.section_briefs)

    def payload(self) -> dict[str, object]:
        s = self.snapshot
        active = {e.supplement.evidence_id for e in s.active_evidence}
        records = []
        for record in s.evidence:
            item = asdict(record)
            item["recorded_at"] = record.recorded_at.astimezone(UTC).isoformat()
            item["supplement"]["method"] = record.supplement.method.value
            item["customer_ref"] = "customer:" + record.supplement.evidence_id
            item["active"] = record.supplement.evidence_id in active
            records.append(item)
        return {
            "mode": "ATTRIBUTED_CUSTOMER_PLANNING_CONTEXT",
            "snapshot_sha256": snapshot_digest(s),
            "project_id": s.task.project_id, "customer_id": s.task.customer_id,
            "task_id": s.task.task_id, "task_version": s.task.task_version,
            "plan_version": s.plan_version, "evidence_version": s.evidence_version,
            "revision": s.revision, "goal": s.task.goal,
            "article_type": s.task.article_type, "search_intent": s.task.search_intent,
            "reader_problem": s.task.reader_problem,
            "section_briefs": [asdict(b) for b in self.section_briefs()],
            "required_point_subjects": s.point_subjects,
            "required_intent": "EXPLAIN",
            "requirements": [asdict(r) for r in s.task.requirements],
            "records": records,
            "use_constraints": (
                "Customer declarations and documents are unverified attributed material, not observed website facts.",
                "Preserve the original goal, operation target, EXPLAIN depth and every retained fact obligation.",
                "Customer refs and declared locators are not page_refs, source_refs or grounding origins.",
                "Plan only; structural coverage does not establish semantic sufficiency or authorize Draft.",
            ),
        }


class IntakeChangePlanner(Protocol):
    async def run(self, site_content: SiteContentPacket, opportunity_report: ContentOpportunityReport, *, task_id: str,
                  customer_context: CustomerPlanningContext) -> cp.ChangePlanReport: ...


@dataclass(frozen=True, slots=True)
class ClaimEvidenceReview:
    """One explicit fact obligation; no generated commercial claims."""
    requirement: EvidenceRequirement
    point_subject: str
    materials: tuple[EvidenceRecord, ...]
    decision: RequirementDecision | None

    def __post_init__(self):
        require(type(self.requirement) is EvidenceRequirement and text(self.point_subject)
                and type(self.materials) is tuple and len(self.materials) <= MAX_EVIDENCE
                and all(type(e) is EvidenceRecord and self.requirement.requirement_id in e.supplement.requirement_ids
                        for e in self.materials)
                and (self.decision is None or type(self.decision) is RequirementDecision
                     and self.decision.requirement_id == self.requirement.requirement_id))

    @property
    def verdict(self) -> SupportVerdict:
        if not self.materials:
            return SupportVerdict.MISSING
        return SupportVerdict.UNREVIEWED if self.decision is None else self.decision.verdict


@dataclass(frozen=True, slots=True)
class PlanningReviewCandidate:
    """A bound native Plan plus per-claim review materials, never execution input."""
    snapshot: IntakeSnapshot
    check: IntakeCheck
    claims: tuple[ClaimEvidenceReview, ...]

    def __post_init__(self):
        require(type(self.snapshot) is IntakeSnapshot and self.snapshot.plan_bound
                and native_plan_error(self.snapshot.planning_input, self.snapshot.point_subjects) is None
                and type(self.check) is IntakeCheck
                and self.check.snapshot_sha256 == snapshot_digest(self.snapshot)
                and type(self.claims) is tuple
                and all(type(c) is ClaimEvidenceReview for c in self.claims)
                and tuple(c.requirement for c in self.claims) == self.snapshot.task.requirements)
        decisions = {} if self.check.assessment is None else {d.requirement_id: d for d in self.check.assessment.decisions}
        for claim in self.claims:
            require(claim.point_subject == self.snapshot.point_subjects[claim.requirement.point_index]
                    and claim.materials == tuple(e for e in self.snapshot.active_evidence
                        if claim.requirement.requirement_id in e.supplement.requirement_ids)
                    and claim.decision == decisions.get(claim.requirement.requirement_id))

    @property
    def return_to_intake(self) -> bool:
        return any(g.reason_code == 'ARTICLE_SCOPE_REQUIREMENT_MISSING' for g in self.check.gaps) or any(c.verdict in {SupportVerdict.MISSING, SupportVerdict.IRRELEVANT, SupportVerdict.CONFLICT}
                   for c in self.claims)

    @property
    def draft_authorized(self) -> bool:
        return False


class SupportVerdict(str, Enum):
    SUPPORTED = "SUPPORTED"
    MISSING = "MISSING"
    IRRELEVANT = "IRRELEVANT"
    CONFLICT = "CONFLICT"
    UNREVIEWED = "UNREVIEWED"


@dataclass(frozen=True, slots=True)
class EvidenceSpan:
    evidence_id: str
    start: int
    end: int
    quote: str

    def __post_init__(self):
        require(bounded_id(self.evidence_id) and type(self.start) is int and type(self.end) is int
                and 0 <= self.start < self.end <= MAX_TEXT and text(self.quote, MAX_TEXT))


@dataclass(frozen=True, slots=True)
class RequirementDecision:
    requirement_id: str
    verdict: SupportVerdict
    reason: str
    spans: tuple[EvidenceSpan, ...] = ()

    def __post_init__(self):
        require(bounded_id(self.requirement_id) and type(self.verdict) is SupportVerdict and text(self.reason)
                and type(self.spans) is tuple and len(self.spans) <= 20
                and all(type(s) is EvidenceSpan for s in self.spans)
                and len(set(self.spans)) == len(self.spans)
                and (self.verdict is not SupportVerdict.SUPPORTED or bool(self.spans)))


@dataclass(frozen=True, slots=True)
class ArticleScopeCoverage:
    """Trusted reviewer checks goal, Plan purpose/title/intents and obligations.

    Bound by SemanticAssessment.snapshot_sha256, never a customer declaration.
    Missing obligations reuse EvidenceRequirement; no lexical semantic detector.
    """
    aligned: bool
    reason: str
    missing_requirements: tuple[EvidenceRequirement, ...] = ()

    def __post_init__(self):
        require(type(self.aligned) is bool and text(self.reason)
                and type(self.missing_requirements) is tuple
                and len(self.missing_requirements) <= MAX_REQUIREMENTS
                and all(type(r) is EvidenceRequirement for r in self.missing_requirements)
                and len({r.requirement_id for r in self.missing_requirements}) == len(self.missing_requirements)
                and (not self.aligned or not self.missing_requirements))


@dataclass(frozen=True, slots=True)
class ReviewedInterpretation:
    text: str
    spans: tuple[EvidenceSpan, ...]
    limitation: str
    procurement_action: str
    proposal: InterpretationProposal | None = None

    def __post_init__(self):
        require(self.proposal is None or (type(self.proposal) is InterpretationProposal
                and self.proposal.limitation == self.limitation
                and self.proposal.procurement_action == self.procurement_action))
        require(text(self.text, MAX_INTERPRETATION_CHARS) and type(self.spans) is tuple and 1 <= len(self.spans) <= 20
                and all(type(s) is EvidenceSpan for s in self.spans) and len(set(self.spans)) == len(self.spans)
                and text(self.limitation, 150) and self.limitation in self.text
                and text(self.procurement_action, 150) and self.procurement_action in self.text)


@dataclass(frozen=True, slots=True)
class SemanticAssessment:
    snapshot_sha256: str
    reviewer_id: str
    reviewed_at: datetime
    decisions: tuple[RequirementDecision, ...]
    scope_coverage: ArticleScopeCoverage | None = None
    interpretations: tuple[ReviewedInterpretation, ...] = ()

    def __post_init__(self):
        require(digest_valid(self.snapshot_sha256) and bounded_id(self.reviewer_id) and aware_time(self.reviewed_at)
                and type(self.decisions) is tuple and 1 <= len(self.decisions) <= MAX_REQUIREMENTS
                and all(type(d) is RequirementDecision for d in self.decisions)
                and len({d.requirement_id for d in self.decisions}) == len(self.decisions)
                and (self.scope_coverage is None or type(self.scope_coverage) is ArticleScopeCoverage))
        require(type(self.interpretations) is tuple and len(self.interpretations) <= MAX_INTERPRETATIONS
                and all(type(i) is ReviewedInterpretation for i in self.interpretations)
                and len({i.text for i in self.interpretations}) == len(self.interpretations))


class EvidenceSemanticReviewer(Protocol):
    def assess(self, snapshot: IntakeSnapshot, *, now: datetime) -> SemanticAssessment:
        """Fresh trusted HUMAN semantic decision, never customer JSON or an LLM flag.

        Must assess all obligations, source authority/applicability, limitations,
        task depth, and conflicts across the entire active evidence and native
        P/S context. Authenticate current reviewer authority at this boundary.
        Explicitly assess whether the approved goal, Plan title/purpose/intents,
        all points and fact obligations cover the same article scope. Report
        missing obligations with actionable facts/uses in scope_coverage.
        Unavailable, expired or revoked decisions must raise. This is only
        evidence admission, not Draft permission. No production adapter exists.
        """
        ...


@dataclass(frozen=True, slots=True)
class EvidenceGap:
    requirement: EvidenceRequirement
    change_ref: str
    point_subject: str
    reason_code: str
    review_reason: str | None = None

    def __post_init__(self):
        require(type(self.requirement) is EvidenceRequirement and self.change_ref == "C1"
                and text(self.point_subject, cp.MAX_CONTENT_POINT_SUBJECT_CHARS)
                and self.reason_code in {"MISSING_CUSTOMER_EVIDENCE", "HUMAN_SEMANTIC_REVIEW_REQUIRED",
                                         "ARTICLE_SCOPE_REQUIREMENT_MISSING",
                                         *(v.value for v in SupportVerdict if v is not SupportVerdict.SUPPORTED)}
                and (self.review_reason is None or text(self.review_reason)))


class IntakeStatus(str, Enum):
    BLOCKED = "BLOCKED"
    CANDIDATE_FOR_REVIEW = "CANDIDATE_FOR_REVIEW"


@dataclass(frozen=True, slots=True)
class IntakeCheck:
    snapshot_sha256: str
    status: IntakeStatus
    gaps: tuple[EvidenceGap, ...]
    reason: str | None
    assessment: SemanticAssessment | None = None

    def __post_init__(self):
        require(digest_valid(self.snapshot_sha256) and type(self.status) is IntakeStatus
                and type(self.gaps) is tuple and len(self.gaps) <= MAX_REQUIREMENTS * 2
                and all(type(g) is EvidenceGap for g in self.gaps)
                and (self.reason is None or self.reason in {
                    "PLAN_REBIND_REQUIRED", "EVIDENCE_GAPS_REMAIN", "HUMAN_SEMANTIC_REVIEW_REQUIRED",
                    "NATIVE_PLANNING_INVALID", "EXPLAIN_EXPANSION_PROFILE_REQUIRED",
                    "ARTICLE_SCOPE_REVIEW_REQUIRED", "ARTICLE_SCOPE_MISMATCH",
                    *(v.value for v in cp.ChangePlanValidationCategory),
                })
                and (self.assessment is None or type(self.assessment) is SemanticAssessment))
        if self.status is IntakeStatus.CANDIDATE_FOR_REVIEW:
            require(not self.gaps and self.reason is None and self.assessment is not None
                    and self.assessment.snapshot_sha256 == self.snapshot_sha256
                    and all(d.verdict is SupportVerdict.SUPPORTED for d in self.assessment.decisions))

    @property
    def draft_authorized(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class CustomerEvidenceRequest:
    """Concrete request tied to the exact task, Plan and evidence revision.

    Empty gaps mean no customer supplement is requested; a staff rebind or
    review may still be required. No request field is an approval credential.
    """
    project_id: str
    customer_id: str
    task_id: str
    task_version: int
    plan_version: int
    evidence_version: int
    snapshot_revision: int
    snapshot_sha256: str
    goal: str
    gaps: tuple[EvidenceGap, ...]
    staff_action: str | None
    schema_version: int = 1

    def __post_init__(self):
        require(all(bounded_id(v) for v in (self.project_id, self.customer_id, self.task_id))
                and all(version(v) for v in (self.task_version, self.plan_version, self.evidence_version, self.snapshot_revision))
                and digest_valid(self.snapshot_sha256) and text(self.goal)
                and type(self.gaps) is tuple and len(self.gaps) <= MAX_REQUIREMENTS * 2
                and all(type(g) is EvidenceGap for g in self.gaps)
                and type(self.schema_version) is int and self.schema_version == 1
                and (self.staff_action is None or text(self.staff_action)))


def validate_assessment(snapshot: IntakeSnapshot, assessment: SemanticAssessment, now: datetime) -> None:
    """Binding/coverage checks only; the trusted reviewer owns semantic judgment."""
    from datetime import timedelta
    require(type(assessment) is SemanticAssessment and aware_time(now)
            and assessment.snapshot_sha256 == snapshot_digest(snapshot)
            and now - timedelta(minutes=5) <= assessment.reviewed_at <= now
            and tuple(d.requirement_id for d in assessment.decisions)
            == tuple(r.requirement_id for r in snapshot.task.requirements))
    evidence = {e.supplement.evidence_id: e.supplement for e in snapshot.active_evidence}
    if assessment.scope_coverage is not None:
        require(all(r.point_index < len(snapshot.point_subjects)
                    for r in assessment.scope_coverage.missing_requirements))
    for decision in assessment.decisions:
        for span in decision.spans:
            material = evidence.get(span.evidence_id)
            require(material is not None and decision.requirement_id in material.requirement_ids
                    and span.end <= len(material.content) and material.content[span.start:span.end] == span.quote)
    approved = {s for d in assessment.decisions if d.verdict is SupportVerdict.SUPPORTED for s in d.spans}
    require(all(set(i.spans) <= approved for i in assessment.interpretations))


def article_scope_error(assessment: SemanticAssessment | None) -> str | None:
    if assessment is None or assessment.scope_coverage is None:
        return "ARTICLE_SCOPE_REVIEW_REQUIRED"
    return None if assessment.scope_coverage.aligned else "ARTICLE_SCOPE_MISMATCH"


class EvidenceIntakeStore(Protocol):
    def create_snapshot(self, snapshot: IntakeSnapshot) -> None: ...
    def latest(self, project_id: str, task_id: str) -> IntakeSnapshot: ...
    def append(self, expected_sha256: str, snapshot: IntakeSnapshot) -> None:
        """Atomically compare current snapshot then append; never overwrite history."""
        ...
    def append_check(self, project_id: str, task_id: str, check: IntakeCheck) -> None:
        """Persist against current digest only; fail on concurrent change."""
        ...
