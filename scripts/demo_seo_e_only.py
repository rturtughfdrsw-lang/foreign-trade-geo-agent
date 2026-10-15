"""Fixed SYNTHETIC TEST-only E → native Draft → SQLite → Review demonstration.

No provider, customer file, reviewer identity, live flag or authority can be
selected via CLI. The scripted verdict is NOT human review or authorization.
"""
import argparse
import asyncio
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
from uuid import uuid4

from scripts.demo_seo_article import ArticleOpportunity, NOW, TITLE
from scripts.demo_seo_evidence import LocalFetcher, LocalResearch, LocalSearch, NeverDraft, URL, CUSTOMER
from foreign_trade_geo_agent.adapters.retained_intake_plan import RetainedIntakePlanWriter
from foreign_trade_geo_agent.core import change_plan as cp
from foreign_trade_geo_agent.core.content_draft import (
    ContentDraftGeneration, ContentDraftGenerationStatus, ContentDraftStatus,
    _evidence_text, _normalized_text, _validate_numeric_grounding, extract_numeric_expressions,
)
from foreign_trade_geo_agent.core.content_draft_review import ContentDraftReviewRequest, render_draft_body_text
from foreign_trade_geo_agent.core.draft_customer_evidence import DraftCustomerEvidence, DraftCustomerSource, native_scope_digest
from foreign_trade_geo_agent.core.evidence_intake import (
    ArticleScopeCoverage, CustomerContext, CustomerSubmission, EvidenceRequirement, EvidenceSpan, IntakeStatus,
    RequirementDecision, SemanticAssessment, Supplement, SupplementMethod, SupportVerdict,
    require, snapshot_digest, validate_assessment,
)
from foreign_trade_geo_agent.core.history import ArtifactRecord, ArtifactType, RunStatus, WorkflowRun, site_key_from_url
from foreign_trade_geo_agent.core.orchestration import EndToEndRunRequest
from foreign_trade_geo_agent.core.search import SearchResponse, SearchResult, SearchStatus
from foreign_trade_geo_agent.reporting.content_draft_review import content_draft_review_payload, render_content_draft_review_markdown
from foreign_trade_geo_agent.runtime import build_planning_workflow
from foreign_trade_geo_agent.storage.evidence_intake import SQLiteEvidenceIntakeStore
from foreign_trade_geo_agent.storage.serialization import encode_artifact, decode_artifact, _encode, _decode
from foreign_trade_geo_agent.storage.sqlite import SQLiteHistoryReader, SQLiteHistoryStore
from foreign_trade_geo_agent.workflows.change_plan import ChangePlanWorkflow
from foreign_trade_geo_agent.workflows.content_draft import ContentDraftWorkflow
from foreign_trade_geo_agent.workflows.content_draft_review import ContentDraftReviewWorkflow
from foreign_trade_geo_agent.workflows.evidence_intake import EvidenceIntakeWorkflow, EvidenceIntakeDraftAdmission
from foreign_trade_geo_agent.workflows.planning_evidence import PlanningEvidenceWorkflow

FACT = ("SYNTHETIC ONLY: NovaCNC NCX7 spindle rated 7200 rpm continuously under NOVA-TEST-7 protocol "
        "at 20 C on an unloaded bench; applies only to NCX7 and is not a cutting-load or production guarantee.")
DOCUMENT = "SYNTHETIC UTF-8 — fictional engineering note.\n" + FACT + "\nTEST-only fixture; no real customer signoff."
LOCATOR = "synthetic:novacnc/NCX7/spindle-v1.txt#paragraph-2"
GOAL = "SYNTHETIC ONLY: create one English resource explaining spindle performance for export buyers."
BACKGROUND = (
    "Buyers need to evaluate spindle performance, machining tolerance and certification scope.",
    "A spindle rating should be read with its test conditions and intended application.",
    "Ask the supplier to identify the test method, operating duty and scope of any performance statement.",
    "Record the intended workpiece material and cutting application in the enquiry before agreeing acceptance criteria.",
    "Keep source documents beside the enquiry and refer unresolved applicability questions to a qualified reviewer.",
    "A bench test and a production acceptance test address different operating situations.",
    "Request evidence for the intended duty before relying on a rating in a purchasing decision.",
    "Describe the planned cutting cycle, tooling and workpiece in the enquiry, then ask which supporting test records apply to those conditions and which questions still require evaluation.",
    "Keep the rating statement separate from acceptance criteria in the purchasing discussion, so that both parties can review the proposed duty and agree how suitability will be assessed.",
    "Retain the original source, its revision and the agreed scope with the enquiry; resolve any conflicting statements before using a technical parameter in commercial material or an order.",
)


