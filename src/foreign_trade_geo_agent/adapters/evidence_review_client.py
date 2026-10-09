"""Public-key-only consumer of fresh authenticated authority/registry responses."""
from datetime import datetime, timedelta
import hashlib
import secrets
import threading

from foreign_trade_geo_agent.core.evidence_review_registry import ReviewRegistrationStatus
from foreign_trade_geo_agent.core.evidence_sufficiency import aware_time, bounded_id
from .evidence_review import _read, _keys, canonical_bytes
from ._evidence_review_protocol import (
    ReviewTrustAnchors, AuthenticatedReviewTransport, AuthenticatedRegistryReply,
    request_payload, parse_authority, parse_registration, authority_valid,
)


class EvidenceReviewClient:
    """Implements existing authenticator AND current registry ports.

    No private-key capability, state writer, authorization cache or local grant DB.
    Revision/time high-water marks here only protect this process lifetime.
    Durable rollback protection must be supplied by the protected host state.
    """
    def __init__(self, *, anchors: ReviewTrustAnchors, transport: AuthenticatedReviewTransport, clock):
        if type(anchors) is not ReviewTrustAnchors or transport is None or clock is None:
            raise ValueError("TRUSTED_CLIENT_ROOT_REQUIRED")
        self.anchors, self._transport, self._clock = anchors, transport, clock
        self._last_revision, self._last_time = 0, None
        self._lock = threading.RLock()

    def _current(self, review_id, challenge):
        with self._lock:
            before = self._clock()
            if not aware_time(before) or (self._last_time is not None and before < self._last_time):
                raise ValueError()
            reply = self._transport.query(request_payload(review_id, challenge))
            after = self._clock()
            if (type(reply) is not AuthenticatedRegistryReply or reply.server_sid != self.anchors.reviewer_sid
                or not aware_time(after) or not before <= after <= before+timedelta(seconds=5)
                or type(reply.payload) is not bytes or not 0 < len(reply.payload) <= 16*1024
                or not self.anchors.registry_key.verify(self.anchors.domain("REGISTRY") + reply.payload, reply.proof)):
                raise ValueError()
            obj = _read(reply.payload, 16*1024)
            _keys(obj, ("schema_version", "environment", "server_sid", "review_id", "challenge",
                        "checked_at", "authority", "registration"))
            if (canonical_bytes(obj) != reply.payload or type(obj["schema_version"]) is not int
                or obj["schema_version"] != 1 or obj["environment"] != self.anchors.environment.value
                or obj["server_sid"] != self.anchors.reviewer_sid or obj["review_id"] != review_id
                or obj["challenge"] != challenge.hex()):
                raise ValueError()
            checked = datetime.fromisoformat(obj["checked_at"])
            if not aware_time(checked) or abs(after-checked) > timedelta(seconds=5):
                raise ValueError()
            authority = parse_authority(obj["authority"])
            if not authority_valid(authority, self.anchors, after) or authority.revision < self._last_revision:
                raise ValueError()
            registration = parse_registration(obj["registration"])
            self._last_revision, self._last_time = authority.revision, after
            if registration is None:
                return authority, None
            p, r = authority.principal, registration
            if (r.review_id != review_id or r.reviewer_id != p.reviewer_id or r.project_id != p.project_id
                or r.task_id not in p.task_ids or r.purpose not in p.purposes
                or r.challenge != challenge or r.checked_at != checked
                or type(r.revision) is not int or not 1 <= r.revision <= authority.revision
                or any(type(v) is not int or not 1 <= v <= 1_000_000
                    for v in (r.task_version, r.plan_version, r.evidence_version))
                or type(r.synthetic) is not bool or r.synthetic != p.synthetic
                or r.status is not ReviewRegistrationStatus.ACTIVE or r.revoked_at is not None
                or not aware_time(r.registered_at) or not aware_time(r.expires_at)
                or not p.valid_from <= r.registered_at <= after < r.expires_at <= p.valid_until
                or r.registered_at < authority.key_valid_from
                or r.expires_at > authority.key_valid_until
                or r.expires_at-r.registered_at > timedelta(days=1)
                or any(type(v) is not str or len(v) != 64 or any(c not in "0123456789abcdef" for c in v)
                    for v in (r.frozen_target_sha256, r.record_sha256, r.proof_sha256))):
                raise ValueError()
            return authority, registration

    def authenticate(self, record: bytes, proof: bytes, now):
        try:
            if (not aware_time(now) or type(record) is not bytes or not 0 < len(record) <= 16*1024
                or not self.anchors.review_key.verify(self.anchors.domain("RECORD") + record, proof)):
                return None
            obj = _read(record, 16*1024)
            if type(obj) is not dict or not bounded_id(obj.get("record_id")):
                return None
            authority, registration = self._current(obj["record_id"], secrets.token_bytes(32))
            if (registration is None or abs(now-registration.checked_at) > timedelta(seconds=5)
                or registration.record_sha256 != hashlib.sha256(record).hexdigest()
                or registration.proof_sha256 != hashlib.sha256(proof).hexdigest()):
                return None
            return authority.principal
        except Exception:
            return None

    def lookup_current(self, review_id: str, challenge: bytes):
        try:
            return self._current(review_id, challenge)[1]
        except Exception:
            raise ValueError("CURRENT_TRUSTED_REVIEW_REQUIRED") from None
