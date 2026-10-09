from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from foreign_trade_geo_agent.core.orchestration import EndToEndRunRequest
from foreign_trade_geo_agent.web.app import create_app
from foreign_trade_geo_agent.web.composition import build_live_composition
from foreign_trade_geo_agent.web.jobs import LocalJobRegistry
from foreign_trade_geo_agent.web.live_application import LiveApplicationService
from tests.test_mvp_composed_flow import (
    SITE_URL,
    _FixtureChangePlanWriter,
    _FixtureContentDraftWriter,
    _FixtureFetcher,
    _FixtureOpportunityWriter,
    _FixtureResearchWriter,
    _FixtureSearchProvider,
)


SEO_GOAL = "Improve industrial pump organic search visibility"


def _live_composition(db_path: Path):
    return build_live_composition(
        db_path,
        provider_configuration_ready=True,
        fetcher=_FixtureFetcher(),
        search_provider=_FixtureSearchProvider(),
        research_writer=_FixtureResearchWriter(),
        content_opportunity_writer=_FixtureOpportunityWriter(),
        change_plan_writer=_FixtureChangePlanWriter(),
        content_draft_writer=_FixtureContentDraftWriter(),
    )


class LiveResultsTests(unittest.IsolatedAsyncioTestCase):
    async def _rendered_pages(self, directory: str):
        live_db_path = Path(directory) / "live.sqlite3"
        composition = _live_composition(live_db_path)
        result = await composition.planning_workflow().run(
            EndToEndRunRequest(SITE_URL, SEO_GOAL, "en")
        )
        run_id = result.run.run_id
        service = LiveApplicationService(composition, LocalJobRegistry())
        draft_id = service.load_change_plan(run_id).draft_id
        self.assertIsNone(draft_id)
        self.assertEqual(result.terminal_report.error, "INTAKE_EXECUTION_BLOCKED")

        def live_factory(path: Path, jobs: LocalJobRegistry):
            return LiveApplicationService(_live_composition(path), jobs)

        with TestClient(
            create_app(
                db_path=Path(directory) / "demo.sqlite3",
                live_db_path=live_db_path,
                live_service_factory=live_factory,
            )
        ) as client:
            results = client.get(f"/live/runs/{run_id}/results")
            changes = client.get(f"/live/runs/{run_id}/changes")
            draft = client.get(f"/live/runs/{run_id}/drafts/D1")
        return results, changes, draft

    async def test_results_show_persisted_live_target_goal_and_language(self) -> None:
        with TemporaryDirectory() as directory:
            results, _changes, _draft = await self._rendered_pages(directory)

        self.assertEqual(results.status_code, 200)
        self.assertIn(SITE_URL, results.text)
        self.assertIn("example.com", results.text)
        self.assertIn(SEO_GOAL, results.text)
        self.assertIn("English", results.text)

    async def test_results_show_crawl_derived_audit_evidence(self) -> None:
        with TemporaryDirectory() as directory:
            results, _changes, _draft = await self._rendered_pages(directory)

        self.assertIn("crawl-seo-audit", results.text)
        self.assertIn("Crawl Robots Allowed", results.text)
        self.assertIn("crawl.robots.allowed", results.text)

    async def test_change_plan_keeps_external_context_separate_from_website_evidence(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            _results, changes, _draft = await self._rendered_pages(directory)

        self.assertEqual(changes.status_code, 200)
        self.assertIn("Website Evidence", changes.text)
        self.assertIn("External Research", changes.text)
        self.assertIn("External context — not website evidence.", changes.text)

    async def test_unapproved_draft_is_unavailable_after_native_planning(self) -> None:
        with TemporaryDirectory() as directory:
            _results, _changes, draft = await self._rendered_pages(directory)

        self.assertNotEqual(draft.status_code, 200)
        self.assertNotIn("WordPress Delivery", draft.text)
        self.assertNotIn("Verification", draft.text)
        self.assertNotIn("Continue to", draft.text)

    async def test_live_pages_contain_no_novacnc_demo_fixture_or_wordpress_copy(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            pages = await self._rendered_pages(directory)

        combined = "\n".join(response.text for response in pages[:2])
        for forbidden in ("NovaCNC", "Demo Mode", "WordPress"):
            self.assertNotIn(forbidden, combined)


if __name__ == "__main__":
    unittest.main()
