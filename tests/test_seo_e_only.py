"""E-only native Draft admission, quotation constraints and historical review."""
import asyncio
from dataclasses import asdict, replace
from datetime import timedelta
import hashlib
import ipaddress
import json
from pathlib import Path
import shutil
import socket
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts.demo_seo_e_only import (
    CUSTOMER, DOCUMENT, FACT, LOCATOR, NOW, FixedEOnlyWriter, SyntheticEOnlyReviewer,
    prepare, prepare_test_input, revalidate_test_input, run_test_candidate,
)
from scripts.demo_seo_evidence import NeverDraft
from foreign_trade_geo_agent.adapters.deepseek_content_draft import DeepSeekContentDraftWriter, content_draft_request_payload
from foreign_trade_geo_agent.core.content_draft import (
    ContentDraftInput, ContentDraftStatus, MAX_SYSTEM_PROMPT_CHARS, MAX_USER_MATERIAL_CHARS,
    MAX_USER_MATERIAL_BYTES, MAX_INPUT_ENVELOPE_CHARS, MAX_INPUT_ENVELOPE_BYTES,
    build_content_draft_prompt, finalize_draft_item, stable_content_draft_input_error,
)
from foreign_trade_geo_agent.core.content_draft_review import ContentDraftReviewRequest
from foreign_trade_geo_agent.core.draft_customer_evidence import DraftCustomerSource
from foreign_trade_geo_agent.core.evidence_intake import (
    CustomerContext, CustomerSubmission, Supplement, SupplementMethod, SupportVerdict, snapshot_digest,
)
from foreign_trade_geo_agent.core.history import ArtifactType, MalformedHistoryDataError
from foreign_trade_geo_agent.reporting.content_draft_review import render_content_draft_review_markdown
from foreign_trade_geo_agent.storage.evidence_intake import SQLiteEvidenceIntakeStore, _load
from foreign_trade_geo_agent.storage.serialization import decode_artifact, encode_artifact, _decode
from foreign_trade_geo_agent.storage.sqlite import SQLiteHistoryReader
from foreign_trade_geo_agent.workflows.content_draft import ContentDraftWorkflow, _parse_specification
from foreign_trade_geo_agent.workflows.content_draft_review import ContentDraftReviewWorkflow
from foreign_trade_geo_agent.workflows.evidence_intake import EvidenceIntakeWorkflow, EvidenceIntakeDraftAdmission


class EOnlyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.fixture = Path(cls.temp.name) / "fixture"
        connect = socket.socket.connect
        def offline(sock, address):
            if not isinstance(address, tuple) or not ipaddress.ip_address(address[0]).is_loopback:
                raise AssertionError("NO EXTERNAL NETWORK")
            return connect(sock, address)
        with patch("socket.socket.connect", new=offline), patch(
                "foreign_trade_geo_agent.cli.load_runtime_environment", side_effect=AssertionError("NO CREDENTIALS")):
            cls.meta = prepare(cls.fixture)

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        for path in self.fixture.iterdir():
            shutil.copyfile(path, self.directory / path.name)
        self.store = SQLiteEvidenceIntakeStore(self.directory / "intake.sqlite3")
        self.project, self.task = self.meta["project_id"], self.meta["task_id"]
        self.reviewer = SyntheticEOnlyReviewer()
        self.snapshot = self.store.latest(self.project, self.task)
        self.value = prepare_test_input(self.store, self.project, self.task,
            expected_sha256=snapshot_digest(self.snapshot), reviewer=self.reviewer)
        self.bundle = self.value.customer_evidence
        self.operation = self.value.change_plan_report.operations[0]
        self.raw = json.loads((self.directory / "04-writer-output.json").read_text(encoding="utf-8"))
        self.report = decode_artifact(ArtifactType.CONTENT_DRAFT, 1,
            (self.directory / "05-content-draft.json").read_text(encoding="utf-8"))

    def fact_claim(self):
        return self.raw["draft"]["sections"][0]["blocks"][1]["claims"][0]

    def finalize(self, value=None):
        value = value or self.value
        operation = value.change_plan_report.operations[0]
        specification = _parse_specification(json.dumps(self.raw), expected_change_ref="C1", operation=operation)
        return finalize_draft_item(1, specification, operation, value.opportunity_report.opportunities[0],
            value.site_content, value.opportunity_report, customer_evidence=value.customer_evidence)

    def revalidate(self, value=None, now=NOW):
        return revalidate_test_input(value or self.value, self.store, reviewer=self.reviewer, now=now)

    def update_evidence(self, content=DOCUMENT):
        supplement = Supplement("E2", ("F1",), SupplementMethod.TEXT_DOCUMENT, content,
            "SYNTHETIC revised note", LOCATOR + "-revision", "FICTIONAL NovaCNC",
            hashlib.sha256(content.encode()).hexdigest(), supersedes="E1")
        return EvidenceIntakeWorkflow(self.store).submit(self.project, self.task,
            CustomerSubmission("SYNTHETIC-UPDATE", snapshot_digest(self.snapshot), (supplement,)),
            customer=CustomerContext(CUSTOMER, "SYNTHETIC-CUSTOMER", NOW))

    def test_complete_native_article_and_sqlite_reopen(self):
        draft, error = self.finalize()
        self.assertIsNone(error)
        self.assertEqual(draft, self.report.drafts[0])
        reopened = SQLiteHistoryReader(self.directory / "history.sqlite3").get_artifact(self.meta["artifact_id"])
        self.assertEqual(reopened.payload, self.report)
        self.assertEqual(draft.customer_evidence, self.bundle)
        source_bytes = (self.directory / "customer-E1.txt").read_bytes()
        self.assertEqual(source_bytes.decode("utf-8"), self.bundle.sources[0].content)
        self.assertEqual(hashlib.sha256(source_bytes).hexdigest(), self.bundle.sources[0].content_sha256)
        self.assertEqual(len(draft.blocks), 4)
        self.assertEqual(draft.section_block_counts, (2, 2))
        self.assertEqual(self.meta["word_count"], 235)
        self.assertFalse(self.meta["draft_authorized"])

    def test_parameter_is_only_in_e_and_has_no_ps_refs(self):
        ps = json.dumps([asdict(self.value.site_content), asdict(self.value.opportunity_report)], default=str)
        for token in (FACT, "7200 rpm", "NCX7", "NOVA-TEST-7", "20 C", "unloaded bench"):
            self.assertNotIn(token, ps)
        claim = self.report.drafts[0].blocks[1].claims[0]
        self.assertEqual(claim.text, FACT)
        self.assertEqual(claim.customer_refs, ("E1",))
        self.assertEqual((claim.page_refs, claim.source_refs), ((), ()))
        self.assertEqual(claim.support_kind.value, "CUSTOMER_REVIEWED_QUOTE")

    def test_markdown_contains_claim_quote_locator_versions_and_test_status(self):
        view = ContentDraftReviewWorkflow(history_reader=SQLiteHistoryReader(self.directory / "history.sqlite3")).review(
            ContentDraftReviewRequest(self.meta["run_id"], self.meta["artifact_id"], "D1"))
        markdown = render_content_draft_review_markdown(view)
        for text in ("CL3: E1", "E1 → CL3", FACT, LOCATOR, "version=2", "span=[46:239]",
                     "TEST_ONLY_SUPPORTED_NOT_HUMAN_SIGNOFF", "UNREVIEWED", "1/2/2/3", "not prove semantic truth"):
            self.assertIn(text, markdown)
        self.assertEqual(view.customer_evidence, self.bundle)

    def test_missing_e_is_rejected_by_native_finalizer(self):
        self.assertEqual(self.finalize(replace(self.value, customer_evidence=None))[1], "UNKNOWN_CUSTOMER_REFERENCE")

    def test_missing_intake_e_refuses_writer(self):
        class MissingStore:
            def latest(inner, project, task):
                return replace(self.snapshot, evidence=(), submission_ids=())
        with self.assertRaises(ValueError):
            prepare_test_input(MissingStore(), self.project, self.task,
                expected_sha256=snapshot_digest(replace(self.snapshot, evidence=(), submission_ids=())), reviewer=self.reviewer)

    def test_changed_number_unit_model_or_protocol_rejected(self):
        for old, new in (("7200 rpm", "7201 rpm"), ("7200 rpm", "7200 mm"),
                         ("NCX7", "NCX8"), ("NOVA-TEST-7", "NOVA-TEST-8"), ("20 C", "21 C")):
            with self.subTest(new=new):
                self.fact_claim()["text"] = FACT.replace(old, new)
                self.assertEqual(self.finalize()[1], "NUMERIC_NOT_GROUNDED")

    def test_changed_conditions_or_omitted_limitations_rejected(self):
        for text in (FACT.replace("unloaded bench", "cutting load"), FACT.split("; applies")[0] + ".",
                     FACT.replace("only to", "to all variants of")):
            with self.subTest(text=text):
                self.fact_claim()["text"] = text
                self.assertEqual(self.finalize()[1], "CUSTOMER_QUOTE_MISMATCH")

    def test_omitting_required_e_claim_cannot_pass(self):
        self.raw["draft"]["sections"][0]["blocks"][1]["claims"].pop(0)
        self.assertEqual(self.finalize()[1], "CUSTOMER_EVIDENCE_COVERAGE")

    def test_relabelling_e_fact_as_p_or_s_does_not_ground_it(self):
        for p, s in ((["P1"], []), ([], ["S1"]), (["P1"], ["S1"])):
            with self.subTest(p=p, s=s):
                self.fact_claim().update(customer_refs=[], page_refs=p, source_refs=s)
                self.assertIn(self.finalize()[1], {"NUMERIC_NOT_GROUNDED", "FIRST_PARTY_FACT_WITHOUT_PAGE"})

    def test_e_model_cannot_be_relabelled_as_general_s_context(self):
        self.fact_claim().update(text="NCX7 spindle rated 7200 rpm continuously.",
            claim_type="GENERAL_TECHNICAL_CONTEXT", customer_refs=[], page_refs=[], source_refs=["S1"])
        self.assertEqual(self.finalize()[1], "FIRST_PARTY_FACT_WITHOUT_PAGE")

    def test_unknown_or_duplicate_e_ids_rejected(self):
        for refs, error in ((["E999"], "UNKNOWN_CUSTOMER_REFERENCE"), (["E1", "E1"], "FIELD_CONTRACT"),
                            (["P1"], "UNKNOWN_CUSTOMER_REFERENCE")):
            with self.subTest(refs=refs):
                self.fact_claim()["customer_refs"] = refs
                self.assertEqual(self.finalize()[1], error)

    def test_model_cannot_forge_locator_review_or_version_fields(self):
        for key, value in (("source_locator", LOCATOR), ("review_status", "SUPPORTED"), ("evidence_version", 2)):
            with self.subTest(key=key):
                self.fact_claim()[key] = value
                with self.assertRaisesRegex(ValueError, "FIELD_CONTRACT"):
                    self.finalize()
                self.fact_claim().pop(key)

    def test_current_e_update_invalidates_old_binding_before_writer(self):
        self.update_evidence()
        writer = FixedEOnlyWriter()
        with self.assertRaises(ValueError):
            asyncio.run(run_test_candidate(self.value, self.store, reviewer=self.reviewer, writer=writer))
        self.assertEqual(writer.calls, 0)

    def test_update_during_writer_discards_candidate(self):
        original = FixedEOnlyWriter.write_content_draft
        async def update_then_write(writer, prompt):
            self.update_evidence()
            return await original(writer, prompt)
        writer = FixedEOnlyWriter()
        before = len(SQLiteHistoryReader(self.directory / "history.sqlite3").list_artifacts(self.meta["run_id"]))
        with patch.object(FixedEOnlyWriter, "write_content_draft", new=update_then_write), self.assertRaises(ValueError):
            asyncio.run(run_test_candidate(self.value, self.store, reviewer=self.reviewer, writer=writer))
        self.assertEqual(writer.calls, 1)
        self.assertEqual(before, len(SQLiteHistoryReader(self.directory / "history.sqlite3").list_artifacts(self.meta["run_id"])))

    def test_wrong_customer_task_project_plan_or_version_rejected(self):
        for field, value in (("customer_id", "SYNTHETIC-OTHER"), ("task_id", "wrong-task"),
                             ("project_id", "wrong-project"), ("plan_version", 3), ("task_version", 2),
                             ("evidence_version", 3), ("snapshot_revision", 4)):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.revalidate(replace(self.value, customer_evidence=replace(self.bundle, **{field: value})))

    def test_forged_locator_source_version_or_requirement_rejected(self):
        source = self.bundle.sources[0]
        for field, value in (("source_locator", "synthetic:forged"), ("evidence_version", 1),
                             ("requirement_ids", ("F99",))):
            with self.subTest(field=field), self.assertRaises(ValueError):
                bundle = replace(self.bundle, sources=(replace(source, **{field: value}),))
                self.revalidate(replace(self.value, customer_evidence=bundle))

    def test_unreviewed_and_conflicting_evidence_not_admitted(self):
        original = SyntheticEOnlyReviewer.assess
        for verdict in (SupportVerdict.UNREVIEWED, SupportVerdict.CONFLICT, SupportVerdict.IRRELEVANT, SupportVerdict.MISSING):
            def assessment(reviewer, snapshot, *, now):
                a = original(reviewer, snapshot, now=now)
                return replace(a, decisions=(replace(a.decisions[0], verdict=verdict),))
            with self.subTest(verdict=verdict), patch.object(SyntheticEOnlyReviewer, "assess", new=assessment), self.assertRaises(ValueError):
                prepare_test_input(self.store, self.project, self.task,
                    expected_sha256=snapshot_digest(self.snapshot), reviewer=self.reviewer)

    def test_expired_review_and_unavailable_reviewer_rejected(self):
        original = SyntheticEOnlyReviewer.assess
        def expired(reviewer, snapshot, *, now):
            return replace(original(reviewer, snapshot, now=now), reviewed_at=now - timedelta(minutes=6))
        for replacement in (expired, lambda *a, **k: (_ for _ in ()).throw(ValueError("REVOKED"))):
            with patch.object(SyntheticEOnlyReviewer, "assess", new=replacement), self.assertRaises(ValueError):
                prepare_test_input(self.store, self.project, self.task,
                    expected_sha256=snapshot_digest(self.snapshot), reviewer=self.reviewer)
        with self.assertRaises(ValueError):
            self.revalidate(now=NOW + timedelta(minutes=6))

    def test_changed_native_plan_invalidates_binding(self):
        resource = replace(self.operation.new_resource_spec, proposed_title="Changed resource title")
        operation = replace(self.operation, proposed_heading=resource.proposed_title, new_resource_spec=resource)
        value = replace(self.value, change_plan_report=replace(self.value.change_plan_report, operations=(operation,)))
        self.assertEqual(stable_content_draft_input_error(value), "CUSTOMER_EVIDENCE_INVALID")
        self.assertEqual(self.finalize(value)[1], "CUSTOMER_EVIDENCE_INVALID")

    def test_invalid_review_status_and_hash_or_span_rejected(self):
        with self.assertRaises(ValueError):
            replace(self.bundle, review_status="SUPPORTED")
        for kwargs in ({"content_sha256": "0" * 64}, {"span_start": 0}, {"quote": FACT.replace("NCX7", "NCX8")}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                replace(self.bundle.sources[0], **kwargs)

    def test_e_dates_certificate_ids_and_bare_numbers_use_native_numeric_checks(self):
        quote = "SYNTHETIC ONLY: NovaCNC NCX7 certificate DEMO-CNC-1 under DEMO-2026 expires 2027-01-01; fictional scope only."
        source = replace(self.bundle.sources[0], content=quote, quote=quote, span_start=0, span_end=len(quote),
            content_sha256=hashlib.sha256(quote.encode()).hexdigest())
        value = replace(self.value, customer_evidence=replace(self.bundle, sources=(source,)))
        self.fact_claim()["text"] = quote
        self.assertIsNone(self.finalize(value)[1])
        for old, new in (("DEMO-CNC-1", "DEMO-CNC-2"), ("DEMO-2026", "DEMO-2025"),
                         ("2027-01-01", "2028-01-01")):
            with self.subTest(new=new):
                self.fact_claim()["text"] = quote.replace(old, new)
                self.assertEqual(self.finalize(value)[1], "NUMERIC_NOT_GROUNDED")
        # Even an exact, purportedly reviewed quotation cannot exempt bare numbers.
        bare = "SYNTHETIC ONLY: NovaCNC NCX7 speed 7200; fictional bench result."
        source = replace(source, content=bare, quote=bare, span_end=len(bare),
            content_sha256=hashlib.sha256(bare.encode()).hexdigest())
        self.fact_claim()["text"] = bare
        self.assertEqual(self.finalize(replace(self.value,
            customer_evidence=replace(self.bundle, sources=(source,))))[1], "NUMERIC_NOT_GROUNDED")

    def test_e_numeric_failure_diagnostic_uses_e_namespace(self):
        from foreign_trade_geo_agent.core.content_draft import describe_numeric_grounding_violation
        self.fact_claim()["text"] = FACT.replace("7200 rpm", "7300 rpm")
        spec = _parse_specification(json.dumps(self.raw), expected_change_ref="C1", operation=self.operation)
        descriptor = describe_numeric_grounding_violation(1, spec, build_content_draft_prompt(self.value, "C1"))
        self.assertEqual(descriptor.cited_ref_ids, ("E1",))
        self.assertEqual(descriptor.source_namespace, "CUSTOMER_EVIDENCE")
        self.assertFalse(descriptor.has_page_refs)
        self.assertTrue(descriptor.evidence_match_failed)

    def test_modified_e_document_not_admitted_even_with_recomputed_hash(self):
        updated = self.update_evidence(DOCUMENT.replace("7200 rpm", "7300 rpm"))
        # Native rebind can retain a plan, but cannot imply semantic approval.
        updated = EvidenceIntakeWorkflow(self.store).rebind_plan(self.project, self.task,
            expected_sha256=snapshot_digest(updated), planning_input=updated.planning_input)
        with self.assertRaises(ValueError):
            prepare_test_input(self.store, self.project, self.task,
                expected_sha256=snapshot_digest(updated), reviewer=self.reviewer)

    def test_synthetic_review_cannot_open_production_draft_gate(self):
        never = NeverDraft()
        workflow = ContentDraftWorkflow(never, intake_admission=EvidenceIntakeDraftAdmission(self.store,
            self.project, self.task, expected_snapshot_sha256=self.bundle.snapshot_sha256))
        result = asyncio.run(workflow.run(self.value))
        self.assertEqual(result.error, "INTAKE_EXECUTION_BLOCKED")
        self.assertEqual(never.calls, 0)
        real_adapter = DeepSeekContentDraftWriter()
        result = asyncio.run(real_adapter.write_content_draft(build_content_draft_prompt(self.value, "C1")))
        self.assertEqual(result.error, "DRAFT_EXECUTION_AUTHORIZATION_REQUIRED")

    def test_test_evidence_cannot_become_wordpress_payload(self):
        from foreign_trade_geo_agent.core.wordpress_draft import build_wordpress_draft_request, WordPressDraftValidationError
        with self.assertRaisesRegex(WordPressDraftValidationError, "TEST-only"):
            build_wordpress_draft_request(self.report.drafts[0])

    def test_prompt_is_bounded_and_e_is_separate(self):
        prompt = build_content_draft_prompt(self.value, "C1")
        material = prompt.material_json()
        system = DeepSeekContentDraftWriter.build_system_prompt(customer_evidence=True)
        raw = json.loads(material)
        self.assertEqual(raw["contract"]["customer_refs"], ["E1"])
        self.assertEqual(raw["customer_evidence"]["sources"][0]["quote"], FACT)
        self.assertNotIn("7200", json.dumps(raw["pages"] + raw["sources"]))
        self.assertLessEqual(len(system), MAX_SYSTEM_PROMPT_CHARS)
        self.assertLessEqual(len(material), MAX_USER_MATERIAL_CHARS)
        self.assertLessEqual(len(material.encode()), MAX_USER_MATERIAL_BYTES)
        envelope = json.dumps(content_draft_request_payload(system, material), ensure_ascii=False, separators=(",", ":"))
        self.assertLessEqual(len(envelope), MAX_INPUT_ENVELOPE_CHARS)
        self.assertLessEqual(len(envelope.encode()), MAX_INPUT_ENVELOPE_BYTES)

    def test_corrupted_persisted_e_ref_or_binding_rejected(self):
        for mutate in (lambda raw: raw["drafts"][0].pop("customer_evidence"),
                       lambda raw: raw["drafts"][0]["blocks"][1]["claims"][0].update(customer_refs=["E999"]),
                       lambda raw: raw["drafts"][0]["customer_evidence"].update(review_status="SUPPORTED")):
            raw = json.loads(encode_artifact(ArtifactType.CONTENT_DRAFT, self.report))
            mutate(raw)
            with self.assertRaises(MalformedHistoryDataError):
                decode_artifact(ArtifactType.CONTENT_DRAFT, 1, json.dumps(raw))

    def test_legacy_intake_input_and_snapshot_digest_unchanged(self):
        from foreign_trade_geo_agent.core.evidence_intake import IntakeSnapshot
        from foreign_trade_geo_agent.storage.serialization import _encode
        raw = _encode(self.snapshot)
        self.assertNotIn("customer_evidence", raw["planning_input"])
        self.assertNotIn("writing_brief", raw["planning_input"])
        self.assertNotIn("propose_interpretations", raw["planning_input"])
        historical = _load(json.dumps(raw), IntakeSnapshot)
        self.assertEqual(historical, self.snapshot)
        legacy = asdict(self.snapshot)
        legacy["planning_input"].pop("customer_evidence")
        legacy["planning_input"].pop("writing_brief")
        legacy["planning_input"].pop("propose_interpretations")
        # Reconstruct the pre-structured-scope V1 shape independently. New
        # optional defaults must neither appear in its codec nor change hashes.
        for field in ('article_type', 'search_intent', 'reader_problem', 'section_briefs'):
            self.assertNotIn(field, raw['task'])
            legacy['task'].pop(field)
        for encoded, operation in zip(raw['planning_input']['change_plan_report']['operations'],
                                      legacy['planning_input']['change_plan_report']['operations']):
            if operation['new_resource_spec'] is not None:
                self.assertNotIn('section_briefs', encoded['new_resource_spec'])
                operation['new_resource_spec'].pop('section_briefs')
        def encode(v):
            from enum import Enum
            return v.value if isinstance(v, Enum) else v.isoformat()
        digest = hashlib.sha256(json.dumps(legacy, default=encode, ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        self.assertEqual(snapshot_digest(self.snapshot), digest)

    def test_old_ps_article_payload_is_still_readable(self):
        path = Path(__file__).parents[1] / "docs/seo-article-acceptance-2026-10-10/03-content-draft.json"
        raw = path.read_text(encoding="utf-8")
        report = decode_artifact(ArtifactType.CONTENT_DRAFT, 1, raw)
        self.assertIsNone(report.drafts[0].customer_evidence)
        self.assertTrue(all(not c.customer_refs for b in report.drafts[0].blocks for c in b.claims))
        self.assertEqual(decode_artifact(ArtifactType.CONTENT_DRAFT, 1, encode_artifact(ArtifactType.CONTENT_DRAFT, report)), report)


if __name__ == "__main__":
    unittest.main()
