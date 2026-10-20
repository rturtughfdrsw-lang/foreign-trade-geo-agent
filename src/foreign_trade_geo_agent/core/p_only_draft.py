"""Opt-in V1 TEST excerpt consumption; no authorization from JSON or Gate flags."""
from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Protocol

from . import content_draft as cd
from .change_plan import ContentPointIntent
from .evidence_sufficiency import (
    AuthenticatedReview, ExcerptReviewTarget, P_ONLY_DRAFT_PURPOSE_V1,
    bounded_id, excerpt_target_error,
)


@dataclass(frozen=True, slots=True)
class POnlyDraftRequestV1:
    """Frozen bytes + receipt ID only. Neither is itself permission to execute."""
    frozen_target: bytes
    review_id: str
    schema_version: int = 1

    def __post_init__(self):
        if (type(self.schema_version) is not int or self.schema_version != 1
            or type(self.frozen_target) is not bytes or not 0 < len(self.frozen_target) <= 128 * 1024
            or not bounded_id(self.review_id)):
            raise ValueError("P_ONLY_DRAFT_REQUEST_INVALID")


@dataclass(frozen=True, slots=True)
class FrozenPOnlyDraft:
    request: POnlyDraftRequestV1
    target: ExcerptReviewTarget
    frozen_sha256: str
    draft_input_sha256: str


class POnlyDraftConsumer(Protocol):
    def prepare(self, request: POnlyDraftRequestV1) -> FrozenPOnlyDraft: ...

    def revalidate(self, execution: FrozenPOnlyDraft) -> AuthenticatedReview:
        """Recheck bytes, fresh identity/key/grants/registration/expiry/revocation."""
        ...


@dataclass(frozen=True, slots=True)
class POnlyDraftMaterial:
    change_ref: str
    page_ref: str
    statements: tuple[str, ...]
    context: str
    attribution: str


@dataclass(frozen=True, slots=True)
class POnlyDraftGeneration:
    specification: cd.ContentDraftSpecification
    context: str
    attribution: str


class POnlyDraftGenerator(Protocol):
    def generate(self, material: POnlyDraftMaterial) -> POnlyDraftGeneration: ...


@dataclass(frozen=True, slots=True)
class ExcerptCoverage:
    obligation_id: str
    claim_id: str
    page_ref: str
    source_url: str
    # (scope index, field, structured index, start, end, exact quote)
    spans: tuple[tuple[int, str, int | None, int, int, str], ...]


@dataclass(frozen=True, slots=True)
class POnlyDraftCoverageProofV1:
    schema_version: int
    purpose: str
    project_id: str
    task_id: str
    versions: tuple[int, int, int]
    review_id: str
    reviewer_id: str
    frozen_target_sha256: str
    draft_input_sha256: str
    output_sha256: str
    coverage: tuple[ExcerptCoverage, ...]


@dataclass(frozen=True, slots=True)
class POnlyDraftResultV1:
    report: cd.ContentDraftReport
    body: str | None
    coverage_proof: POnlyDraftCoverageProofV1 | None
    reason: str | None
    environment: str = "TEST"


def p_only_draft_target_error(target: ExcerptReviewTarget) -> str | None:
    error = excerpt_target_error(target, draft_consumption=True)
    if error is not None:
        return error
    # V1 is deliberately the six-obligation / seven-span profile. No inferred
    # summary, explanation, comparison or partial task may enter this path.
    if (tuple(o.obligation_id for o in target.obligations) != tuple(f"O{i}" for i in range(1, 7))
        or len(target.scope.excerpts) != 7
        or tuple(o.excerpt_indexes for o in target.obligations) != ((0, 1), (2,), (3,), (4,), (5,), (6,))
        or any(p.intent is not ContentPointIntent.DESCRIBE
               for p in target.draft_input.change_plan_report.operations[0].content_points)):
        return "P_ONLY_VERBATIM_PROFILE_REQUIRED"
    return cd.stable_content_draft_input_error(target.draft_input,
        first_party_scope=target.scope, task_id=target.task_id)


def draft_review_binding_error(execution: FrozenPOnlyDraft, review: AuthenticatedReview) -> str | None:
    t = execution.target
    if (type(review) is not AuthenticatedReview or review.principal.synthetic is not True
        or review.record_id != execution.request.review_id
        or (review.project_id, review.task_id, review.task_version, review.plan_version,
            review.evidence_version, review.purpose) != (
                t.project_id, t.task_id, t.task_version, t.plan_version, t.evidence_version, P_ONLY_DRAFT_PURPOSE_V1)
        or review.frozen_target_sha256 != execution.frozen_sha256
        or review.actual_target_sha256 != execution.frozen_sha256
        or review.draft_input_sha256 != execution.draft_input_sha256
        or review.actual_draft_input_sha256 != execution.draft_input_sha256
        or review.obligation_ids != tuple(o.obligation_id for o in t.obligations)):
        return "DRAFT_AUTHORIZATION_REQUIRED"
    return None


def material_for(target: ExcerptReviewTarget) -> POnlyDraftMaterial:
    return POnlyDraftMaterial(target.draft_input.change_plan_report.operations[0].change_id,
        target.scope.page_ref, tuple(o.statement for o in target.obligations), target.context, target.attribution)


