"""Safe, transient block-budget diagnostics and provider contract alignment."""
from contextlib import closing
from dataclasses import asdict, fields, replace
import json
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from foreign_trade_geo_agent.cli import _plan_validation_diagnostic
from foreign_trade_geo_agent.core.content_draft import (
    ContentDraftReport, ContentDraftInput, ContentDraftType, ContentDraftSpecification,
    NewResourceSectionSpecification, TableCellSpecification,
    build_content_draft_prompt, describe_draft_block_budget_violation, stable_content_draft_input_error,
)
from foreign_trade_geo_agent.core.change_plan import (
    ChangeOperationType, ComparisonTableSpec, SectionPurpose,
)
from foreign_trade_geo_agent.core.content_opportunity import ContentOpportunityActionCode
from foreign_trade_geo_agent.adapters.deepseek_content_draft import DeepSeekContentDraftWriter
from foreign_trade_geo_agent.core.history import ArtifactType, RunStatus
from foreign_trade_geo_agent.core.orchestration import EndToEndStage
from foreign_trade_geo_agent.storage.serialization import encode_artifact
from foreign_trade_geo_agent.workflows.content_draft import ContentDraftWorkflow, _parse_specification
from foreign_trade_geo_agent.workflows.run_diagnostics import RunDiagnosticContext
from tests.test_content_draft_workflow import _DraftFakeWriter, _expand_input, _generation, _section_text
from tests.comparison_fixtures import validate_legacy_table
from foreign_trade_geo_agent.core.content_draft import content_draft_block_budget_contract


async def add_section_input():
    from tests.test_change_plan_workflow import opportunity
    value = await _expand_input()
    operation = replace(value.change_plan_report.operations[0],
        source_action_code=ContentOpportunityActionCode.ADD_BUYER_GUIDANCE,
        operation_type=ChangeOperationType.ADD_SECTION,
        proposed_heading='Material selection guide', section_purpose=SectionPurpose.BUYER_GUIDANCE)
    new_opportunity = opportunity(
        action_codes=(ContentOpportunityActionCode.ADD_BUYER_GUIDANCE,))
    return replace(value, change_plan_report=replace(value.change_plan_report, operations=(operation,)),
        opportunity_report=replace(value.opportunity_report, opportunities=(new_opportunity,)))


def five_paragraphs():
    raw = json.loads(_section_text())
    raw['draft']['blocks'] = [
        {'kind': 'PARAGRAPH', 'claims': [{'text': f'DRAFT_SENTINEL_{i}',
            'claim_type': 'GENERAL_TECHNICAL_CONTEXT', 'page_refs': [], 'source_refs': ['S1']}]}
        for i in range(5)
    ]
    return _generation(json.dumps(raw))


