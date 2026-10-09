"""Minimal host application interface; OS identity/state/clock are trusted ports.

No listener, Windows configuration, automatic verdicts or Agent signing RPC.
"""
from dataclasses import replace
from datetime import datetime, timedelta
import hashlib
import threading

from foreign_trade_geo_agent.core.evidence_review_authority import EvidenceReviewAuthorityState
from foreign_trade_geo_agent.core.evidence_review_registry import EvidenceReviewReceipt, VerifiedReviewRegistration, ReviewRegistrationStatus
from foreign_trade_geo_agent.core.evidence_sufficiency import EvidenceGateStatus, aware_time, bounded_id
from foreign_trade_geo_agent.core.p_only_draft import (
    FrozenPOnlyDraft, POnlyDraftRequestV1, draft_review_binding_error, p_only_draft_target_error,
)
from foreign_trade_geo_agent.workflows.evidence_sufficiency import EvidenceSufficiencyPreflight
from .evidence_review import AuthenticatedEvidenceReviewLoader, freeze_excerpt_target, canonical_bytes, _read, draft_input_digest
from ._evidence_review_protocol import (
    ReviewTrustAnchors, ReviewSigner, AuthenticatedSessionIdentity, AuthenticatedRegistryReply,
    authority_valid, authority_payload, registration_payload, parse_request,
    ReviewEnvironment,
)


class _ExplicitDecisionValidator:
    """Validation-only principal after authenticated owner session; never exported."""
    def __init__(self, principal):
        self.principal = principal

    def authenticate(self, record, proof, now):
        return self.principal


