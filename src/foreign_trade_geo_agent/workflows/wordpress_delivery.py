"""Persist one safe WordPress draft-delivery attempt."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from uuid import uuid4

from foreign_trade_geo_agent.core.content_draft import DraftItem
from foreign_trade_geo_agent.core.history import (
    HistoryConflictError,
    WordPressAttemptState,
    WordPressDraftAttempt,
    site_key_from_url,
)
from foreign_trade_geo_agent.core.ports import ContentDraftPublisher, HistoryStore
from foreign_trade_geo_agent.core.wordpress_draft import (
    WordPressDraftRemoteOutcome,
    WordPressDraftResult,
    build_wordpress_draft_request,
    wordpress_request_fingerprint,
)


class WordPressDeliveryStatus(str, Enum):
    SUCCESS = "success"
    FAILED_DEFINITELY = "failed_definitely"
    UNKNOWN = "unknown"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class WordPressDeliveryResult:
    status: WordPressDeliveryStatus
    attempt: WordPressDraftAttempt
    remote_result: WordPressDraftResult | None


class WordPressDeliveryWorkflow:
    def __init__(
        self,
        *,
        publisher: ContentDraftPublisher,
        history_store: HistoryStore,
        id_factory: Callable[[], str] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._publisher = publisher
        self._history_store = history_store
        self._id_factory = id_factory or (lambda: str(uuid4()))
        self._clock = clock or (lambda: datetime.now(UTC))

    async def deliver(
        self,
        run_id: str,
        content_draft_artifact_id: str,
        draft: DraftItem,
        target_site_url: str,
        *,
        title_override: str | None = None,
    ) -> WordPressDeliveryResult:
        request = build_wordpress_draft_request(draft, title_override=title_override)
        target_site_key = site_key_from_url(target_site_url)
        fingerprint = wordpress_request_fingerprint(target_site_key, request)
        blocking = self._blocking_attempts(target_site_key, fingerprint)
        if blocking:
            return WordPressDeliveryResult(WordPressDeliveryStatus.BLOCKED, blocking[0], None)

        pending = WordPressDraftAttempt(
            attempt_id=self._id_factory(),
            run_id=run_id,
            content_draft_artifact_id=content_draft_artifact_id,
            draft_item_id=draft.draft_id,
            target_site_key=target_site_key,
            fingerprint_version=1,
            request_fingerprint=fingerprint,
            attempted_at=self._clock(),
            completed_at=None,
            outcome=WordPressAttemptState.PENDING,
            remote_post_id=None,
            remote_link=None,
            failure_kind=None,
            sanitized_error=None,
        )
        try:
            self._history_store.begin_wordpress_attempt(pending)
        except HistoryConflictError:
            blocking = self._blocking_attempts(target_site_key, fingerprint)
            if blocking:
                return WordPressDeliveryResult(WordPressDeliveryStatus.BLOCKED, blocking[0], None)
            raise

        remote = await self._publisher.publish_draft(request)
        attempt_state = WordPressAttemptState(remote.outcome.value)
        terminal = self._history_store.finish_wordpress_attempt(
            pending.attempt_id,
            outcome=attempt_state,
            completed_at=self._clock(),
            remote_post_id=remote.remote_post_id,
            remote_link=remote.remote_link,
            failure_kind=None if remote.failure_kind is None else remote.failure_kind.value,
            sanitized_error=remote.error,
        )
        return WordPressDeliveryResult(
            WordPressDeliveryStatus(remote.outcome.value),
            terminal,
            remote,
        )

    def _blocking_attempts(
        self,
        target_site_key: str,
        fingerprint: str,
    ) -> tuple[WordPressDraftAttempt, ...]:
        return tuple(
            attempt
            for attempt in self._history_store.find_wordpress_attempts_by_fingerprint(
                target_site_key,
                fingerprint,
            )
            if attempt.outcome in {
                WordPressAttemptState.PENDING,
                WordPressAttemptState.SUCCESS,
                WordPressAttemptState.UNKNOWN,
            }
        )
