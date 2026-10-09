"""Explicit offline preflight. No writer, runtime route, persistence or approval UI."""
from datetime import UTC, datetime

from foreign_trade_geo_agent.core.evidence_sufficiency import (
    AuthenticatedReview, EvidenceGateResult, EvidenceGateStatus, EvidenceReviewLoader,
    ExcerptReviewTarget, excerpt_target_error,
)


class EvidenceSufficiencyPreflight:
    def __init__(self, *, review_loader: EvidenceReviewLoader | None = None,
                 allow_synthetic: bool = False) -> None:
        if type(allow_synthetic) is not bool:
            raise TypeError("Offline synthetic mode must be explicit.")
        self._review_loader = review_loader
        self._allow_synthetic = allow_synthetic

    def check(self, target: ExcerptReviewTarget, record: bytes | None = None,
              proof: bytes | None = None, *, now: datetime | None = None) -> EvidenceGateResult:
        try:
            error = excerpt_target_error(target)
            if error is not None:
                return EvidenceGateResult(EvidenceGateStatus.REJECTED, error)
            # Never return a cached verified object; reauthenticate on every check.
            if self._review_loader is None:
                return EvidenceGateResult(EvidenceGateStatus.REJECTED, "TRUSTED_REVIEW_REQUIRED")
            review = self._review_loader.load_review(target, record, proof,
                datetime.now(UTC) if now is None else now)
            if type(review) is not AuthenticatedReview:
                return EvidenceGateResult(EvidenceGateStatus.REJECTED, "TRUSTED_REVIEW_REQUIRED")
            digest = review.actual_target_sha256
            if (review.principal.synthetic and not self._allow_synthetic
                or (review.project_id, review.task_id, review.task_version, review.plan_version,
                    review.evidence_version, review.purpose) != (
                        target.project_id, target.task_id, target.task_version, target.plan_version,
                        target.evidence_version, target.purpose)
                or review.frozen_target_sha256 != digest
                or review.draft_input_sha256 != review.actual_draft_input_sha256
                or review.obligation_ids != tuple(o.obligation_id for o in target.obligations)):
                return EvidenceGateResult(EvidenceGateStatus.REJECTED, "REVIEW_BINDING_OR_SCOPE_INVALID")
            status = (EvidenceGateStatus.SYNTHETIC_GREEN if review.principal.synthetic
                      else EvidenceGateStatus.OFFLINE_REVIEW_GREEN)
            return EvidenceGateResult(status, None, review.record_id, review.principal.reviewer_id, digest)
        except Exception:
            return EvidenceGateResult(EvidenceGateStatus.REJECTED, "TRUSTED_REVIEW_REQUIRED")