class DraftBlockBudgetTests(unittest.IsolatedAsyncioTestCase):
    async def test_section_material_declares_existing_scoped_limits_without_mutating_plan(self):
        value = await _expand_input()
        before = asdict(value)
        prompt = build_content_draft_prompt(value, 'C1')
        material = json.loads(prompt.material_json())
        self.assertEqual(material['contract']['block_budget'], {
            'blocks': {'min': 1, 'max': 8},
            'paragraph_blocks': {'min': 0, 'max': 4},
            'items_per_bullet_list': {'min': 1, 'max': 6},
        })
        self.assertEqual(asdict(value), before)
        self.assertEqual(prompt.material_json(), build_content_draft_prompt(value, 'C1').material_json())
        self.assertEqual(len(material['change']['content_points']), len(prompt.operation.content_points))
        self.assertEqual(material['change']['page_refs'], list(prompt.operation.page_refs))
        self.assertEqual(material['change']['source_refs'], list(prompt.operation.source_refs))

    def test_system_prompt_exposes_hidden_paragraph_and_nonempty_limits(self):
        system = DeepSeekContentDraftWriter.build_system_prompt()
        self.assertIn('at most 4 PARAGRAPH blocks', system)
        self.assertIn('1 to 8 blocks', system)
        self.assertIn('1 to 6 items', system)
        self.assertIn('at most 30 cells', system)
        self.assertIn('per section', system)

    async def test_five_paragraphs_fail_with_exact_safe_rule_and_path(self):
        value = await add_section_input()
        self.assertIsNone(stable_content_draft_input_error(value))
        before = asdict(value.change_plan_report)
        writer = _DraftFakeWriter([five_paragraphs()])
        workflow = ContentDraftWorkflow(writer)
        report = await workflow.run(value)
        self.assertEqual(report.error, 'BLOCK_BUDGET')
        diagnostic = workflow.last_block_budget_violation
        self.assertEqual(diagnostic.change_ref, 'C1')
        self.assertEqual(diagnostic.operation_type, ChangeOperationType.ADD_SECTION)
        self.assertEqual(diagnostic.rule_id.value, 'PARAGRAPH_COUNT')
        self.assertEqual(diagnostic.field_path, 'draft.blocks')
        self.assertEqual((diagnostic.expected_min, diagnostic.expected_max, diagnostic.actual_count), (0, 4, 5))
        self.assertEqual((diagnostic.paragraph_count, diagnostic.bullet_list_count), (5, 0))
        self.assertNotIn('DRAFT_SENTINEL', json.dumps(asdict(diagnostic)))
        self.assertNotIn('Chemical compatibility', json.dumps(asdict(diagnostic)))
        self.assertEqual(writer.calls, 1)
        self.assertEqual(asdict(value.change_plan_report), before)
        self.assertEqual([f.name for f in fields(ContentDraftReport)],
            ['status', 'drafts', 'limitations', 'error', 'requires_human_review'])
        self.assertNotIn('block_budget_violation', encode_artifact(ArtifactType.CONTENT_DRAFT, report))

    async def test_empty_excess_blocks_and_bullet_item_rule_locations(self):
        value = await add_section_input()
        base = json.loads(_section_text())
        paragraph = base['draft']['blocks'][0]
        for blocks, rule, path, minimum, maximum, actual in [
            ([], 'BLOCK_COUNT', 'draft.blocks', 1, 8, 0),
            ([paragraph] * 9, 'BLOCK_COUNT', 'draft.blocks', 1, 8, 9),
            ([{'kind': 'BULLET_LIST', 'items': []}], 'BULLET_ITEM_COUNT', 'draft.blocks[0].items', 1, 6, 0),
            ([{'kind': 'BULLET_LIST', 'items': paragraph['claims'] * 7}], 'BULLET_ITEM_COUNT', 'draft.blocks[0].items', 1, 6, 7),
        ]:
            with self.subTest(rule=rule, actual=actual):
                raw = {'draft': {**base['draft'], 'blocks': blocks}}
                workflow = ContentDraftWorkflow(_DraftFakeWriter([_generation(json.dumps(raw))]))
                self.assertEqual((await workflow.run(value)).error, 'BLOCK_BUDGET')
                descriptor = workflow.last_block_budget_violation
                self.assertEqual((descriptor.rule_id.value, descriptor.field_path), (rule, path))
                self.assertEqual((descriptor.expected_min, descriptor.expected_max, descriptor.actual_count),
                    (minimum, maximum, actual))

    async def test_resource_local_and_aggregate_rules_use_distinct_paths(self):
        from tests.test_content_draft_workflow import _plan
        from tests.test_change_plan_workflow import common, opportunity, opportunity_report, point
        from foreign_trade_geo_agent.core.content_opportunity import ContentOpportunityType
        value = await _expand_input()
        report = opportunity_report(opportunity(
            action_codes=(ContentOpportunityActionCode.CREATE_SUPPORTING_RESOURCE,),
            opportunity_type=ContentOpportunityType.NEW_SUPPORTING_CONTENT))
        raw = {**common('CREATE_NEW_RESOURCE', action='CREATE_SUPPORTING_RESOURCE',
                target_page_ref=None, locator_kind='NEW_PAGE'),
            'resource_purpose': 'SUPPORTING_RESOURCE', 'proposed_title': 'Chemical Compatibility Guide',
            'content_points': [point('chemical compatibility')],
            'suggested_source_page_refs': ['P1'], 'comparison_table_brief': None}
        plan = await _plan(raw, site=value.site_content, report=report)
        self.assertTrue(plan.operations)
        value = ContentDraftInput(value.site_content, report, plan)
        outline = plan.operations[0].new_resource_spec.outline_headings

        def generation(counts):
            index = 0
            sections = []
            for heading, count in zip(outline, counts):
                blocks = []
                for _ in range(count):
                    # Unique numeric context is permitted for an external-only general claim.
                    blocks.append({'kind': 'PARAGRAPH', 'claims': [{'text': f'Context item {index} is documented.',
                        'claim_type': 'GENERAL_TECHNICAL_CONTEXT', 'page_refs': [], 'source_refs': ['S1']}]})
                    index += 1
                sections.append({'outline_heading': heading, 'blocks': blocks})
            return _generation(json.dumps({'draft': {'change_ref': 'C1', 'draft_type': 'NEW_RESOURCE_DRAFT', 'sections': sections}}))

        # Two legal sections, each <= 4 paragraphs, can still exceed 8 total blocks with bullets.
        self.assertEqual(len(outline), 2)
        local = generation((5, 1))
        workflow = ContentDraftWorkflow(_DraftFakeWriter([local]))
        self.assertEqual((await workflow.run(value)).error, 'BLOCK_BUDGET')
        self.assertEqual(workflow.last_block_budget_violation.field_path, 'draft.sections[0].blocks')
        self.assertEqual(workflow.last_block_budget_violation.rule_id.value, 'PARAGRAPH_COUNT')
        raw_output = json.loads(generation((4, 4)).text)
        raw_output['draft']['sections'][0]['blocks'].append({'kind': 'BULLET_LIST', 'items': [{
            'text': 'Buyer context is documented.', 'claim_type': 'GENERAL_TECHNICAL_CONTEXT',
            'page_refs': [], 'source_refs': ['S1']}]})
        workflow = ContentDraftWorkflow(_DraftFakeWriter([_generation(json.dumps(raw_output))]))
        self.assertEqual((await workflow.run(value)).error, 'BLOCK_BUDGET')
        descriptor = workflow.last_block_budget_violation
        self.assertEqual((descriptor.rule_id.value, descriptor.field_path, descriptor.actual_count),
            ('RESOURCE_TOTAL_BLOCK_COUNT', 'draft.sections[*].blocks', 9))
        budget = json.loads(build_content_draft_prompt(value, 'C1').material_json())['contract']['block_budget']
        self.assertEqual(budget['paragraph_blocks_per_section'], {'min': 0, 'max': 4})
        self.assertEqual(budget['total_blocks_across_sections'], {'max': 8})

    async def test_table_contract_and_rejection_use_the_same_cell_limit(self):
        value = await _expand_input()
        operation = replace(value.change_plan_report.operations[0],
            source_action_code=ContentOpportunityActionCode.ADD_COMPARISON_TABLE,
            operation_type=ChangeOperationType.ADD_COMPARISON_TABLE, proposed_heading='Selection comparison',
            content_points=(), comparison_table_spec=ComparisonTableSpec(('material', 'size'), ('selection', 'maintenance')))
        spec = ContentDraftSpecification('C1', ContentDraftType.COMPARISON_TABLE_DRAFT,
            cells=(TableCellSpecification('selection', 'material', 'DRAFT_SENTINEL'),) * 31)
        _, error = ContentDraftWorkflow._finalize(1, spec, operation, value)
        self.assertEqual(error, 'COMPARISON_UNAVAILABLE')
        _, error = validate_legacy_table(1, spec, operation, value.opportunity_report.opportunities[0],
            value.site_content, value.opportunity_report)
        self.assertEqual(error, 'BLOCK_BUDGET')
        descriptor = describe_draft_block_budget_violation(spec, operation)
        self.assertEqual((descriptor.rule_id.value, descriptor.field_path, descriptor.actual_count),
            ('TABLE_CELL_COUNT', 'draft.cells', 31))
        self.assertEqual(content_draft_block_budget_contract(operation.operation_type)['cells'], {'min': 0, 'max': 30})
        with self.assertRaisesRegex(ValueError, 'COMPARISON_UNAVAILABLE'):
            replace(build_content_draft_prompt(value, 'C1'), operation=operation)

    async def test_descriptor_rejects_arbitrary_text_and_valid_counts(self):
        workflow = ContentDraftWorkflow(_DraftFakeWriter([five_paragraphs()]))
        await workflow.run(await _expand_input())
        descriptor = workflow.last_block_budget_violation
        for name, value in [('field_path', 'DRAFT_SENTINEL'), ('change_ref', 'secret'),
                            ('rule_id', 'prompt'), ('actual_count', 4), ('actual_count', -1)]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                replace(descriptor, **{name: value})

    async def test_success_other_category_and_invalid_input_clear_stale_descriptor(self):
        value = await _expand_input()
        writer = _DraftFakeWriter([five_paragraphs(), _generation(_section_text()), five_paragraphs(), _generation('{}')])
        workflow = ContentDraftWorkflow(writer)
        await workflow.run(value)
        self.assertIsNotNone(workflow.last_block_budget_violation)
        self.assertIsNone((await workflow.run(value)).error)
        self.assertIsNone(workflow.last_block_budget_violation)
        await workflow.run(value)
        self.assertEqual((await workflow.run(value)).error, 'FIELD_CONTRACT')
        self.assertIsNone(workflow.last_block_budget_violation)
        await workflow.run(object())
        self.assertIsNone(workflow.last_block_budget_violation)

    async def test_cli_category_gate_and_context_clearing(self):
        workflow = ContentDraftWorkflow(_DraftFakeWriter([five_paragraphs()]))
        report = await workflow.run(await _expand_input())
        context = RunDiagnosticContext()
        context.block_budget_violation = workflow.last_block_budget_violation
        outer = SimpleNamespace(run_diagnostics=context)
        result = SimpleNamespace(run=SimpleNamespace(status=RunStatus.FAILED),
            stopped_stage=EndToEndStage.CONTENT_DRAFT, terminal_report=report)
        payload = _plan_validation_diagnostic(result, outer)
        self.assertEqual(payload['rule_id'], 'PARAGRAPH_COUNT')
        self.assertEqual(payload['field_path'], 'draft.blocks')
        self.assertNotIn('DRAFT_SENTINEL', json.dumps(payload))
        result.terminal_report = replace(report, error='CLAIM_BUDGET')
        self.assertEqual(_plan_validation_diagnostic(result, outer), {'category': 'CLAIM_BUDGET'})
        context.clear()
        self.assertIsNone(context.block_budget_violation)


