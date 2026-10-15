"""Both paths exercise native Intake, retained Planning, HTTP and frozen input."""
import asyncio
from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient
from scripts import accept_native_article_scope as demo
from scripts import accept_seo_task_scope as case
from foreign_trade_geo_agent.core import content_draft as cd
from foreign_trade_geo_agent.core.evidence_intake import SemanticAssessment, snapshot_digest
from foreign_trade_geo_agent.web.mvp_application import MVPError


class NativeScopePathTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / 'scope'
        self.app = demo.prepare(self.directory)
        self.client = self.enterContext(TestClient(self.app, base_url='http://127.0.0.1'))
        self.service = self.app.state.mvp_service
        self.before = self.service.evidence()['snapshot']

    def form(self):
        return {'csrf_token': self.app.state.csrf_token,
                'expected_sha256': self.service.evidence()['expected_sha256']}

    def request(self):
        return self.client.post('/mvp/scope', data={**self.form(), 'goal': case.NOTE_GOAL, 'reason': 'TEST-only: exclude unsupported selection conclusions.'})

    def consent(self, fields=None):
        return self.client.post('/mvp/scope/test-confirm', data={**(fields or self.form()), 'confirmed': 'TEST_ONLY_SIMULATED_CONSENT'})

    def test_full_guide_only_E1_is_blocked_and_gaps_are_actionable(self):
        view = self.service.evidence()
        self.assertEqual(view['intake_check'].status.value, 'BLOCKED')
        self.assertEqual([g.requirement.requirement_id for g in view['intake_request'].gaps], ['F2','F3','F4','F5'])
        self.assertTrue(all(g.requirement.required_fact and g.requirement.intended_use for g in view['intake_request'].gaps))
        self.assertFalse(self.service.generation.view()['generation_allowed'])
        self.assertEqual(self.client.post('/mvp/generate', data={'csrf_token': self.app.state.csrf_token,
                                                              'binding_sha256': '0'*64}).status_code, 409)
        self.assertFalse((self.directory / 'generation').exists())

    def test_explicit_simulated_consent_creates_independent_plan_and_preserves_parent(self):
        self.assertEqual(self.request().status_code, 200)
        self.assertEqual(self.service.evidence()['snapshot'], self.before)
        self.assertEqual(self.consent().status_code, 200)
        current = self.service.evidence()['snapshot']
        self.assertNotEqual(current.task.task_id, self.before.task.task_id)
        self.assertEqual(current.task.goal, case.NOTE_GOAL)
        self.assertEqual(current.plan_version, 2)
        self.assertEqual(current.planning_input.change_plan_report.operations[0].new_resource_spec.proposed_title, case.NOTE_TITLE)
        _, _, store, _, _ = self.service._load()
        self.assertEqual(store.latest(self.before.task.project_id, self.before.task.task_id), self.before)
        self.assertEqual(current.active_evidence[0].supplement, self.before.active_evidence[0].supplement)
        self.assertEqual(self.service.evidence()['intake_request'].gaps, ())
        self.assertFalse(self.service.evidence()['scope_lineage']['customer_consented'])
        self.assertEqual(self.consent({'csrf_token': self.app.state.csrf_token,
                                      'expected_sha256': snapshot_digest(self.before)}).status_code, 409)
        self.assertEqual(demo.build(self.directory).state.mvp_service.evidence()['snapshot'], current)

    def test_stale_request_cannot_create_a_child(self):
        self.request()
        stale = self.form()
        self.service.submit(expected_sha256=stale['expected_sha256'], content='Changed E1 text, not a reviewed source', source_label='changed')
        self.assertEqual(self.consent(stale).status_code, 409)
        self.assertFalse((self.directory / 'scope-requests/selected.json').exists())

    def test_parent_update_during_child_replan_cannot_select_child_or_transfer_review(self):
        from unittest.mock import patch
        from foreign_trade_geo_agent.adapters.retained_intake_plan import RetainedIntakePlanWriter
        original = RetainedIntakePlanWriter.write_change_plan
        self.request()
        async def update_parent(writer, prompt):
            self.service.submit(expected_sha256=snapshot_digest(self.before),
                content='TEST-only parent changed during child replan', source_label='Unreviewed replacement')
            return await original(writer, prompt)
        with patch.object(RetainedIntakePlanWriter, 'write_change_plan', update_parent):
            self.assertEqual(self.consent().status_code, 409)
        self.assertFalse((self.directory / 'scope-requests/selected.json').exists())
        parent = self.service.evidence()['snapshot']
        self.assertEqual(parent.task.task_id, self.before.task.task_id)
        self.assertFalse(parent.plan_bound)
        _, _, store, _, _ = self.service._load()
        self.assertEqual(store.get_revision(parent.task.project_id, parent.task.task_id, self.before.revision), self.before)
        self.assertFalse(self.service.generation.view()['generation_allowed'])

    def test_child_preserves_exact_replacement_chain_without_relabeling_sources(self):
        from tests.scope_fixtures import ExplicitTestScopeReviewer
        self.service.scope_reviewer = ExplicitTestScopeReviewer()
        self.service.submit(expected_sha256=snapshot_digest(self.before),
            content=self.before.active_evidence[0].supplement.content, source_label='TEST replacement E2')
        parent = self.service.evidence()['snapshot']
        self.service.scope.test_proposal = replace(self.service.scope.test_proposal,
            parent_snapshot_sha256=snapshot_digest(parent))
        self.assertEqual(self.request().status_code, 200)
        self.assertEqual(self.consent().status_code, 200)
        child = self.service.evidence()['snapshot']
        self.assertNotEqual(child.task.task_id, parent.task.task_id)
        self.assertEqual(tuple(e.supplement for e in child.evidence),
                         tuple(e.supplement for e in parent.evidence))
        self.assertEqual(child.active_evidence[0].supplement.evidence_id, 'E2')
        self.assertEqual(child.active_evidence[0].supplement.supersedes, 'E1')
        self.assertEqual(child.scope_consents, ())
        self.assertFalse(self.service.evidence()['scope_lineage']['customer_consented'])
        _, _, store, _, _ = self.service._load()
        self.assertEqual(store.latest(parent.task.project_id, parent.task.task_id), parent)

    def test_child_brief_request_and_E1_freeze_agree_without_execution(self):
        self.request()
        self.consent()
        result = demo.prepare_brief_and_request(self.service)
        self.assertTrue(result['ready_for_next_isolated_flash_freeze'])
        value = self.service.generation._prepare()[2]
        self.assertEqual(value.writing_brief.goal, case.NOTE_GOAL)
        self.assertEqual(value.writing_brief.snapshot_sha256, value.customer_evidence.snapshot_sha256)
        self.assertEqual(value.customer_evidence.sources[0].content, self.before.active_evidence[0].supplement.content)
        request = json.loads((self.directory / 'web-experiment/request.json').read_bytes())
        material = json.loads(request['messages'][1]['content'])
        self.assertEqual(material['writing_brief']['goal'], case.NOTE_GOAL)
        self.assertEqual(material['customer_evidence']['sources'][0]['customer_ref'], 'E1')
        self.assertNotIn('7200 rpm', json.dumps([material['pages'], material['sources']]))
        self.assertEqual(result['real_model_calls'], 0)
        self.assertFalse(result['permit_issued'])
        self.assertEqual(self.service.generation_executor.calls, 0)
        self.assertFalse((self.directory / 'generation').exists())
        self.assertEqual(cd.stable_content_draft_input_error(replace(value,
            writing_brief=replace(value.writing_brief, snapshot_sha256=snapshot_digest(self.before)))), 'CUSTOMER_EVIDENCE_INVALID')
        # Same native validator: the brief cannot introduce a new E fact.
        headings = value.change_plan_report.operations[0].new_resource_spec.outline_headings
        fact = {'text': value.customer_evidence.sources[0].quote, 'claim_type': 'OBSERVED_PRODUCT_FACT',
                'page_refs': [], 'source_refs': [], 'customer_refs': ['E1']}
        cta = {'text': 'Send the intended application and test questions to the supplier and request supporting records.',
               'claim_type': 'CALL_TO_ACTION', 'page_refs': [], 'source_refs': []}
        raw = {'draft': {'change_ref':'C1','draft_type':'NEW_RESOURCE_DRAFT','sections':[
            {'outline_heading':headings[0], 'blocks':[{'kind':'PARAGRAPH','claims':[fact]}]},
            {'outline_heading':headings[1], 'blocks':[{'kind':'PARAGRAPH','claims':[cta]}]}]}}
        from foreign_trade_geo_agent.workflows.content_draft import ContentDraftWorkflow
        class Writer:
            async def write_content_draft(_, prompt):
                return cd.ContentDraftGeneration('synthetic','test',cd.ContentDraftGenerationStatus.SUCCESS,json.dumps(raw),None)
        report = asyncio.run(ContentDraftWorkflow(Writer(), max_repair_attempts=0).run(value))
        self.assertEqual(report.status, cd.ContentDraftStatus.SUCCESS)
        fact['text'] = fact['text'].replace('7200 rpm','7300 rpm')
        rejected = asyncio.run(ContentDraftWorkflow(Writer(), max_repair_attempts=0).run(value))
        self.assertEqual(rejected.status, cd.ContentDraftStatus.INVALID_OUTPUT)
        self.assertIn(rejected.error, {'CUSTOMER_QUOTE_MISMATCH','NUMERIC_NOT_GROUNDED'})

    def test_expand_section_proposal_uses_observed_heading_and_independent_child(self):
        from tests.test_evidence_intake import native_input, customer_task
        value = native_input(('Packing limits',))
        proposal = self.service.scope.test_proposal
        task = replace(proposal.task, goal='TEST-only explain packing limits',
                       requirements=customer_task().requirements[:1])
        self.service.scope.test_proposal = replace(proposal, task=task, planning_input=value)
        self.service.scope_reviewer = None
        response = self.client.post('/mvp/scope', data={**self.form(), 'goal':task.goal, 'reason':'TEST-only expansion fixture'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('新标题：Packing limits', response.text)
        self.assertEqual(self.consent().status_code, 200)
        child = self.service.evidence()['snapshot']
        self.assertNotEqual(child.task.task_id, self.before.task.task_id)
        self.assertIsNone(child.planning_input.change_plan_report.operations[0].new_resource_spec)
        self.assertEqual(self.service.evidence()['scope_lineage']['plan_title'], 'Packing limits')
        self.assertFalse(self.service.generation.view()['generation_allowed'])

    def test_missing_scope_review_never_labels_supplied_F1_as_covered(self):
        original = self.service.scope_reviewer
        class LegacyReviewer:
            def assess(_, snapshot, *, now):
                return replace(original.assess(snapshot, now=now), scope_coverage=None)
        self.service.scope_reviewer = LegacyReviewer()
        page = self.client.get('/mvp/evidence')
        self.assertEqual(page.status_code, 200)
        self.assertNotIn('已覆盖（TEST-only 模拟审核）', page.text)
        self.assertIn('范围待审核', page.text)

    def test_unbound_plan_never_labels_supported_F1_as_covered(self):
        from tests.scope_fixtures import ExplicitTestScopeReviewer
        self.service.scope_reviewer = ExplicitTestScopeReviewer()
        self.service.submit(expected_sha256=snapshot_digest(self.before),
            content=self.before.active_evidence[0].supplement.content, source_label='TEST-only new epoch')
        page = self.client.get('/mvp/evidence')
        self.assertEqual(page.status_code, 200)
        self.assertNotIn('已覆盖（TEST-only 模拟审核）', page.text)
        self.assertNotIn('范围已核对 · 证据缺口未补齐', page.text)
        self.assertIn('Plan 待重新绑定', page.text)
