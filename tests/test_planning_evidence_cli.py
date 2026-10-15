"""Synthetic NovaCNC business handoff; real native workflows, no live ports."""
import asyncio
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, datetime, timedelta
from io import StringIO
import json
import os
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import uuid4

from scripts.demo_seo_evidence import (
    CUSTOMER, GOAL, LocalFetcher, LocalSearch, LocalResearch, LocalOpportunity, LocalPlan,
    NeverDraft, prepare,
)
from foreign_trade_geo_agent.cli import main
from foreign_trade_geo_agent.core.evidence_intake import (
    ArticleScopeCoverage,
    EvidenceSpan, RequirementDecision, SemanticAssessment, SupportVerdict, snapshot_digest,
)
from foreign_trade_geo_agent.storage.evidence_intake import SQLiteEvidenceIntakeStore
from foreign_trade_geo_agent.storage.sqlite import SQLiteHistoryReader
from foreign_trade_geo_agent.workflows.content_draft import ContentDraftWorkflow
from foreign_trade_geo_agent.workflows.evidence_intake import EvidenceIntakeWorkflow, EvidenceIntakeDraftAdmission
from foreign_trade_geo_agent.runtime import build_planning_workflow


class PlanningEvidenceCLITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = TemporaryDirectory()
        cls.addClassCleanup(cls.fixture.cleanup)
        cls.fixture_dir = Path(cls.fixture.name) / "synthetic"
        cls.meta = prepare(cls.fixture_dir)

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        for path in self.fixture_dir.iterdir():
            shutil.copyfile(path, self.directory / path.name)
        self.db = self.directory / "history.sqlite3"
        self.journal = self.directory / "intake.sqlite3"
        self.run_id, self.plan_id = self.meta["run_id"], self.meta["plan_id"]
        self.store = SQLiteEvidenceIntakeStore(self.journal)

    def call(self, action, *extra, expected=0):
        out, err = StringIO(), StringIO()
        args = ["evidence", action, "--run-id", self.run_id, "--plan-id", self.plan_id,
            "--db", str(self.db), "--intake-db", str(self.journal), *map(str, extra)]
        with redirect_stdout(out), redirect_stderr(err), patch(
                "foreign_trade_geo_agent.cli.load_runtime_environment", side_effect=AssertionError("Offline evidence must not load credentials")):
            code = main(args)
        self.assertEqual(code, expected, err.getvalue())
        return out.getvalue(), err.getvalue()

    def status(self):
        return json.loads(self.call("show")[0])

    def current(self):
        return self.store.latest(self.run_id, self.plan_id)

    def submit(self, body=None, expected=0):
        if body is not None:
            (self.directory / "submission.json").write_text(json.dumps(body), encoding="utf-8")
        return self.call("submit", "--customer-id", CUSTOMER, "--file", self.directory / "submission.json", expected=expected)

    def recheck(self, digest=None, expected=0):
        return self.call("recheck", "--expected-sha256", digest or snapshot_digest(self.current()), expected=expected)

    def body(self):
        return json.loads((self.directory / "submission.json").read_text(encoding="utf-8"))

    def test_missing_task_has_exact_goal_origin_and_specific_gaps(self):
        status = self.status()
        self.assertEqual(status["state"], "WAITING_FOR_EVIDENCE")
        self.assertEqual(status["request"]["goal"], GOAL)
        self.assertEqual(status["origin_artifacts"]["change_plan"], self.plan_id)
        self.assertEqual({g["reason_code"] for g in status["request"]["gaps"]}, {"MISSING_CUSTOMER_EVIDENCE"})
        self.assertEqual(len(status["request"]["gaps"]), 3)
        self.assertFalse(status["draft_authorized"])
        text, _ = self.call("show", "--format", "text")
        self.assertIn("Spindle rating, duty, model", text)

    def test_submit_recheck_review_preserves_sources_and_new_epoch(self):
        original = self.current()
        submitted = json.loads(self.submit()[0])
        self.assertEqual(submitted["submission_status"], "SUBMITTED")
        self.assertEqual(submitted["state"], "RECHECK_REQUIRED")
        self.assertFalse(submitted["plan_bound"])
        self.assertEqual(self.current().planning_input, original.planning_input)
        pending = json.loads(self.recheck()[0])
        self.assertEqual(pending["state"], "WAITING_FOR_HUMAN_REVIEW")
        self.assertEqual(pending["evidence_candidate_status"], "AVAILABLE_FOR_HUMAN_REVIEW")
        self.assertFalse(pending["customer_action_required"])
        self.assertFalse(pending["draft_authorized"])
        current = self.current()
        self.assertEqual((current.revision, current.plan_version, current.evidence_version), (3, 2, 2))
        self.assertEqual(current.planning_input.site_content, original.planning_input.site_content)
        self.assertEqual(current.planning_input.opportunity_report, original.planning_input.opportunity_report)
        self.assertEqual(current.planning_input.change_plan_report.operations,
                         original.planning_input.change_plan_report.operations)
        candidate = json.loads(self.call("review")[0])
        self.assertEqual(set(candidate["claim_verdicts"].values()), {"UNREVIEWED"})
        self.assertEqual(candidate["check"]["snapshot_sha256"], snapshot_digest(current))
        for expected, record in zip(self.body()["supplements"], current.evidence):
            self.assertEqual(record.supplement.content, expected["content"])
            self.assertEqual(record.supplement.file_sha256, expected["file_sha256"])
            self.assertEqual(record.supplement.source_locator, expected["source_locator"])
            self.assertEqual(record.actor_id, "LOCAL-OPERATOR")

    def test_partial_submission_requests_only_remaining_materials(self):
        body = self.body()
        body["supplements"] = body["supplements"][:1]
        self.submit(body)
        self.recheck()
        status = self.status()
        self.assertEqual(status["state"], "WAITING_FOR_EVIDENCE")
        missing = [g["requirement"]["requirement_id"] for g in status["request"]["gaps"]
                   if g["reason_code"] == "MISSING_CUSTOMER_EVIDENCE"]
        self.assertEqual(missing, ["F2", "F3"])
        text, _ = self.call("show", "--format", "text")
        self.assertIn("无需为此重复提交", text)

    def test_stale_submission_and_recheck_do_not_mutate_snapshot(self):
        old = snapshot_digest(self.current())
        self.submit()
        submitted = self.current()
        self.submit(expected=2)
        self.recheck(old, expected=2)
        self.assertEqual(self.current(), submitted)
        self.recheck()
        self.assertEqual(self.current().revision, 3)

    def test_review_before_recheck_is_refused_and_recovery_is_idempotent(self):
        self.submit()
        self.call("review", expected=2)
        self.assertEqual(self.status()["state"], "RECHECK_REQUIRED")
        self.recheck()
        bound = self.current()
        self.recheck()
        self.assertEqual(self.current(), bound)

    def test_customer_json_cannot_supply_authority_or_actor(self):
        for key in ("actor_id", "recorded_at", "reviewer_id", "draft_authorized"):
            with self.subTest(key=key):
                body = self.body()
                body[key] = "FORGED"
                self.submit(body, expected=2)
                self.assertEqual(self.current().revision, 1)
                # Restore the original fixture for the next boundary probe.
                shutil.copyfile(self.fixture_dir / "submission.json", self.directory / "submission.json")

    def test_wrong_customer_plan_and_repeat_registration_are_refused(self):
        self.call("submit", "--customer-id", "WRONG-CUSTOMER", "--file", self.directory / "submission.json", expected=2)
        self.call("open", "--customer-id", CUSTOMER, "--requirements", self.directory / "requirements.json", expected=2)
        self.call("show", "--plan-id", str(uuid4()), expected=2)
        self.assertEqual(self.current().revision, 1)

    def test_empty_or_incomplete_obligations_cannot_create_task(self):
        for requirements in ([], json.loads((self.directory / "requirements.json").read_text())[:1]):
            other = self.directory / f"other-{len(requirements)}.sqlite3"
            path = self.directory / "invalid-requirements.json"
            path.write_text(json.dumps(requirements), encoding="utf-8")
            self.call("open", "--intake-db", other, "--customer-id", CUSTOMER,
                      "--requirements", path, expected=2)
            with self.assertRaises(ValueError):
                SQLiteEvidenceIntakeStore(other).latest(self.run_id, self.plan_id)

    def test_bound_check_never_allows_bad_or_stale_evidence_into_draft(self):
        self.submit()
        self.recheck()
        now = datetime.now(UTC)
        current = self.current()
        class Reviewer:
            def __init__(self, verdict, age):
                self.verdict, self.age = verdict, age
            def assess(self, snapshot, *, now):
                decisions = tuple(RequirementDecision(r.requirement_id, self.verdict,
                    "SYNTHETIC explicit human decision; no execution authorization",
                    tuple(EvidenceSpan(e.supplement.evidence_id, 0, len(e.supplement.content), e.supplement.content)
                          for e in snapshot.active_evidence if r.requirement_id in e.supplement.requirement_ids))
                    for r in snapshot.task.requirements)
                return SemanticAssessment(snapshot_digest(snapshot), "SYNTHETIC-HUMAN", now - self.age, decisions, ArticleScopeCoverage(True, "Explicit synthetic scope review; no human signoff."))
        for verdict, age in ((SupportVerdict.MISSING, timedelta()), (SupportVerdict.CONFLICT, timedelta()),
                             (SupportVerdict.IRRELEVANT, timedelta()), (SupportVerdict.UNREVIEWED, timedelta()),
                             (SupportVerdict.SUPPORTED, timedelta(minutes=6)), (SupportVerdict.SUPPORTED, timedelta())):
            with self.subTest(verdict=verdict, age=age):
                flow = EvidenceIntakeWorkflow(self.store, reviewer=Reviewer(verdict, age))
                checked = flow.check(self.run_id, self.plan_id, now=now)
                if verdict is SupportVerdict.SUPPORTED and not age:
                    self.assertFalse(checked.gaps)  # Sufficient evidence needs no repeat upload.
                    self.assertEqual(checked.status.value, "CANDIDATE_FOR_REVIEW")
                else:
                    self.assertEqual(checked.status.value, "BLOCKED")
                writer = NeverDraft()
                draft = ContentDraftWorkflow(writer, intake_admission=EvidenceIntakeDraftAdmission(
                    self.store, self.run_id, self.plan_id, expected_snapshot_sha256=snapshot_digest(current)))
                report = asyncio.run(draft.run(current.planning_input))
                self.assertEqual(report.error, "INTAKE_EXECUTION_BLOCKED")
                self.assertEqual(writer.calls, 0)

    def test_new_evidence_invalidates_old_supported_review_and_binding(self):
        self.submit()
        self.recheck()
        old = self.current()
        class PriorHumanReview:
            def assess(self, snapshot, *, now):
                decisions = tuple(RequirementDecision(r.requirement_id, SupportVerdict.SUPPORTED,
                    "SYNTHETIC human review of the old evidence version only",
                    tuple(EvidenceSpan(e.supplement.evidence_id, 0, len(e.supplement.content), e.supplement.content)
                          for e in snapshot.active_evidence if r.requirement_id in e.supplement.requirement_ids))
                    for r in snapshot.task.requirements)
                return SemanticAssessment(snapshot_digest(snapshot), "SYNTHETIC-HUMAN", now, decisions, ArticleScopeCoverage(True, "Explicit synthetic scope review; no human signoff."))
        prior = EvidenceIntakeWorkflow(self.store, reviewer=PriorHumanReview()).check(
            self.run_id, self.plan_id, now=datetime.now(UTC))
        self.assertEqual(prior.status.value, "CANDIDATE_FOR_REVIEW")
        body = self.body()
        body["submission_id"] = "SYNTHETIC-REPLACEMENT"
        body["expected_snapshot_sha256"] = snapshot_digest(old)
        body["supplements"] = [dict(body["supplements"][0], evidence_id="E1-V2", supersedes="E1")]
        self.submit(body)
        self.recheck()
        current = self.current()
        self.assertEqual((current.evidence_version, current.plan_version), (3, 3))
        self.assertEqual(len(current.evidence), 4)
        self.assertEqual(len(current.active_evidence), 3)
        self.assertNotEqual(snapshot_digest(current), snapshot_digest(old))
        self.assertIn(prior, self.store.checks(self.run_id, self.plan_id))
        self.assertEqual(set(json.loads(self.call("review")[0])["claim_verdicts"].values()), {"UNREVIEWED"})
        guard = EvidenceIntakeDraftAdmission(self.store, self.run_id, self.plan_id,
                                             expected_snapshot_sha256=snapshot_digest(old))
        self.assertEqual(guard.rejection_reason(old.planning_input), "STALE_INTAKE_BINDING")

    def test_main_plan_opt_in_hands_off_without_hiding_original_draft_refusal(self):
        db = self.directory / "main-plan.sqlite3"
        journal = self.directory / "main-intake.sqlite3"
        writer = NeverDraft()
        def factory(path):
            return build_planning_workflow(path, fetcher=LocalFetcher(), search_provider=LocalSearch(),
                research_writer=LocalResearch(), content_opportunity_writer=LocalOpportunity(),
                change_plan_writer=LocalPlan(), content_draft_writer=writer)
        out, err = StringIO(), StringIO()
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "synthetic-unused", "TAVILY_API_KEY": "synthetic-unused"}), \
                patch("foreign_trade_geo_agent.cli.load_runtime_environment"), redirect_stdout(out), redirect_stderr(err):
            code = main(["plan", "--site", "https://novacnc.example/", "--question", GOAL,
                "--db", str(db), "--intake-db", str(journal), "--customer-id", CUSTOMER,
                "--evidence-requirements", str(self.directory / "requirements.json")], planning_factory=factory)
        self.assertEqual(code, 1, err.getvalue())
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["status"], "failed")
        self.assertEqual(payload["validation_diagnostic"]["category"], "INTAKE_EXECUTION_BLOCKED")
        self.assertEqual(payload["evidence_intake"]["state"], "WAITING_FOR_EVIDENCE")
        self.assertEqual(writer.calls, 0)
        self.assertEqual(SQLiteHistoryReader(db).get_run(payload["run_id"]).failure_kind, "content_draft.invalid_input")


if __name__ == "__main__":
    unittest.main()
