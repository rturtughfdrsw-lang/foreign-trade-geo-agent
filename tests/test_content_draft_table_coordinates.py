"""Offline contract tests for transient comparison-table coordinates."""

import json
import unittest
from dataclasses import replace

from foreign_trade_geo_agent.core import content_draft
from foreign_trade_geo_agent.core.change_plan import ChangePlanStatus
from foreign_trade_geo_agent.core.content_draft import (
    CONTENT_DRAFT_LIMITATIONS,
    MAX_TABLE_COLUMNS,
    MAX_TABLE_ROWS,
    ContentDraftGeneration,
    ContentDraftGenerationStatus,
    ContentDraftInput,
    ContentDraftStatus,
    build_content_draft_prompt,
    finalize_draft_item,
)
from foreign_trade_geo_agent.core.content_opportunity import ContentOpportunityActionCode
from foreign_trade_geo_agent.core.history import ArtifactType
from foreign_trade_geo_agent.storage.serialization import decode_artifact, encode_artifact
from foreign_trade_geo_agent.workflows.change_plan import ChangePlanWorkflow
from foreign_trade_geo_agent.workflows.content_draft import ContentDraftWorkflow, _parse_specification
from tests.test_change_plan_workflow import (
    FakeWriter as ChangePlanFakeWriter,
    common,
    generated,
    opportunity,
    opportunity_report,
    packet,
    page,
)
from tests.comparison_fixtures import legacy_plan, legacy_table_operation, validate_legacy_table


def _response(cells, change_ref="C1"):
    return json.dumps({"draft": {
        "change_ref": change_ref,
        "draft_type": "COMPARISON_TABLE_DRAFT",
        "cells": cells,
    }})


def _cell(ref, text, page_refs=(), source_refs=()):
    return {"cell_ref": ref, "text": text,
            "page_refs": list(page_refs), "source_refs": list(source_refs)}


class TableCoordinateContractTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.site = packet(page("P1", body=(
            "Chemical compatibility, material selection, port size, application, "
            "maintenance considerations, pump performance, buyer guidance."
        )))
        self.report = opportunity_report(opportunity(
            action_codes=(ContentOpportunityActionCode.ADD_COMPARISON_TABLE,)
        ))
        raw = {
            **common("ADD_COMPARISON_TABLE", action="ADD_COMPARISON_TABLE"),
            "proposed_heading": "Pump Comparison",
            "column_headers": ["chemical compatibility", "material selection",
                               "port size", "application", "maintenance considerations"],
            "row_dimensions": ["pump performance"],
        }
        self.plan = legacy_plan(legacy_table_operation(
            columns=tuple(raw["column_headers"]), rows=tuple(raw["row_dimensions"]),
        ))
        self.assertEqual(self.plan.status, ChangePlanStatus.SUCCESS)
        self.operation = self.plan.operations[0]

    def _parse(self, cells, *, operation=None, change_ref="C1"):
        return _parse_specification(
            _response(cells, change_ref),
            expected_change_ref=change_ref,
            operation=operation or self.operation,
        )

    def _five(self):
        return [_cell(f"C1_CELL_{n:03d}", f"Buyer consideration {n}")
                for n in range(1, 6)]

    def test_c2_five_column_one_row_catalog_is_stable_and_bounded(self):
        operation = replace(self.operation, change_id="C2")
        catalog = content_draft.table_coordinate_catalog(operation)
        self.assertEqual(catalog, tuple(
            (f"C2_CELL_{n:03d}", "pump performance", column)
            for n, column in enumerate(operation.comparison_table_spec.column_headers, 1)
        ))
        self.assertEqual(catalog, content_draft.table_coordinate_catalog(operation))
        self.assertEqual(len(catalog), 5)
        self.assertLessEqual(len(catalog), MAX_TABLE_ROWS * MAX_TABLE_COLUMNS)
        self.assertEqual(len({(row, column) for _, row, column in catalog}), 5)

    def test_legacy_projection_preserves_labels_but_prompt_is_unavailable(self):
        with self.assertRaisesRegex(ValueError, "COMPARISON_UNAVAILABLE"):
            build_content_draft_prompt(ContentDraftInput(self.site, self.report, self.plan), "C1")
        table = content_draft._operation_payload(
            self.operation, pages=self.site.pages, sources=self.report.source_materials,
        )["comparison_table"]
        self.assertEqual(len(table["cell_catalog"]), 5)
        self.assertEqual(table["cell_catalog"][0], {
            "cell_ref": "C1_CELL_001", "row_dimension": "pump performance",
            "column": "chemical compatibility",
        })
        self.assertEqual({entry["column"] for entry in table["cell_catalog"]},
                         set(table["column_headers"]))

    def test_legacy_provider_labels_are_rejected(self):
        cells = [{"row_dimension": "pump performance", "column": "chemical compatibility",
                  "text": "Buyer consideration", "page_refs": [], "source_refs": []}]
        with self.assertRaisesRegex(ValueError, "FIELD_CONTRACT"):
            self._parse(cells)

    def test_valid_cell_refs_materialize_five_columns_without_full_grid(self):
        specification = self._parse(self._five())
        self.assertEqual([cell.column for cell in specification.cells],
                         list(self.operation.comparison_table_spec.column_headers))
        self.assertEqual([cell.row_dimension for cell in specification.cells],
                         ["pump performance"] * 5)
        item, error = validate_legacy_table(1, specification, self.operation,
                                          self.report.opportunities[0], self.site, self.report)
        self.assertIsNone(error)
        self.assertEqual(len(item.blocks[0].cells), 5)
        self.assertEqual(finalize_draft_item(1, specification, self.operation,
            self.report.opportunities[0], self.site, self.report)[1], "COMPARISON_UNAVAILABLE")

    def test_unknown_and_cross_change_refs_fail_closed(self):
        for ref in ("C1_CELL_999", "C2_CELL_001"):
            with self.subTest(ref=ref):
                cells = self._five()
                cells[0]["cell_ref"] = ref
                with self.assertRaisesRegex(ValueError, "TABLE_SCHEMA_MISMATCH"):
                    self._parse(cells)

    def test_duplicate_coordinate_fails_closed(self):
        cells = self._five() + [_cell("C1_CELL_001", "Additional content")]
        with self.assertRaisesRegex(ValueError, "TABLE_SCHEMA_MISMATCH"):
            self._parse(cells)

    def test_missing_column_coverage_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "TABLE_SCHEMA_MISMATCH"):
            self._parse(self._five()[:-1])

    def test_missing_row_coverage_fails_closed(self):
        operation = replace(self.operation, comparison_table_spec=replace(
            self.operation.comparison_table_spec,
            row_dimensions=("pump performance", "buyer guidance"),
        ))
        with self.assertRaisesRegex(ValueError, "TABLE_SCHEMA_MISMATCH"):
            self._parse(self._five(), operation=operation)

    def test_additional_coordinate_is_preserved_and_sorted(self):
        operation = replace(self.operation, comparison_table_spec=replace(
            self.operation.comparison_table_spec,
            row_dimensions=("pump performance", "buyer guidance"),
        ))
        cells = self._five() + [_cell("C1_CELL_008", "Extra buyer context"),
                                _cell("C1_CELL_006", "Required second row")]
        specification = self._parse(list(reversed(cells)), operation=operation)
        self.assertEqual([(cell.row_dimension, cell.column) for cell in specification.cells],
                         [("pump performance", col) for col in
                          operation.comparison_table_spec.column_headers] + [
                              ("buyer guidance", "chemical compatibility"),
                              ("buyer guidance", "port size")])
        self.assertEqual(specification.cells[-2].text, "Required second row")
        self.assertEqual(specification.cells[-1].text, "Extra buyer context")
        _, error = validate_legacy_table(1, specification, operation,
                                       self.report.opportunities[0], self.site, self.report)
        self.assertIsNone(error)

    def test_sparse_coverage_uses_original_validator_order(self):
        operation = replace(self.operation, comparison_table_spec=replace(
            self.operation.comparison_table_spec,
            row_dimensions=("pump performance", "buyer guidance"),
        ))
        cells = [_cell("C1_CELL_009", "Fourth column"),
                 _cell("C1_CELL_007", "Second column"),
                 _cell("C1_CELL_001", "First column"),
                 _cell("C1_CELL_005", "Fifth column"),
                 _cell("C1_CELL_003", "Third column")]
        specification = self._parse(cells, operation=operation)
        self.assertEqual([cell.column for cell in specification.cells],
                         list(operation.comparison_table_spec.column_headers))
        _, error = validate_legacy_table(1, specification, operation,
                                       self.report.opportunities[0], self.site, self.report)
        self.assertIsNone(error)

    def test_unorderable_sparse_coverage_fails_original_validator_order(self):
        operation = replace(self.operation, comparison_table_spec=replace(
            self.operation.comparison_table_spec,
            row_dimensions=("pump performance", "buyer guidance"),
        ))
        cells = [_cell("C1_CELL_002", "Second column"),
                 _cell("C1_CELL_006", "First column"),
                 _cell("C1_CELL_003", "Third column"),
                 _cell("C1_CELL_004", "Fourth column"),
                 _cell("C1_CELL_005", "Fifth column")]
        with self.assertRaisesRegex(ValueError, "TABLE_SCHEMA_MISMATCH"):
            self._parse(cells, operation=operation)

    def test_more_than_existing_cell_budget_is_rejected(self):
        cells = self._five() * 7
        with self.assertRaisesRegex(ValueError, "BLOCK_BUDGET"):
            self._parse(cells)

    def test_cell_text_and_refs_stay_with_ref_after_sorting(self):
        cells = self._five()
        cells[0] = _cell("C1_CELL_001", "First unique context", ("P1",))
        cells[4] = _cell("C1_CELL_005", "Last unique context", (), ("S1",))
        specification = self._parse(list(reversed(cells)))
        self.assertEqual((specification.cells[0].text, specification.cells[0].page_refs),
                         ("First unique context", ("P1",)))
        self.assertEqual((specification.cells[4].text, specification.cells[4].source_refs),
                         ("Last unique context", ("S1",)))

    def test_budget_and_evidence_validators_remain(self):
        cells = self._five()
        cells[0] = _cell("C1_CELL_001", "Our pump pressure is 10 bar", ("P1",))
        specification = self._parse(cells)
        _, error = validate_legacy_table(1, specification, self.operation,
                                       self.report.opportunities[0], self.site, self.report)
        self.assertEqual(error, "NUMERIC_NOT_GROUNDED")
        cells[0] = _cell("C1_CELL_001", "Buyer consideration 1", ("P9",))
        specification = self._parse(cells)
        _, error = validate_legacy_table(1, specification, self.operation,
                                       self.report.opportunities[0], self.site, self.report)
        self.assertEqual(error, "EVIDENCE_OUTSIDE_CHANGE_SCOPE")
        self.assertEqual(MAX_TABLE_ROWS * MAX_TABLE_COLUMNS, 30)
        self.assertEqual(MAX_TABLE_COLUMNS, 5)

    def test_materialized_artifact_has_no_cell_refs_and_decodes_as_v1(self):
        specification = self._parse(self._five())
        item, error = validate_legacy_table(1, specification, self.operation,
                                          self.report.opportunities[0], self.site, self.report)
        self.assertIsNone(error)
        from foreign_trade_geo_agent.core.content_draft import ContentDraftReport
        report = ContentDraftReport(ContentDraftStatus.SUCCESS, (item,),
                                    CONTENT_DRAFT_LIMITATIONS, None)
        encoded = encode_artifact(ArtifactType.CONTENT_DRAFT, report)
        self.assertNotIn("cell_ref", encoded)
        self.assertEqual(decode_artifact(ArtifactType.CONTENT_DRAFT, 1, encoded), report)

    async def test_legacy_table_workflow_rejects_before_writer(self):
        class Writer:
            calls = 0
            async def write_content_draft(self, prompt):
                self.calls += 1
                return ContentDraftGeneration(
                    provider="fake", model="fake",
                    status=ContentDraftGenerationStatus.SUCCESS,
                    text=_response(list(reversed(self_cells))), error=None,
                )

        self_cells = self._five()
        writer = Writer()
        result = await ContentDraftWorkflow(writer).run(
            ContentDraftInput(self.site, self.report, self.plan)
        )
        self.assertEqual(result.status, ContentDraftStatus.INVALID_INPUT)
        self.assertEqual(result.error, "COMPARISON_UNAVAILABLE")
        self.assertEqual(result.drafts, ())
        self.assertEqual(writer.calls, 0)
