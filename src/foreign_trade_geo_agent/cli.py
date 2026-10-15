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
    PlanningValidationCategory,
    RunStatus,
    WordPressAttemptState,
)
from foreign_trade_geo_agent.core.content_draft_review import (
    ContentDraftReviewRequest,
    ContentDraftReviewValidationError,
)
from foreign_trade_geo_agent.core.content_draft import (
    ClaimTypeViolation,
    CompetitorMentionViolation,
    NumericGroundingViolation,
    DraftBlockBudgetViolation,
    ContentDraftValidationCategory,
)
from foreign_trade_geo_agent.core.change_plan import (
    FieldContractViolation,
    GroundingViolation,
    TargetLocatorViolation,
)
from foreign_trade_geo_agent.core.orchestration import EndToEndRunRequest, EndToEndStage
from foreign_trade_geo_agent.core.wordpress_verification import (
    WordPressVerificationRequest,
    WordPressVerificationValidationError,
)
from foreign_trade_geo_agent.reporting.content_draft_review import (
    content_draft_review_payload,
    render_content_draft_review_text,
    render_content_draft_review_markdown,
)
from foreign_trade_geo_agent.reporting.wordpress_verification import (
    render_wordpress_verification_text,
    wordpress_verification_payload,
)
from foreign_trade_geo_agent.runtime import (
    build_delivery_workflow,
    build_planning_workflow,
    build_review_workflow,
    build_verification_workflow,
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
    plan.add_argument("--evidence-requirements", type=Path,
                      help="Analyst-authored obligations for a supported EXPLAIN task; hand off to intake.")
    plan.add_argument("--customer-id")
    from foreign_trade_geo_agent.evidence_cli import DEFAULT_INTAKE_DB, add_evidence_parser
    plan.add_argument("--intake-db", type=Path, default=DEFAULT_INTAKE_DB)
    add_evidence_parser(subparsers, DEFAULT_DB_PATH)

    review = subparsers.add_parser(
        "review",
        help="Read one persisted content draft for human review.",
    )
    review.add_argument("--run-id", required=True)
    review.add_argument("--artifact-id", required=True)
    review.add_argument("--draft-id", required=True)
    review.add_argument("--format", choices=("text", "json", "markdown"), default="text")
    review.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)

    verify = subparsers.add_parser(
        "verify",
        help="Verify one persisted WordPress draft attempt.",
    )
    verify.add_argument("--attempt-id", required=True)
    verify.add_argument("--format", choices=("text", "json"), default="text")
    verify.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)

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
    verification_factory: Callable[..., object] | None = None,
    cwd: Path | None = None,
) -> int:
    args = _parser().parse_args(argv)
    if args.command == "evidence":
        from foreign_trade_geo_agent.evidence_cli import run_evidence
        return run_evidence(args)
    if args.command == "review":
        return _run_review(args, review_factory or build_review_workflow)
    load_runtime_environment(cwd)
    if args.command == "plan":
        return _run_plan(args, planning_factory or build_planning_workflow)
    if args.command == "verify":
        return _run_verify(
            args,
            verification_factory or build_verification_workflow,
        )
    if args.command == "deliver":
        return _run_deliver(args, delivery_factory or build_delivery_workflow)
    return 1


def _run_plan(args: argparse.Namespace, factory: Callable[..., object]) -> int:
    if bool(args.evidence_requirements) != bool(args.customer_id):
        print("Evidence handoff requires --evidence-requirements and --customer-id.", file=sys.stderr)
        return 2
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
    validation_diagnostic = _plan_validation_diagnostic(result, workflow)
    if validation_diagnostic is not None:
        payload["validation_diagnostic"] = validation_diagnostic
    if args.evidence_requirements:
        from foreign_trade_geo_agent.evidence_cli import open_planning_evidence
        plan_id = next((a.artifact_id for a in result.artifacts
                        if a.artifact_type is ArtifactType.CHANGE_PLAN), None)
        try:
            args.requirements = args.evidence_requirements
            payload["evidence_intake"] = open_planning_evidence(args, result.run.run_id, plan_id)
        except Exception:
            payload["evidence_handoff_error"] = "EVIDENCE_HANDOFF_REJECTED"
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 2
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
        renderer = render_content_draft_review_markdown if args.format == "markdown" else render_content_draft_review_text
        print(renderer(view), end="")
    return 0


