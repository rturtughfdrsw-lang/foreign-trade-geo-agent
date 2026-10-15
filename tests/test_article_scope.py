"""Goal/Plan/obligation review extends intake, never grants Draft permission."""
from dataclasses import replace
import unittest

from tests import test_evidence_intake as fixture
from tests.test_evidence_intake import ScriptedHumanReviewer, supported_script, NOW, PROJECT, TASK
from foreign_trade_geo_agent.core.evidence_intake import IntakeStatus, snapshot_digest
from foreign_trade_geo_agent.workflows.evidence_intake import EvidenceIntakeWorkflow


class ArticleScopeTests(unittest.TestCase):
    setUp = fixture.EvidenceIntakeTests.setUp
    current = fixture.EvidenceIntakeTests.current
    fact = fixture.EvidenceIntakeTests.fact
    submit = fixture.EvidenceIntakeTests.submit
    rebind = fixture.EvidenceIntakeTests.rebind
    check = fixture.EvidenceIntakeTests.check
    complete = fixture.EvidenceIntakeTests.complete
    # Reuse the real SQLite fixture, without inheriting its test cases.
    def test_legacy_supported_facts_without_scope_review_remain_blocked(self):
        self.complete()
        reviewer = ScriptedHumanReviewer(supported_script())
        class Legacy:
            def assess(_, snapshot, *, now):
                assessment = reviewer.assess(snapshot, now=now)
                if hasattr(assessment, 'scope_coverage'):
                    assessment = replace(assessment, scope_coverage=None)
                return assessment
        result = self.check(Legacy())
        self.assertEqual(result.status, IntakeStatus.BLOCKED)
        self.assertEqual(result.reason, 'ARTICLE_SCOPE_REVIEW_REQUIRED')
        self.assertEqual(result.gaps, ())  # no repeated customer material requested

    def test_scope_gaps_use_existing_customer_request(self):
        from foreign_trade_geo_agent.core.evidence_intake import ArticleScopeCoverage
        self.complete()
        missing = replace(self.original.task.requirements[0], requirement_id='F4',
                          required_fact='Application-specific acceptance procedure and exclusions')
        reviewer = ScriptedHumanReviewer(supported_script())
        class Mismatch:
            def assess(_, snapshot, *, now):
                return replace(reviewer.assess(snapshot, now=now), scope_coverage=ArticleScopeCoverage(
                    False, 'The approved goal promises acceptance decisions absent from this Plan and its obligations.', (missing,)))
        flow = EvidenceIntakeWorkflow(self.store, reviewer=Mismatch())
        request = flow.customer_request(PROJECT, TASK, now=NOW)
        self.assertEqual(request.staff_action, 'ARTICLE_SCOPE_MISMATCH')
        self.assertEqual(request.gaps[0].requirement.required_fact, missing.required_fact)
        self.assertEqual(request.gaps[0].reason_code, 'ARTICLE_SCOPE_REQUIREMENT_MISSING')
        self.assertFalse(flow.check(PROJECT, TASK, now=NOW).draft_authorized)
        self.assertTrue(flow.review_candidate(PROJECT, TASK, now=NOW).return_to_intake)

    def test_complete_scope_needs_no_new_customer_material(self):
        from foreign_trade_geo_agent.core.evidence_intake import ArticleScopeCoverage
        self.complete()
        reviewer = ScriptedHumanReviewer(supported_script())
        class Aligned:
            def assess(_, snapshot, *, now):
                return replace(reviewer.assess(snapshot, now=now), scope_coverage=ArticleScopeCoverage(
                    True, 'Synthetic explicit review of goal, Plan title/intent, every point and all obligations.'))
        result = self.check(Aligned())
        self.assertEqual(result.status, IntakeStatus.CANDIDATE_FOR_REVIEW)
        self.assertEqual(result.gaps, ())

    def test_scope_review_cannot_transfer_to_a_new_evidence_epoch(self):
        from foreign_trade_geo_agent.core.evidence_intake import ArticleScopeCoverage
        self.complete()
        old = replace(ScriptedHumanReviewer(supported_script()).assess(self.current(), now=NOW),
                      scope_coverage=ArticleScopeCoverage(True, 'Explicit synthetic review.'))
        self.submit(self.fact(1, evidence_id='E4', supersedes='E1'))
        self.rebind()
        class Stale:
            def assess(_, snapshot, *, now):
                return old
        result = self.check(Stale())
        self.assertEqual(result.status, IntakeStatus.BLOCKED)
        self.assertIsNone(result.assessment)
        self.assertNotEqual(old.snapshot_sha256, snapshot_digest(self.current()))
