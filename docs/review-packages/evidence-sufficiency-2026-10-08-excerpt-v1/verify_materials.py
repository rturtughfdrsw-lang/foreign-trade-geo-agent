"""Read-only blocked-candidate probes. Never plans, finalizes, or writes artifacts."""
from pathlib import Path
import hashlib
import json
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "src"))

from foreign_trade_geo_agent.core.first_party_planning import FirstPartyExcerpt, FirstPartyPlanningScope
from foreign_trade_geo_agent.core.history import ArtifactType
from foreign_trade_geo_agent.core import content_opportunity as co
from foreign_trade_geo_agent.storage.serialization import decode_artifact, encode_artifact


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def read(name):
    return json.loads((HERE / name).read_text(encoding="utf-8"))


def rejected(call):
    try:
        call()
    except ValueError as exc:
        return {"status": "REJECTED", "exception": type(exc).__name__, "message": str(exc)}
    raise AssertionError("Invalid full-task scope unexpectedly accepted")


def probe():
    task, coverage = read("task.json"), read("coverage.json")
    packet = decode_artifact(ArtifactType.SITE_CONTENT, 1, (HERE / "snapshots/site_content.json").read_text(encoding="utf-8"))
    page = packet.pages[2]
    assert page.evidence_id == "P3" and not page.structured_content_truncated
    field = page.structured_content[0].text
    source = (HERE / "snapshots/solutions.astro").read_bytes().decode("utf-8")
    ids = [o["obligation_id"] for o in coverage["obligations"]]
    assert ids == task["required_obligation_ids"] == ["O1", "O2", "O3", "O4", "O5", "O6"]
    spans = [o["artifact_span"] for o in coverage["obligations"]]
    for o in coverage["obligations"]:
        for text, key in ((field, "artifact_span"), (source, "corroborating_source_span")):
            s = o[key]
            assert text[s["start"]:s["end"]] == s["quote"]
            assert sha(text.encode("utf-8")) == s["field_sha256"]
            assert sha(s["quote"].encode("utf-8")) == s["quote_sha256"]
        assert o["human_support_verdict"] == "NOT_REVIEWED"
    def excerpt(s):
        return FirstPartyExcerpt("structured_text", s["start"], s["end"], s["quote"], 0)
    def scope(excerpts):
        return FirstPartyPlanningScope(task["task_id"], packet, "P3", page.h1[0], tuple(excerpts))
    # Full six-sentence task fails before a workflow can receive a legal scope.
    full = rejected(lambda: scope(excerpt(s) for s in spans))
    o1 = rejected(lambda: excerpt(spans[0]))
    # Isolate the count limit with six authentic <=120-char fragments. This
    # deliberately incomplete diagnostic is never offered as the real task.
    fragments = [FirstPartyExcerpt("structured_text", s["start"], min(s["end"], s["start"] + 120), s["quote"][:120], 0) for s in spans]
    count = rejected(lambda: scope(fragments))
    # Split O1 into authentic contiguous fragments: still seven excerpts.
    first = spans[0]
    split = [FirstPartyExcerpt("structured_text", first["start"], first["start"] + 65, first["quote"][:65], 0),
             FirstPartyExcerpt("structured_text", first["start"] + 65, first["end"], first["quote"][65:], 0)]
    split += [excerpt(s) for s in spans[1:]]
    split_result = rejected(lambda: scope(split))
    old = json.loads((ROOT / "docs/review-packages/evidence-sufficiency-2026-10-08-v2/planning-candidate.json").read_text(encoding="utf-8"))["specifications"]["opportunity"]
    spec = co.ContentOpportunitySpecification(co.ContentOpportunityType(old["opportunity_type"]), co.ContentOpportunityPriority(old["priority"]), old["topic"], tuple(co.ContentOpportunityActionCode(a) for a in old["action_codes"]), tuple(old["page_refs"]), (), ())
    old_error = co.validate_content_opportunity_specification(spec, co.build_content_opportunity_evidence_catalog(packet, ()), ())
    assert old_error == "SOURCE_REFERENCE_REQUIRED"
    return {"status": "BLOCKED_NOT_FINALIZED", "sentence_lengths": [len(s["quote"]) for s in spans],
            "total_sentence_characters": sum(len(s["quote"]) for s in spans),
            "full_task_scope": full, "O1_full_sentence": o1, "six_short_fragments_count_probe": count,
            "seven_exact_fragments": split_result, "old_EXPLAIN_opportunity_error": old_error,
            "new_task_workflow_calls": 0, "new_opportunity_finalizer_calls": 0,
            "new_plan_finalizer_calls": 0, "new_artifact_ids": None,
            "draft_writer_calls": 0, "paid_LLM_calls": 0, "wordpress_calls": 0,
            "availability_locator_and_plan_checks": "NOT_REACHED; legal scope prerequisite failed"}


def verify():
    binding, manifest = read("binding.json"), read("manifest.json")
    assert sha(canonical(binding)) == manifest["binding_canonical_sha256"]
    for name, digest in binding["files_sha256"].items():
        assert sha((HERE / name).read_bytes()) == digest, name
    assert read("planning-validation.json") == probe()
    assert binding["opportunity_artifact"] is None and binding["plan_artifact"] is None
    assert binding["task_version"] == 1 and binding["review_object"] == "BLOCKED_PREPARATION_ONLY"
    oldroot = ROOT / "docs/review-packages/evidence-sufficiency-2026-10-08-v2"
    oldmanifest = json.loads((oldroot / "manifest.json").read_text(encoding="utf-8"))
    for name, digest in oldmanifest["package_files_sha256"].items():
        assert sha((ROOT / name).read_bytes()) == digest, name
    for name, kind in (("site_content", ArtifactType.SITE_CONTENT), ("site_audit", ArtifactType.SITE_AUDIT), ("industry_research", ArtifactType.INDUSTRY_RESEARCH), ("content_opportunity", ArtifactType.CONTENT_OPPORTUNITY), ("change_plan", ArtifactType.CHANGE_PLAN)):
        raw = (oldroot / "snapshots" / (name + ".json")).read_text(encoding="utf-8")
        assert json.loads(encode_artifact(kind, decode_artifact(kind, 1, raw))) == json.loads(raw)
    record = read("owner-decision.json")
    assert all(d["status"] == "NOT_REVIEWED" for d in record["whole_item_states"])
    assert all(o["verdict"] == "NOT_REVIEWED" for o in record["obligations"])
    assert not record["source"]["identity_or_signature_verified"] and not record["runtime_approval_valid"]
    print(json.dumps({"integrity": "PASS", "historical_v2": "UNCHANGED; five artifact roundtrips PASS", "probe": probe()}, indent=2))


if __name__ == "__main__":
    verify()
