"""Bounded literal planning capacity; full tasks, never partial successes."""
import asyncio
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import httpx

from foreign_trade_geo_agent.core import change_plan as cp, content_opportunity as co
from foreign_trade_geo_agent.core import content_draft as cd
from foreign_trade_geo_agent.core.extraction import StructuredContentBlock, StructuredContentKind
from foreign_trade_geo_agent.core.first_party_planning import FirstPartyExcerpt, FirstPartyPlanningScope
from foreign_trade_geo_agent.core.history import ArtifactType
from foreign_trade_geo_agent.storage.serialization import decode_artifact, encode_artifact
from foreign_trade_geo_agent.workflows.change_plan import ChangePlanWorkflow
from foreign_trade_geo_agent.workflows.content_opportunity import ContentOpportunityWorkflow
from tests.test_change_plan_workflow import packet, page


ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / "docs/review-packages/evidence-sufficiency-2026-10-08-excerpt-v1"


class LiteralOpportunityWriter:
    def __init__(self):
        self.calls = 0

    async def write_content_opportunities(self, prompt):
        self.calls += 1
        topic = prompt.topic_candidates[0]
        return co.ContentOpportunityGeneration(
            "fixture", "offline", co.ContentOpportunityGenerationStatus.SUCCESS,
            json.dumps({"opportunities": [{
                "opportunity_type": "EXPAND_OBSERVED_CONTENT", "priority": "LOW",
                "topic_ref": topic.candidate_id, "enhancement_action_codes": [],
                "page_refs": [topic.origin_ref], "source_refs": [], "audit_refs": [],
            }]}), None,
        )


class LiteralPlanWriter:
    def __init__(self, mutate=None):
        self.calls = 0
        self.mutate = mutate

    async def write_change_plan(self, prompt):
        self.calls += 1
        scope = prompt.input.first_party_scope
        locator = next(c for c in prompt.locator_candidates_for("R1")
                       if c.target_heading == scope.heading and c.page_ref == scope.page_ref)
        operation = {
            "source_action_code": "EXPAND_PAGE_SECTION", "operation_type": "EXPAND_SECTION",
            "page_refs": [scope.page_ref], "source_refs": [], "locator_ref": locator.candidate_id,
            "content_points": [{"intent": "DESCRIBE", "subject_ref": c.candidate_id}
                               for c in prompt.content_point_candidates_for("R1")],
        }
        raw = {"opportunity_operations": {"R1": {"primary_operation": operation}}}
        if self.mutate:
            self.mutate(raw)
        return cp.ChangePlanGeneration("fixture", "offline", cp.ChangePlanGenerationStatus.SUCCESS,
                                       json.dumps(raw), None)


def six_obligation_fixture():
    selected = decode_artifact(ArtifactType.SITE_CONTENT, 1,
                              (OLD / "snapshots/site_content.json").read_text(encoding="utf-8"))
    coverage = json.loads((OLD / "coverage.json").read_text(encoding="utf-8"))
    excerpts = []
    for obligation in coverage["obligations"]:
        span = obligation["artifact_span"]
        # Exact contiguous fragments, including the boundary character. No
        # strip/normalization/truncation; concatenation reproduces all of O1.
        cuts = (0, 64, len(span["quote"])) if len(span["quote"]) > 120 else (0, len(span["quote"]))
        for start, end in zip(cuts, cuts[1:]):
            excerpts.append(FirstPartyExcerpt("structured_text", span["start"] + start,
                                             span["start"] + end, span["quote"][start:end], 0))
    scope = FirstPartyPlanningScope("six-relations-excerpt-capacity-v2", selected, "P3",
                                   selected.pages[2].h1[0],
                                   tuple(excerpts))
    return selected, scope, coverage


def generic_fixture(count):
    quotes = tuple(f"Packing requirement {i:02d} informs the delivery plan." for i in range(count))
    body = " ".join(quotes)
    selected = packet(page(h1=("Delivery brief",), h2=(), body=body))
    excerpts, cursor = [], 0
    for quote in quotes:
        excerpts.append(FirstPartyExcerpt("body_text", cursor, cursor + len(quote), quote))
        cursor += len(quote) + 1
    return selected, FirstPartyPlanningScope("generic-excerpts", selected, "P1", "Delivery brief", tuple(excerpts))


