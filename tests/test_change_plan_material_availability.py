"""Final provider material must describe executable transient contracts."""

import json
import os
import unittest
from dataclasses import replace
from unittest.mock import patch

import httpx

from foreign_trade_geo_agent.core import change_plan as contract
from foreign_trade_geo_agent.adapters.deepseek_change_plan import DeepSeekChangePlanWriter
from foreign_trade_geo_agent.core.content_opportunity import ContentOpportunityActionCode as Action
from foreign_trade_geo_agent.workflows.change_plan import ChangePlanWorkflow
from tests.test_change_plan_workflow import FakeWriter, opportunity, opportunity_report, packet, page


def make_prompt(*actions, page_refs=("P1",)):
    return contract.build_change_plan_prompt(contract.ChangePlanInput(
        packet(), opportunity_report(opportunity(action_codes=actions, page_refs=page_refs))
    ))


def without(prompt, field):
    return replace(prompt, **{field: tuple(replace(item, candidates=()) for item in getattr(prompt, field))})


class FinalMaterialAvailabilityTests(unittest.TestCase):
    def test_post_budget_zero_content_removes_every_content_operation(self):
        for action, operation in (
            (Action.EXPAND_PAGE_SECTION, contract.ChangeOperationType.EXPAND_SECTION),
            (Action.ADD_BUYER_GUIDANCE, contract.ChangeOperationType.ADD_SECTION),
            (Action.CREATE_SUPPORTING_RESOURCE, contract.ChangeOperationType.CREATE_NEW_RESOURCE),
        ):
            with self.subTest(action=action):
                before = make_prompt(action)
                self.assertTrue(before.content_point_candidates_for("R1"))
                self.assertIn(operation, before.allowed_operation_types_for("R1"))
                after = without(before, "content_point_candidate_sets")
                self.assertNotIn(operation, after.allowed_operation_types_for("R1"))
                self.assertNotIn(operation.value, json.loads(after.material_json())["opportunities"][0]["allowed_operation_types"])

    def test_operations_without_content_points_remain_available(self):
        for action, operation, refs in (
            (Action.REORGANIZE_PAGE_SECTIONS, contract.ChangeOperationType.PROPOSE_SECTION_REORDER, ("P1",)),
            (Action.ADD_INTERNAL_LINK, contract.ChangeOperationType.ADD_INTERNAL_LINK, ("P1", "P2")),
        ):
            with self.subTest(action=action):
                value = without(make_prompt(action, page_refs=refs), "content_point_candidate_sets")
                self.assertIn(operation, value.allowed_operation_types_for("R1"))

    def test_one_content_candidate_preserves_content_operations(self):
        for action in (Action.EXPAND_PAGE_SECTION, Action.ADD_BUYER_GUIDANCE, Action.CREATE_SUPPORTING_RESOURCE):
            with self.subTest(action=action):
                value = make_prompt(action)
                reduced = replace(value, content_point_candidate_sets=tuple(
                    replace(item, candidates=item.candidates[:1]) for item in value.content_point_candidate_sets
                ))
                self.assertEqual(value.allowed_operation_types_for("R1"), reduced.allowed_operation_types_for("R1"))

    def test_add_section_requires_heading_content_and_matching_locator(self):
        value = make_prompt(Action.ADD_BUYER_GUIDANCE)
        for field in ("content_point_candidate_sets", "proposed_heading_candidate_sets", "locator_candidate_sets"):
            with self.subTest(field=field):
                self.assertNotIn(contract.ChangeOperationType.ADD_SECTION, without(value, field).allowed_operation_types_for("R1"))
        mismatched = replace(value, locator_candidate_sets=(replace(value.locator_candidate_sets[0], candidates=(
            contract.LocatorCandidate("P2.LOC_00", contract.SectionLocatorKind.PAGE_LEVEL, "P2", None),
        )),))
        self.assertNotIn(contract.ChangeOperationType.ADD_SECTION, mismatched.allowed_operation_types_for("R1"))

    def test_new_resource_requires_outline_content_and_visible_sources(self):
        value = make_prompt(Action.CREATE_SUPPORTING_RESOURCE)
        for field in ("content_point_candidate_sets", "outline_heading_candidate_sets"):
            self.assertNotIn(contract.ChangeOperationType.CREATE_NEW_RESOURCE, without(value, field).allowed_operation_types_for("R1"))
        single_outline = replace(value, outline_heading_candidate_sets=(replace(
            value.outline_heading_candidate_sets[0], candidates=value.outline_heading_candidates_for("R1")[:1]
        ),))
        self.assertNotIn(contract.ChangeOperationType.CREATE_NEW_RESOURCE, single_outline.allowed_operation_types_for("R1"))
        no_sources = replace(value, catalog=replace(value.catalog, sources=()))
        self.assertNotIn(contract.ChangeOperationType.CREATE_NEW_RESOURCE, no_sources.allowed_operation_types_for("R1"))

    def test_locator_dependent_operations_require_final_locator(self):
        for action in (Action.EXPAND_PAGE_SECTION, Action.ADD_BUYER_GUIDANCE, Action.ADD_COMPARISON_TABLE):
            with self.subTest(action=action):
                value = without(make_prompt(action), "locator_candidate_sets")
                self.assertFalse(set(value.allowed_operation_types_for("R1")) & {
                    contract.ChangeOperationType.EXPAND_SECTION, contract.ChangeOperationType.ADD_SECTION,
                    contract.ChangeOperationType.ADD_COMPARISON_TABLE,
                })

    def test_reorder_requires_two_visible_bounded_headings_on_one_page(self):
        report = opportunity_report(opportunity(action_codes=(Action.REORGANIZE_PAGE_SECTIONS,)))
        value = contract.build_change_plan_prompt(contract.ChangePlanInput(packet(page(h1=(), h2=("One",))), report))
        self.assertEqual(value.allowed_operation_types_for("R1"), ())

    def test_internal_link_requires_distinct_pages_on_same_origin(self):
        self.assertEqual(make_prompt(Action.ADD_INTERNAL_LINK).allowed_operation_types_for("R1"), ())
        value = make_prompt(Action.ADD_INTERNAL_LINK, page_refs=("P1", "P2"))
        foreign_page = replace(value.catalog.pages[1], page=replace(value.catalog.pages[1].page, final_url="https://other.example/p2"))
        changed = replace(value, catalog=replace(value.catalog, pages=(value.catalog.pages[0], foreign_page)))
        self.assertEqual(changed.allowed_operation_types_for("R1"), ())

    def test_budget_preserves_minimum_before_discarding_extra_headings(self):
        value = make_prompt(Action.ADD_BUYER_GUIDANCE)
        minimum = replace(value,
            content_point_candidate_sets=tuple(replace(item, candidates=item.candidates[:1]) for item in value.content_point_candidate_sets),
            locator_candidate_sets=tuple(replace(item, candidates=tuple(c for c in item.candidates if c.locator_kind is contract.SectionLocatorKind.PAGE_LEVEL)) for item in value.locator_candidate_sets),
            proposed_heading_candidate_sets=tuple(replace(item, candidates=item.candidates[:1]) for item in value.proposed_heading_candidate_sets),
        )
        ceiling = len(minimum.material_json()) + contract.CONTENT_POINT_CANDIDATE_REPAIR_RESERVE_CHARS
        with patch.object(contract, "MAX_USER_MATERIAL_CHARS", ceiling):
            trimmed = contract.build_change_plan_prompt(value.input)
        self.assertLessEqual(len(trimmed.material_json()), ceiling - contract.CONTENT_POINT_CANDIDATE_REPAIR_RESERVE_CHARS)
        self.assertEqual(len(trimmed.content_point_candidates_for("R1")), 1)
        self.assertIn(contract.ChangeOperationType.ADD_SECTION, trimmed.allowed_operation_types_for("R1"))

    def test_real_trimmer_zero_content_updates_material_and_parser_catalog(self):
        value = make_prompt(Action.EXPAND_PAGE_SECTION)
        empty = without(value, "content_point_candidate_sets")
        empty = without(empty, "proposed_heading_candidate_sets")
        empty = replace(empty, locator_candidate_sets=tuple(replace(item, candidates=tuple(
            c for c in item.candidates if c.locator_kind is contract.SectionLocatorKind.PAGE_LEVEL
        )) for item in empty.locator_candidate_sets))
        # Force removal of every subject without altering source evidence.
        ceiling = len(empty.material_json()) + contract.CONTENT_POINT_CANDIDATE_REPAIR_RESERVE_CHARS
        with patch.object(contract, "MAX_USER_MATERIAL_CHARS", ceiling):
            trimmed = contract.build_change_plan_prompt(value.input)
        self.assertEqual(trimmed.content_point_candidates_for("R1"), ())
        self.assertEqual(trimmed.allowed_operation_types_for("R1"), ())
        for candidate in value.content_point_candidates_for("R1"):
            self.assertIsNone(trimmed.content_point_candidate("R1", candidate.candidate_id))

    def test_material_ceiling_and_determinism(self):
        first = make_prompt(Action.ADD_BUYER_GUIDANCE)
        second = make_prompt(Action.ADD_BUYER_GUIDANCE)
        self.assertEqual(first.material_json(), second.material_json())
        self.assertEqual(first.allowed_operation_types_for("R1"), second.allowed_operation_types_for("R1"))
        self.assertEqual(contract.MAX_USER_MATERIAL_CHARS, 26_000)
        self.assertEqual(contract.MAX_USER_MATERIAL_BYTES, 56 * 1024)

    def test_consistency_checks_the_rendered_catalog_not_only_prompt_object(self):
        value = make_prompt(Action.ADD_BUYER_GUIDANCE)
        material = json.loads(value.material_json())
        material["opportunities"][0]["content_point_candidates"] = []
        self.assertIsNotNone(contract.validate_provider_generation_material(value, json.dumps(material)))
        self.assertIsNone(contract.validate_provider_generation_material(value, value.material_json()))

    def test_final_allowed_list_cannot_be_forged(self):
        value = without(make_prompt(Action.REORGANIZE_PAGE_SECTIONS), "content_point_candidate_sets")
        material = json.loads(value.material_json())
        material["opportunities"][0]["allowed_operation_types"].append("CREATE_NEW_RESOURCE")
        self.assertIsNotNone(contract.validate_provider_generation_material(value, json.dumps(material)))

    def test_budget_bytes_preserve_minimum_and_reserved_repair_space(self):
        value = make_prompt(Action.ADD_BUYER_GUIDANCE)
        minimum = replace(value,
            content_point_candidate_sets=tuple(replace(item, candidates=item.candidates[:1]) for item in value.content_point_candidate_sets),
            locator_candidate_sets=tuple(replace(item, candidates=tuple(c for c in item.candidates if c.locator_kind is contract.SectionLocatorKind.PAGE_LEVEL)) for item in value.locator_candidate_sets),
            proposed_heading_candidate_sets=tuple(replace(item, candidates=item.candidates[:1]) for item in value.proposed_heading_candidate_sets),
        )
        ceiling = len(minimum.material_json().encode("utf-8")) + contract.CONTENT_POINT_CANDIDATE_REPAIR_RESERVE_BYTES
        with patch.object(contract, "MAX_USER_MATERIAL_BYTES", ceiling):
            trimmed = contract.build_change_plan_prompt(value.input)
        self.assertLessEqual(len(trimmed.material_json().encode("utf-8")), ceiling - contract.CONTENT_POINT_CANDIDATE_REPAIR_RESERVE_BYTES)
        self.assertIn(contract.ChangeOperationType.ADD_SECTION, trimmed.allowed_operation_types_for("R1"))

    def test_parser_rejects_subject_removed_from_final_catalog(self):
        value = make_prompt(Action.EXPAND_PAGE_SECTION)
        removed = value.content_point_candidates_for("R1")[-1]
        trimmed = replace(value, content_point_candidate_sets=(replace(
            value.content_point_candidate_sets[0], candidates=value.content_point_candidates_for("R1")[:1]
        ),))
        points, failure = ChangePlanWorkflow(FakeWriter(None))._parse_content_points(
            [{"intent": "EXPLAIN", "subject_ref": removed.candidate_id}],
            opportunity_ref="R1", field_path="R1.primary_operation.content_points",
            source_refs=("S1",), prompt=trimmed,
        )
        self.assertIsNone(points)
        self.assertEqual(failure.violation.rule_id, contract.FieldContractRule.SUBJECT_REF_INVALID)

    def test_stale_allowlist_cannot_bypass_authoritative_preflight(self):
        value = without(make_prompt(Action.EXPAND_PAGE_SECTION), "content_point_candidate_sets")
        with patch.object(contract.ChangePlanPrompt, "allowed_operation_types_for", return_value=(contract.ChangeOperationType.EXPAND_SECTION,)):
            self.assertEqual(contract.validate_provider_generation_material(value, value.material_json()), "FIELD_CONTRACT")


