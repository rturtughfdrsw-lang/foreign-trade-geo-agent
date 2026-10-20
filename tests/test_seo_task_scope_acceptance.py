"""Case-specific offline business acceptance; no semantic truth claims."""
import asyncio
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import accept_seo_task_scope as case
from foreign_trade_geo_agent.core.content_draft import stable_content_draft_input_error
from foreign_trade_geo_agent.core.evidence_intake import (
    CustomerSubmission, EvidenceSpan, IntakeStatus, RequirementDecision, ScopeAdjustment,
    SemanticAssessment, SupportVerdict, native_plan_error, snapshot_digest, validate_assessment,
)
from foreign_trade_geo_agent.storage.evidence_intake import SQLiteEvidenceIntakeStore
from foreign_trade_geo_agent.workflows.content_draft import ContentDraftWorkflow
from foreign_trade_geo_agent.workflows.evidence_intake import EvidenceIntakeDraftAdmission, EvidenceIntakeWorkflow


class ScopeAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = SQLiteEvidenceIntakeStore.create(Path(self.temp.name) / 'intake.sqlite3')
        self.flow = EvidenceIntakeWorkflow(self.store)
        self.broad = asyncio.run(case.single_e1_case(self.flow, 'GUIDE'))

    def consent(self, agrees=True):
        return self.flow.submit(case.PROJECT, 'GUIDE', CustomerSubmission('SYNTHETIC-CONSENT',
            snapshot_digest(self.broad.snapshot), scope_adjustment=ScopeAdjustment(case.NOTE_GOAL, ('F1',),
                'SYNTHETIC simulated customer confirmation of a spindle test explanation only.', agrees)),
            customer=case.customer())

    def test_frozen_goal_title_mismatch_was_structurally_valid_and_had_only_F1(self):
        old = case.load_frozen()
        self.assertIn('explaining spindle performance', old.task.goal)
        self.assertEqual(old.planning_input.change_plan_report.operations[0].proposed_heading, case.GUIDE_TITLE)
        self.assertEqual(tuple(r.requirement_id for r in old.task.requirements), ('F1',))
        self.assertEqual(old.scope_consents, ())
        self.assertIsNone(native_plan_error(old.planning_input, old.point_subjects))

    def test_single_E1_does_not_clear_the_declared_guide_questions(self):
        self.assertEqual(self.broad.check.status, IntakeStatus.BLOCKED)
        self.assertFalse(self.broad.draft_authorized)
        self.assertEqual({g.requirement.requirement_id: g.reason_code for g in self.broad.check.gaps},
            {'F1': 'HUMAN_SEMANTIC_REVIEW_REQUIRED',
             **{f'F{i}': 'MISSING_CUSTOMER_EVIDENCE' for i in range(2, 6)}})
        request = self.flow.customer_request(case.PROJECT, 'GUIDE', now=case.NOW)
        self.assertIn('workpiece material', request.gaps[1].requirement.required_fact)
        self.assertIn('measurement method', request.gaps[3].requirement.required_fact)
        self.assertEqual(request.snapshot_sha256, snapshot_digest(self.broad.snapshot))

    def test_more_materials_cover_five_points_but_are_not_automatic_sufficiency(self):
        added = case.supplements()
        for item in added:
            self.assertTrue(item.source_locator.startswith('synthetic:novacnc/NCX7/'))
            self.assertIn('revision A', item.content)
            self.assertIn('SYNTHETIC ONLY', item.content)
            self.assertIn('NCX7', item.content)
            self.assertEqual(item.file_sha256, hashlib.sha256(item.content.encode()).hexdigest())
        submitted = self.flow.submit(case.PROJECT, 'GUIDE', CustomerSubmission('SYNTHETIC-MORE',
            snapshot_digest(self.broad.snapshot), added), customer=case.customer())
        self.assertFalse(submitted.plan_bound)
        result = asyncio.run(case.replan(self.flow, submitted))
        self.assertEqual(result.snapshot.plan_version, 3)
        self.assertEqual(result.snapshot.evidence_version, 3)
        self.assertEqual(tuple(p.subject for p in result.snapshot.planning_input.change_plan_report.operations[0].content_points),
                         case.SUBJECTS)
        self.assertEqual(len(result.claims), 5)
        self.assertTrue(all(len(c.materials) == 1 for c in result.claims))
        self.assertEqual(result.check.status, IntakeStatus.BLOCKED)
        self.assertTrue(all(g.reason_code == 'HUMAN_SEMANTIC_REVIEW_REQUIRED' for g in result.check.gaps))
        self.assertIsNone(result.check.assessment)
        self.assertFalse(result.draft_authorized)

    def test_narrowing_without_explicit_consent_rejects_and_preserves_state(self):
        with self.assertRaisesRegex(ValueError, 'CUSTOMER_SUBMISSION_REJECTED'):
            self.consent(False)
        self.assertEqual(self.store.latest(case.PROJECT, 'GUIDE'), self.broad.snapshot)
        with self.assertRaises(ValueError):
            asyncio.run(case.narrow_after_consent(self.flow, self.store, self.broad.snapshot))

    def test_consent_invalidates_old_plan_binding_and_does_not_retitle_it(self):
        current = self.consent()
        self.assertEqual(current.task.task_version, 2)
        self.assertEqual(current.task.goal, case.NOTE_GOAL)
        self.assertEqual(current.point_subjects, case.SUBJECTS[:1])
        self.assertFalse(current.plan_bound)
        self.assertEqual(current.plan_version, 2)
        self.assertEqual(current.planning_input.change_plan_report.operations[0].proposed_heading, case.GUIDE_TITLE)
        self.assertEqual(self.store.get_revision(case.PROJECT, 'GUIDE', self.broad.snapshot.revision), self.broad.snapshot)
        check = self.flow.check(case.PROJECT, 'GUIDE', now=case.NOW)
        self.assertEqual(check.reason, 'PLAN_REBIND_REQUIRED')

    def test_native_rebind_cannot_smuggle_new_title_or_research_into_old_task(self):
        current = self.consent()
        value = asyncio.run(case.native_input(case.NOTE_TITLE, case.SUBJECTS[:1]))
        self.assertIsNone(native_plan_error(value, current.point_subjects))
        with self.assertRaisesRegex(ValueError, 'PLAN_REBIND_REJECTED'):
            self.flow.rebind_plan(case.PROJECT, 'GUIDE', expected_sha256=snapshot_digest(current), planning_input=value)
        self.assertEqual(self.store.latest(case.PROJECT, 'GUIDE'), current)

    def test_confirmed_scope_creates_separate_native_plan_and_new_evidence_binding(self):
        current = self.consent()
        note, lineage = asyncio.run(case.narrow_after_consent(self.flow, self.store, current))
        self.assertEqual(note.snapshot.planning_input.change_plan_report.operations[0].proposed_heading, case.NOTE_TITLE)
        self.assertNotEqual(note.snapshot.task.task_id, current.task.task_id)
        self.assertEqual(note.snapshot.task.task_version, 1)
        self.assertEqual(note.snapshot.plan_version, 2)
        self.assertIsNone(native_plan_error(note.snapshot.planning_input, note.snapshot.point_subjects))
        self.assertEqual(note.snapshot.active_evidence[0].supplement, current.active_evidence[0].supplement)
        self.assertEqual(note.check.status, IntakeStatus.BLOCKED)
        self.assertEqual(note.check.gaps[0].reason_code, 'HUMAN_SEMANTIC_REVIEW_REQUIRED')
        self.assertFalse(lineage['old_review_transferred'])
        self.assertFalse(lineage['production_scope_change_authorized'])
        self.assertEqual(lineage['parent_snapshot_sha256'], snapshot_digest(current))

    def test_stale_evidence_review_and_cross_task_review_are_rejected(self):
        current = self.broad.snapshot
        material = current.active_evidence[0].supplement
        assessment = SemanticAssessment(snapshot_digest(current), 'SYNTHETIC-FIXTURE-NOT-HUMAN', case.NOW,
            (RequirementDecision('F1', SupportVerdict.UNREVIEWED, 'SYNTHETIC binding check only.',
                (EvidenceSpan('E1', 0, len(material.content), material.content),)),
             *(RequirementDecision(f'F{i}', SupportVerdict.MISSING, 'SYNTHETIC missing document.') for i in range(2, 6))))
        validate_assessment(current, assessment, case.NOW)
        submitted = self.flow.submit(case.PROJECT, 'GUIDE', CustomerSubmission('SYNTHETIC-UPDATE',
            snapshot_digest(current), case.supplements()), customer=case.customer())
        updated = asyncio.run(case.replan(self.flow, submitted)).snapshot
        for value in (submitted, updated, replace(current, task=replace(current.task, task_id='OTHER-TASK'))):
            with self.subTest(task=value.task.task_id, revision=value.revision), self.assertRaises(ValueError):
                validate_assessment(value, assessment, case.NOW)

    def test_old_snapshot_cannot_submit_or_replan_after_scope_consent(self):
        self.consent()
        with self.assertRaises(ValueError):
            self.flow.submit(case.PROJECT, 'GUIDE', CustomerSubmission('SYNTHETIC-STALE',
                snapshot_digest(self.broad.snapshot), case.supplements()), customer=case.customer())
        with self.assertRaises(ValueError):
            asyncio.run(case.replan(self.flow, self.broad.snapshot))

    def test_E_stays_separate_from_P_S_and_old_E_bundle_cannot_bind_new_plan(self):
        current = self.consent()
        note, _ = asyncio.run(case.narrow_after_consent(self.flow, self.store, current))
        value = note.snapshot.planning_input
        raw = json.dumps([case._encode(value.site_content), case._encode(value.opportunity_report)])
        for token in ('7200 rpm', 'NOVA-TEST-7', 'NCX7'):
            self.assertNotIn(token, raw)
        old_native = case._decode(json.loads((case.FROZEN.parent / 'native-input.json').read_text(encoding='utf-8')),
                                   type(value))
        self.assertIsNotNone(stable_content_draft_input_error(replace(value, customer_evidence=old_native.customer_evidence)))

    def test_production_draft_admission_stops_before_writer_for_guide_and_note(self):
        class NeverWriter:
            calls = 0
            async def write_content_draft(self, prompt):
                self.calls += 1
                raise AssertionError('No Draft execution is authorized by these scenarios')
        current = self.consent()
        note, _ = asyncio.run(case.narrow_after_consent(self.flow, self.store, current))
        for snapshot in (self.broad.snapshot, current, note.snapshot):
            with self.subTest(task=snapshot.task.task_id):
                writer = NeverWriter()
                report = asyncio.run(ContentDraftWorkflow(writer, intake_admission=EvidenceIntakeDraftAdmission(
                    self.store, case.PROJECT, snapshot.task.task_id,
                    expected_snapshot_sha256=snapshot_digest(snapshot))).run(snapshot.planning_input))
                self.assertEqual(report.error, 'INTAKE_EXECUTION_BLOCKED')
                self.assertEqual(writer.calls, 0)

    def test_end_to_end_acceptance_is_offline_and_does_not_change_frozen_input(self):
        before = case.FROZEN.read_bytes()
        async def offline():
            # Windows initializes asyncio's loop with a local socketpair. Install
            # the network tripwire after loop creation, around the entire case.
            with patch('socket.socket.connect', side_effect=AssertionError('Offline acceptance attempted network')):
                return await case.prepare(Path(self.temp.name) / 'artifacts')
        result = asyncio.run(offline())
        self.assertEqual(result['provider_calls'], 0)
        self.assertEqual(result['wordpress_calls'], 0)
        self.assertEqual(case.FROZEN.read_bytes(), before)
        self.assertEqual(result['single_E1_status'], 'BLOCKED')
        self.assertEqual(result['additional_materials_status'], 'BLOCKED')
        self.assertFalse(result['draft_authorized'])

    def test_scope_consent_cannot_drop_one_fact_obligation_from_a_retained_point(self):
        old = case.load_frozen()
        task = replace(old.task, project_id=case.PROJECT, task_id='SINGLE-POINT',
            requirements=tuple(replace(r, point_index=0) for r in case.requirements()[:2]))
        registered = self.flow.register(task, old.planning_input)
        with self.assertRaisesRegex(ValueError, 'CUSTOMER_SUBMISSION_REJECTED'):
            self.flow.submit(case.PROJECT, task.task_id, CustomerSubmission('SYNTHETIC-PARTIAL-DROP',
                snapshot_digest(registered), scope_adjustment=ScopeAdjustment(case.NOTE_GOAL, ('F1',),
                    'SYNTHETIC cannot weaken an obligation while retaining its original point.', True)), customer=case.customer())
        self.assertEqual(self.store.latest(case.PROJECT, task.task_id), registered)


if __name__ == '__main__':
    unittest.main()
