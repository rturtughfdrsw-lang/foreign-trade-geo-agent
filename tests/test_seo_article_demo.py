"""One synthetic article through existing native contracts; all ports offline."""
import asyncio
from contextlib import redirect_stdout
from dataclasses import replace
from datetime import timedelta
from io import StringIO
import json
import ipaddress
from pathlib import Path
import shutil
import socket
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts.demo_seo_article import (
    CLAIMS, FACTS, NOW, FixedArticleWriter, SyntheticHumanFixture, prepare, run_offline_candidate,
)
from scripts.demo_seo_evidence import NeverDraft
from foreign_trade_geo_agent.adapters.retained_intake_plan import RetainedIntakePlanWriter
from foreign_trade_geo_agent.cli import main
from foreign_trade_geo_agent.core import change_plan as cp
from foreign_trade_geo_agent.core.content_draft import (
    ContentDraftInput, ContentDraftStatus, ContentDraftType, MAX_BLOCKS_PER_DRAFT, MAX_CLAIMS_PER_DRAFT,
)
from foreign_trade_geo_agent.core.content_draft_review import ContentDraftReviewRequest, render_draft_body_text
from foreign_trade_geo_agent.core.evidence_intake import (
    CustomerContext, CustomerSubmission, IntakeStatus, SupportVerdict, native_plan_error, snapshot_digest,
)
from foreign_trade_geo_agent.core.history import ArtifactType, MalformedHistoryDataError
from foreign_trade_geo_agent.reporting.content_draft_review import render_content_draft_review_markdown
from foreign_trade_geo_agent.storage.evidence_intake import SQLiteEvidenceIntakeStore
from foreign_trade_geo_agent.storage.serialization import decode_artifact, encode_artifact
from foreign_trade_geo_agent.storage.sqlite import SQLiteHistoryReader
from foreign_trade_geo_agent.workflows.change_plan import ChangePlanWorkflow
from foreign_trade_geo_agent.workflows.content_draft import ContentDraftWorkflow
from foreign_trade_geo_agent.workflows.content_draft_review import ContentDraftReviewWorkflow
from foreign_trade_geo_agent.workflows.evidence_intake import EvidenceIntakeDraftAdmission, EvidenceIntakeWorkflow


class SEOArticleDemoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = TemporaryDirectory()
        cls.addClassCleanup(cls.fixture.cleanup)
        cls.fixture_dir = Path(cls.fixture.name) / "demo"
        # Any accidental network or credential loading fails the end-to-end fixture.
        connect = socket.socket.connect
        def offline_connect(sock, address):
            # Windows asyncio creates a local socketpair for each event loop.
            if not isinstance(address, tuple) or not ipaddress.ip_address(address[0]).is_loopback:
                raise AssertionError("OFFLINE ONLY")
            return connect(sock, address)
        with patch("socket.socket.connect", new=offline_connect), patch(
                "foreign_trade_geo_agent.cli.load_runtime_environment", side_effect=AssertionError("NO CREDENTIALS")):
            cls.meta = prepare(cls.fixture_dir)

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        for path in self.fixture_dir.iterdir():
            shutil.copyfile(path, self.directory / path.name)
        self.db = self.directory / "history.sqlite3"
        self.store = SQLiteEvidenceIntakeStore(self.directory / "intake.sqlite3")
        self.project, self.task = self.meta["project_id"], self.meta["task_id"]
        self.snapshot = self.store.latest(self.project, self.task)
        self.report = decode_artifact(ArtifactType.CONTENT_DRAFT, 1,
            (self.directory / "03-content-draft.json").read_text(encoding="utf-8"))
        self.draft = self.report.drafts[0]

    def view(self):
        return ContentDraftReviewWorkflow(history_reader=SQLiteHistoryReader(self.db)).review(
            ContentDraftReviewRequest(self.meta["offline_run_id"], self.meta["content_draft_artifact_id"], "D1"))

    def refuse_offline(self, *, reviewer=None, digest=None):
        writer = FixedArticleWriter()
        with self.assertRaises(ValueError):
            asyncio.run(run_offline_candidate(self.directory / "refused.sqlite3", self.store,
                self.project, self.task, expected_sha256=digest or snapshot_digest(self.snapshot),
                reviewer=reviewer, writer=writer))
        self.assertEqual(writer.calls, 0)
        self.assertFalse((self.directory / "refused.sqlite3").exists())

    def test_one_complete_persisted_article_with_native_sections_and_full_qualifiers(self):
        self.assertEqual(self.report.status, ContentDraftStatus.SUCCESS)
        self.assertEqual(len(self.report.drafts), 1)
        self.assertEqual(self.draft.draft_type, ContentDraftType.NEW_RESOURCE_DRAFT)
        self.assertEqual(self.draft.section_block_counts, (2, 3))
        self.assertLessEqual(len(self.draft.blocks), MAX_BLOCKS_PER_DRAFT)
        claims = self.view().draft.claims
        self.assertEqual(tuple(c.text for c in claims), tuple(t for _, t in CLAIMS))
        self.assertLessEqual(len(claims), MAX_CLAIMS_PER_DRAFT)
        rendered = render_draft_body_text(self.draft)
        for fact in FACTS:
            self.assertIn(fact, rendered)
        self.assertIn("## spindle performance", rendered)
        self.assertIn("## machining tolerance", rendered)
        self.assertLess(rendered.index("## spindle performance"), rendered.index(FACTS[0]))
        self.assertLess(rendered.index("## machining tolerance"), rendered.index(FACTS[1]))
        self.assertTrue(self.report.requires_human_review)
        self.assertTrue(self.draft.requires_human_review)

    def test_native_new_resource_intake_is_compatible_with_retained_planning(self):
        value = self.snapshot.planning_input
        self.assertIsNone(native_plan_error(value, self.snapshot.point_subjects))
        self.assertEqual(value.change_plan_report.operations[0].operation_type, cp.ChangeOperationType.CREATE_NEW_RESOURCE)
        self.assertEqual((self.snapshot.task.task_version, self.snapshot.plan_version,
                          self.snapshot.evidence_version, self.snapshot.revision), (1, 2, 2, 3))
        self.assertEqual(set(json.loads((self.directory / "02-intake-human-review.json").read_text())[
            "claim_verdicts"].values()), {"UNREVIEWED"})

    def test_all_fact_obligations_have_exact_customer_spans_and_native_page_refs(self):
        claims = {c.claim_id: c for c in self.view().draft.claims}
        for binding, evidence in zip(self.meta["evidence_binding"], self.snapshot.active_evidence):
            claim = claims[binding["claim_id"]]
            self.assertEqual(claim.text, evidence.supplement.content)
            self.assertEqual(claim.page_refs, ("P1",))
            self.assertEqual(claim.source_refs, ())
            self.assertEqual(binding["file_sha256"], evidence.supplement.file_sha256)
            self.assertEqual(binding["span"], [0, len(claim.text)])
            self.assertEqual(binding["review_state"], "UNREVIEWED")
        self.assertFalse(self.meta["draft_authorized"])
        self.assertFalse(self.meta["model_generated"])

    def test_markdown_review_exports_whole_article_and_each_claim_without_writing(self):
        before = {p.name: p.read_bytes() for p in (self.db, self.directory / "intake.sqlite3")}
        view = self.view()
        markdown = render_content_draft_review_markdown(view)
        for claim in view.draft.claims:
            self.assertIn(claim.claim_id, markdown)
            self.assertIn(claim.text, markdown)
        self.assertIn("NOT RECORDED", markdown)
        self.assertIn("[CL2: P1]", markdown)
        self.assertIn("UNREVIEWED", markdown)
        self.assertIn("https://novacnc.example/", markdown)
        self.assertIn("https://cnc-guide.example/checklist", markdown)
        self.assertIn("unverified external context", markdown)
        self.assertEqual(markdown, render_content_draft_review_markdown(view))
        self.assertEqual(before, {p.name: p.read_bytes() for p in (self.db, self.directory / "intake.sqlite3")})

    def test_cli_markdown_review_is_offline_and_requires_no_credentials(self):
        out = StringIO()
        with redirect_stdout(out), patch("foreign_trade_geo_agent.cli.load_runtime_environment",
                side_effect=AssertionError("NO CREDENTIALS")):
            code = main(["review", "--db", str(self.db), "--run-id", self.meta["offline_run_id"],
                "--artifact-id", self.meta["content_draft_artifact_id"], "--draft-id", "D1", "--format", "markdown"])
        self.assertEqual(code, 0)
        self.assertEqual(out.getvalue(), render_content_draft_review_markdown(self.view()))

    def test_old_artifacts_remain_readable_without_inventing_section_boundaries(self):
        raw = json.loads(encode_artifact(ArtifactType.CONTENT_DRAFT, self.report))
        del raw["drafts"][0]["section_block_counts"]
        old = decode_artifact(ArtifactType.CONTENT_DRAFT, 1, json.dumps(raw))
        self.assertEqual(old.drafts[0].section_block_counts, ())
        self.assertIn("Outline:", render_draft_body_text(old.drafts[0]))
        self.assertNotIn("## spindle performance", render_draft_body_text(old.drafts[0]))

    def test_malformed_section_metadata_is_rejected_by_strict_codec(self):
        for counts in ([1], [2, 2], [True, 4], [0, 5], [2, 9], "2,3"):
            with self.subTest(counts=counts):
                raw = json.loads(encode_artifact(ArtifactType.CONTENT_DRAFT, self.report))
                raw["drafts"][0]["section_block_counts"] = counts
                with self.assertRaises(MalformedHistoryDataError):
                    decode_artifact(ArtifactType.CONTENT_DRAFT, 1, json.dumps(raw))

    def test_missing_evidence_refuses_fixture_writer(self):
        original = self.snapshot
        other = SQLiteEvidenceIntakeStore.create(self.directory / "missing.sqlite3")
        missing = EvidenceIntakeWorkflow(other).register(original.task, original.planning_input)
        self.store, self.snapshot = other, missing
        self.refuse_offline(reviewer=None)

    def test_unreviewed_evidence_refuses_fixture_writer(self):
        self.refuse_offline()

    def test_expired_and_conflicting_semantic_test_verdicts_refuse_fixture_writer(self):
        class Reviewer:
            def __init__(self, verdict, age):
                self.verdict, self.age = verdict, age
            def assess(self, snapshot, *, now):
                base = SyntheticHumanFixture().assess(snapshot, now=now)
                return replace(base, reviewed_at=now-self.age,
                    decisions=tuple(replace(d, verdict=self.verdict) for d in base.decisions))
        for verdict, age in ((SupportVerdict.CONFLICT, timedelta()),
                             (SupportVerdict.MISSING, timedelta()),
                             (SupportVerdict.IRRELEVANT, timedelta()),
                             (SupportVerdict.SUPPORTED, timedelta(minutes=6))):
            with self.subTest(verdict=verdict, age=age):
                self.refuse_offline(reviewer=Reviewer(verdict, age))

    def test_stale_version_and_unbound_new_supplement_refuse_fixture_writer(self):
        self.refuse_offline(reviewer=SyntheticHumanFixture(), digest="0"*64)
        old = self.snapshot
        replacement = replace(old.active_evidence[0].supplement, evidence_id="E1-V2", supersedes="E1")
        new = EvidenceIntakeWorkflow(self.store).submit(self.project, self.task,
            CustomerSubmission("NEW-REVISION", snapshot_digest(old), (replacement,)),
            customer=CustomerContext(old.task.customer_id, "SYNTHETIC-ACTOR", NOW))
        self.refuse_offline(reviewer=SyntheticHumanFixture())
        self.snapshot = new
        self.refuse_offline(reviewer=SyntheticHumanFixture())

    def test_even_current_supported_intake_cannot_authorize_production_draft(self):
        check = EvidenceIntakeWorkflow(self.store, reviewer=SyntheticHumanFixture()).check(self.project, self.task, now=NOW)
        self.assertEqual(check.status, IntakeStatus.CANDIDATE_FOR_REVIEW)
        writer = NeverDraft()
        flow = ContentDraftWorkflow(writer, intake_admission=EvidenceIntakeDraftAdmission(
            self.store, self.project, self.task, expected_snapshot_sha256=snapshot_digest(self.snapshot)))
        report = asyncio.run(flow.run(self.snapshot.planning_input))
        self.assertEqual(report.error, "INTAKE_EXECUTION_BLOCKED")
        self.assertEqual(writer.calls, 0)
        self.assertEqual(self.meta["production_draft_writer_calls"], 0)
        self.assertEqual(self.meta["offline_fixed_writer_calls"], 1)

    def test_customer_evidence_ids_cannot_be_used_as_native_claim_citations(self):
        from foreign_trade_geo_agent.core.content_draft import ContentDraftGeneration, ContentDraftGenerationStatus
        class ForgedWriter:
            async def write_content_draft(self, prompt):
                generation = await FixedArticleWriter().write_content_draft(prompt)
                raw = json.loads(generation.text)
                raw["draft"]["sections"][0]["blocks"][0]["claims"][1]["page_refs"] = ["E1"]
                return ContentDraftGeneration("synthetic", "forged-test", ContentDraftGenerationStatus.SUCCESS, json.dumps(raw), None)
        report = asyncio.run(ContentDraftWorkflow(ForgedWriter()).run(self.snapshot.planning_input))
        self.assertEqual(report.status, ContentDraftStatus.INVALID_OUTPUT)
        self.assertEqual(report.error, "UNKNOWN_PAGE_REFERENCE")

    def test_intake_still_rejects_multi_operation_and_non_explain_profiles(self):
        value = self.snapshot.planning_input
        plan = value.change_plan_report
        op = plan.operations[0]
        second_resource = replace(op.new_resource_spec, proposed_title="spindle performance")
        multi = replace(plan, operations=(op, replace(op, change_id="C2",
            proposed_heading=second_resource.proposed_title, new_resource_spec=second_resource)))
        self.assertIsNotNone(native_plan_error(replace(value, change_plan_report=multi), self.snapshot.point_subjects))
        points = tuple(replace(p, intent=cp.ContentPointIntent.DESCRIBE) for p in op.content_points)
        resource = replace(op.new_resource_spec, content_points=points)
        changed = replace(plan, operations=(replace(op, content_points=points, new_resource_spec=resource),))
        self.assertIsNotNone(native_plan_error(replace(value, change_plan_report=changed), self.snapshot.point_subjects))

    def test_rebind_cannot_change_title_outline_or_source_page_suggestions(self):
        original = self.snapshot
        replacement = replace(original.active_evidence[0].supplement, evidence_id="E1-NEW", supersedes="E1")
        flow = EvidenceIntakeWorkflow(self.store)
        current = flow.submit(self.project, self.task,
            CustomerSubmission("REBIND-PROBE", snapshot_digest(original), (replacement,)),
            customer=CustomerContext(original.task.customer_id, "SYNTHETIC-ACTOR", NOW))
        plan = current.planning_input.change_plan_report
        op = plan.operations[0]
        for field, value in (("proposed_title", "spindle performance"),
                             ("outline_headings", tuple(reversed(op.new_resource_spec.outline_headings))),
                             ("suggested_source_page_refs", ())):
            with self.subTest(field=field):
                changed_resource = replace(op.new_resource_spec, **{field: value})
                changed_op = replace(op, new_resource_spec=changed_resource,
                    proposed_heading=changed_resource.proposed_title)
                changed = replace(current.planning_input, change_plan_report=replace(plan, operations=(changed_op,)))
                with self.assertRaisesRegex(ValueError, "PLAN_REBIND_REJECTED"):
                    flow.rebind_plan(self.project, self.task, expected_sha256=snapshot_digest(current), planning_input=changed)
                self.assertEqual(self.store.latest(self.project, self.task), current)
        candidate = asyncio.run(flow.replan(self.project, self.task, expected_sha256=snapshot_digest(current),
            planner=ChangePlanWorkflow(RetainedIntakePlanWriter()), now=NOW))
        self.assertFalse(candidate.draft_authorized)
