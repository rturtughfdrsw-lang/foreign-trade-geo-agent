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
