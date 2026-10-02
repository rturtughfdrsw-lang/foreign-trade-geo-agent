"""Deterministic text and JSON rendering of the core review view."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from foreign_trade_geo_agent.core.content_draft_review import (
    ContentDraftReviewRequest,
    ContentDraftReviewView,
)
from foreign_trade_geo_agent.reporting.content_draft_review import (
    content_draft_review_payload,
    render_content_draft_review_text,
)
from foreign_trade_geo_agent.storage.sqlite import SQLiteHistoryReader
from foreign_trade_geo_agent.workflows.content_draft_review import (
    ContentDraftReviewWorkflow,
)
from tests.review_fixtures import (
    CONTENT_DRAFT_ARTIFACT_ID,
    RESEARCH_SENTINEL,
    RUN_ID,
    UNUSED_AUDIT_CHECK_KEY,
    persist_review_fixture,
)


def _view(draft_id: str = "D1") -> ContentDraftReviewView:
    with TemporaryDirectory() as temporary:
        fixture = persist_review_fixture(Path(temporary) / "history.sqlite3")
        workflow = ContentDraftReviewWorkflow(
            history_reader=SQLiteHistoryReader(fixture.db_path)
        )
        return workflow.review(
            ContentDraftReviewRequest(
                planning_run_id=RUN_ID,
                content_draft_artifact_id=CONTENT_DRAFT_ARTIFACT_ID,
                draft_id=draft_id,
            )
        )


class ContentDraftReviewTextTests(unittest.TestCase):
    def test_text_exposes_draft_body_change_opportunity_and_evidence(self) -> None:
        rendered = render_content_draft_review_text(_view())

        for expected in (
            RUN_ID,
            CONTENT_DRAFT_ARTIFACT_ID,
            "D1",
            "SECTION_DRAFT",
            "Material selection and port size are observed.",
            "Chemical compatibility guidance appears in the external pump guide.",
            "C1",
            "EXPAND_SECTION",
            "R1",
            "Expand observed",
            "A1",
            "P1",
            "S1",
            "audit observation",
            "unverified",
            "deliver --run-id",
            "--draft-id D1",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, rendered)

    def test_text_never_claims_a_recorded_approval_state(self) -> None:
        rendered = render_content_draft_review_text(_view())

        self.assertIn("Approval record: NOT RECORDED", rendered)
        self.assertIn("Review action: READ ONLY", rendered)
        self.assertNotIn("NOT APPROVED", rendered)
        self.assertNotIn("approved by", rendered.casefold())

    def test_text_keeps_evidence_bounded_and_trust_labelled(self) -> None:
        rendered = render_content_draft_review_text(_view())

        self.assertNotIn(UNUSED_AUDIT_CHECK_KEY, rendered)
        self.assertNotIn("P2", rendered)
        self.assertNotIn(RESEARCH_SENTINEL, rendered)
        self.assertIn("observed content only", rendered)
        self.assertIn("external research", rendered)

    def test_structure_only_text_renders_heading_outline(self) -> None:
        rendered = render_content_draft_review_text(_view("D2"))

        self.assertIn("STRUCTURE_ONLY", rendered)
        self.assertIn("Chemical Compatibility", rendered)
        self.assertIn("Maintenance", rendered)

    def test_rendering_is_deterministic(self) -> None:
        view = _view()

        self.assertEqual(
            render_content_draft_review_text(view),
            render_content_draft_review_text(view),
        )


class ContentDraftReviewJsonTests(unittest.TestCase):
    def test_json_payload_mirrors_the_same_core_view(self) -> None:
        view = _view()

        payload = content_draft_review_payload(view)
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        restored = json.loads(serialized)

        self.assertEqual(restored["run_id"], RUN_ID)
        self.assertEqual(restored["artifact_id"], CONTENT_DRAFT_ARTIFACT_ID)
        self.assertEqual(restored["approval_record"], "NOT RECORDED")
        self.assertEqual(restored["review_action"], "READ ONLY")
        self.assertEqual(restored["draft"]["draft_id"], "D1")
        self.assertEqual(
            restored["draft"]["body_text"],
            view.draft.body_text,
        )
        self.assertEqual(restored["change"]["change_id"], "C1")
        self.assertEqual(restored["opportunity"]["recommendation_id"], "R1")
        self.assertEqual(
            [item["evidence_id"] for item in restored["audit_evidence"]],
            ["A1"],
        )
        self.assertEqual(
            [item["evidence_id"] for item in restored["page_evidence"]],
            ["P1"],
        )
        self.assertEqual(
            [item["source_id"] for item in restored["source_evidence"]],
            ["S1"],
        )
        self.assertTrue(restored["limitations"])
        self.assertIn("--draft-id D1", restored["delivery_handoff"])


if __name__ == "__main__":
    unittest.main()
