"""One frozen SYNTHETIC E-only article experiment; default is offline prepare.

Live mode requires separate human chat authorization, exact bundle and expiry.
Neither TEST review nor local Web display grants production execution authority.
"""
import argparse
import asyncio
from dataclasses import replace
from datetime import UTC, datetime
import json
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory

from scripts import demo_seo_e_only as fixture
from scripts import prepare_seo_article_experiment as shared
from foreign_trade_geo_agent.adapters.deepseek_content_draft import DeepSeekContentDraftWriter, content_draft_request_payload
from foreign_trade_geo_agent.core import content_draft as cd
from foreign_trade_geo_agent.core.evidence_intake import snapshot_digest
from foreign_trade_geo_agent.core.history import ArtifactType
from foreign_trade_geo_agent.storage.evidence_intake import SQLiteEvidenceIntakeStore
from foreign_trade_geo_agent.storage.serialization import _decode, _encode
from foreign_trade_geo_agent.storage.sqlite import SQLiteHistoryReader
from foreign_trade_geo_agent.workflows.content_draft import _parse_specification

require, canonical, sha, write_json = shared.require, shared.canonical, shared.sha, shared.write_json
WORKFLOW = "isolated_e_only_article_experiment"
INSTRUCTIONS = """
ISOLATED SYNTHETIC E-only experiment: write one complete English buyer guide, with opening, connected explanation, practical enquiry questions and restrained closing CTA. Keep the approved title and both outline sections. Explain spindle test applicability for an export buyer. Include the complete required E1 quote with customer_refs ["E1"], never relabel its facts as P/S. P/S support background only. No invented mechanisms, benefits or promises. Preserve all native schema, attribution and budgets. TEST review is not human signoff or production authority.
"""


def code_hashes():
    paths = [Path(__file__).resolve(), shared.ROOT / "scripts/demo_seo_e_only.py"]
    return shared.code_hashes() | {p.relative_to(shared.ROOT).as_posix(): sha(p.read_bytes()) for p in paths}


def request_for(value):
    require(cd.stable_content_draft_input_error(value) is None and value.customer_evidence is not None,
            "NATIVE_INPUT_INVALID")
    require(value.target_language == "en" and len(value.change_plan_report.operations) == 1
            and value.change_plan_report.operations[0].operation_type.value == "CREATE_NEW_RESOURCE",
            "SINGLE_ENGLISH_ARTICLE_REQUIRED")
    native = cd.build_content_draft_prompt(value, "C1").material_json()
    material = json.loads(native)
    require(material["contract"]["customer_refs"] == ["E1"]
            and len(value.customer_evidence.sources) == 1
            and value.customer_evidence.sources[0].content == fixture.DOCUMENT
            and value.customer_evidence.sources[0].quote == fixture.FACT, "E1_REQUIRED")
    ps = canonical([material["pages"], material["sources"]]).decode()
    require(all(t not in ps for t in ("7200 rpm", "NOVA-TEST-7", "NCX7")), "E_FACT_LEAKED_TO_PS")
    system = DeepSeekContentDraftWriter.build_system_prompt(customer_evidence=True) + INSTRUCTIONS
    payload = content_draft_request_payload(system, native)
    # Historical short-article experiment retains its separate 3000-token cap.
    payload["max_tokens"] = 3000
    raw = canonical(payload)
    require(payload["model"] == "deepseek-flash" and payload["max_tokens"] == 3000
            and payload["thinking"] == {"type": "disabled"} and payload["temperature"] == 0,
            "REQUEST_CONFIG_CHANGED")
    require(len(system) <= cd.MAX_SYSTEM_PROMPT_CHARS and len(system.encode()) <= cd.MAX_SYSTEM_PROMPT_BYTES
            and len(native) <= cd.MAX_USER_MATERIAL_CHARS and len(native.encode()) <= cd.MAX_USER_MATERIAL_BYTES
            and len(raw) <= min(shared.MAX_REQUEST_BYTES, cd.MAX_INPUT_ENVELOPE_BYTES)
            and len(raw.decode()) <= cd.MAX_INPUT_ENVELOPE_CHARS, "INPUT_BUDGET_CONFLICT")
    return payload, native


