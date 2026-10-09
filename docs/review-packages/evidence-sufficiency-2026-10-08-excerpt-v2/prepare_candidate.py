"""One-time offline freeze, using production workflows and injected writers.

Refuses to overwrite a candidate. No provider, website, SQLite, or CMS I/O.
"""
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import shutil
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from tests.test_first_party_excerpt_capacity import (
    OLD, LiteralOpportunityWriter, LiteralPlanWriter, six_obligation_fixture,
)
from foreign_trade_geo_agent.core import content_opportunity as co, change_plan as cp, content_draft as cd
from foreign_trade_geo_agent.core.history import ArtifactType
from foreign_trade_geo_agent.storage.serialization import encode_artifact
from foreign_trade_geo_agent.workflows.content_opportunity import ContentOpportunityWorkflow
from foreign_trade_geo_agent.workflows.change_plan import ChangePlanWorkflow
from foreign_trade_geo_agent.workflows.content_draft import ContentDraftWorkflow
from foreign_trade_geo_agent.adapters.deepseek_content_draft import DeepSeekContentDraftWriter, content_draft_request_payload
import asyncio

TASK_ID = "T-P3-SIX-RELATIONS-ATTRIBUTED-EXCERPT-v2"
PACKAGE_ID = "ESG-P3-EXCERPT-CANDIDATE-20261008-v2"


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    return json.loads(path.read_bytes().decode("utf-8"))


def write_json(name, value):
    (HERE / name).write_bytes(canonical(value))


class CapturedOpportunityWriter(LiteralOpportunityWriter):
    async def write_content_opportunities(self, prompt):
        self.material = prompt.material_json()
        result = await super().write_content_opportunities(prompt)
        self.output = result.text
        return result


class CapturedPlanWriter(LiteralPlanWriter):
    async def write_change_plan(self, prompt):
        self.prompt = prompt
        self.material = prompt.material_json()
        result = await super().write_change_plan(prompt)
        self.output = result.text
        return result


class NoDraftWriter:
    def __init__(self):
        self.calls = 0

    async def write_content_draft(self, prompt):
        self.calls += 1
        raise AssertionError("Draft admission must remain closed")


