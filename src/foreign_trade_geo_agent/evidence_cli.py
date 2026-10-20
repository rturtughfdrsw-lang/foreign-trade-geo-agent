"""Local operator interface to existing intake; no credentials or network ports."""
import asyncio
from datetime import UTC, datetime
import json
from pathlib import Path
import sys

from foreign_trade_geo_agent.core.evidence_intake import (
    CustomerContext, MAX_SNAPSHOT_BYTES, require, snapshot_digest,
)
from foreign_trade_geo_agent.reporting.evidence_intake import (
    customer_request_json, planning_review_json, render_customer_request,
)
from foreign_trade_geo_agent.storage.evidence_intake import (
    decode_customer_submission, decode_evidence_requirements,
)
from foreign_trade_geo_agent.runtime import build_planning_evidence_workflow

DEFAULT_INTAKE_DB = Path(".data/evidence-intake.sqlite3")


def add_evidence_parser(subparsers, default_db):
    evidence = subparsers.add_parser("evidence", help="Local customer evidence intake; never authorizes Draft.")
    actions = evidence.add_subparsers(dest="evidence_action", required=True)
    for name in ("open", "show", "submit", "recheck", "review"):
        command = actions.add_parser(name)
        command.add_argument("--run-id", required=True)
        command.add_argument("--plan-id", required=True, help="Original change_plan artifact ID; intake task ID.")
        command.add_argument("--db", type=Path, default=default_db)
        command.add_argument("--intake-db", type=Path, default=DEFAULT_INTAKE_DB)
        if name == "open":
            command.add_argument("--requirements", type=Path, required=True)
            command.add_argument("--customer-id", required=True)
        if name == "submit":
            command.add_argument("--file", type=Path, required=True)
            command.add_argument("--customer-id", required=True,
                                 help="Local operator declaration, not customer authentication.")
        if name == "recheck":
            command.add_argument("--expected-sha256", required=True)
        if name == "show":
            command.add_argument("--format", choices=("text", "json"), default="json")


def read_local_json(path):
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_SNAPSHOT_BYTES + 1)
    require(len(raw) <= MAX_SNAPSHOT_BYTES)
    return raw.decode("utf-8", errors="strict")


def _application(args, run_id, plan_id, *, create=False):
    return build_planning_evidence_workflow(args.db, args.intake_db,
        run_id=run_id, plan_id=plan_id, create=create)


def open_planning_evidence(args, run_id, plan_id):
    requirements = decode_evidence_requirements(read_local_json(args.requirements))
    store, app, _ = _application(args, run_id, plan_id, create=True)
    app.register(run_id, plan_id, customer_id=args.customer_id, requirements=requirements)
    return _status(app, store, run_id, plan_id, datetime.now(UTC))


def _status(app, store, run_id, plan_id, now):
    origin = app.bound_origin(run_id, plan_id, store.get_revision(run_id, plan_id, 1))
    request = app.intake.customer_request(run_id, plan_id, now=now)
    current = store.latest(run_id, plan_id)
    require(snapshot_digest(current) == request.snapshot_sha256)
    needs_customer = any(g.reason_code not in {"HUMAN_SEMANTIC_REVIEW_REQUIRED", "UNREVIEWED"}
                         for g in request.gaps)
    if not current.plan_bound:
        state = "RECHECK_REQUIRED"
    elif needs_customer:
        state = "WAITING_FOR_EVIDENCE"
    else:
        state = "WAITING_FOR_HUMAN_REVIEW"
    return {
        "state": state, "origin_run_id": run_id, "origin_artifacts": origin,
        "intake_project_id": run_id, "intake_task_id": plan_id,
        "submission_status": "SUBMITTED" if current.submission_ids else "NOT_SUBMITTED",
        "evidence_candidate_status": "AVAILABLE_FOR_HUMAN_REVIEW" if current.plan_bound and not needs_customer
                                     else "NOT_READY",
        "semantic_review_status": "HUMAN_SEMANTIC_REVIEW_REQUIRED",
        "draft_authorized": False, "execution_status": "AUTHORIZATION_REQUIRED",
        "plan_bound": current.plan_bound,
        "customer_action_required": needs_customer,
        "request": json.loads(customer_request_json(request)),
        "materials": [{"evidence_id": e.supplement.evidence_id,
            "source_label": e.supplement.source_label, "source_locator": e.supplement.source_locator,
            "declared_source_owner": e.supplement.declared_source_owner,
            "file_sha256": e.supplement.file_sha256, "evidence_version": e.evidence_version,
            "submission_id": e.submission_id, "actor_id": e.actor_id,
            "recorded_at": e.recorded_at.isoformat(), "supersedes": e.supplement.supersedes}
            for e in current.evidence],
    }


def run_evidence(args):
    try:
        if args.evidence_action == "open":
            payload = open_planning_evidence(args, args.run_id, args.plan_id)
        else:
            store, app, planner = _application(args, args.run_id, args.plan_id)
            app.bound_origin(args.run_id, args.plan_id, store.get_revision(args.run_id, args.plan_id, 1))
            now = datetime.now(UTC)
            if args.evidence_action == "submit":
                submission = decode_customer_submission(read_local_json(args.file))
                app.intake.submit(args.run_id, args.plan_id, submission,
                    customer=CustomerContext(args.customer_id, "LOCAL-OPERATOR", now))
                # Submission remains durable if later native revalidation fails.
                # Recheck is an explicit recoverable step, never implicit approval.
            if args.evidence_action == "recheck":
                asyncio.run(app.recheck(args.run_id, args.plan_id,
                    expected_sha256=args.expected_sha256,
                    current=store.latest(args.run_id, args.plan_id),
                    planner=planner, now=now))
            if args.evidence_action == "review":
                candidate = app.intake.review_candidate(args.run_id, args.plan_id, now=now)
                payload = json.loads(planning_review_json(candidate))
            else:
                payload = _status(app, store, args.run_id, args.plan_id, now)
            if args.evidence_action == "show" and args.format == "text":
                print(f"{payload['state']} | Draft: AUTHORIZATION_REQUIRED")
                request = app.intake.customer_request(args.run_id, args.plan_id, now=now)
                print(render_customer_request(request), end="")
                return 0
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    except Exception:
        print("Evidence action rejected. Check IDs, current digest, profile and input schema. "
              "A saved submission can be resumed with show/recheck; no Draft was authorized.", file=sys.stderr)
        return 2
