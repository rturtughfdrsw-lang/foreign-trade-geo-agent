"""Offline rich-evidence acceptance, including honest downstream loss probes.

No credentials, production transports, WordPress, permit or live-freeze path.
The model ports are scripted fixtures: their output is NOT planning/writing
intelligence. All native parsers, validators, gates and persistence stay intact.
"""
import argparse
import asyncio
from dataclasses import replace
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from scripts import novacnc_buyer_fixture as fixture
from scripts import accept_seo_task_scope as legacy
from scripts.accept_native_article_scope import CaseScopeReviewer
from scripts.demo_seo_evidence import LocalFetcher, NeverDraft, URL
from foreign_trade_geo_agent.adapters.customer_evidence import text_document
from foreign_trade_geo_agent.adapters.retained_intake_plan import RetainedIntakePlanWriter
from foreign_trade_geo_agent.adapters.retained_deepseek import MAX_REQUEST_BYTES
from foreign_trade_geo_agent.adapters.deepseek_content_draft import DeepSeekContentDraftWriter, content_draft_request_payload
from foreign_trade_geo_agent.core import change_plan as cp, content_draft as cd
from foreign_trade_geo_agent.core.content_opportunity import ContentOpportunityGeneration, ContentOpportunityGenerationStatus
from foreign_trade_geo_agent.core.draft_customer_evidence import DraftCustomerEvidence, DraftCustomerSource, native_scope_digest
from foreign_trade_geo_agent.core.evidence_intake import (
    ArticleScopeCoverage, CustomerContext, CustomerSubmission, EvidenceRequirement, EvidenceSpan,
    RequirementDecision, SemanticAssessment, SupplementMethod, SupportVerdict, require, snapshot_digest,
    CustomerPlanningContext,
)
from foreign_trade_geo_agent.core.history import ArtifactType
from foreign_trade_geo_agent.core.orchestration import EndToEndRunRequest
from foreign_trade_geo_agent.core.search import SearchResponse, SearchResult, SearchStatus
from foreign_trade_geo_agent.core.research import ResearchGeneration, ResearchGenerationStatus
from foreign_trade_geo_agent.runtime import build_planning_workflow
from foreign_trade_geo_agent.storage.evidence_intake import SQLiteEvidenceIntakeStore
from foreign_trade_geo_agent.storage.serialization import _encode
from foreign_trade_geo_agent.storage.sqlite import SQLiteHistoryReader
from foreign_trade_geo_agent.web.app import create_app
from foreign_trade_geo_agent.web.generation import MockArticleExecutor, canonical
from foreign_trade_geo_agent.workflows.change_plan import ChangePlanWorkflow
from foreign_trade_geo_agent.workflows.content_draft import ContentDraftWorkflow
from foreign_trade_geo_agent.workflows.evidence_intake import EvidenceIntakeWorkflow, EvidenceIntakeDraftAdmission
from foreign_trade_geo_agent.workflows.planning_evidence import PlanningEvidenceWorkflow

ROOT = Path(__file__).resolve().parents[1]
CUSTOMER = "SYNTHETIC-NOVACNC-RICH-BUYER-TEST"
BACKGROUND = (
    "Compare the workpiece and fixture envelope before shortlisting equipment.",
    "Read test conditions alongside any stated performance and request representative trials.",
    "Agree measurement responsibilities and acceptance criteria before placing an order.",
    "Send the intended application and request applicable records and written commercial terms.",
)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, value):
    path.write_bytes(json.dumps(value, default=_encode, ensure_ascii=False, indent=2, allow_nan=False).encode())


def protected_hashes():
    """Read-only hashes; never open historical databases through SQLite."""
    folders = ("seo-model-comparison-live-2026-10-11", "seo-model-comparison-preflight-2026-10-11",
               "seo-native-scope-acceptance-2026-10-11", "seo-task-scope-acceptance-2026-10-11",
               "seo-web-deepseek-live-2026-10-11", "seo-web-deepseek-live-2026-10-10")
    return {p.relative_to(ROOT).as_posix(): sha(p.read_bytes()) for name in folders
            for p in sorted((ROOT / "docs" / name).rglob("*")) if p.is_file()}


