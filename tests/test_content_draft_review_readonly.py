"""Read-only guarantees for the review retrieval path."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from foreign_trade_geo_agent.core.content_draft_review import (
    ContentDraftReviewRequest,
)
from foreign_trade_geo_agent.core.history import UnsupportedHistoryVersionError
from foreign_trade_geo_agent.storage.sqlite import SQLiteHistoryReader
from foreign_trade_geo_agent.workflows.content_draft_review import (
    ContentDraftReviewWorkflow,
)
from tests.review_fixtures import (
    CONTENT_DRAFT_ARTIFACT_ID,
    RUN_ID,
    database_business_snapshot,
    persist_review_fixture,
)


def _request(draft_id: str = "D1") -> ContentDraftReviewRequest:
    return ContentDraftReviewRequest(
        planning_run_id=RUN_ID,
        content_draft_artifact_id=CONTENT_DRAFT_ARTIFACT_ID,
        draft_id=draft_id,
    )


class ReadOnlyRetrievalTests(unittest.TestCase):
    def test_reader_rejects_a_missing_database_without_creating_it(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            missing = root / "nested" / "history.sqlite3"

            with self.assertRaises(FileNotFoundError):
                SQLiteHistoryReader(missing)

            self.assertFalse(missing.exists())
            self.assertFalse(missing.parent.exists())

    def test_reader_rejects_non_history_file_without_writing_schema(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            empty = root / "empty.sqlite3"
            empty.write_bytes(b"")

            with self.assertRaises(UnsupportedHistoryVersionError):
                SQLiteHistoryReader(empty)

            self.assertEqual(empty.read_bytes(), b"")

    def test_runtime_review_construction_does_not_create_a_database(self) -> None:
        from foreign_trade_geo_agent.runtime import build_review_workflow

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            missing = root / "nested" / "history.sqlite3"

            with self.assertRaises(FileNotFoundError):
                build_review_workflow(missing)

            self.assertFalse(missing.exists())
            self.assertFalse(missing.parent.exists())

    def test_review_does_not_write_business_rows(self) -> None:
        with TemporaryDirectory() as temporary:
            fixture = persist_review_fixture(Path(temporary) / "history.sqlite3")
            before = database_business_snapshot(fixture.db_path)
            before_bytes = fixture.db_path.read_bytes()
            workflow = ContentDraftReviewWorkflow(
                history_reader=SQLiteHistoryReader(fixture.db_path)
            )

            first = workflow.review(_request("D1"))
            second = workflow.review(_request("D1"))

            after = database_business_snapshot(fixture.db_path)
            after_bytes = fixture.db_path.read_bytes()

        self.assertEqual(before, after)
        self.assertEqual(before_bytes, after_bytes)
        self.assertEqual(
            (before[0][0], before[0][1], before[0][2]),
            (1, 6, 0),
        )
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
