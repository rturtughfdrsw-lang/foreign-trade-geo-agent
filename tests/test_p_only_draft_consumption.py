"""Isolated TEST execution: ephemeral PSS, local copy generator, no network/LLM/CMS."""
import asyncio
from dataclasses import replace
from datetime import timedelta
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from foreign_trade_geo_agent.core import content_draft as cd, evidence_sufficiency as es
from foreign_trade_geo_agent.core import change_plan as cp
from foreign_trade_geo_agent.core.p_only_draft import (
    POnlyDraftRequestV1, material_for, output_digest, verify_coverage_proof, p_only_draft_target_error,
)
from foreign_trade_geo_agent.core.first_party_planning import FirstPartyExcerpt, FirstPartyPlanningScope
from foreign_trade_geo_agent.adapters.evidence_review import (
    freeze_excerpt_target, draft_input_digest, canonical_bytes,
)
from foreign_trade_geo_agent.adapters.evidence_review_client import EvidenceReviewClient
from foreign_trade_geo_agent.adapters.evidence_review_host import EvidenceReviewHost
from foreign_trade_geo_agent.adapters._evidence_review_protocol import ReviewEnvironment
from foreign_trade_geo_agent.adapters.p_only_draft import FrozenPOnlyDraftConsumer, DeterministicExcerptDraftGenerator
from foreign_trade_geo_agent.adapters.registered_evidence_review import RegisteredEvidenceReviewLoader
from foreign_trade_geo_agent.storage.evidence_review_receipts import SQLiteEvidenceReviewReceipts
from foreign_trade_geo_agent.evidence_review_composition import (
    isolated_test_p_only_draft, production_p_only_draft, isolated_test_preflight,
)
from foreign_trade_geo_agent.workflows.content_draft import ContentDraftWorkflow
from tests.evidence_review_fixtures import NOW, synthetic_target, record_for, review_bytes
from tests.evidence_review_host_fixtures import (
    EphemeralTestSigner, TestClock, MockSessions, TestAuthorityState, LoopbackTestTransport, test_anchors,
)
from tests.test_evidence_sufficiency_preflight import NoWriter
from tests.test_first_party_excerpt_capacity import native_planning


class TransformGenerator:
    def __init__(self, transform):
        self.transform, self.calls = transform, 0

    def generate(self, material):
        self.calls += 1
        return self.transform(DeterministicExcerptDraftGenerator().generate(material))