def validate_candidate(value, text):
    operation = value.change_plan_report.operations[0]
    spec = _parse_specification(text, expected_change_ref="C1", operation=operation)
    require(spec.draft_type is cd.ContentDraftType.NEW_RESOURCE_DRAFT, "NEW_RESOURCE_REQUIRED")
    draft, error = cd.finalize_draft_item(1, spec, operation, value.opportunity_report.opportunities[0],
        value.site_content, value.opportunity_report, customer_evidence=value.customer_evidence)
    require(error is None and draft is not None, error or "NATIVE_VALIDATION_FAILED")
    return cd.ContentDraftReport(cd.ContentDraftStatus.SUCCESS, (draft,), cd.CONTENT_DRAFT_LIMITATIONS, None)


def quality_checklist():
    result = shared.quality_checklist()
    result["scope"] = "SYNTHETIC E-only / TEST-only review, no human signoff"
    result["search_intent"] = "Understand spindle rating applicability and prepare a technically scoped export enquiry."
    result["buyer_questions"] = ["Does the unloaded bench rating establish cutting-load performance?",
        "Which model, duty, protocol and temperature apply?", "Which acceptance evidence should the buyer request?"]
    result["required_facts"] = [{"fact_and_all_qualifiers": fixture.FACT, "source_ref": "E1",
        "source_file": "customer-E1.txt", "claim_ids": [], "decision": "UNREVIEWED", "reason": ""}]
    for row in result["checks"]:
        row["check"] = row["check"].replace("P/S attribution", "P/S/E attribution").replace("against P/S", "against P/S/E")
    result["note"] += " E1 must remain an exact complete quotation; review originality in the surrounding explanation."
    return result


def prepare(directory):
    directory = Path(directory)
    require(not directory.exists(), "OUTPUT_MUST_BE_NEW")
    with TemporaryDirectory() as temporary:
        origin = Path(temporary) / "origin"
        meta = fixture.prepare(origin)  # Existing bounded, offline E Intake and production Gate checks.
        store = SQLiteEvidenceIntakeStore(origin / "intake.sqlite3")
        snapshot = store.latest(meta["project_id"], meta["task_id"])
        value = fixture.prepare_test_input(store, meta["project_id"], meta["task_id"],
            expected_sha256=snapshot_digest(snapshot), reviewer=fixture.SyntheticEOnlyReviewer(), now=datetime.now(UTC))
        payload, native = request_for(value)
        witness = asyncio.run(fixture.FixedEOnlyWriter().write_content_draft(cd.build_content_draft_prompt(value, "C1")))
        report = validate_candidate(value, witness.text)
        directory.mkdir(parents=True)
        shutil.copyfile(origin / "intake.sqlite3", directory / "intake.sqlite3")
        shutil.copyfile(origin / "history.sqlite3", directory / "origin-history.sqlite3")
    write_json(directory / "native-input.json", _encode(value))
    write_json(directory / "task.json", _encode(snapshot.task))
    write_json(directory / "intake-snapshot.json", _encode(snapshot))
    write_json(directory / "change-plan.json", _encode(value.change_plan_report))
    write_json(directory / "evidence-binding.json", _encode(value.customer_evidence))
    (directory / "customer-E1.txt").write_bytes(fixture.DOCUMENT.encode())
    (directory / "native-material.json").write_bytes(native.encode())
    (directory / "user-material.json").write_bytes(payload["messages"][1]["content"].encode())
    (directory / "system-prompt.txt").write_bytes(payload["messages"][0]["content"].encode())
    (directory / "request.json").write_bytes(canonical(payload))
    write_json(directory / "quality-checklist.json", quality_checklist())
    summary = {"status": "PREPARED_PENDING_MOCK", "scope": "SYNTHETIC E-only TEST ONLY",
        "project_id": value.customer_evidence.project_id, "task_id": value.customer_evidence.task_id,
        "request_sha256": sha(canonical(payload)), "request_utf8_bytes": len(canonical(payload)),
        "system_prompt_chars": len(payload["messages"][0]["content"]),
        "endpoint": shared.ENDPOINT, "model": payload["model"], "thinking": payload["thinking"], "temperature": 0,
        "max_output_tokens": 3000, "max_requests": 1, "automatic_retries": 0,
        "timeout_seconds": shared.TIMEOUT_SECONDS, "max_request_bytes": shared.MAX_REQUEST_BYTES,
        "max_response_bytes": shared.MAX_RESPONSE_BYTES, "redirects": False, "trust_env": False,
        "native_output_max_chars": cd.MAX_RAW_OUTPUT_CHARS, "native_output_max_bytes": cd.MAX_RAW_OUTPUT_BYTES,
        "max_blocks": cd.MAX_BLOCKS_PER_DRAFT, "max_claims": cd.MAX_CLAIMS_PER_DRAFT, "max_claim_chars": cd.MAX_CLAIM_CHARS,
        "capacity_witness": {"handwritten_not_model": True, "blocks": len(report.drafts[0].blocks),
            "claims": sum(len(b.claims) for b in report.drafts[0].blocks), "token_fit": "NOT_TOKENIZER_VERIFIED"},
        "production_gate": "INTAKE_EXECUTION_BLOCKED", "production_writer_calls": 0,
        "production_authorized": False, "wordpress_authorized": False, "real_requests": 0,
        "p1": "UNCHANGED", "postgresql": "BLOCKED", "model_quality": "NOT_TESTED",
        "fee_limit": "One request/input/output caps only; no account-side monetary cap asserted.",
        "test_review": "Reassess the exact frozen Intake in disposable copies before/after execution; never human signoff."}
    write_json(directory / "preflight.json", summary)
    manifest = {"files": {p.name: sha(p.read_bytes()) for p in sorted(directory.iterdir())}, "code": code_hashes()}
    write_json(directory / "bundle.json", manifest)
    digest = sha(canonical(manifest))
    (directory / "bundle.sha256").write_text(digest + "\n", encoding="ascii")
    return summary | {"bundle_sha256": digest}


