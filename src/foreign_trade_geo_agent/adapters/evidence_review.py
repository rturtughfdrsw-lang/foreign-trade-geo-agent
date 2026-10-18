"""Strict frozen-input codec and purpose-specific authenticated review loader.

No signing implementation, trust file loader or test credentials live here.
Existing artifact codecs remain unchanged. JSON/digests never grant authority.
"""
from dataclasses import asdict
from datetime import datetime, timedelta
import hashlib
import json

from foreign_trade_geo_agent.core.content_draft import ContentDraftInput
from foreign_trade_geo_agent.core.evidence_sufficiency import (
    ExcerptObligation, ExcerptReviewTarget, EvidenceReviewAuthenticator,
    AuthenticatedReview, ReviewPrincipal, REQUIRED_REVIEW_DECISIONS, aware_time, bounded_id,
    OFFLINE_EXCERPT_PURPOSE, P_ONLY_DRAFT_PURPOSE_V1, P_ONLY_DRAFT_DECISIONS_V1,
)
from foreign_trade_geo_agent.core.first_party_planning import FirstPartyExcerpt, FirstPartyPlanningScope
from foreign_trade_geo_agent.core.history import ArtifactType
from foreign_trade_geo_agent.storage.serialization import decode_artifact, encode_artifact

MAX_FROZEN_BYTES = 128 * 1024
MAX_REVIEW_BYTES = 16 * 1024
MAX_PROOF_BYTES = 4096
MAX_REVIEW_LIFETIME = timedelta(days=1)


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("REVIEW_FORMAT_INVALID")
        result[key] = value
    return result


def _read(raw: bytes, limit: int):
    if type(raw) is not bytes or not 0 < len(raw) <= limit:
        raise ValueError("REVIEW_FORMAT_INVALID")
    return json.loads(raw.decode("utf-8"), object_pairs_hook=_unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("REVIEW_FORMAT_INVALID")))


def _keys(raw, expected):
    if type(raw) is not dict or set(raw) != set(expected):
        raise ValueError("REVIEW_FORMAT_INVALID")


def _input_payload(value):
    return {"site_content": json.loads(encode_artifact(ArtifactType.SITE_CONTENT, value.site_content)),
            "opportunity_report": json.loads(encode_artifact(ArtifactType.CONTENT_OPPORTUNITY, value.opportunity_report)),
            "change_plan_report": json.loads(encode_artifact(ArtifactType.CHANGE_PLAN, value.change_plan_report)),
            "target_language": value.target_language}


def draft_input_digest(value: ContentDraftInput) -> str:
    return hashlib.sha256(canonical_bytes(_input_payload(value))).hexdigest()


_TARGET_FIELDS = ("project_id", "task_id", "task_version", "plan_version", "evidence_version",
                  "question", "attribution", "context", "task_kind", "purpose", "output_constraints")


def freeze_excerpt_target(target: ExcerptReviewTarget) -> bytes:
    # Encoding is not validation or authority. Invalid targets can be preserved
    # for inspection but the preflight revalidates every loaded object.
    payload = {k: getattr(target, k) for k in _TARGET_FIELDS}
    payload.update(schema_version=1, draft_input=_input_payload(target.draft_input),
                   scope={"task_id": target.scope.task_id, "page_ref": target.scope.page_ref,
                          "heading": target.scope.heading, "task_kind": target.scope.task_kind,
                          "excerpts": [asdict(e) for e in target.scope.excerpts]},
                   obligations=[asdict(o) for o in target.obligations])
    raw = canonical_bytes(payload)
    if len(raw) > MAX_FROZEN_BYTES:
        raise ValueError("FROZEN_INPUT_TOO_LARGE")
    return raw


def load_excerpt_target(raw: bytes) -> ExcerptReviewTarget:
    try:
        obj = _read(raw, MAX_FROZEN_BYTES)
        _keys(obj, (*_TARGET_FIELDS, "schema_version", "draft_input", "scope", "obligations"))
        if type(obj["schema_version"]) is not int or obj["schema_version"] != 1:
            raise ValueError()
        inp = obj["draft_input"]
        _keys(inp, ("site_content", "opportunity_report", "change_plan_report", "target_language"))
        values = [decode_artifact(kind, 1, canonical_bytes(inp[field]).decode()) for field, kind in (
            ("site_content", ArtifactType.SITE_CONTENT), ("opportunity_report", ArtifactType.CONTENT_OPPORTUNITY),
            ("change_plan_report", ArtifactType.CHANGE_PLAN))]
        value = ContentDraftInput(*values, target_language=inp["target_language"])
        scope = obj["scope"]
        _keys(scope, ("task_id", "page_ref", "heading", "task_kind", "excerpts"))
        if type(scope["excerpts"]) is not list or type(obj["obligations"]) is not list or type(obj["output_constraints"]) is not list:
            raise ValueError()
        excerpts = []
        for item in scope["excerpts"]:
            _keys(item, ("field", "start", "end", "quote", "structured_index"))
            excerpts.append(FirstPartyExcerpt(**item))
        selected = FirstPartyPlanningScope(scope["task_id"], value.site_content, scope["page_ref"],
            scope["heading"], tuple(excerpts), scope["task_kind"])
        obligations = []
        for o in obj["obligations"]:
            _keys(o, ("obligation_id", "statement", "excerpt_indexes"))
            if type(o["excerpt_indexes"]) is not list:
                raise ValueError()
            obligations.append(ExcerptObligation(o["obligation_id"], o["statement"], tuple(o["excerpt_indexes"])))
        fields = {k: obj[k] for k in _TARGET_FIELDS}
        fields["output_constraints"] = tuple(fields["output_constraints"])
        return ExcerptReviewTarget(**fields, scope=selected, draft_input=value, obligations=tuple(obligations))
    except Exception:
        raise ValueError("FROZEN_INPUT_INVALID") from None


