"""SYNTHETIC NovaCNC single-article fixture, NOT a model-authored draft.

Only the existing isolated TEST composition runs the fixed article writer.
Production and intake Draft admission continue to refuse execution. There is
no provider selector, credential loading, customer input or delivery option.
"""
import argparse
import asyncio
from dataclasses import asdict
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path

from scripts.demo_seo_evidence import (
    CUSTOMER, FACTS as SECTION_FACTS, SUBJECTS, URL, LocalFetcher, LocalSearch, LocalResearch, NeverDraft,
)
from foreign_trade_geo_agent.adapters.retained_intake_plan import RetainedIntakePlanWriter
from foreign_trade_geo_agent.core import change_plan as cp
from foreign_trade_geo_agent.core.content_draft import ContentDraftGeneration, ContentDraftGenerationStatus
from foreign_trade_geo_agent.core.content_draft_review import ContentDraftReviewRequest
from foreign_trade_geo_agent.core.content_opportunity import ContentOpportunityGeneration, ContentOpportunityGenerationStatus
from foreign_trade_geo_agent.core.evidence_intake import (
    ArticleScopeCoverage, CustomerContext, CustomerSubmission, EvidenceRequirement, EvidenceSpan, EvidenceTask,
    IntakeStatus, RequirementDecision, SemanticAssessment, Supplement, SupplementMethod,
    SupportVerdict, require, snapshot_digest,
)
from foreign_trade_geo_agent.core.history import ArtifactType
from foreign_trade_geo_agent.core.orchestration import EndToEndRunRequest
from foreign_trade_geo_agent.reporting.content_draft_review import (
    content_draft_review_payload, render_content_draft_review_markdown,
)
from foreign_trade_geo_agent.reporting.evidence_intake import planning_review_json
from foreign_trade_geo_agent.runtime import build_isolated_test_planning_workflow, build_planning_workflow
from foreign_trade_geo_agent.storage.evidence_intake import SQLiteEvidenceIntakeStore
from foreign_trade_geo_agent.storage.serialization import encode_artifact
from foreign_trade_geo_agent.storage.sqlite import SQLiteHistoryReader
from foreign_trade_geo_agent.workflows.change_plan import ChangePlanWorkflow
from foreign_trade_geo_agent.workflows.content_draft import ContentDraftWorkflow
from foreign_trade_geo_agent.workflows.content_draft_review import ContentDraftReviewWorkflow
from foreign_trade_geo_agent.workflows.evidence_intake import EvidenceIntakeDraftAdmission, EvidenceIntakeWorkflow
from foreign_trade_geo_agent.workflows.planning_evidence import PlanningEvidenceWorkflow

NOW = datetime(2026, 10, 10, 6, 0, tzinfo=UTC)
FACTS = tuple(fact.replace("DEMO-TEST-2;", "DEMO-TEST-2 protocol;") for fact in SECTION_FACTS)
TITLE = "NovaCNC machining center buyer guide"
GOAL = "SYNTHETIC ONLY: create one English buyer guide explaining spindle performance, machining tolerance and certification scope."

