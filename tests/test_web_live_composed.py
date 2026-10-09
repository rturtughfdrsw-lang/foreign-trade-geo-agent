from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from foreign_trade_geo_agent.core.history import ArtifactType
from foreign_trade_geo_agent.core.orchestration import EndToEndRunRequest
from foreign_trade_geo_agent.web.app import create_app
from foreign_trade_geo_agent.web.application import DemoApplicationService
from foreign_trade_geo_agent.web.composition import build_demo_composition
from foreign_trade_geo_agent.web.demo_boundaries import (
    DEMO_RESEARCH_QUESTION,
    DEMO_SITE_URL,
    DEMO_TARGET_LANGUAGE,
)
from foreign_trade_geo_agent.web.jobs import LocalJobRegistry
from foreign_trade_geo_agent.web.live_application import (
    LiveApplicationService,
)
from tests.live_composed_fixtures import (
    ALPHA_URL,
    BETA_URL,
    live_composition,
)


ALPHA_GOAL = "Improve Alpha organic visibility"
BETA_GOAL = "Improve Beta organic visibility"


async def _run_live(db_path: Path, url: str, identity: str, goal: str):
    composition = live_composition(db_path, url, identity)
    result = await composition.planning_workflow().run(
        EndToEndRunRequest(url, goal, "en")
    )
    return composition, result


