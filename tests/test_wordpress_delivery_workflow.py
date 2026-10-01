from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from contextlib import closing
import sqlite3

import httpx

from foreign_trade_geo_agent.adapters.wordpress_rest import WordPressRestDraftPublisher

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
    RunStatus,
    WordPressAttemptState,
    WorkflowRun,
)
from foreign_trade_geo_agent.core.wordpress_draft import (
    WordPressDraftFailureKind,
    WordPressDraftRemoteOutcome,
    WordPressDraftRequest,
    WordPressDraftResult,
    wordpress_request_fingerprint,
)
from foreign_trade_geo_agent.storage.sqlite import SQLiteHistoryStore
from foreign_trade_geo_agent.workflows.wordpress_delivery import (
    WordPressDeliveryStatus,
    WordPressDeliveryWorkflow,
)


RUN_ID = "11111111-1111-4111-8111-111111111111"
ARTIFACT_ID = "22222222-2222-4222-8222-222222222222"
ATTEMPT_1 = "33333333-3333-4333-8333-333333333333"
ATTEMPT_2 = "44444444-4444-4444-8444-444444444444"
NOW = datetime(2026, 10, 2, 8, 30, tzinfo=UTC)
TARGET_URL = "https://cms.example.com/wp-admin?ignored=1"


def draft_item() -> DraftItem:
    claim = DraftClaim(
        claim_id="CL1",
        text="Safe body",
        claim_type=DraftClaimType.GENERAL_TECHNICAL_CONTEXT,
        support_kind=DraftClaimSupportKind.EXTERNAL_CONTEXT,
        page_refs=(),
        source_refs=("S1",),
    )
    return DraftItem(
        draft_id="D1",
        change_ref="C1",
        opportunity_ref="R1",
        draft_type=ContentDraftType.NEW_RESOURCE_DRAFT,
        target_kind=ChangeTargetKind.CREATE_NEW_PAGE,
        target_page_ref=None,
        locator=SectionLocator(SectionLocatorKind.NEW_PAGE, None, None, None, None),
        heading="Buyer Guide",
        ordered_headings=(),
        blocks=(ParagraphBlock(DraftBlockKind.PARAGRAPH, (claim,)),),
        page_refs=(),
        source_refs=("S1",),
    )


def draft_report() -> ContentDraftReport:
    return ContentDraftReport(
        status=ContentDraftStatus.SUCCESS,
        drafts=(draft_item(),),
        limitations=CONTENT_DRAFT_LIMITATIONS,
        error=None,
    )


class FakePublisher:
    def __init__(self, result: WordPressDraftResult, store: SQLiteHistoryStore | None = None) -> None:
        self.result = result
        self.store = store
        self.calls: list[WordPressDraftRequest] = []
        self.observed_pending = False

    async def publish_draft(self, request: WordPressDraftRequest) -> WordPressDraftResult:
        self.calls.append(request)
        if self.store is not None:
            attempts = self.store.list_wordpress_attempts(RUN_ID)
            self.observed_pending = len(attempts) == 1 and attempts[0].outcome is WordPressAttemptState.PENDING
        return self.result


class FailingStore:
    def __init__(self, delegate: SQLiteHistoryStore, *, fail_begin: bool = False, fail_finish: bool = False) -> None:
        self.delegate = delegate
        self.fail_begin = fail_begin
        self.fail_finish = fail_finish

    def __getattr__(self, name: str):
        return getattr(self.delegate, name)

    def begin_wordpress_attempt(self, attempt):
        if self.fail_begin:
            raise HistoryStoreError("sanitized storage failure")
        return self.delegate.begin_wordpress_attempt(attempt)

    def finish_wordpress_attempt(self, *args, **kwargs):
        if self.fail_finish:
            raise HistoryStoreError("sanitized storage failure")
        return self.delegate.finish_wordpress_attempt(*args, **kwargs)


class WordPressFingerprintTests(unittest.TestCase):
    def test_v1_fingerprint_is_canonical_and_sensitive_to_exact_request_and_origin(self) -> None:
        request = WordPressDraftRequest("Buyer Guide", "<p>Safe body</p>")
        actual = wordpress_request_fingerprint("https://cms.example.com:443", request)
        self.assertEqual(actual, "34517c17d3d5db81ddbc647c92f211963a438b836749575a4c1d08384e635ab3")
        self.assertNotEqual(actual, wordpress_request_fingerprint("https://other.example:443", request))
        self.assertNotEqual(actual, wordpress_request_fingerprint("https://cms.example.com:443", WordPressDraftRequest("Buyer Guide ", request.content)))
        self.assertNotEqual(actual, wordpress_request_fingerprint("https://cms.example.com:443", WordPressDraftRequest(request.title, request.content + " ")))


class WordPressDeliveryWorkflowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "history.sqlite3"
        self.store = SQLiteHistoryStore(self.db_path)
        self.store.create_run(
            WorkflowRun(RUN_ID, "https://example.com:443", "content_draft", NOW, None, RunStatus.RUNNING, None, None)
        )
        self.store.append_artifact(
            ArtifactRecord(ARTIFACT_ID, RUN_ID, ArtifactType.CONTENT_DRAFT, 1, NOW, draft_report())
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    async def test_pending_is_committed_before_one_network_call_then_success_is_recorded(self) -> None:
        publisher = FakePublisher(
            WordPressDraftResult(WordPressDraftRemoteOutcome.SUCCESS, 41, "https://cms.example.com/?p=41", True, None, None),
            self.store,
        )
        workflow = WordPressDeliveryWorkflow(
            publisher=publisher,
            history_store=self.store,
            id_factory=lambda: ATTEMPT_1,
            clock=lambda: NOW + timedelta(minutes=1),
        )
        result = await workflow.deliver(RUN_ID, ARTIFACT_ID, draft_item(), TARGET_URL)
        self.assertTrue(publisher.observed_pending)
        self.assertEqual(len(publisher.calls), 1)
        self.assertEqual(result.status, WordPressDeliveryStatus.SUCCESS)
        self.assertEqual(result.attempt.outcome, WordPressAttemptState.SUCCESS)

    async def test_store_failure_before_network_makes_zero_calls(self) -> None:
        publisher = FakePublisher(WordPressDraftResult(WordPressDraftRemoteOutcome.UNKNOWN, None, None, False, WordPressDraftFailureKind.TIMEOUT, "WordPress request timed out."))
        workflow = WordPressDeliveryWorkflow(
            publisher=publisher,
            history_store=FailingStore(self.store, fail_begin=True),
            id_factory=lambda: ATTEMPT_1,
            clock=lambda: NOW + timedelta(minutes=1),
        )
        with self.assertRaises(HistoryStoreError):
            await workflow.deliver(RUN_ID, ARTIFACT_ID, draft_item(), TARGET_URL)
        self.assertEqual(publisher.calls, [])

    async def test_terminal_store_failure_after_remote_call_leaves_pending(self) -> None:
        publisher = FakePublisher(WordPressDraftResult(WordPressDraftRemoteOutcome.SUCCESS, 41, "https://cms.example.com/?p=41", True, None, None))
        workflow = WordPressDeliveryWorkflow(
            publisher=publisher,
            history_store=FailingStore(self.store, fail_finish=True),
            id_factory=lambda: ATTEMPT_1,
            clock=lambda: NOW + timedelta(minutes=1),
        )
        with self.assertRaises(HistoryStoreError):
            await workflow.deliver(RUN_ID, ARTIFACT_ID, draft_item(), TARGET_URL)
        self.assertEqual(len(publisher.calls), 1)
        self.assertEqual(self.store.list_wordpress_attempts(RUN_ID)[0].outcome, WordPressAttemptState.PENDING)

    async def test_unknown_is_persisted_and_blocks_automatic_resend(self) -> None:
        publisher = FakePublisher(WordPressDraftResult(WordPressDraftRemoteOutcome.UNKNOWN, None, None, False, WordPressDraftFailureKind.TIMEOUT, "WordPress request timed out."))
        first = WordPressDeliveryWorkflow(publisher=publisher, history_store=self.store, id_factory=lambda: ATTEMPT_1, clock=lambda: NOW + timedelta(minutes=1))
        result = await first.deliver(RUN_ID, ARTIFACT_ID, draft_item(), TARGET_URL)
        self.assertEqual(result.attempt.outcome, WordPressAttemptState.UNKNOWN)
        second = WordPressDeliveryWorkflow(publisher=publisher, history_store=self.store, id_factory=lambda: ATTEMPT_2, clock=lambda: NOW + timedelta(minutes=2))
        blocked = await second.deliver(RUN_ID, ARTIFACT_ID, draft_item(), TARGET_URL)
        self.assertEqual(blocked.status, WordPressDeliveryStatus.BLOCKED)
        self.assertEqual(len(publisher.calls), 1)

    async def test_credentials_and_upstream_body_secret_are_not_persisted_in_attempt_metadata(self) -> None:
        sentinel = "WP_SECRET_SENTINEL_52d198"
        publisher = WordPressRestDraftPublisher(
            base_url="https://cms.example.com",
            username=sentinel,
            application_password=sentinel,
            transport=httpx.MockTransport(
                lambda request: httpx.Response(401, text=f"Authorization Bearer {sentinel}")
            ),
        )
        workflow = WordPressDeliveryWorkflow(
            publisher=publisher,
            history_store=self.store,
            id_factory=lambda: ATTEMPT_1,
            clock=lambda: NOW + timedelta(minutes=1),
        )
        result = await workflow.deliver(RUN_ID, ARTIFACT_ID, draft_item(), TARGET_URL)
        self.assertEqual(result.status, WordPressDeliveryStatus.FAILED_DEFINITELY)
        with closing(sqlite3.connect(self.db_path)) as connection:
            row = connection.execute(
                "SELECT target_site_key,request_fingerprint,failure_kind,sanitized_error FROM wordpress_draft_attempts"
            ).fetchone()
        self.assertNotIn(sentinel, "|".join(str(value) for value in row))


if __name__ == "__main__":
    unittest.main()