@unittest.skipUnless(sys.platform == "win32", "TEST PSS fixture requires Windows BCrypt")
class POnlyDraftConsumptionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.signer, cls.registry_signer = EphemeralTestSigner(), EphemeralTestSigner()
        cls.addClassCleanup(cls.signer.close)
        cls.addClassCleanup(cls.registry_signer.close)

    def setUp(self):
        self.target = replace(synthetic_target(es), purpose=es.P_ONLY_DRAFT_PURPOSE_V1,
                              output_constraints=es.P_ONLY_DRAFT_CONSTRAINTS_V1)
        self.anchors = test_anchors(self.signer, self.registry_signer)
        self.clock = TestClock()
        self.sessions = MockSessions(self.anchors)
        self.state = TestAuthorityState(self.anchors, self.target)
        self.host = EvidenceReviewHost(anchors=self.anchors, identities=self.sessions, state=self.state,
            clock=self.clock, review_signer=self.signer, registry_signer=self.registry_signer)
        self.transport = LoopbackTestTransport(self.host, self.sessions)
        self.client = EvidenceReviewClient(anchors=self.anchors, transport=self.transport, clock=self.clock)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = SQLiteEvidenceReviewReceipts.create(Path(self.temp.name)/"test-draft-receipts.sqlite3")
        self.record = record_for(self.target, freeze_excerpt_target(self.target), draft_input_digest(self.target.draft_input))
        self.record.update(purpose=self.target.purpose, reviewer_id=self.anchors.reviewer_sid,
            record_id="TEST-DRAFT-CONSUMPTION-001", reviewed_at=NOW.isoformat(),
            decisions=[{"decision_id": d, "verdict": "APPROVED", "reason": "Explicit synthetic TEST Draft permission."}
                       for d in es.P_ONLY_DRAFT_DECISIONS_V1])
        self.receipt = self.seal(self.target, self.record)
        self.store.append(self.receipt)
        self.request = POnlyDraftRequestV1(self.receipt.frozen_target, self.receipt.review_id)
        self.loader = RegisteredEvidenceReviewLoader(receipt_reader=self.store, authenticator=self.client, registry=self.client)
        self.consumer = FrozenPOnlyDraftConsumer(review_loader=self.loader, clock=self.clock)
        self.writer = NoWriter()
        self.workflow = ContentDraftWorkflow(self.writer, p_only_consumer=self.consumer,
                                             p_only_generator=DeterministicExcerptDraftGenerator())

    def seal(self, target, record, *, method=None):
        frozen, raw = freeze_excerpt_target(target), review_bytes(record)
        return (method or self.host.seal_test_draft)(target, raw, session=self.sessions.owner,
            confirmation=hashlib.sha256(self.anchors.domain("CONFIRM")+frozen+raw).digest())

    def run_draft(self, request=None, workflow=None):
        return asyncio.run((workflow or self.workflow).run_p_only(request or self.request))

    def rejected(self, result):
        self.assertNotEqual(result.report.status, cd.ContentDraftStatus.SUCCESS)
        self.assertEqual(result.report.drafts, ())
        self.assertIsNone(result.body)
        self.assertIsNone(result.coverage_proof)
        self.assertNotIn("SECRET-CANARY", result.reason)
        self.assertEqual(self.writer.calls, 0)

    def test_complete_independent_authorization_executes_same_workflow_and_covers_all_spans(self):
        result = self.run_draft()
        self.assertEqual(result.report.status, cd.ContentDraftStatus.SUCCESS, result.reason)
        self.assertEqual(self.writer.calls, 0)
        self.assertEqual(result.environment, "TEST")
        self.assertTrue(result.report.requires_human_review)
        self.assertEqual(result.body, "\n".join((self.target.context, self.target.attribution,
            *(o.statement for o in self.target.obligations))))
        proof = result.coverage_proof
        self.assertEqual(tuple(c.obligation_id for c in proof.coverage), tuple(f"O{i}" for i in range(1, 7)))
        self.assertEqual(sum(len(c.spans) for c in proof.coverage), 7)
        first, second = proof.coverage[0].spans
        self.assertEqual(first[4], second[3])
        self.assertEqual(first[5]+second[5], self.target.obligations[0].statement)
        self.assertEqual(proof.output_sha256, output_digest(result.report, result.body))
        execution = self.consumer.prepare(self.request)
        review = self.consumer.revalidate(execution)
        self.assertTrue(verify_coverage_proof(execution, review, result.report, result.body, proof))
        self.assertEqual(proof.frozen_target_sha256, hashlib.sha256(self.request.frozen_target).hexdigest())
        self.assertEqual(proof.draft_input_sha256, draft_input_digest(self.target.draft_input))
        self.assertGreaterEqual(self.transport.calls, 4)  # current identity + registration before/after

    def test_explicit_test_composition_positive_and_production_entry_locked(self):
        flow = isolated_test_p_only_draft(receipt_reader=self.store, client=self.client, clock=self.clock)
        self.assertEqual(self.run_draft(workflow=flow).report.status, cd.ContentDraftStatus.SUCCESS)
        calls = self.transport.calls
        self.rejected(self.run_draft(workflow=production_p_only_draft()))
        self.rejected(self.run_draft(workflow=ContentDraftWorkflow(self.writer)))
        self.assertEqual(self.transport.calls, calls)
        with self.assertRaises(TypeError):
            production_p_only_draft(client=self.client)
        with self.assertRaises(ValueError):
            isolated_test_p_only_draft(receipt_reader=self.store, client=object(), clock=self.clock)
        production_client = EvidenceReviewClient(anchors=replace(self.anchors, environment=ReviewEnvironment.PRODUCTION),
            transport=self.transport, clock=self.clock)
        with self.assertRaises(ValueError):
            isolated_test_p_only_draft(receipt_reader=self.store, client=production_client, clock=self.clock)
        self.assertIsNone(production_client.authenticate(self.receipt.record, self.receipt.proof, NOW))

    def test_plain_run_and_prompt_still_require_original_p_s_rules(self):
        report = asyncio.run(self.workflow.run(self.target.draft_input))
        self.assertEqual(report.status, cd.ContentDraftStatus.INVALID_INPUT)
        self.assertEqual(self.writer.calls, 0)
        with self.assertRaises(ValueError):
            cd.build_content_draft_prompt(self.target.draft_input, "C1")
        self.assertIsNone(cd.stable_content_draft_input_error(self.target.draft_input,
            first_party_scope=self.target.scope, task_id=self.target.task_id))
        self.assertEqual(cd.stable_content_draft_input_error(self.target.draft_input), "FIELD_CONTRACT")

    def test_old_offline_green_cannot_execute_draft_and_seal_routes_are_separate(self):
        offline = synthetic_target(es)
        self.state.authority = replace(self.state.authority, principal=replace(self.state.authority.principal,
            purposes=(es.OFFLINE_EXCERPT_PURPOSE, es.P_ONLY_DRAFT_PURPOSE_V1)))
        old_record = record_for(offline, freeze_excerpt_target(offline), draft_input_digest(offline.draft_input))
        old_record.update(reviewer_id=self.anchors.reviewer_sid, reviewed_at=NOW.isoformat())
        receipt = self.seal(offline, old_record, method=self.host.seal)
        self.store.append(receipt)
        gate = isolated_test_preflight(receipt_reader=self.store, client=self.client, clock=self.clock)
        self.assertEqual(gate.check(offline, receipt.review_id).status, es.EvidenceGateStatus.SYNTHETIC_GREEN)
        self.rejected(self.run_draft(POnlyDraftRequestV1(receipt.frozen_target, receipt.review_id)))
        self.rejected(self.run_draft(POnlyDraftRequestV1(self.request.frozen_target, receipt.review_id)))
        with self.assertRaises(ValueError): self.seal(self.target, self.record, method=self.host.seal)
        with self.assertRaises(ValueError): self.seal(offline, old_record)
        self.assertEqual(gate.check(self.target, self.request.review_id).status, es.EvidenceGateStatus.REJECTED)

    def test_missing_decisions_and_obligations_are_not_automatic_signoff(self):
        for changed in (dict(self.record, decisions=self.record["decisions"][:-1]),
                        dict(self.record, obligations=self.record["obligations"][:-1]),
                        dict(self.record, signoff="NOT_REVIEWED"),
                        dict(self.record, purpose="EXPLAIN"),
                        dict(self.record, decisions=[dict(d, verdict="NOT_REVIEWED") for d in self.record["decisions"]])):
            with self.subTest(changed=tuple(changed)):
                with self.assertRaises(ValueError): self.seal(self.target, changed)

    def test_output_omission_fragment_reorder_extra_fact_wrong_refs_and_wrappers_reject(self):
        base = DeterministicExcerptDraftGenerator().generate(material_for(self.target))
        claims = tuple(c for b in base.specification.blocks for c in b.claims)
        variants = {
            "missing five": claims[:1], "missing one": claims[:-1],
            "O1 half": (replace(claims[0], text=self.target.scope.excerpts[0].quote), *claims[1:]),
            "O1 reversed spans": (replace(claims[0], text=self.target.scope.excerpts[1].quote+self.target.scope.excerpts[0].quote), *claims[1:]),
            "reverse obligations": tuple(reversed(claims)), "duplicate": (claims[0], *claims[:-1]),
            "new nonnumeric fact": (*claims, replace(claims[0], text="Packing orientation determines weather protection.")),
            "changed whitespace": (replace(claims[0], text=claims[0].text.replace(" ", "  ", 1)), *claims[1:]),
            "wrong page": (replace(claims[0], page_refs=("P99",)), *claims[1:]),
            "source attached": (replace(claims[0], source_refs=("S1",)), *claims[1:]),
            "empty source": (replace(claims[0], page_refs=()), *claims[1:]),
            "explanation": (replace(claims[0], text="This means delivery planning needs packing information."), *claims[1:]),
            "wrong claim type": (replace(claims[0], claim_type=cd.DraftClaimType.CALL_TO_ACTION), *claims[1:]),
        }
        for name, items in variants.items():
            with self.subTest(name=name):
                def transform(output):
                    return replace(output, specification=replace(output.specification, blocks=tuple(
                        cd.ParagraphSpecification(cd.DraftBlockKind.PARAGRAPH, items[i:i+4])
                        for i in range(0, len(items), 4))))
                flow = ContentDraftWorkflow(self.writer, p_only_consumer=self.consumer,
                    p_only_generator=TransformGenerator(transform))
                self.rejected(self.run_draft(workflow=flow))
        for name, transform in (
            ("context", lambda o: replace(o, context="Commercially approved")),
            ("attribution", lambda o: replace(o, attribution="Other source")),
            ("CTA field", lambda o: replace(o, specification=replace(o.specification, anchor_text="Buy now"))),
            ("invalid type", lambda o: {"approved": True}),
        ):
            with self.subTest(name=name):
                self.rejected(self.run_draft(workflow=ContentDraftWorkflow(self.writer, p_only_consumer=self.consumer,
                    p_only_generator=TransformGenerator(transform))))

    def test_final_output_rechecked_after_generic_finalizer(self):
        original = self.workflow._finalize
        def changed(number, spec, operation, value):
            draft, error = original(number, spec, operation, value)
            block = draft.blocks[0]
            return replace(draft, blocks=(replace(block, claims=(replace(block.claims[0], text="Other fact."),
                *block.claims[1:])), *draft.blocks[1:])), error
        with patch.object(self.workflow, "_finalize", side_effect=changed):
            self.rejected(self.run_draft())

    def test_semantics_rechecked_even_when_forged_output_digest_matches(self):
        result = self.run_draft()
        self.assertEqual(result.report.status, cd.ContentDraftStatus.SUCCESS)
        execution = self.consumer.prepare(self.request)
        review = self.consumer.revalidate(execution)
        draft = result.report.drafts[0]
        incomplete = replace(result.report, drafts=(replace(draft, blocks=draft.blocks[:1]),))
        body = "\n".join((self.target.context, self.target.attribution,
                         *(c.text for c in draft.blocks[0].claims)))
        proof = replace(result.coverage_proof, output_sha256=output_digest(incomplete, body))
        self.assertFalse(verify_coverage_proof(execution, review, incomplete, body, proof))
        wrong = replace(result.coverage_proof.coverage[0], spans=result.coverage_proof.coverage[1].spans)
        self.assertFalse(verify_coverage_proof(execution, review, result.report, result.body,
            replace(result.coverage_proof, coverage=(wrong, *result.coverage_proof.coverage[1:]))))
        self.assertFalse(verify_coverage_proof(execution, review, result.report, result.body,
            replace(result.coverage_proof, output_sha256="0"*64)))

    def test_frozen_task_plan_evidence_input_and_scope_changes_reject_before_generation(self):
        value = self.target.draft_input
        operation = value.change_plan_report.operations[0]
        summarized = replace(operation, content_points=tuple(replace(p, intent=cp.ContentPointIntent.SUMMARIZE)
                                                            for p in operation.content_points))
        changes = (
            replace(self.target, task_id="DIFFERENT-TASK"),
            replace(self.target, project_id="DIFFERENT-PROJECT"),
            *(replace(self.target, **{field: 2}) for field in ("task_version", "plan_version", "evidence_version")),
            replace(self.target, context="Changed context"), replace(self.target, attribution="Changed attribution"),
            replace(self.target, draft_input=replace(value, target_language="zh")),
            replace(self.target, obligations=self.target.obligations[:-1]),
            replace(self.target, draft_input=replace(value, change_plan_report=replace(value.change_plan_report,
                                                                                     operations=(summarized,)))),
            replace(self.target, output_constraints=es.EXCERPT_OUTPUT_CONSTRAINTS),
        )
        for target in changes:
            with self.subTest(target=target.task_id, versions=(target.task_version,target.plan_version,target.evidence_version)):
                generator = TransformGenerator(lambda o: o)
                self.rejected(self.run_draft(POnlyDraftRequestV1(freeze_excerpt_target(target), self.request.review_id),
                    ContentDraftWorkflow(self.writer, p_only_consumer=self.consumer, p_only_generator=generator)))
                self.assertEqual(generator.calls, 0)

    def test_editable_frozen_json_and_unsigned_records_never_authorize(self):
        for raw in (self.request.frozen_target+b" ", b'{"approved":true}',
                    self.request.frozen_target.replace(b'"schema_version":1', b'"schema_version":2', 1)):
            self.rejected(self.run_draft(POnlyDraftRequestV1(raw, self.request.review_id)))
        for key, replacement in (("record", self.receipt.record+b" "), ("proof", b"fake")):
            class Reader:
                def get_receipt(inner, review_id):
                    return replace(self.receipt, **{key: replacement})
            loader = RegisteredEvidenceReviewLoader(receipt_reader=Reader(), authenticator=self.client, registry=self.client)
            flow = ContentDraftWorkflow(self.writer, p_only_consumer=FrozenPOnlyDraftConsumer(review_loader=loader, clock=self.clock),
                p_only_generator=DeterministicExcerptDraftGenerator())
            self.rejected(self.run_draft(workflow=flow))

    def test_current_permission_key_grant_review_revocation_expiry_and_unavailability_reject(self):
        authority = self.state.authority
        registration = self.state.registrations[self.request.review_id]
        mutations = (
            lambda: setattr(self.state, "authority", replace(authority, key_revoked=True)),
            lambda: setattr(self.state, "authority", replace(authority, grant_revoked=True)),
            lambda: setattr(self.state, "authority", replace(authority, key_valid_until=NOW)),
            lambda: setattr(self.state, "authority", replace(authority, principal=replace(authority.principal, purposes=(es.OFFLINE_EXCERPT_PURPOSE,)))),
            lambda: setattr(self.state, "authority", replace(authority, principal=replace(authority.principal, task_ids=("OTHER-TASK",)))),
            lambda: setattr(self.state, "authority", replace(authority, principal=replace(authority.principal, valid_until=NOW))),
            lambda: self.host.revoke(self.request.review_id, reason="TEST revocation", session=self.sessions.owner),
            lambda: self.state.registrations.update({self.request.review_id: replace(registration, expires_at=NOW)}),
            lambda: self.state.registrations.clear(),
            lambda: setattr(self.transport, "broken", True),
        )
        for i, mutation in enumerate(mutations):
            with self.subTest(mutation=i):
                self.state.authority = authority
                self.state.registrations[self.request.review_id] = registration
                self.transport.broken = False
                mutation()
                generator = TransformGenerator(lambda o:o)
                self.rejected(self.run_draft(workflow=ContentDraftWorkflow(self.writer, p_only_consumer=self.consumer,
                    p_only_generator=generator)))
                self.assertEqual(generator.calls, 0)

    def test_repeated_execution_reauthenticates_and_then_rejects_revocation(self):
        self.assertEqual(self.run_draft().report.status, cd.ContentDraftStatus.SUCCESS)
        calls = self.transport.calls
        self.assertEqual(self.run_draft().report.status, cd.ContentDraftStatus.SUCCESS)
        self.assertGreaterEqual(self.transport.calls, calls+4)
        self.host.revoke(self.request.review_id, reason="TEST revoke", session=self.sessions.owner)
        self.rejected(self.run_draft())

    def test_revoked_during_generation_never_delivers_output(self):
        def transform(o):
            self.host.revoke(self.request.review_id, reason="TEST in-flight revoke", session=self.sessions.owner)
            return o
        self.rejected(self.run_draft(workflow=ContentDraftWorkflow(self.writer, p_only_consumer=self.consumer,
            p_only_generator=TransformGenerator(transform))))

    def test_expired_during_generation_never_delivers_output(self):
        def transform(o):
            self.clock.now = NOW+timedelta(hours=2)
            return o
        self.rejected(self.run_draft(workflow=ContentDraftWorkflow(self.writer, p_only_consumer=self.consumer,
            p_only_generator=TransformGenerator(transform))))

    def test_request_replaced_after_authorization_rejects_and_cannot_replace_private_input(self):
        def transform(o):
            object.__setattr__(self.request, "frozen_target", freeze_excerpt_target(replace(self.target, context="Replaced")))
            return o
        self.rejected(self.run_draft(workflow=ContentDraftWorkflow(self.writer, p_only_consumer=self.consumer,
            p_only_generator=TransformGenerator(transform))))

    def test_caller_target_is_never_executed_after_freezing(self):
        object.__setattr__(self.target.draft_input, "target_language", "zh")
        result = self.run_draft()
        self.assertEqual(result.report.status, cd.ContentDraftStatus.SUCCESS)
        self.assertEqual(result.coverage_proof.draft_input_sha256,
            draft_input_digest(self.consumer.prepare(self.request).target.draft_input))
        self.assertNotEqual(result.coverage_proof.draft_input_sha256, draft_input_digest(self.target.draft_input))

    def test_signed_stale_registration_response_replay_rejects(self):
        self.assertEqual(self.run_draft().report.status, cd.ContentDraftStatus.SUCCESS)
        old_reply = self.transport.reply
        self.transport.transform = lambda reply: old_reply
        self.rejected(self.run_draft())

    def test_generator_exception_is_sanitized_and_not_delivered(self):
        def transform(o):
            raise RuntimeError("SECRET-CANARY")
        self.rejected(self.run_draft(workflow=ContentDraftWorkflow(self.writer, p_only_consumer=self.consumer,
            p_only_generator=TransformGenerator(transform))))

    def custom_quote_target(self, first_quote, review_id):
        quotes = (first_quote, *(o.statement for o in self.target.obligations[1:]))
        selected = self.target.draft_input.site_content
        selected = replace(selected, pages=(replace(selected.pages[0], body_text=" ".join(quotes)),))
        excerpts, cursor = [], 0
        for i, quote in enumerate(quotes):
            cut = 64 if i == 0 else len(quote)
            excerpts.append(FirstPartyExcerpt("body_text", cursor, cursor+cut, quote[:cut]))
            if i == 0:
                excerpts.append(FirstPartyExcerpt("body_text", cursor+cut, cursor+len(quote), quote[cut:]))
            cursor += len(quote)+1
        scope = FirstPartyPlanningScope(self.target.task_id, selected, "P1", "Delivery brief", tuple(excerpts))
        opportunity, plan, _, _ = native_planning(selected, scope)
        target = replace(self.target, scope=scope, draft_input=cd.ContentDraftInput(selected, opportunity, plan),
            obligations=tuple(replace(o, statement=q) for o, q in zip(self.target.obligations, quotes)))
        record = dict(self.record, record_id=review_id, frozen_target_sha256=hashlib.sha256(freeze_excerpt_target(target)).hexdigest(),
                      draft_input_sha256=draft_input_digest(target.draft_input))
        return target, record

    def custom_quote_request(self, first_quote, review_id):
        target, record = self.custom_quote_target(first_quote, review_id)
        receipt = self.seal(target, record)
        self.store.append(receipt)
        return POnlyDraftRequestV1(receipt.frozen_target, receipt.review_id)

    def test_long_o1_two_spans_form_one_complete_claim_without_truncation(self):
        quote = "Packing orientation, protective wrapping, internal bracing and handling instructions inform the delivery plan for this fictional shipment and its receiving team."
        self.assertGreater(len(quote), 120)
        request = self.custom_quote_request(quote, "TEST-LONG-O1")
        result = self.run_draft(request)
        self.assertEqual(result.report.status, cd.ContentDraftStatus.SUCCESS, result.reason)
        self.assertEqual(result.report.drafts[0].blocks[0].claims[0].text, quote)
        self.assertEqual(len(result.coverage_proof.coverage[0].spans), 2)

    def test_native_planning_normalization_conflict_cannot_obtain_test_draft_authority(self):
        quote = "Packing orientation, protective wrapping, internal bracing and handling instructions  inform the delivery plan for this fictional shipment and its receiving team."
        target, record = self.custom_quote_target(quote, "TEST-WHITESPACE-O1")
        self.assertIsNotNone(p_only_draft_target_error(target))
        with self.assertRaises(ValueError): self.seal(target, record)
        self.rejected(self.run_draft(POnlyDraftRequestV1(freeze_excerpt_target(target), self.request.review_id)))

    def test_native_planning_rejects_promotional_quote_before_test_authorization(self):
        quote = "Our packing service is the best choice for every shipment, with guaranteed perfect delivery planning for the fictional receiving team."
        target, record = self.custom_quote_target(quote, "TEST-PROMOTIONAL-O1")
        self.assertIsNotNone(p_only_draft_target_error(target))
        with self.assertRaises(ValueError): self.seal(target, record)
        self.rejected(self.run_draft(POnlyDraftRequestV1(freeze_excerpt_target(target), self.request.review_id)))

    def test_base_finalizer_failure_is_not_waived_by_verbatim_authorization(self):
        with patch.object(self.workflow, "_finalize", return_value=(None, "NUMERIC_NOT_GROUNDED")):
            result = self.run_draft()
        self.rejected(result)
        self.assertEqual(result.reason, "BASE_DRAFT_VALIDATION_FAILED")
        self.assertEqual(result.report.error, "NUMERIC_NOT_GROUNDED")

    def test_changed_registration_versions_or_digests_cannot_consume_cached_review(self):
        original = self.state.registrations[self.request.review_id]
        for field, value in (("task_version", 2), ("plan_version", 2), ("evidence_version", 2),
                             ("frozen_target_sha256", "0"*64), ("record_sha256", "0"*64),
                             ("proof_sha256", "0"*64), ("purpose", es.OFFLINE_EXCERPT_PURPOSE)):
            with self.subTest(field=field):
                self.state.registrations[self.request.review_id] = replace(original, **{field: value})
                self.rejected(self.run_draft())

    def test_span_gap_wrong_span_and_changed_evidence_reject_before_generation(self):
        raw = json.loads(self.request.frozen_target)
        for transform in (
            lambda obj: obj["scope"]["excerpts"][1].update(start=5),
            lambda obj: obj["scope"]["excerpts"][0].update(quote="Fake"),
            lambda obj: obj["obligations"][0].update(excerpt_indexes=[1,0]),
            lambda obj: obj["draft_input"]["site_content"]["pages"][0].update(body_text="Changed evidence"),
        ):
            obj = json.loads(json.dumps(raw))
            transform(obj)
            generator = TransformGenerator(lambda o:o)
            self.rejected(self.run_draft(POnlyDraftRequestV1(canonical_bytes(obj), self.request.review_id),
                ContentDraftWorkflow(self.writer, p_only_consumer=self.consumer, p_only_generator=generator)))
            self.assertEqual(generator.calls, 0)

    def test_key_grant_and_transport_lost_during_generation_discard_output(self):
        authority = self.state.authority
        for field in ("key_revoked", "grant_revoked", "transport"):
            with self.subTest(field=field):
                self.state.authority = authority
                self.transport.broken = False
                def transform(o):
                    if field == "transport": self.transport.broken = True
                    else: self.state.authority = replace(authority, **{field:True})
                    return o
                self.rejected(self.run_draft(workflow=ContentDraftWorkflow(self.writer, p_only_consumer=self.consumer,
                    p_only_generator=TransformGenerator(transform))))

    def test_test_draft_signoff_method_cannot_run_under_production_anchors(self):
        host = EvidenceReviewHost(anchors=replace(self.anchors, environment=ReviewEnvironment.PRODUCTION),
            identities=self.sessions, state=self.state, clock=self.clock,
            review_signer=self.signer, registry_signer=self.registry_signer)
        with self.assertRaisesRegex(ValueError, "ISOLATED_TEST_ROOT_REQUIRED"):
            self.seal(self.target, self.record, method=host.seal_test_draft)


class POnlyDraftRequestContractTests(unittest.TestCase):
    def test_version_type_size_and_gate_flag_rejected(self):
        for args in ((b"x", "R1", 2), (b"x", "R1", True), (b"", "R1", 1),
                     (b"x"*(128*1024+1), "R1", 1), (bytearray(b"x"), "R1", 1)):
            with self.assertRaises(ValueError): POnlyDraftRequestV1(*args)
        report = asyncio.run(production_p_only_draft().run_p_only({"approved":True}))
        self.assertEqual(report.report.drafts, ())
        self.assertIsNone(report.coverage_proof)
