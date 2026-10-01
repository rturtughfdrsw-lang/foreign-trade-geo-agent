from __future__ import annotations

from datetime import UTC, datetime
import unittest

from foreign_trade_geo_agent.core.approved_wordpress_delivery import (
    ApprovedWordPressDraftDeliveryRequest,
    ApprovedWordPressDraftDeliveryValidationError,
)
from foreign_trade_geo_agent.core.change_plan import (
    ChangeTargetKind,
    SectionLocator,
    SectionLocatorKind,
)
from foreign_trade_geo_agent.core.content_draft import (
    CONTENT_DRAFT_LIMITATIONS,
    ContentDraftReport,
    ContentDraftStatus,
    ContentDraftType,
    DraftBlockKind,
    DraftClaim,
    DraftClaimSupportKind,
    DraftClaimType,
    DraftItem,
    ParagraphBlock,
)
from foreign_trade_geo_agent.core.history import (
    ArtifactRecord,
    ArtifactType,
    HistoryStoreError,
    WordPressAttemptState,
    WordPressDraftAttempt,
)
from foreign_trade_geo_agent.core.wordpress_draft import (
    WordPressDraftFailureKind,
    WordPressDraftRemoteOutcome,
    WordPressDraftResult,
)
from foreign_trade_geo_agent.workflows.approved_wordpress_delivery import (
    ApprovedWordPressDraftDeliveryWorkflow,
)
from foreign_trade_geo_agent.workflows.wordpress_delivery import (
    WordPressDeliveryResult,
    WordPressDeliveryStatus,
)


RUN_ID = "11111111-1111-4111-8111-111111111111"
OTHER_RUN_ID = "11111111-1111-4111-8111-111111111112"
ARTIFACT_ID = "22222222-2222-4222-8222-222222222222"
ATTEMPT_ID = "33333333-3333-4333-8333-333333333333"
NOW = datetime(2026, 10, 2, 8, 30, tzinfo=UTC)
TARGET_URL = "https://cms.example.com/wp-admin?approved=1"


def draft_item(draft_id: str, heading: str) -> DraftItem:
    number = draft_id[1:]
    claim = DraftClaim(
        claim_id=f"CL{number}",
        text=f"Safe body {number}",
        claim_type=DraftClaimType.GENERAL_TECHNICAL_CONTEXT,
        support_kind=DraftClaimSupportKind.EXTERNAL_CONTEXT,
        page_refs=(),
        source_refs=("S1",),
    )
    return DraftItem(
        draft_id=draft_id,
        change_ref=f"C{number}",
        opportunity_ref=f"R{number}",
        draft_type=ContentDraftType.NEW_RESOURCE_DRAFT,
        target_kind=ChangeTargetKind.CREATE_NEW_PAGE,
        target_page_ref=None,
        locator=SectionLocator(
            SectionLocatorKind.NEW_PAGE,
            None,
            None,
            None,
            None,
        ),
        heading=heading,
        ordered_headings=(),
        blocks=(ParagraphBlock(DraftBlockKind.PARAGRAPH, (claim,)),),
        page_refs=(),
        source_refs=("S1",),
    )


def draft_report() -> ContentDraftReport:
    return ContentDraftReport(
        status=ContentDraftStatus.SUCCESS,
        drafts=(draft_item("D1", "First draft"), draft_item("D2", "Second draft")),
        limitations=CONTENT_DRAFT_LIMITATIONS,
        error=None,
    )


def artifact(
    *,
    run_id: str = RUN_ID,
    artifact_type: ArtifactType = ArtifactType.CONTENT_DRAFT,
    payload_version: int = 1,
    payload: object | None = None,
) -> ArtifactRecord:
    return ArtifactRecord(
        artifact_id=ARTIFACT_ID,
        run_id=run_id,
        artifact_type=artifact_type,
        payload_version=payload_version,
        created_at=NOW,
        payload=draft_report() if payload is None else payload,
    )