def package(directory):
    directory.mkdir()
    facts = list(fixture.rows())
    supplements = []
    names = ("retained-spindle-note", "base-configurations", "spindle-and-measurements",
             "material-and-cutting-trials", "conditional-selection", "rfq-and-acceptance", "service-and-register")
    for i, name in enumerate(names, 1):
        eid = f"E{i}"
        rows = [r for r in facts if r["evidence_id"] == eid]
        if eid == "E1":
            original = legacy.load_frozen().active_evidence[0].supplement
            content = original.content
            # Original source identity/content/hash preserved; obligations belong to the NEW task.
            locator, label, owner = original.source_locator, original.source_label, original.declared_source_owner
        else:
            content = (f"SYNTHETIC / TEST ONLY — fictional NovaCNC {name}\n"
                       "Revision B-TEST-2026-10-11; dossier validity 2026-10-11 through 2027-01-09.\n"
                       "Register dates describe this fictional offline case, not real technical authentication.\n"
                       + "\n".join(r["quote"] for r in rows)
                       + "\nSYNTHETIC / TEST ONLY. No customer approval, engineering certification or execution authority.\n")
            locator, label, owner = f"synthetic:novacnc/rich-buyer/B-TEST/{eid}", f"SYNTHETIC / TEST ONLY {name}", "FICTIONAL NovaCNC"
        path = directory / f"{eid}-{name}.txt"
        path.write_bytes(content.encode("utf-8"))
        ids = tuple(n[0] for n in fixture.NEEDS if eid in n[4])
        supplement = text_document(evidence_id=eid, requirement_ids=ids, payload=path.read_bytes(),
            source_label=label, source_locator=locator, declared_source_owner=owner)
        supplements.append(supplement)
        for row in rows:
            row.update(source_file=path.name, source_locator=locator, file_sha256=supplement.file_sha256,
                       span_start=content.index(row["quote"]), span_end=content.index(row["quote"]) + len(row["quote"]))
    save(directory / "facts.json", facts)
    save(directory / "documents.json", supplements)
    save(directory / "consistency-checks.json", consistency_checks(facts, tuple(supplements)))
    return facts, tuple(supplements)


def consistency_checks(facts, supplements):
    """Fixture-specific arithmetic/identity checks; not engineering validation."""
    by_id = {r["fact_id"]: r for r in facts}
    docs = {s.evidence_id: s for s in supplements}
    require(len(by_id) == len(facts) == 43 and len(docs) == 7)
    for row in facts:
        doc = docs[row["evidence_id"]]
        require(doc.content[row["span_start"]:row["span_end"]] == row["quote"]
                and sha(doc.content.encode()) == row["file_sha256"]
                and all(row[k] for k in ("subject", "attribute", "unit", "test_conditions", "applicable_scope", "limitations", "revision", "source_locator"))
                and row["valid_from"] <= "2026-10-11" <= row["valid_through"])
    legacy_note = legacy.load_frozen().active_evidence[0].supplement
    require(docs["E1"].content == legacy_note.content and docs["E1"].file_sha256 == legacy_note.file_sha256
            and docs["E1"].source_locator == legacy_note.source_locator
            and by_id["SPINDLE-LEGACY"]["value"] == 7200)
    # Nominal table can accommodate the stated travel extents; this says
    # nothing about reachable/usable envelope, structural or dynamic safety.
    for model in ("NCX7", "NCX10"):
        travel, table = by_id[model+"-TRAVEL"]["value"], by_id[model+"-TABLE"]["value"]
        require(travel[0] <= table[0] and travel[1] <= table[1])
        require(abs(float(by_id[model+"-COUPON"]["value"].replace("+/-", ""))) == .02)
    small, large = by_id["FIT-SMALL"]["value"], by_id["FIT-LARGE"]["value"]
    require(all(small[0] <= by_id[m+"-TABLE"]["value"][0] and small[1] <= by_id[m+"-TABLE"]["value"][1]
                and small[2] <= by_id[m+"-LOAD"]["value"] for m in ("NCX7", "NCX10")))
    require(large[1] > by_id["NCX7-TABLE"]["value"][1] and large[2] > by_id["NCX7-LOAD"]["value"]
            and large[0] <= by_id["NCX10-TABLE"]["value"][0] and large[1] <= by_id["NCX10-TABLE"]["value"][1]
            and large[2] <= by_id["NCX10-LOAD"]["value"])
    require(by_id["AL-CUT"]["value"][0] <= by_id["SPINDLE-LEGACY"]["value"] < by_id["NCX10-SPEED"]["value"])
    require(by_id["FAT-CRITERION"]["value"] == "+/-0.025" and by_id["MEASUREMENT"]["value"] == .005)
    require({r["quote"] for r in facts} == {s.quote for n in fixture.NEEDS for s in spans_for(n[0], facts)})
    return dict(status="PASS_SYNTHETIC_INTERNAL_CONSISTENCY_ONLY", fact_count=43, document_count=7,
        checks=("unique fact identity; exact source offsets and UTF-8 hashes; complete metadata",
                "legacy E1 content/hash/locator retained; new task requirement mapping explicit",
                "nominal travel/table consistency; small/large fixture comparisons match stated load/width",
                "trial speed below stated unloaded rating; no inferred cutting capability",
                "observed coupon deviation differs from proposed acceptance criterion; decision rule remains pending",
                "every fact appears in at least one TEST review obligation; fixture date lies within dossier register interval"),
        engineering_certification=False, actual_calibration=False, actual_customer_approval=False)


