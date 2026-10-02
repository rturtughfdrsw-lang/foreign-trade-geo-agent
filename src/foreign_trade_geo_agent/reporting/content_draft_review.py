"""Deterministic human and machine rendering of one read-only review view."""

from __future__ import annotations

from dataclasses import asdict

from foreign_trade_geo_agent.core.content_draft_review import (
    ContentDraftReviewView,
)


APPROVAL_RECORD_STATE = "NOT RECORDED"
REVIEW_ACTION = "READ ONLY"


def delivery_handoff(view: ContentDraftReviewView) -> str:
    """Return the exact next command without executing anything."""

    return (
        f"deliver --run-id {view.planning_run_id} "
        f"--artifact-id {view.content_draft_artifact_id} "
        f"--draft-id {view.draft.draft_id} "
        "--site <your WordPress site>"
    )


def content_draft_review_payload(
    view: ContentDraftReviewView,
) -> dict[str, object]:
    """Return the same core view as a JSON-ready mapping."""

    payload = dict(asdict(view))
    payload["run_id"] = view.planning_run_id
    payload["artifact_id"] = view.content_draft_artifact_id
    payload["approval_record"] = APPROVAL_RECORD_STATE
    payload["review_action"] = REVIEW_ACTION
    payload["delivery_handoff"] = delivery_handoff(view)
    return payload


def _bullet_lines(items: tuple[str, ...]) -> list[str]:
    return [f"- {item}" for item in items] or ["- (none)"]


def render_content_draft_review_text(view: ContentDraftReviewView) -> str:
    """Render one review view as a bounded, human-readable plain-text page."""

    draft = view.draft
    lines: list[str] = [
        "Content draft review (read-only inspection)",
        "",
        f"Run: {view.planning_run_id}",
        f"Artifact: {view.content_draft_artifact_id} (payload v{view.payload_version})",
        f"Draft: {draft.draft_id} ({draft.draft_type})",
        f"Heading: {draft.heading if draft.heading else '(none)'}",
        f"Target: {draft.target_kind} / locator {draft.locator_kind}"
        + (f" / {draft.locator_heading}" if draft.locator_heading else ""),
        f"Approval record: {APPROVAL_RECORD_STATE}",
        f"Review action: {REVIEW_ACTION}",
        "Human review required: yes",
        "",
        "Review only inspects persisted artifacts. It is not approval, it changes",
        "no approval state, and `deliver` remains a separate explicit action.",
    ]
    if draft.requires_title_override:
        lines.append("Title override required: deliver needs --title for this draft.")

    lines += ["", "--- Draft body ---", "", draft.body_text]

    change = view.change
    lines += [
        "",
        f"--- Change context ({change.change_id}) ---",
        f"Operation: {change.operation_type}",
        f"Source action: {change.source_action_code}",
        f"Target kind: {change.target_kind}",
        f"Locator: {change.locator_kind}"
        + (f" / {change.locator_heading}" if change.locator_heading else ""),
    ]
    if change.target_page_ref:
        lines.append(f"Target page: {change.target_page_ref}")
    if change.proposed_heading:
        lines.append(f"Proposed heading: {change.proposed_heading}")
    if change.section_purpose:
        lines.append(f"Section purpose: {change.section_purpose}")
    lines.append("Content points:")
    lines += _bullet_lines(
        tuple(f"[{intent}] {subject}" for intent, subject in change.content_points)
    )
    if change.briefs:
        lines.append("Briefs:")
        lines += _bullet_lines(change.briefs)

    opportunity = view.opportunity
    lines += [
        "",
        f"--- Opportunity ({opportunity.recommendation_id}) ---",
        f"Type: {opportunity.opportunity_type}",
        f"Priority: {opportunity.priority}",
        f"Title: {opportunity.title}",
        f"Rationale: {opportunity.rationale}",
        "Actions:",
    ]
    lines += _bullet_lines(opportunity.actions)

    lines += [
        "",
        "--- Evidence provenance ---",
        "Audit observations (A#) are audit observations only and are never a",
        "source of draft facts:",
    ]
    lines += _bullet_lines(
        tuple(
            f"{item.evidence_id} [{item.category}] {item.check_key} "
            f"outcome={item.outcome} observed={item.observed_value}"
            + (f" note={item.note}" if item.note else "")
            for item in view.audit_evidence
        )
    )
    lines += [
        "Observed page evidence (P#) records observed content only; a missing",
        "observation never supports an absence claim:",
    ]
    page_lines: list[str] = []
    for page in view.page_evidence:
        title = page.title or "(untitled)"
        page_lines.append(f"- {page.evidence_id} {title} - {page.url}")
        if page.excerpt:
            page_lines.append(f"  excerpt: {page.excerpt}")
        page_lines.append(
            f"  truncated: {'yes' if page.content_truncated else 'no'}"
        )
    lines += page_lines or ["- (none)"]
    lines += [
        "External research context (S#) is unverified external material, not an",
        "authoritative citation:",
    ]
    source_lines: list[str] = []
    for source in view.source_evidence:
        source_lines.append(f"- {source.source_id} {source.title} - {source.url}")
        if source.excerpt:
            source_lines.append(f"  excerpt: {source.excerpt}")
        source_lines.append(
            f"  truncated: {'yes' if source.content_truncated else 'no'}"
        )
    lines += source_lines or ["- (none)"]

    lines += ["", "--- Claim provenance ---"]
    if draft.claims:
        for claim in draft.claims:
            references = tuple(claim.page_refs) + tuple(claim.source_refs)
            support = claim.support_kind or "n/a"
            lines.append(
                f"- {claim.claim_id} [{claim.claim_type} / {support}] "
                + (", ".join(references) if references else "no evidence references")
                + f" :: {claim.text}"
            )
    else:
        lines.append("- (none)")

    lines += ["", "--- Draft limitations ---"]
    lines += _bullet_lines(view.limitations)
    lines += [
        "",
        "--- Next step (not executed) ---",
        delivery_handoff(view),
    ]
    return "\n".join(lines) + "\n"
