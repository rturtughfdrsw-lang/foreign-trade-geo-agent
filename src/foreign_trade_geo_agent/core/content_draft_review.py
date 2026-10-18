"""Provider-independent read-only review view for one persisted D#."""

from __future__ import annotations

from .draft_customer_evidence import DraftCustomerEvidence
from .draft_candidate_review import CandidateDecision

from dataclasses import dataclass
import json
import re
import unicodedata
import hashlib
from datetime import datetime
from typing import Protocol

from .change_plan import ChangeOperation
from .content_draft import (
    MAX_CLAIMS_PER_DRAFT,
    MAX_RAW_OUTPUT_CHARS,
    BulletListBlock,
    ComparisonTableBlock,
    DraftBlock,
    DraftItem,
    InternalLinkBlock,
    ParagraphBlock,
    article_quality_findings,
)
from .content_opportunity import (
    ContentOpportunity,
    ContentOpportunitySource,
    ContentOpportunitySourceMaterial,
)
from .history import validate_uuid
from .history import validate_aware_datetime
from .optimization import NumberedAuditEvidence
from .site_content import SiteContentEvidence


MAX_REVIEW_EXCERPT_CHARS = 200

_DRAFT_ID_PATTERN = re.compile(r"D[1-9][0-9]*")

LOCAL_REVIEW_STATUSES = ("PENDING_REVIEW", "CHANGES_REQUESTED", "LOCAL_REVIEW_COMPLETE")
MAX_LOCAL_BODY = MAX_RAW_OUTPUT_CHARS
MAX_LOCAL_NOTE = 2000
MAX_LOCAL_REVISIONS = 100


