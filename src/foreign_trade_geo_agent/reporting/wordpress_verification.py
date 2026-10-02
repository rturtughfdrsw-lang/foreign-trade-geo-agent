"""Deterministic rendering of one WordPress draft verification result."""

from __future__ import annotations

from foreign_trade_geo_agent.core.wordpress_verification import (
    WordPressDraftVerificationResult,
)


REMOTE_MODE = "read_only"
LOCAL_HISTORY_MODE = "append_only"
NO_RETRY_WARNING = "Do not retry create while remote state is uncertain."
MODE_STATEMENT = (
    "Remote verification is read-only; local verification history "
    "is append-only."
)


def wordpress_verification_payload(
    result: WordPressDraftVerificationResult,
) -> dict[str, object]:
    """Return one JSON-ready view with separate create and verification states."""

    attempt = result.attempt
    verification = result.verification
    return {
        "attempt_id": attempt.attempt_id,
        "run_id": attempt.run_id,
        "content_draft_artifact_id": attempt.content_draft_artifact_id,
        "draft_item_id": attempt.draft_item_id,
        "target_site_key": attempt.target_site_key,
        "create_outcome": attempt.outcome.value,
        "remote_post_id": attempt.remote_post_id,
        "remote_link": attempt.remote_link,
        "verification_outcome": (
            None if verification is None else verification.outcome.value
        ),
        "not_applicable": result.not_applicable,
        "lookup_kind": (
            None if verification is None else verification.lookup_kind.value
        ),
        "failure_kind": (
            None
            if verification is None or verification.failure_kind is None
            else verification.failure_kind.value
        ),
        "observed_remote_post_id": (
            None if verification is None else verification.observed_remote_post_id
        ),
        "observed_status": (
            None if verification is None else verification.observed_status
        ),
        "sanitized_error": (
            None if verification is None else verification.sanitized_error
        ),
        "verified_at": (
            None if verification is None else verification.verified_at.isoformat()
        ),
        "manual_action_required": result.manual_action_required,
        "remote_mode": REMOTE_MODE,
        "local_history_mode": LOCAL_HISTORY_MODE,
        "mode_statement": MODE_STATEMENT,
        "no_retry_warning": (
            NO_RETRY_WARNING if result.manual_action_required else None
        ),
    }


def render_wordpress_verification_text(
    result: WordPressDraftVerificationResult,
) -> str:
    """Render one verification as parseable plain text with both dimensions."""

    attempt = result.attempt
    verification = result.verification
    lines = [
        "WordPress draft verification",
        "",
        f"Attempt: {attempt.attempt_id}",
        f"Run: {attempt.run_id}",
        f"Draft: {attempt.draft_item_id}",
        f"Target site: {attempt.target_site_key}",
        f"Create outcome: {attempt.outcome.value.upper()}",
        "Remote post ID: "
        + ("(none)" if attempt.remote_post_id is None else str(attempt.remote_post_id)),
    ]
    if verification is None:
        lines += [
            "Verification: NOT APPLICABLE",
            "Manual action required: no",
            "",
            "Verification not applicable: the create attempt failed definitely "
            "and no remote object is expected.",
        ]
        return "\n".join(lines) + "\n"

    lines += [
        f"Verification outcome: {verification.outcome.value.upper()}",
        f"Lookup kind: {verification.lookup_kind.value}",
        "Observed status: "
        + (
            "(none)"
            if verification.observed_status is None
            else verification.observed_status
        ),
        "Failure kind: "
        + (
            "(none)"
            if verification.failure_kind is None
            else verification.failure_kind.value
        ),
        f"Verified at: {verification.verified_at.isoformat()}",
        "Manual action required: "
        + ("yes" if result.manual_action_required else "no"),
    ]
    if verification.sanitized_error:
        lines.append(f"Detail: {verification.sanitized_error}")
    lines += ["", MODE_STATEMENT]
    if result.manual_action_required:
        lines += ["", NO_RETRY_WARNING]
    return "\n".join(lines) + "\n"