def spans_for(fid, facts):
    expected = next(n[4] for n in fixture.NEEDS if n[0] == fid)
    selected = [r for r in facts if r["evidence_id"] in expected]
    if fid == "F2":
        selected = [r for r in selected if r["attribute"] in
                    {"continuous unloaded speed", "continuous motor nameplate power", "trial warm-up"}]
    if fid == "F4":
        selected = [r for r in selected if r["evidence_id"] == "E4" or "COUPON" in r["fact_id"] or r["fact_id"] == "MEASUREMENT"]
    if fid == "F8":
        selected = [r for r in selected if r["fact_id"] in {"REGISTER", "OPTIONS", "CONFIG-REVIEW"}]
    return tuple(EvidenceSpan(r["evidence_id"], r["span_start"], r["span_end"], r["quote"]) for r in selected)


class DossierReviewer:
    """Explicit case-local TEST review, not a reusable semantic detector."""
    def __init__(self, facts, supplements):
        self.facts, self.supplements = facts, supplements

    def assess(self, snapshot, *, now):
        require(tuple(e.supplement for e in snapshot.active_evidence) == self.supplements)
        op = snapshot.planning_input.change_plan_report.operations[0]
        require(snapshot.task.customer_id == CUSTOMER and snapshot.task.goal == fixture.GOAL
                and tuple(p.subject for p in op.content_points) == fixture.SUBJECTS
                and op.new_resource_spec.proposed_title == fixture.TITLE
                and snapshot.task.requirements == requirements())
        # Expiry and content matching are scripted dossier checks; native V1 has
        # no intrinsic document-expiry metadata or independent engineering test.
        require(all(r["valid_from"] <= now.date().isoformat() <= r["valid_through"] for r in self.facts))
        return SemanticAssessment(snapshot_digest(snapshot), "SYNTHETIC-DOSSIER-REVIEW-NOT-HUMAN", now,
            tuple(RequirementDecision(n[0], SupportVerdict.SUPPORTED,
                "TEST-only: fictional dossier addresses this obligation within its documented proposal/trial limits; not engineering or customer approval.",
                spans_for(n[0], self.facts)) for n in fixture.NEEDS),
            ArticleScopeCoverage(True, "TEST-only: goal, full five EXPLAIN subjects and eight obligations align. This does not prove chapter depth or downstream fact retention."))


def requirements():
    return tuple(EvidenceRequirement(fid, index, need, use,
        "P/S identify purchasing questions only; applicable customer-specific facts and commercial proposals require E records.",
        (SupplementMethod.TEXT_DOCUMENT,)) for fid, index, need, use, _ in fixture.NEEDS)


class TopicFetcher(LocalFetcher):
    async def fetch(self, url, **kwargs):
        require(url == URL)
        html = (f'<html><head><title>{fixture.SUBJECTS[4]}</title><meta name="description" content="SYNTHETIC / TEST ONLY purchasing topics"></head>'
                '<body><main><h1>SYNTHETIC NovaCNC</h1><h2>Buyer questions</h2><p>'
                + "; ".join(fixture.SUBJECTS) + '</p></main></body></html>')
        return self.result(url, html.encode(), "text/html")


class TopicSearch:
    async def search(self, query):
        # S is wholly fictional, unverified general context. No E parameters.
        sources = ((fixture.HEADINGS[0], "; ".join((fixture.HEADINGS[1], fixture.SUBJECTS[0], fixture.TITLE, *fixture.HEADINGS[2:], *BACKGROUND))),
                   *((fixture.SUBJECTS[i], BACKGROUND[i-1]) for i in range(1, 4)))
        return SearchResponse(query, SearchStatus.SUCCESS, tuple(SearchResult(title,
            f"https://synthetic-context.example/buyer/{i}", content, 1.0) for i, (title, content) in enumerate(sources, 1)), None)


class ScriptedOpportunity:
    async def write_content_opportunities(self, prompt):
        topic = next(c for c in prompt.topic_candidates if c.text == fixture.SUBJECTS[0])
        body = {"opportunities": [{"opportunity_type": "NEW_SUPPORTING_CONTENT", "priority": "HIGH",
            "topic_ref": topic.candidate_id, "enhancement_action_codes": [], "page_refs": ["P1"],
            "source_refs": ["S1", "S2", "S3", "S4"], "audit_refs": []}]}
        return ContentOpportunityGeneration("synthetic", "scripted-opportunity-NOT-MODEL",
            ContentOpportunityGenerationStatus.SUCCESS, json.dumps(body), None)


