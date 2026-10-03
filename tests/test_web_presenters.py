from __future__ import annotations

from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from foreign_trade_geo_agent.core.orchestration import EndToEndRunRequest
from foreign_trade_geo_agent.core.history import ArtifactType
from foreign_trade_geo_agent.web.application import DemoApplicationService
from foreign_trade_geo_agent.web.composition import build_demo_composition
from foreign_trade_geo_agent.web.demo_boundaries import (
    DEMO_RESEARCH_QUESTION,
    DEMO_SITE_URL,
    DEMO_TARGET_LANGUAGE,
)
from foreign_trade_geo_agent.web.jobs import LocalJobRegistry


class DemoPresenterTests(unittest.IsolatedAsyncioTestCase):
    async def _service_with_run(
        self,
        directory: str,
    ) -> tuple[DemoApplicationService, str]:
        composition = build_demo_composition(Path(directory) / "history.sqlite3")
        result = await composition.planning_workflow().run(
            EndToEndRunRequest(
                DEMO_SITE_URL,
                DEMO_RESEARCH_QUESTION,
                DEMO_TARGET_LANGUAGE,
            )
        )
        return (
            DemoApplicationService(composition, LocalJobRegistry()),
            result.run.run_id,
        )

    async def test_results_are_recovered_from_sqlite_with_a_p_r_metadata(self) -> None:
        with TemporaryDirectory() as directory:
            service, run_id = await self._service_with_run(directory)

            view = service.load_results(run_id)

            self.assertEqual(view.run_id, run_id)
            self.assertEqual((view.audit_score, view.audit_band), (78, "needs improvement"))
            self.assertEqual(
                tuple(item.evidence_id for item in view.audit_observations),
                ("A1", "A2"),
            )
            self.assertEqual(
                tuple(item.evidence_id for item in view.website_evidence),
                ("P1", "P2"),
            )
            self.assertEqual(
                tuple(item.recommendation_id for item in view.opportunities),
                ("R1",),
            )
            self.assertIn("NovaCNC supplies", view.website_evidence[0].excerpt or "")
            self.assertEqual(view.website_evidence[0].page_label, "Home page")
            self.assertEqual(view.website_evidence[1].page_label, "Machine page")
            self.assertEqual(view.seo_health_label, "Needs improvement")
            self.assertEqual(view.key_observation_count, 2)
            self.assertEqual(view.high_priority_opportunity_count, 1)
            self.assertEqual(
                view.key_findings,
                (
                    "Existing product content is present across 2 captured pages.",
                    "Buyer-selection guidance was not detected by the audit.",
                    "One high-priority content opportunity was identified.",
                ),
            )

    async def test_change_plan_separates_three_evidence_classes(self) -> None:
        with TemporaryDirectory() as directory:
            service, run_id = await self._service_with_run(directory)

            view = service.load_change_plan(run_id)

            self.assertEqual(len(view.changes), 1)
            change = view.changes[0]
            self.assertEqual(change.change_id, "C1")
            self.assertEqual(change.title, "Expand existing product content")
            self.assertEqual(change.target_label, "Precision CNC Machinery")
            self.assertEqual(change.priority, "HIGH")
            self.assertNotIn("Observed page evidence P1", change.why)
            self.assertEqual(
                tuple(item.evidence_id for item in change.website_evidence),
                ("P1",),
            )
            self.assertEqual(
                tuple(item.evidence_id for item in change.audit_evidence),
                ("A1",),
            )
            self.assertEqual(
                tuple(item.evidence_id for item in change.external_research),
                ("S1",),
            )
            self.assertTrue(
                all(item.evidence_class == "Website Evidence" for item in change.website_evidence)
            )
            self.assertTrue(
                all(item.evidence_class == "SEO Audit Evidence" for item in change.audit_evidence)
            )
            self.assertTrue(
                all(item.evidence_class == "External Research" for item in change.external_research)
            )
            audit = change.audit_evidence[0]
            self.assertEqual(audit.title, "Selection guidance")
            self.assertEqual(audit.detail, "Not detected")
            self.assertEqual(audit.outcome, "ABSENT")
            self.assertEqual(view.draft_id, "D1")

    async def test_not_detected_is_not_presented_as_confirmed_missing(self) -> None:
        with TemporaryDirectory() as directory:
            service, run_id = await self._service_with_run(directory)

            observation = next(
                item
                for item in service.load_results(run_id).audit_observations
                if item.evidence_id == "A2"
            )

            self.assertEqual(observation.outcome, "NOT_DETECTED")
            self.assertIn("Audit outcome: NOT_DETECTED", observation.description)
            self.assertNotIn("confirmed missing", observation.description.casefold())

    async def test_navigation_uses_persisted_artifacts_for_valid_destinations(self) -> None:
        with TemporaryDirectory() as directory:
            service, run_id = await self._service_with_run(directory)

            navigation = service.navigation(current_step="results", run_id=run_id)

            by_key = {item.key: item for item in navigation.items}
            self.assertEqual(by_key["start"].state, "completed")
            self.assertEqual(by_key["progress"].state, "completed")
            self.assertEqual(by_key["results"].state, "active")
            self.assertEqual(by_key["changes"].state, "available")
            self.assertEqual(by_key["draft"].state, "locked")
            self.assertEqual(by_key["progress"].href, f"/runs/{run_id}/progress")
            self.assertEqual(by_key["results"].href, f"/runs/{run_id}/results")
            self.assertEqual(by_key["changes"].href, f"/runs/{run_id}/changes")
            self.assertIsNone(by_key["draft"].href)

    async def test_navigation_locks_destinations_when_artifacts_are_unavailable(self) -> None:
        with TemporaryDirectory() as directory:
            service, run_id = await self._service_with_run(directory)
            connection = sqlite3.connect(Path(directory) / "history.sqlite3")
            try:
                connection.execute(
                    "DELETE FROM artifacts WHERE run_id=? AND artifact_type IN (?, ?)",
                    (
                        run_id,
                        ArtifactType.CHANGE_PLAN.value,
                        ArtifactType.CONTENT_DRAFT.value,
                    ),
                )
                connection.commit()
            finally:
                connection.close()

            navigation = service.navigation(current_step="results", run_id=run_id)

            by_key = {item.key: item for item in navigation.items}
            self.assertEqual(by_key["results"].state, "active")
            self.assertEqual(by_key["changes"].state, "locked")
            self.assertIsNone(by_key["changes"].href)
            self.assertEqual(by_key["draft"].state, "locked")
            self.assertIsNone(by_key["draft"].href)


if __name__ == "__main__":
    unittest.main()