def specification_coverage_error(target: ExcerptReviewTarget, output: POnlyDraftGeneration) -> str | None:
    """Raw text is checked before the generic finalizer can normalize it."""
    if type(output) is not POnlyDraftGeneration:
        return "VERBATIM_COVERAGE_INVALID"
    m = material_for(target)
    claims = tuple(cd.DraftClaimSpecification(s, cd.DraftClaimType.OBSERVED_PRODUCT_FACT,
        (m.page_ref,), ()) for s in m.statements)
    expected = cd.ContentDraftSpecification(m.change_ref, cd.ContentDraftType.SECTION_DRAFT,
        blocks=tuple(cd.ParagraphSpecification(cd.DraftBlockKind.PARAGRAPH, claims[i:i+4])
                     for i in range(0, len(claims), 4)))
    if output != POnlyDraftGeneration(expected, m.context, m.attribution):
        return "VERBATIM_COVERAGE_INVALID"
    return None


def render_body(target: ExcerptReviewTarget, draft: cd.DraftItem) -> str:
    return "\n".join((target.context, target.attribution,
        *(c.text for b in draft.blocks for c in b.claims)))


def output_digest(report: cd.ContentDraftReport, body: str) -> str:
    # Bind ALL final metadata and text, not a provider's self-reported digest.
    raw = json.dumps({"report": asdict(report), "body": body}, ensure_ascii=False,
        sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def final_coverage_error(target: ExcerptReviewTarget, report: cd.ContentDraftReport, body: str) -> str | None:
    if (p_only_draft_target_error(target) is not None
        or type(report) is not cd.ContentDraftReport or report.status is not cd.ContentDraftStatus.SUCCESS
        or len(report.drafts) != 1 or report.limitations != cd.CONTENT_DRAFT_LIMITATIONS
        or report.error is not None or report.requires_human_review is not True):
        return "VERBATIM_COVERAGE_INVALID"
    draft, operation = report.drafts[0], target.draft_input.change_plan_report.operations[0]
    if (type(draft) is not cd.DraftItem or draft.draft_id != "D1"
        or draft.change_ref != operation.change_id or draft.opportunity_ref != operation.opportunity_ref
        or draft.draft_type is not cd.ContentDraftType.SECTION_DRAFT or draft.target_kind != operation.target_kind
        or draft.target_page_ref != target.scope.page_ref or draft.locator != operation.locator
        or draft.heading is not None or draft.ordered_headings != ()
        or draft.page_refs != (target.scope.page_ref,) or draft.source_refs != ()
        or draft.requires_human_review is not True
        or len(draft.blocks) != 2
        or any(type(b) is not cd.ParagraphBlock or b.kind is not cd.DraftBlockKind.PARAGRAPH for b in draft.blocks)
        or tuple(len(b.claims) for b in draft.blocks) != (4, 2)):
        return "VERBATIM_COVERAGE_INVALID"
    claims = tuple(c for b in draft.blocks for c in b.claims)
    for n, (claim, obligation) in enumerate(zip(claims, target.obligations), 1):
        if (type(claim) is not cd.DraftClaim or claim.claim_id != f"CL{n}"
            or claim.text != obligation.statement or claim.claim_type is not cd.DraftClaimType.OBSERVED_PRODUCT_FACT
            or claim.support_kind is not cd.DraftClaimSupportKind.FIRST_PARTY_OBSERVED
            or claim.page_refs != (target.scope.page_ref,) or claim.source_refs != ()):
            return "VERBATIM_COVERAGE_INVALID"
    if body != render_body(target, draft):
        return "VERBATIM_COVERAGE_INVALID"
    return None


def coverage_proof(execution: FrozenPOnlyDraft, review: AuthenticatedReview,
                   report: cd.ContentDraftReport, body: str) -> POnlyDraftCoverageProofV1:
    t = execution.target
    if final_coverage_error(t, report, body) is not None or draft_review_binding_error(execution, review):
        raise ValueError("VERBATIM_COVERAGE_INVALID")
    page = next(p for p in t.draft_input.site_content.pages if p.evidence_id == t.scope.page_ref)
    claims = tuple(c for b in report.drafts[0].blocks for c in b.claims)
    mapping = tuple(ExcerptCoverage(o.obligation_id, c.claim_id, t.scope.page_ref, page.final_url,
        tuple((i, e.field, e.structured_index, e.start, e.end, e.quote)
              for i in o.excerpt_indexes for e in (t.scope.excerpts[i],)))
        for o, c in zip(t.obligations, claims))
    return POnlyDraftCoverageProofV1(1, t.purpose, t.project_id, t.task_id,
        (t.task_version, t.plan_version, t.evidence_version), review.record_id, review.principal.reviewer_id,
        execution.frozen_sha256, execution.draft_input_sha256, output_digest(report, body), mapping)


def verify_coverage_proof(execution: FrozenPOnlyDraft, review: AuthenticatedReview,
                          report: cd.ContentDraftReport, body: str, proof: POnlyDraftCoverageProofV1) -> bool:
    """Recompute semantic coverage before digest/proof comparison; never digest-only."""
    try:
        return type(proof) is POnlyDraftCoverageProofV1 and proof == coverage_proof(execution, review, report, body)
    except (AttributeError, TypeError, ValueError, IndexError):
        return False
