"""Production denial and independent synthetic intake acceptance, no live I/O."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from foreign_trade_geo_agent.adapters.deepseek_content_draft import DeepSeekContentDraftWriter
from foreign_trade_geo_agent.core import change_plan as cp
from foreign_trade_geo_agent.core.content_draft import ContentDraftInput, build_content_draft_prompt
from foreign_trade_geo_agent.core.content_opportunity import ContentOpportunityGeneration, ContentOpportunityGenerationStatus
from foreign_trade_geo_agent.core.evidence_intake import (
    CustomerContext, CustomerSubmission, EvidenceRequirement, EvidenceTask,
    Supplement, SupplementMethod, snapshot_digest,
)
from foreign_trade_geo_agent.core.fetching import FetchStatus, HtmlFetchResult
from foreign_trade_geo_agent.core.history import ArtifactType
from foreign_trade_geo_agent.core.orchestration import EndToEndRunRequest, EndToEndStage
from foreign_trade_geo_agent.core.p_only_draft import POnlyDraftRequestV1
from foreign_trade_geo_agent.core.research import ResearchGeneration, ResearchGenerationStatus
from foreign_trade_geo_agent.core.search import SearchResponse, SearchResult, SearchStatus
from foreign_trade_geo_agent.runtime import build_planning_workflow
from foreign_trade_geo_agent.storage.evidence_intake import SQLiteEvidenceIntakeStore
from foreign_trade_geo_agent.workflows.change_plan import ChangePlanWorkflow
from foreign_trade_geo_agent.workflows.content_draft import ContentDraftWorkflow
from foreign_trade_geo_agent.workflows.evidence_intake import EvidenceIntakeDraftAdmission, EvidenceIntakeWorkflow


NOW = datetime(2026, 10, 9, 8, tzinfo=UTC)
URL = "https://bellharbor.example/products/f9"
PROJECT, CUSTOMER, TASK = "SYNTHETIC-BELLHARBOR", "FICTIONAL-FILTER-EXPORTER", "EXPLAIN-F9"
SUBJECTS = ("filter retention", "housing compatibility")
FACTS = (
    "Synthetic F9 retention: 10 micrometres in water at 15 C using TEST-RETENTION; no aerosol claim.",
    "Synthetic F9 housing: polypropylene, water at 5-30 C under TEST-HOUSING; solvents excluded.",
)


class Fetcher:
    async def fetch_text(self, url, **kwargs):
        assert url == "https://bellharbor.example/robots.txt"
        return self.result(url, b"User-agent: *\nAllow: /", "text/plain")

    async def fetch(self, url, **kwargs):
        assert url == URL
        return self.result(url, b"<html><head><title>BellHarbor F9 filters</title>"
            b'<meta name="description" content="Synthetic F9 export filters">'
            b'<link rel="canonical" href="https://bellharbor.example/products/f9"></head><body><main>'
            b"<h1>F9 filter</h1><h2>Filter data</h2><p>filter retention; housing compatibility</p>"
            b"</main></body></html>", "text/html")

    @staticmethod
    def result(url, data, content_type):
        return HtmlFetchResult(url, url, FetchStatus.SUCCESS, 200, content_type, data,
            "93.184.216.34", len(data), len(data), 1, (url,), None, None)


class Search:
    async def search(self, query):
        return SearchResponse(query, SearchStatus.SUCCESS,
            (SearchResult("filter retention", "https://context.example/filters", "; ".join(SUBJECTS), 1.0),), None)


class Research:
    async def write_report(self, question, materials, target_language):
        return ResearchGeneration("synthetic", "fixture", ResearchGenerationStatus.SUCCESS, "Filter topic context [S1]", None)


class Opportunities:
    async def write_content_opportunities(self, prompt):
        topic = next(c for c in prompt.topic_candidates if c.text == SUBJECTS[0])
        value = {"opportunities": [{"opportunity_type": "EXPAND_OBSERVED_CONTENT", "priority": "HIGH",
            "topic_ref": topic.candidate_id, "enhancement_action_codes": [], "page_refs": ["P1"],
            "source_refs": ["S1"], "audit_refs": []}]}
        return ContentOpportunityGeneration("synthetic", "fixture", ContentOpportunityGenerationStatus.SUCCESS, json.dumps(value), None)


class Planner:
    def __init__(self, during=None):
        self.prompts, self.during = [], during

    async def write_change_plan(self, prompt):
        self.prompts.append(prompt)
        if self.during:
            self.during()
        points = [next(c for c in prompt.content_point_candidates_for("R1") if c.text == s) for s in SUBJECTS]
        locator = next(c for c in prompt.locator_candidates_for("R1") if c.target_heading == "Filter data")
        op = {"source_action_code": "EXPAND_PAGE_SECTION", "operation_type": "EXPAND_SECTION",
            "page_refs": ["P1"], "source_refs": ["S1"], "locator_ref": locator.candidate_id,
            "content_points": [{"intent": "EXPLAIN", "subject_ref": p.candidate_id} for p in points]}
        return cp.ChangePlanGeneration("synthetic", "fixture", cp.ChangePlanGenerationStatus.SUCCESS,
            json.dumps({"opportunity_operations": {"R1": {"primary_operation": op, "secondary_operation": None}}}), None)


class Writer:
    def __init__(self):
        self.calls = 0

    async def write_content_draft(self, prompt):
        self.calls += 1
        raise AssertionError("No synthetic customer Draft permission")


class PermissiveLegacyAdmission:
    def rejection_reason(self, value):
        return None


class DraftExecutionBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.writer = Writer()

    def runtime(self, admission=None):
        return build_planning_workflow(self.root / "history.sqlite", fetcher=Fetcher(),
            search_provider=Search(), research_writer=Research(), content_opportunity_writer=Opportunities(),
            change_plan_writer=Planner(), content_draft_writer=self.writer, intake_admission=admission)

    def initial_input(self):
        runtime = self.runtime()
        result = asyncio.run(runtime.run(EndToEndRunRequest(URL, "Explain F9 retention and housing limitations")))
        self.assertEqual(result.stopped_stage, EndToEndStage.CONTENT_DRAFT)
        self.assertEqual(result.terminal_report.error, "INTAKE_EXECUTION_BLOCKED")
        self.assertEqual(self.writer.calls, 0)
        records = runtime._history_store.list_artifacts(result.run.run_id)
        values = {a.artifact_type: a.payload for a in records}
        self.assertNotIn(ArtifactType.CONTENT_DRAFT, values)
        self.assertEqual(len(values), 5)
        return ContentDraftInput(values[ArtifactType.SITE_CONTENT], values[ArtifactType.CONTENT_OPPORTUNITY],
                                 values[ArtifactType.CHANGE_PLAN])

    def test_default_runtime_preserves_native_artifacts_and_refuses_before_writer(self):
        self.initial_input()

    def test_production_runtime_cannot_be_unlocked_by_permissive_old_admission(self):
        runtime = self.runtime(PermissiveLegacyAdmission())
        result = asyncio.run(runtime.run(EndToEndRunRequest(URL, "Explain F9 filters")))
        self.assertEqual(result.stopped_stage, EndToEndStage.CONTENT_DRAFT)
        self.assertEqual(result.terminal_report.error, "INTAKE_EXECUTION_BLOCKED")
        self.assertEqual(self.writer.calls, 0)

    def test_bound_low_level_workflow_cannot_treat_binding_only_as_authorization(self):
        value = self.initial_input()
        result = asyncio.run(ContentDraftWorkflow(self.writer, intake_admission=PermissiveLegacyAdmission()).run(value))
        self.assertEqual(result.error, "INTAKE_EXECUTION_BLOCKED")
        self.assertEqual(self.writer.calls, 0)

    def test_direct_default_provider_refuses_before_http_even_with_key(self):
        value = self.initial_input()
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "synthetic-placeholder"}), patch(
                "httpx.AsyncClient", side_effect=AssertionError("No live client")):
            result = asyncio.run(DeepSeekContentDraftWriter().write_content_draft(build_content_draft_prompt(value, "C1")))
        self.assertEqual(result.status.value, "failed")
        self.assertEqual(result.error, "DRAFT_EXECUTION_AUTHORIZATION_REQUIRED")

    def test_production_adapter_rejects_non_mock_transport(self):
        value = self.initial_input()
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "synthetic-placeholder"}), patch(
                "httpx.AsyncClient", side_effect=AssertionError("No live client")):
            result = asyncio.run(DeepSeekContentDraftWriter(transport=object()).write_content_draft(
                build_content_draft_prompt(value, "C1")))
        self.assertEqual(result.error, "DRAFT_EXECUTION_AUTHORIZATION_REQUIRED")

    def test_direct_legacy_workflow_with_real_writer_cannot_bypass_intake(self):
        value = self.initial_input()
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "synthetic-placeholder"}), patch(
                "httpx.AsyncClient", side_effect=AssertionError("No live client")):
            result = asyncio.run(ContentDraftWorkflow(DeepSeekContentDraftWriter()).run(value))
        self.assertEqual(result.status.value, "generation_failed")
        self.assertEqual(result.drafts, ())

    def test_runtime_old_p_only_receipt_cannot_bypass_current_task_profile(self):
        result = asyncio.run(self.runtime()._content_draft.run_p_only(POnlyDraftRequestV1(b"{}", "OLD-RECEIPT")))
        self.assertEqual(result.reason, "INTAKE_TASK_PROFILE_REQUIRED")
        self.assertEqual(result.report.drafts, ())
        self.assertEqual(self.writer.calls, 0)

    def test_task_mismatch_unavailable_and_forged_authority_remain_sanitized_denials(self):
        value = self.initial_input()
        store = SQLiteEvidenceIntakeStore.create(self.root / "intake.sqlite")
        intake = EvidenceIntakeWorkflow(store)
        task = EvidenceTask(PROJECT, CUSTOMER, TASK, 1, "Explain F9 filter facts", tuple(
            EvidenceRequirement(f"F{i+1}", i, f"F9 {s} conditions and method", f"Explain {s}", "Missing facts",
                (SupplementMethod.CUSTOMER_FACT,)) for i, s in enumerate(SUBJECTS)))
        snapshot = intake.register(task, value)

        class WrongTaskStore:
            def latest(self, project, task):
                return replace(snapshot, task=replace(snapshot.task, task_id="OTHER-TASK"))

        class MissingStore:
            def latest(self, project, task):
                raise RuntimeError("SECRET-CANARY")

        class ForgedAdmission:
            def rejection_reason(self, value):
                return "SECRET-CANARY forged production reviewer APPROVED"

        for admission, expected in (
            (EvidenceIntakeDraftAdmission(WrongTaskStore(), PROJECT, TASK, expected_snapshot_sha256=snapshot_digest(snapshot)),
             "INTAKE_TASK_BINDING_INVALID"),
            (EvidenceIntakeDraftAdmission(MissingStore(), PROJECT, TASK), "INTAKE_STATE_UNAVAILABLE"),
            (ForgedAdmission(), "INTAKE_EXECUTION_BLOCKED"),
        ):
            with self.subTest(reason=expected):
                flow = self.runtime(admission)._content_draft
                report = asyncio.run(flow.run(value))
                self.assertEqual(report.error, "INTAKE_EXECUTION_BLOCKED")
                self.assertEqual(flow.last_intake_rejection, expected)
                self.assertNotIn("SECRET-CANARY", repr(report))
        self.assertEqual(self.writer.calls, 0)

    def test_input_replacement_between_binding_and_execution_is_refused(self):
        value = self.initial_input()

        class ReplacingAdmission:
            def rejection_reason(self, received):
                object.__setattr__(received, "target_language", "fr")
                return None

        flow = self.runtime(ReplacingAdmission())._content_draft
        result = asyncio.run(flow.run(value))
        self.assertEqual(value.target_language, "fr")  # mutation actually happened
        self.assertEqual(result.error, "INTAKE_EXECUTION_BLOCKED")
        self.assertEqual(self.writer.calls, 0)

    def test_concurrent_update_after_binding_read_cannot_open_writer_window(self):
        value = self.initial_input()
        store = SQLiteEvidenceIntakeStore.create(self.root / "intake.sqlite")
        intake = EvidenceIntakeWorkflow(store)
        task = EvidenceTask(PROJECT, CUSTOMER, TASK, 1, "Explain F9 filter facts", tuple(
            EvidenceRequirement(f"F{i+1}", i, f"F9 {s} conditions and method", f"Explain {s}", "Missing facts",
                (SupplementMethod.CUSTOMER_FACT,)) for i, s in enumerate(SUBJECTS)))
        original = intake.register(task, value)
        digest = snapshot_digest(original)
        submission = CustomerSubmission("CONCURRENT-SUB", digest, (Supplement("E1", ("F1",),
            SupplementMethod.CUSTOMER_FACT, FACTS[0], "Synthetic engineering", "F9/paragraph-1", "BellHarbor"),))

        class RacingStore:
            def latest(self, project, task):
                snapshot = store.latest(project, task)
                with ThreadPoolExecutor(max_workers=1) as pool:
                    pool.submit(intake.submit, PROJECT, TASK, submission,
                        customer=CustomerContext(CUSTOMER, "SYNTHETIC-ENGINEER", NOW)).result(timeout=10)
                return snapshot  # now demonstrably stale, although its digest matches

        flow = self.runtime(EvidenceIntakeDraftAdmission(RacingStore(), PROJECT, TASK,
            expected_snapshot_sha256=digest))._content_draft
        report = asyncio.run(flow.run(value))
        current = store.latest(PROJECT, TASK)
        self.assertEqual(current.evidence_version, 2)
        self.assertFalse(current.plan_bound)
        self.assertNotEqual(snapshot_digest(current), digest)
        self.assertEqual(report.error, "INTAKE_EXECUTION_BLOCKED")
        self.assertEqual(self.writer.calls, 0)
        flow = self.runtime(EvidenceIntakeDraftAdmission(store, PROJECT, TASK, expected_snapshot_sha256=digest))._content_draft
        self.assertEqual(asyncio.run(flow.run(value)).error, "INTAKE_EXECUTION_BLOCKED")
        self.assertEqual(flow.last_intake_rejection, "STALE_INTAKE_BINDING")

    def test_isolated_root_has_no_provider_defaults_or_production_enable_flag(self):
        from foreign_trade_geo_agent.runtime import build_isolated_test_planning_workflow
        with self.assertRaisesRegex(ValueError, "ISOLATED_TEST_PORTS_REQUIRED"):
            build_isolated_test_planning_workflow(self.root / "test.sqlite", fetcher=None, search_provider=None,
                research_writer=None, content_opportunity_writer=None, change_plan_writer=None, content_draft_writer=None)
        self.assertFalse((self.root / "test.sqlite").exists())
        with self.assertRaises(TypeError):
            build_planning_workflow(self.root / "enable.sqlite", approved=True)
        self.assertFalse((self.root / "enable.sqlite").exists())

    def test_default_cli_factory_denies_with_five_native_artifacts(self):
        from tests.test_cli import invoke_main
        from foreign_trade_geo_agent.storage.sqlite import SQLiteHistoryStore
        db = self.root / "cli.sqlite"
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "synthetic-placeholder", "TAVILY_API_KEY": "synthetic-placeholder"}), patch(
                "foreign_trade_geo_agent.cli.load_runtime_environment"), patch.multiple(
                "foreign_trade_geo_agent.runtime", SafeHtmlFetcher=lambda **kw: Fetcher(),
                TavilySearchAdapter=Search, DeepSeekResearchWriter=Research, DeepSeekContentOpportunityWriter=Opportunities,
                DeepSeekChangePlanWriter=Planner, DeepSeekContentDraftWriter=lambda: self.writer):
            code, output, errors = invoke_main(["plan", "--site", URL, "--question", "Explain F9 limitations", "--db", str(db)])
        payload = json.loads(output)
        self.assertEqual((code, errors), (1, ""))
        self.assertEqual(len(SQLiteHistoryStore(db).list_artifacts(payload["run_id"])), 5)
        self.assertEqual(self.writer.calls, 0)

    def test_live_post_runs_shared_production_boundary_and_cannot_accept_forged_flags(self):
        from fastapi.testclient import TestClient
        from foreign_trade_geo_agent.web.app import create_app
        from foreign_trade_geo_agent.web.composition import build_live_composition
        from foreign_trade_geo_agent.web.live_application import LiveApplicationService
        from tests.test_web_live_routes import _csrf
        from tests.test_web_live_application import _wait_terminal
        holders = {}

        def factory(path, jobs):
            composition = build_live_composition(path, provider_configuration_ready=True, fetcher=Fetcher(),
                search_provider=Search(), research_writer=Research(), content_opportunity_writer=Opportunities(),
                change_plan_writer=Planner(), content_draft_writer=self.writer)
            holders.update(composition=composition, jobs=jobs)
            return LiveApplicationService(composition, jobs)

        with TestClient(create_app(db_path=self.root / "demo.sqlite", live_db_path=self.root / "live.sqlite",
                                  live_service_factory=factory)) as client:
            token = _csrf(client.get("/live/start").text)
            response = client.post("/live/analyses", headers={"Host": "127.0.0.1:8000"},
                data={"csrf_token": token, "website_url": URL, "seo_goal": "Explain F9 limitations",
                    "task_id": TASK, "approved": "true", "reviewer_id": "owner", "draft_authorized": "true"},
                follow_redirects=False)
            self.assertEqual(response.status_code, 303)
            job = client.portal.call(_wait_terminal, holders["jobs"], response.headers["location"].rsplit("/", 1)[-1])
            records = holders["composition"].history_reader.list_artifacts(job.run_id)
            self.assertEqual(len(records), 5)
            self.assertEqual(client.get(f"/live/runs/{job.run_id}/changes").status_code, 200)
            self.assertEqual(client.get(f"/live/runs/{job.run_id}/drafts/D1").status_code, 503)
        self.assertEqual(self.writer.calls, 0)

    def test_independent_customer_partial_complete_replanning_still_waits_for_human(self):
        value = self.initial_input()
        store = SQLiteEvidenceIntakeStore.create(self.root / "intake.sqlite")
        intake = EvidenceIntakeWorkflow(store)
        requirements = tuple(EvidenceRequirement(f"F{i+1}", i, fact, f"Explain F9 {SUBJECTS[i]} with limits",
            "Native P/S mention topics only", (SupplementMethod.CUSTOMER_FACT,)) for i, fact in enumerate((
                "Retention units, model, fluid, temperature and test method", "Housing material, media, temperature and exclusions")))
        task = EvidenceTask(PROJECT, CUSTOMER, TASK, 1, "Explain both F9 buyer facts without reducing depth", requirements)
        original = intake.register(task, value)
        customer = CustomerContext(CUSTOMER, "SYNTHETIC-ENGINEER", NOW)
        request = intake.customer_request(PROJECT, TASK, now=NOW)
        self.assertEqual(tuple(g.requirement.requirement_id for g in request.gaps), ("F1", "F2"))
        versions = [original]
        for i in (1, 2):
            supplement = Supplement(f"E{i}", (f"F{i}",), SupplementMethod.CUSTOMER_FACT, FACTS[i-1],
                "Synthetic engineering statement", f"F9/paragraph-{i}", "Fictional BellHarbor")
            updated = intake.submit(PROJECT, TASK, CustomerSubmission(f"SUB-{i}", snapshot_digest(versions[-1]), (supplement,)),
                                    customer=customer)
            self.assertEqual(updated.task, task)
            self.assertFalse(updated.plan_bound)
            versions.append(updated)
            planner = Planner()
            candidate = asyncio.run(intake.replan(PROJECT, TASK, expected_sha256=snapshot_digest(updated),
                planner=ChangePlanWorkflow(planner), now=NOW))
            versions.append(candidate.snapshot)
            self.assertEqual(planner.prompts[0].input.customer_context.snapshot, updated)
            self.assertFalse(candidate.draft_authorized)
            self.assertEqual(candidate.snapshot.task, task)
            if i == 1:
                self.assertEqual(tuple(g.requirement.requirement_id for g in candidate.check.gaps
                    if g.reason_code == "MISSING_CUSTOMER_EVIDENCE"), ("F2",))
                self.assertTrue(candidate.return_to_intake)
        self.assertFalse(candidate.return_to_intake)
        self.assertTrue(all(c.verdict.value == "UNREVIEWED" for c in candidate.claims))
        self.assertEqual((candidate.snapshot.evidence_version, candidate.snapshot.plan_version, candidate.snapshot.revision), (3, 3, 5))
        self.assertEqual(len({snapshot_digest(s) for s in versions}), 5)
        for old in versions:
            for supplied_digest in (snapshot_digest(old), snapshot_digest(candidate.snapshot)):
                flow = self.runtime(EvidenceIntakeDraftAdmission(store, PROJECT, TASK, expected_snapshot_sha256=supplied_digest))
                result = asyncio.run(flow._content_draft.run(old.planning_input))
                self.assertEqual(result.error, "INTAKE_EXECUTION_BLOCKED")
        # Equal wording is not an evidence epoch. The original input can be equal
        # to the fresh plan; neither request has an executable purpose.
        self.assertEqual(self.writer.calls, 0)


if __name__ == "__main__":
    unittest.main()
