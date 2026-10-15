"""Prepare a SYNTHETIC NovaCNC intake demo using the production Draft guard.

All external ports are local fixed data. No model/API/WordPress call is made.
Run from the repository root with --output-dir pointing to a NEW directory.
"""
import argparse
import asyncio
from dataclasses import asdict
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from foreign_trade_geo_agent.core import change_plan as cp
from foreign_trade_geo_agent.core.content_opportunity import ContentOpportunityGeneration, ContentOpportunityGenerationStatus
from foreign_trade_geo_agent.core.evidence_intake import EvidenceRequirement, SupplementMethod
from foreign_trade_geo_agent.core.fetching import HtmlFetchResult, FetchStatus
from foreign_trade_geo_agent.core.history import ArtifactType
from foreign_trade_geo_agent.core.orchestration import EndToEndRunRequest
from foreign_trade_geo_agent.core.research import ResearchGeneration, ResearchGenerationStatus
from foreign_trade_geo_agent.core.search import SearchResponse, SearchResult, SearchStatus
from foreign_trade_geo_agent.evidence_cli import open_planning_evidence
from foreign_trade_geo_agent.runtime import build_planning_workflow

URL = "https://novacnc.example/"
CUSTOMER = "SYNTHETIC-NOVACNC"
SUBJECTS = ("spindle performance", "machining tolerance", "certification scope")
GOAL = "SYNTHETIC NovaCNC: explain VMC-DEMO spindle performance, machining tolerance and certification scope for export buyers."
FACTS = (
    "SYNTHETIC ONLY: VMC-DEMO spindle rated 8000 rpm continuously under DEMO-SPINDLE-1 at 20 C; no cutting-load claim.",
    "SYNTHETIC ONLY: VMC-DEMO test piece tolerance +/-0.02 mm in aluminum at 20 C under DEMO-TEST-2; no other material or production guarantee.",
    "SYNTHETIC ONLY: certificate DEMO-CNC-1 issued by Fictional Lab under DEMO-2026 for VMC-DEMO; expires 2027-01-01; no real certification.",
)


class LocalFetcher:
    @staticmethod
    def result(url, data, content_type):
        return HtmlFetchResult(url, url, FetchStatus.SUCCESS, 200, content_type, data,
            "93.184.216.34", len(data), len(data), 1, (url,), None, None)

    async def fetch_text(self, url, **kwargs):
        assert url == URL + "robots.txt"
        return self.result(url, b"User-agent: *\nAllow: /", "text/plain")

    async def fetch(self, url, **kwargs):
        assert url == URL
        html = ("<html><head><title>SYNTHETIC NovaCNC VMC-DEMO</title>"
            '<meta name="description" content="Fictional local demonstration only"></head>'
            "<body><main><h1>SYNTHETIC NovaCNC</h1><h2>Buyer considerations</h2>"
            "<p>Buyers need to evaluate spindle performance, machining tolerance and certification scope. "
            "This synthetic page names engineering topics only. No model-specific test methods, "
            "applicable conditions, guaranteed tolerances or real certificates are supplied.</p>"
            "</main></body></html>").encode()
        return self.result(url, html, "text/html")


class LocalSearch:
    async def search(self, query):
        return SearchResponse(query, SearchStatus.SUCCESS,
            (SearchResult("SYNTHETIC buyer topics", "https://cnc-guide.example/topics",
                          "; ".join(SUBJECTS), 1.0),), None)


class LocalResearch:
    async def write_report(self, question, materials, target_language):
        return ResearchGeneration("synthetic", "fixed", ResearchGenerationStatus.SUCCESS,
            "SYNTHETIC CNC buyer topic context [S1]", None)


class LocalOpportunity:
    async def write_content_opportunities(self, prompt):
        topic = next(c for c in prompt.topic_candidates if c.text == SUBJECTS[0])
        body = {"opportunities": [{"opportunity_type": "EXPAND_OBSERVED_CONTENT",
            "priority": "HIGH", "topic_ref": topic.candidate_id, "enhancement_action_codes": [],
            "page_refs": ["P1"], "source_refs": ["S1"], "audit_refs": []}]}
        return ContentOpportunityGeneration("synthetic", "fixed",
            ContentOpportunityGenerationStatus.SUCCESS, json.dumps(body), None)


