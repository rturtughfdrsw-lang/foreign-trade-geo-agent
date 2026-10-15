"""Scope, multi-fact grounding and quality admission, with no live transports."""
import asyncio
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts import accept_evidence_backed_article as case
from foreign_trade_geo_agent.core import content_draft as cd, change_plan as cp
from foreign_trade_geo_agent.core.evidence_intake import (
    IntakeSnapshot, SemanticAssessment, CustomerPlanningContext, validate_assessment, snapshot_digest,
)
from foreign_trade_geo_agent.storage.serialization import _decode
from foreign_trade_geo_agent.workflows.content_draft import ContentDraftWorkflow
from foreign_trade_geo_agent.workflows.change_plan import ChangePlanWorkflow
from foreign_trade_geo_agent.adapters.retained_intake_plan import RetainedIntakePlanWriter
from foreign_trade_geo_agent.web.generation import MockArticleExecutor
from foreign_trade_geo_agent.workflows.evidence_intake import reviewed_draft_input, EvidenceIntakeDraftAdmission
from foreign_trade_geo_agent.storage.evidence_intake import SQLiteEvidenceIntakeStore


class EvidenceBackedArticleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name) / 'acceptance'
        cls.result = case.prepare(cls.root)
        cls.rich = cls.root / 'B-rich-evidence'
        cls.value = _decode(json.loads((cls.rich / 'complete-draft-input.json').read_bytes()), cd.ContentDraftInput)
        cls.snapshot = _decode(json.loads((cls.rich / 'snapshot.json').read_bytes()), IntakeSnapshot)
        cls.assessment = _decode(json.loads((cls.rich / '04-test-only-review.json').read_bytes())['assessment'], SemanticAssessment)
        cls.response = json.loads((cls.rich / 'mock-writer-response.json').read_bytes())

    def run_response(self, response, value=None):
        class Writer:
            async def write_content_draft(self, prompt):
                return cd.ContentDraftGeneration('synthetic', 'contract-probe', cd.ContentDraftGenerationStatus.SUCCESS,
                                                  json.dumps(response), None)
        return asyncio.run(ContentDraftWorkflow(Writer(), max_repair_attempts=0).run(value or self.value))

    def test_low_only_E1_blocks_with_concrete_gaps_and_zero_writer_calls(self):
        self.assertEqual(self.result['low_status'], 'BLOCKED')
        self.assertEqual({g['id'] for g in self.result['low_missing']}, {f'F{i}' for i in range(1, 9)})
        self.assertTrue(all(g['fact'] and g['intended_use'] for g in self.result['low_missing']))
        blocked = json.loads((self.root / 'A-low-evidence/draft-blocked.json').read_bytes())
        self.assertEqual(blocked['writer_calls'], 0)
        self.assertEqual(blocked['report']['error'], 'INTAKE_EXECUTION_BLOCKED')
        legacy = json.loads((self.root / 'A-low-evidence-legacy/scope-and-evidence-review.json').read_bytes())
        self.assertEqual([g['requirement']['requirement_id'] for g in legacy['gaps']], ['F2', 'F3', 'F4', 'F5'])

    def test_rich_native_plan_is_scope_bound_and_all_43_facts_reach_writer(self):
        self.assertEqual(self.result['status'], 'READY')
        self.assertEqual((self.result['document_count'], self.result['writer_fact_count']), (7, 43))
        value = self.value
        resource = value.change_plan_report.operations[0].new_resource_spec
        self.assertEqual(len(resource.outline_headings), 6)
        self.assertEqual(resource.section_briefs, CustomerPlanningContext(self.snapshot).section_briefs())
        self.assertTrue(all(b.reader_question and b.explanation_goal and b.supporting_evidence and b.limitations
                            and b.procurement_action for b in resource.section_briefs))
        raw = json.loads(cd.build_content_draft_prompt(value, 'C1').material_json())
        facts = [f for s in raw['customer_evidence']['sources'] for f in s['facts']]
        self.assertEqual(len(facts), 43)
        self.assertTrue(all(f['requirement_ids'] for f in facts))
        self.assertEqual(raw['writing_brief']['goal'], self.snapshot.task.goal)
        self.assertEqual(raw['writing_brief']['article_type'], self.snapshot.task.article_type)
        self.assertEqual(raw['writing_brief']['search_intent'], self.snapshot.task.search_intent)
        self.assertEqual(raw['writing_brief']['reader_problem'], self.snapshot.task.reader_problem)
        self.assertNotIn('7200 rpm', json.dumps([raw['pages'], raw['sources']]))

    def test_mock_end_to_end_persists_multi_fact_interpretations_and_quality_results(self):
        mechanics = self.result['mechanics']
        self.assertEqual(mechanics['parser_validator_finalizer_sqlite_markdown_web'], 'PASS')
        self.assertEqual(mechanics['mock_requests'], 1)
        self.assertEqual(mechanics['interpretation_count'], 6)
        self.assertEqual(mechanics['quality_findings'], ())
        self.assertTrue(mechanics['sqlite_reopen'] and mechanics['duplicate_blocked'] and mechanics['reviewer_revocation_blocked'])
        self.assertEqual(mechanics['real_model_calls'], 0)
        self.assertEqual(mechanics['wordpress_calls'], 0)
        report = self.run_response(self.response)
        self.assertEqual(report.status, cd.ContentDraftStatus.SUCCESS)
        claims = [c for b in report.drafts[0].blocks for c in b.claims]
        interpretations = [c for c in claims if c.claim_type is cd.DraftClaimType.EVIDENCE_BASED_INTERPRETATION]
        self.assertTrue(all(len(c.customer_refs) >= 2 and not c.page_refs and not c.source_refs
            and c.support_kind is cd.DraftClaimSupportKind.CUSTOMER_REVIEWED_INTERPRETATION for c in interpretations))

    def test_unsupported_assumption_and_reworded_direct_fact_rejected(self):
        for claim_index, text in ((1, 'The machine delivers excellent heavy steel cutting performance.'),
                                  (0, 'The fixture guarantees production suitability.')):
            response = deepcopy(self.response)
            response['draft']['sections'][0]['blocks'][0]['claims'][claim_index]['text'] = text
            report = self.run_response(response)
            self.assertEqual(report.status, cd.ContentDraftStatus.INVALID_OUTPUT)
            self.assertEqual(report.error, 'CUSTOMER_QUOTE_MISMATCH')

    def test_interpretation_cannot_omit_premises_or_masquerade_as_direct_fact(self):
        for mutation in ('omit', 'direct', 'wrong', 'mixed'):
            response = deepcopy(self.response)
            claim = response['draft']['sections'][0]['blocks'][0]['claims'][1]
            if mutation == 'omit':
                claim['customer_refs'].pop()
            elif mutation == 'direct':
                claim['claim_type'] = 'OBSERVED_PRODUCT_FACT'
            elif mutation == 'wrong':
                claim['customer_refs'][0] = 'E1.F99'
            else:
                claim['page_refs'] = ['P1']
            report = self.run_response(response)
            self.assertEqual(report.status, cd.ContentDraftStatus.INVALID_OUTPUT, mutation)

    def test_assumption_cannot_escape_as_external_context_or_editorial_text(self):
        for kind in ('GENERAL_TECHNICAL_CONTEXT', 'EDITORIAL_TRANSITION', 'COMPARATIVE_CONTEXT'):
            response = deepcopy(self.response)
            response['draft']['sections'][0]['blocks'][0]['claims'].append(dict(
                text='The equipment handles every steel workpiece.', claim_type=kind,
                page_refs=[], source_refs=['S1'] if kind != 'EDITORIAL_TRANSITION' else [], customer_refs=[]))
            self.assertEqual(self.run_response(response).error, 'CLAIM_TYPE_CONTRACT')

    def test_unsupported_numeric_inference_rejected_even_if_added_to_options(self):
        # A mistaken reviewer option cannot bypass the independent numeric rule.
        interpretation = self.value.customer_evidence.interpretations[0]
        bad = replace(interpretation, text='It delivers 99999 rpm. ' + interpretation.text)
        bundle = replace(self.value.customer_evidence, interpretations=(bad, *self.value.customer_evidence.interpretations[1:]))
        response = deepcopy(self.response)
        response['draft']['sections'][0]['blocks'][0]['claims'][1]['text'] = bad.text
        report = self.run_response(response, replace(self.value, customer_evidence=bundle))
        self.assertEqual(report.error, 'NUMERIC_NOT_GROUNDED')

    def test_quality_gate_rejects_parameter_dump_missing_CTA_and_wrong_question(self):
        response = deepcopy(self.response)
        response['draft']['sections'][-1]['blocks'][0]['claims'].pop()
        self.assertEqual(self.run_response(response).error, 'ARTICLE_QUALITY_GAP')
        # All fact references remain used by other sections, so this specifically
        # tests the question-to-interpretation quality boundary.
        report = self.run_response(self.response)
        draft = report.drafts[0]
        blocks = list(draft.blocks)
        blocks[0] = replace(blocks[0], claims=(blocks[0].claims[0],))
        findings = cd.article_quality_findings(self.value.change_plan_report.operations[0], tuple(blocks),
                                              draft.section_block_counts, draft.customer_evidence)
        self.assertTrue(any('SECTION_EXPLANATION_ACTION_LIMIT_MISSING' in f for f in findings))
        response = deepcopy(self.response)
        first, other = response['draft']['sections'][0], response['draft']['sections'][2]
        first['blocks'][0]['claims'][1], other['blocks'][0]['claims'][1] = other['blocks'][0]['claims'][1], first['blocks'][0]['claims'][1]
        self.assertEqual(self.run_response(response).error, 'ARTICLE_QUALITY_GAP')

    def test_stale_binding_missing_scope_and_unreviewed_premises_fail_closed(self):
        with self.assertRaises(ValueError):
            reviewed_draft_input(self.snapshot, self.assessment, now=self.assessment.reviewed_at + timedelta(minutes=6))
        with self.assertRaises(ValueError):
            reviewed_draft_input(self.snapshot, replace(self.assessment, scope_coverage=None), now=self.assessment.reviewed_at)
        with self.assertRaises(ValueError):
            reviewed_draft_input(self.snapshot, replace(self.assessment, interpretations=()), now=self.assessment.reviewed_at)
        interpretation = self.assessment.interpretations[0]
        decisions = tuple(replace(d, spans=d.spans[1:]) if interpretation.spans[0] in d.spans else d
                          for d in self.assessment.decisions)
        with self.assertRaises(ValueError):
            validate_assessment(self.snapshot, replace(self.assessment, decisions=decisions), self.assessment.reviewed_at)
        fact = self.value.customer_evidence.sources[1].facts[0]
        with self.assertRaises(ValueError):
            replace(self.value.customer_evidence.sources[1], facts=(replace(fact, start=fact.start + 1),))

    def test_native_reconstruction_cannot_tamper_with_interpretation_text(self):
        draft = self.run_response(self.response).drafts[0]
        claims = list(draft.blocks[0].claims)
        claims[1] = replace(claims[1], text='An unsupported explanation.')
        with self.assertRaises(ValueError):
            replace(draft, blocks=(replace(draft.blocks[0], claims=tuple(claims)), *draft.blocks[1:]))

    def test_scope_is_generic_and_bounded_not_a_topic_keyword_switch(self):
        task = replace(self.snapshot.task, goal='Choose a filtration package for an export tender',
                       article_type='Tender decision note', reader_problem='Verify package applicability',
                       search_intent='Compare packages before tender submission')
        self.assertEqual(task.section_briefs, self.snapshot.task.section_briefs)
        with self.assertRaises(ValueError):
            replace(task, section_briefs=(*task.section_briefs, task.section_briefs[0]))
        with self.assertRaises(ValueError):
            replace(task, requirements=task.requirements[1:])
        # Editorial headings may come from trusted task scope, not S-copying.
        briefs = tuple(replace(b, heading='Tender question ' + chr(65 + i)) for i, b in enumerate(task.section_briefs))
        current = replace(self.snapshot, task=replace(task, section_briefs=briefs))
        prompt = cp.build_change_plan_prompt(cp.ChangePlanInput(current.planning_input.site_content,
            current.planning_input.opportunity_report, task_id=current.task.task_id, customer_context=CustomerPlanningContext(current)))
        self.assertEqual(prompt.deterministic_outline_headings_for('R1'), tuple(b.heading for b in briefs))
        self.assertTrue(set(current.point_subjects) <= {c.text for c in prompt.content_point_candidates_for('R1')})
        report = asyncio.run(ChangePlanWorkflow(RetainedIntakePlanWriter()).run(current.planning_input.site_content,
            current.planning_input.opportunity_report, task_id=current.task.task_id, customer_context=CustomerPlanningContext(current)))
        self.assertEqual(report.status, cp.ChangePlanStatus.SUCCESS)
        self.assertEqual(report.operations[0].new_resource_spec.outline_headings, tuple(b.heading for b in briefs))

    def test_input_envelope_never_truncates_evidence_to_fit(self):
        from unittest.mock import patch
        with patch.object(cd, 'MAX_INPUT_ENVELOPE_BYTES', 100):
            with self.assertRaisesRegex(ValueError, 'INPUT_BUDGET_EXCEEDED'):
                MockArticleExecutor.request_for(self.value)

    def test_rich_projection_does_not_authorize_production_admission(self):
        store = SQLiteEvidenceIntakeStore(self.rich / 'interactive-intake.sqlite3')
        admission = EvidenceIntakeDraftAdmission(store, self.snapshot.task.project_id, self.snapshot.task.task_id,
                                                expected_snapshot_sha256=snapshot_digest(self.snapshot))
        self.assertIsNotNone(admission.rejection_reason(self.value))
        self.assertFalse(self.result['production_authorized'])
        self.assertFalse(self.result['human_signoff'])


if __name__ == '__main__':
    unittest.main()
