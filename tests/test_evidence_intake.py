"""Independent fictional export-packaging customer; no live authority or writer."""
import asyncio
from contextlib import closing
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from foreign_trade_geo_agent.adapters.customer_evidence import text_document
from foreign_trade_geo_agent.core import change_plan as cp
from foreign_trade_geo_agent.core.content_draft import ContentDraftInput, ContentDraftStatus
from foreign_trade_geo_agent.core.content_opportunity import (
    CONTENT_OPPORTUNITY_LIMITATIONS, ContentOpportunityActionCode as Action,
    ContentOpportunityPage, ContentOpportunityPriority, ContentOpportunityReport,
    ContentOpportunitySource, ContentOpportunitySourceMaterial, ContentOpportunitySpecification,
    ContentOpportunityStatus, ContentOpportunityType, finalize_content_opportunity,
)
from foreign_trade_geo_agent.core.crawling import CrawlStopReason
from foreign_trade_geo_agent.core.evidence_intake import (
    ArticleScopeCoverage, CustomerContext, CustomerSubmission, EvidenceRequirement, EvidenceSpan, EvidenceTask,
    IntakeStatus, RequirementDecision, ScopeAdjustment, SemanticAssessment,
    Supplement, SupplementMethod as Method, SupportVerdict as Verdict, snapshot_digest,
)
from foreign_trade_geo_agent.core.extraction import PageExtractionStatus
from foreign_trade_geo_agent.core.research import ResearchEvidenceClassification as Classification
from foreign_trade_geo_agent.core.site_content import SiteContentEvidence, SiteContentPacket
from foreign_trade_geo_agent.storage.evidence_intake import SQLiteEvidenceIntakeStore
from foreign_trade_geo_agent.reporting.evidence_intake import customer_request_json, render_customer_request
from foreign_trade_geo_agent.workflows.content_draft import ContentDraftWorkflow
from foreign_trade_geo_agent.workflows.evidence_intake import EvidenceIntakeWorkflow

NOW = datetime(2026, 10, 9, 4, 0, tzinfo=UTC)
PROJECT, CUSTOMER, TASK = "SYNTHETIC-EXPORT-PACKAGING", "FICTIONAL-CUSTOMER", "EXPLAIN-PACKAGING"
SUBJECTS = ("packing limits", "seal compatibility", "certification scope")
FACTS = (
    "Fictional test only: model Pack-A load limit 12 kg for dry indoor storage; test protocol QA-A.",
    "Fictional test only: Seal-A tested with water at 20-25 C using QA-SEAL-A; no other fluid is supported.",
    "Fictional certificate DEMO-1 from Example Test Body covers Pack-A packaging against fictional standard DEMO-PACK-2026, expires 2027-01-01.",
)


def native_input(subjects=SUBJECTS):
    """Topic-only P/S material deliberately cannot substantiate the required facts."""
    body = ". ".join(SUBJECTS) + "."
    page = SiteContentEvidence(evidence_id="P1", final_url="https://fictional-packaging.example/products/pack-a",
        title="Fictional Pack-A", description="Controlled synthetic fixture", h1=("Packing limits",), h2=(), body_text=body,
        structured_content=(), extraction_status=PageExtractionStatus.SUCCESS, extraction_failure_kind=None,
        structured_content_truncated=False, content_truncated=False)
    packet = SiteContentPacket((page,), 1, CrawlStopReason.COMPLETED, False, False)
    opportunity = finalize_content_opportunity(1, ContentOpportunitySpecification(
        ContentOpportunityType.EXPAND_OBSERVED_CONTENT, ContentOpportunityPriority.HIGH,
        "packing limits", (Action.EXPAND_PAGE_SECTION,), ("P1",), ("S1",)))
    report = ContentOpportunityReport(ContentOpportunityStatus.SUCCESS, (opportunity,),
        (ContentOpportunityPage("P1", page.final_url, page.title),),
        (ContentOpportunitySource("S1", "Fictional packaging topics", "https://fictional-guide.example/topics",
            (Classification.EXTERNAL_RESEARCH_CONTEXT, Classification.UNVERIFIED_SEARCH_RESULT)),),
        CONTENT_OPPORTUNITY_LIMITATIONS, None,
        source_materials=(ContentOpportunitySourceMaterial("S1", "Fictional packaging topics", body, False),))
    prompt = cp.build_change_plan_prompt(cp.ChangePlanInput(packet, report))
    spec = cp.ExpandSectionSpecification("R1", Action.EXPAND_PAGE_SECTION, cp.ChangeOperationType.EXPAND_SECTION,
        ("P1",), ("S1",), cp.SectionLocatorSpecification(cp.SectionLocatorKind.EXACT_OBSERVED_HEADING,
        "P1", "Packing limits"), tuple(cp.ContentPointSpecification(cp.ContentPointIntent.EXPLAIN, s, "P1") for s in subjects))
    operation, error = cp.validate_and_finalize_specification(1, spec, prompt.catalog)
    if error:
        raise AssertionError(error)
    plan = cp.ChangePlanReport(cp.ChangePlanStatus.SUCCESS, (operation,), cp.CHANGE_PLAN_LIMITATIONS, None)
    return ContentDraftInput(packet, report, plan)