def load_frozen(directory, digest, *, now=None):
    directory = Path(directory)
    manifest_raw = (directory / "bundle.json").read_bytes()
    require(sha(manifest_raw) == digest, "BUNDLE_CHANGED")
    manifest = json.loads(manifest_raw)
    require(manifest["code"] == code_hashes(), "EXPERIMENT_CODE_CHANGED")
    require(all(Path(name).name == name and sha((directory / name).read_bytes()) == expected
                for name, expected in manifest["files"].items()), "FROZEN_INPUT_CHANGED")
    frozen = _decode(json.loads((directory / "native-input.json").read_bytes()), cd.ContentDraftInput)
    bundle = frozen.customer_evidence
    now = now or datetime.now(UTC)
    # Checks append audit records. Disposable copies keep the frozen journal immutable.
    with TemporaryDirectory() as temporary:
        journal = Path(temporary) / "intake.sqlite3"
        shutil.copyfile(directory / "intake.sqlite3", journal)
        value = fixture.prepare_test_input(SQLiteEvidenceIntakeStore(journal), bundle.project_id, bundle.task_id,
            expected_sha256=bundle.snapshot_sha256, reviewer=fixture.SyntheticEOnlyReviewer(), now=now)
    require(replace(value, customer_evidence=replace(value.customer_evidence, reviewed_at=bundle.reviewed_at)) == frozen,
            "FROZEN_INPUT_CHANGED")
    request = (directory / "request.json").read_bytes()
    require(request == canonical(request_for(value)[0]), "FROZEN_REQUEST_CHANGED")
    return value, request


def refreeze(source, digest, directory):
    """New code binding with byte-identical historical inputs; never regenerate E."""
    source, directory = Path(source), Path(directory)
    require(not directory.exists(), "OUTPUT_MUST_BE_NEW")
    raw = (source / "bundle.json").read_bytes()
    require(sha(raw) == digest, "BUNDLE_CHANGED")
    previous = json.loads(raw)
    files = previous["files"]
    require(all(Path(name).name == name and sha((source / name).read_bytes()) == expected
                for name, expected in files.items()), "FROZEN_INPUT_CHANGED")
    directory.mkdir(parents=True)
    shared.restrict_directory(directory)
    for name in files:
        shared.save_bytes(directory / name, (source / name).read_bytes())
    manifest = {"files": files, "code": code_hashes()}
    write_json(directory / "bundle.json", manifest)
    updated_digest = sha(canonical(manifest))
    (directory / "bundle.sha256").write_text(updated_digest + "\n", encoding="ascii")
    # Reconstruct/reassess the frozen native input, including exact request equality.
    load_frozen(directory, updated_digest)
    return {"status": "PREPARED_PENDING_MOCK", "bundle_sha256": updated_digest,
            "previous_bundle_sha256": digest, "input_files_changed": [], "real_requests": 0,
            "authorization": "NEW_EXPLICIT_HUMAN_AUTHORIZATION_REQUIRED"}


