"""Real PSS + TEST-only sessions/state; never an OS isolation acceptance test."""
import asyncio
from dataclasses import replace
from datetime import timedelta
import hashlib
import json
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import unittest

from foreign_trade_geo_agent.core import evidence_sufficiency as es
from foreign_trade_geo_agent.adapters.evidence_review import (
    freeze_excerpt_target, draft_input_digest, load_excerpt_target, canonical_bytes,
)
from foreign_trade_geo_agent.adapters.evidence_review_host import EvidenceReviewHost
from foreign_trade_geo_agent.adapters.evidence_review_client import EvidenceReviewClient
from foreign_trade_geo_agent.adapters.evidence_review_cng import RsaPssPublicKey
from foreign_trade_geo_agent.adapters._evidence_review_protocol import ReviewEnvironment, request_payload
from foreign_trade_geo_agent.evidence_review_composition import production_preflight, isolated_test_preflight
from foreign_trade_geo_agent.storage.evidence_review_receipts import SQLiteEvidenceReviewReceipts
from foreign_trade_geo_agent.workflows.content_draft import ContentDraftWorkflow
from foreign_trade_geo_agent.core.content_draft import ContentDraftStatus
from tests.test_evidence_sufficiency_preflight import NoWriter
from tests.evidence_review_fixtures import NOW, synthetic_target, record_for, review_bytes
from tests.evidence_review_host_fixtures import (
    EphemeralTestSigner, TestClock, MockSessions, TestAuthorityState, LoopbackTestTransport, test_anchors,
)


