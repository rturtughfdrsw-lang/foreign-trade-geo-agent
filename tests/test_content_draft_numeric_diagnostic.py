"""Numeric failure locations are exact, transient, and contain no evidence text."""
from contextlib import closing
from dataclasses import asdict, fields, replace
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from foreign_trade_geo_agent.cli import _plan_validation_diagnostic
from foreign_trade_geo_agent.core.change_plan import ChangeOperationType, ComparisonTableSpec, InternalLinkSpec, NewResourceSpec
from foreign_trade_geo_agent.core.content_draft import (
    ContentDraftStatus, ContentDraftSpecification, ContentDraftType, NewResourceSectionSpecification,
    TableCellSpecification, build_content_draft_prompt, describe_numeric_grounding_violation, finalize_draft_item,
)
from foreign_trade_geo_agent.core.content_opportunity import ContentOpportunityActionCode
from foreign_trade_geo_agent.core.history import ArtifactType, RunStatus
from foreign_trade_geo_agent.core.orchestration import EndToEndStage
from foreign_trade_geo_agent.storage.serialization import encode_artifact, decode_artifact
from foreign_trade_geo_agent.workflows.content_draft import ContentDraftWorkflow, _parse_specification
from foreign_trade_geo_agent.workflows.run_diagnostics import RunDiagnosticContext
from tests.test_content_draft_workflow import _DraftFakeWriter, _expand_input, _generation, _section_text
from tests.comparison_fixtures import validate_legacy_table


def response(text='Our pump delivers 987654 GPM.', *, bullet=False):
    raw = json.loads(_section_text())
    claim = raw['draft']['blocks'][0]['claims'][0]
    claim['text'] = text
    if bullet:
        raw['draft']['blocks'] = [{'kind': 'BULLET_LIST', 'items': [claim]}]
    return _generation(json.dumps(raw))