class TopicResearch:
    async def write_report(self, question, materials, target_language):
        return ResearchGeneration("synthetic", "scripted-research-NOT-MODEL", ResearchGenerationStatus.SUCCESS,
            "SYNTHETIC / TEST ONLY: procurement question map [S1] [S2] [S3] [S4]", None)


class ScriptedPlan:
    """Port substitute only. Never manually edits finalized Plan or headings."""
    async def write_change_plan(self, prompt):
        points = [next(c for c in prompt.content_point_candidates_for("R1") if c.text == s) for s in fixture.SUBJECTS]
        body = {"opportunity_operations": {"R1": {"primary_operation": {
            "source_action_code": "CREATE_SUPPORTING_RESOURCE", "operation_type": "CREATE_NEW_RESOURCE",
            "page_bindings": [{"page_ref": "P1", "suggested_source": True}], "source_refs": ["S1", "S2", "S3", "S4"],
            "resource_purpose": "SUPPORTING_RESOURCE", "proposed_title": fixture.TITLE,
            "content_points": [{"intent": "EXPLAIN", "subject_ref": p.candidate_id} for p in points],
            "comparison_table_brief": None}, "secondary_operation": None}}}
        return cp.ChangePlanGeneration("synthetic", "scripted-plan-NOT-MODEL", cp.ChangePlanGenerationStatus.SUCCESS, json.dumps(body), None)


def source_for(record, span):
    m = record.supplement
    return DraftCustomerSource(m.evidence_id, record.evidence_version, m.requirement_ids,
        m.source_label, m.source_locator, m.content, m.file_sha256, span.start, span.end, span.quote)


def bundle_for(snapshot, assessment, sources):
    value = snapshot.planning_input
    return DraftCustomerEvidence(snapshot.task.project_id, snapshot.task.customer_id, snapshot.task.task_id,
        snapshot.task.task_version, snapshot.plan_version, snapshot.evidence_version, snapshot.revision,
        snapshot_digest(snapshot), native_scope_digest(value.site_content, value.opportunity_report, value.change_plan_report.operations[0]),
        "C1", assessment.reviewer_id, assessment.reviewed_at, "TEST_ONLY_SUPPORTED_NOT_HUMAN_SIGNOFF", tuple(sources))


def demo_response(value):
    """Mechanics-only extractive projection. Never a quality demonstration."""
    def claim(text, kind, e=(), s=()):
        return dict(text=text, claim_type=kind, page_refs=[], source_refs=list(s), customer_refs=list(e))
    quotes = [claim(s.quote, "OBSERVED_PRODUCT_FACT", (s.evidence_id,)) for s in value.customer_evidence.sources]
    headings = value.change_plan_report.operations[0].new_resource_spec.outline_headings
    return {"draft": {"change_ref": "C1", "draft_type": "NEW_RESOURCE_DRAFT", "sections": [
        {"outline_heading": headings[0], "blocks": [{"kind": "PARAGRAPH", "claims": quotes[:4]},
            {"kind": "PARAGRAPH", "claims": quotes[4:]}]},
        {"outline_heading": headings[1], "blocks": [{"kind": "PARAGRAPH", "claims": [
            claim("Prepare the enquiry and keep its supporting records together.", "EDITORIAL_TRANSITION"),
            claim(BACKGROUND[2], "GENERAL_TECHNICAL_CONTEXT", s=("S4",)),
            claim("Send the intended application and request applicable records and written commercial terms.", "CALL_TO_ACTION")]}]},
    ]}}


async def old_control(directory):
    directory.mkdir()
    store = SQLiteEvidenceIntakeStore.create(directory / "intake.sqlite3")
    flow = EvidenceIntakeWorkflow(store)
    candidate = await legacy.single_e1_case(flow, "LOW-EVIDENCE-GUIDE-CONTROL")
    reviewed = EvidenceIntakeWorkflow(store, reviewer=CaseScopeReviewer()).check(
        candidate.snapshot.task.project_id, candidate.snapshot.task.task_id, now=datetime.now(UTC))
    save(directory / "snapshot.json", candidate.snapshot)
    save(directory / "scope-and-evidence-review.json", reviewed)
    require(reviewed.status.value == "BLOCKED" and tuple(g.requirement.requirement_id for g in reviewed.gaps) == ("F2", "F3", "F4", "F5"))
    return reviewed