class EOnlySearch(LocalSearch):
    async def search(self, query):
        return SearchResponse(query, SearchStatus.SUCCESS, (SearchResult("spindle performance",
            "https://cnc-guide.example/checklist", "; ".join(("Test conditions and scope", "Buyer enquiry checklist",
            "spindle performance", TITLE, *BACKGROUND[1:])), 1.0),), None)


class EOnlyPlan:
    async def write_change_plan(self, prompt):
        point = next(c for c in prompt.content_point_candidates_for("R1") if c.text == "spindle performance")
        body = {"opportunity_operations": {"R1": {"primary_operation": {
            "source_action_code": "CREATE_SUPPORTING_RESOURCE", "operation_type": "CREATE_NEW_RESOURCE",
            "page_bindings": [{"page_ref": "P1", "suggested_source": True}], "source_refs": ["S1"],
            "resource_purpose": "SUPPORTING_RESOURCE", "proposed_title": TITLE,
            "content_points": [{"intent": "EXPLAIN", "subject_ref": point.candidate_id}],
            "comparison_table_brief": None}, "secondary_operation": None}}}
        return cp.ChangePlanGeneration("synthetic", "fixed-e-only-plan", cp.ChangePlanGenerationStatus.SUCCESS,
            json.dumps(body), None)


class SyntheticEOnlyReviewer:
    """Scripted fixture decision, never an authenticated HUMAN semantic reviewer."""
    def assess(self, snapshot, *, now):
        sources = snapshot.active_evidence
        require(len(sources) == 1 and sources[0].supplement.evidence_id == "E1"
                and sources[0].supplement.content == DOCUMENT
                and sources[0].supplement.source_locator == LOCATOR)
        start = DOCUMENT.index(FACT)
        return SemanticAssessment(snapshot_digest(snapshot), "SYNTHETIC-TEST-REVIEWER-NOT-HUMAN", now,
            (RequirementDecision("F1", SupportVerdict.SUPPORTED,
                "TEST-only scripted decision for fictional parameter and full limitations; no human signoff.",
                (EvidenceSpan("E1", start, start + len(FACT), FACT),)),),
            ArticleScopeCoverage(True, "Legacy synthetic fixture scope assumption, not real semantic proof or human signoff."))


def prepare_test_input(store, project_id, task_id, *, expected_sha256, reviewer, now=NOW):
    """Reload current state; fail closed. This function grants no production purpose."""
    require(type(reviewer) is SyntheticEOnlyReviewer)
    current = store.latest(project_id, task_id)
    require(current.task.project_id == project_id and current.task.task_id == task_id
            and current.task.customer_id == CUSTOMER and current.plan_bound
            and snapshot_digest(current) == expected_sha256
            and current.planning_input.customer_evidence is None)
    check = EvidenceIntakeWorkflow(store, reviewer=reviewer).check(project_id, task_id, now=now)
    require(check.status is IntakeStatus.CANDIDATE_FOR_REVIEW and check.snapshot_sha256 == expected_sha256)
    validate_assessment(current, check.assessment, now)
    records = {e.supplement.evidence_id: e for e in current.active_evidence}
    sources = []
    for decision in check.assessment.decisions:
        require(decision.verdict is SupportVerdict.SUPPORTED)
        for span in decision.spans:
            record = records[span.evidence_id]
            material = record.supplement
            require(material.method is SupplementMethod.TEXT_DOCUMENT)
            sources.append(DraftCustomerSource(material.evidence_id, record.evidence_version,
                material.requirement_ids, material.source_label, material.source_locator,
                material.content, material.file_sha256, span.start, span.end, span.quote))
    value = current.planning_input
    bundle = DraftCustomerEvidence(project_id, CUSTOMER, task_id, current.task.task_version,
        current.plan_version, current.evidence_version, current.revision, expected_sha256,
        native_scope_digest(value.site_content, value.opportunity_report, value.change_plan_report.operations[0]),
        "C1", check.assessment.reviewer_id, check.assessment.reviewed_at,
        "TEST_ONLY_SUPPORTED_NOT_HUMAN_SIGNOFF", tuple(sources))
    require(bundle.fresh_at(now))
    return replace(value, customer_evidence=bundle)


