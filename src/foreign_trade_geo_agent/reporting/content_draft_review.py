"""Deterministic human and machine rendering of one read-only review view."""

from __future__ import annotations

from dataclasses import asdict
import re

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
    if view.customer_evidence is not None:
        payload["customer_evidence"]["reviewed_at"] = view.customer_evidence.reviewed_at.isoformat()
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
            references = tuple(claim.page_refs) + tuple(claim.source_refs) + tuple(claim.customer_refs)
            support = claim.support_kind or "n/a"
            lines.append(
                f"- {claim.claim_id} [{claim.claim_type} / {support}] "
                + (", ".join(references) if references else "no evidence references")
                + f" :: {claim.text}"
            )
    else:
        lines.append("- (none)")

    lines += ["", "--- Quality preflight (human review still required) ---"]
    lines += _bullet_lines(view.draft.quality_findings or ('No obvious structural gaps; semantic quality remains unverified.',))
    lines += ["", "--- Draft limitations ---"]
    lines += _bullet_lines(view.limitations)
    lines += [
        "",
        "--- Next step (not executed) ---",
        delivery_handoff(view),
    ]
    return "\n".join(lines) + "\n"


def render_content_draft_review_markdown(view: ContentDraftReviewView) -> str:
    """Whole persisted draft plus per-claim provenance, without an approval action.

    Body section boundaries come from finalization, never guessed from block
    counts at export time. Historical bodies keep their legacy outline display.
    """
    draft = view.draft
    lines = ["# " + (draft.heading or "Content draft"), "",
        "> Human review required. Approval record: NOT RECORDED. Review action: READ ONLY.", "",
        f"Run: {view.planning_run_id} · Artifact: {view.content_draft_artifact_id} · Draft: {draft.draft_id}", "",
        "## Article candidate", ""]
    body = draft.body_text
    if draft.heading and body.startswith(draft.heading + "\n\n"):
        body = body[len(draft.heading) + 2:]
    # One pass avoids attaching markers inside previously inserted markers or
    # inside a longer claim containing another claim's text.
    markers = {c.text: f" [{c.claim_id}" +
        (": " + ", ".join((*c.page_refs, *c.source_refs, *c.customer_refs)) if c.page_refs or c.source_refs or c.customer_refs else "") + "]"
        for c in draft.claims}
    if markers:
        body = re.sub("|".join(re.escape(t) for t in sorted(markers, key=len, reverse=True)),
            lambda match: match.group(0) + markers[match.group(0)], body)
    lines.extend((body, "", "## Claim references and review status", ""))
    for claim in draft.claims:
        refs = ", ".join((*claim.page_refs, *claim.source_refs, *claim.customer_refs)) or "no factual references"
        lines.extend((f"- **{claim.claim_id}** [{claim.claim_type}; {claim.support_kind or 'n/a'}; "
                      f"{refs}] — UNREVIEWED: {claim.text}", ""))
    lines.extend(("## Sources", "", "P records observed page material; S is unverified external context. "
                  "Audit observations are not factual citations.", ""))
    for page in view.page_evidence:
        lines.append(f"- {page.evidence_id}: {page.title or '(untitled)'} — {page.url}")
    for source in view.source_evidence:
        lines.append(f"- {source.source_id}: {source.title} — {source.url} (unverified context)")
    if view.customer_evidence is not None:
        bundle = view.customer_evidence
        lines.extend(("", "## Customer evidence (E) — historical TEST-only binding", "",
            "Exact quotations and hashes check preservation only; they do not prove semantic truth. "
            "This simulated review is not customer approval, human signoff or execution permission.", "",
            f"Project/customer/task: {bundle.project_id} / {bundle.customer_id} / {bundle.task_id}",
            f"Task/Plan/evidence/revision: {bundle.task_version}/{bundle.plan_version}/{bundle.evidence_version}/{bundle.snapshot_revision}",
            f"Snapshot: {bundle.snapshot_sha256}",
            f"Review: {bundle.review_status}; reviewer={bundle.reviewer_id}; at={bundle.reviewed_at.isoformat()}", ""))
        for source in bundle.sources:
            claim_ids = ", ".join(c.claim_id for c in draft.claims if any(r.split('.')[0] == source.evidence_id for r in c.customer_refs))
            lines.extend((f"- **{source.evidence_id} → {claim_ids}**; version={source.evidence_version}; "
                f"requirements={', '.join(source.requirement_ids)}; locator={source.source_locator}; "
                f"span=[{source.span_start}:{source.span_end}]; sha256={source.content_sha256}", "",
                "> " + source.quote.replace("\n", "\n> "), ""))
            for fact in source.facts:
                ids = ', '.join(c.claim_id for c in draft.claims if fact.fact_ref in c.customer_refs)
                lines.extend((f'- {fact.fact_ref} → {ids}; span=[{fact.start}:{fact.end}]', '', '> ' + fact.quote, ''))
        if bundle.interpretations:
            lines.extend(('## Reviewed interpretation boundaries', '',
                'Interpretations are reviewed separately from direct quotations. New inference requires a new review.', ''))
            lines.extend(f'- {i.text} Premises: {", ".join(i.fact_refs)}' for i in bundle.interpretations)
    lines.extend(('', '## Quality preflight', '',
        *_bullet_lines(view.draft.quality_findings or ('No obvious structural gaps; human semantic review required.',)), ''))
    lines.extend(("", "## Limitations", "", *_bullet_lines(view.limitations), ""))
    return "\n".join(lines)