class EvidenceReviewHost:
    def __init__(self, *, anchors: ReviewTrustAnchors, identities: AuthenticatedSessionIdentity,
                 state: EvidenceReviewAuthorityState, clock, review_signer: ReviewSigner,
                 registry_signer: ReviewSigner):
        if (type(anchors) is not ReviewTrustAnchors or review_signer is None or registry_signer is None
            or identities is None or state is None or clock is None
            or review_signer.public_key != anchors.review_key or registry_signer.public_key != anchors.registry_key):
            raise ValueError("TRUSTED_HOST_ROOT_REQUIRED")
        self._anchors, self._identities, self._state = anchors, identities, state
        self._clock, self._review_signer, self._registry_signer = clock, review_signer, registry_signer
        self._last_time = None
        self._lock = threading.RLock()

    def _current(self, session, expected_sid):
        if self._identities.caller_sid(session) != expected_sid:
            raise ValueError()
        now = self._clock()
        if not aware_time(now) or (self._last_time is not None and now < self._last_time):
            raise ValueError()
        self._last_time = now
        authority = self._state.current_authority(now)
        if not authority_valid(authority, self._anchors, now):
            raise ValueError()
        return now, authority

    def query_current(self, request: bytes, session: object) -> AuthenticatedRegistryReply:
        try:
            with self._lock:
                now, authority = self._current(session, self._anchors.agent_sid)
                review_id, challenge = parse_request(request)
                authority, registration = self._state.snapshot(review_id, now)
                if not authority_valid(authority, self._anchors, now):
                    raise ValueError()
                if registration is not None:
                    registration = replace(registration, challenge=challenge, checked_at=now)
                payload = canonical_bytes({"schema_version": 1, "environment": self._anchors.environment.value,
                    "server_sid": self._anchors.reviewer_sid, "review_id": review_id,
                    "challenge": challenge.hex(), "checked_at": now.isoformat(),
                    "authority": authority_payload(authority), "registration": registration_payload(registration)})
                if len(payload) > 16*1024:
                    raise ValueError()
                proof = self._registry_signer.sign(self._anchors.domain("REGISTRY") + payload)
                return AuthenticatedRegistryReply(self._anchors.reviewer_sid, payload, proof)
        except Exception:
            raise ValueError("CURRENT_TRUSTED_REVIEW_REQUIRED") from None

    def seal(self, target, record: bytes, *, confirmation: bytes, session: object) -> EvidenceReviewReceipt:
        """Owner-local call: explicit per-item verdict/reason and exact confirmation.

        confirmation is SHA256(CONFIRM domain + frozen bytes + original record).
        It prevents accidental record substitution; it does NOT prove human intent.
        Actual owner interaction must supply it after displaying the final record.
        Client reviewer_id is checked for equality, never used as authentication.
        """
        return self._seal(target, record, confirmation=confirmation, session=session, draft_consumption=False)

    def seal_test_draft(self, target, record: bytes, *, confirmation: bytes, session: object) -> EvidenceReviewReceipt:
        """Separate explicit TEST signoff. Ordinary/offline seal cannot grant Draft."""
        if self._anchors.environment is not ReviewEnvironment.TEST:
            raise ValueError("ISOLATED_TEST_ROOT_REQUIRED")
        return self._seal(target, record, confirmation=confirmation, session=session, draft_consumption=True)

    def _seal(self, target, record, *, confirmation, session, draft_consumption):
        try:
            if draft_consumption and self._anchors.environment is not ReviewEnvironment.TEST:
                raise ValueError()
            with self._lock:
                now, authority = self._current(session, self._anchors.reviewer_sid)
                frozen = freeze_excerpt_target(target)
                if (type(record) is not bytes or not 0 < len(record) <= 16*1024
                    or type(confirmation) is not bytes or confirmation != hashlib.sha256(
                        self._anchors.domain("CONFIRM") + frozen + record).digest()):
                    raise ValueError()
                validator = AuthenticatedEvidenceReviewLoader(_ExplicitDecisionValidator(authority.principal))
                if not draft_consumption:
                    gate = EvidenceSufficiencyPreflight(review_loader=validator, allow_synthetic=True)
                    result = gate.check(target, record, b"validation-only", now=now)
                    if result.status not in (EvidenceGateStatus.SYNTHETIC_GREEN, EvidenceGateStatus.OFFLINE_REVIEW_GREEN):
                        raise ValueError()
                elif p_only_draft_target_error(target) is not None:
                    raise ValueError()
                review = validator.load_review(target, record, b"validation-only", now)
                if draft_consumption:
                    execution = FrozenPOnlyDraft(POnlyDraftRequestV1(frozen, review.record_id), target,
                        hashlib.sha256(frozen).hexdigest(), draft_input_digest(target.draft_input))
                    if draft_review_binding_error(execution, review):
                        raise ValueError()
                obj = _read(record, 16*1024)
                reviewed = datetime.fromisoformat(obj["reviewed_at"].replace("Z", "+00:00"))
                # Five-minute confirmation window; registration/audit use host UTC.
                if now-reviewed > timedelta(minutes=5) or authority.revision >= 1_000_000_000:
                    raise ValueError()
                if self._state.current_registration(review.record_id, now) is not None:
                    raise ValueError()
                expiry = datetime.fromisoformat(obj["expires_at"].replace("Z", "+00:00"))
                if expiry > authority.key_valid_until:
                    raise ValueError()
                proof = self._review_signer.sign(self._anchors.domain("RECORD") + record)
                if not self._anchors.review_key.verify(self._anchors.domain("RECORD") + record, proof):
                    raise ValueError()
                receipt = EvidenceReviewReceipt(review.record_id, frozen, record, proof)
                registration = VerifiedReviewRegistration(review.record_id, authority.principal.reviewer_id,
                    review.project_id, review.task_id, review.task_version, review.plan_version,
                    review.evidence_version, review.purpose, review.actual_target_sha256,
                    hashlib.sha256(record).hexdigest(), hashlib.sha256(proof).hexdigest(),
                    authority.revision+1, now, expiry, None, ReviewRegistrationStatus.ACTIVE,
                    b"", now, authority.principal.synthetic)
                self._state.register(receipt, registration, self._anchors.reviewer_sid, now)
                return receipt  # never returned unless durable register succeeds
        except Exception:
            raise ValueError("EXPLICIT_AUTHORIZED_REVIEW_REQUIRED") from None

    def revoke(self, review_id: str, *, reason: str, session: object) -> None:
        try:
            with self._lock:
                now, _ = self._current(session, self._anchors.reviewer_sid)
                if (not bounded_id(review_id) or type(reason) is not str or not reason.strip()
                    or len(reason) > 1000):
                    raise ValueError()
                self._state.revoke(review_id, self._anchors.reviewer_sid, now, reason)
        except Exception:
            raise ValueError("AUTHORIZED_REVOCATION_REQUIRED") from None
