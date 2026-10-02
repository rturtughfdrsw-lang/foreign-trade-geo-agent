"""Command-line interface for planning and approved WordPress draft delivery."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Callable, Sequence
import json
import os
from pathlib import Path
import sys

from foreign_trade_geo_agent.core.approved_wordpress_delivery import (
    ApprovedWordPressDraftDeliveryRequest,
    ApprovedWordPressDraftDeliveryValidationError,
)
from foreign_trade_geo_agent.core.history import (
    ArtifactType,
    RunStatus,
    WordPressAttemptState,
)
from foreign_trade_geo_agent.core.content_draft_review import (
    ContentDraftReviewRequest,
    ContentDraftReviewValidationError,
)
from foreign_trade_geo_agent.core.orchestration import EndToEndRunRequest
from foreign_trade_geo_agent.reporting.content_draft_review import (
    content_draft_review_payload,
    render_content_draft_review_text,
)
from foreign_trade_geo_agent.runtime import (
    build_delivery_workflow,
    build_planning_workflow,
    build_review_workflow,
    load_runtime_environment,
)
from foreign_trade_geo_agent.workflows.wordpress_delivery import (
    WordPressDeliveryStatus,
)


DEFAULT_DB_PATH = Path(".data/history.sqlite3")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="foreign-trade-geo-agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan = subparsers.add_parser("plan", help="Run the fixed planning workflow.")
    plan.add_argument("--site", required=True)
    plan.add_argument("--question", required=True)
    plan.add_argument("--language", default="en")
    plan.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)

    review = subparsers.add_parser(
        "review",
        help="Read one persisted content draft for human review.",
    )
    review.add_argument("--run-id", required=True)
    review.add_argument("--artifact-id", required=True)
    review.add_argument("--draft-id", required=True)
    review.add_argument("--format", choices=("text", "json"), default="text")
    review.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)

    deliver = subparsers.add_parser(
        "deliver",
        help="Create one explicitly approved WordPress draft.",
    )
    deliver.add_argument("--run-id", required=True)
    deliver.add_argument("--artifact-id", required=True)
    deliver.add_argument("--draft-id", required=True)
    deliver.add_argument("--site", required=True)
    deliver.add_argument("--title")
    deliver.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    planning_factory: Callable[..., object] | None = None,
    delivery_factory: Callable[..., object] | None = None,
    review_factory: Callable[..., object] | None = None,
    cwd: Path | None = None,
) -> int:
    args = _parser().parse_args(argv)
    load_runtime_environment(cwd)
    if args.command == "plan":
        return _run_plan(args, planning_factory or build_planning_workflow)
    if args.command == "review":
        return _run_review(args, review_factory or build_review_workflow)
    if args.command == "deliver":
        return _run_deliver(args, delivery_factory or build_delivery_workflow)
    return 1


def _run_plan(args: argparse.Namespace, factory: Callable[..., object]) -> int:
    if not _required_environment("DEEPSEEK_API_KEY", "TAVILY_API_KEY"):
        return 2
    try:
        request = EndToEndRunRequest(
            site_url=args.site,
            research_question=args.question,
            target_language=args.language,
        )
    except (TypeError, ValueError):
        print("Invalid plan request.", file=sys.stderr)
        return 2

    try:
        workflow = factory(args.db)
        result = asyncio.run(workflow.run(request))
    except Exception:
        print("Planning failed unexpectedly.", file=sys.stderr)
        return 1

    payload = _plan_payload(result)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if result.run.status is RunStatus.SUCCEEDED else 1


def _run_deliver(args: argparse.Namespace, factory: Callable[..., object]) -> int:
    if not _required_environment(
        "WORDPRESS_USERNAME",
        "WORDPRESS_APPLICATION_PASSWORD",
    ):
        return 2
    try:
        request = ApprovedWordPressDraftDeliveryRequest(
            planning_run_id=args.run_id,
            content_draft_artifact_id=args.artifact_id,
            draft_id=args.draft_id,
            target_site_url=args.site,
            title_override=args.title,
        )
    except (ApprovedWordPressDraftDeliveryValidationError, TypeError, ValueError):
        print("Invalid delivery request.", file=sys.stderr)
        return 2

    username = os.environ["WORDPRESS_USERNAME"].strip()
    application_password = os.environ["WORDPRESS_APPLICATION_PASSWORD"].strip()
    try:
        workflow = factory(
            args.db,
            target_site_url=args.site,
            username=username,
            application_password=application_password,
        )
        result = asyncio.run(workflow.deliver(request))
    except Exception:
        print("Delivery failed unexpectedly.", file=sys.stderr)
        return 1

    payload = _delivery_payload(result)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return _delivery_exit_code(
        result.delivery_result.status,
        result.attempt.outcome,
    )


def _run_review(args: argparse.Namespace, factory: Callable[..., object]) -> int:
    try:
        request = ContentDraftReviewRequest(
            planning_run_id=args.run_id,
            content_draft_artifact_id=args.artifact_id,
            draft_id=args.draft_id,
        )
    except (ContentDraftReviewValidationError, TypeError, ValueError):
        print("Invalid review request.", file=sys.stderr)
        return 2

    try:
        workflow = factory(args.db)
        view = workflow.review(request)
    except Exception:
        print("Review failed unexpectedly.", file=sys.stderr)
        return 1

    if args.format == "json":
        print(
            json.dumps(
                content_draft_review_payload(view),
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(render_content_draft_review_text(view), end="")
    return 0


def _required_environment(*names: str) -> bool:
    for name in names:
        if not os.environ.get(name, "").strip():
            print(
                f"Missing required environment variable: {name}",
                file=sys.stderr,
            )
            return False
    return True


def _plan_payload(result: object) -> dict[str, object]:
    artifacts = [_artifact_payload(item) for item in result.artifacts]
    content_draft_id = next(
        (
            item.artifact_id
            for item in result.artifacts
            if item.artifact_type is ArtifactType.CONTENT_DRAFT
        ),
        None,
    )
    payload: dict[str, object] = {
        "run_id": result.run.run_id,
        "status": result.run.status.value,
        "site_key": result.run.site_key,
        "artifacts": artifacts,
        "content_draft_artifact_id": content_draft_id,
        "requires_human_review": result.requires_human_review,
    }
    if result.run.status is RunStatus.SUCCEEDED:
        drafts = getattr(result.terminal_report, "drafts", ())
        payload["drafts"] = [
            {
                "draft_id": draft.draft_id,
                "type": draft.draft_type.value,
                "title": _safe_label(draft.heading),
            }
            for draft in drafts
        ]
    else:
        payload["stopped_stage"] = (
            None if result.stopped_stage is None else result.stopped_stage.value
        )
        payload["failure_kind"] = result.run.failure_kind
    return payload


def _artifact_payload(artifact: object) -> dict[str, object]:
    return {
        "artifact_id": artifact.artifact_id,
        "artifact_type": artifact.artifact_type.value,
        "payload_version": artifact.payload_version,
    }


def _safe_label(value: object, *, max_chars: int = 160) -> str | None:
    if type(value) is not str:
        return None
    cleaned = " ".join(
        "".join(
            character
            for character in value
            if character.isprintable() or character.isspace()
        ).split()
    )
    if not cleaned:
        return None
    return cleaned if len(cleaned) <= max_chars else cleaned[: max_chars - 3] + "..."


def _delivery_payload(result: object) -> dict[str, object]:
    attempt = result.attempt
    payload: dict[str, object] = {
        "selected_draft_id": result.selected_draft_id,
        "delivery_status": result.delivery_result.status.value,
        "attempt_id": attempt.attempt_id,
        "attempt_outcome": attempt.outcome.value,
        "remote_post_id": attempt.remote_post_id,
        "remote_link": attempt.remote_link,
        "reconciliation_required": result.reconciliation_required,
    }
    if result.reconciliation_required:
        payload["operator_action"] = "manual reconciliation required"
    return payload


def _delivery_exit_code(
    status: WordPressDeliveryStatus,
    attempt_outcome: WordPressAttemptState,
) -> int:
    if status is WordPressDeliveryStatus.SUCCESS:
        return 0
    if status is WordPressDeliveryStatus.FAILED_DEFINITELY:
        return 1
    if (
        status is WordPressDeliveryStatus.BLOCKED
        and attempt_outcome is WordPressAttemptState.SUCCESS
    ):
        return 0
    return 3