# Hand-written fixture statements, deliberately retained with full qualifiers.
# P1 independently contains these statements in the SYNTHETIC site fixture.
# E1-E3 remain attributed customer documents; they are never relabelled as P/S.
CLAIMS = (
    ("EDITORIAL_TRANSITION", "Use this guide to prepare questions before discussing an order."),
    ("OBSERVED_PRODUCT_FACT", FACTS[0]),
    ("OBSERVED_PRODUCT_FACT", "The synthetic spindle statement identifies a continuous rating and a named test method; its scope explicitly excludes a cutting-load claim."),
    ("GENERAL_TECHNICAL_CONTEXT", "A buyer enquiry should distinguish the stated spindle test conditions from the intended cutting application, then request evidence for any different duty or operating conditions."),
    ("GENERAL_TECHNICAL_CONTEXT", "Record the intended workpiece material, operating conditions and acceptance method in the enquiry so that the supplier can address applicability rather than relying on a headline rating."),
    ("EDITORIAL_TRANSITION", "Continue with the enquiry checklist and keep its limitations beside the corresponding statements."),
    ("OBSERVED_PRODUCT_FACT", FACTS[1]),
    ("OBSERVED_PRODUCT_FACT", "The synthetic tolerance statement applies to an aluminum test piece under the stated method and temperature; it gives no guarantee for other materials or production conditions."),
    ("GENERAL_TECHNICAL_CONTEXT", "Request a representative test piece and an agreed measurement method for the intended material before treating the stated tolerance as a purchasing acceptance criterion."),
    ("OBSERVED_PRODUCT_FACT", FACTS[2]),
    ("OBSERVED_PRODUCT_FACT", "The synthetic certificate identifies a fictional issuer, a named standard and a model scope; the statement explicitly says that it is not a real certification."),
    ("GENERAL_TECHNICAL_CONTEXT", "Ask for the original certificate, confirm the issuing body and covered model, and review its validity for the intended enquiry before making a certification statement to a buyer."),
    ("GENERAL_TECHNICAL_CONTEXT", "Keep the spindle test record, tolerance test record and certificate together with the enquiry; review each source against the intended use and retain any unresolved differences for clarification."),
    ("CALL_TO_ACTION", "Prepare an enquiry and request the applicable evidence and limitations before proceeding."),
)


class ArticleFetcher(LocalFetcher):
    async def fetch(self, url, **kwargs):
        require(url == URL)
        paragraphs = "".join(f"<p>{text}</p>" for kind, text in CLAIMS if kind == "OBSERVED_PRODUCT_FACT")
        html = ('<html><head><title>SYNTHETIC NovaCNC machining center</title>'
            '<meta name="description" content="Fictional offline article demonstration"></head>'
            '<body><main><h1>SYNTHETIC NovaCNC</h1><h2>Buyer considerations</h2><p>'
            + "; ".join(SUBJECTS) + "</p>" + paragraphs + "</main></body></html>").encode()
        return self.result(url, html, "text/html")


class ArticleSearch(LocalSearch):
    async def search(self, query):
        from foreign_trade_geo_agent.core.search import SearchResponse, SearchResult, SearchStatus
        # The first two deterministic outline candidates are native planner data.
        content = ("; ".join((*SUBJECTS[1:], SUBJECTS[0])) + "; " + TITLE + "; "
            + " ".join(text for kind, text in CLAIMS if kind == "GENERAL_TECHNICAL_CONTEXT"))
        return SearchResponse(query, SearchStatus.SUCCESS,
            (SearchResult(SUBJECTS[0], "https://cnc-guide.example/checklist", content, 1.0),), None)


class ArticleOpportunity:
    async def write_content_opportunities(self, prompt):
        topic = next(c for c in prompt.topic_candidates if c.text == SUBJECTS[0])
        body = {"opportunities": [{"opportunity_type": "NEW_SUPPORTING_CONTENT", "priority": "HIGH",
            "topic_ref": topic.candidate_id, "enhancement_action_codes": [],
            "page_refs": ["P1"], "source_refs": ["S1"], "audit_refs": []}]}
        return ContentOpportunityGeneration("synthetic", "fixed-article-fixture",
            ContentOpportunityGenerationStatus.SUCCESS, json.dumps(body), None)


class ArticlePlan:
    async def write_change_plan(self, prompt):
        points = [next(c for c in prompt.content_point_candidates_for("R1") if c.text == subject) for subject in SUBJECTS]
        body = {"opportunity_operations": {"R1": {"primary_operation": {
            "source_action_code": "CREATE_SUPPORTING_RESOURCE", "operation_type": "CREATE_NEW_RESOURCE",
            "page_bindings": [{"page_ref": "P1", "suggested_source": True}], "source_refs": ["S1"],
            "resource_purpose": "SUPPORTING_RESOURCE", "proposed_title": TITLE,
            "content_points": [{"intent": "EXPLAIN", "subject_ref": point.candidate_id} for point in points],
            "comparison_table_brief": None}, "secondary_operation": None}}}
        return cp.ChangePlanGeneration("synthetic", "fixed-article-fixture", cp.ChangePlanGenerationStatus.SUCCESS,
            json.dumps(body), None)