async def prepare_native(directory, facts, supplements, *, scope=None, reviewer_factory=DossierReviewer):
    candidate = directory / "candidate"
    candidate.mkdir()
    never = NeverDraft()
    run = await build_planning_workflow(candidate / "history.sqlite3", fetcher=TopicFetcher(),
        search_provider=TopicSearch(), research_writer=TopicResearch(), content_opportunity_writer=ScriptedOpportunity(),
        change_plan_writer=ScriptedPlan(), content_draft_writer=never).run(EndToEndRunRequest(URL, fixture.GOAL))
    save(directory / "native-run.json", run)
    require(run.terminal_report.error == "INTAKE_EXECUTION_BLOCKED" and never.calls == 0)
    plan_id = next(a.artifact_id for a in run.artifacts if a.artifact_type is ArtifactType.CHANGE_PLAN)
    reader = SQLiteHistoryReader(candidate / "history.sqlite3")
    store = SQLiteEvidenceIntakeStore.create(directory / "interactive-intake.sqlite3")
    planning = PlanningEvidenceWorkflow(reader, EvidenceIntakeWorkflow(store))
    current = planning.register(run.run.run_id, plan_id, customer_id=CUSTOMER, requirements=requirements(), **(scope or {}))
    save(directory / "01-missing-evidence.json", planning.intake.customer_request(run.run.run_id, plan_id, now=datetime.now(UTC)))
    current = planning.intake.submit(run.run.run_id, plan_id,
        CustomerSubmission("SYNTHETIC-RICH-DOSSIER", snapshot_digest(current), supplements),
        customer=CustomerContext(CUSTOMER, "SYNTHETIC-OPERATOR-NOT-CUSTOMER", datetime.now(UTC)))
    # Full documents are visible to the native replan, separate from P/S.
    prompt = cp.build_change_plan_prompt(cp.ChangePlanInput(current.planning_input.site_content,
        current.planning_input.opportunity_report, task_id=plan_id, customer_context=CustomerPlanningContext(current)))
    (directory / "02-native-replan-material.json").write_bytes(prompt.material_json().encode())
    replanned = await planning.recheck(run.run.run_id, plan_id, expected_sha256=snapshot_digest(current), current=current,
        planner=ChangePlanWorkflow(RetainedIntakePlanWriter()), now=datetime.now(UTC))
    save(directory / "03-unreviewed-candidate.json", replanned)
    current = replanned.snapshot
    reviewer = reviewer_factory(facts, supplements)
    review = EvidenceIntakeWorkflow(store, reviewer=reviewer).check(run.run.run_id, plan_id, now=datetime.now(UTC))
    require(review.status.value == "CANDIDATE_FOR_REVIEW")
    save(directory / "04-test-only-review.json", review)
    save(directory / "snapshot.json", current)
    save(directory / "opportunity.json", current.planning_input.opportunity_report)
    save(directory / "plan.json", current.planning_input.change_plan_report)
    save(directory / "append-only-intake.json", tuple(store.get_revision(run.run.run_id, plan_id, i) for i in range(1, current.revision + 1)))
    save(directory / "session.json", dict(profile="SYNTHETIC_LOCAL_MVP_V1", project_id=run.run.run_id, task_id=plan_id,
        candidate_run_id="NOT-GENERATED", candidate_artifact_id="NOT-GENERATED"))
    return current, review.assessment, reviewer, store


