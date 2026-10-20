"""Isolated NovaCNC article experiment. Default CLI prepares OFFLINE only.

Never imported by production. --live additionally requires fresh human consent
in the chat, the frozen bundle digest and an explicit authorization expiry.
A digest/flag is a binding check, not evidence of human or production approval.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory
from uuid import uuid4

import httpx

from scripts import demo_seo_article as fixture
from foreign_trade_geo_agent.adapters.deepseek_content_draft import (
    DeepSeekContentDraftWriter, content_draft_request_payload,
)
from foreign_trade_geo_agent.core import content_draft as cd
from foreign_trade_geo_agent.core.content_draft_review import ContentDraftReviewRequest
from foreign_trade_geo_agent.core.history import ArtifactRecord, ArtifactType, RunStatus, WorkflowRun
from foreign_trade_geo_agent.core.orchestration import EndToEndRunRequest
from foreign_trade_geo_agent.reporting.content_draft_review import render_content_draft_review_markdown
from foreign_trade_geo_agent.runtime import build_planning_workflow
from foreign_trade_geo_agent.storage.serialization import decode_artifact, encode_artifact
from foreign_trade_geo_agent.storage.sqlite import SQLiteHistoryReader, SQLiteHistoryStore
from foreign_trade_geo_agent.workflows.content_draft import _parse_specification
from foreign_trade_geo_agent.workflows.content_draft_review import ContentDraftReviewWorkflow

ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = "https://api.deepseek.com/chat/completions"
MAX_REQUEST_BYTES = 16_000
MAX_RESPONSE_BYTES = 65_536
TIMEOUT_SECONDS = 60.0
OFFLINE_KEY = "OFFLINE-ARTICLE-PLACEHOLDER"
INPUT_FILES = {
    ArtifactType.SITE_CONTENT: "site-content.json",
    ArtifactType.CONTENT_OPPORTUNITY: "opportunities.json",
    ArtifactType.CHANGE_PLAN: "change-plan.json",
}
EXPERIMENT_INSTRUCTIONS = """
ISOLATED SYNTHETIC ARTICLE EXPERIMENT: write one complete English buyer guide using the supplied native NEW_RESOURCE_DRAFT contract and exact approved title/outline. This is fictional NovaCNC P/S material, not customer E-only evidence or production authority.
Serve a buyer preparing a machining-center enquiry: explain what the stated spindle rating and tolerance do and do not establish, how test applicability affects an enquiry, and how to check certificate scope. Include an opening, connected explanatory paragraphs, practical evidence requests, and a restrained closing CTA. Place certification discussion within the second approved section; do not add headings or metadata.
Preserve ALL facts, identifiers, conditions and exclusions in experiment_requirements, attached to the relevant facts. Do not omit required facts to fit budgets. Do not invent technical mechanisms, parameters, benefits or promises. Use your own explanatory wording where evidence supports it; preserve numeric expressions verbatim. Avoid observed-topic/meta-analysis prose and redundant restatement of evidence. Do not copy the source prose into a list and call it an article. Keep the native budgets, especially 16 claims total, 8 blocks total and 300 characters per paragraph claim. If you cannot cover the task, do not conceal the conflict by dropping qualifications.
"""


def canonical(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write_json(path, value):
    pending = path.with_name(path.name + ".pending")
    save_bytes(pending, canonical(value))
    os.replace(pending, path)


def require(condition, category):
    if not condition:
        raise ValueError(category)


def code_hashes():
    paths = list((ROOT / "src/foreign_trade_geo_agent").rglob("*.py"))
    paths += [Path(__file__).resolve(), ROOT / "scripts/demo_seo_article.py",
              ROOT / "scripts/demo_seo_evidence.py", ROOT / "scripts/local_env.py"]
    return {p.relative_to(ROOT).as_posix(): sha(p.read_bytes()) for p in sorted(paths)}


async def fixture_input():
    # Production planning stops at its unchanged Gate. No TEST admission,
    # customer E intake, real writer, crawl, search or provider is used.
    with TemporaryDirectory() as temporary:
        db = Path(temporary) / "history.sqlite3"
        never = fixture.NeverDraft()
        result = await build_planning_workflow(db, **fixture.ports(never)).run(
            EndToEndRunRequest(fixture.URL, fixture.GOAL))
        require(result.terminal_report.error == "INTAKE_EXECUTION_BLOCKED" and never.calls == 0,
                "PRODUCTION_GATE_CHANGED")
        reader = SQLiteHistoryReader(db)
        artifacts = {a.artifact_type: reader.get_artifact(a.artifact_id).payload for a in result.artifacts}
        return cd.ContentDraftInput(*(artifacts[kind] for kind in INPUT_FILES))


def requirements():
    return {
        "project_id": "SYNTHETIC-NOVACNC",
        "task_id": "SYNTHETIC-NOVACNC-ARTICLE-001",
        "goal": fixture.GOAL,
        "search_intent": "Prepare a machining-center buyer enquiry by understanding spindle test applicability, tolerance test applicability and certificate scope.",
        "mandatory_facts_and_qualifiers": list(fixture.FACTS),
        "buyer_questions": [
            "Does a continuous spindle rating under the stated test conditions establish cutting-load performance?",
            "Does the aluminum test-piece tolerance apply to another material or production conditions?",
            "Which original certificate, issuer, model, standard and validity information should the buyer check?",
        ],
        "scope": "SYNTHETIC P/S ONLY; no customer E-only generation validation",
    }


def request_for(value):
    require(cd.stable_content_draft_input_error(value) is None, "NATIVE_INPUT_INVALID")
    require(value.target_language == "en" and len(value.change_plan_report.operations) == 1,
            "SINGLE_ENGLISH_ARTICLE_REQUIRED")
    operation = value.change_plan_report.operations[0]
    require(operation.operation_type.value == "CREATE_NEW_RESOURCE", "CREATE_REQUIRED")
    native = cd.build_content_draft_prompt(value, operation.change_id).material_json()
    material = json.loads(native)
    material["experiment_requirements"] = requirements()
    user = canonical(material).decode()
    system = DeepSeekContentDraftWriter.build_system_prompt() + EXPERIMENT_INSTRUCTIONS
    payload = content_draft_request_payload(system, user)
    # Historical short-article experiment retains its separate 3000-token cap.
    payload["max_tokens"] = 3000
    raw = canonical(payload)
    require(payload["model"] == "deepseek-flash" and payload["max_tokens"] == 3000
            and payload["thinking"] == {"type": "disabled"} and payload["temperature"] == 0,
            "REQUEST_CONFIG_CHANGED")
    require(len(system) <= cd.MAX_SYSTEM_PROMPT_CHARS
            and len(system.encode()) <= cd.MAX_SYSTEM_PROMPT_BYTES
            and len(user) <= cd.MAX_USER_MATERIAL_CHARS and len(user.encode()) <= cd.MAX_USER_MATERIAL_BYTES
            and len(raw) <= min(MAX_REQUEST_BYTES, cd.MAX_INPUT_ENVELOPE_BYTES)
            and len(raw.decode()) <= cd.MAX_INPUT_ENVELOPE_CHARS, "INPUT_BUDGET_CONFLICT")
    # Ensure the FULL mandatory fact strings occur in the native P material,
    # independently of the instruction ledger. E is never relabelled as P/S.
    pages = canonical(material["pages"]).decode()
    require(all(fact in pages for fact in fixture.FACTS), "REQUIRED_PS_FACT_MISSING")
    return payload, native


def validate_candidate(value, text):
    operation = value.change_plan_report.operations[0]
    spec = _parse_specification(text, expected_change_ref=operation.change_id, operation=operation)
    require(spec.draft_type is cd.ContentDraftType.NEW_RESOURCE_DRAFT, "NEW_RESOURCE_REQUIRED")
    opportunity = value.opportunity_report.opportunities[0]
    draft, error = cd.finalize_draft_item(1, spec, operation, opportunity,
                                        value.site_content, value.opportunity_report)
    require(error is None and draft is not None, error or "NATIVE_VALIDATION_FAILED")
    return cd.ContentDraftReport(cd.ContentDraftStatus.SUCCESS, (draft,), cd.CONTENT_DRAFT_LIMITATIONS, None)


def quality_checklist():
    return {
        "decision": "PENDING_REAL_MODEL_AND_INDEPENDENT_HUMAN_REVIEW",
        "scope": requirements()["scope"],
        "required_facts": [{"fact_and_all_qualifiers": fact, "source_ref": "P1",
                            "source_file": "native-material.json", "claim_ids": [], "decision": "UNREVIEWED",
                            "reason": ""} for fact in fixture.FACTS],
        "checks": [{"check": check, "decision": "UNREVIEWED", "claim_ids_or_paragraphs": [], "reason": ""}
                   for check in (
                       "Native complete article, approved title and both sections; not a fragment",
                       "Every fact, condition and exclusion covered with supporting P/S attribution",
                       "Reverse-check every claim for invented parameters, relationships or marketing promises",
                       "Answers all frozen buyer questions and the search intent",
                       "Natural paragraph transitions, opening and closing",
                       "Explains applicability and practical buyer decisions, not merely observed topics",
                       "Compare against P/S sentence by sentence for excessive copying or repetition; immutable numbers are not originality evidence",
                       "Persisted native artifact reopens unchanged and exports Markdown",
                   )],
        "note": "Schema success and citation/keyword presence do not establish semantic coverage or writing quality. Review the article independently from the handwritten mock witness.",
    }


def prepare(directory):
    require(not directory.exists(), "OUTPUT_MUST_BE_NEW")
    value = asyncio.run(fixture_input())
    payload, native = request_for(value)
    # A local capacity witness only, NEVER supplied as model response in live mode.
    witness = asyncio.run(fixture.FixedArticleWriter().write_content_draft(
        cd.build_content_draft_prompt(value, "C1")))
    report = validate_candidate(value, witness.text)
    body = " ".join(c.text for b in report.drafts[0].blocks for c in
                    (b.claims if hasattr(b, "claims") else b.items))
    require(all(fact in body for fact in fixture.FACTS), "FACT_COVERAGE_BUDGET_CONFLICT")
    directory.mkdir(parents=True)
    for kind, name in INPUT_FILES.items():
        field = {ArtifactType.SITE_CONTENT: value.site_content,
                 ArtifactType.CONTENT_OPPORTUNITY: value.opportunity_report,
                 ArtifactType.CHANGE_PLAN: value.change_plan_report}[kind]
        (directory / name).write_text(encode_artifact(kind, field), encoding="utf-8")
    (directory / "request.json").write_bytes(canonical(payload))
    (directory / "system-prompt.txt").write_text(payload["messages"][0]["content"], encoding="utf-8")
    (directory / "user-material.json").write_bytes(payload["messages"][1]["content"].encode())
    (directory / "native-material.json").write_bytes(native.encode())
    write_json(directory / "quality-checklist.json", quality_checklist())
    summary = {
        "status": "READY", "scope": requirements()["scope"], "real_requests": 0,
        "endpoint": ENDPOINT, "method": "POST", "model": payload["model"],
        "thinking": payload["thinking"], "temperature": 0, "max_output_tokens": 3000,
        "timeout_seconds": TIMEOUT_SECONDS, "max_requests": 1, "automatic_retries": 0,
        "redirects": False, "trust_env": False, "request_utf8_bytes": len(canonical(payload)),
        "max_request_bytes": MAX_REQUEST_BYTES, "max_response_bytes": MAX_RESPONSE_BYTES,
        "native_output_max_chars": cd.MAX_RAW_OUTPUT_CHARS, "native_output_max_bytes": cd.MAX_RAW_OUTPUT_BYTES,
        "max_blocks": cd.MAX_BLOCKS_PER_DRAFT, "max_claims": cd.MAX_CLAIMS_PER_DRAFT,
        "max_claim_chars": cd.MAX_CLAIM_CHARS,
        "outline": list(value.change_plan_report.operations[0].new_resource_spec.outline_headings),
        "request_sha256": sha(canonical(payload)), "production_gate": "INTAKE_EXECUTION_BLOCKED",
        "production_writer_calls": 0, "production_authorized": False, "wordpress_authorized": False,
        "model_quality": "NOT_TESTED", "authorization": "REQUIRED_BEFORE_LIVE",
        "capacity_witness": {"handwritten_not_model": True, "claims": 14, "blocks": 5,
                             "all_qualifiers": True, "provider_text_bytes": len(witness.text.encode()),
                             "token_fit": "NOT_TOKENIZER_VERIFIED; no demonstrated structural conflict; live length failure stops"},
        "fee_limit": "One request and token/input caps only; no provider-side monetary cap or billing estimate asserted.",
    }
    write_json(directory / "preflight.json", summary)
    manifest = {"files": {p.name: sha(p.read_bytes()) for p in sorted(directory.iterdir())},
                "code": code_hashes()}
    write_json(directory / "bundle.json", manifest)
    (directory / "bundle.sha256").write_text(sha(canonical(manifest)) + "\n", encoding="ascii")
    return summary | {"bundle_sha256": sha(canonical(manifest))}


def load_frozen(directory, expected_digest):
    raw = (directory / "bundle.json").read_bytes()
    require(sha(raw) == expected_digest, "BUNDLE_CHANGED")
    manifest = json.loads(raw)
    require(manifest["code"] == code_hashes(), "EXPERIMENT_CODE_CHANGED")
    require(all(Path(name).name == name and sha((directory / name).read_bytes()) == digest
                for name, digest in manifest["files"].items()), "FROZEN_INPUT_CHANGED")
    value = cd.ContentDraftInput(*(decode_artifact(kind, 1, (directory / name).read_text(encoding="utf-8"))
                                  for kind, name in INPUT_FILES.items()))
    payload, _ = request_for(value)
    request = (directory / "request.json").read_bytes()
    require(request == canonical(payload), "FROZEN_REQUEST_CHANGED")
    return value, request


from foreign_trade_geo_agent.adapters.retained_deepseek import (
    OneShotTransport, restrict_directory, save_bytes, contains_secret, retain_response, receive_candidate,
)


def validation_detail(value, text, category):
    """Text-free locations/counts; exact rejected text lives only in local files."""
    detail = {"category": category, "max_claims": cd.MAX_CLAIMS_PER_DRAFT,
              "max_blocks": cd.MAX_BLOCKS_PER_DRAFT}
    try:
        body = json.loads(text)
    except json.JSONDecodeError as exc:
        return detail | {"line": exc.lineno, "column": exc.colno, "offset": exc.pos}
    if type(body) is not dict or type(body.get("draft")) is not dict:
        return detail
    draft = body["draft"]
    sections = draft.get("sections", [])
    if type(sections) is not list:
        return detail
    blocks = [block for section in sections if type(section) is dict
              and type(section.get("blocks")) is list for block in section["blocks"]]
    claims = [claim for block in blocks if type(block) is dict
              for name in ("claims", "items") if type(block.get(name)) is list for claim in block[name]]
    detail.update(block_count=len(blocks), claim_count=len(claims))
    detail["customer_reference_fields"] = [
        {"claim_index": index, "refs": [r for r in claim.get("customer_refs", [])
         if type(r) is str and re.fullmatch(r"E[1-9][0-9]{0,2}", r)]}
        for index, claim in enumerate(claims) if type(claim) is dict
        and type(claim.get("customer_refs")) is list and claim["customer_refs"]]
    if category == "NUMERIC_NOT_GROUNDED":
        spec = _parse_specification(text, expected_change_ref="C1", operation=value.change_plan_report.operations[0])
        violation = cd.describe_numeric_grounding_violation(1, spec, cd.build_content_draft_prompt(value, "C1"))
        if violation is not None:
            detail.update({name: getattr(violation, name) for name in (
                "field_path", "rule_id", "source_namespace", "grounded_count", "ungrounded_count")})
    return detail


async def _candidate(value, raw_request, transport, key, *, output, metadata, validator=None):
    return await receive_candidate(value, raw_request, transport, key, output=output, metadata=metadata,
        validator=validator or validate_candidate, detail=validation_detail, timeout=TIMEOUT_SECONDS,
        response_limit=MAX_RESPONSE_BYTES)


def persist_candidate(directory, value, report, text, *, is_mock,
                      workflow_name="isolated_article_experiment", scope="SYNTHETIC P/S",
                      checklist=None):
    store = SQLiteHistoryStore(directory / "history.sqlite3")
    run_id, artifact_id, now = str(uuid4()), str(uuid4()), datetime.now(UTC)
    store.create_run(WorkflowRun(run_id, "https://novacnc.example:443", workflow_name,
                                now, None, RunStatus.RUNNING, None, None))
    for kind, payload in ((ArtifactType.SITE_CONTENT, value.site_content),
                          (ArtifactType.CONTENT_OPPORTUNITY, value.opportunity_report),
                          (ArtifactType.CHANGE_PLAN, value.change_plan_report),
                          (ArtifactType.CONTENT_DRAFT, report)):
        store.append_artifact(ArtifactRecord(artifact_id if kind is ArtifactType.CONTENT_DRAFT else str(uuid4()),
                                            run_id, kind, 1, now, payload))
    store.finish_run(run_id, status=RunStatus.SUCCEEDED, completed_at=datetime.now(UTC))
    reader = SQLiteHistoryReader(directory / "history.sqlite3")
    require(reader.get_artifact(artifact_id).payload == report, "PERSISTENCE_MISMATCH")
    view = ContentDraftReviewWorkflow(history_reader=reader).review(ContentDraftReviewRequest(run_id, artifact_id, "D1"))
    (directory / "article-preview.md").write_text(
        ("> MOCK — hand-written fixture response, NOT a real model article.\n" if is_mock else "")
        + f"> ISOLATED {scope} CANDIDATE — independent human quality review pending.\n\n"
        + render_content_draft_review_markdown(view), encoding="utf-8")
    require((directory / "model-output.txt").read_bytes() == text.encode("utf-8"), "PERSISTENCE_MISMATCH")
    (directory / "content-draft.json").write_text(encode_artifact(ArtifactType.CONTENT_DRAFT, report), encoding="utf-8")
    write_json(directory / "quality-review.json", checklist or quality_checklist())
    require(store.list_wordpress_attempts(run_id) == (), "WORDPRESS_SIDE_EFFECT")
    return {"run_id": run_id, "artifact_id": artifact_id}


async def run_once(directory, digest, *, mock_transport=None, expires_at=None, experiment=None):
    # Optional isolated driver; never used by production runtime or its Gate.
    loader = load_frozen if experiment is None else experiment.load_frozen
    persister = persist_candidate if experiment is None else experiment.persist_candidate
    value, request = loader(directory, digest)
    offline = mock_transport is not None
    if offline:
        require(type(mock_transport) is httpx.MockTransport, "MOCK_TRANSPORT_REQUIRED")
        output = directory / ("mock-" + uuid4().hex)
    else:
        require(type(expires_at) is datetime and expires_at.tzinfo is not None
                and datetime.now(UTC) < expires_at, "LIVE_AUTHORIZATION_EXPIRED_OR_MISSING")
        # Human authorization is supplied in the chat before this mode is used.
        # Reserve BEFORE credentials/transport/network; failure/crash consumes it.
        output = directory / "live-attempt"
    metadata = {"mode": "MOCK" if offline else "LIVE", "real_requests": 0, "request_count": 0,
                "status": "FAILED", "quality": "UNREVIEWED", "wordpress_attempts": 0,
                "production_authorized": False, "model_generated": False,
                "output": str(output), "bundle_sha256": digest, "request_sha256": sha(request),
                "http_status": None, "usage": None, "finish_reason": None,
                "response_state": "NO_RESPONSE", "response_saved": False,
                "response_complete": False, "failure_stage": "attempt_reservation"}
    # An existing attempt is never touched, even to write an error report.
    try:
        output.mkdir()
    except FileExistsError:
        raise
    except OSError:
        return metadata | {"status": "INCOMPLETE", "error": "PERSISTENCE_FAILED"}
    guard = None
    try:
        metadata["failure_stage"] = "attempt_persistence"
        restrict_directory(output)
        write_json(output / "started.json", {"bundle_sha256": digest, "request_sha256": sha(request),
            "expires_at": None if offline else expires_at.isoformat(), "automatic_retries": 0,
            "status": "STARTED_INCOMPLETE_UNTIL_DIAGNOSTICS", "mode": metadata["mode"]})
        key, inner = OFFLINE_KEY, mock_transport
        if not offline:
            metadata["failure_stage"] = "credentials"
            from scripts.local_env import load_api_keys
            try:
                load_api_keys("DEEPSEEK_API_KEY", project_root=ROOT)
                key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
                require(bool(key), "MISSING_KEY")
            except Exception:
                raise ValueError("CREDENTIALS_UNAVAILABLE") from None
            inner = httpx.AsyncHTTPTransport(retries=0, trust_env=False)
        guard = OneShotTransport(inner, request, expires_at=None if offline else expires_at)
        candidate = _candidate(value, request, guard, key, output=output, metadata=metadata,
                               validator=None if experiment is None else experiment.validate_candidate)
        report, text, usage = await asyncio.wait_for(candidate, TIMEOUT_SECONDS)
        metadata["failure_stage"] = "binding_revalidation"
        latest, _ = loader(directory, digest)  # No stale input/code exported after await.
        if experiment is not None:
            experiment.revalidate_execution(value, latest)
        if not offline:
            require(datetime.now(UTC) < expires_at, "LIVE_AUTHORIZATION_EXPIRED_OR_MISSING")
        persistence_options = {} if experiment is None else {"after_review": latest.customer_evidence}
        metadata["failure_stage"] = "candidate_persistence"
        metadata.update(persister(output, value, report, text, is_mock=offline, **persistence_options),
                        status="SUCCESS", model_generated=not offline, usage=usage)
        metadata["failure_stage"] = None
    except Exception as exc:
        allowed = {c.value for c in cd.ContentDraftValidationCategory} | {
            "NEW_RESOURCE_REQUIRED", "NATIVE_VALIDATION_FAILED", "PROVIDER_HTTP_FAILURE", "RESPONSE_BUDGET_EXCEEDED",
            "SECRET_OUTPUT_REFUSED", "PROVIDER_ENVELOPE_INVALID", "OUTPUT_INCOMPLETE", "FROZEN_INPUT_CHANGED",
            "BUNDLE_CHANGED", "EXPERIMENT_CODE_CHANGED", "LIVE_AUTHORIZATION_EXPIRED_OR_MISSING",
            "PROVIDER_JSON_FORMAT", "CREDENTIALS_UNAVAILABLE", "ENCODED_RESPONSE_REFUSED"}
        if metadata["failure_stage"] in {"attempt_persistence", "response_persistence", "model_text_persistence",
                "rejected_candidate_persistence", "candidate_persistence"} and str(exc) != "SECRET_OUTPUT_REFUSED":
            metadata.update(status="INCOMPLETE", error="PERSISTENCE_FAILED")
        elif isinstance(exc, (TimeoutError, httpx.TimeoutException)):
            metadata["error"] = "REQUEST_TIMEOUT"
        elif isinstance(exc, httpx.RequestError):
            metadata["error"] = "REQUEST_DISCONNECTED"
        else:
            metadata["error"] = str(exc) if type(exc) is ValueError and str(exc) in allowed else "REQUEST_OR_VALIDATION_FAILED"
    metadata.update(request_count=0 if guard is None else guard.calls,
                    real_requests=0 if offline or guard is None else guard.calls)

    def discard_incomplete_candidate():
        # These files belong exclusively to this newly reserved attempt.
        # A partially exported candidate must not be opened as a valid Draft.
        metadata.pop("run_id", None)
        metadata.pop("artifact_id", None)
        metadata["model_generated"] = False
        for name in ("content-draft.json", "history.sqlite3", "article-preview.md"):
            try:
                (output / name).unlink(missing_ok=True)
            except OSError:
                metadata["candidate_cleanup_failed"] = True

    if metadata["status"] == "INCOMPLETE":
        discard_incomplete_candidate()
    try:
        write_json(output / "diagnostics.json", metadata)
    except Exception:
        metadata.update(status="INCOMPLETE", error="PERSISTENCE_FAILED", failure_stage="diagnostics_persistence")
        discard_incomplete_candidate()
    return metadata


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
    return 0 if result.get("status") in {"READY", "SUCCESS"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