class FixedArticleWriter:
    """Hand-written JSON fixture; no model invocation or quality claim."""
    def __init__(self):
        self.calls = 0

    async def write_content_draft(self, prompt):
        self.calls += 1
        headings = prompt.operation.new_resource_spec.outline_headings
        claims = [{"text": text, "claim_type": kind,
            "page_refs": ["P1"] if kind in {"OBSERVED_PRODUCT_FACT", "GENERAL_TECHNICAL_CONTEXT"} else [],
            "source_refs": ["S1"] if kind == "GENERAL_TECHNICAL_CONTEXT" else []} for kind, text in CLAIMS]
        sections = []
        for heading, selected in zip(headings, (claims[:5], claims[5:])):
            sections.append({"outline_heading": heading, "blocks": [
                {"kind": "PARAGRAPH", "claims": selected[i:i+4]} for i in range(0, len(selected), 4)]})
        body = {"draft": {"change_ref": prompt.change_ref, "draft_type": "NEW_RESOURCE_DRAFT", "sections": sections}}
        return ContentDraftGeneration("synthetic", "hand-written-fixture-NOT-LLM", ContentDraftGenerationStatus.SUCCESS,
            json.dumps(body), None)


class SyntheticHumanFixture:
    """Test verdicts ONLY; neither real human signoff nor production authority."""
    def assess(self, snapshot, *, now):
        decisions = tuple(RequirementDecision(r.requirement_id, SupportVerdict.SUPPORTED,
            "Explicit synthetic TEST verdict for the fixed documents; not production review.",
            tuple(EvidenceSpan(e.supplement.evidence_id, 0, len(e.supplement.content), e.supplement.content)
                  for e in snapshot.active_evidence if r.requirement_id in e.supplement.requirement_ids))
            for r in snapshot.task.requirements)
        return SemanticAssessment(snapshot_digest(snapshot), "SYNTHETIC-TEST-REVIEWER", now, decisions, ArticleScopeCoverage(True, "Explicit synthetic scope review; no human signoff."))


def ports(writer):
    return dict(fetcher=ArticleFetcher(), search_provider=ArticleSearch(), research_writer=LocalResearch(),
        content_opportunity_writer=ArticleOpportunity(), change_plan_writer=ArticlePlan(), content_draft_writer=writer)


async def run_offline_candidate(db, store, project_id, task_id, *, expected_sha256, reviewer, writer, now=NOW):
    """Demonstration harness only; no production authorization branch.

    Refuse missing/stale/conflicting evidence before entering the existing
    isolated composition. Post-checks prevent exporting changed evidence.
    Only the concrete hand-written fixture writer may be supplied here.
    """
    require(type(writer) is FixedArticleWriter)
    current = store.latest(project_id, task_id)
    require(snapshot_digest(current) == expected_sha256 and current.plan_bound)
    check = EvidenceIntakeWorkflow(store, reviewer=reviewer).check(project_id, task_id, now=now)
    require(check.status is IntakeStatus.CANDIDATE_FOR_REVIEW and check.snapshot_sha256 == expected_sha256)
    result = await build_isolated_test_planning_workflow(db, **ports(writer)).run(EndToEndRunRequest(URL, GOAL))
    require(result.terminal_report.status.value == "success")
    reader = SQLiteHistoryReader(db)
    by_kind = {a.artifact_type: reader.get_artifact(a.artifact_id).payload for a in result.artifacts}
    original = current.planning_input
    require(by_kind[ArtifactType.SITE_CONTENT] == original.site_content
            and by_kind[ArtifactType.CONTENT_OPPORTUNITY] == original.opportunity_report
            and by_kind[ArtifactType.CHANGE_PLAN] == original.change_plan_report)
    final_check = EvidenceIntakeWorkflow(store, reviewer=reviewer).check(project_id, task_id, now=now)
    require(snapshot_digest(store.latest(project_id, task_id)) == expected_sha256
            and final_check.status is IntakeStatus.CANDIDATE_FOR_REVIEW)
    return result


