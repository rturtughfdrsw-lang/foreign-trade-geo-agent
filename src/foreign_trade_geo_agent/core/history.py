"""Provider-independent historical persistence models and errors."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from urllib.parse import urlsplit
from uuid import UUID
import re

from .fetching import UrlOrigin


class HistoryStoreError(RuntimeError):
    """A stable persistence-boundary failure."""


class HistoryConflictError(HistoryStoreError):
    """The requested append or state transition conflicts with history."""


class UnsupportedHistoryVersionError(HistoryStoreError):
    """A database or payload version is not supported."""


class MalformedHistoryDataError(HistoryStoreError):
    """Persisted data cannot be safely reconstructed."""


class RunStatus(str, Enum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    NEEDS_RECONCILIATION = "needs_reconciliation"


class ArtifactType(str, Enum):
    SITE_CONTENT = "site_content"
    SITE_AUDIT = "site_audit"
    VISIBILITY = "visibility"
    SITE_OPTIMIZATION = "site_optimization"
    INDUSTRY_RESEARCH = "industry_research"
    CONTENT_OPPORTUNITY = "content_opportunity"
    CHANGE_PLAN = "change_plan"
    CONTENT_DRAFT = "content_draft"


class WordPressAttemptState(str, Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED_DEFINITELY = "failed_definitely"
    UNKNOWN = "unknown"


class WordPressVerificationOutcome(str, Enum):
    """How one independent read-back of a remote draft resolved."""

    VERIFIED = "verified"
    NOT_FOUND = "not_found"
    MISMATCH = "mismatch"
    UNKNOWN = "unknown"
    UNRESOLVED = "unresolved"


class WordPressVerificationLookupKind(str, Enum):
    """Which lookup strategy a verification used."""

    REMOTE_ID = "remote_id"
    NONE = "none"


class WordPressVerificationFailureKind(str, Enum):
    """Sanitized reasons a verification could not confirm a remote draft."""

    NO_REMOTE_IDENTIFIER = "no_remote_identifier"
    SITE_MISMATCH = "site_mismatch"
    TIMEOUT = "timeout"
    REQUEST_FAILED = "request_failed"
    REDIRECT_REJECTED = "redirect_rejected"
    AUTH_FAILED = "auth_failed"
    HTTP_STATUS = "http_status"
    RESPONSE_TOO_LARGE = "response_too_large"
    MALFORMED_RESPONSE = "malformed_response"
    POST_ID_MISMATCH = "post_id_mismatch"
    RESPONSE_NOT_DRAFT = "response_not_draft"
    LINK_ORIGIN_MISMATCH = "link_origin_mismatch"


_REMOTE_ONLY_FAILURE_KINDS = frozenset(
    {
        WordPressVerificationFailureKind.TIMEOUT,
        WordPressVerificationFailureKind.REQUEST_FAILED,
        WordPressVerificationFailureKind.REDIRECT_REJECTED,
        WordPressVerificationFailureKind.AUTH_FAILED,
        WordPressVerificationFailureKind.HTTP_STATUS,
        WordPressVerificationFailureKind.RESPONSE_TOO_LARGE,
        WordPressVerificationFailureKind.MALFORMED_RESPONSE,
    }
)
_MISMATCH_FAILURE_KINDS = frozenset(
    {
        WordPressVerificationFailureKind.POST_ID_MISMATCH,
        WordPressVerificationFailureKind.RESPONSE_NOT_DRAFT,
        WordPressVerificationFailureKind.LINK_ORIGIN_MISMATCH,
    }
)
_UNRESOLVED_FAILURE_KINDS = frozenset(
    {
        WordPressVerificationFailureKind.NO_REMOTE_IDENTIFIER,
        WordPressVerificationFailureKind.SITE_MISMATCH,
    }
)


def site_key_from_url(url: str) -> str:
    """Return a credential-free exact-origin identity with an effective port."""

    if type(url) is not str or not url or len(url) > 2_048:
        raise ValueError("Site URL is invalid.")
    if "\\" in url or any(character.isspace() or ord(character) == 127 for character in url):
        raise ValueError("Site URL is invalid.")
    try:
        parsed = urlsplit(url)
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("Site URL must not contain credentials.")
        scheme = parsed.scheme.casefold()
        if scheme not in {"http", "https"} or parsed.hostname is None:
            raise ValueError("Site URL is invalid.")
        port = parsed.port if parsed.port is not None else (443 if scheme == "https" else 80)
        origin = UrlOrigin(scheme, parsed.hostname, port)
    except ValueError as exc:
        if str(exc) == "Site URL must not contain credentials.":
            raise
        raise ValueError("Site URL is invalid.") from exc
    host = f"[{origin.host}]" if ":" in origin.host else origin.host
    return f"{origin.scheme}://{host}:{origin.port}"


def validate_uuid(value: object, field_name: str) -> str:
    if type(value) is not str:
        raise ValueError(f"{field_name} must be a canonical UUID string.")
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"{field_name} must be a canonical UUID string.") from exc
    if str(parsed) != value:
        raise ValueError(f"{field_name} must be a canonical UUID string.")
    return value


def validate_aware_datetime(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be an aware datetime.")
    return value


def validate_optional_sanitized_text(value: object, field_name: str) -> None:
    if value is None:
        return
    if (
        type(value) is not str
        or not value.strip()
        or len(value) > 512
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ValueError(f"{field_name} is invalid.")


@dataclass(frozen=True, slots=True)
class WorkflowRun:
    run_id: str
    site_key: str
    workflow_name: str
    started_at: datetime
    completed_at: datetime | None
    status: RunStatus
    failure_kind: str | None
    sanitized_error: str | None

    def __post_init__(self) -> None:
        validate_uuid(self.run_id, "run_id")
        if type(self.site_key) is not str or site_key_from_url(self.site_key) != self.site_key:
            raise ValueError("site_key is invalid.")
        if type(self.workflow_name) is not str or not self.workflow_name.strip():
            raise ValueError("workflow_name is required.")
        validate_aware_datetime(self.started_at, "started_at")
        if self.completed_at is not None:
            validate_aware_datetime(self.completed_at, "completed_at")
            if self.completed_at < self.started_at:
                raise ValueError("completed_at cannot precede started_at.")
        if not isinstance(self.status, RunStatus):
            raise ValueError("Run status is invalid.")
        validate_optional_sanitized_text(self.failure_kind, "failure_kind")
        validate_optional_sanitized_text(self.sanitized_error, "sanitized_error")
        if self.status is RunStatus.RUNNING:
            if self.completed_at is not None or self.failure_kind is not None or self.sanitized_error is not None:
                raise ValueError("A running run cannot have terminal fields.")
        elif self.completed_at is None:
            raise ValueError("A terminal run requires completed_at.")
        elif self.status is RunStatus.SUCCEEDED:
            if self.failure_kind is not None or self.sanitized_error is not None:
                raise ValueError("A successful run cannot have failure fields.")
        elif self.failure_kind is None or self.sanitized_error is None:
            raise ValueError("A failed or uncertain run requires sanitized failure fields.")


@dataclass(frozen=True, slots=True)
class ArtifactRecord:
    artifact_id: str
    run_id: str
    artifact_type: ArtifactType
    payload_version: int
    created_at: datetime
    payload: object

    def __post_init__(self) -> None:
        validate_uuid(self.artifact_id, "artifact_id")
        validate_uuid(self.run_id, "run_id")
        if not isinstance(self.artifact_type, ArtifactType):
            raise ValueError("Artifact type is invalid.")
        if type(self.payload_version) is not int or self.payload_version <= 0:
            raise ValueError("Artifact payload version is invalid.")
        validate_aware_datetime(self.created_at, "created_at")


@dataclass(frozen=True, slots=True)
class WordPressDraftAttempt:
    attempt_id: str
    run_id: str
    content_draft_artifact_id: str
    draft_item_id: str
    target_site_key: str
    fingerprint_version: int
    request_fingerprint: str
    attempted_at: datetime
    completed_at: datetime | None
    outcome: WordPressAttemptState
    remote_post_id: int | None
    remote_link: str | None
    failure_kind: str | None
    sanitized_error: str | None

    def __post_init__(self) -> None:
        validate_uuid(self.attempt_id, "attempt_id")
        validate_uuid(self.run_id, "run_id")
        validate_uuid(self.content_draft_artifact_id, "content_draft_artifact_id")
        if type(self.draft_item_id) is not str or re.fullmatch(r"D[1-9][0-9]*", self.draft_item_id) is None:
            raise ValueError("draft_item_id is invalid.")
        if type(self.target_site_key) is not str or site_key_from_url(self.target_site_key) != self.target_site_key:
            raise ValueError("target_site_key is invalid.")
        if type(self.fingerprint_version) is not int or self.fingerprint_version != 1:
            raise ValueError("fingerprint_version is unsupported.")
        if type(self.request_fingerprint) is not str or re.fullmatch(r"[0-9a-f]{64}", self.request_fingerprint) is None:
            raise ValueError("request_fingerprint is invalid.")
        validate_aware_datetime(self.attempted_at, "attempted_at")
        if self.completed_at is not None:
            validate_aware_datetime(self.completed_at, "completed_at")
            if self.completed_at < self.attempted_at:
                raise ValueError("completed_at cannot precede attempted_at.")
        if not isinstance(self.outcome, WordPressAttemptState):
            raise ValueError("WordPress attempt outcome is invalid.")
        validate_optional_sanitized_text(self.failure_kind, "failure_kind")
        validate_optional_sanitized_text(self.sanitized_error, "sanitized_error")
        if self.outcome is WordPressAttemptState.PENDING:
            if any(value is not None for value in (self.completed_at, self.remote_post_id, self.remote_link, self.failure_kind, self.sanitized_error)):
                raise ValueError("Pending WordPress attempt fields are inconsistent.")
        elif self.outcome is WordPressAttemptState.SUCCESS:
            if (
                self.completed_at is None
                or type(self.remote_post_id) is not int
                or self.remote_post_id <= 0
                or not valid_public_remote_link(self.remote_link)
                or self.failure_kind is not None
                or self.sanitized_error is not None
            ):
                raise ValueError("Successful WordPress attempt fields are inconsistent.")
        elif (
            self.completed_at is None
            or self.remote_post_id is not None
            or self.remote_link is not None
            or self.failure_kind is None
            or self.sanitized_error is None
        ):
            raise ValueError("Failed or uncertain WordPress attempt fields are inconsistent.")


def valid_public_remote_link(value: object) -> bool:
    if type(value) is not str or not value or len(value) > 2_048:
        return False
    if "\\" in value or any(character.isspace() or ord(character) == 127 for character in value):
        return False
    try:
        parsed = urlsplit(value)
        scheme = parsed.scheme.casefold()
        hostname = parsed.hostname
        username = parsed.username
        password = parsed.password
        port = parsed.port
    except ValueError:
        return False
    return (
        scheme == "https"
        and hostname is not None
        and username is None
        and password is None
        and (port is None or 1 <= port <= 65_535)
    )


@dataclass(frozen=True, slots=True)
class WordPressVerification:
    """One append-only, independent read-back record for a draft attempt.

    ``UNKNOWN`` means a remote lookup was attempted but stayed inconclusive;
    ``UNRESOLVED`` means no safe remote lookup was possible at all. The two must
    never be conflated, so the shape of each record is enforced here and in
    SQLite.
    """

    verification_id: str
    attempt_id: str
    run_id: str
    content_draft_artifact_id: str
    draft_item_id: str
    target_site_key: str
    lookup_kind: WordPressVerificationLookupKind
    observed_remote_post_id: int | None
    observed_status: str | None
    outcome: WordPressVerificationOutcome
    failure_kind: WordPressVerificationFailureKind | None
    sanitized_error: str | None
    verified_at: datetime

    def __post_init__(self) -> None:
        validate_uuid(self.verification_id, "verification_id")
        validate_uuid(self.attempt_id, "attempt_id")
        validate_uuid(self.run_id, "run_id")
        validate_uuid(
            self.content_draft_artifact_id,
            "content_draft_artifact_id",
        )
        if (
            type(self.draft_item_id) is not str
            or re.fullmatch(r"D[1-9][0-9]*", self.draft_item_id) is None
        ):
            raise ValueError("draft_item_id is invalid.")
        if (
            type(self.target_site_key) is not str
            or site_key_from_url(self.target_site_key) != self.target_site_key
        ):
            raise ValueError("target_site_key is invalid.")
        if not isinstance(self.lookup_kind, WordPressVerificationLookupKind):
            raise ValueError("verification lookup kind is invalid.")
        if not isinstance(self.outcome, WordPressVerificationOutcome):
            raise ValueError("verification outcome is invalid.")
        if self.failure_kind is not None and not isinstance(
            self.failure_kind,
            WordPressVerificationFailureKind,
        ):
            raise ValueError("verification failure kind is invalid.")
        validate_aware_datetime(self.verified_at, "verified_at")
        validate_optional_sanitized_text(self.sanitized_error, "sanitized_error")
        if self.observed_remote_post_id is not None and (
            type(self.observed_remote_post_id) is not int
            or self.observed_remote_post_id <= 0
        ):
            raise ValueError("observed_remote_post_id is invalid.")
        if self.observed_status is not None and (
            type(self.observed_status) is not str
            or not self.observed_status.strip()
            or len(self.observed_status) > 64
        ):
            raise ValueError("observed_status is invalid.")

        outcome = self.outcome
        if outcome is WordPressVerificationOutcome.VERIFIED:
            valid = (
                self.lookup_kind is WordPressVerificationLookupKind.REMOTE_ID
                and self.observed_remote_post_id is not None
                and self.observed_status == "draft"
                and self.failure_kind is None
                and self.sanitized_error is None
            )
        elif outcome is WordPressVerificationOutcome.NOT_FOUND:
            valid = (
                self.lookup_kind is WordPressVerificationLookupKind.REMOTE_ID
                and self.observed_remote_post_id is None
                and self.observed_status is None
                and self.failure_kind is None
                and self.sanitized_error is None
            )
        elif outcome is WordPressVerificationOutcome.MISMATCH:
            valid = (
                self.lookup_kind is WordPressVerificationLookupKind.REMOTE_ID
                and self.failure_kind in _MISMATCH_FAILURE_KINDS
                and self.sanitized_error is not None
            )
        elif outcome is WordPressVerificationOutcome.UNKNOWN:
            valid = (
                self.lookup_kind is WordPressVerificationLookupKind.REMOTE_ID
                and self.failure_kind in _REMOTE_ONLY_FAILURE_KINDS
                and self.sanitized_error is not None
            )
        else:
            valid = (
                self.lookup_kind is WordPressVerificationLookupKind.NONE
                and self.observed_remote_post_id is None
                and self.observed_status is None
                and self.failure_kind in _UNRESOLVED_FAILURE_KINDS
                and self.sanitized_error is not None
            )
        if not valid:
            raise ValueError("verification outcome fields are inconsistent.")