def _run_verify(args: argparse.Namespace, factory: Callable[..., object]) -> int:
    if not _required_environment(
        "WORDPRESS_USERNAME",
        "WORDPRESS_APPLICATION_PASSWORD",
    ):
        return 2
    try:
        request = WordPressVerificationRequest(attempt_id=args.attempt_id)
    except (WordPressVerificationValidationError, TypeError, ValueError):
        print("Invalid verify request.", file=sys.stderr)
        return 2

    username = os.environ["WORDPRESS_USERNAME"].strip()
    application_password = os.environ["WORDPRESS_APPLICATION_PASSWORD"].strip()
    try:
        workflow = factory(
            args.db,
            username=username,
            application_password=application_password,
        )
        result = asyncio.run(workflow.verify(request))
    except Exception:
        print("Verification failed unexpectedly.", file=sys.stderr)
        return 1

    if args.format == "json":
        print(
            json.dumps(
                wordpress_verification_payload(result),
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(render_wordpress_verification_text(result), end="")
    return 3 if result.manual_action_required else 0


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


def _plan_validation_diagnostic(
    result: object,
    workflow: object,
) -> dict[str, object] | None:
    run = getattr(result, "run", None)
    if getattr(run, "status", None) is not RunStatus.FAILED:
        return None
    stopped_stage = getattr(result, "stopped_stage", None)
    if stopped_stage is EndToEndStage.CONTENT_DRAFT:
        raw_category = getattr(getattr(result, "terminal_report", None), "error", None)
        try:
            category = ContentDraftValidationCategory(raw_category).value
        except (TypeError, ValueError):
            return None
        payload: dict[str, object] = {"category": category}
        diagnostics = getattr(workflow, "run_diagnostics", None)
        claim_type_violation = getattr(diagnostics, "claim_type_violation", None)
        if category == "CLAIM_TYPE_CONTRACT" and isinstance(claim_type_violation, ClaimTypeViolation):
            payload.update({
                "change_ref": claim_type_violation.change_ref,
                "operation_type": claim_type_violation.operation_type.value,
                "draft_item_index": claim_type_violation.draft_item_index,
                "field_path": claim_type_violation.field_path,
                "rule_id": claim_type_violation.rule_id,
                "actual_claim_type": claim_type_violation.actual_claim_type.value,
                "expected_claim_types": tuple(item.value for item in claim_type_violation.expected_claim_types),
                "prior_category": None if claim_type_violation.prior_category is None else claim_type_violation.prior_category.value,
                "has_page_refs": claim_type_violation.has_page_refs,
                "has_source_refs": claim_type_violation.has_source_refs,
                "has_numeric_expression": claim_type_violation.has_numeric_expression,
                "has_first_party_expression": claim_type_violation.has_first_party_expression,
                "has_promotional_term": claim_type_violation.has_promotional_term,
            })
        numeric_violation = getattr(diagnostics, "numeric_grounding_violation", None)
        if category == "NUMERIC_NOT_GROUNDED" and isinstance(numeric_violation, NumericGroundingViolation):
            payload.update({
                "change_ref": numeric_violation.change_ref,
                "operation_type": numeric_violation.operation_type.value,
                "draft_item_index": numeric_violation.draft_item_index,
                "field_path": numeric_violation.field_path,
                "numeric_kind": numeric_violation.numeric_kind,
                "rule_id": numeric_violation.rule_id,
                "attempt": numeric_violation.attempt,
                "bare_number_count": numeric_violation.bare_number_count,
                "evidence_mismatch_count": numeric_violation.evidence_mismatch_count,
                "has_page_refs": numeric_violation.has_page_refs,
                "has_source_refs": numeric_violation.has_source_refs,
                "is_bare_number": numeric_violation.is_bare_number,
                "evidence_match_failed": numeric_violation.evidence_match_failed,
                "numeric_occurrence_index": numeric_violation.numeric_occurrence_index,
                "numeric_literal_count": numeric_violation.numeric_literal_count,
                "grounded_count": numeric_violation.grounded_count,
                "ungrounded_count": numeric_violation.ungrounded_count,
                "cited_ref_ids": numeric_violation.cited_ref_ids,
                "grounding_mode": numeric_violation.grounding_mode,
                "source_namespace": numeric_violation.source_namespace,
                "table_row_index": numeric_violation.table_row_index,
                "table_column_index": numeric_violation.table_column_index,
            })
        budget_violation = getattr(diagnostics, "block_budget_violation", None)
        if category == "BLOCK_BUDGET" and isinstance(budget_violation, DraftBlockBudgetViolation):
            payload.update({
                "change_ref": budget_violation.change_ref,
                "operation_type": budget_violation.operation_type.value,
                "field_path": budget_violation.field_path,
                "rule_id": budget_violation.rule_id.value,
                "expected_min": budget_violation.expected_min,
                "expected_max": budget_violation.expected_max,
                "actual_count": budget_violation.actual_count,
                "paragraph_count": budget_violation.paragraph_count,
                "bullet_list_count": budget_violation.bullet_list_count,
            })
        violation = getattr(diagnostics, "competitor_mention_violation", None)
        if category == "COMPETITOR_MENTION" and isinstance(violation, CompetitorMentionViolation):
            payload.update({
                "change_ref": violation.change_ref,
                "operation_type": violation.operation_type.value,
                "draft_item_index": violation.draft_item_index,
                "section_index": violation.section_index,
                "field_path": violation.field_path,
                "match_kind": violation.match_kind,
                "competitor_index": violation.competitor_index,
                "mention_count": violation.mention_count,
                "source_origin": violation.source_origin,
            })
        return payload
    if stopped_stage is not EndToEndStage.CHANGE_PLAN:
        return None
    raw_category = getattr(run, "final_validation_category", None)
    raw_category = getattr(raw_category, "value", raw_category)
    try:
        category = PlanningValidationCategory(raw_category).value
    except (TypeError, ValueError):
        return None
    payload: dict[str, object] = {"category": category}
    diagnostics = getattr(workflow, "run_diagnostics", None)
    if category == "CONTENT_NOT_GROUNDED":
        violation = getattr(diagnostics, "grounding_violation", None)
        if isinstance(violation, GroundingViolation):
            payload.update(
                {
                    "opportunity": violation.opportunity_ref,
                    "slot": violation.slot,
                    "operation_type": violation.operation_type.value,
                    "field_path": violation.field_path,
                    "grounding_mode": violation.grounding_mode.value,
                    "cited_ref_ids": list(violation.cited_ref_ids),
                    "normalized_length": violation.normalized_length,
                }
            )
            for name in (
                "contiguous_match",
                "token_coverage_pass",
                "normalized_token_count",
                "matched_token_count",
            ):
                value = getattr(violation, name)
                if value is not None:
                    payload[name] = value
    if category == "FIELD_CONTRACT":
        violation = getattr(diagnostics, "field_contract_violation", None)
        if isinstance(violation, FieldContractViolation):
            payload.update(
                {
                    "rule_id": violation.rule_id.value,
                    "field_path": violation.field_path,
                    "repair_class": violation.repair_class.value,
                    "expected": dict(violation.expected),
                    "actual": dict(violation.actual),
                }
            )
    if category == "TARGET_LOCATOR_INVALID":
        violation = getattr(diagnostics, "target_locator_violation", None)
        if isinstance(violation, TargetLocatorViolation):
            payload["field_path"] = violation.field_path
            if violation.repair_rule is not None:
                payload["locator_rule"] = violation.repair_rule.value
    return payload


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
