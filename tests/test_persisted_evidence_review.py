"""Synthetic signed receipts/current registry, real SQLite, never real owner approval."""
from dataclasses import replace
from contextlib import closing
from datetime import timedelta
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from foreign_trade_geo_agent.core import evidence_sufficiency as es
from foreign_trade_geo_agent.adapters.evidence_review import freeze_excerpt_target, draft_input_digest, canonical_bytes
from tests.evidence_review_fixtures import NOW, SyntheticAuthority, synthetic_target, record_for, review_bytes
from tests.test_evidence_sufficiency_preflight import NoWriter
from foreign_trade_geo_agent.workflows.content_draft import ContentDraftWorkflow
from foreign_trade_geo_agent.core.content_draft import ContentDraftStatus
import asyncio


class SyntheticCurrentRegistry:
    """Only tests: state is owned outside receipt DB; no production identity claim."""
    def __init__(self, contract, target, receipt):
        self.contract = contract
        self.calls = 0
        self.unavailable = False
        self.stale_response = False
        self.registration = contract.VerifiedReviewRegistration(
            review_id=receipt.review_id, reviewer_id="SYNTHETIC-OWNER", project_id=target.project_id,
            task_id=target.task_id, task_version=target.task_version, plan_version=target.plan_version,
            evidence_version=target.evidence_version, purpose=target.purpose,
            frozen_target_sha256=hashlib.sha256(receipt.frozen_target).hexdigest(),
            record_sha256=hashlib.sha256(receipt.record).hexdigest(),
            proof_sha256=hashlib.sha256(receipt.proof).hexdigest(), revision=1,
            registered_at=NOW-timedelta(minutes=30), expires_at=NOW+timedelta(hours=1),
            revoked_at=None, status=contract.ReviewRegistrationStatus.ACTIVE,
            challenge=b"", checked_at=NOW, synthetic=True,
        )

    def lookup_current(self, review_id, challenge):
        self.calls += 1
        if self.unavailable:
            raise RuntimeError("SECRET-CANARY")
        if self.registration.review_id != review_id:
            return None
        # Contract assumes authenticated fresh IPC; this in-memory double
        # exercises current-state semantics while actual record HMAC is real.
        return replace(self.registration, challenge=b"old-response" if self.stale_response else challenge)