def revalidate_test_input(value, store, *, reviewer, now=NOW):
    bundle = value.customer_evidence
    require(bundle is not None and bundle.fresh_at(now))
    fresh = prepare_test_input(store, bundle.project_id, bundle.task_id,
        expected_sha256=bundle.snapshot_sha256, reviewer=reviewer, now=now)
    # Compare against freshly reconstructed trusted-side state, not self-reported hash/state.
    require(fresh == value)


class FixedEOnlyWriter:
    """One complete, hand-written native article JSON. No model transport."""
    def __init__(self):
        self.calls = 0
        self.output = None

    async def write_content_draft(self, prompt):
        self.calls += 1
        require(prompt.input.customer_evidence is not None)
        headings = prompt.operation.new_resource_spec.outline_headings
        def claim(text, kind, p=(), s=(), e=()):
            return dict(text=text, claim_type=kind, page_refs=list(p), source_refs=list(s), customer_refs=list(e))
        claims = [claim("Use this guide to prepare an enquiry and keep the supporting records together.", "EDITORIAL_TRANSITION"),
            claim(BACKGROUND[0], "GENERAL_TECHNICAL_CONTEXT", ("P1",)),
            claim(FACT, "OBSERVED_PRODUCT_FACT", e=("E1",)),
            *(claim(t, "GENERAL_TECHNICAL_CONTEXT", s=("S1",)) for t in BACKGROUND[1:]),
            claim("Prepare an enquiry and request the applicable supporting records before proceeding.", "CALL_TO_ACTION")]
        body = {"draft": {"change_ref": "C1", "draft_type": "NEW_RESOURCE_DRAFT", "sections": [
            {"outline_heading": headings[0], "blocks": [
                {"kind": "PARAGRAPH", "claims": claims[:2]},
                {"kind": "PARAGRAPH", "claims": claims[2:6]}]},
            {"outline_heading": headings[1], "blocks": [
                {"kind": "PARAGRAPH", "claims": claims[6:10]},
                {"kind": "PARAGRAPH", "claims": claims[10:]}]}]}}
        self.output = json.dumps(body)
        return ContentDraftGeneration("synthetic", "fixed-e-only-writer-not-model",
            ContentDraftGenerationStatus.SUCCESS, self.output, None)


async def run_test_candidate(value, store, *, reviewer, writer, now=NOW):
    require(type(writer) is FixedEOnlyWriter)
    revalidate_test_input(value, store, reviewer=reviewer, now=now)
    report = await ContentDraftWorkflow(writer).run(value)
    revalidate_test_input(value, store, reviewer=reviewer, now=now)
    require(report.status is ContentDraftStatus.SUCCESS and writer.calls == 1)
    return report