class LiveComposedTests(unittest.IsolatedAsyncioTestCase):
    async def test_generic_domain_runs_native_planning_without_novacnc_and_stops_before_draft(self) -> None:
        with TemporaryDirectory() as directory:
            composition, result = await _run_live(
                Path(directory) / "live.sqlite3",
                ALPHA_URL,
                "Alpha Flow",
                ALPHA_GOAL,
            )
            service = LiveApplicationService(composition, LocalJobRegistry())
            view = service.load_change_plan(result.run.run_id)
            plan = next(a.payload for a in composition.history_reader.list_artifacts(result.run.run_id)
                        if a.artifact_type is ArtifactType.CHANGE_PLAN)

        self.assertTrue(plan.requires_human_review)
        self.assertEqual(result.terminal_report.error, "INTAKE_EXECUTION_BLOCKED")
        self.assertEqual(len(result.artifacts), 5)
        self.assertIsNone(view.draft_id)
        self.assertNotIn("NovaCNC", repr(view))

    async def test_alpha_and_beta_domains_persist_independent_inputs_and_artifacts(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            db_path = Path(directory) / "live.sqlite3"
            alpha, alpha_result = await _run_live(
                db_path, ALPHA_URL, "Alpha Flow", ALPHA_GOAL
            )
            beta, beta_result = await _run_live(
                db_path, BETA_URL, "Beta Flow", BETA_GOAL
            )
            alpha_input = beta.history_reader.get_analysis_run_input(
                alpha_result.run.run_id
            )
            beta_input = beta.history_reader.get_analysis_run_input(
                beta_result.run.run_id
            )
            alpha_artifacts = beta.history_reader.list_artifacts(
                alpha_result.run.run_id
            )
            beta_artifacts = beta.history_reader.list_artifacts(beta_result.run.run_id)

        self.assertEqual(alpha_input.website_url, ALPHA_URL)
        self.assertEqual(beta_input.website_url, BETA_URL)
        self.assertEqual(len(alpha_artifacts), 5)
        self.assertEqual(len(beta_artifacts), 5)
        self.assertNotIn(ArtifactType.CONTENT_DRAFT, {a.artifact_type for a in alpha_artifacts + beta_artifacts})
        self.assertTrue(all(item.run_id == alpha_result.run.run_id for item in alpha_artifacts))
        self.assertTrue(all(item.run_id == beta_result.run.run_id for item in beta_artifacts))

    async def test_each_results_page_displays_only_its_own_target(self) -> None:
        with TemporaryDirectory() as directory:
            live_db = Path(directory) / "live.sqlite3"
            _alpha, alpha_result = await _run_live(
                live_db, ALPHA_URL, "Alpha Flow", ALPHA_GOAL
            )
            _beta, beta_result = await _run_live(
                live_db, BETA_URL, "Beta Flow", BETA_GOAL
            )

            def live_factory(path: Path, jobs: LocalJobRegistry):
                return LiveApplicationService(
                    live_composition(path, ALPHA_URL, "unused"),
                    jobs,
                )

            with TestClient(
                create_app(
                    db_path=Path(directory) / "demo.sqlite3",
                    live_db_path=live_db,
                    live_service_factory=live_factory,
                )
            ) as client:
                alpha_html = client.get(
                    f"/live/runs/{alpha_result.run.run_id}/results"
                ).text
                beta_html = client.get(
                    f"/live/runs/{beta_result.run.run_id}/results"
                ).text

        self.assertIn(ALPHA_URL, alpha_html)
        self.assertNotIn(BETA_URL, alpha_html)
        self.assertIn(BETA_URL, beta_html)
        self.assertNotIn(ALPHA_URL, beta_html)

    async def test_live_run_id_cannot_be_read_through_demo_service(self) -> None:
        with TemporaryDirectory() as directory:
            demo_db = Path(directory) / "demo.sqlite3"
            live_db = Path(directory) / "live.sqlite3"
            _live, live_result = await _run_live(
                live_db, ALPHA_URL, "Alpha Flow", ALPHA_GOAL
            )
            demo = DemoApplicationService(
                build_demo_composition(demo_db),
                LocalJobRegistry(),
            )

            with self.assertRaises(Exception):
                demo.load_results(live_result.run.run_id)

    async def test_demo_run_id_cannot_be_read_through_live_service(self) -> None:
        with TemporaryDirectory() as directory:
            demo_db = Path(directory) / "demo.sqlite3"
            live_db = Path(directory) / "live.sqlite3"
            demo_composition = build_demo_composition(demo_db)
            demo_result = await demo_composition.planning_workflow().run(
                EndToEndRunRequest(
                    DEMO_SITE_URL,
                    DEMO_RESEARCH_QUESTION,
                    DEMO_TARGET_LANGUAGE,
                )
            )

            def live_factory(path: Path, jobs: LocalJobRegistry):
                return LiveApplicationService(
                    live_composition(path, ALPHA_URL, "unused"), jobs
                )

            with TestClient(
                create_app(
                    db_path=demo_db,
                    live_db_path=live_db,
                    live_service_factory=live_factory,
                )
            ) as client:
                response = client.get(
                    f"/live/runs/{demo_result.run.run_id}/results"
                )

        self.assertEqual(response.status_code, 404)
        self.assertNotIn(DEMO_SITE_URL, response.text)

    async def test_demo_and_live_databases_never_cross_query(self) -> None:
        with TemporaryDirectory() as directory:
            demo_db = Path(directory) / "demo.sqlite3"
            live_db = Path(directory) / "live.sqlite3"
            demo = build_demo_composition(demo_db)
            demo_result = await demo.planning_workflow().run(
                EndToEndRunRequest(
                    DEMO_SITE_URL,
                    DEMO_RESEARCH_QUESTION,
                    DEMO_TARGET_LANGUAGE,
                )
            )
            live, live_result = await _run_live(
                live_db, ALPHA_URL, "Alpha Flow", ALPHA_GOAL
            )
            self.assertIsNone(demo.history_reader.get_run(live_result.run.run_id))
            self.assertIsNone(live.history_reader.get_run(demo_result.run.run_id))

    async def test_live_composed_flow_never_constructs_wordpress_adapter(self) -> None:
        with TemporaryDirectory() as directory, patch(
            "foreign_trade_geo_agent.web.composition.WordPressRestDraftPublisher",
            side_effect=AssertionError("WordPress adapter constructed"),
        ):
            _composition, result = await _run_live(
                Path(directory) / "live.sqlite3",
                ALPHA_URL,
                "Alpha Flow",
                ALPHA_GOAL,
            )

        self.assertEqual(
            tuple(item.artifact_type for item in result.artifacts),
            (
                ArtifactType.SITE_CONTENT,
                ArtifactType.SITE_AUDIT,
                ArtifactType.INDUSTRY_RESEARCH,
                ArtifactType.CONTENT_OPPORTUNITY,
                ArtifactType.CHANGE_PLAN,
            ),
        )


if __name__ == "__main__":
    unittest.main()
