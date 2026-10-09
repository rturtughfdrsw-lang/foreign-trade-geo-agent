"""Synthetic only: random in-memory authentication keys, never production grants."""
from dataclasses import replace
from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import json
import secrets

from tests.test_first_party_excerpt_capacity import generic_fixture, native_planning
from foreign_trade_geo_agent.core.content_draft import ContentDraftInput

NOW = datetime(2026, 10, 8, 4, 0, tzinfo=UTC)


def synthetic_target(es, count=6):
    packet, scope = generic_fixture(count)
    scope = replace(scope, task_id="SYNTHETIC-LOGISTICS-EXCERPT-v1")
    # One statement is two adjacent fragments: six obligations/seven spans.
    # This is unrelated logistics text, never a synthetic NovaCNC signoff.
    first = scope.excerpts[0]
    cut = 4
    parts = (replace(first, end=first.start+cut, quote=first.quote[:cut]),
             replace(first, start=first.start+cut, quote=first.quote[cut:]))
    original_quotes = scope.quotes
    scope = replace(scope, excerpts=(*parts, *scope.excerpts[1:]))
    opportunity, plan, _, _ = native_planning(packet, scope)
    return es.ExcerptReviewTarget(
        project_id="SYNTHETIC-PROJECT", task_id=scope.task_id,
        task_version=1, plan_version=1, evidence_version=1,
        question="Quote all six synthetic packing observations in order.",
        attribution="Synthetic logistics fixture page",
        context="Fictional controlled test; no engineering or commercial approval.",
        scope=scope, draft_input=ContentDraftInput(packet, opportunity, plan),
        obligations=tuple(es.ExcerptObligation(f"O{i+1}", quote, (0, 1) if i == 0 else (i+1,))
                          for i, quote in enumerate(original_quotes)),
    )


class SyntheticAuthority:
    """Actual byte authentication; identity/grants never read from signed JSON."""
    def __init__(self, es, target):
        self._key = secrets.token_bytes(32)
        self.revoked = False
        self.principal = es.ReviewPrincipal(
            "SYNTHETIC-OWNER", target.project_id, (target.task_id,),
            ("OFFLINE_P_ONLY_EXCERPT",), NOW - timedelta(days=1),
            NOW + timedelta(days=1), True,
        )

    def sign(self, raw):
        return hmac.digest(self._key, b"SYNTHETIC-EVIDENCE-REVIEW-v1\x00" + raw, "sha256")

    def authenticate(self, raw, proof, now):
        if self.revoked or not hmac.compare_digest(self.sign(raw), proof):
            return None
        return self.principal


def record_for(target, frozen_bytes, input_digest):
    return {
        "schema_version": 1, "record_id": "SYNTHETIC-REVIEW-001",
        "reviewer_id": "SYNTHETIC-OWNER", "purpose": "OFFLINE_P_ONLY_EXCERPT",
        "project_id": target.project_id, "task_id": target.task_id,
        "task_version": target.task_version, "plan_version": target.plan_version,
        "evidence_version": target.evidence_version,
        "frozen_target_sha256": hashlib.sha256(frozen_bytes).hexdigest(),
        "draft_input_sha256": input_digest,
        "reviewed_at": "2026-10-08T03:00:00Z", "expires_at": "2026-10-08T05:00:00Z",
        "signoff": "APPROVED",
        "obligations": [{"obligation_id": o.obligation_id, "verdict": "APPROVED",
                         "reason": "Synthetic human decision fixture: exact scoped quote."}
                        for o in target.obligations],
        "decisions": [{"decision_id": d, "verdict": "APPROVED",
                       "reason": "Synthetic fixture, isolated offline scope only."}
                      for d in ("SOURCE_USE", "TASK_AND_DEPTH", "OFFLINE_PLACEMENT",
                                "P_ONLY_CANDIDATE", "FROZEN_CONSUMPTION",
                                "REVIEW_AUTHORITY", "VALIDITY_AND_STORAGE")],
    }


def review_bytes(record):
    return json.dumps(record, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode()
