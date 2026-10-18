"""Bounded excerpt review profiles; offline default never grants Draft/CMS."""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import re
from typing import Protocol

from . import change_plan as cp
from .content_draft import ContentDraftInput, MAX_CLAIM_CHARS
from .first_party_planning import FirstPartyPlanningScope, MAX_FIRST_PARTY_EXCERPTS

OFFLINE_EXCERPT_PURPOSE = "OFFLINE_P_ONLY_EXCERPT"
EXCERPT_OUTPUT_CONSTRAINTS = (
    "All required complete statements verbatim and in source order; grouping and attribution only.",
    "Always state the controlled fictional demonstration context.",
    "No free paraphrase, engineering certification, SEO efficacy, commercial placement, EXPLAIN or comparison.",
    "Offline review only; no Draft generation, provider calls or CMS permission.",
)
REQUIRED_REVIEW_DECISIONS = (
    "SOURCE_USE", "TASK_AND_DEPTH", "OFFLINE_PLACEMENT", "P_ONLY_CANDIDATE",
    "FROZEN_CONSUMPTION", "REVIEW_AUTHORITY", "VALIDITY_AND_STORAGE",
)

# Independent, versioned consumption purpose. Old offline receipts cannot be
# reinterpreted as execution permission, even with identical evidence.
P_ONLY_DRAFT_PURPOSE_V1 = "TEST_P_ONLY_VERBATIM_DRAFT_V1"
P_ONLY_DRAFT_CONSTRAINTS_V1 = (
    *EXCERPT_OUTPUT_CONSTRAINTS[:3],
    "Isolated TEST verbatim Draft only; no provider calls, commercial placement or CMS permission.",
)
P_ONLY_DRAFT_DECISIONS_V1 = (
    "SOURCE_USE", "TASK_AND_DEPTH", "TEST_DRAFT_CONSUMPTION", "P_ONLY_CANDIDATE",
    "FROZEN_CONSUMPTION", "REVIEW_AUTHORITY", "VALIDITY_AND_STORAGE",
)


@dataclass(frozen=True, slots=True)
class ExcerptObligation:
    obligation_id: str
    statement: str
    excerpt_indexes: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class ExcerptReviewTarget:
    project_id: str
    task_id: str
    task_version: int
    plan_version: int
    evidence_version: int
    question: str
    attribution: str
    context: str
    scope: FirstPartyPlanningScope
    draft_input: ContentDraftInput
    obligations: tuple[ExcerptObligation, ...]
    task_kind: str = "ATTRIBUTED_EXCERPT"
    purpose: str = OFFLINE_EXCERPT_PURPOSE
    output_constraints: tuple[str, ...] = EXCERPT_OUTPUT_CONSTRAINTS


@dataclass(frozen=True, slots=True)
class ReviewPrincipal:
    """Current identity/grants from an external trusted authority, never JSON."""
    reviewer_id: str
    project_id: str
    task_ids: tuple[str, ...]
    purposes: tuple[str, ...]
    valid_from: datetime
    valid_until: datetime
    synthetic: bool


class EvidenceReviewAuthenticator(Protocol):
    def authenticate(self, record: bytes, proof: bytes, now: datetime) -> ReviewPrincipal | None:
        """Authenticate EXACT bytes against protected identity/key/grant state.

        Must check signature, identity, key lifecycle and current revocation.
        No key/grant may be trusted from record/target/proof self declarations.
        Return None on unavailable trust state. The composition root is trusted.
        """
        ...


@dataclass(frozen=True, slots=True)
class AuthenticatedReview:
    principal: ReviewPrincipal
    record_id: str
    project_id: str
    task_id: str
    task_version: int
    plan_version: int
    evidence_version: int
    purpose: str
    frozen_target_sha256: str
    draft_input_sha256: str
    obligation_ids: tuple[str, ...]
    actual_target_sha256: str
    actual_draft_input_sha256: str


class EvidenceReviewLoader(Protocol):
    def load_review(self, target: ExcerptReviewTarget, record: bytes, proof: bytes,
                    now: datetime) -> AuthenticatedReview:
        """Authenticate and bind current frozen bytes; raise on any trust failure."""
        ...


class EvidenceGateStatus(str, Enum):
    REJECTED = "REJECTED"
    SYNTHETIC_GREEN = "SYNTHETIC_GREEN"
    OFFLINE_REVIEW_GREEN = "OFFLINE_REVIEW_GREEN"


@dataclass(frozen=True, slots=True)
class EvidenceGateResult:
    status: EvidenceGateStatus
    reason: str | None
    review_id: str | None = None
    reviewer_id: str | None = None
    frozen_target_sha256: str | None = None


