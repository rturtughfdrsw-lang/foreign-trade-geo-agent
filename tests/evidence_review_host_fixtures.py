"""Ephemeral BCrypt keys and mock sessions/state ONLY for single-process TEST.

No private-key export/persistence; no real Windows identity authentication.
"""
import ctypes
from dataclasses import replace
from datetime import timedelta
import struct

from foreign_trade_geo_agent.adapters.evidence_review_cng import (
    _BCrypt, _SPKI_PREFIX, _SPKI_SUFFIX, RsaPssPublicKey,
)
from foreign_trade_geo_agent.adapters.evidence_review_signing import BCryptRsaPssSigner
from foreign_trade_geo_agent.adapters._evidence_review_protocol import (
    ReviewTrustAnchors, ReviewEnvironment, authority_valid,
)
from foreign_trade_geo_agent.core.evidence_review_authority import CurrentReviewAuthority
from foreign_trade_geo_agent.core.evidence_review_registry import ReviewRegistrationStatus
from foreign_trade_geo_agent.core.evidence_sufficiency import ReviewPrincipal, aware_time, bounded_id
from tests.evidence_review_fixtures import NOW


class EphemeralTestSigner:
    def __init__(self):
        self.native = _BCrypt()
        self.algorithm = self.native.open()
        self.key = ctypes.c_void_p()
        self.calls = 0
        try:
            self.native.check(self.native.dll.BCryptGenerateKeyPair(self.algorithm, ctypes.byref(self.key), 3072, 0))
            self.native.check(self.native.dll.BCryptFinalizeKeyPair(self.key, 0))
            size = ctypes.c_ulong()
            self.native.check(self.native.dll.BCryptExportKey(self.key, None, "RSAPUBLICBLOB", None, 0, ctypes.byref(size), 0))
            blob = ctypes.create_string_buffer(size.value)
            self.native.check(self.native.dll.BCryptExportKey(self.key, None, "RSAPUBLICBLOB", blob, size.value, ctypes.byref(size), 0))
            if struct.unpack("<4I", blob.raw[:16]) != (0x31415352, 3072, 3, 384):
                raise ValueError("TEST_KEY_INVALID")
            self.public_key = RsaPssPublicKey(_SPKI_PREFIX + blob.raw[27:411] + _SPKI_SUFFIX)
            self.signer = BCryptRsaPssSigner(key_handle=self.key, public_key=self.public_key)
        except Exception:
            self.close()
            raise

    def sign(self, message):
        self.calls += 1
        return self.signer.sign(message)

    def close(self):
        if self.key.value:
            self.native.dll.BCryptDestroyKey(self.key)
            self.key = ctypes.c_void_p()
        if self.algorithm is not None:
            self.native.dll.BCryptCloseAlgorithmProvider(self.algorithm, 0)
            self.algorithm = None


class TestClock:
    def __init__(self):
        self.now, self.broken = NOW, False

    def __call__(self):
        if self.broken:
            raise RuntimeError("SECRET-CANARY")
        return self.now


class MockSessions:
    def __init__(self, anchors):
        self.owner, self.agent = object(), object()
        self.identities = {self.owner: anchors.reviewer_sid, self.agent: anchors.agent_sid}

    def caller_sid(self, session):
        return self.identities[session]


class TestAuthorityState:
    """TEST transaction double, not durable/protected authorization storage."""
    def __init__(self, anchors, target):
        self.anchors = anchors
        self.authority = CurrentReviewAuthority(
            ReviewPrincipal(anchors.reviewer_sid, target.project_id, (target.task_id,), (target.purpose,),
                NOW-timedelta(days=1), NOW+timedelta(days=1), True),
            anchors.review_key.fingerprint, NOW-timedelta(days=1), NOW+timedelta(days=1), False, False, 1)
        self.registrations, self.receipts, self.audit = {}, {}, []
        self.last_time = NOW
        self.broken, self.fail_register, self.concurrent_revoke = False, False, False

    def guard(self, now):
        if self.broken or not aware_time(now) or now < self.last_time:
            raise RuntimeError("SECRET-CANARY")
        self.last_time = now

    def current_authority(self, now):
        self.guard(now)
        return self.authority

    def current_registration(self, review_id, now):
        self.guard(now)
        return self.registrations.get(review_id)

    def snapshot(self, review_id, now):
        self.guard(now)
        return self.authority, self.registrations.get(review_id)

    def register(self, receipt, registration, actor, now):
        self.guard(now)
        if self.concurrent_revoke:
            self.authority = replace(self.authority, grant_revoked=True, revision=self.authority.revision+1)
        if (self.fail_register or not authority_valid(self.authority, self.anchors, now)
            or actor != self.anchors.reviewer_sid or receipt.review_id in self.registrations
            or registration.revision != self.authority.revision+1):
            raise RuntimeError("SECRET-CANARY")
        self.registrations[receipt.review_id] = registration
        self.receipts[receipt.review_id] = receipt
        self.authority = replace(self.authority, revision=registration.revision)
        self.audit.append(("REGISTER", actor, now, registration.revision, receipt.review_id))

    def revoke(self, review_id, actor, now, reason):
        self.guard(now)
        if not bounded_id(review_id) or actor != self.anchors.reviewer_sid:
            raise ValueError()
        old = self.registrations[review_id]
        if old.status is not ReviewRegistrationStatus.ACTIVE:
            raise ValueError()
        revision = self.authority.revision+1
        self.registrations[review_id] = replace(old, status=ReviewRegistrationStatus.REVOKED,
            revoked_at=now, revision=revision)
        self.authority = replace(self.authority, revision=revision)
        self.audit.append(("REVOKE", actor, now, revision, review_id, reason))


class LoopbackTestTransport:
    def __init__(self, host, sessions):
        self.host, self.sessions = host, sessions
        self.calls, self.broken, self.transform, self.reply = 0, False, None, None

    def query(self, request):
        self.calls += 1
        if self.broken:
            raise RuntimeError("SECRET-CANARY")
        reply = self.host.query_current(request, self.sessions.agent)
        self.reply = reply
        return reply if self.transform is None else self.transform(reply)


def test_anchors(review_signer, registry_signer):
    return ReviewTrustAnchors(ReviewEnvironment.TEST, "TEST-OWNER", "TEST-AGENT",
        review_signer.public_key, registry_signer.public_key)
