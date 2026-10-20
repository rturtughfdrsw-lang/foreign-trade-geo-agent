"""Offline request contracts; controlled responses do not prove model compliance."""

import json
import os
import unittest
from unittest.mock import patch

import httpx

from foreign_trade_geo_agent.adapters.deepseek_content_draft import DeepSeekContentDraftWriter
from foreign_trade_geo_agent.core.content_draft import (
    MAX_INPUT_ENVELOPE_BYTES,
    MAX_INPUT_ENVELOPE_CHARS,
    MAX_SYSTEM_PROMPT_BYTES,
    MAX_SYSTEM_PROMPT_CHARS,
    ContentDraftInput,
    ContentDraftStatus,
)
from foreign_trade_geo_agent.core.content_opportunity import ContentOpportunityActionCode
from foreign_trade_geo_agent.workflows.change_plan import ChangePlanWorkflow
from foreign_trade_geo_agent.workflows.content_draft import ContentDraftWorkflow
from tests.test_change_plan_workflow import (
    FakeWriter as PlanWriter, common, generated, opportunity, opportunity_report, packet, page,
)
from tests.test_content_draft_table_coordinates import _cell, _response
from tests.test_content_draft_workflow import _section_text
from tests.comparison_fixtures import legacy_table_operation, validate_legacy_table
from foreign_trade_geo_agent.core.content_draft import _operation_payload
from foreign_trade_geo_agent.workflows.content_draft import _parse_specification


class DraftNumericPromptRequestTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        site = packet(page("P4", body=(
            "Chemical compatibility, material selection, port size, application, "
            "maintenance considerations, pump performance. Reference 316."
        )))
        opportunities = opportunity_report(opportunity(
            page_refs=("P4",),
            action_codes=(ContentOpportunityActionCode.EXPAND_PAGE_SECTION, ContentOpportunityActionCode.ADD_COMPARISON_TABLE),
        ))
        raw = {
            **common("ADD_COMPARISON_TABLE", action="ADD_COMPARISON_TABLE",
                     page_refs=["P4"], target_page_ref="P4"),
            "proposed_heading": "Pump comparison",
            "column_headers": ["chemical compatibility", "material selection", "port size",
                               "application", "maintenance considerations"],
            "row_dimensions": ["pump performance"],
        }
        ordinary = {**common("EXPAND_SECTION", action="EXPAND_PAGE_SECTION",
                            page_refs=["P4"], target_page_ref="P4"),
                    "content_points": [{"intent": "EXPLAIN", "subject_ref": "P4.CP_02"}]}
        plan = await ChangePlanWorkflow(PlanWriter(generated([ordinary]))).run(site, opportunities)
        self.assertEqual(plan.status.value, "success")
        self.site, self.opportunities = site, opportunities
        self.legacy_operation = legacy_table_operation(page_ref="P4",
            columns=tuple(raw["column_headers"]), rows=tuple(raw["row_dimensions"]))
        self.cells = [
            _cell("C1_CELL_001", "Chemical compatibility considerations", ("P4",)),
            _cell("C1_CELL_002", "Material selection context", (), ("S1",)),
            _cell("C1_CELL_003", "Port selection context"),
            _cell("C1_CELL_004", "Application context"),
            _cell("C1_CELL_005", "Maintenance context"),
        ]
        # Current requests exercise ordinary SEO; legacy cells remain local projections.
        unsafe_section = json.loads(_section_text())
        unsafe_section["draft"]["blocks"][0]["claims"][0].update(text="316", page_refs=["P4"])
        safe_section = json.loads(_section_text())
        safe_section["draft"]["blocks"][0]["claims"][0].update(
            text="Chemical compatibility considerations", page_refs=["P4"])
        responses = [json.dumps(unsafe_section), json.dumps(safe_section)]
        self.requests = []

        def handler(request):
            self.requests.append(json.loads(request.content))
            return httpx.Response(200, json={"choices": [{
                "message": {"content": responses[len(self.requests) - 1]},
                "finish_reason": "stop",
            }]})

        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "TEST_KEY"}, clear=True):
            writer = DeepSeekContentDraftWriter(transport=httpx.MockTransport(handler))
            self.result = await ContentDraftWorkflow(writer).run(
                ContentDraftInput(site, opportunities, plan)
            )
        self.assertEqual(len(self.requests), 2)
        self.materials = [json.loads(body["messages"][1]["content"])
                          for body in self.requests]

    def test_initial_request_carries_bare_and_cell_local_numeric_rules(self):
        system = self.requests[0]["messages"][0]["content"]
        for instruction in (
            "Never emit a numeric expression the validator treats as bare",
            "including standalone integers and decimals",
            "even if it appears in P evidence or its unit is in a table label",
            "preserving number-unit spacing",
            "Each comparison-table cell's numbers must come from that cell's own cited P evidence",
            "page_refs or source_refs alone does not establish numeric grounding",
            "never substitute numbers from another cell, another Change, or an uncited page",
        ):
            with self.subTest(instruction=instruction):
                self.assertIn(instruction, system)

    def test_initial_request_forbids_evasion_and_unverified_comparisons(self):
        system = self.requests[0]["messages"][0]["content"]
        for instruction in (
            "never invent or append units, symbols, or percentages to bypass validation",
            "prefer accurate, conservative non-numeric wording supported by current evidence",
            "never invent replacement facts",
            "never evade numeric validation by omitting a required cell, deleting a coordinate, or changing the schema",
            "do not assert unverified advantages, rankings, or performance conclusions",
            "only in non-first-party ordinary claims as GENERAL_TECHNICAL_CONTEXT",
        ):
            with self.subTest(instruction=instruction):
                self.assertIn(instruction, system)

    def test_retry_keeps_system_rules_and_replaces_ambiguous_omission_guidance(self):
        self.assertEqual(self.requests[1]["messages"][0], self.requests[0]["messages"][0])
        self.assertIsNone(self.materials[0]["contract"]["retry_feedback"])
        feedback = self.materials[1]["contract"]["retry_feedback"]
        self.assertEqual(feedback["validator"], "NUMERIC_NOT_GROUNDED")
        action = feedback["required_action"]
        for instruction in (
            "Regenerate the complete response under the system NUMERIC RULE",
            "Never emit a bare number",
            "accurate, conservative non-numeric wording supported by current evidence",
            "do not invent replacement facts",
            "Preserve required table cells, cell_ref coordinates, schema, and row/column coverage",
        ):
            with self.subTest(instruction=instruction):
                self.assertIn(instruction, action)
        self.assertNotIn("omit the claim", action)

    def test_retry_preserves_material_scope_catalog_and_coverage_instructions(self):
        first, retry = self.materials
        first_without_feedback = {**first, "contract": {
            **first["contract"], "retry_feedback": None,
        }}
        retry_without_feedback = {**retry, "contract": {
            **retry["contract"], "retry_feedback": None,
        }}
        self.assertEqual(retry_without_feedback, first_without_feedback)
        for body, material in zip(self.requests, self.materials):
            system = body["messages"][0]["content"]
            self.assertIn("Cover every supplied column and row dimension at least once", system)
            self.assertIn("without duplicate cell_ref", system)
            self.assertIn('Each cell is exactly {"cell_ref","text","page_refs","source_refs"}', system)
            self.assertIn("never output row_dimension or column in a cell", system)
            self.assertIsNone(material["change"].get("comparison_table"))
            table = _operation_payload(self.legacy_operation, pages=self.site.pages,
                sources=self.opportunities.source_materials)["comparison_table"]
            table = json.loads(json.dumps(table))
            self.assertEqual(table["row_dimensions"], ["pump performance"])
            self.assertEqual(table["column_headers"], [
                "chemical compatibility", "material selection", "port size",
                "application", "maintenance considerations",
            ])
            self.assertEqual(table["cell_catalog"], [{
                "cell_ref": f"C1_CELL_{n:03d}", "row_dimension": "pump performance",
                "column": column,
            } for n, column in enumerate(table["column_headers"], 1)])
            self.assertEqual(material["change"]["page_refs"], ["P4"])
            self.assertEqual(material["change"]["source_refs"], ["S1"])

    def test_section_retry_and_legacy_projection_preserve_text_and_refs(self):
        self.assertEqual(self.result.status, ContentDraftStatus.SUCCESS)
        ordinary = self.result.drafts[0]
        self.assertEqual(ordinary.draft_type.value, "SECTION_DRAFT")
        self.assertEqual(ordinary.blocks[0].claims[0].text, "Chemical compatibility considerations")
        self.assertEqual(ordinary.blocks[0].claims[0].page_refs, ("P4",))
        spec = _parse_specification(_response(list(reversed(self.cells))),
            expected_change_ref="C1", operation=self.legacy_operation)
        item, error = validate_legacy_table(1, spec, self.legacy_operation,
            self.opportunities.opportunities[0], self.site, self.opportunities)
        self.assertIsNone(error)
        cells = item.blocks[0].cells
        self.assertEqual(len(cells), 5)
        self.assertEqual([cell.column for cell in cells], [
            "chemical compatibility", "material selection", "port size",
            "application", "maintenance considerations",
        ])
        self.assertEqual({cell.row_dimension for cell in cells}, {"pump performance"})
        self.assertEqual([(cell.text, cell.page_refs, cell.source_refs) for cell in cells], [
            ("Chemical compatibility considerations", ("P4",), ()),
            ("Material selection context", (), ("S1",)),
            ("Port selection context", (), ()),
            ("Application context", (), ()),
            ("Maintenance context", (), ()),
        ])

    def test_initial_and_retry_requests_stay_within_prompt_envelope_budgets(self):
        for body in self.requests:
            system = body["messages"][0]["content"]
            envelope = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
            self.assertLessEqual(len(system), MAX_SYSTEM_PROMPT_CHARS)
            self.assertLessEqual(len(system.encode("utf-8")), MAX_SYSTEM_PROMPT_BYTES)
            self.assertLessEqual(len(envelope), MAX_INPUT_ENVELOPE_CHARS)
            self.assertLessEqual(len(envelope.encode("utf-8")), MAX_INPUT_ENVELOPE_BYTES)


if __name__ == "__main__":
    unittest.main()
