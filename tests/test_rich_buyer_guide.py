"""Honest readiness detection for rich customer evidence, entirely offline."""
import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts import accept_rich_buyer_guide as case
from scripts import novacnc_buyer_fixture as fixture
from foreign_trade_geo_agent.core import content_draft as cd
from foreign_trade_geo_agent.core.evidence_intake import IntakeSnapshot, SemanticAssessment, validate_assessment
from foreign_trade_geo_agent.storage.serialization import _decode
from foreign_trade_geo_agent.workflows.content_draft import ContentDraftWorkflow


class RichBuyerGuideTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.directory = Path(cls.temp.name) / "independent-case"
        cls.summary = case.prepare(cls.directory)
        cls.rich = cls.directory / "B-rich-evidence"

    def read(self, name, root=None):
        return json.loads(((root or self.rich) / name).read_bytes())

    def test_materials_have_independent_facts_complete_traceability_and_reused_E1(self):
        materials = self.directory / "customer-materials"
        facts = self.read("facts.json", materials)
        docs = self.read("documents.json", materials)
        self.assertEqual(len(docs), 7)
        self.assertEqual(len(facts), len({r["fact_id"] for r in facts}))
        self.assertGreaterEqual(len(facts), 40)
        lookup = {r["evidence_id"]: r for r in docs}
        for row in facts:
            self.assertEqual(lookup[row["evidence_id"]]["content"][row["span_start"]:row["span_end"]], row["quote"])
            self.assertEqual(row["file_sha256"], case.sha((materials / row["source_file"]).read_bytes()))
            self.assertTrue(row["synthetic_only"])
        frozen = case.legacy.load_frozen().active_evidence[0].supplement
        self.assertEqual(lookup["E1"]["content"], frozen.content)
        self.assertEqual(lookup["E1"]["source_locator"], frozen.source_locator)
        self.assertEqual(lookup["E1"]["file_sha256"], frozen.file_sha256)
        self.assertNotEqual(lookup["E1"]["requirement_ids"], list(frozen.requirement_ids))
        checks = self.read("consistency-checks.json", materials)
        self.assertFalse(checks["engineering_certification"])
        self.assertFalse(checks["actual_customer_approval"])

    def test_low_evidence_guide_stays_blocked_and_historical_bytes_stay_unchanged(self):
        check = self.read("scope-and-evidence-review.json", self.directory / "A-low-evidence")
        self.assertEqual(check["status"], "BLOCKED")
        self.assertEqual([r["requirement"]["requirement_id"] for r in check["gaps"]], ["F2", "F3", "F4", "F5"])
        self.assertEqual(self.read("historical-hashes-before.json", self.directory), self.read("historical-hashes-after.json", self.directory))

    def test_intake_replan_preserves_full_customer_documents_and_version_binding(self):
        snapshot = _decode(self.read("snapshot.json"), IntakeSnapshot)
        review = self.read("04-test-only-review.json")
        self.assertEqual(snapshot.task.goal, fixture.GOAL)
        self.assertEqual((snapshot.task.task_version, snapshot.plan_version, snapshot.evidence_version, snapshot.revision), (1, 2, 2, 3))
        self.assertTrue(snapshot.plan_bound)
        self.assertEqual(review["status"], "CANDIDATE_FOR_REVIEW")
        self.assertEqual(len(review["assessment"]["decisions"]), 8)
        self.assertEqual(review["gaps"], [])
        material = self.read("02-native-replan-material.json")
        records = material["customer_evidence_intake"]["records"]
        self.assertEqual(tuple(r["supplement"]["content"] for r in records), tuple(e.supplement.content for e in snapshot.active_evidence))
        self.assertTrue(all(r["customer_ref"].startswith("customer:E") for r in records))
        ps = json.dumps([material["pages"], material["sources"]])
        self.assertNotIn("7200 rpm", ps)
        self.assertNotIn("520 kg", ps)
        self.assertEqual(self.read("03-unreviewed-candidate.json")["check"]["status"], "BLOCKED")

    def test_known_fact_loss_never_yields_READY_or_a_paid_request_freeze(self):
        loss = self.read("downstream-loss.json")
        self.assertGreater(len(loss["facts_lost_before_writer"]), 0)
        self.assertIn("NCX10-TRAVEL", loss["facts_lost_before_writer"])
        self.assertIn("WARRANTY", loss["facts_lost_before_writer"])
        self.assertEqual(set(loss["lossless_native_binding_failures"]), {"one_source_per_reviewed_span", "one_whole_document_quote_per_source"})
        self.assertEqual(self.summary["status"], "BLOCKED")
        self.assertFalse(self.summary["complete_draft_input_ready"])
        self.assertFalse(self.summary["paid_request_frozen"])
        self.assertEqual(self.summary["permits_issued"], 0)
        self.assertFalse((self.rich / "web-experiment").exists())

    def test_full_brief_rejection_is_retained_and_mock_success_is_only_diagnostic(self):
        full = self.read("full-brief-web-blocked.json")
        self.assertGreater(full["full_brief_request_bytes"], full["request_limit_bytes"])
        self.assertEqual(full["requests_sent"], 0)
        web = self.summary["offline_mechanics"]
        self.assertEqual(web["mock_requests"], 1)
        self.assertFalse(web["diagnostic_uses_full_brief"])
        self.assertEqual(web["real_model_calls"], 0)
        self.assertEqual(web["wordpress_calls"], 0)
        self.assertTrue(web["sqlite_reopen"])
        bindings = self.read("claim-evidence-bindings.json")
        for claim in bindings:
            if claim["E"]:
                self.assertEqual(claim["P"], [])
                self.assertEqual(claim["S"], [])

    def test_native_validator_rejects_reworded_E_and_out_of_plan_sections(self):
        value = _decode(self.read("diagnostic-web-native-input.json"), cd.ContentDraftInput)
        response = self.read("scripted-writer-response.json")
        class Writer:
            async def write_content_draft(self, prompt):
                return cd.ContentDraftGeneration("synthetic", "validator-probe-NOT-MODEL", cd.ContentDraftGenerationStatus.SUCCESS,
                    json.dumps(response), None)
        baseline = asyncio.run(ContentDraftWorkflow(Writer(), max_repair_attempts=0).run(value))
        self.assertEqual(baseline.status, cd.ContentDraftStatus.SUCCESS)
        response["draft"]["sections"][0]["blocks"][0]["claims"][0]["text"] += " Ask whether this applies to the intended production cycle."
        rejected = asyncio.run(ContentDraftWorkflow(Writer(), max_repair_attempts=0).run(value))
        self.assertEqual(rejected.status, cd.ContentDraftStatus.INVALID_OUTPUT)
        self.assertEqual(rejected.error, "CUSTOMER_QUOTE_MISMATCH")
        response = self.read("scripted-writer-response.json")
        response["draft"]["sections"][0]["outline_heading"] = "Hand-written replacement chapter"
        rejected = asyncio.run(ContentDraftWorkflow(Writer(), max_repair_attempts=0).run(value))
        self.assertEqual(rejected.status, cd.ContentDraftStatus.INVALID_OUTPUT)

    def test_stale_review_and_expired_fictional_dossier_cannot_be_reused(self):
        snapshot = _decode(self.read("snapshot.json"), IntakeSnapshot)
        assessment = _decode(self.read("04-test-only-review.json")["assessment"], SemanticAssessment)
        with self.assertRaises(ValueError):
            validate_assessment(snapshot, assessment, assessment.reviewed_at + timedelta(minutes=6))
        facts = self.read("facts.json", self.directory / "customer-materials")
        reviewer = case.DossierReviewer(facts, tuple(e.supplement for e in snapshot.active_evidence))
        with self.assertRaises(ValueError):
            reviewer.assess(snapshot, now=datetime(2027, 1, 10, tzinfo=UTC))
        with self.assertRaises(ValueError):
            reviewer.assess(replace(snapshot, task=replace(snapshot.task, goal="Changed task")), now=assessment.reviewed_at)

    def test_production_admission_and_authority_remain_closed(self):
        report = self.read("production-admission-blocked.json")
        self.assertEqual(report["error"], "INTAKE_EXECUTION_BLOCKED")
        self.assertFalse(self.summary["production_authorized"])
        self.assertFalse(self.summary["human_signoff"])
        self.assertFalse(self.summary["customer_approved"])
        self.assertTrue(self.summary["offline_mechanics"]["reviewer_revocation_blocked"])


if __name__ == "__main__":
    unittest.main()