def revalidate_execution(value, latest):
    now = datetime.now(UTC)
    require(value.customer_evidence.fresh_at(now) and latest.customer_evidence.fresh_at(now),
            "CUSTOMER_EVIDENCE_INVALID")
    require(replace(latest, customer_evidence=replace(latest.customer_evidence,
        reviewed_at=value.customer_evidence.reviewed_at)) == value, "FROZEN_INPUT_CHANGED")


def persist_candidate(directory, value, report, text, *, is_mock, after_review):
    shutil.copyfile(directory.parent / "origin-history.sqlite3", directory / "history.sqlite3")
    result = shared.persist_candidate(directory, value, report, text, is_mock=is_mock,
        workflow_name=WORKFLOW, scope="SYNTHETIC E-only TEST ONLY", checklist=quality_checklist())
    write_json(directory / "execution-review.json", {"before": _encode(value.customer_evidence),
        "after": _encode(after_review), "human_signoff": False, "production_authorized": False})
    return result


async def run_once(directory, digest, *, mock_transport=None, expires_at=None):
    return await shared.run_once(Path(directory), digest, mock_transport=mock_transport,
        expires_at=expires_at, experiment=sys.modules[__name__])


def prepare_web_preview(directory, digest, result, output):
    """Explicit local package creation; no browser-controlled paths or generation API."""
    directory, output = Path(directory), Path(output)
    require(not output.exists(), "OUTPUT_MUST_BE_NEW")
    value, _ = load_frozen(directory, digest)
    source = Path(result["output"])
    require(source.resolve().parent == directory.resolve() and result["status"] == "SUCCESS"
            and result["bundle_sha256"] == digest
            and json.loads((source / "diagnostics.json").read_bytes()) == result, "CANDIDATE_BINDING_INVALID")
    reader = SQLiteHistoryReader(source / "history.sqlite3")
    run = reader.get_run(result["run_id"])
    report = reader.get_artifact(result["artifact_id"]).payload
    require(run.workflow_name == WORKFLOW and report.status is cd.ContentDraftStatus.SUCCESS,
            "CANDIDATE_BINDING_INVALID")
    bundle = report.drafts[0].customer_evidence
    require(replace(bundle, reviewed_at=value.customer_evidence.reviewed_at) == value.customer_evidence,
            "CANDIDATE_BINDING_INVALID")
    (output / "candidate").mkdir(parents=True)
    shutil.copyfile(source / "history.sqlite3", output / "candidate/history.sqlite3")
    shutil.copyfile(source / "diagnostics.json", output / "candidate/diagnostics.json")
    shutil.copyfile(directory / "intake.sqlite3", output / "interactive-intake.sqlite3")
    write_json(output / "session.json", {"profile": "SYNTHETIC_LOCAL_MVP_V1", "project_id": bundle.project_id,
        "task_id": bundle.task_id, "candidate_run_id": result["run_id"], "candidate_artifact_id": result["artifact_id"]})
    return str(output)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--approved-bundle-sha256")
    parser.add_argument("--authorization-expires-at")
    args = parser.parse_args(argv)
    if args.live:
        require(args.approved_bundle_sha256 is not None and args.authorization_expires_at is not None,
                "EXPLICIT_LIVE_BINDING_REQUIRED")
        result = asyncio.run(run_once(args.output_dir, args.approved_bundle_sha256,
            expires_at=datetime.fromisoformat(args.authorization_expires_at)))
    else:
        require(args.approved_bundle_sha256 is None and args.authorization_expires_at is None,
                "PREPARE_DOES_NOT_ACCEPT_AUTHORIZATION")
        result = prepare(args.output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") in {"PREPARED_PENDING_MOCK", "SUCCESS"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