class NumericDiagnosticTests(unittest.IsolatedAsyncioTestCase):
    async def failure(self, generation=None, value=None):
        generation = generation or response()
        writer = _DraftFakeWriter([generation, generation])
        workflow = ContentDraftWorkflow(writer)
        report = await workflow.run(value or await _expand_input())
        self.assertEqual(report.error, 'NUMERIC_NOT_GROUNDED')
        self.assertEqual(writer.calls, 2)
        return workflow, report, writer

    async def test_paragraph_exact_location_and_no_literal_or_prose(self):
        workflow, report, writer = await self.failure()
        descriptor = workflow.last_numeric_grounding_violation
        self.assertEqual(descriptor.field_path, 'draft.blocks[0].claims[0].text')
        self.assertEqual(descriptor.change_ref, 'C1')
        self.assertEqual(descriptor.draft_item_index, 0)
        self.assertEqual(descriptor.numeric_kind, 'NUMBER_WITH_UNIT')
        self.assertEqual(descriptor.cited_ref_ids, ('P1',))
        self.assertEqual(descriptor.source_namespace, 'PAGE_EVIDENCE')
        self.assertEqual(descriptor.grounding_mode, 'NORMALIZED_EXACT_NON_BARE')
        self.assertEqual((descriptor.numeric_occurrence_index, descriptor.numeric_literal_count,
                          descriptor.grounded_count, descriptor.ungrounded_count), (0, 1, 0, 1))
        encoded = json.dumps(asdict(descriptor))
        for forbidden in ['987654', 'GPM', 'Our pump', 'Chemical compatibility', 'material selection']:
            self.assertNotIn(forbidden, encoded)
        self.assertEqual([f.name for f in fields(report)],
                         ['status', 'drafts', 'limitations', 'error', 'requires_human_review'])
        artifact = encode_artifact(ArtifactType.CONTENT_DRAFT, report)
        self.assertNotIn('numeric_grounding', artifact)
        self.assertEqual(decode_artifact(ArtifactType.CONTENT_DRAFT, 1, artifact), report)
        feedback = json.loads(writer.prompts[1].material_json())['contract']['retry_feedback']
        self.assertEqual(feedback['validator'], 'NUMERIC_NOT_GROUNDED')
        self.assertIn('Never emit a bare number', feedback['required_action'])

    async def test_bullet_index_and_multiple_occurrences(self):
        value = await _expand_input()
        page = replace(value.site_content.pages[0], body_text='Our pump uses 12 inch and delivers 34 GPM.')
        value = replace(value, site_content=replace(value.site_content, pages=(page,)))
        generation = response('Our pump uses 12 inch, delivers 987654 GPM, and supports 34 GPM.', bullet=True)
        workflow, _, _ = await self.failure(generation, value)
        descriptor = workflow.last_numeric_grounding_violation
        self.assertEqual(descriptor.field_path, 'draft.blocks[0].items[0].text')
        self.assertEqual((descriptor.numeric_occurrence_index, descriptor.numeric_literal_count,
                          descriptor.grounded_count, descriptor.ungrounded_count), (1, 3, 2, 1))

    async def test_success_other_second_category_and_invalid_input_leave_no_descriptor(self):
        value = await _expand_input()
        writer = _DraftFakeWriter([response(), response(), response(), _generation(_section_text()),
                                  response(), _generation('{}')])
        workflow = ContentDraftWorkflow(writer)
        await workflow.run(value)
        self.assertIsNotNone(workflow.last_numeric_grounding_violation)
        self.assertEqual((await workflow.run(value)).status, ContentDraftStatus.SUCCESS)
        self.assertIsNone(workflow.last_numeric_grounding_violation)
        self.assertEqual((await workflow.run(value)).error, 'FIELD_CONTRACT')
        self.assertIsNone(workflow.last_numeric_grounding_violation)
        await workflow.run(object())
        self.assertIsNone(workflow.last_numeric_grounding_violation)
        self.assertEqual(writer.calls, 6)

    async def test_cli_category_gate_and_context_clear(self):
        workflow, report, _ = await self.failure()
        context = RunDiagnosticContext()
        context.numeric_grounding_violation = workflow.last_numeric_grounding_violation
        result = SimpleNamespace(run=SimpleNamespace(status=RunStatus.FAILED),
            stopped_stage=EndToEndStage.CONTENT_DRAFT, terminal_report=report)
        payload = _plan_validation_diagnostic(result, SimpleNamespace(run_diagnostics=context))
        self.assertEqual(payload['field_path'], 'draft.blocks[0].claims[0].text')
        self.assertNotIn('987654', json.dumps(payload))
        result.terminal_report = replace(report, error='CLAIM_BUDGET')
        self.assertEqual(_plan_validation_diagnostic(result, SimpleNamespace(run_diagnostics=context)),
                         {'category': 'CLAIM_BUDGET'})
        context.clear()
        self.assertIsNone(context.numeric_grounding_violation)

    async def test_descriptor_rejects_unsafe_metadata(self):
        workflow, _, _ = await self.failure()
        descriptor = workflow.last_numeric_grounding_violation
        for name, value in [('field_path', 'Our pump 987654 GPM'), ('change_ref', 'secret'),
                            ('numeric_kind', '987654 GPM'), ('cited_ref_ids', ('raw evidence',)),
                            ('source_namespace', 'prompt'), ('grounding_mode', 'loose'),
                            ('numeric_occurrence_index', 1), ('grounded_count', 1),
                            ('ungrounded_count', 0), ('draft_item_index', 8)]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                replace(descriptor, **{name: value})

    async def test_unavailable_table_stops_before_numeric_diagnostic(self):
        value = await _expand_input()
        operation = replace(value.change_plan_report.operations[0],
            source_action_code=ContentOpportunityActionCode.ADD_COMPARISON_TABLE,
            operation_type=ChangeOperationType.ADD_COMPARISON_TABLE, proposed_heading='Selection comparison',
            content_points=(), comparison_table_spec=ComparisonTableSpec(('material', 'size'), ('selection', 'maintenance')))
        prompt = SimpleNamespace(input=value, operation=operation,
            opportunity=value.opportunity_report.opportunities[0], change_ref='C1')
        spec = ContentDraftSpecification('C1', ContentDraftType.COMPARISON_TABLE_DRAFT, cells=(
            TableCellSpecification('selection', 'material', 'Material selection is documented.', ('P1',)),
            TableCellSpecification('selection', 'size', 'Port size is 987654 inch.', ('P1',)),
            TableCellSpecification('maintenance', 'material', 'Maintenance is documented.', ('P1',)),
            TableCellSpecification('maintenance', 'size', 'Application is documented.', ('P1',)),
        ))
        self.assertEqual(finalize_draft_item(1, spec, operation, prompt.opportunity,
            value.site_content, value.opportunity_report)[1], 'COMPARISON_UNAVAILABLE')
        self.assertEqual(validate_legacy_table(1, spec, operation, prompt.opportunity,
            value.site_content, value.opportunity_report)[1], 'NUMERIC_NOT_GROUNDED')
        descriptor = describe_numeric_grounding_violation(1, spec, prompt)
        self.assertIsNone(descriptor)

    async def test_nested_resource_and_link_anchor_and_insertion_paths(self):
        from foreign_trade_geo_agent.core.change_plan import NewResourcePurpose, ChangeTargetKind, SectionLocator, SectionLocatorKind
        value = await _expand_input()
        prompt = build_content_draft_prompt(value, 'C1')
        section = _parse_specification(response().text, expected_change_ref='C1')
        operation = replace(prompt.operation, operation_type=ChangeOperationType.CREATE_NEW_RESOURCE,
            source_action_code=ContentOpportunityActionCode.CREATE_SUPPORTING_RESOURCE,
            target_kind=ChangeTargetKind.CREATE_NEW_PAGE, proposed_heading='Guidance',
            locator=SectionLocator(SectionLocatorKind.NEW_PAGE, None, None, None, None),
            new_resource_spec=NewResourceSpec(NewResourcePurpose.SUPPORTING_RESOURCE,
                'Guidance', ('Material selection', 'Application'), prompt.operation.content_points, ('P1',), None))
        prompt = replace(prompt, operation=operation)
        good = _parse_specification(_section_text(), expected_change_ref='C1')
        resource = ContentDraftSpecification('C1', ContentDraftType.NEW_RESOURCE_DRAFT, sections=(
            NewResourceSectionSpecification('Material selection', good.blocks),
            NewResourceSectionSpecification('Application', section.blocks),
        ))
        descriptor = describe_numeric_grounding_violation(1, resource, prompt)
        self.assertEqual(descriptor.field_path, 'draft.sections[1].blocks[0].claims[0].text')
        page = replace(value.site_content.pages[0], evidence_id='P2', final_url='https://example.com/target')
        value = replace(value, site_content=replace(value.site_content,
            pages=(*value.site_content.pages, page), source_page_count=2))
        operation = replace(value.change_plan_report.operations[0], operation_type=ChangeOperationType.ADD_INTERNAL_LINK,
            source_action_code=ContentOpportunityActionCode.ADD_INTERNAL_LINK,
            content_points=(), page_refs=('P1', 'P2'),
            locator=SectionLocator(SectionLocatorKind.PAGE_LEVEL, 'P1', None, None, None),
            internal_link_spec=InternalLinkSpec('P1', 'P2', 'https://example.com/source',
                'https://example.com/target', 'Material selection'))
        prompt = replace(prompt, operation=operation, input=value)
        link = ContentDraftSpecification('C1', ContentDraftType.INTERNAL_LINK_DRAFT,
            anchor_text='Our pump 987654 GPM', insertion_claims=section.blocks[0].claims)
        descriptor = describe_numeric_grounding_violation(1, link, prompt)
        self.assertEqual(descriptor.field_path, 'draft.anchor_text')
        self.assertEqual(descriptor.source_namespace, 'TARGET_PAGE_EVIDENCE')
        link = replace(link, anchor_text='Material selection')
        descriptor = describe_numeric_grounding_violation(1, link, prompt)
        self.assertEqual(descriptor.field_path, 'draft.insertion_claims[0].text')

    async def test_observer_uses_original_validation_precedence_and_success(self):
        value = await _expand_input()
        prompt = build_content_draft_prompt(value, 'C1')
        for generation, category in [(response(), 'NUMERIC_NOT_GROUNDED'),
                                     (_generation(_section_text()), None)]:
            spec = _parse_specification(generation.text, expected_change_ref='C1')
            before = finalize_draft_item(1, spec, prompt.operation, prompt.opportunity,
                value.site_content, value.opportunity_report)
            descriptor = describe_numeric_grounding_violation(1, spec, prompt)
            self.assertEqual(before[1], category)
            self.assertEqual(descriptor is not None, category == 'NUMERIC_NOT_GROUNDED')
            self.assertEqual(finalize_draft_item(1, spec, prompt.operation, prompt.opportunity,
                value.site_content, value.opportunity_report), before)
        raw = json.loads(response().text)
        raw['draft']['blocks'][0]['claims'][0]['page_refs'] = ['P99']
        spec = _parse_specification(json.dumps(raw), expected_change_ref='C1')
        self.assertIsNone(describe_numeric_grounding_violation(1, spec, prompt))