def prepare(directory: Path):
    directory.mkdir(parents=True, exist_ok=False)
    def save(name, value):
        (directory / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    db, intake_db = directory / "history.sqlite3", directory / "intake.sqlite3"
    never = NeverDraft()
    initial = asyncio.run(build_planning_workflow(db, **ports(never)).run(EndToEndRunRequest(URL, GOAL)))
    require(initial.terminal_report.error == "INTAKE_EXECUTION_BLOCKED" and never.calls == 0)
    plan_id = next(a.artifact_id for a in initial.artifacts if a.artifact_type is ArtifactType.CHANGE_PLAN)
    store = SQLiteEvidenceIntakeStore.create(intake_db)
    intake = EvidenceIntakeWorkflow(store)
    planning = PlanningEvidenceWorkflow(SQLiteHistoryReader(db), intake)
    requirements = tuple(EvidenceRequirement(f"F{i+1}", i,
        ("Spindle duty, method, temperature and cutting-load exclusion",
         "Tolerance model, material, method, temperature and production exclusion",
         "Certificate issuer, identifier, standard, model, expiry and fictional status")[i],
        f"Explain {SUBJECTS[i]} with every applicable condition and exclusion",
        "Synthetic site statements need attributed customer source documents and human applicability review.",
        (SupplementMethod.TEXT_DOCUMENT,)) for i in range(3))
    original = planning.register(initial.run.run_id, plan_id, customer_id=CUSTOMER, requirements=requirements)
    save("01-missing-evidence.json", asdict(intake.customer_request(original.task.project_id, plan_id, now=NOW)))
    supplements = tuple(Supplement(f"E{i+1}", (f"F{i+1}",), SupplementMethod.TEXT_DOCUMENT, fact,
        "SYNTHETIC NovaCNC engineering document", f"synthetic:VMC-DEMO/document-v1/paragraph-{i+1}",
        "FICTIONAL NovaCNC", hashlib.sha256(fact.encode()).hexdigest()) for i, fact in enumerate(FACTS))
    submission = CustomerSubmission("SYNTHETIC-ARTICLE-SUBMISSION", snapshot_digest(original), supplements)
    save("submission.json", asdict(submission))
    submitted = intake.submit(original.task.project_id, plan_id, submission,
        customer=CustomerContext(CUSTOMER, "SYNTHETIC-CUSTOMER-ENGINEER", NOW))
    candidate = asyncio.run(planning.recheck(original.task.project_id, plan_id,
        expected_sha256=snapshot_digest(submitted), current=submitted,
        planner=ChangePlanWorkflow(RetainedIntakePlanWriter()), now=NOW))
    (directory / "02-intake-human-review.json").write_text(planning_review_json(candidate), encoding="utf-8")
    snapshot = candidate.snapshot
    digest = snapshot_digest(snapshot)
    guarded = ContentDraftWorkflow(never, intake_admission=EvidenceIntakeDraftAdmission(
        store, original.task.project_id, plan_id, expected_snapshot_sha256=digest))
    blocked = asyncio.run(guarded.run(snapshot.planning_input))
    require(blocked.error == "INTAKE_EXECUTION_BLOCKED" and never.calls == 0)
    writer = FixedArticleWriter()
    result = asyncio.run(run_offline_candidate(db, store, original.task.project_id, plan_id,
        expected_sha256=digest, reviewer=SyntheticHumanFixture(), writer=writer))
    artifact_ref = next(a for a in result.artifacts if a.artifact_type is ArtifactType.CONTENT_DRAFT)
    artifact = SQLiteHistoryReader(db).get_artifact(artifact_ref.artifact_id)
    view = ContentDraftReviewWorkflow(history_reader=SQLiteHistoryReader(db)).review(
        ContentDraftReviewRequest(result.run.run_id, artifact.artifact_id, "D1"))
    report = artifact.payload
    (directory / "03-content-draft.json").write_text(encode_artifact(ArtifactType.CONTENT_DRAFT, report), encoding="utf-8")
    save("04-article-review.json", content_draft_review_payload(view))
    claims = {c.text: c.claim_id for c in view.draft.claims}
    bindings = []
    for i, fact in enumerate(FACTS):
        require(fact in claims)  # Exact qualifiers must survive assembly and persistence.
        evidence = snapshot.active_evidence[i]
        bindings.append({"requirement_id": f"F{i+1}", "claim_id": claims[fact],
            "customer_evidence_id": evidence.supplement.evidence_id, "page_ref": "P1",
            "customer_source_locator": evidence.supplement.source_locator,
            "file_sha256": evidence.supplement.file_sha256, "span": [0, len(fact)], "quote": fact,
            "review_state": "UNREVIEWED", "binding_kind": "EXACT_SYNTHETIC_FIXTURE_MATCH_NOT_AUTHORIZATION"})
    origin = SQLiteHistoryReader(db)
    origin_artifacts = [{"artifact_type": a.artifact_type.value, "artifact_id": a.artifact_id,
        "payload_sha256": hashlib.sha256(encode_artifact(a.artifact_type, a.payload).encode()).hexdigest()}
        for a in origin.list_artifacts(snapshot.task.project_id)]
    manifest = {"synthetic_only": True, "model_generated": False, "article_review_state": "UNREVIEWED",
        "draft_authorized": False, "production_draft_writer_calls": never.calls,
        "offline_fixed_writer_calls": writer.calls, "production_error": blocked.error,
        "project_id": snapshot.task.project_id, "customer_id": CUSTOMER, "task_id": plan_id,
        "versions": {"task": snapshot.task.task_version, "plan": snapshot.plan_version,
                     "evidence": snapshot.evidence_version, "revision": snapshot.revision},
        "snapshot_sha256": digest, "offline_run_id": result.run.run_id,
        "origin_artifacts": origin_artifacts,
        "content_draft_artifact_id": artifact.artifact_id,
        "draft_sha256": hashlib.sha256(encode_artifact(ArtifactType.CONTENT_DRAFT, report).encode()).hexdigest(),
        "evidence_binding": bindings,
        "limitations": ["P/S come from explicit synthetic offline fixtures, not live crawl/research.",
            "E records are attributed customer context, not native Draft grounding.",
            "TEST semantic verdicts are scripted; article claims remain UNREVIEWED.",
            "Not a production customer-evidence Draft path or model quality acceptance."]}
    save("05-evidence-binding.json", manifest)
    preview = ("> SYNTHETIC OFFLINE FIXTURE — hand-written test sample, NOT a real model draft.\n"
        "> All customer, website, research and certificate data are fictional. Production Draft remains blocked.\n\n"
        + render_content_draft_review_markdown(view) + "\n## Customer evidence binding (review only)\n\n"
        + f"Snapshot SHA256: {digest}\n\nVersions: task {snapshot.task.task_version}, plan {snapshot.plan_version}, "
          f"evidence {snapshot.evidence_version}, revision {snapshot.revision}.\n\n"
        + "\n".join(f"- {b['claim_id']} → {b['requirement_id']} / {b['customer_evidence_id']} / "
                    f"{b['customer_source_locator']} — UNREVIEWED" for b in bindings) + "\n")
    (directory / "article-preview.md").write_text(preview, encoding="utf-8")
    manifest["article_word_count"] = sum(len(text.split()) for _, text in CLAIMS)
    save("verification.json", manifest)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    print(json.dumps(prepare(parser.parse_args().output_dir), ensure_ascii=False, indent=2))