def prepare():
    allowed = {"prepare_candidate.py", "verify_materials.py", "README.md"}
    if any(p.name not in allowed for p in HERE.iterdir()):
        raise SystemExit("STOP: candidate already exists; no overwrite permitted")
    selected, scope, coverage = six_obligation_fixture()
    scope = replace(scope, task_id=TASK_ID)
    writer, planner = CapturedOpportunityWriter(), CapturedPlanWriter()
    report = asyncio.run(ContentOpportunityWorkflow(writer).run(
        selected, None, first_party_scope=scope, task_id=TASK_ID))
    plan = asyncio.run(ChangePlanWorkflow(planner).run(
        selected, report, first_party_scope=scope, task_id=TASK_ID))
    assert report.status is co.ContentOpportunityStatus.SUCCESS
    assert plan.status is cp.ChangePlanStatus.SUCCESS and len(plan.operations) == 1
    assert (writer.calls, planner.calls) == (1, 1)
    assert cp.validate_change_plan_input(cp.ChangePlanInput(selected, report, scope, TASK_ID)) is None
    assert cp.validate_provider_generation_material(planner.prompt, planner.material) is None
    assert planner.prompt.allowed_operation_types_for("R1") == (cp.ChangeOperationType.EXPAND_SECTION,)
    assert tuple(p.subject for p in plan.operations[0].content_points) == scope.quotes

    # Construct the actual input object, but preserve the native rejection.
    # Direct serializer inspection never authorizes a writer invocation.
    draft_input = cd.ContentDraftInput(selected, report, plan, "en")
    admission_error = cd.stable_content_draft_input_error(draft_input)
    assert admission_error == "FIELD_CONTRACT"
    try:
        cd.build_content_draft_prompt(draft_input, "C1")
    except ValueError as exc:
        assert str(exc) == admission_error
    else:
        raise AssertionError("Native Draft builder unexpectedly admitted task")
    draft_writer = NoDraftWriter()
    draft_report = asyncio.run(ContentDraftWorkflow(draft_writer).run(draft_input))
    assert draft_report.status is cd.ContentDraftStatus.INVALID_INPUT and draft_writer.calls == 0
    draft_preview = cd.ContentDraftPrompt(draft_input, "C1", plan.operations[0], report.opportunities[0],
                                         (selected.pages[2],), ())
    material = draft_preview.material_json()
    system = DeepSeekContentDraftWriter.build_system_prompt()
    envelope = json.dumps(content_draft_request_payload(system, material), ensure_ascii=False, separators=(",", ":"))
    assert len(material) <= cd.MAX_USER_MATERIAL_CHARS and len(material.encode()) <= cd.MAX_USER_MATERIAL_BYTES
    assert len(system) <= cd.MAX_SYSTEM_PROMPT_CHARS and len(system.encode()) <= cd.MAX_SYSTEM_PROMPT_BYTES
    assert len(envelope) <= cd.MAX_INPUT_ENVELOPE_CHARS and len(envelope.encode()) <= cd.MAX_INPUT_ENVELOPE_BYTES
    payload = json.loads(material)
    assert payload["sources"] == [] and payload["change"]["source_refs"] == []
    full_field = payload["pages"][0]["structured_content"][0]["text"]
    for obligation in coverage["obligations"]:
        span = obligation["artifact_span"]
        indexes = [i for i, e in enumerate(scope.excerpts) if span["start"] <= e.start < e.end <= span["end"]]
        parts = [scope.excerpts[i] for i in indexes]
        assert parts[0].start == span["start"] and parts[-1].end == span["end"]
        assert all(a.end == b.start for a, b in zip(parts, parts[1:]))
        assert "".join(e.quote for e in parts) == full_field[span["start"]:span["end"]] == span["quote"]
        assert obligation["human_support_verdict"] == "NOT_REVIEWED"
        obligation.update(task_id=TASK_ID, task_version=2,
                          content_point_paths=[f"operations[0].content_points[{i}]" for i in indexes],
                          excerpt_spans=[asdict(e) for e in parts],
                          draft_visible_span={"field_path": "pages[0].structured_content[0].text", **span})

    # All dependent files are emitted only after full native Planning succeeds.
    (HERE / "snapshots").mkdir()
    for name in ("site_content.json", "solutions.astro", "DemoDisclosure.astro", "config.ts", "experiment-baseline.md"):
        shutil.copyfile(OLD / "snapshots" / name, HERE / "snapshots" / name)
    shutil.copyfile(OLD / "owner-decision.json", HERE / "owner-decision-inherited.json")
    shutil.copyfile(OLD / "source-provenance.json", HERE / "source-provenance.json")
    opportunity_raw = encode_artifact(ArtifactType.CONTENT_OPPORTUNITY, report)
    plan_raw = encode_artifact(ArtifactType.CHANGE_PLAN, plan)
    (HERE / "content_opportunity.json").write_bytes(opportunity_raw.encode("utf-8"))
    (HERE / "change_plan.json").write_bytes(plan_raw.encode("utf-8"))
    for name, text in (("opportunity-visible-material.json", writer.material), ("opportunity-writer-output.json", writer.output),
                       ("plan-visible-material.json", planner.material), ("plan-writer-output.json", planner.output),
                       ("draft-visible-material.json", material)):
        (HERE / name).write_bytes(text.encode("utf-8"))
    task = read(OLD / "task.json")
    task.update(task_id=TASK_ID, task_version=2, status="NATIVE_PLANNING_SUCCESS_REVIEW_PENDING",
                previous_excerpt_task_id=task["task_id"], previous_excerpt_binding_sha256=sha((OLD / "binding.json").read_bytes()),
                opportunity_artifact="content_opportunity.json", plan_artifact="change_plan.json")
    write_json("task.json", task)
    write_json("coverage.json", coverage)
    write_json("planning-scope.json", {"task_id": TASK_ID, "task_kind": scope.task_kind, "page_ref": scope.page_ref,
                                       "heading": scope.heading, "site_content_file": "snapshots/site_content.json",
                                       "excerpts": [asdict(e) for e in scope.excerpts]})
    write_json("draft-input.json", {"site_content": read(HERE / "snapshots/site_content.json"),
                                   "opportunity_report": json.loads(opportunity_raw), "change_plan_report": json.loads(plan_raw),
                                   "target_language": draft_input.target_language})
    write_json("draft-visible-input.json", {
        "status": "PRODUCTION_SERIALIZER_PREVIEW; NATIVE_DRAFT_ADMISSION_BLOCKED",
        "actual_DraftInput_file": "draft-input.json", "actual_DraftInput_canonical_sha256": sha(canonical(read(HERE / "draft-input.json"))),
        "serializer": "core.content_draft.ContentDraftPrompt.material_json",
        "material_file": "draft-visible-material.json", "material_utf8_sha256": sha(material.encode()),
        "system_prompt_utf8_sha256": sha(system.encode()), "envelope_utf8_sha256": sha(envelope.encode()),
        "material_characters": len(material), "material_bytes": len(material.encode()),
        "system_characters": len(system), "system_bytes": len(system.encode()),
        "envelope_characters": len(envelope), "envelope_bytes": len(envelope.encode()),
        "native_builder_error": admission_error, "native_workflow_status": draft_report.status.value,
        "draft_writer_calls": 0, "draft_admission": False,
        "limitation": "No admitted DraftPrompt or actual provider request exists. This exact candidate serializer output is bound for review; D05 input consumption and a trusted loader/Gate are unimplemented.",
    })
    code_files = [
        "core/first_party_planning.py", "core/change_plan.py", "core/content_opportunity.py", "core/content_draft.py",
        "workflows/change_plan.py", "workflows/content_opportunity.py", "workflows/content_draft.py",
        "adapters/deepseek_change_plan.py", "adapters/deepseek_content_draft.py", "storage/serialization.py",
    ]
    write_json("capacity-policy.json", {
        "excerpt_characters": 120, "scope_fragments": 10, "p_only_expand_points": 10, "p_only_operations": 1,
        "aggregate_subject_characters": 1200, "ordinary_operation_points": 5,
        "basis": "Existing per-opportunity budget: 2 operations x 5 points x 120 characters; consolidate only literal P-only excerpts into one substantive expansion.",
        "schema_codec_public_signature_changes": False, "draft_admission": False, "gate_implemented": False,
        "code_sha256": {"src/foreign_trade_geo_agent/" + name: sha((ROOT / "src/foreign_trade_geo_agent" / name).read_bytes()) for name in code_files},
    })
    write_json("planning-validation.json", {
        "opportunity_status": report.status.value, "plan_status": plan.status.value,
        "full_task_complete_at_planning": True, "required_obligations": ["O1", "O2", "O3", "O4", "O5", "O6"],
        "full_sentence_characters": 705, "fragment_count": 7, "fragment_lengths": [len(e.quote) for e in scope.excerpts],
        "operation_count": 1, "source_refs": [], "audit_refs": [],
        "allowed_operation_types": ["EXPAND_SECTION"], "stable_planning_input_error": None,
        "provider_material_error": None, "offline_opportunity_writer_calls": 1, "offline_plan_writer_calls": 1,
        "paid_LLM_calls": 0, "draft_writer_calls": 0, "wordpress_calls": 0, "external_website_operations": 0,
        "history_artifact_ids": None, "artifact_location": "Local frozen V1 codec payload files; not appended to production SQLite",
        "native_Draft_admission_error": admission_error, "gate_status": "NOT_IMPLEMENTED_NOT_GREEN",
    })
    inherited = read(HERE / "owner-decision-inherited.json")
    write_json("review-record.template.json", {
        "package_id": PACKAGE_ID, "task_id": TASK_ID, "task_version": 2,
        "overall_verdict": "NOT_REVIEWED", "runtime_approval_valid": False,
        "owner_decisions": [{"decision_id": d["id"], "decision": "NOT_REVIEWED", "reason": None}
                            for d in inherited["whole_item_states"]],
        "obligations": [{"obligation_id": o["obligation_id"], "verdict": "NOT_REVIEWED", "reason": None}
                        for o in coverage["obligations"]],
        "reviewer": None, "reviewed_at": None, "expires_at": None,
    })
    prior_files = {}
    for prior in (OLD, ROOT / "docs/review-packages/evidence-sufficiency-2026-10-08-v2"):
        for path in prior.rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts:
                prior_files[str(path.relative_to(ROOT)).replace("\\", "/")] = sha(path.read_bytes())
    names = [p.relative_to(HERE).as_posix() for p in HERE.rglob("*") if p.is_file()
             and "__pycache__" not in p.parts and p.name != "README.md"]
    binding = {
        "package_id": PACKAGE_ID, "task_id": TASK_ID, "task_version": 2,
        "review_object": "FULL_NATIVE_PLANNING_CANDIDATE; DRAFT_BLOCKED; NOT_REVIEWED",
        "files_sha256": {name: sha((HERE / name).read_bytes()) for name in sorted(names)},
        "prior_package_files_sha256": prior_files,
        "opportunity_payload_version": 1, "plan_payload_version": 1,
        "selected_evidence": ["P3"], "required_obligation_ids": ["O1", "O2", "O3", "O4", "O5", "O6"],
        "draft_material_sha256": sha(material.encode()), "human_verdict": "NOT_REVIEWED",
        "runtime_approval_valid": False,
    }
    write_json("binding.json", binding)
    write_json("manifest.json", {"package_id": PACKAGE_ID, "binding_canonical_sha256": sha(canonical(binding)),
                                "gate_green": False, "O1_to_O6": "NOT_REVIEWED"})
    print(json.dumps({"package": PACKAGE_ID, "opportunity": report.status.value, "plan": plan.status.value,
                      "binding_sha256": sha(canonical(binding)), "Draft": admission_error, "Gate": "NOT_GREEN"}, indent=2))


if __name__ == "__main__":
    prepare()