def local_text_digest(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def validate_local_review_text(body: str, note: str, status: str) -> None:
    if (type(body) is not str or not body.strip() or len(body) > MAX_LOCAL_BODY
            or type(note) is not str or len(note) > MAX_LOCAL_NOTE
            or any(ord(c) < 32 and c not in "\n\r\t" for c in body + note)
            or status not in LOCAL_REVIEW_STATUSES):
        raise ContentDraftReviewValidationError("Local review input is invalid.")


@dataclass(frozen=True, slots=True)
class LocalDraftRevision:
    """Local feedback on one native Draft; never a DraftItem or approval record."""

    origin_sha256: str
    version: int
    parent_version: int
    body_text: str
    body_sha256: str
    note: str
    status: str
    validation_state: str
    frozen_evidence_sha256: str
    observed_evidence_sha256: str
    saved_at: datetime
    candidate_decisions: tuple[CandidateDecision, ...] = ()

    def __post_init__(self):
        if (type(self.candidate_decisions) is not tuple or len(self.candidate_decisions) > MAX_CLAIMS_PER_DRAFT
                or not all(type(d) is CandidateDecision for d in self.candidate_decisions)
                or len({d.claim_id for d in self.candidate_decisions}) != len(self.candidate_decisions)):
            raise ContentDraftReviewValidationError("Candidate decisions are invalid.")
        validate_local_review_text(self.body_text, self.note, self.status)
        validate_aware_datetime(self.saved_at, "saved_at")
        if (type(self.version) is not int or not 1 <= self.version <= MAX_LOCAL_REVISIONS
                or type(self.parent_version) is not int or self.parent_version != self.version - 1
                or self.validation_state not in {"HISTORICAL_NATIVE_VALIDATION", "PENDING_REVALIDATION"}
                or self.body_sha256 != local_text_digest(self.body_text)
                or any(type(h) is not str or re.fullmatch(r"[0-9a-f]{64}", h) is None
                       for h in (self.origin_sha256, self.frozen_evidence_sha256, self.observed_evidence_sha256))):
            raise ContentDraftReviewValidationError("Local revision is invalid.")


class LocalDraftReviewStore(Protocol):
    def revisions(self, origin_sha256: str) -> tuple[LocalDraftRevision, ...]: ...

    def append(self, *, origin_sha256: str, expected_version: int, original_body: str,
               body_text: str, note: str, status: str, frozen_evidence_sha256: str,
               observed_evidence_sha256: str, saved_at: datetime) -> LocalDraftRevision: ...


class ContentDraftReviewValidationError(ValueError):
    """A deterministic local validation failure before any read happens."""


@dataclass(frozen=True, slots=True)
class ContentDraftReviewRequest:
    planning_run_id: str
    content_draft_artifact_id: str
    draft_id: str

    def __post_init__(self) -> None:
        try:
            validate_uuid(self.planning_run_id, "planning_run_id")
            validate_uuid(
                self.content_draft_artifact_id,
                "content_draft_artifact_id",
            )
        except ValueError:
            raise ContentDraftReviewValidationError(
                "Review identifiers are invalid."
            ) from None
        if (
            type(self.draft_id) is not str
            or _DRAFT_ID_PATTERN.fullmatch(self.draft_id) is None
        ):
            raise ContentDraftReviewValidationError("Review draft ID is invalid.")


@dataclass(frozen=True, slots=True)
class ReviewClaimView:
    claim_id: str
    claim_type: str
    support_kind: str | None
    text: str
    page_refs: tuple[str, ...]
    source_refs: tuple[str, ...]
    customer_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ReviewDraftView:
    draft_id: str
    draft_type: str
    heading: str | None
    requires_title_override: bool
    body_text: str
    ordered_headings: tuple[str, ...]
    target_kind: str
    target_page_ref: str | None
    locator_kind: str
    locator_heading: str | None
    requires_human_review: bool
    claims: tuple[ReviewClaimView, ...]
    quality_findings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ReviewChangeView:
    change_id: str
    opportunity_ref: str
    operation_type: str
    source_action_code: str
    target_kind: str
    target_page_ref: str | None
    locator_kind: str
    locator_heading: str | None
    proposed_heading: str | None
    section_purpose: str | None
    content_points: tuple[tuple[str, str], ...]
    briefs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReviewOpportunityView:
    recommendation_id: str
    opportunity_type: str
    priority: str
    topic: str
    title: str
    rationale: str
    actions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReviewAuditEvidenceView:
    evidence_id: str
    category: str
    check_key: str
    outcome: str
    observed_value: str
    provider_field: str
    note: str | None


@dataclass(frozen=True, slots=True)
class ReviewPageEvidenceView:
    evidence_id: str
    title: str | None
    url: str
    excerpt: str | None
    content_truncated: bool


@dataclass(frozen=True, slots=True)
class ReviewSourceEvidenceView:
    source_id: str
    title: str
    url: str
    excerpt: str | None
    content_truncated: bool


@dataclass(frozen=True, slots=True)
class ContentDraftReviewView:
    planning_run_id: str
    content_draft_artifact_id: str
    payload_version: int
    draft: ReviewDraftView
    change: ReviewChangeView
    opportunity: ReviewOpportunityView
    audit_evidence: tuple[ReviewAuditEvidenceView, ...]
    page_evidence: tuple[ReviewPageEvidenceView, ...]
    source_evidence: tuple[ReviewSourceEvidenceView, ...]
    limitations: tuple[str, ...]
    customer_evidence: DraftCustomerEvidence | None = None


def _display_text(value: object, *, max_chars: int | None = None) -> str:
    """Collapse untrusted text to one safe display line."""

    text = "" if value is None else str(value)
    text = "".join(
        " " if unicodedata.category(character).startswith("C") else character
        for character in text
    )
    collapsed = " ".join(text.split())
    if max_chars is not None and len(collapsed) > max_chars:
        return collapsed[: max_chars - 3] + "..."
    return collapsed


def _excerpt(value: object) -> str | None:
    text = _display_text(value, max_chars=MAX_REVIEW_EXCERPT_CHARS)
    return text or None


def _render_block(block: DraftBlock) -> str:
    if isinstance(block, ParagraphBlock):
        return _display_text(" ".join(claim.text for claim in block.claims))
    if isinstance(block, BulletListBlock):
        return "\n".join(
            f"- {_display_text(item.text)}" for item in block.items
        )
    if isinstance(block, ComparisonTableBlock):
        rows: list[str] = []
        for cell in block.cells:
            if cell.row_dimension not in rows:
                rows.append(cell.row_dimension)
        columns: list[str] = []
        for cell in block.cells:
            if cell.column not in columns:
                columns.append(cell.column)
        values = {(cell.row_dimension, cell.column): cell.text for cell in block.cells}
        lines = [
            "| Dimension | " + " | ".join(columns) + " |",
            "| --- | " + " | ".join("---" for _ in columns) + " |",
        ]
        for row in rows:
            lines.append(
                "| "
                + _display_text(row)
                + " | "
                + " | ".join(
                    _display_text(values.get((row, column), ""))
                    for column in columns
                )
                + " |"
            )
        return "\n".join(lines)
    if isinstance(block, InternalLinkBlock):
        insertion = _display_text(
            " ".join(claim.text for claim in block.insertion_claims)
        )
        link = f"[{_display_text(block.anchor_text)}] -> {_display_text(block.target_url)}"
        return f"{insertion} {link}".strip()
    return ""


def render_draft_body_text(draft: DraftItem) -> str:
    """Render the persisted draft blocks as deterministic plain text."""

    sections: list[str] = []
    if _display_text(draft.heading):
        sections.append(_display_text(draft.heading))
    if draft.draft_type.value == "STRUCTURE_ONLY":
        if draft.ordered_headings:
            sections.append(
                "\n".join(
                    f"{number}. {_display_text(heading)}"
                    for number, heading in enumerate(draft.ordered_headings, start=1)
                )
            )
    elif draft.draft_type.value == "NEW_RESOURCE_DRAFT":
        if draft.section_block_counts:
            offset = 0
            for heading, count in zip(draft.ordered_headings, draft.section_block_counts):
                sections.append("## " + _display_text(heading))
                sections.extend(_render_block(block) for block in draft.blocks[offset:offset + count])
                offset += count
            return "\n\n".join(sections)
        if draft.ordered_headings:
            sections.append(
                "Outline:\n"
                + "\n".join(
                    f"{number}. {_display_text(heading)}"
                    for number, heading in enumerate(draft.ordered_headings, start=1)
                )
            )
        rendered = [_render_block(block) for block in draft.blocks]
        sections.extend(item for item in rendered if item)
    else:
        rendered = [_render_block(block) for block in draft.blocks]
        sections.extend(item for item in rendered if item)
    if not sections:
        return "(no draft body content was persisted for this draft)"
    return "\n\n".join(sections)


def _change_briefs(change: ChangeOperation) -> tuple[str, ...]:
    briefs: list[str] = []
    if change.comparison_table_spec is not None:
        briefs.append(
            "Comparison table columns: "
            + ", ".join(change.comparison_table_spec.column_headers)
            + " / rows: "
            + ", ".join(change.comparison_table_spec.row_dimensions)
        )
    if change.internal_link_spec is not None:
        briefs.append(
            "Internal link: "
            f"{change.internal_link_spec.source_page_ref} -> "
            f"{change.internal_link_spec.target_page_ref} "
            f"(anchor intent: {change.internal_link_spec.anchor_intent})"
        )
    if change.new_resource_spec is not None:
        briefs.append(
            "New resource purpose: "
            + change.new_resource_spec.resource_purpose.value
            + " / outline: "
            + "; ".join(change.new_resource_spec.outline_headings)
        )
    return tuple(_display_text(brief) for brief in briefs)


def build_content_draft_review_view(
    *,
    planning_run_id: str,
    content_draft_artifact_id: str,
    payload_version: int,
    draft: DraftItem,
    change: ChangeOperation,
    opportunity: ContentOpportunity,
    audit_evidence: tuple[NumberedAuditEvidence, ...],
    pages: tuple[SiteContentEvidence, ...],
    materials: tuple[ContentOpportunitySourceMaterial, ...],
    sources: tuple[ContentOpportunitySource, ...],
    limitations: tuple[str, ...],
) -> ContentDraftReviewView:
    """Build the single core view consumed by every review renderer."""

    material_by_id = {material.source_id: material for material in materials}
    source_by_id = {source.source_id: source for source in sources}
    claim_views: list[ReviewClaimView] = []
    for block in draft.blocks:
        claims = ()
        if isinstance(block, ParagraphBlock):
            claims = block.claims
        elif isinstance(block, BulletListBlock):
            claims = block.items
        elif isinstance(block, InternalLinkBlock):
            claims = block.insertion_claims
        for claim in claims:
            claim_views.append(
                ReviewClaimView(
                    claim_id=claim.claim_id,
                    claim_type=claim.claim_type.value,
                    support_kind=(
                        None
                        if claim.support_kind is None
                        else claim.support_kind.value
                    ),
                    text=_display_text(claim.text),
                    page_refs=claim.page_refs,
                    source_refs=claim.source_refs,
                    customer_refs=claim.customer_refs,
                )
            )
    return ContentDraftReviewView(
        planning_run_id=planning_run_id,
        content_draft_artifact_id=content_draft_artifact_id,
        payload_version=payload_version,
        draft=ReviewDraftView(
            draft_id=draft.draft_id,
            draft_type=draft.draft_type.value,
            heading=draft.heading,
            requires_title_override=not _display_text(draft.heading),
            body_text=render_draft_body_text(draft),
            ordered_headings=tuple(
                _display_text(heading) for heading in draft.ordered_headings
            ),
            target_kind=draft.target_kind.value,
            target_page_ref=draft.target_page_ref,
            locator_kind=draft.locator.locator_kind.value,
            locator_heading=draft.locator.observed_heading,
            requires_human_review=draft.requires_human_review,
            claims=tuple(claim_views),
            quality_findings=article_quality_findings(change, draft.blocks, draft.section_block_counts, draft.customer_evidence),
        ),
        change=ReviewChangeView(
            change_id=change.change_id,
            opportunity_ref=change.opportunity_ref,
            operation_type=change.operation_type.value,
            source_action_code=change.source_action_code.value,
            target_kind=change.target_kind.value,
            target_page_ref=change.locator.page_ref,
            locator_kind=change.locator.locator_kind.value,
            locator_heading=change.locator.observed_heading,
            proposed_heading=change.proposed_heading,
            section_purpose=(
                None
                if change.section_purpose is None
                else change.section_purpose.value
            ),
            content_points=tuple(
                (_display_text(point.intent.value), _display_text(point.subject))
                for point in change.content_points
            ),
            briefs=_change_briefs(change),
        ),
        opportunity=ReviewOpportunityView(
            recommendation_id=opportunity.recommendation_id,
            opportunity_type=opportunity.opportunity_type.value,
            priority=opportunity.priority.value,
            topic=_display_text(opportunity.topic),
            title=_display_text(opportunity.title),
            rationale=_display_text(opportunity.rationale),
            actions=tuple(_display_text(action) for action in opportunity.actions),
        ),
        audit_evidence=tuple(
            ReviewAuditEvidenceView(
                evidence_id=item.evidence_id,
                category=item.evidence.category.value,
                check_key=item.evidence.check_key,
                outcome=item.evidence.outcome.value,
                observed_value=_display_text(
                    json.dumps(
                        item.evidence.observed_value,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    max_chars=MAX_REVIEW_EXCERPT_CHARS,
                ),
                provider_field=item.evidence.provider_field,
                note=(
                    None
                    if item.evidence.note is None
                    else _display_text(item.evidence.note)
                ),
            )
            for item in audit_evidence
        ),
        page_evidence=tuple(
            ReviewPageEvidenceView(
                evidence_id=page.evidence_id,
                title=page.title,
                url=page.final_url,
                excerpt=_excerpt(page.body_text),
                content_truncated=page.content_truncated,
            )
            for page in pages
        ),
        source_evidence=tuple(
            ReviewSourceEvidenceView(
                source_id=source_by_id[material.source_id].source_id,
                title=source_by_id[material.source_id].title,
                url=source_by_id[material.source_id].url,
                excerpt=_excerpt(material_by_id[material.source_id].content),
                content_truncated=material_by_id[material.source_id].content_truncated,
            )
            for material in materials
        ),
        limitations=tuple(_display_text(item) for item in limitations),
        customer_evidence=draft.customer_evidence,
    )