class LocalPlan:
    async def write_change_plan(self, prompt):
        points = [next(c for c in prompt.content_point_candidates_for("R1") if c.text == s) for s in SUBJECTS]
        locator = next(c for c in prompt.locator_candidates_for("R1") if c.target_heading == "Buyer considerations")
        body = {"opportunity_operations": {"R1": {"primary_operation": {
            "source_action_code": "EXPAND_PAGE_SECTION", "operation_type": "EXPAND_SECTION",
            "page_refs": ["P1"], "source_refs": ["S1"], "locator_ref": locator.candidate_id,
            "content_points": [{"intent": "EXPLAIN", "subject_ref": c.candidate_id} for c in points]},
            "secondary_operation": None}}}
        return cp.ChangePlanGeneration("synthetic", "fixed", cp.ChangePlanGenerationStatus.SUCCESS,
                                       json.dumps(body), None)


class NeverDraft:
    calls = 0
    async def write_content_draft(self, prompt):
        self.calls += 1
        raise AssertionError("Synthetic demo must retain production Draft refusal")


def prepare(directory: Path):
    directory.mkdir(parents=True, exist_ok=False)
    db, journal = directory / "history.sqlite3", directory / "intake.sqlite3"
    draft = NeverDraft()
    workflow = build_planning_workflow(db, fetcher=LocalFetcher(), search_provider=LocalSearch(),
        research_writer=LocalResearch(), content_opportunity_writer=LocalOpportunity(),
        change_plan_writer=LocalPlan(), content_draft_writer=draft)
    result = asyncio.run(workflow.run(EndToEndRunRequest(URL, GOAL)))
    assert result.run.failure_kind == "content_draft.invalid_input", result.run
    assert result.terminal_report.error == "INTAKE_EXECUTION_BLOCKED"
    assert draft.calls == 0
    plan_id = next(a.artifact_id for a in result.artifacts if a.artifact_type is ArtifactType.CHANGE_PLAN)
    requirements = tuple(EvidenceRequirement(f"F{i+1}", i, fact,
        f"Explain VMC-DEMO {SUBJECTS[i]} with applicable conditions and exclusions",
        "Synthetic P1/S1 name topics only; model-specific tests, limits and source authority are absent.",
        (SupplementMethod.CUSTOMER_FACT, SupplementMethod.TEXT_DOCUMENT)) for i, fact in enumerate((
            "Spindle rating, duty, model, units, test method and conditions",
            "Tolerance, test piece/material, units, method, conditions and limits",
            "Certificate identifier, issuer, standard, model scope and expiry")))
    def save(name, value):
        (directory / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    save("requirements.json", [asdict(r) for r in requirements])
    status = open_planning_evidence(SimpleNamespace(db=db, intake_db=journal,
        requirements=directory / "requirements.json", customer_id=CUSTOMER), result.run.run_id, plan_id)
    save("01-waiting.json", status)
    supplements = [{"evidence_id": f"E{i+1}", "requirement_ids": [f"F{i+1}"],
        "method": "TEXT_DOCUMENT", "content": fact,
        "source_label": "SYNTHETIC NovaCNC engineering document",
        "source_locator": f"synthetic:VMC-DEMO/document-v1/paragraph-{i+1}",
        "declared_source_owner": "FICTIONAL NovaCNC",
        "file_sha256": hashlib.sha256(fact.encode()).hexdigest(), "supersedes": None}
        for i, fact in enumerate(FACTS)]
    save("submission.json", {"submission_id": "SYNTHETIC-SUBMISSION-1",
        "expected_snapshot_sha256": status["request"]["snapshot_sha256"],
        "supplements": supplements, "scope_adjustment": None})
    metadata = {"synthetic_only": True, "run_id": result.run.run_id, "plan_id": plan_id,
        "customer_id": CUSTOMER, "db": str(db.resolve()), "intake_db": str(journal.resolve()),
        "draft_writer_calls": draft.calls, "original_run_status": result.run.status.value,
        "original_draft_error": result.terminal_report.error,
        "prepared_at": datetime.now(UTC).isoformat()}
    save("demo.json", metadata)
    return metadata


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    print(json.dumps(prepare(parser.parse_args().output_dir), ensure_ascii=False, indent=2))
