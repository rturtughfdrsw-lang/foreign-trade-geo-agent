"""Comparison capability is unavailable; reading V1 never authorizes execution."""

import json
import unittest
from dataclasses import replace
import os
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import UTC, datetime, timedelta

import httpx
from foreign_trade_geo_agent.adapters.deepseek_change_plan import DeepSeekChangePlanWriter
from foreign_trade_geo_agent.adapters.deepseek_content_draft import DeepSeekContentDraftWriter

from foreign_trade_geo_agent.core import change_plan as planning
from foreign_trade_geo_agent.core import content_draft as drafting
from foreign_trade_geo_agent.core.content_opportunity import ContentOpportunityActionCode as Action
from foreign_trade_geo_agent.core.history import ArtifactType, ArtifactRecord, RunStatus, WorkflowRun
from foreign_trade_geo_agent.storage.sqlite import SQLiteHistoryStore
from foreign_trade_geo_agent.storage.serialization import decode_artifact, encode_artifact
from foreign_trade_geo_agent.workflows.change_plan import ChangePlanWorkflow
from foreign_trade_geo_agent.workflows.content_draft import ContentDraftWorkflow
from tests.comparison_fixtures import legacy_plan, legacy_table_operation
from tests.test_change_plan_workflow import FakeWriter, common, expand, generated, opportunity, opportunity_report, packet
from tests.test_content_draft_workflow import _DraftFakeWriter, _generation, _section_text


def comparison_raw():
    return {**common("ADD_COMPARISON_TABLE", action="ADD_COMPARISON_TABLE"),
            "proposed_heading": "Pump Comparison",
            "column_headers": ["material selection", "port size"],
            "row_dimensions": ["application"]}


def resource_raw():
    return {**common("CREATE_NEW_RESOURCE", action="CREATE_SUPPORTING_RESOURCE"),
            "resource_purpose": "SUPPORTING_RESOURCE",
            "proposed_title": "Chemical Compatibility Guide",
            "outline_headings": ["Material Selection", "Application"],
            "content_points": [{"intent": "EXPLAIN", "subject_ref": "S1.CP_02"}],
            "suggested_source_page_refs": ["P1"],
            "comparison_table_brief": {"column_headers": ["material selection", "port size"],
                                       "row_dimensions": ["application"]}}


class ComparisonAdmissionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.site = packet()
        self.report = opportunity_report(opportunity(action_codes=(Action.EXPAND_PAGE_SECTION, Action.ADD_COMPARISON_TABLE)))

    def prompt(self, report=None):
        return planning.build_change_plan_prompt(planning.ChangePlanInput(self.site, report or self.report))

    async def ordinary_plan(self):
        return await ChangePlanWorkflow(FakeWriter(generated([expand()]))).run(self.site, self.report)

    def test_new_allowlist_abandons_comparison_without_inventing_actions(self):
        material = json.loads(self.prompt().material_json())
        self.assertEqual(material["opportunities"][0]["allowed_operation_types"], ["EXPAND_SECTION"])
        only = opportunity_report(opportunity(action_codes=(Action.ADD_COMPARISON_TABLE,)))
        self.assertEqual(self.prompt(only).allowed_operation_types_for("R1"), ())

    async def test_provider_comparison_rejects_whole_new_plan_without_retry(self):
        writer = FakeWriter(generated([expand(), comparison_raw()]))
        result = await ChangePlanWorkflow(writer).run(self.site, self.report)
        self.assertEqual(result.status, planning.ChangePlanStatus.INVALID_OUTPUT)
        self.assertEqual(result.error, "COMPARISON_UNAVAILABLE")
        self.assertEqual(result.operations, ())
        self.assertEqual(len(writer.prompts), 1)
        self.assertEqual(result.final_validation_category.value, "OPERATION_NOT_ALLOWED")

    async def test_nested_table_cannot_bypass_via_supporting_resource(self):
        report = opportunity_report(opportunity(action_codes=(Action.CREATE_SUPPORTING_RESOURCE,)))
        writer = FakeWriter(generated([resource_raw()]))
        result = await ChangePlanWorkflow(writer).run(self.site, report)
        self.assertEqual(result.status, planning.ChangePlanStatus.INVALID_OUTPUT)
        self.assertEqual(result.error, "COMPARISON_UNAVAILABLE")
        self.assertEqual(len(writer.prompts), 1)

    async def test_comparison_only_opportunity_is_explicitly_deferred_in_new_plan(self):
        report = opportunity_report(
            opportunity(action_codes=(Action.EXPAND_PAGE_SECTION,)),
            opportunity(recommendation_id="R2", action_codes=(Action.ADD_COMPARISON_TABLE,)),
        )
        before = encode_artifact(ArtifactType.CONTENT_OPPORTUNITY, report)
        writer = FakeWriter(generated([expand()]))
        result = await ChangePlanWorkflow(writer).run(self.site, report)
        self.assertEqual(result.status, planning.ChangePlanStatus.SUCCESS)
        material = json.loads(writer.prompts[0].material_json())
        self.assertEqual([r["opportunity_ref"] for r in material["opportunities"]], ["R1"])
        self.assertEqual(material["unavailable_opportunities"], [{"opportunity_ref": "R2", "reason": "COMPARISON_UNAVAILABLE"}])
        self.assertEqual(encode_artifact(ArtifactType.CONTENT_OPPORTUNITY, report), before)
        self.assertEqual([c.operation_type for c in result.operations], [planning.ChangeOperationType.EXPAND_SECTION])
        self.assertTrue(result.requires_human_review)

    async def test_only_comparison_input_fails_before_writer(self):
        report = opportunity_report(opportunity(action_codes=(Action.ADD_COMPARISON_TABLE,)))
        writer = FakeWriter(generated([]))
        result = await ChangePlanWorkflow(writer).run(self.site, report)
        self.assertEqual(result.status, planning.ChangePlanStatus.INVALID_INPUT)
        self.assertEqual(result.error, "COMPARISON_UNAVAILABLE")
        self.assertEqual(writer.prompts, [])

    async def test_direct_planning_adapter_preserves_comparison_refusal_before_http(self):
        report = opportunity_report(opportunity(action_codes=(Action.ADD_COMPARISON_TABLE,)))
        requests = []

        def handler(request):
            requests.append(request)
            raise AssertionError("Unavailable comparison must not reach HTTP")

        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "unit-test-key"}):
            result = await DeepSeekChangePlanWriter(
                transport=httpx.MockTransport(handler)
            ).write_change_plan(self.prompt(report))

        self.assertEqual(result.status, planning.ChangePlanGenerationStatus.FAILED)
        self.assertEqual(result.error, "COMPARISON_UNAVAILABLE")
        self.assertEqual(requests, [])

    async def test_supporting_resource_stays_available_when_separately_authorized(self):
        report = opportunity_report(opportunity(action_codes=(Action.CREATE_SUPPORTING_RESOURCE, Action.ADD_COMPARISON_TABLE)))
        writer = FakeWriter(generated([{**resource_raw(), "comparison_table_brief": None}]))
        result = await ChangePlanWorkflow(writer).run(self.site, report)
        self.assertEqual(result.status, planning.ChangePlanStatus.SUCCESS)
        self.assertEqual(self.prompt(report).allowed_operation_types_for("R1"), (planning.ChangeOperationType.CREATE_NEW_RESOURCE,))
        self.assertIsNone(result.operations[0].new_resource_spec.comparison_table_spec)

    def test_deferral_and_allowlist_cannot_be_forged_in_rendered_material(self):
        report = opportunity_report(opportunity(action_codes=(Action.EXPAND_PAGE_SECTION,)),
            opportunity(recommendation_id="R2", action_codes=(Action.ADD_COMPARISON_TABLE,)))
        prompt = self.prompt(report)
        material = json.loads(prompt.material_json())
        self.assertIsNone(planning.validate_provider_generation_material(prompt, json.dumps(material)))
        material["unavailable_opportunities"] = []
        self.assertEqual(planning.validate_provider_generation_material(prompt, json.dumps(material)), "FIELD_CONTRACT")
        material = json.loads(prompt.material_json())
        material["opportunities"][0]["allowed_operation_types"].append("ADD_COMPARISON_TABLE")
        self.assertEqual(planning.validate_provider_generation_material(prompt, json.dumps(material)), "FIELD_CONTRACT")

    async def test_comparison_failure_persists_using_existing_v4_category(self):
        result = await ChangePlanWorkflow(FakeWriter(generated([expand(), comparison_raw()]))).run(self.site, self.report)
        now = datetime(2026, 10, 8, tzinfo=UTC)
        run_id = "11111111-1111-4111-8111-111111111111"
        artifact_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        with TemporaryDirectory() as folder:
            store = SQLiteHistoryStore(Path(folder) / "history.sqlite3")
            store.create_run(WorkflowRun(run_id, "https://example.com:443", "plan", now,
                None, RunStatus.RUNNING, None, None))
            store.append_artifact(ArtifactRecord(artifact_id, run_id, ArtifactType.CHANGE_PLAN, 1, now, result))
            store.finish_run(run_id, status=RunStatus.FAILED, completed_at=now + timedelta(seconds=1),
                failure_kind="change_plan_invalid_output", sanitized_error=result.error,
                final_validation_category=result.final_validation_category,
                writer_attempt_count=result.writer_attempt_count)
            self.assertEqual(store.get_run(run_id).final_validation_category.value, "OPERATION_NOT_ALLOWED")
            self.assertEqual(store.get_artifact(artifact_id).payload.error, "COMPARISON_UNAVAILABLE")

    async def test_legacy_c2_rejects_all_drafting_without_mutating_plan(self):
        ordinary = await self.ordinary_plan()
        # Exact attribute-by-attribute shape of invalid historical C2, synthetic evidence.
        table = legacy_table_operation(change_id="C2", columns=("Working Table Size", "X / Y / Z Travel", "Spindle Speed", "Spindle Taper", "Positioning Accuracy"), rows=("Machine Weight",))
        plan = legacy_plan(ordinary.operations[0], table)
        before = encode_artifact(ArtifactType.CHANGE_PLAN, plan)
        restored = decode_artifact(ArtifactType.CHANGE_PLAN, 1, before)
        writer = _DraftFakeWriter([_generation(_section_text())])
        result = await ContentDraftWorkflow(writer).run(drafting.ContentDraftInput(self.site, self.report, restored))
        self.assertEqual(result.status, drafting.ContentDraftStatus.INVALID_INPUT)
        self.assertEqual(result.error, "COMPARISON_UNAVAILABLE")
        self.assertEqual(result.drafts, ())
        self.assertEqual(writer.calls, 0)
        self.assertEqual(encode_artifact(ArtifactType.CHANGE_PLAN, restored), before)
        self.assertEqual([c.change_id for c in restored.operations], ["C1", "C2"])

    async def test_new_ordinary_plan_executes_with_comparison_action_still_upstream(self):
        plan = await self.ordinary_plan()
        plan = decode_artifact(ArtifactType.CHANGE_PLAN, 1, encode_artifact(ArtifactType.CHANGE_PLAN, plan))
        writer = _DraftFakeWriter([_generation(_section_text())])
        result = await ContentDraftWorkflow(writer).run(drafting.ContentDraftInput(self.site, self.report, plan))
        self.assertEqual(result.status, drafting.ContentDraftStatus.SUCCESS)
        self.assertEqual(len(result.drafts), 1)
        self.assertEqual(result.drafts[0].change_ref, "C1")
        self.assertEqual(writer.calls, 1)
        self.assertTrue(result.requires_human_review)
        self.assertTrue(result.drafts[0].requires_human_review)

    async def test_prompt_cannot_draft_ordinary_c1_from_ineligible_whole_plan(self):
        ordinary = await self.ordinary_plan()
        value = drafting.ContentDraftInput(self.site, self.report, legacy_plan(ordinary.operations[0], legacy_table_operation(change_id="C2")))
        with self.assertRaisesRegex(ValueError, "COMPARISON_UNAVAILABLE"):
            drafting.build_content_draft_prompt(value, "C1")

    async def test_direct_finalizer_cannot_execute_legacy_comparison(self):
        operation = legacy_table_operation()
        spec = drafting.ContentDraftSpecification("C1", drafting.ContentDraftType.COMPARISON_TABLE_DRAFT,
            cells=(drafting.TableCellSpecification("application", "material selection", "Buyer context"),
                   drafting.TableCellSpecification("application", "port size", "Selection context")))
        item, error = drafting.finalize_draft_item(1, spec, operation, self.report.opportunities[0], self.site, self.report)
        self.assertIsNone(item)
        self.assertEqual(error, "COMPARISON_UNAVAILABLE")

    async def test_direct_adapter_rechecks_forged_prompt_before_http(self):
        value = drafting.ContentDraftInput(self.site, self.report, await self.ordinary_plan())
        prompt = drafting.build_content_draft_prompt(value, "C1")
        # Simulate a deserialized/tampered prompt bypassing its constructor.
        object.__setattr__(prompt, "operation", legacy_table_operation())
        requests = []
        def handler(request):
            requests.append(request)
            return httpx.Response(200, json={"choices": [{"message": {"content": _section_text()}, "finish_reason": "stop"}]})
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "unit-test-key"}):
            result = await DeepSeekContentDraftWriter(transport=httpx.MockTransport(handler)).write_content_draft(prompt)
        self.assertEqual(result.status, drafting.ContentDraftGenerationStatus.FAILED)
        self.assertEqual(result.error, "COMPARISON_UNAVAILABLE")
        self.assertEqual(requests, [])

    async def test_legacy_nested_resource_reads_but_cannot_draft_sections(self):
        ordinary = (await self.ordinary_plan()).operations[0]
        table = planning.ComparisonTableSpec(("material selection", "port size"), ("application",))
        resource = planning.NewResourceSpec(planning.NewResourcePurpose.SUPPORTING_RESOURCE, "Guidance",
            ("Material Selection", "Application"), ordinary.content_points, ("P1",), table)
        nested = replace(ordinary, source_action_code=Action.CREATE_SUPPORTING_RESOURCE,
            operation_type=planning.ChangeOperationType.CREATE_NEW_RESOURCE,
            target_kind=planning.ChangeTargetKind.CREATE_NEW_PAGE,
            locator=planning.SectionLocator(planning.SectionLocatorKind.NEW_PAGE, None, None, None, None),
            proposed_heading="Guidance", comparison_table_spec=table, new_resource_spec=resource)
        plan = decode_artifact(ArtifactType.CHANGE_PLAN, 1, encode_artifact(ArtifactType.CHANGE_PLAN, legacy_plan(nested)))
        report = opportunity_report(opportunity(action_codes=(Action.CREATE_SUPPORTING_RESOURCE,)))
        writer = _DraftFakeWriter([])
        result = await ContentDraftWorkflow(writer).run(drafting.ContentDraftInput(self.site, report, plan))
        self.assertEqual(result.status, drafting.ContentDraftStatus.INVALID_INPUT)
        self.assertEqual(result.error, "COMPARISON_UNAVAILABLE")
        self.assertEqual(writer.calls, 0)

    def test_old_plan_missing_compat_fields_decodes_without_execution_upgrade(self):
        raw = json.loads(encode_artifact(ArtifactType.CHANGE_PLAN, legacy_plan(legacy_table_operation())))
        raw.pop("final_validation_category")
        raw.pop("writer_attempt_count")
        raw["operations"][0].pop("audit_refs")
        restored = decode_artifact(ArtifactType.CHANGE_PLAN, 1, json.dumps(raw))
        self.assertEqual(restored.operations[0], legacy_table_operation())
        self.assertEqual(drafting.stable_content_draft_input_error(drafting.ContentDraftInput(self.site, self.report, restored)), "COMPARISON_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
