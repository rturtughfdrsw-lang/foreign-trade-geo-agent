"""Offline planning capability; no review verdict or Draft admission is fabricated."""
import asyncio
import json
import unittest
from dataclasses import replace
from pathlib import Path
import hashlib
from unittest.mock import patch
import httpx

from foreign_trade_geo_agent.core import content_opportunity as co
from foreign_trade_geo_agent.core import change_plan as cp
from foreign_trade_geo_agent.core.content_draft import ContentDraftInput, stable_content_draft_input_error
from foreign_trade_geo_agent.workflows.content_opportunity import ContentOpportunityWorkflow
from foreign_trade_geo_agent.workflows.change_plan import ChangePlanWorkflow
from tests.test_change_plan_workflow import page, packet, opportunity_report
from foreign_trade_geo_agent.core.extraction import StructuredContentBlock, StructuredContentKind, PageExtractionStatus, PageExtractionFailureKind
from foreign_trade_geo_agent.core.first_party_planning import FirstPartyExcerpt, FirstPartyPlanningScope
from foreign_trade_geo_agent.core.history import ArtifactType
from foreign_trade_geo_agent.storage.serialization import decode_artifact, encode_artifact


QUOTE = "Packing requirements inform the delivery plan."


class OpportunityWriter:
    def __init__(self):
        self.calls = 0

    async def write_content_opportunities(self, prompt):
        self.calls += 1
        candidate = prompt.topic_candidates[0]
        return co.ContentOpportunityGeneration(
            "fake", "offline", co.ContentOpportunityGenerationStatus.SUCCESS,
            json.dumps({"opportunities": [{
                "opportunity_type": "EXPAND_OBSERVED_CONTENT", "priority": "LOW",
                "topic_ref": candidate.candidate_id, "enhancement_action_codes": [],
                "page_refs": ["P1"], "source_refs": [], "audit_refs": [],
            }]}), None,
        )


class PlanWriter:
    def __init__(self):
        self.calls = 0

    async def write_change_plan(self, prompt):
        self.calls += 1
        points = prompt.content_point_candidates_for("R1")
        locators = prompt.locator_candidates_for("R1")
        return cp.ChangePlanGeneration(
            "fake", "offline", cp.ChangePlanGenerationStatus.SUCCESS,
            json.dumps({"opportunity_operations": {"R1": {"primary_operation": {
                "source_action_code": "EXPAND_PAGE_SECTION", "operation_type": "EXPAND_SECTION",
                "page_refs": ["P1"], "source_refs": [],
                "locator_ref": next(x.candidate_id for x in locators if x.target_heading == "Delivery brief"),
                "content_points": [{"intent": "SUMMARIZE", "subject_ref": points[0].candidate_id}],
            }}}}), None,
        )


