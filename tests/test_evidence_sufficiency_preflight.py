"""Authentication, complete coverage and frozen binding; no Draft permission."""
import asyncio
from dataclasses import replace
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import unittest

from tests.evidence_review_fixtures import (
    NOW, SyntheticAuthority, synthetic_target, record_for, review_bytes,
)
from foreign_trade_geo_agent.core import change_plan as cp, content_draft as cd
from foreign_trade_geo_agent.core.first_party_planning import FirstPartyExcerpt, FirstPartyPlanningScope
from foreign_trade_geo_agent.core.history import ArtifactType
from foreign_trade_geo_agent.storage.serialization import decode_artifact, encode_artifact
from foreign_trade_geo_agent.workflows.content_draft import ContentDraftWorkflow


class NoWriter:
    calls = 0

    async def write_content_draft(self, prompt):
        self.calls += 1
        raise AssertionError("Preflight must not open native Draft")


class EvidenceSufficiencyPreflightTests(unittest.TestCase):
    def setUp(self):
        name = "foreign_trade_geo_agent.workflows.evidence_sufficiency"
        self.assertIsNotNone(importlib.util.find_spec(name), "trusted preflight is missing")
        self.es = importlib.import_module("foreign_trade_geo_agent.core.evidence_sufficiency")
        self.loader = importlib.import_module("foreign_trade_geo_agent.adapters.evidence_review")
        self.workflow = importlib.import_module(name)
        self.target = synthetic_target(self.es)
        self.authority = SyntheticAuthority(self.es, self.target)
        self.record = record_for(self.target, self.loader.freeze_excerpt_target(self.target),
                                 self.loader.draft_input_digest(self.target.draft_input))
        self.gate = self.workflow.EvidenceSufficiencyPreflight(
            review_loader=self.loader.AuthenticatedEvidenceReviewLoader(self.authority), allow_synthetic=True)

    def check(self, record=None, *, target=None, raw=None, proof=None, gate=None, now=NOW):
        raw = review_bytes(record or self.record) if raw is None else raw
        return (gate or self.gate).check(target or self.target, raw,
                                       self.authority.sign(raw) if proof is None else proof, now=now)

    def assertRejected(self, result, target=None):
        self.assertEqual(result.status, self.es.EvidenceGateStatus.REJECTED)
        self.assertTrue(result.reason)
        writer = NoWriter()
        report = asyncio.run(ContentDraftWorkflow(writer).run((target or self.target).draft_input))
        self.assertEqual(report.status, cd.ContentDraftStatus.INVALID_INPUT)
        self.assertEqual(writer.calls, 0)

    def test_authenticated_synthetic_complete_task_passes_without_opening_draft(self):
        self.assertEqual(len(self.target.obligations), 6)
        self.assertEqual(len(self.target.scope.excerpts), 7)
        self.assertEqual(self.target.obligations[0].excerpt_indexes, (0, 1))
        result = self.check()
        self.assertEqual(result.status, self.es.EvidenceGateStatus.SYNTHETIC_GREEN)
        self.assertEqual(result.reviewer_id, "SYNTHETIC-OWNER")
        self.assertEqual(result.review_id, "SYNTHETIC-REVIEW-001")
        writer = NoWriter()
        self.assertEqual(asyncio.run(ContentDraftWorkflow(writer).run(self.target.draft_input)).status,
                         cd.ContentDraftStatus.INVALID_INPUT)
        self.assertEqual(writer.calls, 0)

    def test_default_authority_and_default_mode_reject_synthetic(self):
        for gate in (self.workflow.EvidenceSufficiencyPreflight(),
                     self.workflow.EvidenceSufficiencyPreflight(
                         review_loader=self.loader.AuthenticatedEvidenceReviewLoader(self.authority))):
            with self.subTest(gate=type(gate).__name__):
                self.assertRejected(self.check(gate=gate))

    def test_not_reviewed_partial_missing_duplicate_and_reasonless_reject(self):
        variants = []
        for verdict in ("NOT_REVIEWED", "REJECTED", "SUPPORTED"):
            r = json.loads(review_bytes(self.record)); r["obligations"][2]["verdict"] = verdict; variants.append(r)
        r = json.loads(review_bytes(self.record)); r["obligations"].pop(); variants.append(r)
        r = json.loads(review_bytes(self.record)); r["obligations"].append(r["obligations"][0]); variants.append(r)
        r = json.loads(review_bytes(self.record)); r["obligations"][0]["reason"] = ""; variants.append(r)
        r = json.loads(review_bytes(self.record)); r["signoff"] = "NOT_REVIEWED"; variants.append(r)
        r = json.loads(review_bytes(self.record)); r["decisions"].pop(); variants.append(r)
        r = json.loads(review_bytes(self.record)); r["decisions"][0]["verdict"] = "NOT_REVIEWED"; variants.append(r)
        for i, r in enumerate(variants):
            with self.subTest(case=i): self.assertRejected(self.check(r))

    def test_expired_future_naive_reversed_times_reject(self):
        for field, value in (("expires_at", "2026-10-08T04:00:00Z"),
                             ("reviewed_at", "2026-10-08T04:00:01Z"),
                             ("reviewed_at", "2026-10-08T03:00:00"),
                             ("expires_at", "2026-10-08T02:00:00Z")):
            r = dict(self.record); r[field] = value
            with self.subTest(field=field, value=value): self.assertRejected(self.check(r))
        self.assertRejected(self.check(now=NOW.replace(tzinfo=None)))

    def test_identity_and_permissions_are_external_and_current(self):
        principal = self.authority.principal
        for change in ({"reviewer_id": "someone-else"}, {"project_id": "other"},
                       {"task_ids": ("EXPLAIN-old-task",)}, {"purposes": ("EXPLAIN",)},
                       {"valid_until": NOW}, {"valid_from": NOW.replace(hour=5)}):
            self.authority.principal = replace(principal, **change)
            with self.subTest(change=tuple(change)): self.assertRejected(self.check())
        self.authority.principal = principal
        self.authority.revoked = True
        self.assertRejected(self.check())

    def test_task_plan_evidence_input_and_historical_authorization_mismatch(self):
        for key, value in (("task_id", "T-P3-EQUIPMENT-BRIEF-CANDIDATE-v2"),
                           ("task_version", 2), ("plan_version", 2), ("evidence_version", 2),
                           ("purpose", "EXPLAIN"), ("draft_input_sha256", "0"*64),
                           ("frozen_target_sha256", "0"*64), ("project_id", "other")):
            r = dict(self.record); r[key] = value
            with self.subTest(field=key): self.assertRejected(self.check(r))
        for change in ({"question": "Explain the machinery."}, {"context": "Operating manufacturer"},
                       {"plan_version": 2}, {"evidence_version": 2},
                       {"draft_input": replace(self.target.draft_input, target_language="zh")},
                       {"obligations": self.target.obligations[:-1]}):
            target = replace(self.target, **change)
            with self.subTest(target_change=tuple(change)): self.assertRejected(self.check(target=target), target)

    def test_forged_proof_and_mutable_json_flags_cannot_authorize(self):
        self.assertRejected(self.check(proof=b"0"*32))
        original = review_bytes(self.record)
        r = dict(self.record); r["record_id"] = "forged"
        self.assertRejected(self.check(raw=review_bytes(r), proof=self.authority.sign(original)))
        r = dict(self.record); r["runtime_approval_valid"] = True
        self.assertRejected(self.check(r))
        r = dict(self.record); r["synthetic"] = False
        self.assertRejected(self.check(r))

    def test_duplicate_keys_oversized_unknown_and_malformed_json_fail_closed(self):
        raw = review_bytes(self.record)
        for malformed in (raw[:-1]+b',"signoff":"APPROVED"}', b'[]', b'null',
                          b'{"error":"SECRET-CANARY"}', b'x'*20000, b'\xff'):
            with self.subTest(length=len(malformed)):
                result = self.check(raw=malformed)
                self.assertRejected(result)
                self.assertNotIn("SECRET-CANARY", result.reason)

    def test_scope_forgery_explain_comparison_and_missing_target_obligations(self):
        base = synthetic_target(self.es, count=3)
        operation = base.draft_input.change_plan_report.operations[0]
        for intent in (cp.ContentPointIntent.EXPLAIN, cp.ContentPointIntent.COMPARE):
            points = (replace(operation.content_points[0], intent=intent), *operation.content_points[1:])
            op = replace(operation, content_points=points)
            target = replace(base, draft_input=replace(base.draft_input,
                change_plan_report=replace(base.draft_input.change_plan_report, operations=(op,))))
            # Even a freshly authenticated record cannot approve illegal P-only semantics.
            r = record_for(target, self.loader.freeze_excerpt_target(target),
                           self.loader.draft_input_digest(target.draft_input))
            self.assertRejected(self.check(r, target=target), target)
        for obligations in ((), (replace(self.target.obligations[0], excerpt_indexes=(99,)),),
                            (replace(self.target.obligations[0], statement="Forged quote"), *self.target.obligations[1:])):
            target = replace(self.target, obligations=obligations)
            self.assertRejected(self.check(target=target), target)

    def test_freeze_reload_checks_same_bytes_and_changed_source_is_not_authorized(self):
        raw = self.loader.freeze_excerpt_target(self.target)
        loaded = self.loader.load_excerpt_target(raw)
        self.assertEqual(loaded, self.target)
        self.assertEqual(self.check(target=loaded).status, self.es.EvidenceGateStatus.SYNTHETIC_GREEN)
        changed = json.loads(raw); changed["draft_input"]["site_content"]["pages"][0]["title"] = "Changed source"
        loaded = self.loader.load_excerpt_target(json.dumps(changed).encode())
        self.assertRejected(self.check(target=loaded), loaded)
        with self.assertRaises(ValueError): self.loader.load_excerpt_target(b'x'*200000)

    def test_authority_failure_is_sanitized_and_rejected(self):
        class Broken:
            def authenticate(self, *args): raise RuntimeError("SECRET-CANARY")
        result = self.check(gate=self.workflow.EvidenceSufficiencyPreflight(
            review_loader=self.loader.AuthenticatedEvidenceReviewLoader(Broken()), allow_synthetic=True))
        self.assertRejected(result)
        self.assertNotIn("SECRET-CANARY", result.reason)

    def test_real_frozen_six_obligations_remain_unreviewed_and_writer_zero(self):
        folder = Path(__file__).resolve().parents[1]/"docs/review-packages/evidence-sufficiency-2026-10-08-excerpt-v2"
        read = lambda name: json.loads((folder/name).read_bytes())
        get = lambda kind, name: decode_artifact(kind, 1, (folder/name).read_bytes().decode())
        packet = get(ArtifactType.SITE_CONTENT, "snapshots/site_content.json")
        raw_scope = read("planning-scope.json")
        scope = FirstPartyPlanningScope(raw_scope["task_id"], packet, raw_scope["page_ref"],
            raw_scope["heading"], tuple(FirstPartyExcerpt(**e) for e in raw_scope["excerpts"]))
        inp = cd.ContentDraftInput(packet, get(ArtifactType.CONTENT_OPPORTUNITY, "content_opportunity.json"),
                                  get(ArtifactType.CHANGE_PLAN, "change_plan.json"))
        coverage = read("coverage.json")["obligations"]
        target = replace(self.target, project_id="foreign-trade-geo-agent", task_id=scope.task_id,
            task_version=2, scope=scope, draft_input=inp,
            obligations=tuple(self.es.ExcerptObligation(o["obligation_id"], o["artifact_span"]["quote"],
                tuple(scope.excerpts.index(FirstPartyExcerpt(**e)) for e in o["excerpt_spans"])) for o in coverage))
        self.assertEqual([o["human_support_verdict"] for o in coverage], ["NOT_REVIEWED"]*6)
        self.assertRejected(self.workflow.EvidenceSufficiencyPreflight().check(target), target)
        for kind, value in ((ArtifactType.SITE_CONTENT, inp.site_content),
                            (ArtifactType.CONTENT_OPPORTUNITY, inp.opportunity_report),
                            (ArtifactType.CHANGE_PLAN, inp.change_plan_report)):
            encoded = encode_artifact(kind, value)
            self.assertEqual(encode_artifact(kind, decode_artifact(kind, 1, encoded)), encoded)

    def test_new_owner_package_roundtrip_digest_and_pending_state(self):
        folder = Path(__file__).resolve().parents[1]/"docs/review-packages/evidence-sufficiency-2026-10-08-trusted-preflight"
        raw = (folder/"frozen-target.json").read_bytes()
        target = self.loader.load_excerpt_target(raw)
        template = json.loads((folder/"review-record.UNSIGNED.template.json").read_bytes())
        self.assertEqual(self.es.excerpt_target_error(target), None)
        self.assertEqual(self.loader.freeze_excerpt_target(target), raw)
        self.assertEqual((target.task_version, target.plan_version, target.evidence_version), (2, 2, 1))
        self.assertEqual(hashlib.sha256(raw).hexdigest(), template["frozen_target_sha256"])
        self.assertEqual(self.loader.draft_input_digest(target.draft_input),
                         "a24428cbc575527b09d59897422fdabe6038c13b206878ddc4cce0a93256b7e2")
        self.assertEqual(template["draft_input_sha256"], self.loader.draft_input_digest(target.draft_input))
        self.assertEqual([o["verdict"] for o in template["obligations"]], ["NOT_REVIEWED"]*6)
        self.assertEqual([d["verdict"] for d in template["decisions"]], ["NOT_REVIEWED"]*7)
        self.assertIsNone(template["reviewer_id"])
        self.assertIsNone(template["reviewed_at"])
        self.assertEqual(template["signoff"], "NOT_REVIEWED")
        self.assertEqual(len(target.scope.excerpts), 7)
        result = self.workflow.EvidenceSufficiencyPreflight().check(target,
            (folder/"review-record.UNSIGNED.template.json").read_bytes(), b"forged")
        self.assertRejected(result, target)
        self.assertEqual(result.reason, "TRUSTED_REVIEW_REQUIRED")