class ComposedNumericDiagnosticTests(unittest.TestCase):
    def test_cli_sqlite_public_progress_keep_diagnostic_transient(self):
        from tests.test_cli import CliTests
        from tests.test_mvp_composed_flow import _FixtureContentDraftWriter
        from foreign_trade_geo_agent.web.composition import build_live_composition
        from foreign_trade_geo_agent.web.live_application import LiveApplicationService
        from foreign_trade_geo_agent.web.jobs import LocalJobRegistry

        async def invalid_generation(_writer, _prompt):
            return response()

        with TemporaryDirectory() as temporary, patch.object(
                _FixtureContentDraftWriter, 'write_content_draft', invalid_generation):
            db, workflows, (code, stdout, stderr) = CliTests()._run_real_fake_boundary_plan(Path(temporary))
            self.assertEqual((code, stderr), (1, ''))
            payload = json.loads(stdout)
            self.assertEqual(payload['validation_diagnostic']['field_path'], 'draft.blocks[0].claims[0].text')
            self.assertIsNotNone(workflows[0].run_diagnostics.numeric_grounding_violation)
            composition = build_live_composition(db, provider_configuration_ready=False)
            service = LiveApplicationService(composition, LocalJobRegistry())
            progress = json.dumps(asdict(service.get_progress(run_id=payload['run_id'])))
            with closing(sqlite3.connect(db)) as connection:
                dump = '\n'.join(connection.iterdump())
                self.assertEqual(connection.execute('SELECT count(*) FROM artifacts').fetchone()[0], 5)
                self.assertEqual(connection.execute('SELECT count(*) FROM wordpress_draft_attempts').fetchone()[0], 0)
                self.assertEqual(connection.execute('SELECT count(*) FROM wordpress_draft_verifications').fetchone()[0], 0)
            for forbidden in ['987654', 'Our pump delivers', 'numeric_grounding_violation',
                              'NORMALIZED_EXACT_NON_BARE', 'draft.blocks[0].claims[0].text']:
                self.assertNotIn(forbidden, dump)
                self.assertNotIn(forbidden, progress)


if __name__ == '__main__':
    unittest.main()