class PersistedEvidenceReviewTests(unittest.TestCase):
    def setUp(self):
        name = "foreign_trade_geo_agent.workflows.persisted_evidence_review"
        self.assertIsNotNone(importlib.util.find_spec(name), "persistent review preflight is missing")
        self.flow = importlib.import_module(name)
        self.contract = importlib.import_module("foreign_trade_geo_agent.core.evidence_review_registry")
        self.storage = importlib.import_module("foreign_trade_geo_agent.storage.evidence_review_receipts")
        self.adapter = importlib.import_module("foreign_trade_geo_agent.adapters.registered_evidence_review")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/"receipts.sqlite3"
        self.target = synthetic_target(es)
        self.signer = SyntheticAuthority(es, self.target)
        self.record = record_for(self.target, freeze_excerpt_target(self.target), draft_input_digest(self.target.draft_input))
        raw = review_bytes(self.record)
        self.receipt = self.contract.EvidenceReviewReceipt(self.record["record_id"], freeze_excerpt_target(self.target), raw, self.signer.sign(raw))
        self.store = self.storage.SQLiteEvidenceReviewReceipts.create(self.path)
        self.store.append(self.receipt)
        self.registry = SyntheticCurrentRegistry(self.contract, self.target, self.receipt)
        self.loader = self.adapter.RegisteredEvidenceReviewLoader(
            receipt_reader=self.store, authenticator=self.signer, registry=self.registry)
        self.gate = self.flow.PersistedEvidenceSufficiencyPreflight(
            review_loader=self.loader, allow_synthetic=True, clock=lambda: NOW)

    def result(self, *, target=None, review_id=None, gate=None):
        return (gate or self.gate).check(target or self.target, review_id or self.receipt.review_id)

    def rejected(self, result, target=None):
        self.assertEqual(result.status, es.EvidenceGateStatus.REJECTED)
        self.assertNotIn("SECRET-CANARY", result.reason)
        writer = NoWriter()
        draft = asyncio.run(ContentDraftWorkflow(writer).run((target or self.target).draft_input))
        self.assertEqual(draft.status, ContentDraftStatus.INVALID_INPUT)
        self.assertEqual(writer.calls, 0)

    def sql(self, command, args=()):
        with closing(sqlite3.connect(self.path)) as conn:
            with conn:
                if command.startswith("UPDATE "):
                    conn.execute("DROP TRIGGER IF EXISTS receipt_no_update")
                if command.startswith("DELETE "):
                    conn.execute("DROP TRIGGER IF EXISTS receipt_no_delete")
                conn.execute(command, args)
                # Restore cache safeguards after deliberate byte tampering so
                # crypto/current-state tests reach their intended trust boundary.
                if command.startswith(("UPDATE ", "DELETE ")):
                    for name, sql in self.storage._TRIGGERS.items():
                        if conn.execute("SELECT 1 FROM sqlite_schema WHERE name=?", (name,)).fetchone() is None:
                            conn.execute(sql)

    def test_signed_receipt_survives_reopen_and_reauthenticates_each_preflight(self):
        reopened = self.storage.SQLiteEvidenceReviewReceipts(self.path)
        self.assertEqual(reopened.get_receipt(self.receipt.review_id), self.receipt)
        self.loader = self.adapter.RegisteredEvidenceReviewLoader(
            receipt_reader=reopened, authenticator=self.signer, registry=self.registry)
        gate = self.flow.PersistedEvidenceSufficiencyPreflight(
            review_loader=self.loader, allow_synthetic=True, clock=lambda: NOW)
        self.assertEqual(self.result(gate=gate).status, es.EvidenceGateStatus.SYNTHETIC_GREEN)
        self.assertEqual(self.result(gate=gate).status, es.EvidenceGateStatus.SYNTHETIC_GREEN)
        self.assertEqual(self.registry.calls, 2)  # read-only active recheck is idempotent
        writer = NoWriter()
        self.assertEqual(asyncio.run(ContentDraftWorkflow(writer).run(self.target.draft_input)).status,
                         ContentDraftStatus.INVALID_INPUT)
        self.assertEqual(writer.calls, 0)
        self.signer.revoked = True
        self.rejected(self.result(gate=gate))

    def test_default_production_mode_and_missing_dependencies_reject(self):
        self.rejected(self.result(gate=self.flow.PersistedEvidenceSufficiencyPreflight(clock=lambda: NOW)))
        self.rejected(self.result(gate=self.flow.PersistedEvidenceSufficiencyPreflight(
            review_loader=self.loader, clock=lambda: NOW)))
        for kwargs in ({"receipt_reader": self.store, "authenticator": self.signer},
                       {"receipt_reader": self.store, "registry": self.registry},
                       {"authenticator": self.signer, "registry": self.registry}):
            loader = self.adapter.RegisteredEvidenceReviewLoader(**kwargs)
            self.rejected(self.result(gate=self.flow.PersistedEvidenceSufficiencyPreflight(
                review_loader=loader, allow_synthetic=True, clock=lambda: NOW)))

    def test_duplicate_id_append_never_overwrites_original(self):
        with self.assertRaises(ValueError): self.store.append(self.receipt)
        with self.assertRaises(ValueError): self.store.append(replace(self.receipt, record=b"forged"))
        self.assertEqual(self.store.get_receipt(self.receipt.review_id), self.receipt)
        self.assertEqual(self.result().status, es.EvidenceGateStatus.SYNTHETIC_GREEN)

    def test_read_only_lookup_does_not_write_or_create_missing_db(self):
        before = self.path.read_bytes()
        self.assertEqual(self.store.get_receipt(self.receipt.review_id), self.receipt)
        self.assertIsNone(self.store.get_receipt("unknown"))
        self.assertEqual(self.path.read_bytes(), before)
        absent = Path(self.temp.name)/"absent.sqlite3"
        with self.assertRaises(ValueError): self.storage.SQLiteEvidenceReviewReceipts(absent)
        self.assertFalse(absent.exists())
        with self.assertRaises(ValueError): self.storage.SQLiteEvidenceReviewReceipts.create(self.path)
        self.assertEqual(self.path.read_bytes(), before)

    def test_cache_creation_closes_all_connections_before_return(self):
        connections=[]
        original=sqlite3.connect
        class Tracked(sqlite3.Connection):
            closed=False
            def close(self):
                self.closed=True
                super().close()
        def connect(*args,**kwargs):
            conn=original(*args,**kwargs,factory=Tracked)
            connections.append(conn)
            return conn
        with patch("sqlite3.connect",side_effect=connect):
            self.storage.SQLiteEvidenceReviewReceipts.create(Path(self.temp.name)/"close-check.sqlite3")
        try:
            self.assertTrue(all(c.closed for c in connections),"cache creation leaked an SQLite connection")
        finally:
            for conn in connections: conn.close()

    def test_history_db_is_rejected_without_schema_change(self):
        history = Path(self.temp.name)/"history.sqlite3"
        with closing(sqlite3.connect(history)) as conn:
            with conn:
                conn.execute("CREATE TABLE runs(id TEXT PRIMARY KEY)")
                conn.execute("PRAGMA user_version=4")
        before = history.read_bytes()
        with self.assertRaises(ValueError): self.storage.SQLiteEvidenceReviewReceipts(history)
        self.assertEqual(history.read_bytes(), before)

    def test_untrusted_schema_objects_and_changed_trigger_are_rejected(self):
        original = self.path.read_bytes()
        mutations = (
            "CREATE TRIGGER infinite_append AFTER INSERT ON review_receipts BEGIN "
            "WITH RECURSIVE spin(n) AS (VALUES(1) UNION ALL SELECT n+1 FROM spin) SELECT n FROM spin; END",
            "CREATE VIEW unexpected AS SELECT * FROM review_receipts",
            "CREATE INDEX unexpected ON review_receipts(record)",
            "DROP TRIGGER receipt_no_update",
        )
        for sql in mutations:
            with self.subTest(sql=sql.split()[1:3]):
                self.path.write_bytes(original)
                self.sql(sql)
                if sql.startswith("DROP "):
                    self.sql("CREATE TRIGGER receipt_no_update BEFORE UPDATE ON review_receipts BEGIN SELECT 1; END")
                with self.assertRaises(ValueError):
                    self.storage.SQLiteEvidenceReviewReceipts(self.path)
                self.rejected(self.result())
                with self.assertRaises(ValueError): self.store.append(self.receipt)

    def test_sqlite_vm_execution_has_finite_budget(self):
        installed = []
        original = sqlite3.connect
        class Tracked(sqlite3.Connection):
            def set_progress_handler(self, callback, steps):
                installed.append((callback, steps))
                super().set_progress_handler(callback, steps)
        def connect(*args, **kwargs):
            return original(*args, **kwargs, factory=Tracked)
        with patch("sqlite3.connect", side_effect=connect):
            with self.store._connect() as conn:
                self.assertTrue(installed, "untrusted SQLite has no VM execution budget")
                # This recursive query cannot finish without the execution guard.
                with self.assertRaises(sqlite3.DatabaseError):
                    conn.execute("WITH RECURSIVE spin(n) AS (VALUES(1) UNION ALL SELECT n+1 FROM spin) "
                                 "SELECT sum(n) FROM spin").fetchone()

    def test_schema_cannot_change_between_validation_and_append(self):
        with self.store._connect(writable=True) as protected:
            self.store._validate_schema(protected)
            with closing(sqlite3.connect(self.path, timeout=0)) as attacker:
                with self.assertRaises(sqlite3.OperationalError):
                    attacker.execute("CREATE TRIGGER race_append AFTER INSERT ON review_receipts "
                                     "BEGIN SELECT 1; END")
        self.assertEqual(self.store.get_receipt(self.receipt.review_id), self.receipt)

    def test_db_record_tamper_is_rejected_even_after_local_digest_recompute(self):
        self.sql("DROP TRIGGER receipt_no_update")
        changed = dict(self.record); changed["signoff"] = "NOT_REVIEWED"
        raw = review_bytes(changed)
        self.sql("UPDATE review_receipts SET record=? WHERE review_id=?", (raw, self.receipt.review_id))
        self.rejected(self.result())
        # Even a new cryptographically valid test signature is insufficient
        # without current out-of-DB registration of those exact bytes.
        changed["signoff"] = "APPROVED"; changed["reviewed_at"] = "2026-10-08T03:01:00Z"
        raw = review_bytes(changed)
        self.sql("UPDATE review_receipts SET record=?, proof=? WHERE review_id=?",
                 (raw, self.signer.sign(raw), self.receipt.review_id))
        self.rejected(self.result())

    def test_db_proof_and_frozen_target_tamper_reject(self):
        self.sql("DROP TRIGGER receipt_no_update")
        self.sql("UPDATE review_receipts SET proof=?", (b"fake-proof",))
        self.rejected(self.result())
        self.sql("UPDATE review_receipts SET proof=?", (self.receipt.proof,))
        frozen = json.loads(self.receipt.frozen_target)
        frozen["draft_input"]["target_language"] = "zh"
        self.sql("UPDATE review_receipts SET frozen_target=?", (canonical_bytes(frozen),))
        self.rejected(self.result())

    def test_db_delete_or_unknown_receipt_rejects(self):
        self.rejected(self.result(review_id="unknown"))
        self.sql("DROP TRIGGER receipt_no_delete")
        self.sql("DELETE FROM review_receipts")
        self.rejected(self.result())

    def test_local_database_approval_flag_cannot_authorize(self):
        self.sql("ALTER TABLE review_receipts ADD COLUMN approved INTEGER DEFAULT 1")
        self.registry.registration = replace(self.registry.registration,
            status=self.contract.ReviewRegistrationStatus.REVOKED, revoked_at=NOW, revision=2)
        self.rejected(self.result())

    def test_revocation_and_old_database_backup_replay_reject(self):
        backup = Path(self.temp.name)/"old-backup.sqlite3"
        shutil.copyfile(self.path, backup)
        self.assertEqual(self.result().status, es.EvidenceGateStatus.SYNTHETIC_GREEN)
        self.registry.registration = replace(self.registry.registration,
            status=self.contract.ReviewRegistrationStatus.REVOKED, revoked_at=NOW, revision=2)
        reopened = self.storage.SQLiteEvidenceReviewReceipts(backup)
        loader = self.adapter.RegisteredEvidenceReviewLoader(receipt_reader=reopened,
            authenticator=self.signer, registry=self.registry)
        gate = self.flow.PersistedEvidenceSufficiencyPreflight(review_loader=loader,
            allow_synthetic=True, clock=lambda: NOW)
        self.rejected(self.result(gate=gate))
        self.rejected(self.result())

    def test_superseded_record_same_id_and_stale_registry_response_reject(self):
        original = self.registry.registration
        self.registry.registration = replace(original, record_sha256="0"*64, revision=2)
        self.rejected(self.result())
        self.registry.registration = original
        self.registry.stale_response = True
        self.rejected(self.result())
        self.registry.stale_response = False
        self.registry.registration = replace(original, checked_at=NOW-timedelta(seconds=6))
        self.rejected(self.result())

    def test_registry_unavailable_missing_or_malformed_is_fail_closed(self):
        self.registry.unavailable = True
        self.rejected(self.result())
        self.registry.unavailable = False
        original = self.registry.registration
        for change in ({"review_id":"unregistered"}, {"revision":0}, {"revision":True},
                       {"status":"ACTIVE"}, {"synthetic":False}, {"registered_at":NOW+timedelta(seconds=1)},
                       {"expires_at":NOW}, {"revoked_at":NOW}, {"checked_at":NOW.replace(tzinfo=None)}):
            self.registry.registration = replace(original, **change)
            with self.subTest(change=tuple(change)): self.rejected(self.result())

    def test_registry_identity_project_task_versions_and_digests_must_match(self):
        original = self.registry.registration
        for change in ({"reviewer_id":"other-owner"}, {"project_id":"other-project"},
                       {"task_id":"EXPLAIN-old-task"}, {"task_version":2}, {"plan_version":2},
                       {"evidence_version":2}, {"purpose":"EXPLAIN"}, {"frozen_target_sha256":"0"*64},
                       {"record_sha256":"0"*64}, {"proof_sha256":"0"*64}):
            self.registry.registration = replace(original, **change)
            with self.subTest(change=tuple(change)): self.rejected(self.result())

    def test_target_task_span_plan_obligation_input_changes_require_new_review(self):
        scope = self.target.scope
        for change in ({"question":"Explain equipment choices"}, {"plan_version":2}, {"evidence_version":2},
                       {"task_id":"other-task"}, {"obligations":self.target.obligations[:-1]},
                       {"scope":replace(scope, excerpts=scope.excerpts[1:])},
                       {"draft_input":replace(self.target.draft_input,target_language="zh")}):
            target = replace(self.target, **change)
            with self.subTest(change=tuple(change)): self.rejected(self.result(target=target),target)

    def test_signed_identity_change_or_cross_task_registration_does_not_authorize(self):
        self.sql("DROP TRIGGER receipt_no_update")
        for field, value in (("reviewer_id","other-owner"), ("task_id","EXPLAIN-old-task")):
            record=dict(self.record); record[field]=value; raw=review_bytes(record)
            self.sql("UPDATE review_receipts SET record=?, proof=?", (raw,self.signer.sign(raw)))
            self.rejected(self.result())

    def test_unreviewed_or_partial_signed_receipt_still_rejects(self):
        self.sql("DROP TRIGGER receipt_no_update")
        for variant in ("NOT_REVIEWED","partial"):
            record=json.loads(review_bytes(self.record))
            if variant=="partial": record["obligations"].pop()
            else: record["obligations"][0]["verdict"]=variant
            raw=review_bytes(record)
            self.sql("UPDATE review_receipts SET record=?, proof=?", (raw,self.signer.sign(raw)))
            self.registry.registration=replace(self.registry.registration,
                record_sha256=hashlib.sha256(raw).hexdigest(),proof_sha256=hashlib.sha256(self.signer.sign(raw)).hexdigest())
            self.rejected(self.result())

    def test_expired_signed_review_and_invalid_trusted_clock_reject(self):
        for now in (NOW+timedelta(hours=1),NOW.replace(tzinfo=None)):
            gate=self.flow.PersistedEvidenceSufficiencyPreflight(review_loader=self.loader,
                allow_synthetic=True,clock=lambda:now)
            self.rejected(self.result(gate=gate))
        class BrokenClock:
            def __call__(self): raise RuntimeError("SECRET-CANARY")
        self.rejected(self.result(gate=self.flow.PersistedEvidenceSufficiencyPreflight(
            review_loader=self.loader,allow_synthetic=True,clock=BrokenClock())))

    def test_receipt_bounds_and_malformed_storage_values_reject(self):
        for kwargs in ({"record":b"x"*16385},{"proof":b"x"*4097},{"frozen_target":b"x"*131073},
                       {"record":"not-bytes"},{"review_id":"../bad"}):
            with self.subTest(field=tuple(kwargs)):
                with self.assertRaises(ValueError): replace(self.receipt,**kwargs)
        self.sql("DROP TRIGGER receipt_no_update")
        self.sql("UPDATE review_receipts SET proof='text-not-blob'")
        self.rejected(self.result())

    def test_real_six_obligations_are_not_registered_or_signed(self):
        from foreign_trade_geo_agent.adapters.evidence_review import load_excerpt_target
        folder=Path(__file__).resolve().parents[1]/"docs/review-packages/evidence-sufficiency-2026-10-08-trusted-preflight"
        target=load_excerpt_target((folder/"frozen-target.json").read_bytes())
        template=json.loads((folder/"review-record.UNSIGNED.template.json").read_bytes())
        self.assertEqual([o["verdict"] for o in template["obligations"]],["NOT_REVIEWED"]*6)
        self.rejected(self.flow.PersistedEvidenceSufficiencyPreflight().check(target,"real-pending"),target)