def _load_authenticated_review(target: ExcerptReviewTarget, raw: bytes, proof: bytes, *,
                              authenticator: EvidenceReviewAuthenticator | None,
                              now: datetime) -> AuthenticatedReview:
    """Authenticate before interpreting signoff; sanitized fail-closed errors."""
    try:
        if (authenticator is None or not aware_time(now) or type(raw) is not bytes
            or not 0 < len(raw) <= MAX_REVIEW_BYTES or type(proof) is not bytes
            or not 0 < len(proof) <= MAX_PROOF_BYTES):
            raise ValueError()
        principal = authenticator.authenticate(raw, proof, now)
        if (type(principal) is not ReviewPrincipal or not bounded_id(principal.reviewer_id)
            or not bounded_id(principal.project_id) or type(principal.synthetic) is not bool
            or type(principal.task_ids) is not tuple or not all(bounded_id(i) for i in principal.task_ids)
            or type(principal.purposes) is not tuple or not all(bounded_id(i) for i in principal.purposes)
            or not aware_time(principal.valid_from) or not aware_time(principal.valid_until)
            or not principal.valid_from <= now < principal.valid_until):
            raise ValueError()
        record = _read(raw, MAX_REVIEW_BYTES)
        _keys(record, ("schema_version", "record_id", "reviewer_id", "purpose", "project_id", "task_id",
                       "task_version", "plan_version", "evidence_version", "frozen_target_sha256",
                       "draft_input_sha256", "reviewed_at", "expires_at", "signoff", "obligations", "decisions"))
        if (type(record["schema_version"]) is not int or record["schema_version"] != 1
            or record["signoff"] != "APPROVED" or record["reviewer_id"] != principal.reviewer_id
            or record["project_id"] != principal.project_id or record["task_id"] not in principal.task_ids
            or record["purpose"] not in principal.purposes
            or not all(bounded_id(record[k]) for k in ("record_id", "reviewer_id", "purpose", "project_id", "task_id"))
            or any(type(record[k]) is not int or not 1 <= record[k] <= 1_000_000
                   for k in ("task_version", "plan_version", "evidence_version"))):
            raise ValueError()
        for field in ("frozen_target_sha256", "draft_input_sha256"):
            digest = record[field]
            if type(digest) is not str or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise ValueError()
        if any(type(record[k]) is not str for k in ("reviewed_at", "expires_at")):
            raise ValueError()
        reviewed, expires = (datetime.fromisoformat(record[k].replace("Z", "+00:00"))
                             for k in ("reviewed_at", "expires_at"))
        if (not aware_time(reviewed) or not aware_time(expires)
            or not principal.valid_from <= reviewed <= now < expires <= principal.valid_until
            or expires - reviewed > MAX_REVIEW_LIFETIME):
            raise ValueError()
        ids = []
        for field, id_key, maximum in (("obligations", "obligation_id", 10), ("decisions", "decision_id", 7)):
            items = record[field]
            if type(items) is not list or not 1 <= len(items) <= maximum:
                raise ValueError()
            group = []
            for item in items:
                _keys(item, (id_key, "verdict", "reason"))
                if (not bounded_id(item[id_key]) or item["verdict"] != "APPROVED"
                    or type(item["reason"]) is not str or not item["reason"].strip() or len(item["reason"]) > 1000):
                    raise ValueError()
                group.append(item[id_key])
            if len(set(group)) != len(group):
                raise ValueError()
            ids.append(tuple(group))
        decisions = {OFFLINE_EXCERPT_PURPOSE: REQUIRED_REVIEW_DECISIONS,
                     P_ONLY_DRAFT_PURPOSE_V1: P_ONLY_DRAFT_DECISIONS_V1}.get(target.purpose)
        if decisions is None or ids[1] != decisions:
            raise ValueError()
        return AuthenticatedReview(principal, record["record_id"], record["project_id"], record["task_id"],
            record["task_version"], record["plan_version"], record["evidence_version"], record["purpose"],
            record["frozen_target_sha256"], record["draft_input_sha256"], ids[0],
            hashlib.sha256(freeze_excerpt_target(target)).hexdigest(), draft_input_digest(target.draft_input))
    except Exception:
        raise ValueError("TRUSTED_REVIEW_REQUIRED") from None


class AuthenticatedEvidenceReviewLoader:
    def __init__(self, authenticator: EvidenceReviewAuthenticator) -> None:
        self._authenticator = authenticator

    def load_review(self, target: ExcerptReviewTarget, record: bytes, proof: bytes,
                    now: datetime) -> AuthenticatedReview:
        return _load_authenticated_review(target, record, proof,
                                          authenticator=self._authenticator, now=now)