def customer_task():
    facts = (
        ("Load rating with units, model, test conditions and limitations", "Explain which shipping loads Pack-A can support"),
        ("Seal material, supported fluids, temperature range and test method", "Explain seal selection and its application limits"),
        ("Certificate identifier, issuer, standard, product scope and validity", "Explain exactly what certification Pack-A holds"),
    )
    return EvidenceTask(PROJECT, CUSTOMER, TASK, 1,
        "Explain packing limits, seal compatibility and certification scope for fictional Pack-A.",
        tuple(EvidenceRequirement(f"F{i+1}", i, fact, use,
            "Existing P1 and S1 only name this topic; they contain no model-specific supporting facts.",
            (Method.CUSTOMER_FACT, Method.TEXT_DOCUMENT)) for i, (fact, use) in enumerate(facts)))


class ScriptedHumanReviewer:
    """Explicit synthetic human decisions, not an automated semantic evaluator."""
    def __init__(self, decisions):
        self.script = decisions
        self.calls = 0
        self.seen = []

    def assess(self, snapshot, *, now):
        self.calls += 1
        self.seen.append(snapshot_digest(snapshot))
        materials = {e.supplement.evidence_id: e.supplement for e in snapshot.active_evidence}
        decisions = []
        for requirement in snapshot.task.requirements:
            verdict, refs, reason = self.script[requirement.requirement_id]
            spans = tuple(EvidenceSpan(ref, 0, len(materials[ref].content), materials[ref].content) for ref in refs)
            decisions.append(RequirementDecision(requirement.requirement_id, verdict, reason, spans))
        return SemanticAssessment(snapshot_digest(snapshot), "SYNTHETIC-HUMAN-REVIEWER", now, tuple(decisions), ArticleScopeCoverage(True, "Explicit synthetic scope review; no human signoff."))


def supported_script():
    return {f"F{i}": (Verdict.SUPPORTED, (f"E{i}",),
        "Explicit fictional human assessment: source, model, limitations and explanatory use reviewed.") for i in range(1, 4)}


class NeverWriter:
    calls = 0
    async def write_content_draft(self, prompt):
        self.calls += 1
        raise AssertionError("Intake candidate must not execute Draft")


class EvidenceIntakeTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "客户资料.sqlite"
        self.store = SQLiteEvidenceIntakeStore.create(self.path)
        self.flow = EvidenceIntakeWorkflow(self.store)
        self.input = native_input()
        self.original = self.flow.register(customer_task(), self.input)
        self.customer = CustomerContext(CUSTOMER, "SYNTHETIC-CUSTOMER-STAFF", NOW)

    def current(self):
        return self.store.latest(PROJECT, TASK)

    def fact(self, i, *, content=None, evidence_id=None, supersedes=None):
        return Supplement(evidence_id or f"E{i}", (f"F{i}",), Method.CUSTOMER_FACT,
            content or FACTS[i-1], "Fictional customer's engineering declaration",
            f"customer-record:pack-a/fact-{i}", "Fictional Packaging Co", supersedes=supersedes)

    def submit(self, *supplements, adjustment=None, expected=None, customer=None, submission_id=None):
        current = self.current()
        value = CustomerSubmission(submission_id or f"SUB-{current.revision}", expected or snapshot_digest(current),
                                   supplements, adjustment)
        return self.flow.submit(PROJECT, TASK, value, customer=customer or self.customer)

    def rebind(self, inp=None, expected=None):
        return self.flow.rebind_plan(PROJECT, TASK, expected_sha256=expected or snapshot_digest(self.current()),
                                     planning_input=inp or self.input)

    def check(self, reviewer=None):
        return EvidenceIntakeWorkflow(self.store, reviewer=reviewer).check(PROJECT, TASK, now=NOW)

    def complete(self):
        self.submit(self.fact(1), self.fact(2), self.fact(3))
        self.rebind()

    def test_initial_insufficient_generates_precise_customer_request_and_no_draft(self):
        result = self.check()
        self.assertEqual(result.status, IntakeStatus.BLOCKED)
        self.assertFalse(result.draft_authorized)
        self.assertEqual([g.requirement.requirement_id for g in result.gaps], ["F1", "F2", "F3"])
        for i, gap in enumerate(result.gaps):
            self.assertEqual(gap.requirement, self.original.task.requirements[i])
            self.assertEqual(gap.point_subject, SUBJECTS[i])
            self.assertEqual(gap.change_ref, "C1")
            self.assertEqual(gap.reason_code, "MISSING_CUSTOMER_EVIDENCE")
            self.assertTrue(gap.requirement.intended_use)
            self.assertIn("P1 and S1", gap.requirement.existing_material_insufficiency)
            self.assertEqual(gap.requirement.allowed_methods, (Method.CUSTOMER_FACT, Method.TEXT_DOCUMENT))
        writer = NeverWriter()
        report = asyncio.run(ContentDraftWorkflow(writer).run(result))
        self.assertEqual(report.status, ContentDraftStatus.INVALID_INPUT)
        self.assertEqual(writer.calls, 0)

    def test_partial_customer_submission_rechecks_remaining_gaps(self):
        changed = self.submit(self.fact(1))
        self.assertFalse(changed.plan_bound)
        self.assertEqual((changed.task.task_version, changed.plan_version, changed.evidence_version), (1, 1, 2))
        blocked = self.check()
        self.assertEqual(blocked.reason, "PLAN_REBIND_REQUIRED")
        self.rebind()
        script = supported_script()
        for r in ("F2", "F3"):
            script[r] = (Verdict.MISSING, (), "Customer has not supplied the required model-specific facts.")
        reviewer = ScriptedHumanReviewer(script)
        result = self.check(reviewer)
        self.assertEqual([g.requirement.requirement_id for g in result.gaps], ["F2", "F3"])
        self.assertEqual(result.status, IntakeStatus.BLOCKED)
        self.assertEqual(reviewer.calls, 1)

    def test_customer_request_has_exact_versions_purpose_remaining_facts_and_no_authority_flag(self):
        request = self.flow.customer_request(PROJECT, TASK, now=NOW)
        raw = json.loads(customer_request_json(request))
        self.assertEqual((raw["task_version"], raw["plan_version"], raw["evidence_version"]), (1, 1, 1))
        self.assertEqual(raw["snapshot_sha256"], snapshot_digest(self.original))
        self.assertEqual(raw["customer_id"], CUSTOMER)
        self.assertEqual(len(raw["gaps"]), 3)
        self.assertNotIn("approved", raw)
        self.assertNotIn("draft_authorized", raw)
        rendered = render_customer_request(request)
        self.assertIn("Certificate identifier", rendered)
        self.assertIn("明确同意", rendered)
        self.assertIn("不授予 Draft", rendered)
        self.submit(self.fact(1))
        self.rebind()
        script = supported_script()
        script.update({r: (Verdict.MISSING, (), "Still missing") for r in ("F2", "F3")})
        flow = EvidenceIntakeWorkflow(self.store, reviewer=ScriptedHumanReviewer(script))
        updated = flow.customer_request(PROJECT, TASK, now=NOW)
        self.assertEqual([g.requirement.requirement_id for g in updated.gaps], ["F2", "F3"])
        self.assertEqual((updated.task_version, updated.plan_version, updated.evidence_version), (1, 2, 2))

    def test_snapshot_digest_binds_every_task_plan_source_and_scope_field(self):
        original = snapshot_digest(self.original)
        page = self.input.site_content.pages[0]
        source = self.input.opportunity_report.source_materials[0]
        variants = [replace(self.original, task=replace(self.original.task, goal="Different customer objective")),
            replace(self.original, task=replace(self.original.task, task_version=2)),
            replace(self.original, plan_version=2), replace(self.original, evidence_version=2),
            replace(self.original, planning_input=replace(self.input, target_language="zh")),
            replace(self.original, planning_input=replace(self.input, site_content=replace(self.input.site_content,
                pages=(replace(page, body_text=page.body_text+" Changed evidence."),)))),
            replace(self.original, planning_input=replace(self.input, opportunity_report=replace(self.input.opportunity_report,
                source_materials=(replace(source, content=source.content+" Changed context."),))))]
        for variant in variants:
            self.assertNotEqual(snapshot_digest(variant), original)

    def test_contract_size_types_upload_digest_and_method_limits_fail_closed(self):
        for changes in ({"content": "x"*16001}, {"method": "CUSTOMER_FACT"}, {"file_sha256": "0"*64},
                        {"requirement_ids": ["F1"]}, {"content": "secret\x00canary"}):
            with self.subTest(field=tuple(changes)), self.assertRaisesRegex(ValueError, "EVIDENCE_INTAKE_INVALID"):
                replace(self.fact(1), **changes)
        with self.assertRaises(TypeError):
            CustomerSubmission("FORGED", snapshot_digest(self.original), (self.fact(1),), approved=True)
        with self.assertRaises(ValueError):
            replace(self.original.task, task_version=True)
        with self.assertRaises(ValueError):
            replace(self.customer, recorded_at=NOW.replace(tzinfo=None))
        single_method_task = replace(customer_task(), task_id="FACTS-ONLY", requirements=tuple(
            replace(r, allowed_methods=(Method.CUSTOMER_FACT,)) for r in customer_task().requirements))
        current = self.flow.register(single_method_task, self.input)
        doc = text_document(evidence_id="DOC", requirement_ids=("F1",), payload=FACTS[0].encode(),
                            source_label="test", source_locator="upload:test", declared_source_owner="Fictional QA")
        submission = CustomerSubmission("UPLOAD", snapshot_digest(current), (doc,))
        with self.assertRaisesRegex(ValueError, "CUSTOMER_SUBMISSION_REJECTED"):
            self.flow.submit(PROJECT, "FACTS-ONLY", submission, customer=self.customer)

    def test_scope_remaps_retained_point_and_preserves_removed_evidence_history(self):
        self.submit(self.fact(1), self.fact(2), self.fact(3))
        self.submit(adjustment=ScopeAdjustment("Explain only seal compatibility for fictional Pack-A.",
            ("F2",), "Customer explicitly removes packing and certification obligations.", True))
        current = self.current()
        self.assertEqual(current.task.requirements[0].point_index, 0)
        self.assertEqual(current.point_subjects, (SUBJECTS[1],))
        self.assertEqual(len(current.evidence), 3)
        self.rebind(native_input((SUBJECTS[1],)))
        reviewer = ScriptedHumanReviewer({"F2": supported_script()["F2"]})
        self.assertEqual(self.check(reviewer).status, IntakeStatus.CANDIDATE_FOR_REVIEW)

    def test_all_materials_require_fresh_plan_and_human_semantic_assessment(self):
        self.submit(self.fact(1), self.fact(2), self.fact(3))
        reviewer = ScriptedHumanReviewer(supported_script())
        self.assertEqual(self.check(reviewer).reason, "PLAN_REBIND_REQUIRED")
        rebound = self.rebind()
        self.assertEqual(rebound.plan_version, 2)
        self.assertEqual(self.check().status, IntakeStatus.BLOCKED)
        self.assertEqual(len(self.check().gaps), 3)
        result = self.check(reviewer)
        self.assertEqual(result.status, IntakeStatus.CANDIDATE_FOR_REVIEW)
        self.assertEqual(result.gaps, ())
        self.assertFalse(result.draft_authorized)
        self.assertEqual(result.assessment.snapshot_sha256, snapshot_digest(rebound))
        writer = NeverWriter()
        self.assertEqual(asyncio.run(ContentDraftWorkflow(writer).run(result)).status, ContentDraftStatus.INVALID_INPUT)
        self.assertEqual(writer.calls, 0)

    def test_evidence_and_plan_history_are_immutable_and_roundtrip_traceable(self):
        self.submit(self.fact(1))
        self.rebind()
        self.submit(self.fact(2), self.fact(3))
        rebound = self.rebind()
        reopened = SQLiteEvidenceIntakeStore(self.path)
        self.assertEqual(reopened.latest(PROJECT, TASK), rebound)
        self.assertEqual(reopened.get_revision(PROJECT, TASK, 1), self.original)
        self.assertEqual([e.evidence_version for e in rebound.evidence], [2, 3, 3])
        self.assertEqual(rebound.plan_version, 3)
        for record in rebound.evidence:
            self.assertEqual(record.customer_id, CUSTOMER)
            self.assertEqual(record.actor_id, self.customer.actor_id)
            self.assertEqual(record.recorded_at, NOW)
            self.assertTrue(record.submission_id)
            self.assertTrue(record.supplement.source_locator)
        self.check()
        with closing(sqlite3.connect(self.path)) as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM intake_snapshots").fetchone(), (5,))
            for sql in ("DELETE FROM intake_snapshots", "UPDATE intake_snapshots SET digest='changed'",
                        "DELETE FROM intake_checks"):
                # A trigger is exercised with an existing row.
                with self.assertRaises(sqlite3.IntegrityError):
                    conn.execute(sql)
                conn.rollback()

    def test_old_candidate_review_plan_binding_and_stale_submission_cannot_be_reused(self):
        self.complete()
        reviewer = ScriptedHumanReviewer(supported_script())
        old = self.check(reviewer)
        old_snapshot = self.current()
        stale_assessment = old.assessment
        self.submit(self.fact(1, evidence_id="E1-v2", content=FACTS[0]+" Revised scope.", supersedes="E1"))
        self.assertNotEqual(snapshot_digest(self.current()), old.snapshot_sha256)
        with self.assertRaisesRegex(ValueError, "CUSTOMER_SUBMISSION_REJECTED"):
            self.submit(self.fact(2, evidence_id="stale"), expected=old.snapshot_sha256)
        with self.assertRaisesRegex(ValueError, "PLAN_REBIND_REJECTED"):
            self.rebind(expected=old.snapshot_sha256)
        with self.assertRaisesRegex(ValueError, "INTAKE_STORE_CHECK_REJECTED"):
            self.store.append_check(PROJECT, TASK, old)
        self.assertEqual(self.check(reviewer).reason, "PLAN_REBIND_REQUIRED")
        self.rebind()
        class Replay:
            def assess(self, *args, **kwargs):
                return stale_assessment
        result = self.check(Replay())
        self.assertEqual(result.status, IntakeStatus.BLOCKED)
        self.assertIsNone(result.assessment)
        self.assertEqual(self.store.get_revision(PROJECT, TASK, old_snapshot.revision), old_snapshot)

    def test_irrelevant_material_never_satisfies_fact_even_with_matching_topics(self):
        self.submit(self.fact(1, content="Packing limits seal compatibility certification scope are topics."))
        self.rebind()
        script = {"F1": (Verdict.IRRELEVANT, ("E1",), "Topic list supplies no rating, model or test conditions."),
                  "F2": (Verdict.MISSING, (), "Missing seal test."), "F3": (Verdict.MISSING, (), "Missing certificate.")}
        result = self.check(ScriptedHumanReviewer(script))
        self.assertEqual(result.status, IntakeStatus.BLOCKED)
        self.assertEqual(result.gaps[0].reason_code, "IRRELEVANT")
        self.assertIn("no rating", result.gaps[0].review_reason)

    def test_contradictory_material_remains_visible_and_blocks_until_reviewed_correction(self):
        self.complete()
        self.submit(self.fact(1, evidence_id="E1-conflict", content="Fictional Pack-A limit is 30 kg under QA-A."))
        self.rebind()
        script = supported_script()
        script["F1"] = (Verdict.CONFLICT, ("E1", "E1-conflict"), "Different ratings for same model and protocol; customer must resolve.")
        result = self.check(ScriptedHumanReviewer(script))
        self.assertEqual(result.status, IntakeStatus.BLOCKED)
        self.assertEqual(result.gaps[0].reason_code, "CONFLICT")
        self.assertEqual(len(self.current().active_evidence), 4)
        self.submit(self.fact(1, evidence_id="E1-corrected", supersedes="E1-conflict"))
        self.rebind()
        script["F1"] = (Verdict.SUPPORTED, ("E1", "E1-corrected"), "Fictional human reviewed explicit correction and both remaining ratings.")
        self.assertEqual(self.check(ScriptedHumanReviewer(script)).status, IntakeStatus.CANDIDATE_FOR_REVIEW)
        self.assertEqual(len(self.current().evidence), 5)
        self.assertEqual(len(self.current().active_evidence), 4)

    def test_no_scope_adjustment_without_explicit_customer_consent(self):
        old = self.current()
        for consents in (False,):
            with self.assertRaisesRegex(ValueError, "CUSTOMER_SUBMISSION_REJECTED"):
                self.submit(adjustment=ScopeAdjustment("Explain only packing limits.", ("F1",), "Drop other sections", consents))
        self.assertEqual(self.current(), old)
        # Changing the Plan alone cannot delete obligations or switch intent.
        self.submit(self.fact(1))
        with self.assertRaisesRegex(ValueError, "PLAN_REBIND_REJECTED"):
            self.rebind(native_input((SUBJECTS[0],)))
        changed_op = replace(self.input.change_plan_report.operations[0], content_points=tuple(
            replace(p, intent=cp.ContentPointIntent.DESCRIBE) for p in self.input.change_plan_report.operations[0].content_points))
        with self.assertRaisesRegex(ValueError, "PLAN_REBIND_REJECTED"):
            self.rebind(replace(self.input, change_plan_report=replace(self.input.change_plan_report, operations=(changed_op,))))

    def test_explicit_scope_consent_versions_task_and_requires_matching_new_plan(self):
        changed = self.submit(self.fact(1), adjustment=ScopeAdjustment("Explain only packing limits for fictional Pack-A.",
            ("F1",), "Customer cancels seal and certification sections explicitly.", True))
        self.assertEqual(changed.task.task_version, 2)
        self.assertEqual(changed.point_subjects, (SUBJECTS[0],))
        consent = changed.scope_consents[0]
        self.assertEqual(consent.previous_snapshot_sha256, snapshot_digest(self.original))
        self.assertEqual(consent.context, self.customer)
        self.assertEqual(consent.adjustment.retained_requirement_ids, ("F1",))
        with self.assertRaisesRegex(ValueError, "PLAN_REBIND_REJECTED"):
            self.rebind()
        self.rebind(native_input((SUBJECTS[0],)))
        script = {"F1": supported_script()["F1"]}
        result = self.check(ScriptedHumanReviewer(script))
        self.assertEqual(result.status, IntakeStatus.CANDIDATE_FOR_REVIEW)
        self.assertFalse(result.draft_authorized)

    def test_no_partial_weakening_within_retained_explanation(self):
        extra = replace(self.original.task.requirements[0], requirement_id="F1-test")
        new_task = replace(customer_task(), task_id="GROUPED", requirements=(self.original.task.requirements[0], extra,
            *self.original.task.requirements[1:]))
        grouped = self.flow.register(new_task, self.input)
        submission = CustomerSubmission("GROUP-CHANGE", snapshot_digest(grouped), scope_adjustment=ScopeAdjustment(
            "Explain packing limits", ("F1",), "Omit supporting test condition", True))
        with self.assertRaisesRegex(ValueError, "CUSTOMER_SUBMISSION_REJECTED"):
            self.flow.submit(PROJECT, "GROUPED", submission, customer=self.customer)

    def test_utf8_upload_preserves_exact_bytes_digest_locator_and_requires_review(self):
        payload = (FACTS[0]+"\r\n客户签注：仅限虚构测试。").encode("utf-8")
        document = text_document(evidence_id="E1", requirement_ids=("F1",), payload=payload,
            source_label="pack-a-test.txt", source_locator="upload:synthetic-document-v1", declared_source_owner="Fictional QA")
        self.assertEqual(document.content.encode("utf-8"), payload)
        self.assertEqual(document.file_sha256, hashlib.sha256(payload).hexdigest())
        self.submit(document)
        self.assertEqual(self.current().evidence[0].supplement, document)
        self.assertEqual(self.check().status, IntakeStatus.BLOCKED)
        pending_request = self.flow.customer_request(PROJECT, TASK, now=NOW)
        self.assertIn("无需为此重复提交", render_customer_request(pending_request))
        for bad in (b"\xff", b"%PDF-1.7\x00", b"a"*64001, b""):
            with self.subTest(length=len(bad)), self.assertRaisesRegex(ValueError, "CUSTOMER_TEXT_DOCUMENT_REJECTED"):
                text_document(evidence_id="bad", requirement_ids=("F1",), payload=bad,
                    source_label="bad", source_locator="upload:bad", declared_source_owner="Customer")

    def test_customer_identity_unknown_fact_and_duplicate_submission_rejected_without_writes(self):
        old = self.current()
        for supplement, customer in ((self.fact(1), replace(self.customer, customer_id="OTHER-CUSTOMER")),
                                    (replace(self.fact(1), requirement_ids=("UNKNOWN",)), self.customer)):
            with self.assertRaisesRegex(ValueError, "CUSTOMER_SUBMISSION_REJECTED"):
                self.submit(supplement, customer=customer)
            self.assertEqual(self.current(), old)
        self.submit(self.fact(1), submission_id="ONCE")
        with self.assertRaisesRegex(ValueError, "CUSTOMER_SUBMISSION_REJECTED"):
            self.submit(self.fact(2), submission_id="ONCE")
        with self.assertRaisesRegex(ValueError, "CUSTOMER_SUBMISSION_REJECTED"):
            self.submit(self.fact(1))

    def test_assessment_wrong_versions_spans_coverage_times_and_failures_fail_closed(self):
        self.complete()
        valid = ScriptedHumanReviewer(supported_script()).assess(self.current(), now=NOW)
        variants = [replace(valid, snapshot_sha256="0"*64), replace(valid, decisions=valid.decisions[:-1]),
                    replace(valid, decisions=valid.decisions[::-1]), replace(valid, reviewed_at=NOW+timedelta(seconds=1)),
                    replace(valid, reviewed_at=NOW-timedelta(minutes=6))]
        for change in ({"quote": "Unsupported certification"}, {"evidence_id": "E2"}, {"end": 16000},
                       {"evidence_id": "UNKNOWN"}):
            span = replace(valid.decisions[0].spans[0], **change)
            variants.append(replace(valid, decisions=(replace(valid.decisions[0], spans=(span,)), *valid.decisions[1:])))
        class Bad:
            def assess(self, *args, **kwargs):
                return self.value
        for variant in variants:
            reviewer = Bad(); reviewer.value = variant
            result = self.check(reviewer)
            self.assertEqual(result.status, IntakeStatus.BLOCKED)
            self.assertIsNone(result.assessment)
        class Unavailable:
            def assess(self, *args, **kwargs):
                raise RuntimeError("SECRET-CANARY")
        result = self.check(Unavailable())
        self.assertEqual(result.status, IntakeStatus.BLOCKED)
        self.assertNotIn("SECRET-CANARY", str(result))

    def test_review_is_fresh_every_time_and_concurrent_change_discards_candidate(self):
        self.complete()
        reviewer = ScriptedHumanReviewer(supported_script())
        self.assertEqual(self.check(reviewer).status, IntakeStatus.CANDIDATE_FOR_REVIEW)
        self.assertEqual(self.check(reviewer).status, IntakeStatus.CANDIDATE_FOR_REVIEW)
        self.assertEqual(reviewer.calls, 2)
        owner = self
        class Racing:
            def assess(self, snapshot, *, now):
                review = reviewer.assess(snapshot, now=now)
                owner.submit(owner.fact(1, evidence_id="RACE", supersedes="E1"))
                return review
        before = len(self.store.checks(PROJECT, TASK))
        with self.assertRaisesRegex(ValueError, "INTAKE_CHECK_REJECTED"):
            self.check(Racing())
        self.assertEqual(len(self.store.checks(PROJECT, TASK)), before)
        self.assertFalse(self.current().plan_bound)

    def test_registration_requires_complete_fact_obligations_and_native_valid_plan(self):
        for requirements in (customer_task().requirements[:1], customer_task().requirements[1:]):
            task = replace(customer_task(), task_id="INCOMPLETE", requirements=requirements)
            with self.assertRaisesRegex(ValueError, "INTAKE_REGISTRATION_REJECTED"):
                self.flow.register(task, self.input)
        with self.assertRaisesRegex(ValueError, "INTAKE_REGISTRATION_REJECTED"):
            self.flow.register(customer_task(), self.input)
        op = self.input.change_plan_report.operations[0]
        wrong = replace(op, content_points=(replace(op.content_points[0], subject="unobserved product capability"), *op.content_points[1:]))
        value = replace(self.input, change_plan_report=replace(self.input.change_plan_report, operations=(wrong,)))
        with self.assertRaisesRegex(ValueError, "INTAKE_REGISTRATION_REJECTED"):
            self.flow.register(replace(customer_task(), task_id="UNGROUNDED"), value)

    def test_store_cas_and_direct_history_rewrite_or_plan_shortcut_rejected(self):
        current = self.submit(self.fact(1))
        with self.assertRaisesRegex(ValueError, "INTAKE_STORE_APPEND_REJECTED"):
            self.store.append(snapshot_digest(self.original), replace(current, revision=3))
        for changes in ({"task": replace(current.task, goal="Silently shortened goal")},
                        {"plan_bound": True}, {"evidence": ()}):
            with self.assertRaisesRegex(ValueError, "INTAKE_STORE_APPEND_REJECTED"):
                self.store.append(snapshot_digest(current), replace(current, revision=current.revision+1, **changes))
        self.assertEqual(self.current(), current)

    def test_store_schema_tampering_and_creation_overwrite_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "INTAKE_STORE_CREATION_REJECTED"):
            SQLiteEvidenceIntakeStore.create(self.path)
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute("DROP TRIGGER intake_snapshots_no_update")
            conn.commit()
        with self.assertRaisesRegex(ValueError, "INTAKE_STORE_UNAVAILABLE"):
            SQLiteEvidenceIntakeStore(self.path)
        with self.assertRaisesRegex(ValueError, "INTAKE_CHECK_REJECTED"):
            self.check()

    def test_roundtrip_digest_normalizes_timezone_and_rejects_unknown_or_duplicate_json(self):
        self.customer = replace(self.customer, recorded_at=NOW.astimezone(timezone(timedelta(hours=8))))
        supplied = self.submit(self.fact(1))
        self.assertEqual(snapshot_digest(supplied), snapshot_digest(self.current()))
        # New journal only: mutate an isolated copy after disabling its trigger.
        with closing(sqlite3.connect(self.path)) as conn:
            raw = conn.execute("SELECT payload FROM intake_snapshots WHERE revision=2").fetchone()[0]
            conn.execute("DROP TRIGGER intake_snapshots_no_update")
            # Schema is restored exactly after the deliberately corrupted write.
            from foreign_trade_geo_agent.storage.evidence_intake import _TRIGGERS
            for malformed in (raw[:-1]+',"revision":2}', json.dumps({**json.loads(raw), "approved": True})):
                conn.execute("UPDATE intake_snapshots SET payload=? WHERE revision=2", (malformed,))
                conn.execute(_TRIGGERS["intake_snapshots_no_update"])
                conn.commit()
                with self.assertRaisesRegex(ValueError, "INTAKE_STORE_READ_REJECTED"):
                    self.current()
                conn.execute("DROP TRIGGER intake_snapshots_no_update")