def wordpress_attempt(state: WordPressAttemptState) -> WordPressDraftAttempt:
    pending = state is WordPressAttemptState.PENDING
    successful = state is WordPressAttemptState.SUCCESS
    return WordPressDraftAttempt(
        attempt_id=ATTEMPT_ID,
        run_id=RUN_ID,
        content_draft_artifact_id=ARTIFACT_ID,
        draft_item_id="D2",
        target_site_key="https://cms.example.com:443",
        fingerprint_version=1,
        request_fingerprint="a" * 64,
        attempted_at=NOW,
        completed_at=None if pending else NOW,
        outcome=state,
        remote_post_id=41 if successful else None,
        remote_link="https://cms.example.com/?p=41" if successful else None,
        failure_kind=(
            None if pending or successful else WordPressDraftFailureKind.TIMEOUT.value
        ),
        sanitized_error=(
            None if pending or successful else "WordPress request timed out."
        ),
    )


def delivery_result(status: WordPressDeliveryStatus) -> WordPressDeliveryResult:
    if status is WordPressDeliveryStatus.SUCCESS:
        remote = WordPressDraftResult(
            WordPressDraftRemoteOutcome.SUCCESS,
            41,
            "https://cms.example.com/?p=41",
            True,
            None,
            None,
        )
        return WordPressDeliveryResult(status, wordpress_attempt(WordPressAttemptState.SUCCESS), remote)
    if status is WordPressDeliveryStatus.FAILED_DEFINITELY:
        remote = WordPressDraftResult(
            WordPressDraftRemoteOutcome.FAILED_DEFINITELY,
            None,
            None,
            False,
            WordPressDraftFailureKind.AUTH_FAILED,
            "WordPress authentication failed.",
        )
        return WordPressDeliveryResult(
            status,
            wordpress_attempt(WordPressAttemptState.FAILED_DEFINITELY),
            remote,
        )
    if status is WordPressDeliveryStatus.UNKNOWN:
        remote = WordPressDraftResult(
            WordPressDraftRemoteOutcome.UNKNOWN,
            None,
            None,
            False,
            WordPressDraftFailureKind.TIMEOUT,
            "WordPress request timed out.",
        )
        return WordPressDeliveryResult(
            status,
            wordpress_attempt(WordPressAttemptState.UNKNOWN),
            remote,
        )
    return WordPressDeliveryResult(
        status,
        wordpress_attempt(WordPressAttemptState.PENDING),
        None,
    )


class FakeHistoryStore:
    def __init__(
        self,
        stored_artifact: ArtifactRecord | None,
        *,
        error: HistoryStoreError | None = None,
    ) -> None:
        self.stored_artifact = stored_artifact
        self.error = error
        self.get_calls: list[str] = []
        self.run_mutation_calls: list[str] = []

    def get_artifact(self, artifact_id: str) -> ArtifactRecord | None:
        self.get_calls.append(artifact_id)
        if self.error is not None:
            raise self.error
        return self.stored_artifact

    def create_run(self, *args: object, **kwargs: object) -> None:
        self.run_mutation_calls.append("create_run")
        raise AssertionError("Delivery must not create a planning run.")

    def finish_run(self, *args: object, **kwargs: object) -> None:
        self.run_mutation_calls.append("finish_run")
        raise AssertionError("Delivery must not mutate the planning run.")


class FakeWordPressDeliveryWorkflow:
    def __init__(self, result: WordPressDeliveryResult) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    async def deliver(
        self,
        run_id: str,
        content_draft_artifact_id: str,
        draft: DraftItem,
        target_site_url: str,
        *,
        title_override: str | None = None,
    ) -> WordPressDeliveryResult:
        self.calls.append(
            {
                "run_id": run_id,
                "content_draft_artifact_id": content_draft_artifact_id,
                "draft": draft,
                "target_site_url": target_site_url,
                "title_override": title_override,
            }
        )
        return self.result