@unittest.skipUnless(sys.platform == "win32", "Windows BCrypt required; never substitute crypto double")
class EvidenceReviewHostClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.review_signer = EphemeralTestSigner()
        cls.addClassCleanup(cls.review_signer.close)
        cls.registry_signer = EphemeralTestSigner()
        cls.addClassCleanup(cls.registry_signer.close)

    def setUp(self):
        self.anchors = test_anchors(self.review_signer, self.registry_signer)
        self.target = synthetic_target(es)
        self.clock = TestClock()
        self.sessions = MockSessions(self.anchors)
        self.state = TestAuthorityState(self.anchors, self.target)
        self.host = self.new_host()
        self.transport = LoopbackTestTransport(self.host, self.sessions)
        self.client = self.new_client()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = SQLiteEvidenceReviewReceipts.create(Path(self.temp.name)/"test-receipts.sqlite3")
        self.record = record_for(self.target, freeze_excerpt_target(self.target), draft_input_digest(self.target.draft_input))
        self.record.update(reviewer_id=self.anchors.reviewer_sid, reviewed_at=NOW.isoformat())
        self.receipt = self.seal(self.record)
        self.store.append(self.receipt)

    def new_host(self):
        return EvidenceReviewHost(anchors=self.anchors, identities=self.sessions, state=self.state,
            clock=self.clock, review_signer=self.review_signer, registry_signer=self.registry_signer)

    def new_client(self, anchors=None):
        return EvidenceReviewClient(anchors=anchors or self.anchors, transport=self.transport, clock=self.clock)

    def seal(self, record, target=None, session=None, confirmation=None):
        target = target or self.target
        raw = review_bytes(record)
        confirmation = confirmation if confirmation is not None else hashlib.sha256(
            self.anchors.domain("CONFIRM")+freeze_excerpt_target(target)+raw).digest()
        return self.host.seal(target, raw, confirmation=confirmation,
            session=self.sessions.owner if session is None else session)

    def result(self, target=None, client=None):
        return isolated_test_preflight(receipt_reader=self.store, client=client or self.client,
            clock=self.clock).check(target or self.target, self.receipt.review_id)

    def rejected(self, result):
        self.assertEqual(result.status, es.EvidenceGateStatus.REJECTED)
        self.assertNotIn("SECRET-CANARY", result.reason)

    def mutate_reply(self, change):
        def transform(reply):
            obj = json.loads(reply.payload)
            change(obj)
            payload = canonical_bytes(obj)
            return replace(reply, payload=payload, proof=self.registry_signer.sign(
                self.anchors.domain("REGISTRY")+payload))
        self.transport.transform = transform

    def test_pss_roundtrip_rechecks_current_and_writer_zero(self):
        self.assertEqual(len(self.receipt.proof),384)
        self.assertEqual(self.result().status,es.EvidenceGateStatus.SYNTHETIC_GREEN)
        calls=self.transport.calls
        self.assertEqual(self.result().status,es.EvidenceGateStatus.SYNTHETIC_GREEN)
        self.assertGreater(self.transport.calls,calls)
        self.assertEqual(self.store.get_receipt(self.receipt.review_id),self.receipt)
        writer=NoWriter()
        self.assertEqual(asyncio.run(ContentDraftWorkflow(writer).run(self.target.draft_input)).status,ContentDraftStatus.INVALID_INPUT)
        self.assertEqual(writer.calls,0)
        self.assertFalse(hasattr(self.client,"sign"))
        self.assertFalse(hasattr(self.client,"register"))

    def test_native_signature_dotnet_interoperability(self):
        import base64
        script = r'''
$ErrorActionPreference='Stop'
$o=[Console]::In.ReadToEnd() | ConvertFrom-Json
$r=[Security.Cryptography.RSACng]::new()
try {
 $spki=[Convert]::FromBase64String($o.spki); $n=0
 $r.ImportSubjectPublicKeyInfo($spki,[ref]$n)
 $ok=$r.VerifyData([Convert]::FromBase64String($o.message),[Convert]::FromBase64String($o.proof),
   [Security.Cryptography.HashAlgorithmName]::SHA256,[Security.Cryptography.RSASignaturePadding]::Pss)
 $r2=[Security.Cryptography.RSACng]::new(3072)
 try {
  @{ok=$ok; consumed=$n; spki=[Convert]::ToBase64String($r2.ExportSubjectPublicKeyInfo());
    proof=[Convert]::ToBase64String($r2.SignData([Convert]::FromBase64String($o.message),
    [Security.Cryptography.HashAlgorithmName]::SHA256,[Security.Cryptography.RSASignaturePadding]::Pss))} | ConvertTo-Json -Compress
 } finally {$r2.Dispose()}
} finally {$r.Dispose()}
'''
        message=self.anchors.domain("RECORD")+self.receipt.record
        data={k:base64.b64encode(v).decode() for k,v in (
            ("spki",self.anchors.review_key.spki),("message",message),("proof",self.receipt.proof))}
        proc=subprocess.run(["pwsh","-NoProfile","-NonInteractive","-Command",script],
            input=json.dumps(data),capture_output=True,text=True,timeout=30)
        self.assertEqual(proc.returncode,0,"Local .NET PSS interoperability failed")
        result=json.loads(proc.stdout)
        self.assertIs(result["ok"],True); self.assertEqual(result["consumed"],422)
        public=RsaPssPublicKey(base64.b64decode(result["spki"]))
        self.assertTrue(public.verify(message,base64.b64decode(result["proof"])))

    def test_forged_wrong_key_wrong_domain_and_changed_original_bytes_reject(self):
        message=self.anchors.domain("RECORD")+self.receipt.record
        for proof in (b"fake",b"\0"*384,self.registry_signer.sign(message),
            self.review_signer.sign(self.anchors.domain("REGISTRY")+self.receipt.record)):
            self.assertIsNone(self.client.authenticate(self.receipt.record,proof,NOW))
        self.assertIsNone(self.client.authenticate(self.receipt.record+b" ",self.receipt.proof,NOW))

    def test_payload_reviewer_is_not_authenticated_session(self):
        for session in (self.sessions.agent,object(),self.anchors.reviewer_sid):
            with self.assertRaisesRegex(ValueError,"EXPLICIT_AUTHORIZED_REVIEW_REQUIRED"):
                self.seal(dict(self.record,record_id="TEST-NEW"),session=session)
        with self.assertRaises(ValueError):
            self.seal(dict(self.record,record_id="TEST-NEW",reviewer_id="CLIENT-FORGED-OWNER"))
        self.assertEqual(len(self.state.audit),1)

    def test_query_only_accepts_agent_and_cannot_register_or_sign(self):
        request=request_payload(self.receipt.review_id,secrets.token_bytes(32))
        for session in (self.sessions.owner,object(),self.anchors.agent_sid):
            with self.assertRaises(ValueError): self.host.query_current(request,session)
        for extra in ({"reviewer_id":self.anchors.reviewer_sid},{"action":"seal"},{"approved":True}):
            request=dict(schema_version=1,review_id=self.receipt.review_id,challenge=secrets.token_hex(32),**extra)
            with self.assertRaises(ValueError): self.host.query_current(canonical_bytes(request),self.sessions.agent)
        self.assertEqual(len(self.state.audit),1)

    def test_explicit_all_item_verdicts_reasons_required_before_signing(self):
        calls=self.review_signer.calls
        for field in ("obligations","decisions"):
            for mode in ("missing","unreviewed","rejected","reason","empty"):
                record=json.loads(review_bytes(self.record)); record["record_id"]="TEST-NEW"
                if mode=="missing": record[field].pop()
                elif mode=="empty": record[field]=[]
                elif mode=="reason": record[field][0]["reason"]=" "
                else: record[field][0]["verdict"]="NOT_REVIEWED" if mode=="unreviewed" else "REJECTED"
                with self.subTest(field=field,mode=mode),self.assertRaises(ValueError): self.seal(record)
        self.assertEqual(self.review_signer.calls,calls)
        self.assertEqual(len(self.state.audit),1)

    def test_confirmation_and_wrong_binding_reject_before_signing(self):
        calls=self.review_signer.calls
        for confirmation in (b"",b"x"*32):
            with self.assertRaises(ValueError): self.seal(dict(self.record,record_id="TEST-NEW"),confirmation=confirmation)
        for field in ("frozen_target_sha256","draft_input_sha256","task_id","project_id","purpose"):
            record=dict(self.record,record_id="TEST-NEW"); record[field]="0"*64
            with self.subTest(field=field),self.assertRaises(ValueError): self.seal(record)
        self.assertEqual(self.review_signer.calls,calls)

    def test_task_versions_input_span_context_and_purpose_changes_reject(self):
        for change in ({"task_id":"CROSS-TASK"},{"task_version":2},{"plan_version":2},{"evidence_version":2},
            {"purpose":"EXPLAIN"},{"obligations":self.target.obligations[:-1]},
            {"scope":replace(self.target.scope,excerpts=self.target.scope.excerpts[1:])},
            {"draft_input":replace(self.target.draft_input,target_language="zh")},{"context":"Changed context"}):
            with self.subTest(change=tuple(change)): self.rejected(self.result(replace(self.target,**change)))

    def test_review_revocation_old_receipt_replay_and_id_revival_refuse(self):
        self.host.revoke(self.receipt.review_id,reason="Explicit TEST revocation",session=self.sessions.owner)
        self.rejected(self.result())
        self.assertEqual(self.state.audit[-1][0],"REVOKE")
        with self.assertRaises(ValueError): self.seal(self.record)

    def test_key_and_grant_revocation_each_refuse_without_review_revocation(self):
        original=self.state.authority
        for field in ("key_revoked","grant_revoked"):
            self.state.authority=replace(original,**{field:True})
            self.rejected(self.result())
            with self.assertRaises(ValueError): self.seal(dict(self.record,record_id="TEST-NEW"))

    def test_agent_cannot_revoke_or_reuse_review_id(self):
        with self.assertRaises(ValueError): self.host.revoke(self.receipt.review_id,reason="Attempt",session=self.sessions.agent)
        with self.assertRaises(ValueError): self.seal(self.record)
        self.assertEqual(len(self.state.audit),1)

    def test_expiry_and_untrusted_clock_reject(self):
        self.clock.now=NOW+timedelta(hours=1); self.rejected(self.result())
        self.clock.broken=True; self.rejected(self.result())
        self.clock.broken=False; self.clock.now=NOW.replace(tzinfo=None); self.rejected(self.result())

    def test_host_and_client_clock_rollback_reject(self):
        self.assertEqual(self.result().status,es.EvidenceGateStatus.SYNTHETIC_GREEN)
        self.clock.now=NOW-timedelta(seconds=1); self.rejected(self.result())
        with self.assertRaises(ValueError): self.seal(dict(self.record,record_id="TEST-NEW"))

    def test_missing_current_service_or_state_refuse_cached_approval(self):
        self.assertEqual(self.result().status,es.EvidenceGateStatus.SYNTHETIC_GREEN)
        self.transport.broken=True; self.rejected(self.result())
        self.transport.broken=False; self.state.broken=True; self.rejected(self.result())

    def test_forged_registry_proof_tampered_payload_wrong_signing_role_refuse(self):
        for transform in (lambda r:replace(r,proof=b"\0"*384),lambda r:replace(r,payload=r.payload+b" "),
            lambda r:replace(r,proof=self.review_signer.sign(self.anchors.domain("REGISTRY")+r.payload))):
            self.transport.transform=transform; self.rejected(self.result())

    def test_authenticated_server_os_identity_required(self):
        self.transport.transform=lambda r:replace(r,server_sid="FAKE-SERVER"); self.rejected(self.result())

    def test_old_signed_response_challenge_replay_reject(self):
        self.assertEqual(self.result().status,es.EvidenceGateStatus.SYNTHETIC_GREEN)
        old=self.transport.reply; self.transport.transform=lambda _:old; self.rejected(self.result())

    def test_signed_stale_time_wrong_query_binding_and_revision_reject(self):
        self.assertEqual(self.result().status,es.EvidenceGateStatus.SYNTHETIC_GREEN)
        changes=(lambda o:o.update(checked_at=(NOW-timedelta(seconds=6)).isoformat()),
            lambda o:o.update(review_id="WRONG-ID"),lambda o:o.update(challenge="00"*32),
            lambda o:o.update(server_sid="WRONG-SERVER"),lambda o:o["authority"].update(revision=1))
        for change in changes: self.mutate_reply(change); self.rejected(self.result())

    def test_signed_registration_and_authority_wrong_bindings_reject(self):
        fields={"record_sha256":"0"*64,"proof_sha256":"0"*64,"frozen_target_sha256":"0"*64,
            "task_id":"OTHER-TASK","plan_version":2,"evidence_version":2,"reviewer_id":"OTHER-OWNER",
            "purpose":"EXPLAIN","revision":True,"synthetic":False}
        for field,value in fields.items():
            self.mutate_reply(lambda o,f=field,v=value:o["registration"].update({f:v}))
            with self.subTest(field=field): self.rejected(self.result())
        self.mutate_reply(lambda o:o["authority"].update(review_key_fingerprint="0"*64)); self.rejected(self.result())

    def test_changed_grant_project_task_scope_and_expiry_refuse(self):
        original=self.state.authority
        for change in ({"project_id":"OTHER"},{"task_ids":("OTHER",)},{"purposes":("EXPLAIN",)},
            {"valid_until":NOW},{"synthetic":False}):
            self.state.authority=replace(original,principal=replace(original.principal,**change)); self.rejected(self.result())

    def test_register_failure_and_concurrent_grant_revoke_return_no_receipt(self):
        for field in ("fail_register","concurrent_revoke"):
            setattr(self.state,field,True)
            with self.assertRaisesRegex(ValueError,"EXPLICIT_AUTHORIZED_REVIEW_REQUIRED"):
                self.seal(dict(self.record,record_id="TEST-NEW"))
            self.assertNotIn("TEST-NEW",self.state.receipts); self.assertEqual(len(self.state.audit),1)
            setattr(self.state,field,False)

    def test_duplicate_extra_oversized_and_noncanonical_query_refuse(self):
        request=request_payload(self.receipt.review_id,secrets.token_bytes(32))
        for raw in (b"x"*1025,b'{"schema_version":1,"schema_version":1}',request+b" "):
            with self.assertRaises(ValueError): self.host.query_current(raw,self.sessions.agent)
        self.mutate_reply(lambda o:o.update(unexpected=True)); self.rejected(self.result())

    def test_invalid_public_anchor_formats_and_shared_key_roles_refuse(self):
        for key in (b"",self.anchors.review_key.spki+b"x",self.anchors.review_key.spki[:-1]):
            with self.assertRaises(ValueError): RsaPssPublicKey(key)
        with self.assertRaises(ValueError): replace(self.anchors,registry_key=self.anchors.review_key)

    def test_missing_host_roots_and_wrong_signing_key_refuse(self):
        kwargs=dict(anchors=self.anchors,identities=self.sessions,state=self.state,clock=self.clock,
            review_signer=self.review_signer,registry_signer=self.registry_signer)
        for name in kwargs:
            with self.subTest(root=name),self.assertRaises(ValueError):
                EvidenceReviewHost(**dict(kwargs,**{name:None}))
        with self.assertRaises(ValueError): EvidenceReviewHost(**dict(kwargs,review_signer=self.registry_signer))

    def test_key_expiry_and_current_registration_absence_refuse(self):
        original=self.state.authority
        for change in ({"key_valid_until":NOW},{"key_valid_from":NOW+timedelta(seconds=1)}):
            self.state.authority=replace(original,**change); self.rejected(self.result())
        self.state.authority=original
        self.state.registrations.clear(); self.rejected(self.result())

    def test_slow_response_and_client_clock_rollback_during_query_refuse(self):
        for delta in (timedelta(seconds=6),timedelta(seconds=-1)):
            self.clock.now=NOW
            def transform(reply,delta=delta):
                self.clock.now=NOW+delta
                return reply
            self.transport.transform=transform
            self.rejected(self.result(client=self.new_client()))

    def test_fresh_owner_confirmation_window_and_blank_revocation_reason(self):
        calls=self.review_signer.calls
        for reviewed in (NOW-timedelta(minutes=6),NOW+timedelta(seconds=1)):
            with self.assertRaises(ValueError):
                self.seal(dict(self.record,record_id="TEST-NEW",reviewed_at=reviewed.isoformat()))
        self.assertEqual(self.review_signer.calls,calls)
        with self.assertRaises(ValueError): self.host.revoke(self.receipt.review_id,reason=" ",session=self.sessions.owner)
        self.clock.now=NOW+timedelta(seconds=1)
        self.assertEqual(self.seal(dict(self.record,record_id="TEST-NEW")).review_id,"TEST-NEW")

    def test_actual_signing_adapter_rejects_wrong_public_anchor(self):
        from foreign_trade_geo_agent.adapters.evidence_review_signing import BCryptRsaPssSigner
        signer=BCryptRsaPssSigner(key_handle=self.review_signer.key,public_key=self.registry_signer.public_key)
        with self.assertRaisesRegex(ValueError,"HOST_SIGNATURE_FAILED"): signer.sign(b"TEST-only mismatch")

    def test_test_signature_not_accepted_under_production_protocol(self):
        prod=self.new_client(replace(self.anchors,environment=ReviewEnvironment.PRODUCTION))
        self.assertIsNone(prod.authenticate(self.receipt.record,self.receipt.proof,NOW))
        with self.assertRaises(ValueError): isolated_test_preflight(receipt_reader=self.store,client=prod,clock=self.clock)
        self.rejected(production_preflight().check(self.target,self.receipt.review_id))

    def test_production_has_no_injection_or_synthetic_switch_missing_test_roots_refuse(self):
        for kw in ({"client":self.client},{"anchors":self.anchors},{"clock":self.clock},{"allow_synthetic":True}):
            with self.assertRaises(TypeError): production_preflight(**kw)
        for kwargs in ({"receipt_reader":None,"client":self.client,"clock":self.clock},
            {"receipt_reader":self.store,"client":None,"clock":self.clock},
            {"receipt_reader":self.store,"client":self.client,"clock":None}):
            with self.assertRaises(ValueError): isolated_test_preflight(**kwargs)

    def test_real_target_still_unreviewed_refused_writer_zero(self):
        folder=Path(__file__).resolve().parents[1]/"docs/review-packages/evidence-sufficiency-2026-10-08-trusted-preflight"
        target=load_excerpt_target((folder/"frozen-target.json").read_bytes())
        template=json.loads((folder/"review-record.UNSIGNED.template.json").read_bytes())
        self.assertEqual([o["verdict"] for o in template["obligations"]],["NOT_REVIEWED"]*6)
        self.assertEqual([d["verdict"] for d in template["decisions"]],["NOT_REVIEWED"]*7)
        self.rejected(production_preflight().check(target,"REAL-NOT-REVIEWED"))
        with self.assertRaises(ValueError): self.seal(dict(self.record,record_id="TEST-REAL-ATTEMPT"),target=target)
        writer=NoWriter()
        self.assertEqual(asyncio.run(ContentDraftWorkflow(writer).run(target.draft_input)).status,ContentDraftStatus.INVALID_INPUT)
        self.assertEqual(writer.calls,0)
