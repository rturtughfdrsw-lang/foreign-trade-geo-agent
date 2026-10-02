"""Provider-independent read-back and verification models for WordPress drafts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .history import (
    WordPressAttemptState,
    WordPressDraftAttempt,
    WordPressVerification,
    WordPressVerificationFailureKind,
    WordPressVerificationOutcome,
    validate_uuid,
)
from .wordpress_draft import normalize_wordpress_https_url


class WordPressVerificationValidationError(ValueError):
    """A deterministic local validation failure before any read happens."""


@dataclass(frozen=True, slots=True)
class WordPressVerificationRequest:
    attempt_id: str

    def __post_init__(self) -> None:
        try:
            validate_uuid(self.attempt_id, "attempt_id")
        except ValueError:
            raise WordPressVerificationValidationError(
                "Verification attempt identifier is invalid."
            ) from None


class WordPressDraftReadOutcome(str, Enum):
    """Result of one bounded, authenticated GET of a remote draft."""

    FOUND = "found"
    NOT_FOUND = "not_found"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class WordPressDraftReadRequest:
    remote_post_id: int

    def __post_init__(self) -> None:
        if type(self.remote_post_id) is not int or self.remote_post_id <= 0:
            raise ValueError("WordPress draft read requires a positive post ID.")


@dataclass(frozen=True, slots=True)
class WordPressDraftReadResult:
    outcome: WordPressDraftReadOutcome
    remote_post_id: int | None
    status: str | None
    link: str | None
    has_title: bool
    has_content: bool
    failure_kind: WordPressVerificationFailureKind | None
    error: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, WordPressDraftReadOutcome):
            raise ValueError("WordPress draft read outcome is invalid.")
        if type(self.has_title) is not bool or type(self.has_content) is not bool:
            raise ValueError("WordPress draft read presence flags are invalid.")
        if self.failure_kind is not None and not isinstance(
            self.failure_kind,
            WordPressVerificationFailureKind,
        ):
            raise ValueError("WordPress draft read failure kind is invalid.")
        if self.remote_post_id is not None and (
            type(self.remote_post_id) is not int or self.remote_post_id <= 0
        ):
            raise ValueError("WordPress draft read post ID is invalid.")
        if self.link is not None and normalize_wordpress_https_url(self.link) != self.link:
            raise ValueError("WordPress draft read link is invalid.")
        if self.error is not None and (
            type(self.error) is not str
            or not self.error.strip()
            or len(self.error) > 512
            or any(
                ord(character) < 32 or ord(character) == 127
                for character in self.error
            )
        ):
            raise ValueError("WordPress draft read error is invalid.")

        if self.outcome is WordPressDraftReadOutcome.FOUND:
            valid = (
                self.remote_post_id is not None
                and type(self.status) is str
                and bool(self.status.strip())
                and self.failure_kind is None
                and self.error is None
            )
        elif self.outcome is WordPressDraftReadOutcome.NOT_FOUND:
            valid = (
                self.remote_post_id is None
                and self.status is None
                and self.link is None
                and not self.has_title
                and not self.has_content
                and self.failure_kind is None
                and self.error is None
            )
        else:
            valid = (
                self.remote_post_id is None
                and self.status is None
                and self.failure_kind is not None
                and self.error is not None
            )
        if not valid:
            raise ValueError("WordPress draft read fields are inconsistent.")


@dataclass(frozen=True, slots=True)
class WordPressDraftVerificationResult:
    attempt: WordPressDraftAttempt
    verification: WordPressVerification | None

    def __post_init__(self) -> None:
        if not isinstance(self.attempt, WordPressDraftAttempt):
            raise TypeError("Verification result requires a WordPressDraftAttempt.")
        if self.attempt.outcome is WordPressAttemptState.FAILED_DEFINITELY:
            if self.verification is not None:
                raise ValueError(
                    "A definitely failed create requires no verification record."
                )
            return
        if not isinstance(self.verification, WordPressVerification):
            raise ValueError(
                "A verifiable create attempt requires one verification record."
            )
        if (
            self.verification.attempt_id != self.attempt.attempt_id
            or self.verification.run_id != self.attempt.run_id
            or self.verification.content_draft_artifact_id
            != self.attempt.content_draft_artifact_id
            or self.verification.draft_item_id != self.attempt.draft_item_id
            or self.verification.target_site_key != self.attempt.target_site_key
        ):
            raise ValueError("Verification record does not match its attempt.")

    @property
    def not_applicable(self) -> bool:
        return self.verification is None

    @property
    def verification_outcome(self) -> WordPressVerificationOutcome | None:
        return None if self.verification is None else self.verification.outcome

    @property
    def manual_action_required(self) -> bool:
        return (
            self.verification is not None
            and self.verification.outcome is not WordPressVerificationOutcome.VERIFIED
        )
