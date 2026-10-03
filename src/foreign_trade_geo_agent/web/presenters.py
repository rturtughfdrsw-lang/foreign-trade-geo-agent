"""Bounded presentation models for the local Demo UI."""

from __future__ import annotations

from dataclasses import dataclass
import unicodedata
from urllib.parse import urlsplit

from foreign_trade_geo_agent.core.audit import SiteAuditResult
from foreign_trade_geo_agent.core.change_plan import ChangePlanReport
from foreign_trade_geo_agent.core.content_draft_review import ContentDraftReviewView
from foreign_trade_geo_agent.core.content_opportunity import ContentOpportunityReport
from foreign_trade_geo_agent.core.site_content import SiteContentPacket


_MAX_EXCERPT_CHARS = 240
_NAVIGATION_STEPS = (
    ("start", "Start"),
    ("progress", "Analysis Progress"),
    ("results", "Audit / Results"),
    ("changes", "Change Plan"),
    ("draft", "Draft Review"),
)


@dataclass(frozen=True, slots=True)
class DemoProgressStageView:
    key: str
    label: str
    state: str


@dataclass(frozen=True, slots=True)
class DemoProgressView:
    location: str
    run_id: str | None
    stages: tuple[DemoProgressStageView, ...]
    terminal: bool
    polling: bool
    interrupted: bool
    message: str | None


@dataclass(frozen=True, slots=True)
class DemoStartResult:
    job_id: str


@dataclass(frozen=True, slots=True)
class NavigationItemView:
    key: str
    label: str
    href: str | None
    state: str
    marker: str
    status_label: str


@dataclass(frozen=True, slots=True)
class DemoNavigationView:
    items: tuple[NavigationItemView, ...]


@dataclass(frozen=True, slots=True)
class AuditObservationView:
    evidence_id: str
    category: str
    outcome: str
    label: str
    status_label: str
    check_key: str
    description: str


@dataclass(frozen=True, slots=True)
class WebsiteEvidenceView:
    evidence_id: str
    evidence_class: str
    title: str | None
    page_label: str
    url: str
    excerpt: str | None
    content_truncated: bool


@dataclass(frozen=True, slots=True)
class OpportunityView:
    recommendation_id: str
    title: str
    priority: str
    summary: str
    rationale: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DemoResultsView:
    run_id: str
    audit_score: int
    audit_band: str
    seo_health_label: str
    key_findings: tuple[str, ...]
    key_observation_count: int
    high_priority_opportunity_count: int
    audit_recommendations: tuple[str, ...]
    audit_observations: tuple[AuditObservationView, ...]
    website_evidence: tuple[WebsiteEvidenceView, ...]
    opportunities: tuple[OpportunityView, ...]


@dataclass(frozen=True, slots=True)
class ChangeEvidenceView:
    evidence_id: str
    evidence_class: str
    title: str
    detail: str
    url: str | None = None
    outcome: str | None = None
    metadata: str | None = None


@dataclass(frozen=True, slots=True)
class ChangeView:
    change_id: str
    operation_type: str
    target: str
    title: str
    target_label: str
    priority: str
    why: str
    website_evidence: tuple[ChangeEvidenceView, ...]
    audit_evidence: tuple[ChangeEvidenceView, ...]
    external_research: tuple[ChangeEvidenceView, ...]


@dataclass(frozen=True, slots=True)
class DemoChangePlanView:
    run_id: str
    changes: tuple[ChangeView, ...]
    limitations: tuple[str, ...]
    draft_id: str | None


@dataclass(frozen=True, slots=True)
class DemoDraftReviewView:
    review: ContentDraftReviewView
    draft_title: str
    metadata: str
    why_title: str
    why: str
    website_evidence: tuple[ChangeEvidenceView, ...]
    audit_evidence: tuple[ChangeEvidenceView, ...]
    external_research: tuple[ChangeEvidenceView, ...]
    human_review_required: str = "Human Review Required"
    review_action: str = "READ ONLY"
    approval_record: str = "NOT RECORDED"
    approval_note: str = "Review does not record approval."
    delivery_label: str = "Continue to Delivery Setup — Coming in Demo Phase 2"
    delivery_enabled: bool = False


def present_navigation(
    *,
    current_step: str,
    destinations: dict[str, str | None],
) -> DemoNavigationView:
    step_keys = tuple(key for key, _label in _NAVIGATION_STEPS)
    if current_step not in step_keys:
        raise ValueError("Unknown Demo navigation step.")
    current_index = step_keys.index(current_step)
    items: list[NavigationItemView] = []
    for index, (key, label) in enumerate(_NAVIGATION_STEPS):
        href = destinations.get(key)
        if key == current_step:
            state, marker, status_label = "active", "\u25cf", "Current"
        elif href is not None and index < current_index:
            state, marker, status_label = "completed", "\u2713", "Completed"
        elif href is not None and index == current_index + 1:
            state, marker, status_label = "available", "\u25cb", "Available"
        else:
            state, marker, status_label = "locked", "\u25cb", "Locked"
            href = None
        items.append(
            NavigationItemView(
                key=key,
                label=label,
                href=href,
                state=state,
                marker=marker,
                status_label=status_label,
            )
        )
    return DemoNavigationView(items=tuple(items))