def bounded_id(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", value) is not None


def aware_time(value: object) -> bool:
    return type(value) is datetime and value.tzinfo is not None and value.utcoffset() is not None


def excerpt_target_error(target: ExcerptReviewTarget, *, draft_consumption: bool = False) -> str | None:
    """Reuse native Planning invariants and check full ordered obligation coverage."""
    try:
        if type(draft_consumption) is not bool:
            return "EXCERPT_TARGET_INVALID"
        purpose = P_ONLY_DRAFT_PURPOSE_V1 if draft_consumption else OFFLINE_EXCERPT_PURPOSE
        constraints = P_ONLY_DRAFT_CONSTRAINTS_V1 if draft_consumption else EXCERPT_OUTPUT_CONSTRAINTS
        if type(target) is not ExcerptReviewTarget or (
            not all(bounded_id(v) for v in (target.project_id, target.task_id))
            or any(type(v) is not int or not 1 <= v <= 1_000_000
                   for v in (target.task_version, target.plan_version, target.evidence_version))
            or target.task_kind != "ATTRIBUTED_EXCERPT" or target.purpose != purpose
            or target.output_constraints != constraints
            or any(type(v) is not str or not v.strip() or len(v) > 1000
                   for v in (target.question, target.attribution, target.context))
            or type(target.scope) is not FirstPartyPlanningScope
            or type(target.draft_input) is not ContentDraftInput
            or type(target.obligations) is not tuple
            or not 1 <= len(target.obligations) <= MAX_FIRST_PARTY_EXCERPTS
        ):
            return "EXCERPT_TARGET_INVALID"
        scope, value = target.scope, target.draft_input
        # Reconstruct to recheck exact source text/heading/spans, including reloads.
        FirstPartyPlanningScope(scope.task_id, value.site_content, scope.page_ref,
                                scope.heading, scope.excerpts, scope.task_kind)
        if not scope.matches_task(target.task_id) or not scope.matches_packet(value.site_content):
            return "EXCERPT_TARGET_BINDING"
        used, ids = [], set()
        for item in target.obligations:
            if (type(item) is not ExcerptObligation or not bounded_id(item.obligation_id)
                or item.obligation_id in ids or type(item.statement) is not str
                or not 1 <= len(item.statement) <= MAX_CLAIM_CHARS
                or type(item.excerpt_indexes) is not tuple or not item.excerpt_indexes
                or any(type(i) is not int or not 0 <= i < len(scope.excerpts) for i in item.excerpt_indexes)):
                return "OBLIGATION_COVERAGE_INVALID"
            ids.add(item.obligation_id)
            parts = tuple(scope.excerpts[i] for i in item.excerpt_indexes)
            if ("".join(e.quote for e in parts) != item.statement
                or any((a.field, a.structured_index, a.end) != (b.field, b.structured_index, b.start)
                       for a, b in zip(parts, parts[1:]))):
                return "OBLIGATION_COVERAGE_INVALID"
            used.extend(item.excerpt_indexes)
        if used != list(range(len(scope.excerpts))):
            return "OBLIGATION_COVERAGE_INVALID"
        # Ensure source order even across separate obligations/structured fields.
        coordinates = tuple((e.structured_index if e.structured_index is not None else -1, e.start, e.end)
                            for e in scope.excerpts)
        if any(a[0] > b[0] or a[0] == b[0] and a[2] > b[1] for a, b in zip(coordinates, coordinates[1:])):
            return "OBLIGATION_COVERAGE_INVALID"
        change_input = cp.ChangePlanInput(value.site_content, value.opportunity_report, scope, target.task_id)
        if cp.validate_change_plan_input(change_input) is not None:
            return "NATIVE_PLANNING_INVALID"
        report = value.change_plan_report
        if (report.status is not cp.ChangePlanStatus.SUCCESS or len(report.operations) != 1
            or report.limitations != cp.CHANGE_PLAN_LIMITATIONS or report.error is not None
            or report.requires_human_review is not True
            or value.opportunity_report.source_materials or value.opportunity_report.audit_evidence):
            return "NATIVE_PLANNING_INVALID"
        operation = report.operations[0]
        if operation.operation_type is not cp.ChangeOperationType.EXPAND_SECTION:
            return "P_ONLY_OPERATION_INVALID"
        prompt = cp.build_change_plan_prompt(change_input)
        spec = cp.ExpandSectionSpecification(
            operation.opportunity_ref, operation.source_action_code, operation.operation_type,
            operation.page_refs, operation.source_refs,
            cp.SectionLocatorSpecification(operation.locator.locator_kind, operation.locator.page_ref,
                                          operation.locator.observed_heading),
            tuple(cp.ContentPointSpecification(p.intent, p.subject, scope.page_ref) for p in operation.content_points),
        )
        finalized, error = cp.validate_and_finalize_specification(
            1, spec, prompt.catalog, first_party_scope=scope, task_id=target.task_id)
        if error is not None or finalized != operation:
            return "NATIVE_PLANNING_INVALID"
        return None
    except (AttributeError, TypeError, ValueError, IndexError, KeyError):
        return "EXCERPT_TARGET_INVALID"
