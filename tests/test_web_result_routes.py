from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from foreign_trade_geo_agent.core.orchestration import EndToEndRunRequest
from foreign_trade_geo_agent.web.app import create_app
from foreign_trade_geo_agent.web.application import DemoApplicationService
from foreign_trade_geo_agent.web.composition import build_demo_composition
from foreign_trade_geo_agent.web.demo_boundaries import (
    DEMO_RESEARCH_QUESTION,
    DEMO_SITE_URL,
    DEMO_TARGET_LANGUAGE,
)
from foreign_trade_geo_agent.web.presenters import present_navigation


async def _completed_run(db_path: Path) -> str:
    composition = build_demo_composition(db_path)
    result = await composition.planning_workflow().run(
        EndToEndRunRequest(
            DEMO_SITE_URL,
            DEMO_RESEARCH_QUESTION,
            DEMO_TARGET_LANGUAGE,
        )
    )
    return result.run.run_id


class DemoResultRouteTests(unittest.TestCase):
    def test_results_screen_renders_audit_evidence_and_opportunities(self) -> None:
        with TemporaryDirectory() as directory:
            db_path = Path(directory) / "history.sqlite3"
            run_id = asyncio.run(_completed_run(db_path))
            with TestClient(create_app(db_path=db_path)) as client:
                response = client.get(f"/runs/{run_id}/results")

        self.assertEqual(response.status_code, 200)
        for text in (
            "Audit / Results",
            "Key findings",
            "SEO Health",
            "78 / 100",
            "Needs improvement",
            "2 key observations",
            "1 high-priority opportunity",
            "Buyer-selection guidance was not detected by the audit.",
            "Website Evidence",
            "Home page",
            "P1",
            "SEO Audit Evidence",
            "A1",
            "Audit outcome: ABSENT",
            "Content Opportunities",
            "R1",
            "Expand observed CNC machining center content",
            "View Change Plan →",
        ):
            self.assertIn(text, response.text)
        self.assertNotIn(f"/runs/{run_id}/drafts/D1", response.text)
        self.assertNotIn("Review D1", response.text)
        self.assertNotIn("SiteAuditResult(", response.text)

    def test_change_screen_renders_human_fields_and_three_evidence_groups(self) -> None:
        with TemporaryDirectory() as directory:
            db_path = Path(directory) / "history.sqlite3"
            run_id = asyncio.run(_completed_run(db_path))
            with TestClient(create_app(db_path=db_path)) as client:
                response = client.get(f"/runs/{run_id}/changes")

        self.assertEqual(response.status_code, 200)
        for text in (
            "Change Plan",
            "Recommended SEO Change",
            "Expand existing product content",
            "Target",
            "Precision CNC Machinery",
            "C1 · EXPAND_SECTION · P1",
            "Evidence",
            "Website Evidence",
            "SEO Audit Evidence",
            "External Research",
            "Selection guidance",
            "Not detected",
            "content.selection_guidance.present · ABSENT",
            "Review notes",
            "Human review is required before execution.",
            "View technical limitations",
            "← Back to Results",
            "Review Generated Draft →",
            "C1",
            "P1",
            "A1",
            "S1",
        ):
            self.assertIn(text, response.text)
        self.assertIn(f'/runs/{run_id}/drafts/D1', response.text)
        self.assertNotIn("Observed page evidence P1 contains", response.text)

    def test_draft_screen_renders_full_review_and_read_only_semantics(self) -> None:
        with TemporaryDirectory() as directory:
            db_path = Path(directory) / "history.sqlite3"
            run_id = asyncio.run(_completed_run(db_path))
            with TestClient(create_app(db_path=db_path)) as client:
                response = client.get(f"/runs/{run_id}/drafts/D1")

        self.assertEqual(response.status_code, 200)
        for text in (
            "Draft Review",
            "Generated Draft",
            "D1 · C1 · High priority",
            "NovaCNC supplies CNC machining centers for industrial production teams.",
            "Human Review Required",
            "Review action:",
            "Approval record:",
            "READ ONLY",
            "NOT RECORDED",
            "Review does not record approval.",
            "Continue to WordPress Delivery →",
            "Why This Draft",
            "Review notes &amp; limitations",
            "Website Evidence",
            "SEO Audit Evidence",
            "External Research",
            "Compare travel and spindle capability.",
        ):
            self.assertIn(text, response.text)
        self.assertIn('class="draft-primary-grid"', response.text)
        self.assertIn('class="draft-evidence-grid"', response.text)
        self.assertIn(
            f'href="/runs/{run_id}/drafts/D1/delivery"',
            response.text,
        )
        self.assertNotIn("<form", response.text)
        self.assertNotIn("Coming in Demo Phase 2", response.text)
        self.assertNotIn("ContentDraftReviewView(", response.text)

    def test_draft_screen_does_not_fabricate_delivery_href_when_unavailable(self) -> None:
        with TemporaryDirectory() as directory:
            db_path = Path(directory) / "history.sqlite3"
            run_id = asyncio.run(_completed_run(db_path))
            unavailable = present_navigation(
                current_step="draft",
                destinations={},
            )
            app = create_app(db_path=db_path)
            with (
                patch.object(
                    DemoApplicationService,
                    "navigation",
                    return_value=unavailable,
                ),
                TestClient(app) as client,
            ):
                response = client.get(f"/runs/{run_id}/drafts/D1")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(
            f'href="/runs/{run_id}/drafts/D1/delivery"',
            response.text,
        )

    def test_phase_one_has_no_approval_delivery_or_verification_route(self) -> None:
        with TemporaryDirectory() as directory:
            app = create_app(db_path=Path(directory) / "history.sqlite3")
            with TestClient(app) as client:
                for path in (
                    "/approve",
                    "/deliver",
                    "/verify",
                    "/runs/11111111-1111-4111-8111-111111111111/deliver",
                    "/runs/11111111-1111-4111-8111-111111111111/verify",
                ):
                    with self.subTest(path=path):
                        self.assertEqual(client.post(path).status_code, 404)

    def test_invalid_run_or_draft_identifier_returns_sanitized_not_found(self) -> None:
        with TemporaryDirectory() as directory:
            app = create_app(db_path=Path(directory) / "history.sqlite3")
            with TestClient(app) as client:
                results = client.get("/runs/not-a-run/results")
                draft = client.get("/runs/not-a-run/drafts/not-a-draft")

        self.assertEqual(results.status_code, 404)
        self.assertEqual(draft.status_code, 404)
        self.assertIn("unavailable or invalid", results.text)
        self.assertIn("unavailable or invalid", draft.text)
        self.assertNotIn("Traceback", results.text + draft.text)


if __name__ == "__main__":
    unittest.main()