def _display_text(value: object, *, max_chars: int | None = None) -> str:
    text = "" if value is None else str(value)
    text = "".join(
        " " if unicodedata.category(character).startswith("C") else character
        for character in text
    )
    collapsed = " ".join(text.split())
    if max_chars is not None and len(collapsed) > max_chars:
        return collapsed[: max_chars - 3] + "..."
    return collapsed


def _audit_description(outcome: str, observed_value: object, note: str | None) -> str:
    description = f"Audit outcome: {outcome}. Observed value: {_display_text(observed_value)}."
    if note:
        description += f" {_display_text(note, max_chars=_MAX_EXCERPT_CHARS)}"
    return description


def _page_label(url: str) -> str:
    path = urlsplit(url).path.strip("/")
    if not path:
        return "Home page"
    slug = path.rsplit("/", 1)[-1].rsplit(".", 1)[0].replace("-", " ")
    if slug.casefold() == "machines":
        return "Machine page"
    return f"{slug.title()} page"


def _audit_label(check_key: str) -> str:
    labels = {
        "content.selection_guidance.present": "Selection guidance",
        "schema.product.detected": "Product schema",
    }
    return labels.get(check_key, check_key.replace(".", " ").replace("_", " ").title())


def _audit_status(outcome: str) -> str:
    if outcome in {"ABSENT", "NOT_DETECTED"}:
        return "Not detected"
    if outcome == "PRESENT":
        return "Detected"
    return outcome.replace("_", " ").title()


def _operation_label(operation_type: str) -> str:
    labels = {
        "EXPAND_SECTION": "Expand existing product content",
        "ADD_SECTION": "Add a focused content section",
        "ADD_COMPARISON_TABLE": "Add a buyer comparison table",
        "ADD_INTERNAL_LINK": "Add an internal content link",
        "CREATE_NEW_RESOURCE": "Create a supporting resource",
        "PROPOSE_SECTION_REORDER": "Reorder existing content sections",
    }
    return labels.get(operation_type, operation_type.replace("_", " ").title())


def _opportunity_summary(priority: str, topic: str) -> str:
    return f"A {priority.lower()}-priority opportunity focused on {topic} content."


def _change_reason(priority: str, topic: str) -> str:
    return (
        f"This {priority.lower()}-priority recommendation focuses on {topic} "
        "content already observed on the target page."
    )


def present_results(
    *,
    run_id: str,
    audit: SiteAuditResult,
    packet: SiteContentPacket,
    opportunities: ContentOpportunityReport,
) -> DemoResultsView:
    observations = tuple(
        AuditObservationView(
            evidence_id=item.evidence_id,
            category=item.evidence.category.value,
            outcome=item.evidence.outcome.value.upper(),
            label=_audit_label(item.evidence.check_key),
            status_label=_audit_status(item.evidence.outcome.value.upper()),
            check_key=item.evidence.check_key,
            description=_audit_description(
                item.evidence.outcome.value.upper(),
                item.evidence.observed_value,
                item.evidence.note,
            ),
        )
        for item in opportunities.audit_evidence
    )
    pages = tuple(
        WebsiteEvidenceView(
            evidence_id=page.evidence_id,
            evidence_class="Website Evidence",
            title=page.title,
            page_label=_page_label(page.final_url),
            url=page.final_url,
            excerpt=(
                _display_text(page.body_text, max_chars=_MAX_EXCERPT_CHARS) or None
            ),
            content_truncated=page.content_truncated,
        )
        for page in packet.pages
    )
    opportunity_rows = tuple(
        OpportunityView(
            recommendation_id=item.recommendation_id,
            title=item.title,
            priority=item.priority.value,
            summary=_opportunity_summary(item.priority.value, item.topic),
            rationale=item.rationale,
            evidence_refs=(*item.page_refs, *item.audit_refs, *item.source_refs),
        )
        for item in opportunities.opportunities
    )
    high_priority_count = sum(
        item.priority.value == "HIGH" for item in opportunities.opportunities
    )
    findings: list[str] = []
    if pages:
        findings.append(
            "Existing product content is present across "
            f"{len(pages)} captured page{'s' if len(pages) != 1 else ''}."
        )
    if any(
        item.evidence.check_key == "content.selection_guidance.present"
        and item.evidence.outcome.value.upper() in {"ABSENT", "NOT_DETECTED"}
        for item in opportunities.audit_evidence
    ):
        findings.append("Buyer-selection guidance was not detected by the audit.")
    if high_priority_count:
        findings.append(
            "One high-priority content opportunity was identified."
            if high_priority_count == 1
            else f"{high_priority_count} high-priority content opportunities were identified."
        )
    assert audit.score is not None and audit.band is not None
    return DemoResultsView(
        run_id=run_id,
        audit_score=audit.score,
        audit_band=audit.band,
        seo_health_label=audit.band.capitalize(),
        key_findings=tuple(findings[:3]),
        key_observation_count=len(observations),
        high_priority_opportunity_count=high_priority_count,
        audit_recommendations=audit.recommendations,
        audit_observations=observations,
        website_evidence=pages,
        opportunities=opportunity_rows,
    )