def render_local_draft_review_markdown(view, revision, *, validation_state, local_status, revalidation_records=()):
    """Export exactly one local body; historical citations never annotate edited text."""
    original = render_content_draft_review_markdown(view)
    provenance = original.split("## Claim references and review status", 1)[1]
    result = "\n".join((
        "# Local article revision", "",
        "> SYNTHETIC / TEST ONLY. Local feedback only; human_signoff=false; production_authorized=false.", "",
        f"Run: {view.planning_run_id} · Artifact: {view.content_draft_artifact_id} · Draft: {view.draft.draft_id}",
        f"Version: {revision.version} · Parent: {revision.parent_version} · Saved: {revision.saved_at.isoformat()}",
        f"Local status: {local_status} · Validation: {validation_state}",
        f"Origin SHA256: {revision.origin_sha256} · Body SHA256: {revision.body_sha256}",
        f"Frozen evidence: {revision.frozen_evidence_sha256}",
        f"Evidence observed at save: {revision.observed_evidence_sha256}", "",
        "## Local feedback", "", revision.note or "(none)", "",
        "## Selected article body", "", revision.body_text, "",
        "## Historical original claim references and review status", "",
        "> These references map ONLY to the original native body. See the version-specific local revalidation records below when present. "
        "Local completion does not grant production approval.", "", provenance,
    ))
    for record in revalidation_records:
        report = record.report
        result += '\n\n## Version-specific local revalidation\n\n' + '\n'.join((
            f'Version: {report.version}; Body: {report.body_sha256}; Evidence: {report.evidence_sha256}',
            f'Rule: {report.rule_version}; Native technical validation: {report.native_state}',
            f'Current validation state: {validation_state}; historical eligible: {report.eligible}',
            f'Local operator (unauthenticated): {record.saved_at.isoformat()}; decision: {record.decision}',
            'trusted_human_signoff=false; production_authorized=false; semantic_truth_proven=false',
            'Local review note: ' + record.note, *report.reasons,
            *(f'- {i.claim_id}: {i.state}; refs={", ".join(i.refs) or "none"}; {i.reason}\n  Revision text: {i.revision_text}\n  '
              + '\n  '.join(i.details) for i in report.items)))
    return result
def render_candidate_review_markdown(check, revision):
    """Export all candidate text, premises, failures and local decisions."""
    from foreign_trade_geo_agent.core.draft_candidate_review import effective_decisions
    decisions = effective_decisions(check, revision)
    lines = ['# Native model interpretation candidate', '',
        'TEST-only local review; no authenticated human signoff or production permission.', '',
        f'State: {check.state}', f'Binding: {check.binding_sha256}',
        f'Exact output SHA256: {check.raw_sha256}', '']
    lines.extend(check.errors)
    for claim in check.claims:
        lines.extend(('', f'## {claim.claim_id} · {claim.claim_type}', '', claim.text, ''))
        if claim.proposal:
            p = claim.proposal
            lines.extend((f'Question: {p.procurement_question}', f'Unverified reasoning: {p.reasoning}',
                f'Assumptions needing review: {p.assumptions}', f'Limitation: {p.limitation}',
                f'Procurement action: {p.procurement_action}',
                'Review: ' + (decisions[claim.claim_id].decision if claim.claim_id in decisions else 'PENDING_REVIEW')))
        if claim.deterministic_error:
            lines.append('Deterministic failure: ' + claim.deterministic_error)
        lines.extend('> ' + detail for detail in claim.evidence_details)
    lines.extend(('', '## Full frozen source documents and applicability context', ''))
    lines.extend('```text\n' + document + '\n```' for document in check.source_documents)
    return '\n'.join(lines) + '\n'