def loss_probes(directory, snapshot, assessment, facts):
    records = {r.supplement.evidence_id: r for r in snapshot.active_evidence}
    spans = tuple(dict.fromkeys(s for d in assessment.decisions for s in d.spans))
    failures = {}
    # Both obvious lossless encodings are rejected by the ACTUAL native contract.
    try:
        bundle_for(snapshot, assessment, [source_for(records[s.evidence_id], s) for s in spans])
    except ValueError as exc:
        failures["one_source_per_reviewed_span"] = str(exc)
    try:
        bundle_for(snapshot, assessment, [source_for(r, EvidenceSpan(e, 0, len(r.supplement.content), r.supplement.content))
                                          for e, r in records.items()])
    except ValueError as exc:
        failures["one_whole_document_quote_per_source"] = str(exc)
    require(len(failures) == 2)
    selected = ("SPINDLE-LEGACY", "NCX7-TRAVEL", "NCX10-SPEED", "AL-CUT", "FIT-LARGE", "FAT-CRITERION", "DELIVERY")
    projected = [next(s for s in spans if s.quote == next(r["quote"] for r in facts if r["fact_id"] == key)) for key in selected]
    brief = cd.ArticleWritingBrief(snapshot_digest(snapshot), snapshot.task.goal,
        "Commercial investigation: procurement teams need conditional model comparisons, applicable test evidence, an RFQ and negotiable acceptance and service terms.", fixture.BRIEF_INSTRUCTIONS)
    value = replace(snapshot.planning_input, customer_evidence=bundle_for(snapshot, assessment,
        [source_for(records[s.evidence_id], s) for s in projected]), writing_brief=brief)
    save(directory / "writing-brief.json", brief)
    save(directory / "diagnostic-native-input.json", value)
    material = json.loads(cd.build_content_draft_prompt(value, "C1").material_json())
    save(directory / "diagnostic-draft-material.json", material)
    emitted = {s["quote"] for s in material["customer_evidence"]["sources"]}
    audit = {"purpose": "DIAGNOSTIC LOSSY PROJECTION ONLY; NOT QUALITY-READY OR LIVE-FROZEN",
        "fact_count": len(facts), "reviewed_unique_spans": len(spans), "projected_E_sources": len(projected),
        "facts_present_in_writer_material": [r["fact_id"] for r in facts if r["quote"] in emitted],
        "facts_lost_before_writer": [r["fact_id"] for r in facts if r["quote"] not in emitted],
        "lossless_native_binding_failures": failures,
        "native_limits": dict(E_sources=8, single_quote_chars=300, draft_claims=cd.MAX_CLAIMS_PER_DRAFT,
                              draft_blocks=cd.MAX_BLOCKS_PER_DRAFT, output_tokens=cd.MAX_PROVIDER_TOKENS),
        "actual_headings": value.change_plan_report.operations[0].new_resource_spec.outline_headings,
        "full_documents_in_replan": True, "full_documents_in_draft_prompt": False,
        "automatic_planning_quality_measured": False, "real_model_writing_quality_measured": False}
    save(directory / "downstream-loss.json", audit)
    return value, audit


def web_acceptance(directory, snapshot, reviewer, store, value):
    app = create_app(mvp_dir=directory, db_path=directory / "demo.sqlite3", live_db_path=directory / "live.sqlite3")
    service = app.state.mvp_service
    service.scope_reviewer = reviewer
    response = demo_response(value)
    save(directory / "scripted-writer-response.json", response)
    requests = []
    def handler(request):
        requests.append(request.content)
        return httpx.Response(200, json={"model": "deepseek-flash", "choices": [
            {"message": {"content": json.dumps(response)}, "finish_reason": "stop"}]})
    service.generation_executor = MockArticleExecutor(task=snapshot.task, template=value, transport=httpx.MockTransport(handler))
    pages = directory / "web"
    pages.mkdir()
    with TestClient(app, base_url="http://127.0.0.1") as client:
        for route in ("/mvp", "/mvp/evidence", "/mvp/generate"):
            result = client.get(route)
            require(result.status_code == 200)
            (pages / (route.rsplit("/", 1)[-1] + ".html")).write_bytes(result.content)
        # Keep the full Brief rejection. Do not silently compress it to obtain
        # a purported rich-input success. The second run is mechanics ONLY.
        system = DeepSeekContentDraftWriter.build_system_prompt(customer_evidence=True)
        full_material = cd.build_content_draft_prompt(value, "C1").material_json()
        full_request = canonical(content_draft_request_payload(system, full_material))
        require(len(full_request) > MAX_REQUEST_BYTES and not service.generation.view()["generation_allowed"])
        require(client.post("/mvp/generate", data={"csrf_token": app.state.csrf_token, "binding_sha256": "0" * 64}).status_code == 409)
        require(not requests)
        blocked = dict(error="INPUT_BUDGET_EXCEEDED", full_brief_request_bytes=len(full_request),
            request_limit_bytes=MAX_REQUEST_BYTES, system_chars=len(system), user_material_chars=len(full_material),
            provider_max_tokens=cd.MAX_PROVIDER_TOKENS, requests_sent=0, paid_request_frozen=False)
        save(directory / "full-brief-web-blocked.json", blocked)
        short_brief = replace(value.writing_brief, instructions=(
            "SYNTHETIC / TEST ONLY mechanics diagnostic: preserve supplied quotes exactly and add a scope-matched enquiry CTA. This abbreviated brief and lossy quote subset cannot demonstrate a complete buyer guide or model writing quality.",))
        value = replace(value, writing_brief=short_brief)
        save(directory / "diagnostic-web-native-input.json", value)
        service.generation_executor = MockArticleExecutor(task=snapshot.task, template=value, transport=httpx.MockTransport(handler))
        client.get("/mvp/generate")  # native fresh ticket for diagnostic binding
        key = service.generation.view()["binding_sha256"]
        require(service.generation.view()["generation_allowed"])
        result = client.post("/mvp/generate", data={"csrf_token": app.state.csrf_token, "binding_sha256": key})
        require(result.status_code == 200)
        # Poll actual persisted reservation through HTTP; each GET yields to the
        # TestClient event loop, no external socket/server or blocking sleep.
        import time
        for _ in range(100):
            result = client.get("/mvp/generate")
            if service.generation.view()["generation_state"] != "RUNNING":
                break
            time.sleep(.01)
        require(service.generation.view()["generation_state"] == "SUCCEEDED")
        article = service.article()
        require(article["candidate_mode"] == "MOCK" and article["version_matches"])
        page = client.get("/mvp/article")
        require(page.status_code == 200)
        (pages / "article.html").write_bytes(page.content)
        (directory / "diagnostic-article-review.md").write_bytes(service.markdown().encode())
        selected = service.generation.selected()
        save(directory / "web-result.json", selected[1])
        # Reopen independently via native review and Web facade (no executor).
        from foreign_trade_geo_agent.web.mvp_application import MVPApplicationService
        require(MVPApplicationService(directory).article()["origin_sha256"] == article["origin_sha256"])
        client.post("/mvp/generate", data={"csrf_token": app.state.csrf_token, "binding_sha256": key})
        require(len(requests) == 1)
        denied = client.post("/mvp/delivery", data={"csrf_token": app.state.csrf_token,
            "version": "0", "binding_sha256": "0" * 64})
        require(denied.status_code in {409, 403})
        # Full facts are NOT silently considered retained because a native
        # mechanically valid projection generated an article.
        citations = [{"claim_id": c.claim_id, "text": c.text, "P": c.page_refs, "S": c.source_refs, "E": c.customer_refs}
                     for c in article["review"].draft.claims]
        save(directory / "claim-evidence-bindings.json", citations)
        for c in citations:
            if c["E"]:
                require(not c["P"] and not c["S"])
        # Revoking reviewer closes native scope admission even with an executor.
        service.scope_reviewer = None
        require(not service.generation.view()["generation_allowed"])
        require(client.post("/mvp/generate", data={"csrf_token": app.state.csrf_token, "binding_sha256": key}).status_code == 409)
    return dict(mock_requests=len(requests), executor_calls=service.generation_executor.calls,
        parser_validator_finalizer_sqlite_markdown_web="PASS_DIAGNOSTIC_ONLY", web_article_status=page.status_code,
        sqlite_reopen=True, duplicate_did_not_repeat=True, reviewer_revocation_blocked=True,
        wordpress_route_denied=True, real_model_calls=0, wordpress_calls=0,
        request_sha256=sha(requests[0]), request_bytes=len(requests[0]), real_writing_quality_measured=False,
        full_brief_request_blocked=blocked, diagnostic_uses_full_brief=False)


