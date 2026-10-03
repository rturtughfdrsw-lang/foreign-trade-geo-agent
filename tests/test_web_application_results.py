from __future__ import annotations

import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4

from foreign_trade_geo_agent.core.content_draft_review import ContentDraftReviewView
from foreign_trade_geo_agent.core.history import ArtifactType
from foreign_trade_geo_agent.core.orchestration import EndToEndRunRequest
from foreign_trade_geo_agent.web.application import (
    DemoApplicationError,
    DemoApplicationService,
)
from foreign_trade_geo_agent.web.composition import build_demo_composition
from foreign_trade_geo_agent.web.demo_boundaries import (
    DEMO_RESEARCH_QUESTION,
    DEMO_SITE_URL,
    DEMO_TARGET_LANGUAGE,
)
from foreign_trade_geo_agent.web.jobs import LocalJobRegistry


def _business_snapshot(db_path: Path) -> tuple[object, ...]:
    connection = sqlite3.connect(db_path)
    try:
        return (
            tuple(connection.execute("SELECT * FROM runs ORDER BY run_id")),
            tuple(connection.execute("SELECT * FROM artifacts ORDER BY artifact_id")),
            tuple(
                connection.execute(
                    "SELECT * FROM wordpress_draft_attempts ORDER BY attempt_id"
                )
            ),
        )
    finally:
        connection.close()


class DemoApplicationResultsTests(unittest.IsolatedAsyncioTestCase):
    async def _completed_run(
        self,
        directory: str,
    ) -> tuple[Path, DemoApplicationService, str]:
        db_path = Path(directory) / "history.sqlite3"
        composition = build_demo_composition(db_path)
        result = await composition.planning_workflow().run(
            EndToEndRunRequest(
                DEMO_SITE_URL,
                DEMO_RESEARCH_QUESTION,
                DEMO_TARGET_LANGUAGE,
            )
        )
        fresh_composition = build_demo_composition(db_path)
        return (
            db_path,
            DemoApplicationService(fresh_composition, LocalJobRegistry()),
            result.run.run_id,
        )

    async def test_draft_review_uses_real_review_workflow_and_is_read_only(self) -> None:
        with TemporaryDirectory() as directory:
            db_path, service, run_id = await self._completed_run(directory)
            before = _business_snapshot(db_path)

            view = service.review_draft(run_id, "D1")

            self.assertIsInstance(view.review, ContentDraftReviewView)
            self.assertEqual(view.review.planning_run_id, run_id)
            self.assertEqual(view.review.draft.draft_id, "D1")
            self.assertEqual(view.review_action, "READ ONLY")
            self.assertEqual(view.approval_record, "NOT RECORDED")
            self.assertEqual(view.approval_note, "Review does not record approval.")
            self.assertEqual(
                view.delivery_label,
                "Continue to Delivery Setup — Coming in Demo Phase 2",
            )
            self.assertFalse(view.delivery_enabled)
            self.assertEqual(_business_snapshot(db_path), before)

    async def test_missing_duplicate_or_malformed_artifacts_fail_sanitized(self) -> None:
        for corruption in ("missing", "duplicate", "malformed"):
            with self.subTest(corruption=corruption), TemporaryDirectory() as directory:
                db_path, _service, run_id = await self._completed_run(directory)
                connection = sqlite3.connect(db_path)
                try:
                    artifact = connection.execute(
                        "SELECT artifact_id FROM artifacts "
                        "WHERE run_id=? AND artifact_type=?",
                        (run_id, ArtifactType.SITE_CONTENT.value),
                    ).fetchone()
                    assert artifact is not None
                    artifact_id = artifact[0]
                    if corruption == "missing":
                        connection.execute(
                            "DELETE FROM artifacts WHERE artifact_id=?",
                            (artifact_id,),
                        )
                    elif corruption == "duplicate":
                        connection.execute(
                            "INSERT INTO artifacts "
                            "SELECT ?,run_id,artifact_type,payload_version,created_at,payload_json "
                            "FROM artifacts WHERE artifact_id=?",
                            (str(uuid4()), artifact_id),
                        )
                    else:
                        connection.execute(
                            "UPDATE artifacts SET payload_json=? WHERE artifact_id=?",
                            ('{"provider_secret":"LEAK-ME"', artifact_id),
                        )
                    connection.commit()
                finally:
                    connection.close()
                service = DemoApplicationService(
                    build_demo_composition(db_path),
                    LocalJobRegistry(),
                )

                with self.assertRaises(DemoApplicationError) as raised:
                    service.load_results(run_id)

                self.assertEqual(
                    str(raised.exception),
                    "The persisted planning results are unavailable or invalid.",
                )
                self.assertNotIn("LEAK-ME", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