def native_planning(selected, scope, mutate=None):
    writer, planner = LiteralOpportunityWriter(), LiteralPlanWriter(mutate)
    report = asyncio.run(ContentOpportunityWorkflow(writer).run(
        selected, None, first_party_scope=scope, task_id=scope.task_id))
    plan = asyncio.run(ChangePlanWorkflow(planner).run(
        selected, report, first_party_scope=scope, task_id=scope.task_id))
    return report, plan, writer, planner


class FirstPartyExcerptCapacityTests(unittest.TestCase):
    def test_six_complete_obligations_pass_native_planning_and_roundtrip(self):
        selected, scope, coverage = six_obligation_fixture()
        self.assertEqual(len(scope.excerpts), 7)
        report, plan, writer, planner = native_planning(selected, scope)
        self.assertEqual(report.status, co.ContentOpportunityStatus.SUCCESS)
        self.assertEqual(plan.status, cp.ChangePlanStatus.SUCCESS)
        self.assertEqual((writer.calls, planner.calls), (1, 1))
        self.assertEqual(len(plan.operations), 1)
        self.assertEqual(tuple(p.subject for p in plan.operations[0].content_points), scope.quotes)
        source = (OLD / "snapshots/solutions.astro").read_bytes().decode("utf-8")
        field = selected.pages[2].structured_content[0].text
        for obligation in coverage["obligations"]:
            span = obligation["artifact_span"]
            parts = [e for e in scope.excerpts if span["start"] <= e.start < e.end <= span["end"]]
            self.assertEqual(parts[0].start, span["start"])
            self.assertEqual(parts[-1].end, span["end"])
            self.assertTrue(all(a.end == b.start for a, b in zip(parts, parts[1:])))
            self.assertEqual("".join(e.quote for e in parts), span["quote"])
            self.assertEqual(field[span["start"]:span["end"]], span["quote"])
            corroborating = obligation["corroborating_source_span"]
            self.assertEqual(source[corroborating["start"]:corroborating["end"]], span["quote"])
            self.assertEqual(hashlib.sha256(field.encode()).hexdigest(), span["field_sha256"])
            self.assertEqual(obligation["human_support_verdict"], "NOT_REVIEWED")
        for kind, value in ((ArtifactType.CONTENT_OPPORTUNITY, report), (ArtifactType.CHANGE_PLAN, plan)):
            raw = encode_artifact(kind, value)
            self.assertEqual(encode_artifact(kind, decode_artifact(kind, 1, raw)), raw)
        # Capacity is not authority, including after V1 codec roundtrip.
        self.assertIsNotNone(cp.validate_change_plan_input(cp.ChangePlanInput(selected, report)))
        self.assertIsNotNone(cd.stable_content_draft_input_error(cd.ContentDraftInput(selected, report, plan)))
        with self.assertRaises(ValueError):
            cd.build_content_draft_prompt(cd.ContentDraftInput(selected, report, plan), "C1")

    def test_generic_ten_point_boundary_and_eleven_rejection(self):
        selected, scope = generic_fixture(10)
        report, plan, _, _ = native_planning(selected, scope)
        self.assertEqual(plan.status, cp.ChangePlanStatus.SUCCESS)
        self.assertEqual(len(plan.operations[0].content_points), 10)
        self.assertEqual(10, cp.MAX_OPERATIONS_PER_OPPORTUNITY * cp.MAX_CONTENT_POINTS_PER_OPERATION)
        with self.assertRaises(ValueError):
            generic_fixture(11)
        with self.assertRaises(ValueError):
            FirstPartyExcerpt("body_text", 0, 121, "x" * 121)
        with self.assertRaises(ValueError):
            cp.ContentPoint(cp.ContentPointIntent.DESCRIBE, "x" * 121)
        prompt = cp.build_change_plan_prompt(cp.ChangePlanInput(selected, report, scope, scope.task_id))
        self.assertEqual(json.loads(prompt.material_json())["contract"]["first_party_planning"]["max_content_points"], 10)
        # Native parser rejects output above the limit, rather than returning
        # the first ten valid items as a partial result.
        def append(raw):
            points = raw["opportunity_operations"]["R1"]["primary_operation"]["content_points"]
            points.append(dict(points[0]))
        bad = native_planning(selected, scope, append)[1]
        self.assertEqual(bad.status, cp.ChangePlanStatus.INVALID_OUTPUT)
        self.assertEqual(bad.operations, ())

    def test_maximum_fragment_character_budget_and_original_explain_negative(self):
        # A different site/language fills all 1,200 characters without raising
        # either the 120-character subject limit or the envelope budgets.
        quotes = tuple(f"{i:02d}" + "证" * 118 for i in range(10))
        body = " ".join(quotes)
        blocks = tuple(StructuredContentBlock(StructuredContentKind.SECTION, heading="Delivery brief",
                                             text=" ".join(quotes[i:i + 5])) for i in (0, 5))
        selected = packet(replace(page(h1=("Delivery brief",), h2=(), body="Observed delivery notes."),
                                  structured_content=blocks))
        scope = FirstPartyPlanningScope("full-char-budget", selected, "P1", "Delivery brief",
                                        tuple(FirstPartyExcerpt("structured_text", (i % 5) * 121,
                                                                (i % 5) * 121 + 120, q, i // 5)
                                              for i, q in enumerate(quotes)))
        report, plan, _, _ = native_planning(selected, scope)
        self.assertEqual(plan.status, cp.ChangePlanStatus.SUCCESS)
        self.assertEqual(sum(len(p.subject) for p in plan.operations[0].content_points), 1200)
        prompt = cp.build_change_plan_prompt(cp.ChangePlanInput(selected, report, scope, scope.task_id))
        self.assertIsNone(cp.validate_provider_generation_material(prompt, prompt.material_json()))
        self.assertLessEqual(len(prompt.material_json().encode()), cp.MAX_USER_MATERIAL_BYTES)
        specifications = tuple(cp.ContentPointSpecification(cp.ContentPointIntent.DESCRIBE, q, "P1") for q in quotes)
        self.assertEqual(cp._validate_content_points(specifications[:6], (body,)), "FIELD_CONTRACT")
        # The parser's default budget also stays 5 for other operation types.
        parsed, error = ChangePlanWorkflow(LiteralPlanWriter())._parse_content_points(
            [{"intent": "DESCRIBE", "subject_ref": p.candidate_id}
             for p in prompt.content_point_candidates_for("R1")[:6]],
            opportunity_ref="R1", field_path="R1.primary_operation.content_points",
            source_refs=(), prompt=prompt)
        self.assertIsNone(parsed)
        self.assertIsNotNone(error)
        selected, scope, _ = six_obligation_fixture()
        old = json.loads((ROOT / "docs/review-packages/evidence-sufficiency-2026-10-08-v2/planning-candidate.json").read_text(encoding="utf-8"))["specifications"]["opportunity"]
        spec = co.ContentOpportunitySpecification(
            co.ContentOpportunityType(old["opportunity_type"]), co.ContentOpportunityPriority(old["priority"]),
            old["topic"], tuple(co.ContentOpportunityActionCode(a) for a in old["action_codes"]),
            tuple(old["page_refs"]), (), ())
        self.assertEqual(co.validate_content_opportunity_specification(
            spec, co.build_content_opportunity_evidence_catalog(selected, ()), ()), "SOURCE_REFERENCE_REQUIRED")

    def test_missing_reordered_duplicate_false_refs_explain_and_compare_all_reject(self):
        selected, scope, _ = six_obligation_fixture()
        mutations = {
            "missing_first": lambda points: points.pop(0),
            "missing_last": lambda points: points.pop(),
            "reordered": lambda points: points.reverse(),
            "duplicate": lambda points: points.__setitem__(-1, dict(points[0])),
            "false_ref": lambda points: points[0].__setitem__("subject_ref", "P99.CP_01"),
            "explain": lambda points: points[0].__setitem__("intent", "EXPLAIN"),
            "compare": lambda points: points[0].__setitem__("intent", "COMPARE"),
        }
        for name, mutate_points in mutations.items():
            with self.subTest(case=name):
                def mutate(raw):
                    mutate_points(raw["opportunity_operations"]["R1"]["primary_operation"]["content_points"])
                bad = native_planning(selected, scope, mutate)[1]
                self.assertEqual(bad.status, cp.ChangePlanStatus.INVALID_OUTPUT)
                self.assertEqual(bad.operations, ())
                if name == "compare":
                    self.assertEqual(bad.error, "COMPARISON_UNAVAILABLE")

    def test_two_complete_operations_cannot_double_the_task_budget(self):
        selected, scope = generic_fixture(10)
        def mutate(raw):
            slots = raw["opportunity_operations"]["R1"]
            secondary = json.loads(json.dumps(slots["primary_operation"]))
            for point in secondary["content_points"]:
                point["intent"] = "SUMMARIZE"
            slots["secondary_operation"] = secondary
        bad = native_planning(selected, scope, mutate)[1]
        self.assertEqual(bad.status, cp.ChangePlanStatus.INVALID_OUTPUT)
        self.assertEqual(bad.operations, ())

    def test_no_evidence_wrong_packet_task_page_and_default_path_fail_closed(self):
        selected, scope, _ = six_obligation_fixture()
        with self.assertRaises(ValueError):
            replace(scope, excerpts=())
        with self.assertRaises(ValueError):
            replace(scope, excerpts=(replace(scope.excerpts[0], start=0), *scope.excerpts[1:]))
        with self.assertRaises(ValueError):
            replace(scope, page_ref="P1")
        report = native_planning(selected, scope)[0]
        for wrong_packet, task in ((selected, "other-task"), (replace(selected, truncated=not selected.truncated), scope.task_id)):
            writer, planner = LiteralOpportunityWriter(), LiteralPlanWriter()
            bad = asyncio.run(ContentOpportunityWorkflow(writer).run(
                wrong_packet, None, first_party_scope=scope, task_id=task))
            self.assertNotEqual(bad.status, co.ContentOpportunityStatus.SUCCESS)
            bad = asyncio.run(ChangePlanWorkflow(planner).run(
                wrong_packet, report, first_party_scope=scope, task_id=task))
            self.assertEqual(bad.status, cp.ChangePlanStatus.INVALID_INPUT)
            self.assertEqual((writer.calls, planner.calls), (0, 0))
        operation = native_planning(selected, scope)[1].operations[0]
        # Structural extension is constrained to one-page, exact-heading,
        # source-free literal expansions. Unrelated stored shapes stay at 5.
        for kwargs in ({"source_refs": ("S1",)}, {"audit_refs": ("A1",)},
                       {"page_refs": ("P1", "P3")},
                       {"content_points": tuple(replace(p, intent=cp.ContentPointIntent.EXPLAIN)
                                                for p in operation.content_points)}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                replace(operation, **kwargs)

    def test_expanded_mock_adapter_still_obeys_all_request_budgets(self):
        from foreign_trade_geo_agent.adapters.deepseek_change_plan import DeepSeekChangePlanWriter
        selected, scope = generic_fixture(10)
        report = native_planning(selected, scope)[0]
        prompt = cp.build_change_plan_prompt(cp.ChangePlanInput(selected, report, scope, scope.task_id))
        self.assertIsNone(cp.validate_provider_generation_material(prompt, prompt.material_json()))
        captures = []
        def handler(request):
            captures.append(request.content)
            return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}]})
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "offline-placeholder"}):
            result = asyncio.run(DeepSeekChangePlanWriter(transport=httpx.MockTransport(handler)).write_change_plan(prompt))
        self.assertEqual(len(captures), 1)
        payload = json.loads(captures[0])
        system, material = (m["content"] for m in payload["messages"])
        self.assertLessEqual(len(system), cp.MAX_SYSTEM_PROMPT_CHARS)
        self.assertIn("first_party_planning overrides S/point limits", system)
        self.assertLessEqual(len(system.encode()), cp.MAX_SYSTEM_PROMPT_BYTES)
        self.assertLessEqual(len(material), cp.MAX_USER_MATERIAL_CHARS)
        self.assertLessEqual(len(material.encode()), cp.MAX_USER_MATERIAL_BYTES)
        self.assertLessEqual(len(captures[0].decode()), cp.MAX_INPUT_ENVELOPE_CHARS)
        self.assertLessEqual(len(captures[0]), cp.MAX_INPUT_ENVELOPE_BYTES)
        self.assertEqual(payload["max_tokens"], cp.MAX_PROVIDER_TOKENS)
        self.assertEqual(result.status, cp.ChangePlanGenerationStatus.SUCCESS)
        # Native trimming may never erase a required quote to satisfy budget.
        with patch.object(cp, "MAX_USER_MATERIAL_CHARS", 100):
            bounded = cp.build_change_plan_prompt(cp.ChangePlanInput(selected, report, scope, scope.task_id))
            self.assertEqual(bounded.allowed_operation_types_for("R1"), ())
            self.assertIsNotNone(cp.validate_provider_generation_material(bounded, bounded.material_json()))


if __name__ == "__main__":
    unittest.main()