def write_reports(directory, facts, snapshot, assessment, loss, web, historical):
    matrix = ["# SYNTHETIC / TEST ONLY — fact-level evidence matrix", "",
        "Traceability and fictional internal consistency only; no actual engineering certification. JSON contains exact offsets and SHA-256 for each row.", "",
        "| Fact | Subject / attribute | Value / unit | Conditions | Applicability | Limits | Source / revision / validity |",
        "|---|---|---|---|---|---|---|"]
    for r in facts:
        matrix.append(f"| {r['fact_id']} | {r['subject']} / {r['attribute']} | {r['value']} / {r['unit']} | {r['test_conditions']} | {r['applicable_scope']} | {r['limitations']} | {r['evidence_id']} / {r['revision']} / {r['valid_from']} through {r['valid_through']} |")
    (directory / "fact-matrix.md").write_bytes(("\n".join(matrix) + "\n").encode())
    rows = ["# SYNTHETIC / TEST ONLY — evidence obligations", "", "All reviews below are scripted, not human signoff or engineering authentication.", "",
            "| Obligation | Procurement question / intended use | Exact source facts | Scope and unresolved limits |", "|---|---|---|---|"]
    for need, decision in zip(fixture.NEEDS, assessment.decisions):
        keys = [r["fact_id"] for r in facts if any(r["quote"] == s.quote for s in decision.spans)]
        rows.append(f"| {need[0]} | {need[2]}; {need[3]} | {', '.join(keys)} | Fictional base configurations; tests or unsigned proposals only; see fact-level limits |")
    (directory / "evidence-matrix.md").write_bytes(("\n".join(rows) + "\n").encode())
    op = snapshot.planning_input.change_plan_report.operations[0]
    lines = ["# SYNTHETIC / TEST ONLY — actual Plan and writing brief", "",
        "Model ports used scripted responses. Native parsing/finalization and Intake replan produced the following Plan; no finalized Plan was replaced.", "",
        f"Title: {op.new_resource_spec.proposed_title}", "", "Actual native headings:", "",
        *(f"- {h}" for h in op.new_resource_spec.outline_headings), "", "Actual EXPLAIN points:", "",
        *(f"- {p.subject}" for p in op.content_points), "", "Requested writing requirements (analyst authored, NOT generated chapters):", "",
        *(f"- {instruction}" for instruction in fixture.BRIEF_INSTRUCTIONS), "",
        "The actual two headings are a deterministic S-candidate projection. They are not a demonstrated multi-section procurement plan and contain no per-model/condition evidence allocation."]
    (directory / "plan-and-writing-brief.md").write_bytes(("\n".join(lines)+"\n").encode())
    summary = dict(status="BLOCKED", reason="Native Plan and extractive E-only writer contract cannot carry the complete rich-dossier purchasing brief.",
        synthetic_only=True, fact_count=len(facts), document_count=7, requirement_count=len(fixture.NEEDS),
        task_id=snapshot.task.task_id, project_id=snapshot.task.project_id, task_version=snapshot.task.task_version,
        plan_version=snapshot.plan_version, evidence_version=snapshot.evidence_version, snapshot_revision=snapshot.revision,
        snapshot_sha256=snapshot_digest(snapshot), old_low_evidence_status="BLOCKED", old_low_evidence_gaps=["F2", "F3", "F4", "F5"],
        rich_native_intake="CANDIDATE_FOR_REVIEW_TEST_ONLY", rich_document_internal_consistency="PASS_SYNTHETIC_ONLY",
        downstream_fact_loss_count=len(loss["facts_lost_before_writer"]), actual_headings=op.new_resource_spec.outline_headings,
        complete_draft_input_ready=False, complete_procurement_plan_ready=False, offline_mechanics=web,
        historical_files_unchanged=historical, paid_request_frozen=False, permits_issued=0,
        production_authorized=False, customer_approved=False, human_signoff=False,
        next_flash_conditions=["Resolve bounded per-document multiple reviewed-fact representation without weakening native quotation/reference/numeric checks.",
            "Resolve generic native chapter planning and explicit model/condition/limit allocation; prove coverage without replacing finalized Plan.",
            "Resolve the isolated 16000-byte request envelope mismatch using a bounded generic design; do not strip the substantive Brief or evidence.",
            "Repeat this offline positive/negative acceptance with complete fact retention and suitable explanation budget; keep A blocked.",
            "Only after READY freeze one deepseek-flash request, task/Plan/evidence/brief/prompt, exact SHA-256, input length, token budget and then-current price estimate.",
            "Obtain a NEW explicit authorization for that exact isolated paid request; no production or WordPress authority."])
    save(directory / "readiness.json", summary)
    return summary


