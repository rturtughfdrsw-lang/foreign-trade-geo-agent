"""Read an untrusted receipt, authenticate it, and verify current independent registration."""
from datetime import datetime, timedelta
import hashlib
import secrets

from foreign_trade_geo_agent.core.evidence_review_registry import (
    CurrentEvidenceReviewRegistry, EvidenceReviewReceipt, EvidenceReviewReceiptReader,
    ReviewRegistrationStatus, VerifiedReviewRegistration,
)
from foreign_trade_geo_agent.core.evidence_sufficiency import (
    AuthenticatedReview, EvidenceReviewAuthenticator, ExcerptReviewTarget, aware_time, bounded_id,
)
from .evidence_review import AuthenticatedEvidenceReviewLoader, freeze_excerpt_target, load_excerpt_target


class RegisteredEvidenceReviewLoader:
    """No signer or registry write path. Missing production roots always refuse."""
    def __init__(self, *, receipt_reader: EvidenceReviewReceiptReader | None = None,
                 authenticator: EvidenceReviewAuthenticator | None = None,
                 registry: CurrentEvidenceReviewRegistry | None = None) -> None:
        self._reader = receipt_reader
        self._authenticator = authenticator
        self._registry = registry

    def load_persisted_review(self, target: ExcerptReviewTarget, review_id: str,
                              now: datetime) -> AuthenticatedReview:
        try:
            if (self._reader is None or self._authenticator is None or self._registry is None
                or not bounded_id(review_id) or not aware_time(now)):
                raise ValueError()
            receipt = self._reader.get_receipt(review_id)
            if type(receipt) is not EvidenceReviewReceipt or receipt.review_id != review_id:
                raise ValueError()
            EvidenceReviewReceipt(receipt.review_id, receipt.frozen_target, receipt.record, receipt.proof)
            loaded = load_excerpt_target(receipt.frozen_target)
            if loaded != target or freeze_excerpt_target(target) != receipt.frozen_target:
                raise ValueError()
            review = AuthenticatedEvidenceReviewLoader(self._authenticator).load_review(
                target, receipt.record, receipt.proof, now)
            if review.record_id != review_id:
                raise ValueError()
            challenge = secrets.token_bytes(32)
            registration = self._registry.lookup_current(review_id, challenge)
            if (type(registration) is not VerifiedReviewRegistration
                or type(registration.challenge) is not bytes or registration.challenge != challenge
                or not aware_time(registration.checked_at)
                or abs(now-registration.checked_at) > timedelta(seconds=5)
                or type(registration.revision) is not int or not 1 <= registration.revision <= 1_000_000_000
                or type(registration.synthetic) is not bool or registration.synthetic != review.principal.synthetic
                or registration.status is not ReviewRegistrationStatus.ACTIVE
                or registration.revoked_at is not None
                or not aware_time(registration.registered_at) or not aware_time(registration.expires_at)
                or not registration.registered_at <= now < registration.expires_at
                or (registration.review_id, registration.reviewer_id, registration.project_id,
                    registration.task_id, registration.task_version, registration.plan_version,
                    registration.evidence_version, registration.purpose) != (
                        review_id, review.principal.reviewer_id, review.project_id, review.task_id,
                        review.task_version, review.plan_version, review.evidence_version, review.purpose)
                or any(type(v) is not int for v in (registration.task_version,
                    registration.plan_version, registration.evidence_version))
                or registration.frozen_target_sha256 != review.actual_target_sha256
                or registration.record_sha256 != hashlib.sha256(receipt.record).hexdigest()
                or registration.proof_sha256 != hashlib.sha256(receipt.proof).hexdigest()):
                raise ValueError()
            return review
        except Exception:
            raise ValueError("CURRENT_TRUSTED_REVIEW_REQUIRED") from None
