"""Controlled provider outputs for table numeric grounding; never use live I/O."""

from dataclasses import asdict, replace
import json
from types import SimpleNamespace
import unittest

from foreign_trade_geo_agent.cli import _plan_validation_diagnostic
from foreign_trade_geo_agent.core.content_draft import (
    ContentDraftInput, ContentDraftStatus, build_content_draft_prompt,
    describe_numeric_grounding_violation, extract_numeric_expressions,
    finalize_draft_item,
)
from foreign_trade_geo_agent.core.content_opportunity import ContentOpportunityActionCode
from foreign_trade_geo_agent.core.history import RunStatus
from foreign_trade_geo_agent.core.orchestration import EndToEndStage
from foreign_trade_geo_agent.workflows.change_plan import ChangePlanWorkflow
from foreign_trade_geo_agent.workflows.content_draft import ContentDraftWorkflow, _parse_specification
from foreign_trade_geo_agent.workflows.run_diagnostics import RunDiagnosticContext
from tests.test_change_plan_workflow import (
    FakeWriter as PlanWriter, common, expand, generated, opportunity,
    opportunity_report, packet, page,
)
from tests.test_content_draft_table_coordinates import _cell, _response
from tests.test_content_draft_workflow import _DraftFakeWriter, _generation, _section_text
from tests.comparison_fixtures import legacy_plan, legacy_table_operation, validate_legacy_table


class TableNumericContractTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.site = packet(page('P1'), page('P4', body=(
            'Chemical compatibility, material selection, port size, application, '
            'maintenance considerations, pump performance. Pressure 10 bar. '
            'Temperature 20 C. Reference 316. Attached pressure 10bar. '
            'Attached temperature 20\u00b0C.'
        )))
        self.report = opportunity_report(
            opportunity(),
            opportunity('R2', page_refs=('P4',),
                        action_codes=(ContentOpportunityActionCode.ADD_COMPARISON_TABLE,)),
            source_text='Buyer context supports 77 bar and reference 316.',
        )
        raw = {
            **common('ADD_COMPARISON_TABLE', action='ADD_COMPARISON_TABLE',
                     page_refs=['P4'], target_page_ref='P4'),
            'opportunity_ref': 'R2', 'proposed_heading': 'Pump comparison',
            'column_headers': ['chemical compatibility', 'material selection',
                               'port size', 'application', 'maintenance considerations'],
            'row_dimensions': ['pump performance'],
        }
        self.ordinary_plan = await ChangePlanWorkflow(PlanWriter(generated([expand()]))).run(
            self.site, self.report)
        self.ordinary_value = ContentDraftInput(self.site, self.report, self.ordinary_plan)
        self.plan = legacy_plan(self.ordinary_plan.operations[0], legacy_table_operation(
            change_id='C2', opportunity_ref='R2', page_ref='P4',
            columns=tuple(raw['column_headers']), rows=tuple(raw['row_dimensions']),
        ))
        self.assertEqual(self.plan.status.value, 'success')
        self.value = ContentDraftInput(self.site, self.report, self.plan)
        self.operation = self.plan.operations[1]

    def cells(self, text, page_refs=('P4',), source_refs=()):
        return [_cell('C2_CELL_001', text, page_refs, source_refs),
                _cell('C2_CELL_002', 'Material selection context'),
                _cell('C2_CELL_003', 'Port selection context'),
                _cell('C2_CELL_004', 'Application context'),
                _cell('C2_CELL_005', 'Maintenance context')]

    def finalize(self, cells):
        spec = _parse_specification(_response(cells, 'C2'),
                                    expected_change_ref='C2', operation=self.operation)
        result = validate_legacy_table(2, spec, self.operation, self.report.opportunities[1],
                                     self.site, self.report)
        return spec, result

    async def test_provider_matrix_preserves_fail_closed_numeric_contract(self):
        cases = [
            ('Pressure 10 bar', ('P4',), (), None),
            ('Pressure 99 bar', ('P4',), (), 'NUMERIC_NOT_GROUNDED'),
            ('316', ('P4',), (), 'NUMERIC_NOT_GROUNDED'),
            ('Pressure 10 bar and 316', ('P4',), (), 'NUMERIC_NOT_GROUNDED'),
            ('Pressure 10 bar and 99 bar', ('P4',), (), 'NUMERIC_NOT_GROUNDED'),
            ('Pressure 10 bar', ('P4',), ('S1',), None),
            ('Buyer context 77 bar', ('P4',), ('S1',), 'NUMERIC_NOT_GROUNDED'),
            ('Buyer context 77 bar', (), ('S1',), None),
            ('Buyer context 77 bar', (), (), None),
            ('316', (), ('S1',), None),
            ('Our pump pressure 10 bar', (), ('S1',), 'FIRST_PARTY_FACT_WITHOUT_PAGE'),
            ('Pressure 10 bar', ('P1',), (), 'EVIDENCE_OUTSIDE_CHANGE_SCOPE'),
            ('Pressure 10 bar', ('P4',), ('S99',), 'EVIDENCE_OUTSIDE_CHANGE_SCOPE'),
        ]
        for text, pages, sources, error in cases:
            with self.subTest(text=text, pages=pages, sources=sources):
                _, (item, actual) = self.finalize(self.cells(text, pages, sources))
                self.assertEqual(actual, error)
                if error:
                    self.assertIsNone(item)
                else:
                    self.assertEqual(item.blocks[0].cells[0].text, text)
        writer = _DraftFakeWriter([])
        result = await ContentDraftWorkflow(writer).run(self.value)
        self.assertEqual(result.error, 'COMPARISON_UNAVAILABLE')
        self.assertEqual(result.status, ContentDraftStatus.INVALID_INPUT)
        self.assertEqual(writer.calls, 0)

    def test_attached_unit_expression_keeps_observed_spacing(self):
        self.assertEqual(extract_numeric_expressions('Pressure 10bar'), ('10bar',))
        self.assertEqual(extract_numeric_expressions('Temperature 20\u00b0C'), ('20\u00b0c',))

    def test_identical_attached_units_are_grounded_but_spacing_conversion_is_not(self):
        self.site = replace(self.site, pages=(self.site.pages[0], replace(
            self.site.pages[1], body_text='Pressure 10bar and temperature 20\u00b0C')))
        for text in ('Pressure 10bar', 'Temperature 20\u00b0C'):
            with self.subTest(text=text):
                _, (item, error) = self.finalize(self.cells(text))
                self.assertIsNone(error)
                self.assertIsNotNone(item)
        for text in ('Pressure 10 bar', 'Temperature 20\u00b0 C'):
            with self.subTest(text=text):
                _, (_, error) = self.finalize(self.cells(text))
                self.assertEqual(error, 'NUMERIC_NOT_GROUNDED')

    def test_claim_and_cell_have_different_first_party_gates(self):
        for kind, error in [('GENERAL_TECHNICAL_CONTEXT', None),
                            ('OBSERVED_PRODUCT_FACT', 'NUMERIC_NOT_GROUNDED')]:
            raw = json.loads(_section_text())
            raw['draft']['blocks'][0]['claims'][0].update(
                text='Buyer pressure 99 bar', claim_type=kind, source_refs=['S1'])
            spec = _parse_specification(json.dumps(raw), expected_change_ref='C1')
            _, actual = finalize_draft_item(1, spec, self.plan.operations[0],
                                            self.report.opportunities[0], self.site, self.report)
            self.assertEqual(actual, error)
        _, (_, error) = self.finalize(self.cells('Buyer pressure 99 bar', ('P4',), ('S1',)))
        self.assertEqual(error, 'NUMERIC_NOT_GROUNDED')

    def test_unit_prefix_and_embedded_identifier_are_not_exact_numeric_evidence(self):
        for text, body in [('Length 10 m', 'Length 10 mm'),
                           ('Pressure 10 bar', 'Pressure 10 barrel'),
                           ('Pressure 10 bar', 'Model A10 bar')]:
            with self.subTest(text=text, body=body):
                self.site = replace(self.site, pages=(self.site.pages[0], replace(
                    self.site.pages[1], body_text=body)))
                _, (item, error) = self.finalize(self.cells(text))
                self.assertEqual(error, 'NUMERIC_NOT_GROUNDED')
                self.assertIsNone(item)

    async def test_sorting_keeps_numeric_text_and_refs_at_legacy_coordinate(self):
        cells = self.cells('Pressure 10 bar and 316', ('P4',), ('S1',))
        spec, (_, error) = self.finalize(list(reversed(cells)))
        self.assertEqual(error, 'NUMERIC_NOT_GROUNDED')
        self.assertEqual((spec.cells[0].text, spec.cells[0].page_refs, spec.cells[0].source_refs),
                         ('Pressure 10 bar and 316', ('P4',), ('S1',)))
        self.assertEqual((spec.cells[0].row_dimension, spec.cells[0].column),
                         ('pump performance', 'chemical compatibility'))
        # Numeric diagnostic behavior is now exercised on an eligible ordinary claim.
        diagnostic, _ = await self.diagnostic_payload('Pressure 10 bar and 316', ('S1',))
        self.assertEqual((diagnostic.field_path, diagnostic.table_row_index,
                          diagnostic.table_column_index), ('draft.blocks[0].claims[0].text', None, None))
        self.assertEqual((diagnostic.numeric_kind, diagnostic.grounded_count,
                          diagnostic.ungrounded_count), ('BARE_INTEGER', 1, 1))

    async def diagnostic_payload(self, text, source_refs=()):
        opportunities = opportunity_report(opportunity(page_refs=('P4',)))
        plan = await ChangePlanWorkflow(PlanWriter(generated([expand(
            page_refs=['P4'], target_page_ref='P4',
            content_points=[{'intent': 'EXPLAIN', 'subject_ref': 'P4.CP_02'}],
        )]))).run(self.site, opportunities)
        raw = json.loads(_section_text())
        raw['draft']['blocks'][0]['claims'][0].update(
            text=text, page_refs=['P4'], source_refs=list(source_refs))
        generation = _generation(json.dumps(raw))
        workflow = ContentDraftWorkflow(_DraftFakeWriter([generation, generation]))
        report = await workflow.run(ContentDraftInput(self.site, opportunities, plan))
        self.assertEqual(report.error, 'NUMERIC_NOT_GROUNDED')
        context = RunDiagnosticContext()
        context.numeric_grounding_violation = workflow.last_numeric_grounding_violation
        result = SimpleNamespace(run=SimpleNamespace(status=RunStatus.FAILED),
                                 stopped_stage=EndToEndStage.CONTENT_DRAFT, terminal_report=report)
        return workflow.last_numeric_grounding_violation, _plan_validation_diagnostic(
            result, SimpleNamespace(run_diagnostics=context))

    async def test_safe_diagnostic_separates_bare_rule_from_evidence_mismatch(self):
        diagnostic, payload = await self.diagnostic_payload('Pressure 10 bar and 316', ('S1',))
        self.assertEqual(payload.get('rule_id'), 'BARE_NUMBER_FORBIDDEN')
        self.assertEqual(payload.get('attempt'), 2)
        self.assertEqual(payload.get('bare_number_count'), 1)
        self.assertEqual(payload.get('evidence_mismatch_count'), 0)
        self.assertIs(payload.get('has_page_refs'), True)
        self.assertIs(payload.get('has_source_refs'), True)
        self.assertIs(payload.get('is_bare_number'), True)
        self.assertIs(payload.get('evidence_match_failed'), False)
        encoded = json.dumps(asdict(diagnostic))
        self.assertNotIn('316', encoded)
        self.assertNotIn('Pressure', encoded)
        self.assertNotIn('source_text', encoded)

    async def test_safe_diagnostic_counts_each_rejection_without_literal_text(self):
        _, payload = await self.diagnostic_payload('Pressure 99 bar and 316')
        self.assertEqual(payload.get('rule_id'), 'NUMERIC_EXPRESSION_NOT_IN_CITED_PAGE')
        self.assertEqual(payload.get('bare_number_count'), 1)
        self.assertEqual(payload.get('evidence_mismatch_count'), 1)
        self.assertEqual((payload['grounded_count'], payload['ungrounded_count']), (0, 2))
        self.assertIs(payload.get('has_source_refs'), False)
        self.assertIs(payload.get('is_bare_number'), False)
        self.assertIs(payload.get('evidence_match_failed'), True)

    async def test_new_diagnostic_fields_reject_unsafe_or_inconsistent_values(self):
        diagnostic, _ = await self.diagnostic_payload('Pressure 10 bar and 316', ('S1',))
        for name, value in [('rule_id', 'raw provider text'), ('attempt', 0),
                            ('attempt', True), ('attempt', 3), ('has_source_refs', 'secret'),
                            ('bare_number_count', -1), ('bare_number_count', 0),
                            ('evidence_mismatch_count', 1),
                            ('rule_id', 'NUMERIC_EXPRESSION_NOT_IN_CITED_PAGE')]:
            with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                replace(diagnostic, **{name: value})

    def test_first_attempt_diagnostic_preserves_supplied_attempt_context(self):
        spec, (_, error) = self.finalize(self.cells('316'))
        self.assertEqual(error, 'NUMERIC_NOT_GROUNDED')
        raw = json.loads(_section_text())
        raw['draft']['blocks'][0]['claims'][0]['text'] = '316'
        ordinary = _parse_specification(json.dumps(raw), expected_change_ref='C1')
        diagnostic = describe_numeric_grounding_violation(
            1, ordinary, build_content_draft_prompt(self.ordinary_value, 'C1'), attempt=1)
        self.assertEqual(diagnostic.attempt, 1)


if __name__ == '__main__':
    unittest.main()