def request(draft_id: str = "D2") -> ApprovedWordPressDraftDeliveryRequest:
    return ApprovedWordPressDraftDeliveryRequest(
        planning_run_id=RUN_ID,
        content_draft_artifact_id=ARTIFACT_ID,
        draft_id=draft_id,
        target_site_url=TARGET_URL,
        title_override="Approved title",
    )


class ApprovedWordPressDraftDeliveryRequestTests(unittest.TestCase):
    def test_malformed_draft_ids_are_rejected_before_delivery(self) -> None:
        for draft_id in ("", "1", "d1", "D0", "D01", "D1,D2"):
            with self.subTest(draft_id=draft_id):
                with self.assertRaises(ApprovedWordPressDraftDeliveryValidationError):
                    request(draft_id)


class ApprovedWordPressDraftDeliveryWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_success_loads_artifact_and_delivers_exact_d2_once(self) -> None:
        stored = artifact()
        history = FakeHistoryStore(stored)
        delivery = FakeWordPressDeliveryWorkflow(
            delivery_result(WordPressDeliveryStatus.SUCCESS)
        )
        workflow = ApprovedWordPressDraftDeliveryWorkflow(
            history_store=history,
            wordpress_delivery=delivery,
        )

        result = await workflow.deliver(request())

        self.assertEqual(history.get_calls, [ARTIFACT_ID])
        self.assertEqual(history.run_mutation_calls, [])
        self.assertEqual(len(delivery.calls), 1)
        self.assertIs(delivery.calls[0]["draft"], stored.payload.drafts[1])
        self.assertEqual(delivery.calls[0]["run_id"], RUN_ID)
        self.assertEqual(delivery.calls[0]["content_draft_artifact_id"], ARTIFACT_ID)
        self.assertEqual(delivery.calls[0]["target_site_url"], TARGET_URL)
        self.assertEqual(delivery.calls[0]["title_override"], "Approved title")
        self.assertEqual(result.planning_run_id, RUN_ID)
        self.assertEqual(result.content_draft_artifact_id, ARTIFACT_ID)
        self.assertEqual(result.selected_draft_id, "D2")
        self.assertIs(result.delivery_result, delivery.result)
        self.assertIs(result.attempt, delivery.result.attempt)
        self.assertFalse(result.reconciliation_required)

    async def test_d1_selects_d1_without_delivering_d2(self) -> None:
        stored = artifact()
        delivery = FakeWordPressDeliveryWorkflow(
            delivery_result(WordPressDeliveryStatus.SUCCESS)
        )
        workflow = ApprovedWordPressDraftDeliveryWorkflow(
            history_store=FakeHistoryStore(stored),
            wordpress_delivery=delivery,
        )

        result = await workflow.deliver(request("D1"))

        self.assertEqual(result.selected_draft_id, "D1")
        self.assertEqual(len(delivery.calls), 1)
        self.assertIs(delivery.calls[0]["draft"], stored.payload.drafts[0])

    async def test_nonexistent_draft_has_no_fallback_and_zero_delivery_calls(self) -> None:
        delivery = FakeWordPressDeliveryWorkflow(
            delivery_result(WordPressDeliveryStatus.SUCCESS)
        )
        workflow = ApprovedWordPressDraftDeliveryWorkflow(
            history_store=FakeHistoryStore(artifact()),
            wordpress_delivery=delivery,
        )

        with self.assertRaises(ApprovedWordPressDraftDeliveryValidationError):
            await workflow.deliver(request("D3"))

        self.assertEqual(delivery.calls, [])

    async def test_artifact_validation_failures_make_zero_delivery_calls(self) -> None:
        failed_report = ContentDraftReport(
            status=ContentDraftStatus.GENERATION_FAILED,
            drafts=(),
            limitations=(),
            error=None,
        )
        cases = {
            "missing": None,
            "wrong run": artifact(run_id=OTHER_RUN_ID),
            "wrong type": artifact(artifact_type=ArtifactType.CHANGE_PLAN),
            "unsupported version": artifact(payload_version=2),
            "unexpected payload": artifact(payload="not a report"),
            "failed report": artifact(payload=failed_report),
        }
        for name, stored in cases.items():
            with self.subTest(name=name):
                delivery = FakeWordPressDeliveryWorkflow(
                    delivery_result(WordPressDeliveryStatus.SUCCESS)
                )
                workflow = ApprovedWordPressDraftDeliveryWorkflow(
                    history_store=FakeHistoryStore(stored),
                    wordpress_delivery=delivery,
                )

                with self.assertRaises(
                    ApprovedWordPressDraftDeliveryValidationError
                ):
                    await workflow.deliver(request())

                self.assertEqual(delivery.calls, [])

    async def test_duplicate_draft_id_in_corrupted_report_is_rejected(self) -> None:
        corrupted = draft_report()
        object.__setattr__(
            corrupted,
            "drafts",
            (corrupted.drafts[0], corrupted.drafts[0]),
        )
        delivery = FakeWordPressDeliveryWorkflow(
            delivery_result(WordPressDeliveryStatus.SUCCESS)
        )
        workflow = ApprovedWordPressDraftDeliveryWorkflow(
            history_store=FakeHistoryStore(artifact(payload=corrupted)),
            wordpress_delivery=delivery,
        )

        with self.assertRaises(ApprovedWordPressDraftDeliveryValidationError):
            await workflow.deliver(request("D1"))

        self.assertEqual(delivery.calls, [])

    async def test_history_failure_propagates_without_delivery(self) -> None:
        expected = HistoryStoreError("stable history failure")
        history = FakeHistoryStore(artifact(), error=expected)
        delivery = FakeWordPressDeliveryWorkflow(
            delivery_result(WordPressDeliveryStatus.SUCCESS)
        )
        workflow = ApprovedWordPressDraftDeliveryWorkflow(
            history_store=history,
            wordpress_delivery=delivery,
        )

        with self.assertRaises(HistoryStoreError) as raised:
            await workflow.deliver(request())

        self.assertIs(raised.exception, expected)
        self.assertEqual(delivery.calls, [])

    async def test_failed_definitely_is_returned_without_retry(self) -> None:
        delivery = FakeWordPressDeliveryWorkflow(
            delivery_result(WordPressDeliveryStatus.FAILED_DEFINITELY)
        )
        workflow = ApprovedWordPressDraftDeliveryWorkflow(
            history_store=FakeHistoryStore(artifact()),
            wordpress_delivery=delivery,
        )

        result = await workflow.deliver(request())

        self.assertEqual(result.delivery_result.status, WordPressDeliveryStatus.FAILED_DEFINITELY)
        self.assertFalse(result.reconciliation_required)
        self.assertEqual(len(delivery.calls), 1)

    async def test_unknown_requires_reconciliation_without_retry(self) -> None:
        delivery = FakeWordPressDeliveryWorkflow(
            delivery_result(WordPressDeliveryStatus.UNKNOWN)
        )
        workflow = ApprovedWordPressDraftDeliveryWorkflow(
            history_store=FakeHistoryStore(artifact()),
            wordpress_delivery=delivery,
        )

        result = await workflow.deliver(request())

        self.assertEqual(result.delivery_result.status, WordPressDeliveryStatus.UNKNOWN)
        self.assertTrue(result.reconciliation_required)
        self.assertEqual(len(delivery.calls), 1)

    async def test_blocked_pending_requires_reconciliation_without_second_send(self) -> None:
        delivery = FakeWordPressDeliveryWorkflow(
            delivery_result(WordPressDeliveryStatus.BLOCKED)
        )
        workflow = ApprovedWordPressDraftDeliveryWorkflow(
            history_store=FakeHistoryStore(artifact()),
            wordpress_delivery=delivery,
        )

        result = await workflow.deliver(request())

        self.assertEqual(result.delivery_result.status, WordPressDeliveryStatus.BLOCKED)
        self.assertTrue(result.reconciliation_required)
        self.assertEqual(len(delivery.calls), 1)


if __name__ == "__main__":
    unittest.main()