class FirstPartyPlanningTests(unittest.TestCase):
    def setUp(self):
        self.packet = packet(page(h1=("Delivery brief",), h2=(), body=QUOTE))
        self.scope = FirstPartyPlanningScope(
            "fixture-excerpt-task", self.packet, "P1", "Delivery brief",
            (FirstPartyExcerpt("body_text", 0, len(QUOTE), QUOTE),),
        )
        self.spec = co.ContentOpportunitySpecification(
            co.ContentOpportunityType.EXPAND_OBSERVED_CONTENT, co.ContentOpportunityPriority.LOW,
            "Delivery brief", (co.ContentOpportunityActionCode.EXPAND_PAGE_SECTION,), ("P1",), (), (),
        )
        self.catalog = co.build_content_opportunity_evidence_catalog(self.packet, ())

    def test_scope_requires_complete_observed_fields_and_unambiguous_section(self):
        for changed_page in (
            replace(self.packet.pages[0], body_text=None),
            replace(self.packet.pages[0], content_truncated=True),
            replace(self.packet.pages[0], h1=("Other section",)),
            replace(self.packet.pages[0], h2=("Another section",)),
            replace(self.packet.pages[0], extraction_status=PageExtractionStatus.FAILED,
                    extraction_failure_kind=PageExtractionFailureKind.EXTRACTION_FAILED),
        ):
            with self.subTest(page=changed_page), self.assertRaises(ValueError):
                replace(self.scope, site_content=packet(changed_page))
        with self.assertRaises(ValueError):
            replace(self.scope, excerpts=())
        with self.assertRaises(ValueError):
            replace(self.scope, task_kind="TECHNICAL_EXPLANATION")
        with self.assertRaises(ValueError):
            replace(self.scope, excerpts=(FirstPartyExcerpt("body_text", 1, len(QUOTE), QUOTE),))

    def test_structured_excerpt_can_use_complete_field_when_body_is_truncated(self):
        block = StructuredContentBlock(StructuredContentKind.SECTION, heading="Delivery brief", text=QUOTE)
        selected = packet(replace(self.packet.pages[0], content_truncated=True, structured_content=(block,)))
        excerpt = FirstPartyExcerpt("structured_text", 0, len(QUOTE), QUOTE, 0)
        scope = replace(self.scope, site_content=selected, excerpts=(excerpt,))
        self.assertTrue(scope.matches_packet(selected))
        with self.assertRaises(ValueError):
            replace(scope, site_content=packet(replace(selected.pages[0], structured_content_truncated=True)))
        with self.assertRaises(ValueError):
            replace(scope, excerpts=(replace(excerpt, structured_index=3),))
        with self.assertRaises(ValueError):
            replace(scope, site_content=packet(replace(selected.pages[0], structured_content=(replace(block, heading="Other section"),))))

    def test_decorative_known_s_is_not_an_escape_hatch(self):
        source = co.ContentOpportunitySourceMaterial("S1", "Delivery brief", "Unrelated market statistics.", False)
        catalog = co.build_content_opportunity_evidence_catalog(self.packet, (source,))
        self.assertIsNotNone(co.validate_content_opportunity_specification(
            replace(self.spec, source_refs=("S1",)), catalog, (source,),
            first_party_scope=self.scope, task_id=self.scope.task_id,
        ))
        # Provider cannot insert context/approval into the response schema.
        prompt = co.ContentOpportunityPrompt(self.packet, self.catalog, (), False,
                                            first_party_scope=self.scope, task_id=self.scope.task_id)
        generation = asyncio.run(OpportunityWriter().write_content_opportunities(prompt))
        raw = json.loads(generation.text)
        raw["opportunities"][0]["first_party_scope"] = {"approved": True}
        result, error = ContentOpportunityWorkflow(OpportunityWriter())._validate_and_render(json.dumps(raw), prompt)
        self.assertIsNone(result)
        self.assertIsNotNone(error)
        for count in (0, 2):
            raw = json.loads(generation.text)
            raw["opportunities"] = raw["opportunities"] * count
            result, error = ContentOpportunityWorkflow(OpportunityWriter())._validate_and_render(json.dumps(raw), prompt)
            self.assertIsNone(result)
            self.assertIsNotNone(error)

    def test_historical_artifacts_roundtrip_without_reinterpretation(self):
        root = Path(__file__).resolve().parents[1]
        bundle = root / "docs/review-packages/evidence-sufficiency-2026-10-08-v2"
        binding = json.loads((bundle / "binding.json").read_text(encoding="utf-8"))
        for name, kind in (
            ("site_content", ArtifactType.SITE_CONTENT), ("site_audit", ArtifactType.SITE_AUDIT),
            ("industry_research", ArtifactType.INDUSTRY_RESEARCH),
            ("content_opportunity", ArtifactType.CONTENT_OPPORTUNITY), ("change_plan", ArtifactType.CHANGE_PLAN),
        ):
            raw = (bundle / "snapshots" / (name + ".json")).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), binding["snapshot_files_sha256"]["snapshots/" + name + ".json"])
            decoded = decode_artifact(kind, 1, raw.decode("utf-8"))
            self.assertEqual(json.loads(encode_artifact(kind, decoded)), json.loads(raw))
            if name == "change_plan":
                self.assertTrue(any(cp.comparison_operation_error(op) == "COMPARISON_UNAVAILABLE" for op in decoded.operations))
        # V1 persists no implicit privilege; a new report also loses planning
        # eligibility when reloaded without an explicitly matching context.
        decoded = decode_artifact(ArtifactType.CONTENT_OPPORTUNITY, 1, encode_artifact(ArtifactType.CONTENT_OPPORTUNITY, self.report()))
        self.assertIsNotNone(cp.validate_change_plan_input(cp.ChangePlanInput(self.packet, decoded)))

    def test_original_review_package_unchanged_and_supplement_does_not_approve_it(self):
        root = Path(__file__).resolve().parents[1]
        bundle = root / "docs/review-packages/evidence-sufficiency-2026-10-08-v2"
        manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
        for name, digest in manifest["package_files_sha256"].items():
            self.assertEqual(hashlib.sha256((root / name).read_bytes()).hexdigest(), digest, name)
        template = json.loads((bundle / "review-record.template.json").read_text(encoding="utf-8"))
        self.assertTrue(all(d["decision"] == "NOT_REVIEWED" for d in template["owner_decisions"]))
        statement = json.loads((root / "docs/review-packages/evidence-sufficiency-2026-10-08-p-only/owner-authorization-statement.json").read_text(encoding="utf-8"))
        self.assertFalse(statement["runtime_approval_valid"])
        self.assertFalse(statement["source"]["identity_or_signature_verified"])
        self.assertEqual(statement["overall_verdict"], "NOT_REVIEWED")
        self.assertTrue(all(d["status"] == "NOT_REVIEWED" for d in statement["owner_decisions"][2:]))
        self.assertTrue(all(o["verdict"] == "NOT_REVIEWED" for o in statement["obligation_verdicts"]))

    def test_multiple_required_excerpts_cannot_be_pruned_or_omitted(self):
        second = "Shipment terms inform the delivery plan."
        body = QUOTE + " " + second
        selected = packet(replace(self.packet.pages[0], body_text=body))
        scope = replace(self.scope, site_content=selected, excerpts=(
            self.scope.excerpts[0], FirstPartyExcerpt("body_text", len(QUOTE) + 1, len(body), second),
        ))
        report = self.report()
        prompt = cp.build_change_plan_prompt(cp.ChangePlanInput(selected, report, scope, scope.task_id))
        trimmed = replace(prompt, content_point_candidate_sets=(replace(prompt.content_point_candidate_sets[0], candidates=prompt.content_point_candidate_sets[0].candidates[:1]),))
        self.assertEqual(trimmed.allowed_operation_types_for("R1"), ())
        self.assertIsNotNone(cp.validate_provider_generation_material(trimmed, trimmed.material_json()))
        operation, error = cp.validate_and_finalize_specification(1, self.plan_spec(), prompt.catalog, first_party_scope=scope, task_id=scope.task_id)
        self.assertIsNone(operation)
        self.assertIsNotNone(error)

    def error(self, spec=None, **kwargs):
        return co.validate_content_opportunity_specification(
            spec or self.spec, self.catalog, (), first_party_scope=self.scope,
            task_id=kwargs.pop("task_id", self.scope.task_id), **kwargs,
        )

    def test_default_still_requires_source_and_explicit_scope_allows_excerpt(self):
        self.assertEqual(co.validate_content_opportunity_specification(self.spec, self.catalog, ()), "SOURCE_REFERENCE_REQUIRED")
        self.assertIsNone(self.error())

    def test_no_evidence_illegal_refs_and_other_actions_fail_closed(self):
        for spec in (
            replace(self.spec, page_refs=()), replace(self.spec, page_refs=("P9",)),
            replace(self.spec, page_refs=("S1",)), replace(self.spec, source_refs=("P1",)),
            replace(self.spec, source_refs=("S9",)), replace(self.spec, audit_refs=("A9",)),
            replace(self.spec, action_codes=(co.ContentOpportunityActionCode.EXPAND_PAGE_SECTION, co.ContentOpportunityActionCode.ADD_COMPARISON_TABLE)),
            replace(self.spec, topic="Unobserved topic"),
        ):
            with self.subTest(spec=spec):
                self.assertIsNotNone(self.error(spec))

    def test_task_and_packet_binding_are_required(self):
        self.assertIsNotNone(self.error(task_id="other-task"))
        self.assertIsNotNone(self.error(task_id=None))
        with self.assertRaises(ValueError):
            replace(self.scope, site_content=packet(page(h1=("Delivery brief",), body="Delivery topic only.")))
        self.assertFalse(self.scope.matches_packet(replace(self.packet, truncated=True)))

    def test_topic_only_cannot_supply_required_explanation(self):
        with self.assertRaises(ValueError):
            replace(self.scope, excerpts=(replace(self.scope.excerpts[0], quote="Packing is guaranteed safe."),))
        # The scope has no sufficient/approved status; its literal excerpts do
        # not approve arbitrary EXPLAIN work, even with a valid topic.
        report = self.report()
        prompt = cp.build_change_plan_prompt(cp.ChangePlanInput(self.packet, report, self.scope, self.scope.task_id))
        spec = self.plan_spec(intent=cp.ContentPointIntent.EXPLAIN)
        operation, error = cp.validate_and_finalize_specification(1, spec, prompt.catalog, first_party_scope=self.scope, task_id=self.scope.task_id)
        self.assertIsNone(operation)
        self.assertIsNotNone(error)

    def report(self):
        self.assertIsNone(self.error())
        item = co.finalize_content_opportunity(1, self.spec)
        return co.ContentOpportunityReport(
            co.ContentOpportunityStatus.SUCCESS, (item,),
            tuple(co.ContentOpportunityPage(p.evidence_id, p.final_url, p.title) for p in self.packet.pages),
            (), co.CONTENT_OPPORTUNITY_LIMITATIONS, None,
        )

    def plan_spec(self, intent=cp.ContentPointIntent.SUMMARIZE):
        return cp.ExpandSectionSpecification(
            "R1", co.ContentOpportunityActionCode.EXPAND_PAGE_SECTION, cp.ChangeOperationType.EXPAND_SECTION,
            ("P1",), (), cp.SectionLocatorSpecification(cp.SectionLocatorKind.EXACT_OBSERVED_HEADING, "P1", "Delivery brief"),
            (cp.ContentPointSpecification(intent, QUOTE, "P1"),),
        )

    def test_native_availability_finalizer_and_stable_validation(self):
        report = self.report()
        value = cp.ChangePlanInput(self.packet, report, self.scope, self.scope.task_id)
        self.assertIsNone(cp.validate_change_plan_input(value))
        self.assertIsNotNone(cp.validate_change_plan_input(cp.ChangePlanInput(self.packet, report)))
        prompt = cp.build_change_plan_prompt(value)
        self.assertEqual(prompt.allowed_operation_types_for("R1"), (cp.ChangeOperationType.EXPAND_SECTION,))
        self.assertIsNone(cp.validate_provider_generation_material(prompt, prompt.material_json()))
        operation, error = cp.validate_and_finalize_specification(1, self.plan_spec(), prompt.catalog, first_party_scope=self.scope, task_id=self.scope.task_id)
        self.assertIsNone(error)
        self.assertIsNotNone(operation)
        self.assertTrue(report.requires_human_review)
        self.assertNotIn("external research context ,", report.opportunities[0].rationale)
        plan = cp.ChangePlanReport(cp.ChangePlanStatus.SUCCESS, (operation,), cp.CHANGE_PLAN_LIMITATIONS, None)
        self.assertIsNotNone(stable_content_draft_input_error(ContentDraftInput(self.packet, report, plan)))

    def test_wrong_point_origin_locator_task_and_quote_are_rejected(self):
        prompt = cp.build_change_plan_prompt(cp.ChangePlanInput(self.packet, self.report(), self.scope, self.scope.task_id))
        for spec in (
            replace(self.plan_spec(), opportunity_ref="R2"),
            replace(self.plan_spec(), content_points=(cp.ContentPointSpecification(cp.ContentPointIntent.SUMMARIZE, QUOTE, "P2"),)),
            replace(self.plan_spec(), content_points=(cp.ContentPointSpecification(cp.ContentPointIntent.SUMMARIZE, "Delivery brief", "P1"),)),
            replace(self.plan_spec(), locator=cp.SectionLocatorSpecification(cp.SectionLocatorKind.PAGE_LEVEL, "P1", None)),
        ):
            operation, error = cp.validate_and_finalize_specification(1, spec, prompt.catalog, first_party_scope=self.scope, task_id=self.scope.task_id)
            self.assertIsNone(operation)
            self.assertIsNotNone(error)
        operation, error = cp.validate_and_finalize_specification(1, self.plan_spec(), prompt.catalog, first_party_scope=self.scope, task_id="other-task")
        self.assertIsNone(operation)
        self.assertIsNotNone(error)

    def test_mixed_path_and_comparison_refusal_unchanged(self):
        original = opportunity_report()
        self.assertIsNone(cp.validate_change_plan_input(cp.ChangePlanInput(packet(), original)))
        prompt = cp.build_change_plan_prompt(cp.ChangePlanInput(self.packet, self.report(), self.scope, self.scope.task_id))
        spec = replace(self.plan_spec(), content_points=(cp.ContentPointSpecification(cp.ContentPointIntent.COMPARE, QUOTE, "P1"),))
        operation, error = cp.validate_and_finalize_specification(1, spec, prompt.catalog, first_party_scope=self.scope, task_id=self.scope.task_id)
        self.assertIsNone(operation)
        self.assertEqual(error, "COMPARISON_UNAVAILABLE")

    def test_workflows_without_research_or_paid_models_and_wrong_binding_writer_zero(self):
        writer = OpportunityWriter()
        report = asyncio.run(ContentOpportunityWorkflow(writer).run(self.packet, None, first_party_scope=self.scope, task_id=self.scope.task_id))
        self.assertEqual(report.status, co.ContentOpportunityStatus.SUCCESS)
        planner = PlanWriter()
        plan = asyncio.run(ChangePlanWorkflow(planner).run(self.packet, report, first_party_scope=self.scope, task_id=self.scope.task_id))
        self.assertEqual(plan.status, cp.ChangePlanStatus.SUCCESS)
        self.assertEqual(len(plan.operations), 1)
        self.assertEqual((writer.calls, planner.calls), (1, 1))
        bad_writer = OpportunityWriter()
        bad = asyncio.run(ContentOpportunityWorkflow(bad_writer).run(self.packet, None, first_party_scope=self.scope, task_id="wrong"))
        self.assertNotEqual(bad.status, co.ContentOpportunityStatus.SUCCESS)
        self.assertEqual(bad_writer.calls, 0)
        bad_planner = PlanWriter()
        bad = asyncio.run(ChangePlanWorkflow(bad_planner).run(self.packet, report, first_party_scope=self.scope, task_id="wrong"))
        self.assertEqual(bad.status, cp.ChangePlanStatus.INVALID_INPUT)
        self.assertEqual(bad_planner.calls, 0)

    def test_adapters_send_conditional_contract_only_through_mock_transport(self):
        from foreign_trade_geo_agent.adapters.deepseek_content_opportunity import DeepSeekContentOpportunityWriter
        from foreign_trade_geo_agent.adapters.deepseek_change_plan import DeepSeekChangePlanWriter
        opportunity_prompt = co.ContentOpportunityPrompt(
            self.packet, self.catalog, (), False, first_party_scope=self.scope, task_id=self.scope.task_id,
        )
        plan_prompt = cp.build_change_plan_prompt(cp.ChangePlanInput(self.packet, self.report(), self.scope, self.scope.task_id))
        for writer_type, prompt, method, fragment in (
            (DeepSeekContentOpportunityWriter, opportunity_prompt, "write_content_opportunities", "cite that origin in page_refs"),
            (DeepSeekChangePlanWriter, plan_prompt, "write_change_plan", "EXPLAIN and COMPARE are unavailable"),
        ):
            captured = []
            def handler(request):
                captured.append(json.loads(request.content))
                return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}]})
            with self.subTest(writer=writer_type.__name__), patch.dict("os.environ", {"DEEPSEEK_API_KEY": "offline-placeholder"}):
                writer = writer_type(transport=httpx.MockTransport(handler))
                asyncio.run(getattr(writer, method)(prompt))
                self.assertEqual(len(captured), 1)
                system = captured[0]["messages"][0]["content"]
                self.assertIn("PLANNING_ONLY", system)
                self.assertIn(fragment, system)
                material = json.loads(captured[0]["messages"][1]["content"])
                self.assertFalse(material["contract"]["first_party_planning"]["draft_admission"])
