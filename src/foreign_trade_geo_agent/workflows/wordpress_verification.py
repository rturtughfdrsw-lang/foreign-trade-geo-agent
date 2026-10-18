"""Remote read-only verification with append-only local history.

Remote verification is read-only (GET only). Local verification history is
append-only: the original ``wordpress_draft_attempts`` create outcome is never
rewritten by a verification.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from foreign_trade_geo_agent.core.history import (
    WordPressAttemptState,
    WordPressDraftAttempt,
    WordPressVerification,
    WordPressVerificationFailureKind,
    WordPressVerificationLookupKind,
    WordPressVerificationOutcome,
    site_key_from_url,
)
from foreign_trade_geo_agent.core.ports import HistoryStore, WordPressDraftReader
from foreign_trade_geo_agent.core.wordpress_verification import (
    WordPressDraftReadOutcome,
    WordPressDraftReadRequest,
    WordPressDraftReadResult,
    WordPressDraftVerificationResult,
    WordPressVerificationRequest,
)


_NO_REMOTE_IDENTIFIER_ERROR = "No remote identifier is available for this attempt."
_SITE_MISMATCH_ERROR = "The remote reader targets a different site."


class WordPressVerificationError(RuntimeError):
    """A sanitized local failure while loading or persisting verification."""


class WordPressDraftVerificationWorkflow:
    """Verify one persisted attempt without any remote write capability."""

    def __init__(
        self,
        *,
        history_store: HistoryStore,
        draft_reader_factory: Callable[[str], WordPressDraftReader],
        id_factory: Callable[[], str] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._history_store = history_store
        self._draft_reader_factory = draft_reader_factory
        self._id_factory = id_factory or (lambda: str(uuid4()))
        self._clock = clock or (lambda: datetime.now(UTC))

    async def verify(
        self,
        request: WordPressVerificationRequest,
    ) -> WordPressDraftVerificationResult:
        if not isinstance(request, WordPressVerificationRequest):
            raise TypeError(
                "WordPress verification requires its stable request model."
            )
        attempt = await asyncio.to_thread(
            self._history_store.get_wordpress_attempt,
            request.attempt_id,
        )
        if not isinstance(attempt, WordPressDraftAttempt):
            raise WordPressVerificationError("WordPress attempt was not found.")

        if attempt.outcome is WordPressAttemptState.FAILED_DEFINITELY:
            return WordPressDraftVerificationResult(
                attempt=attempt,
                verification=None,
            )

        if attempt.remote_post_id is None:
            verification = self._record(
                attempt,
                outcome=WordPressVerificationOutcome.UNRESOLVED,
                lookup_kind=WordPressVerificationLookupKind.NONE,
                failure_kind=WordPressVerificationFailureKind.NO_REMOTE_IDENTIFIER,
                observed_remote_post_id=None,
                observed_status=None,
                sanitized_error=_NO_REMOTE_IDENTIFIER_ERROR,
            )
            await asyncio.to_thread(
                self._history_store.append_wordpress_verification,
                verification,
            )
            return WordPressDraftVerificationResult(
                attempt=attempt,
                verification=verification,
            )

        reader = self._draft_reader_factory(attempt.target_site_key)
        if reader.target_site_key != attempt.target_site_key:
            verification = self._record(
                attempt,
                outcome=WordPressVerificationOutcome.UNRESOLVED,
                lookup_kind=WordPressVerificationLookupKind.NONE,
                failure_kind=WordPressVerificationFailureKind.SITE_MISMATCH,
                observed_remote_post_id=None,
                observed_status=None,
                sanitized_error=_SITE_MISMATCH_ERROR,
            )
            await asyncio.to_thread(
                self._history_store.append_wordpress_verification,
                verification,
            )
            return WordPressDraftVerificationResult(
                attempt=attempt,
                verification=verification,
            )

        try:
            read = await reader.read_draft(
                WordPressDraftReadRequest(remote_post_id=attempt.remote_post_id)
            )
        except Exception:
            read = WordPressDraftReadResult(
                outcome=WordPressDraftReadOutcome.FAILED,
                remote_post_id=None,
                status=None,
                link=None,
                has_title=False,
                has_content=False,
                failure_kind=WordPressVerificationFailureKind.REQUEST_FAILED,
                error="WordPress draft read failed unexpectedly.",
            )

        (
            outcome,
            failure_kind,
            observed_remote_post_id,
            observed_status,
            sanitized_error,
        ) = self._classify(read, attempt)
        verification = self._record(
            attempt,
            outcome=outcome,
            lookup_kind=WordPressVerificationLookupKind.REMOTE_ID,
            failure_kind=failure_kind,
            observed_remote_post_id=observed_remote_post_id,
            observed_status=observed_status,
            sanitized_error=sanitized_error,
        )
        await asyncio.to_thread(
            self._history_store.append_wordpress_verification,
            verification,
        )
        return WordPressDraftVerificationResult(
            attempt=attempt,
            verification=verification,
        )

    @staticmethod
    def _classify(
        read: WordPressDraftReadResult,
        attempt: WordPressDraftAttempt,
    ) -> tuple[
        WordPressVerificationOutcome,
        WordPressVerificationFailureKind | None,
        int | None,
        str | None,
        str | None,
    ]:
        if read.outcome is WordPressDraftReadOutcome.NOT_FOUND:
            return (WordPressVerificationOutcome.NOT_FOUND, None, None, None, None)
        if read.outcome is WordPressDraftReadOutcome.FAILED:
            return (
                WordPressVerificationOutcome.UNKNOWN,
                read.failure_kind
                or WordPressVerificationFailureKind.REQUEST_FAILED,
                None,
                None,
                read.error or "WordPress draft read failed.",
            )
        if read.remote_post_id != attempt.remote_post_id:
            return (
                WordPressVerificationOutcome.MISMATCH,
                WordPressVerificationFailureKind.POST_ID_MISMATCH,
                read.remote_post_id,
                read.status,
                "WordPress returned a different post ID.",
            )
        if read.status != "draft":
            return (
                WordPressVerificationOutcome.MISMATCH,
                WordPressVerificationFailureKind.RESPONSE_NOT_DRAFT,
                read.remote_post_id,
                read.status,
                "WordPress reported a non-draft status.",
            )
        link_site_key: str | None = None
        if read.link is not None:
            try:
                link_site_key = site_key_from_url(read.link)
            except ValueError:
                link_site_key = None
        if link_site_key != attempt.target_site_key:
            return (
                WordPressVerificationOutcome.MISMATCH,
                WordPressVerificationFailureKind.LINK_ORIGIN_MISMATCH,
                read.remote_post_id,
                read.status,
                "WordPress reported a link outside the target site.",
            )
        return (
            WordPressVerificationOutcome.VERIFIED,
            None,
            read.remote_post_id,
            "draft",
            None,
        )

    def _record(
        self,
        attempt: WordPressDraftAttempt,
        *,
        outcome: WordPressVerificationOutcome,
        lookup_kind: WordPressVerificationLookupKind,
        failure_kind: WordPressVerificationFailureKind | None,
        observed_remote_post_id: int | None,
        observed_status: str | None,
        sanitized_error: str | None,
    ) -> WordPressVerification:
        return WordPressVerification(
            verification_id=self._id_factory(),
            attempt_id=attempt.attempt_id,
            run_id=attempt.run_id,
            content_draft_artifact_id=attempt.content_draft_artifact_id,
            draft_item_id=attempt.draft_item_id,
            target_site_key=attempt.target_site_key,
            lookup_kind=lookup_kind,
            observed_remote_post_id=observed_remote_post_id,
            observed_status=observed_status,
            outcome=outcome,
            failure_kind=failure_kind,
            sanitized_error=sanitized_error,
            verified_at=self._clock(),
        )