class ComposedDraftBlockBudgetTests(unittest.TestCase):
    def test_cli_sqlite_and_public_progress_keep_budget_descriptor_transient(self):
        from tests.test_cli import CliTests
        from tests.test_mvp_composed_flow import _FixtureContentDraftWriter
        from foreign_trade_geo_agent.web.composition import build_live_composition
        from foreign_trade_geo_agent.web.live_application import LiveApplicationService
        from foreign_trade_geo_agent.web.jobs import LocalJobRegistry

        async def invalid_generation(_writer, _prompt):
            return five_paragraphs()

        with TemporaryDirectory() as temporary, patch.object(
                _FixtureContentDraftWriter, 'write_content_draft', invalid_generation):
            db, workflows, (code, stdout, stderr) = CliTests()._run_real_fake_boundary_plan(Path(temporary))
            self.assertEqual((code, stderr), (1, ''))
            payload = json.loads(stdout)
            self.assertEqual(payload['validation_diagnostic']['rule_id'], 'PARAGRAPH_COUNT')
            self.assertEqual(payload['validation_diagnostic']['actual_count'], 5)
            self.assertIsNotNone(workflows[0].run_diagnostics.block_budget_violation)
            composition = build_live_composition(db, provider_configuration_ready=False)
            service = LiveApplicationService(composition, LocalJobRegistry())
            progress = json.dumps(asdict(service.get_progress(run_id=payload['run_id'])))
            with closing(sqlite3.connect(db)) as connection:
                dump = '\n'.join(connection.iterdump())
                self.assertEqual(connection.execute('SELECT count(*) FROM artifacts').fetchone()[0], 5)
                self.assertEqual(connection.execute('SELECT count(*) FROM wordpress_draft_attempts').fetchone()[0], 0)
                self.assertEqual(connection.execute('SELECT count(*) FROM wordpress_draft_verifications').fetchone()[0], 0)
            for forbidden in ['DRAFT_SENTINEL', 'PARAGRAPH_COUNT', 'block_budget_violation', 'draft.blocks']:
                self.assertNotIn(forbidden, dump)
                self.assertNotIn(forbidden, progress)


if __name__ == '__main__':
    unittest.main()
