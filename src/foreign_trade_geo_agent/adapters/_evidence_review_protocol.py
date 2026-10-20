"""Bounded host/client wire format. Authority comes from pinned keys/ports."""
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from typing import Protocol

from foreign_trade_geo_agent.core.evidence_review_authority import CurrentReviewAuthority
from foreign_trade_geo_agent.core.evidence_review_registry import VerifiedReviewRegistration, ReviewRegistrationStatus
from foreign_trade_geo_agent.core.evidence_sufficiency import ReviewPrincipal, aware_time, bounded_id
from .evidence_review import _read, _keys, canonical_bytes
from .evidence_review_cng import RsaPssPublicKey


class ReviewEnvironment(str, Enum):
    TEST = "TEST"
    PRODUCTION = "PRODUCTION"


@dataclass(frozen=True, slots=True)
class ReviewTrustAnchors:
    """Only protected installation may supply these; never read from receipts."""
    environment: ReviewEnvironment
    reviewer_sid: str
    agent_sid: str
    review_key: RsaPssPublicKey
    registry_key: RsaPssPublicKey

    def __post_init__(self):
        if (type(self.environment) is not ReviewEnvironment
            or not bounded_id(self.reviewer_sid) or not bounded_id(self.agent_sid)
            or self.reviewer_sid == self.agent_sid
            or type(self.review_key) is not RsaPssPublicKey or type(self.registry_key) is not RsaPssPublicKey
            or self.review_key == self.registry_key):
            raise ValueError("REVIEW_ANCHORS_INVALID")

    def domain(self, purpose: str) -> bytes:
        if purpose not in ("RECORD", "REGISTRY", "CONFIRM"):
            raise ValueError("REVIEW_DOMAIN_INVALID")
        return f"FTE-EVIDENCE-{self.environment.value}-{purpose}-v1\x00".encode("ascii")


class ReviewSigner(Protocol):
    @property
    def public_key(self) -> RsaPssPublicKey: ...

    def sign(self, message: bytes) -> bytes:
        """Host-only signing capability. Never pass to verification client."""
        ...


class AuthenticatedSessionIdentity(Protocol):
    def caller_sid(self, session: object) -> str:
        """From OS token of authenticated connection, NEVER payload reviewer_id.

        Windows implementation must impersonate/check token and always revert.
        Reject remote pipes and unidentified/anonymous sessions.
        """
        ...


@dataclass(frozen=True, slots=True)
class AuthenticatedRegistryReply:
    server_sid: str
    payload: bytes
    proof: bytes


class AuthenticatedReviewTransport(Protocol):
    def query(self, request: bytes) -> AuthenticatedRegistryReply:
        """Bounded local IPC with independently authenticated server OS SID.

        server_sid must come from verified connection process/token, not JSON.
        Enforce connection/read timeouts, local-only and message size limits.
        query-only: no signing, registration or revocation RPC for Agent.
        """
        ...


def authority_valid(authority, anchors, now):
    if type(authority) is not CurrentReviewAuthority or not aware_time(now):
        return False
    p = authority.principal
    return (type(p) is ReviewPrincipal and p.reviewer_id == anchors.reviewer_sid
        and bounded_id(p.project_id) and type(p.task_ids) is tuple and 0 < len(p.task_ids) <= 32
        and all(bounded_id(v) for v in p.task_ids) and len(set(p.task_ids)) == len(p.task_ids)
        and type(p.purposes) is tuple and 0 < len(p.purposes) <= 8
        and all(bounded_id(v) for v in p.purposes) and len(set(p.purposes)) == len(p.purposes)
        and type(p.synthetic) is bool and p.synthetic == (anchors.environment is ReviewEnvironment.TEST)
        and all(aware_time(v) for v in (p.valid_from, p.valid_until,
            authority.key_valid_from, authority.key_valid_until))
        and p.valid_from <= now < p.valid_until
        and authority.key_valid_from <= now < authority.key_valid_until
        and type(authority.key_revoked) is bool and not authority.key_revoked
        and type(authority.grant_revoked) is bool and not authority.grant_revoked
        and authority.review_key_fingerprint == anchors.review_key.fingerprint
        and type(authority.revision) is int and 1 <= authority.revision <= 1_000_000_000)


def authority_payload(authority):
    obj = asdict(authority)
    p = obj["principal"]
    for field in ("valid_from", "valid_until"):
        p[field] = p[field].isoformat()
    for field in ("key_valid_from", "key_valid_until"):
        obj[field] = obj[field].isoformat()
    return obj


def parse_authority(obj):
    _keys(obj, CurrentReviewAuthority.__dataclass_fields__)
    p = obj["principal"]
    _keys(p, ReviewPrincipal.__dataclass_fields__)
    if type(p["task_ids"]) is not list or type(p["purposes"]) is not list:
        raise ValueError()
    p = dict(p, task_ids=tuple(p["task_ids"]), purposes=tuple(p["purposes"]))
    for field in ("valid_from", "valid_until"):
        p[field] = datetime.fromisoformat(p[field])
    obj = dict(obj, principal=ReviewPrincipal(**p))
    for field in ("key_valid_from", "key_valid_until"):
        obj[field] = datetime.fromisoformat(obj[field])
    return CurrentReviewAuthority(**obj)


def registration_payload(registration):
    if registration is None:
        return None
    obj = asdict(registration)
    obj["challenge"] = registration.challenge.hex()
    for field in ("registered_at", "expires_at", "revoked_at", "checked_at"):
        obj[field] = None if obj[field] is None else obj[field].isoformat()
    return obj


def parse_registration(obj):
    if obj is None:
        return None
    _keys(obj, VerifiedReviewRegistration.__dataclass_fields__)
    obj = dict(obj)
    obj["challenge"] = bytes.fromhex(obj["challenge"])
    obj["status"] = ReviewRegistrationStatus(obj["status"])
    for field in ("registered_at", "expires_at", "revoked_at", "checked_at"):
        obj[field] = None if obj[field] is None else datetime.fromisoformat(obj[field])
    return VerifiedReviewRegistration(**obj)


def request_payload(review_id, challenge):
    if not bounded_id(review_id) or type(challenge) is not bytes or len(challenge) != 32:
        raise ValueError("REVIEW_QUERY_INVALID")
    return canonical_bytes({"schema_version": 1, "review_id": review_id, "challenge": challenge.hex()})


def parse_request(raw):
    obj = _read(raw, 1024)
    _keys(obj, ("schema_version", "review_id", "challenge"))
    if type(obj["schema_version"]) is not int or obj["schema_version"] != 1:
        raise ValueError()
    challenge = bytes.fromhex(obj["challenge"])
    if request_payload(obj["review_id"], challenge) != raw:
        raise ValueError()
    return obj["review_id"], challenge