def present_change_plan(
    *,
    run_id: str,
    packet: SiteContentPacket,
    opportunities: ContentOpportunityReport,
    change_plan: ChangePlanReport,
    draft_id: str | None = None,
) -> DemoChangePlanView:
    page_by_id = {item.evidence_id: item for item in packet.pages}
    opportunity_by_id = {
        item.recommendation_id: item for item in opportunities.opportunities
    }
    audit_by_id = {
        item.evidence_id: item for item in opportunities.audit_evidence
    }
    material_by_id = {
        item.source_id: item for item in opportunities.source_materials
    }
    source_by_id = {item.source_id: item for item in opportunities.sources}
    rows: list[ChangeView] = []
    for change in change_plan.operations:
        opportunity = opportunity_by_id[change.opportunity_ref]
        website = tuple(
            ChangeEvidenceView(
                evidence_id=reference,
                evidence_class="Website Evidence",
                title=page_by_id[reference].title or page_by_id[reference].final_url,
                detail=(
                    _display_text(
                        page_by_id[reference].body_text,
                        max_chars=_MAX_EXCERPT_CHARS,
                    )
                    or "No text excerpt was retained."
                ),
                url=page_by_id[reference].final_url,
            )
            for reference in change.page_refs
        )
        audits = tuple(
            ChangeEvidenceView(
                evidence_id=reference,
                evidence_class="SEO Audit Evidence",
                title=_audit_label(audit_by_id[reference].evidence.check_key),
                detail=_audit_status(
                    audit_by_id[reference].evidence.outcome.value.upper()
                ),
                outcome=audit_by_id[reference].evidence.outcome.value.upper(),
                metadata=(
                    f"{audit_by_id[reference].evidence.check_key} · "
                    f"{audit_by_id[reference].evidence.outcome.value.upper()}"
                ),
            )
            for reference in change.audit_refs
        )
        research = tuple(
            ChangeEvidenceView(
                evidence_id=reference,
                evidence_class="External Research",
                title=material_by_id[reference].title,
                detail=_display_text(
                    material_by_id[reference].content,
                    max_chars=_MAX_EXCERPT_CHARS,
                ),
                url=source_by_id[reference].url,
            )
            for reference in change.source_refs
        )
        target = (
            change.locator.page_ref
            if change.locator.page_ref is not None
            else change.target_kind.value
        )
        target_label = (
            page_by_id[target].title or _page_label(page_by_id[target].final_url)
            if target in page_by_id
            else target
        )
        operation_type = change.operation_type.value
        rows.append(
            ChangeView(
                change_id=change.change_id,
                operation_type=operation_type,
                target=target,
                title=_operation_label(operation_type),
                target_label=target_label,
                priority=opportunity.priority.value,
                why=_change_reason(opportunity.priority.value, opportunity.topic),
                website_evidence=website,
                audit_evidence=audits,
                external_research=research,
            )
        )
    return DemoChangePlanView(
        run_id=run_id,
        changes=tuple(rows),
        limitations=change_plan.limitations,
        draft_id=draft_id,
    )


def present_draft_review(review: ContentDraftReviewView) -> DemoDraftReviewView:
    priority = review.opportunity.priority
    website = tuple(
        ChangeEvidenceView(
            evidence_id=item.evidence_id,
            evidence_class="Website Evidence",
            title=item.title or _page_label(item.url),
            detail=item.excerpt or "No text excerpt was retained.",
            url=item.url,
        )
        for item in review.page_evidence
    )
    audits = tuple(
        ChangeEvidenceView(
            evidence_id=item.evidence_id,
            evidence_class="SEO Audit Evidence",
            title=_audit_label(item.check_key),
            detail=_audit_status(item.outcome.upper()),
            outcome=item.outcome.upper(),
            metadata=f"{item.check_key} · {item.outcome.upper()}",
        )
        for item in review.audit_evidence
    )
    research = tuple(
        ChangeEvidenceView(
            evidence_id=item.source_id,
            evidence_class="External Research",
            title=item.title,
            detail=item.excerpt or "No text excerpt was retained.",
            url=item.url,
        )
        for item in review.source_evidence
    )
    return DemoDraftReviewView(
        review=review,
        draft_title=review.draft.heading or review.opportunity.title,
        metadata=(
            f"{review.draft.draft_id} · {review.change.change_id} · "
            f"{priority.title()} priority"
        ),
        why_title=_operation_label(review.change.operation_type),
        why=_change_reason(priority, review.opportunity.topic),
        website_evidence=website,
        audit_evidence=audits,
        external_research=research,
    )
