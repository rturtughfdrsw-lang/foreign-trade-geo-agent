"""Read-only integrity and native full-task replay. No approval or Gate verdict."""
from dataclasses import replace
import asyncio
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from tests.test_first_party_excerpt_capacity import (
    LiteralOpportunityWriter, LiteralPlanWriter, native_planning,
)
from foreign_trade_geo_agent.core import content_opportunity as co, change_plan as cp, content_draft as cd
from foreign_trade_geo_agent.core.first_party_planning import FirstPartyExcerpt, FirstPartyPlanningScope
from foreign_trade_geo_agent.core.history import ArtifactType
from foreign_trade_geo_agent.storage.serialization import decode_artifact, encode_artifact
from foreign_trade_geo_agent.workflows.change_plan import ChangePlanWorkflow
from foreign_trade_geo_agent.workflows.content_draft import ContentDraftWorkflow
from foreign_trade_geo_agent.adapters.deepseek_content_draft import DeepSeekContentDraftWriter, content_draft_request_payload


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def read(name):
    return json.loads((HERE / name).read_bytes().decode("utf-8"))


def artifact(kind, name):
    raw = (HERE / name).read_bytes().decode("utf-8")
    value = decode_artifact(kind, 1, raw)
    assert json.loads(encode_artifact(kind, value)) == json.loads(raw)
    return value


class NoDraftWriter:
    calls = 0

    async def write_content_draft(self, prompt):
        self.calls += 1
        raise AssertionError("Draft admission remains closed")