class MaterialPreflightTests(unittest.IsolatedAsyncioTestCase):
    async def test_wrong_material_fails_before_http(self):
        value = make_prompt(Action.EXPAND_PAGE_SECTION)
        material = json.loads(value.material_json())
        material["opportunities"][0]["content_point_candidates"] = []
        requests = []
        def handler(request):
            requests.append(request)
            return httpx.Response(200, json={})
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "unit-test-key"}), patch.object(contract.ChangePlanPrompt, "material_json", return_value=json.dumps(material)):
            result = await DeepSeekChangePlanWriter(transport=httpx.MockTransport(handler)).write_change_plan(value)
        self.assertEqual(requests, [])
        self.assertEqual(result.status, contract.ChangePlanGenerationStatus.FAILED)

    async def test_direct_adapter_empty_allowed_set_fails_before_http(self):
        value = without(make_prompt(Action.EXPAND_PAGE_SECTION), "content_point_candidate_sets")
        requests = []
        def handler(request):
            requests.append(request)
            return httpx.Response(200, json={})
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "unit-test-key"}):
            result = await DeepSeekChangePlanWriter(transport=httpx.MockTransport(handler)).write_change_plan(value)
        self.assertEqual(requests, [])
        self.assertEqual(result.status, contract.ChangePlanGenerationStatus.FAILED)

    async def test_workflow_rejects_wrong_rendered_material_before_writer(self):
        value = make_prompt(Action.EXPAND_PAGE_SECTION)
        material = json.loads(value.material_json())
        material["opportunities"][0]["locator_candidates"] = []
        writer = FakeWriter(None)
        with patch("foreign_trade_geo_agent.workflows.change_plan.build_change_plan_prompt", return_value=value), patch.object(contract.ChangePlanPrompt, "material_json", return_value=json.dumps(material)):
            result = await ChangePlanWorkflow(writer).run(value.input.site_content, value.input.opportunities)
        self.assertEqual(writer.prompts, [])
        self.assertEqual(result.status, contract.ChangePlanStatus.INVALID_INPUT)
        self.assertEqual(result.error, "FIELD_CONTRACT")

    async def test_empty_allowed_set_fails_before_writer(self):
        value = without(make_prompt(Action.EXPAND_PAGE_SECTION), "content_point_candidate_sets")
        writer = FakeWriter(contract.ChangePlanGeneration(
            "fake", "fake", contract.ChangePlanGenerationStatus.SUCCESS,
            '{"opportunity_operations":{}}', None,
        ))
        with patch("foreign_trade_geo_agent.workflows.change_plan.build_change_plan_prompt", return_value=value):
            result = await ChangePlanWorkflow(writer).run(value.input.site_content, value.input.opportunities)
        self.assertEqual(result.status, contract.ChangePlanStatus.INVALID_INPUT)
        self.assertEqual(result.error, "FIELD_CONTRACT")
        self.assertEqual(writer.prompts, [])
