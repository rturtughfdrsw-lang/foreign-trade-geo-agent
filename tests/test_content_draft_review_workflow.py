"""Read-only review workflow over persisted planning artifacts."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from foreign_trade_geo_agent.core.content_draft_review import (
    ContentDraftReviewRequest,
)
from foreign_trade_geo_agent.storage.sqlite import SQLiteHistoryReader
from foreign_trade_geo_agent.workflows.content_draft_review import (
    ContentDraftReviewError,
    ContentDraftReviewWorkflow,
)
from tests.review_fixtures import (
    CHANGE_PLAN_ARTIFACT_ID,
    CONTENT_DRAFT_ARTIFACT_ID,
    PAGE_EXCERPT_SENTINEL,
    RUN_ID,
    UNKNOWN_ARTIFACT_ID,
    UNUSED_AUDIT_CHECK_KEY,
    UNUSED_PAGE_EXCERPT_SENTINEL,
    corrupt_artifact_payload,
    persist_review_fixture,
    raw_sqlite_update,
    rewrite_opportunity_audit_refs,
)


def _request(draft_id: str = "D1") -> ContentDraftReviewRequest:
    return ContentDraftReviewRequest(
        planning_run_id=RUN_ID,
        content_draft_artifact_id=CONTENT_DRAFT_ARTIFACT_ID,
        draft_id=draft_id,
    )


class ContentDraftReviewWorkflowTests(unittest.TestCase):
    def test_review_resolves_draft_change_opportunity_and_cited_evidence(self) -> None:
        with TemporaryDirectory() as temporary:
            fixture = persist_review_fixture(Path(temporary) / "history.sqlite3")
            workflow = ContentDraftReviewWorkflow(
                history_reader=SQLiteHistoryReader(fixture.db_path)
            )

            view = workflow.review(_request("D1"))

        self.assertEqual(view.planning_run_id, RUN_ID)
        self.assertEqual(view.content_draft_artifact_id, CONTENT_DRAFT_ARTIFACT_ID)
        self.assertEqual(view.payload_version, 1)
        self.assertEqual(view.draft.draft_id, "D1")
        self.assertEqual(view.draft.draft_type, "SECTION_DRAFT")
        self.assertIn("Material selection and port size are observed.", view.draft.body_text)
        self.assertTrue(view.draft.requires_human_review)
        self.assertEqual(view.change.change_id, "C1")
        self.assertEqual(view.change.operation_type, "EXPAND_SECTION")
        self.assertEqual(view.change.opportunity_ref, "R1")
        self.assertEqual(view.opportunity.recommendation_id, "R1")
        self.assertIn("Expand observed", view.opportunity.title)
        self.assertTrue(view.opportunity.rationale)
        self.assertTrue(view.opportunity.actions)
        self.assertEqual(
            tuple(item.evidence_id for item in view.audit_evidence),
            ("A1",),
        )
        self.assertEqual(
            tuple(item.evidence_id for item in view.page_evidence),
            ("P1",),
        )
        self.assertEqual(
            tuple(item.source_id for item in view.source_evidence),
            ("S1",),
        )
        self.assertIn(PAGE_EXCERPT_SENTINEL, view.page_evidence[0].excerpt or "")
        self.assertIn("Chemical compatibility", view.source_evidence[0].excerpt or "")
        self.assertTrue(view.draft.claims)
        self.assertTrue(
            all(claim.claim_id.startswith("CL") for claim in view.draft.claims)
        )

    def test_review_selects_structure_only_draft_exactly(self) -> None:
        with TemporaryDirectory() as temporary:
            fixture = persist_review_fixture(Path(temporary) / "history.sqlite3")
            workflow = ContentDraftReviewWorkflow(
                history_reader=SQLiteHistoryReader(fixture.db_path)
            )

            view = workflow.review(_request("D2"))

        self.assertEqual(view.draft.draft_id, "D2")
        self.assertEqual(view.draft.draft_type, "STRUCTURE_ONLY")
        self.assertIn("Chemical Compatibility", view.draft.body_text)
        self.assertEqual(view.change.operation_type, "PROPOSE_SECTION_REORDER")
        self.assertEqual(view.opportunity.recommendation_id, "R2")
        self.assertEqual(view.audit_evidence, ())

    def test_review_does_not_recover_uncited_evidence(self) -> None:
        with TemporaryDirectory() as temporary:
            fixture = persist_review_fixture(Path(temporary) / "history.sqlite3")
            workflow = ContentDraftReviewWorkflow(
                history_reader=SQLiteHistoryReader(fixture.db_path)
            )

            view = workflow.review(_request("D1"))

        self.assertNotIn(
            UNUSED_AUDIT_CHECK_KEY,
            tuple(item.check_key for item in view.audit_evidence),
        )
        self.assertNotIn(
            "P2",
            tuple(item.evidence_id for item in view.page_evidence),
        )
        self.assertNotIn(
            UNUSED_PAGE_EXCERPT_SENTINEL,
            tuple(item.excerpt or "" for item in view.page_evidence),
        )

    def test_review_fails_closed_for_unknown_run_artifact_and_draft(self) -> None:
        with TemporaryDirectory() as temporary:
            fixture = persist_review_fixture(Path(temporary) / "history.sqlite3")
            workflow = ContentDraftReviewWorkflow(
                history_reader=SQLiteHistoryReader(fixture.db_path)
            )
            other_run = "33333333-3333-4333-8333-333333333333"
            cases = (
                ContentDraftReviewRequest(
                    planning_run_id=other_run,
                    content_draft_artifact_id=CONTENT_DRAFT_ARTIFACT_ID,
                    draft_id="D1",
                ),
                ContentDraftReviewRequest(
                    planning_run_id=RUN_ID,
                    content_draft_artifact_id=UNKNOWN_ARTIFACT_ID,
                    draft_id="D1",
                ),
                ContentDraftReviewRequest(
                    planning_run_id=RUN_ID,
                    content_draft_artifact_id=CHANGE_PLAN_ARTIFACT_ID,
                    draft_id="D1",
                ),
                _request("D9"),
            )
            for request in cases:
                with self.subTest(request=request):
                    with self.assertRaises(ContentDraftReviewError):
                        workflow.review(request)

    def test_review_fails_closed_when_change_plan_artifact_is_missing(self) -> None:
        with TemporaryDirectory() as temporary:
            fixture = persist_review_fixture(Path(temporary) / "history.sqlite3")
            raw_sqlite_update(
                fixture.db_path,
                "DELETE FROM artifacts WHERE artifact_id=?",
                (CHANGE_PLAN_ARTIFACT_ID,),
            )
            workflow = ContentDraftReviewWorkflow(
                history_reader=SQLiteHistoryReader(fixture.db_path)
            )

            with self.assertRaises(ContentDraftReviewError):
                workflow.review(_request("D1"))

    def test_review_fails_closed_on_corrupted_artifact_payload(self) -> None:
        with TemporaryDirectory() as temporary:
            fixture = persist_review_fixture(Path(temporary) / "history.sqlite3")
            corrupt_artifact_payload(fixture.db_path, CONTENT_DRAFT_ARTIFACT_ID)
            workflow = ContentDraftReviewWorkflow(
                history_reader=SQLiteHistoryReader(fixture.db_path)
            )

            with self.assertRaises(ContentDraftReviewError) as raised:
                workflow.review(_request("D1"))

        self.assertNotIn("not-json", str(raised.exception))

    def test_review_fails_closed_on_inconsistent_audit_provenance(self) -> None:
        with TemporaryDirectory() as temporary:
            fixture = persist_review_fixture(Path(temporary) / "history.sqlite3")
            rewrite_opportunity_audit_refs(
                fixture.db_path,
                recommendation_id="R1",
                audit_refs=["A2"],
            )
            workflow = ContentDraftReviewWorkflow(
                history_reader=SQLiteHistoryReader(fixture.db_path)
            )

            with self.assertRaises(ContentDraftReviewError):
                workflow.review(_request("D1"))

    def test_review_requires_its_stable_request_model(self) -> None:
        with TemporaryDirectory() as temporary:
            fixture = persist_review_fixture(Path(temporary) / "history.sqlite3")
            workflow = ContentDraftReviewWorkflow(
                history_reader=SQLiteHistoryReader(fixture.db_path)
            )

            with self.assertRaises(TypeError):
                workflow.review(object())  # type: ignore[arg-type]

    def test_review_recovers_everything_after_close_and_reopen(self) -> None:
        with TemporaryDirectory() as temporary:
            fixture = persist_review_fixture(Path(temporary) / "history.sqlite3")

            first = ContentDraftReviewWorkflow(
                history_reader=SQLiteHistoryReader(fixture.db_path)
            ).review(_request("D1"))
            reopened = ContentDraftReviewWorkflow(
                history_reader=SQLiteHistoryReader(fixture.db_path)
            ).review(_request("D1"))

        self.assertEqual(first, reopened)
        self.assertIn(
            "Material selection and port size are observed.",
            reopened.draft.body_text,
        )
        self.assertEqual(reopened.change.change_id, "C1")
        self.assertEqual(reopened.opportunity.recommendation_id, "R1")
        self.assertEqual(
            tuple(item.evidence_id for item in reopened.audit_evidence),
            ("A1",),
        )
        self.assertEqual(
            tuple(item.evidence_id for item in reopened.page_evidence),
            ("P1",),
        )
        self.assertEqual(
            tuple(item.source_id for item in reopened.source_evidence),
            ("S1",),
        )


if __name__ == "__main__":
    unittest.main()
