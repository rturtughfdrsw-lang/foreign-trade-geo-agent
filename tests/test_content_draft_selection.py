"""Shared persisted-content-draft loading and exact D# selection."""

from __future__ import annotations

from dataclasses import dataclass
import unittest

from foreign_trade_geo_agent.core.content_draft import (
    CONTENT_DRAFT_LIMITATIONS,
    ContentDraftReport,
    ContentDraftStatus,
)
from foreign_trade_geo_agent.core.history import ArtifactRecord, ArtifactType
from foreign_trade_geo_agent.workflows.content_draft_selection import (
    ContentDraftSelectionError,
    load_persisted_content_draft_report,
    select_content_draft,
)
from tests.review_fixtures import (
    CONTENT_DRAFT_ARTIFACT_ID,
    CONTENT_OPPORTUNITY_ARTIFACT_ID,
    NOW,
    RUN_ID,
)


@dataclass(frozen=True)
class _StubDraft:
    draft_id: str


@dataclass(frozen=True)
class _StubReport:
    drafts: tuple[_StubDraft, ...]


class _StubReader:
    def __init__(self, artifact: ArtifactRecord | None) -> None:
        self._artifact = artifact

    def get_artifact(self, artifact_id: str) -> ArtifactRecord | None:
        return self._artifact


def _success_report() -> ContentDraftReport:
    return ContentDraftReport(
        status=ContentDraftStatus.SUCCESS,
        drafts=(),
        limitations=CONTENT_DRAFT_LIMITATIONS,
        error=None,
    )


def _artifact(
    payload: object,
    *,
    artifact_type: ArtifactType = ArtifactType.CONTENT_DRAFT,
    run_id: str = RUN_ID,
    payload_version: int = 1,
    artifact_id: str = CONTENT_DRAFT_ARTIFACT_ID,
) -> ArtifactRecord:
    return ArtifactRecord(
        artifact_id=artifact_id,
        run_id=run_id,
        artifact_type=artifact_type,
        payload_version=payload_version,
        created_at=NOW,
        payload=payload,
    )


class SelectContentDraftTests(unittest.TestCase):
    def test_selects_exactly_one_matching_draft(self) -> None:
        report = _StubReport((_StubDraft("D1"), _StubDraft("D2")))

        self.assertEqual(select_content_draft(report, "D2").draft_id, "D2")

    def test_unknown_malformed_and_duplicate_draft_ids_fail_closed(self) -> None:
        cases = (
            (_StubReport((_StubDraft("D1"),)), "D2"),
            (_StubReport((_StubDraft("D1"),)), "d1"),
            (_StubReport((_StubDraft("D1"),)), ""),
            (_StubReport((_StubDraft("D1"), _StubDraft("D1"))), "D1"),
            (_StubReport(()), "D1"),
        )
        for report, draft_id in cases:
            with self.subTest(draft_id=draft_id):
                with self.assertRaises(ContentDraftSelectionError):
                    select_content_draft(report, draft_id)


class LoadPersistedContentDraftTests(unittest.TestCase):
    def test_valid_success_report_is_returned(self) -> None:
        report = _success_report()

        loaded = load_persisted_content_draft_report(
            _StubReader(_artifact(report)),
            planning_run_id=RUN_ID,
            content_draft_artifact_id=CONTENT_DRAFT_ARTIFACT_ID,
        )

        self.assertEqual(loaded, report)

    def test_missing_artifact_fails_closed(self) -> None:
        with self.assertRaises(ContentDraftSelectionError):
            load_persisted_content_draft_report(
                _StubReader(None),
                planning_run_id=RUN_ID,
                content_draft_artifact_id=CONTENT_DRAFT_ARTIFACT_ID,
            )

    def test_artifact_from_another_run_fails_closed(self) -> None:
        other_run = "33333333-3333-4333-8333-333333333333"
        with self.assertRaises(ContentDraftSelectionError):
            load_persisted_content_draft_report(
                _StubReader(_artifact(_success_report(), run_id=other_run)),
                planning_run_id=RUN_ID,
                content_draft_artifact_id=CONTENT_DRAFT_ARTIFACT_ID,
            )

    def test_wrong_artifact_type_fails_closed(self) -> None:
        with self.assertRaises(ContentDraftSelectionError):
            load_persisted_content_draft_report(
                _StubReader(
                    _artifact(
                        _success_report(),
                        artifact_type=ArtifactType.CONTENT_OPPORTUNITY,
                        artifact_id=CONTENT_OPPORTUNITY_ARTIFACT_ID,
                    )
                ),
                planning_run_id=RUN_ID,
                content_draft_artifact_id=CONTENT_OPPORTUNITY_ARTIFACT_ID,
            )

    def test_unsupported_payload_version_fails_closed(self) -> None:
        with self.assertRaises(ContentDraftSelectionError):
            load_persisted_content_draft_report(
                _StubReader(_artifact(_success_report(), payload_version=2)),
                planning_run_id=RUN_ID,
                content_draft_artifact_id=CONTENT_DRAFT_ARTIFACT_ID,
            )

    def test_foreign_payload_fails_closed(self) -> None:
        with self.assertRaises(ContentDraftSelectionError):
            load_persisted_content_draft_report(
                _StubReader(_artifact(object())),
                planning_run_id=RUN_ID,
                content_draft_artifact_id=CONTENT_DRAFT_ARTIFACT_ID,
            )

    def test_non_success_report_fails_closed(self) -> None:
        failed = ContentDraftReport(
            status=ContentDraftStatus.INVALID_OUTPUT,
            drafts=(),
            limitations=(),
            error="FIELD_CONTRACT",
        )
        with self.assertRaises(ContentDraftSelectionError):
            load_persisted_content_draft_report(
                _StubReader(_artifact(failed)),
                planning_run_id=RUN_ID,
                content_draft_artifact_id=CONTENT_DRAFT_ARTIFACT_ID,
            )


if __name__ == "__main__":
    unittest.main()