def prepare(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    def save(name, value):
        (directory / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    db = directory / "history.sqlite3"
    never = NeverDraft()
    initial = asyncio.run(build_planning_workflow(db, fetcher=LocalFetcher(), search_provider=EOnlySearch(),
        research_writer=LocalResearch(), content_opportunity_writer=ArticleOpportunity(),
        change_plan_writer=EOnlyPlan(), content_draft_writer=never).run(EndToEndRunRequest(URL, GOAL)))
    require(initial.terminal_report.error == "INTAKE_EXECUTION_BLOCKED" and never.calls == 0)
    plan_id = next(a.artifact_id for a in initial.artifacts if a.artifact_type is ArtifactType.CHANGE_PLAN)
    intake_store = SQLiteEvidenceIntakeStore.create(directory / "intake.sqlite3")
    intake = EvidenceIntakeWorkflow(intake_store)
    planning = PlanningEvidenceWorkflow(SQLiteHistoryReader(db), intake)
    original = planning.register(initial.run.run_id, plan_id, customer_id=CUSTOMER,
        requirements=(EvidenceRequirement("F1", 0, "Spindle parameter, exact model, duty, test conditions and limitations",
            "Include the complete reviewed parameter statement without dropping its scope",
            "P/S provide background only and contain no customer spindle parameter.", (SupplementMethod.TEXT_DOCUMENT,)),))
    project = original.task.project_id
    save("01-missing-evidence.json", asdict(intake.customer_request(project, plan_id, now=NOW)))
    supplement = Supplement("E1", ("F1",), SupplementMethod.TEXT_DOCUMENT, DOCUMENT,
        "SYNTHETIC NovaCNC UTF-8 engineering note", LOCATOR, "FICTIONAL NovaCNC", hashlib.sha256(DOCUMENT.encode()).hexdigest())
    submission = CustomerSubmission("SYNTHETIC-E-ONLY-SUBMISSION", snapshot_digest(original), (supplement,))
    save("submission.json", asdict(submission))
    # Preserve the exact UTF-8 bytes hashed by Intake, including LF on Windows.
    (directory / "customer-E1.txt").write_bytes(DOCUMENT.encode("utf-8"))
    submitted = intake.submit(project, plan_id, submission, customer=CustomerContext(CUSTOMER, "SYNTHETIC-CUSTOMER", NOW))
    candidate = asyncio.run(planning.recheck(project, plan_id, expected_sha256=snapshot_digest(submitted),
        current=submitted, planner=ChangePlanWorkflow(RetainedIntakePlanWriter()), now=NOW))
    save("02-unreviewed-intake.json", asdict(candidate))
    digest = snapshot_digest(candidate.snapshot)
    reviewer = SyntheticEOnlyReviewer()
    value = prepare_test_input(intake_store, project, plan_id, expected_sha256=digest, reviewer=reviewer)
    encoded_input = _encode(value)
    require(_decode(encoded_input, type(value)) == value)
    save("03-native-input.json", encoded_input)
    guarded = ContentDraftWorkflow(never, intake_admission=EvidenceIntakeDraftAdmission(
        intake_store, project, plan_id, expected_snapshot_sha256=digest))
    require(asyncio.run(guarded.run(value)).error == "INTAKE_EXECUTION_BLOCKED" and never.calls == 0)
    ps_text = json.dumps([asdict(value.site_content), asdict(value.opportunity_report)], default=str)
    require(all(t not in ps_text for t in (FACT, "7200 rpm", "NOVA-TEST-7", "NCX7")))
    writer = FixedEOnlyWriter()
    report = asyncio.run(run_test_candidate(value, intake_store, reviewer=reviewer, writer=writer))
    save("04-writer-output.json", json.loads(writer.output))
    raw = encode_artifact(ArtifactType.CONTENT_DRAFT, report)
    require(decode_artifact(ArtifactType.CONTENT_DRAFT, 1, raw) == report)
    (directory / "05-content-draft.json").write_text(raw, encoding="utf-8")
    run_id, artifact_id = str(uuid4()), str(uuid4())
    history = SQLiteHistoryStore(db)
    history.create_run(WorkflowRun(run_id, site_key_from_url(URL), "synthetic_e_only_native_draft_TEST_ONLY",
        NOW, None, RunStatus.RUNNING, None, None))
    original_reader = SQLiteHistoryReader(db)
    for ref in initial.artifacts:
        if ref.artifact_type is ArtifactType.CONTENT_DRAFT:
            continue
        artifact = original_reader.get_artifact(ref.artifact_id)
        payload = value.change_plan_report if ref.artifact_type is ArtifactType.CHANGE_PLAN else artifact.payload
        history.append_artifact(ArtifactRecord(str(uuid4()), run_id, ref.artifact_type, 1, NOW, payload))
    history.append_artifact(ArtifactRecord(artifact_id, run_id, ArtifactType.CONTENT_DRAFT, 1, NOW, report))
    history.finish_run(run_id, status=RunStatus.SUCCEEDED, completed_at=NOW)
    reopened = SQLiteHistoryReader(db).get_artifact(artifact_id).payload
    require(reopened == report)
    view = ContentDraftReviewWorkflow(history_reader=SQLiteHistoryReader(db)).review(
        ContentDraftReviewRequest(run_id, artifact_id, "D1"))
    markdown = render_content_draft_review_markdown(view)
    require(FACT in markdown and LOCATOR in markdown and "TEST_ONLY_SUPPORTED_NOT_HUMAN_SIGNOFF" in markdown)
    (directory / "article-review.md").write_text(markdown, encoding="utf-8")
    save("06-review.json", content_draft_review_payload(view))
    pages = {p.evidence_id: p for p in value.site_content.pages}
    external = {s.source_id: s for s in value.opportunity_report.source_materials}
    customer_sources = {s.evidence_id: s for s in value.customer_evidence.sources}
    bindings = []
    for claim in view.draft.claims:
        require(all(r in pages for r in claim.page_refs) and all(r in external for r in claim.source_refs)
                and all(r in customer_sources for r in claim.customer_refs))
        first_party = " ".join([*(_evidence_text(pages[r]) for r in claim.page_refs),
            *(_normalized_text(customer_sources[r].quote) for r in claim.customer_refs)])
        bindings.append({"claim_id": claim.claim_id, "text": claim.text,
            "P": [{"ref": r, "url": pages[r].final_url, "observed_body": pages[r].body_text} for r in claim.page_refs],
            "S": [{"ref": r, "content": external[r].content, "status": "UNVERIFIED_EXTERNAL_CONTEXT"} for r in claim.source_refs],
            "E": [asdict(customer_sources[r]) for r in claim.customer_refs],
            "source_existence_and_scope": "PASS", "numeric_expressions": extract_numeric_expressions(claim.text),
            "numeric_lexical_check": "PASS" if not extract_numeric_expressions(claim.text) or
                _validate_numeric_grounding(claim.text, first_party) is None else "FAIL",
            "article_review_status": "UNREVIEWED", "semantic_truth_automatically_proved": False})
    require(all(b["numeric_lexical_check"] == "PASS" for b in bindings))
    save("07-evidence-binding.json", {"checks": "Existence, frozen scope, exact quote and numeric preservation only",
        "customer_review": value.customer_evidence.review_status, "claims": bindings})
    manifest = {"profile": "SYNTHETIC TEST ONLY / NOT HUMAN SIGNOFF / NO PRODUCTION AUTHORITY",
        "project_id": project, "task_id": plan_id, "run_id": run_id, "artifact_id": artifact_id,
        "native_pipeline": "Parser → Validator/Finalizer → SQLite reopen → native Markdown Review",
        "native_draft_sha256": hashlib.sha256(raw.encode()).hexdigest(),
        "article_body_sha256": hashlib.sha256(render_draft_body_text(report.drafts[0]).encode()).hexdigest(),
        "writer_calls": writer.calls, "production_writer_calls": never.calls,
        "sqlite_reopen_equal": reopened == report, "e_only_fact_absent_from_ps": True,
        "claims": [asdict(c) for c in view.draft.claims], "customer_binding": asdict(value.customer_evidence),
        "draft_authorized": False, "human_review": "UNREVIEWED", "production_gate": "BLOCKED",
        "postgresql": "BLOCKED", "real_model_calls": 0, "wordpress_writes": 0,
        "word_count": sum(len(c.text.split()) for c in view.draft.claims), "result": "OFFLINE_ENGINEERING_PASS"}
    save("verification.json", manifest)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.output_dir)
    print(json.dumps({k: result[k] for k in ("result", "run_id", "artifact_id", "writer_calls", "word_count")}, indent=2))