def prepare(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    before = protected_hashes()
    save(directory / "historical-hashes-before.json", before)
    facts, supplements = package(directory / "customer-materials")
    # This hard guard makes any accidental real httpx transport fail immediately.
    with patch("httpx.AsyncHTTPTransport", side_effect=AssertionError("NO LIVE HTTP AUTHORIZED")), \
         patch("httpx.HTTPTransport", side_effect=AssertionError("NO LIVE HTTP AUTHORIZED")):
        asyncio.run(old_control(directory / "A-low-evidence"))
        rich = directory / "B-rich-evidence"
        rich.mkdir()
        snapshot, assessment, reviewer, store = asyncio.run(prepare_native(rich, facts, supplements))
        value, loss = loss_probes(rich, snapshot, assessment, facts)
        # Production admission remains closed for the same input.
        never = NeverDraft()
        report = asyncio.run(ContentDraftWorkflow(never, intake_admission=EvidenceIntakeDraftAdmission(
            store, snapshot.task.project_id, snapshot.task.task_id, expected_snapshot_sha256=snapshot_digest(snapshot))).run(value))
        require(report.error == "INTAKE_EXECUTION_BLOCKED" and never.calls == 0)
        save(rich / "production-admission-blocked.json", report)
        web = web_acceptance(rich, snapshot, reviewer, store, value)
    after = protected_hashes()
    save(directory / "historical-hashes-after.json", after)
    require(before == after)
    summary = write_reports(directory, facts, snapshot, assessment, loss, web, len(before))
    # Hash only immutable files after closing all local connections; mutable DBs
    # are evidence snapshots, not authorization or a future paid-request freeze.
    save(directory / "artifact-sha256.json", {p.relative_to(directory).as_posix(): sha(p.read_bytes())
         for p in sorted(directory.rglob("*")) if p.is_file()})
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True, help="NEW directory only")
    print(json.dumps(prepare(parser.parse_args().output_dir), ensure_ascii=False, indent=2))