def verify():
    binding, manifest = read("binding.json"), read("manifest.json")
    assert sha(canonical(binding)) == manifest["binding_canonical_sha256"]
    for name, digest in binding["files_sha256"].items():
        assert sha((HERE / name).read_bytes()) == digest, name
    for name, digest in binding["prior_package_files_sha256"].items():
        assert sha((ROOT / name).read_bytes()) == digest, name
    policy = read("capacity-policy.json")
    for name, digest in policy["code_sha256"].items():
        assert sha((ROOT / name).read_bytes()) == digest, name
    assert (policy["scope_fragments"], policy["excerpt_characters"]) == (10, 120)
    selected = artifact(ArtifactType.SITE_CONTENT, "snapshots/site_content.json")
    report = artifact(ArtifactType.CONTENT_OPPORTUNITY, "content_opportunity.json")
    plan = artifact(ArtifactType.CHANGE_PLAN, "change_plan.json")
    task, raw_scope = read("task.json"), read("planning-scope.json")
    scope = FirstPartyPlanningScope(raw_scope["task_id"], selected, raw_scope["page_ref"], raw_scope["heading"],
                                   tuple(FirstPartyExcerpt(**e) for e in raw_scope["excerpts"]), raw_scope["task_kind"])
    assert task["task_id"] == scope.task_id == binding["task_id"] and task["task_version"] == 2
    assert task["required_obligation_ids"] == binding["required_obligation_ids"] == ["O1", "O2", "O3", "O4", "O5", "O6"]
    assert report.status is co.ContentOpportunityStatus.SUCCESS and plan.status is cp.ChangePlanStatus.SUCCESS
    assert len(plan.operations) == 1 and len(plan.operations[0].content_points) == 7
    assert plan.operations[0].page_refs == ("P3",) and not plan.operations[0].source_refs
    assert not report.source_materials and not report.audit_evidence
    assert cp.validate_change_plan_input(cp.ChangePlanInput(selected, report, scope, scope.task_id)) is None
    replay_report, replay_plan, writer, planner = native_planning(selected, scope)
    assert replay_report == report and replay_plan == plan and (writer.calls, planner.calls) == (1, 1)
    prompt = cp.build_change_plan_prompt(cp.ChangePlanInput(selected, report, scope, scope.task_id))
    assert prompt.material_json().encode() == (HERE / "plan-visible-material.json").read_bytes()
    assert cp.validate_provider_generation_material(prompt, prompt.material_json()) is None
    assert prompt.allowed_operation_types_for("R1") == (cp.ChangeOperationType.EXPAND_SECTION,)

    # Full obligations, precise snapshot spans, exact source-file corroboration,
    # and actual production serializer material all agree. No partial coverage.
    coverage = read("coverage.json")
    assert [o["obligation_id"] for o in coverage["obligations"]] == task["required_obligation_ids"]
    actual_input = cd.ContentDraftInput(selected, report, plan, "en")
    serialized_input = {"site_content": read("snapshots/site_content.json"), "opportunity_report": read("content_opportunity.json"),
                        "change_plan_report": read("change_plan.json"), "target_language": "en"}
    assert serialized_input == read("draft-input.json")
    preview = cd.ContentDraftPrompt(actual_input, "C1", plan.operations[0], report.opportunities[0], (selected.pages[2],), ())
    material = preview.material_json()
    assert material.encode() == (HERE / "draft-visible-material.json").read_bytes()
    visible = json.loads(material)
    field = selected.pages[2].structured_content[0].text
    visible_field = visible["pages"][0]["structured_content"][0]["text"]
    assert field == visible_field
    source = (HERE / "snapshots/solutions.astro").read_bytes().decode("utf-8")
    used_indexes = []
    for obligation in coverage["obligations"]:
        assert obligation["task_id"] == task["task_id"] and obligation["task_version"] == 2
        assert obligation["human_support_verdict"] == "NOT_REVIEWED" and obligation["human_reason"] is None
        span, corroborating = obligation["artifact_span"], obligation["corroborating_source_span"]
        assert sha(field.encode()) == span["field_sha256"]
        assert sha(source.encode()) == corroborating["field_sha256"]
        assert field[span["start"]:span["end"]] == source[corroborating["start"]:corroborating["end"]] == span["quote"]
        assert sha(span["quote"].encode()) == span["quote_sha256"] == corroborating["quote_sha256"]
        parts = [FirstPartyExcerpt(**e) for e in obligation["excerpt_spans"]]
        assert parts[0].start == span["start"] and parts[-1].end == span["end"]
        assert all(a.end == b.start for a, b in zip(parts, parts[1:]))
        assert "".join(e.quote for e in parts) == visible_field[span["start"]:span["end"]] == span["quote"]
        indexes = [scope.excerpts.index(e) for e in parts]
        assert obligation["content_point_paths"] == [f"operations[0].content_points[{i}]" for i in indexes]
        assert [plan.operations[0].content_points[i].subject for i in indexes] == [e.quote for e in parts]
        used_indexes.extend(indexes)
    assert used_indexes == list(range(7))
    assert sum(len(o["artifact_span"]["quote"]) for o in coverage["obligations"]) == 705
    assert tuple(p.subject for p in plan.operations[0].content_points) == scope.quotes

    draft_info = read("draft-visible-input.json")
    assert sha(canonical(serialized_input)) == draft_info["actual_DraftInput_canonical_sha256"]
    assert sha(material.encode()) == draft_info["material_utf8_sha256"] == binding["draft_material_sha256"]
    system = DeepSeekContentDraftWriter.build_system_prompt()
    envelope = json.dumps(content_draft_request_payload(system, material), ensure_ascii=False, separators=(",", ":"))
    assert sha(system.encode()) == draft_info["system_prompt_utf8_sha256"]
    assert sha(envelope.encode()) == draft_info["envelope_utf8_sha256"]
    for text, chars, byte_limit in ((material, cd.MAX_USER_MATERIAL_CHARS, cd.MAX_USER_MATERIAL_BYTES),
                                     (system, cd.MAX_SYSTEM_PROMPT_CHARS, cd.MAX_SYSTEM_PROMPT_BYTES),
                                     (envelope, cd.MAX_INPUT_ENVELOPE_CHARS, cd.MAX_INPUT_ENVELOPE_BYTES)):
        assert len(text) <= chars and len(text.encode()) <= byte_limit
    assert cd.stable_content_draft_input_error(actual_input) == "FIELD_CONTRACT"
    try:
        cd.build_content_draft_prompt(actual_input, "C1")
    except ValueError as exc:
        assert str(exc) == "FIELD_CONTRACT"
    else:
        raise AssertionError("Draft admitted without Gate")
    no_draft = NoDraftWriter()
    assert asyncio.run(ContentDraftWorkflow(no_draft).run(actual_input)).status is cd.ContentDraftStatus.INVALID_INPUT
    assert no_draft.calls == 0
    # Native task binding and full-task rejection, including writer=0.
    wrong_writer = LiteralPlanWriter()
    bad = asyncio.run(ChangePlanWorkflow(wrong_writer).run(selected, report, first_party_scope=scope, task_id="other-task"))
    assert bad.status is cp.ChangePlanStatus.INVALID_INPUT and wrong_writer.calls == 0
    for intent in ("EXPLAIN", "COMPARE"):
        def mutate(raw):
            raw["opportunity_operations"]["R1"]["primary_operation"]["content_points"][0]["intent"] = intent
        bad = native_planning(selected, scope, mutate)[1]
        assert bad.status is cp.ChangePlanStatus.INVALID_OUTPUT and not bad.operations
    original = ROOT / "docs/review-packages/evidence-sufficiency-2026-10-08-v2"
    old = json.loads((original / "planning-candidate.json").read_bytes())["specifications"]["opportunity"]
    spec = co.ContentOpportunitySpecification(co.ContentOpportunityType(old["opportunity_type"]),
        co.ContentOpportunityPriority(old["priority"]), old["topic"],
        tuple(co.ContentOpportunityActionCode(a) for a in old["action_codes"]), tuple(old["page_refs"]), (), ())
    assert co.validate_content_opportunity_specification(spec, co.build_content_opportunity_evidence_catalog(selected, ()), ()) == "SOURCE_REFERENCE_REQUIRED"
    for name, kind in (("site_content", ArtifactType.SITE_CONTENT), ("site_audit", ArtifactType.SITE_AUDIT),
                       ("industry_research", ArtifactType.INDUSTRY_RESEARCH), ("content_opportunity", ArtifactType.CONTENT_OPPORTUNITY),
                       ("change_plan", ArtifactType.CHANGE_PLAN)):
        raw = (original / "snapshots" / (name + ".json")).read_bytes().decode("utf-8")
        value = decode_artifact(kind, 1, raw)
        assert json.loads(encode_artifact(kind, value)) == json.loads(raw)
        if name == "change_plan":
            assert any(cp.comparison_operation_error(op) == "COMPARISON_UNAVAILABLE" for op in value.operations)
    template = read("review-record.template.json")
    assert all(o["verdict"] == "NOT_REVIEWED" for o in template["obligations"])
    assert all(d["decision"] == "NOT_REVIEWED" for d in template["owner_decisions"])
    assert not template["runtime_approval_valid"] and not manifest["gate_green"]
    print(json.dumps({"integrity": "PASS", "native_full_task_planning": "PASS; six obligations, seven spans, one Change",
                      "historical_packages": "UNCHANGED; five V1 roundtrips PASS", "draft_visibility": "SERIALIZER_PREVIEW_ONLY",
                      "native_Draft": "FIELD_CONTRACT; writer=0", "O1_to_O6": "NOT_REVIEWED", "Gate": "NOT_GREEN"}, indent=2))


if __name__ == "__main__":
    verify()
