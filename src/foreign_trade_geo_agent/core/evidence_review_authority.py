"""Host authority ports, extending existing review contracts without new codecs.

Implementations require independent protected storage and authenticated sessions.
In-memory fixtures cannot supply a production trust root.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from .evidence_review_registry import EvidenceReviewReceipt, VerifiedReviewRegistration
from .evidence_sufficiency import ReviewPrincipal


@dataclass(frozen=True, slots=True)
class CurrentReviewAuthority:
    principal: ReviewPrincipal
    review_key_fingerprint: str
    key_valid_from: datetime
    key_valid_until: datetime
    key_revoked: bool
    grant_revoked: bool
    revision: int


class EvidenceReviewAuthorityState(Protocol):
    def current_authority(self, now: datetime) -> CurrentReviewAuthority:
        """Read protected CURRENT key/grant/revocation, refusing UTC rollback."""
        ...

    def current_registration(self, review_id: str, now: datetime) -> VerifiedReviewRegistration | None:
        ...

    def snapshot(self, review_id: str, now: datetime) -> tuple[CurrentReviewAuthority, VerifiedReviewRegistration | None]:
        """One atomic read of current key/grant/review and persisted clock guard."""
        ...

    def register(self, receipt: EvidenceReviewReceipt, registration: VerifiedReviewRegistration,
                 actor: str, now: datetime) -> None:
        """Atomically recheck current authority, append receipt+audit, advance revision.

        No ID reuse, no authority changes since validated revision. Persist UTC
        high-water mark; refuse rollback even after restart. Failure rolls back.
        This is host storage, never the caller-writable receipt cache.
        Receipt record contains every explicit verdict/reason; audit binds its
        digest, actor, actual registration UTC, action and old/new revisions.
        """
        ...

    def revoke(self, review_id: str, actor: str, now: datetime, reason: str) -> None:
        """Atomic irreversible revocation + actor/time/reason audit + revision."""
        ...
