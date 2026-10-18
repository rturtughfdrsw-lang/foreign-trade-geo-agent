"""Single-project review receipts and externally verified current-state ports.

Receipts are untrusted cache data. No signer/bootstrap/approval authority here.
"""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Protocol

from .evidence_sufficiency import AuthenticatedReview, ExcerptReviewTarget, bounded_id


@dataclass(frozen=True, slots=True)
class EvidenceReviewReceipt:
    review_id: str
    frozen_target: bytes
    record: bytes
    proof: bytes

    def __post_init__(self) -> None:
        if not bounded_id(self.review_id) or any(
            type(value) is not bytes or not 0 < len(value) <= limit
            for value, limit in ((self.frozen_target, 128*1024), (self.record, 16*1024), (self.proof, 4096))
        ):
            raise ValueError("Evidence review receipt is invalid.")


class ReviewRegistrationStatus(str, Enum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"


@dataclass(frozen=True, slots=True)
class VerifiedReviewRegistration:
    """Authenticated fresh state from protected service, NEVER local receipt DB."""
    review_id: str
    reviewer_id: str
    project_id: str
    task_id: str
    task_version: int
    plan_version: int
    evidence_version: int
    purpose: str
    frozen_target_sha256: str
    record_sha256: str
    proof_sha256: str
    revision: int
    registered_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    status: ReviewRegistrationStatus
    challenge: bytes
    checked_at: datetime
    synthetic: bool


class EvidenceReviewReceiptReader(Protocol):
    def get_receipt(self, review_id: str) -> EvidenceReviewReceipt | None:
        """Read bounded opaque data; no authorization or schema migration."""
        ...


class CurrentEvidenceReviewRegistry(Protocol):
    def lookup_current(self, review_id: str, challenge: bytes) -> VerifiedReviewRegistration | None:
        """Read authenticated CURRENT state from an independent protected root.

        Implementation must authenticate transport/response and service identity,
        reject cached/unauthenticated responses, bind challenge and own UTC time,
        and consult current revocation state. A nonce echo alone is not proof.
        Root must prevent ID reuse, revival and revision rollback. Never read
        grants or ACTIVE flags from the caller's package/receipt database.
        """
        ...


class PersistedEvidenceReviewLoader(Protocol):
    def load_persisted_review(self, target: ExcerptReviewTarget, review_id: str,
                              now: datetime) -> AuthenticatedReview:
        """Reauthenticate bytes and CURRENT registration; fail on unavailable root."""
        ...
