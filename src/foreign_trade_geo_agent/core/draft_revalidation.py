"""Bounded local replay of one revision; never semantic or production authority.

Only an unchanged body or a single trailing CTA substitution can complete this
local path. Native validation is structural; a human must still review the
entire text, evidence and applicability, including whether the CTA adds facts.
"""
from dataclasses import asdict, dataclass
from datetime import datetime
import json
import re
from typing import Protocol

from .content_draft import (
    BulletListBlock, BulletListSpecification, ContentDraftSpecification,
    DraftClaimSpecification, NewResourceSectionSpecification,
    ParagraphBlock, ParagraphSpecification, finalize_draft_item,
)
from .content_draft_review import local_text_digest, render_draft_body_text, MAX_LOCAL_NOTE
from .evidence_intake import digest_valid, require, snapshot_digest, text
from .history import validate_aware_datetime

RULE_VERSION = 'TRAILING_CTA_LOCAL_V1'


@dataclass(frozen=True, slots=True)
class RevisionCheckItem:
    claim_id: str
    original_text: str
    revision_text: str
    state: str
    refs: tuple[str, ...]
    details: tuple[str, ...]
    reason: str

    def __post_init__(self):
        require(text(self.claim_id, 128) and text(self.original_text, 16000) and text(self.revision_text, 16000)
                and self.state in {'BINDING_RECHECKED', 'EDITORIAL_UNCHANGED', 'MANUAL_CTA_REVIEW', 'PENDING'}
                and type(self.refs) is tuple and len(self.refs) <= 32
                and all(text(r, 128) for r in self.refs)
                and type(self.details) is tuple and len(self.details) <= 32
                and all(text(d, 4000) for d in self.details) and text(self.reason, 2000)
                and (self.state == 'BINDING_RECHECKED' or not self.refs))


@dataclass(frozen=True, slots=True)
class RevisionRevalidationReport:
    rule_version: str
    origin_sha256: str
    version: int
    latest_version: int
    body_sha256: str
    evidence_sha256: str
    native_state: str
    eligible: bool
    items: tuple[RevisionCheckItem, ...]
    reasons: tuple[str, ...]

    def __post_init__(self):
        require(self.rule_version == RULE_VERSION
                and all(digest_valid(h) for h in (self.origin_sha256, self.body_sha256, self.evidence_sha256))
                and type(self.version) is int and 1 <= self.version <= 100
                and type(self.latest_version) is int and self.version <= self.latest_version <= 100
                and self.native_state in {'PASSED', 'BLOCKED', 'NOT_RUN'}
                and type(self.eligible) is bool and type(self.items) is tuple
                and 1 <= len(self.items) <= 17 and all(type(i) is RevisionCheckItem for i in self.items)
                and type(self.reasons) is tuple and len(self.reasons) <= 10
                and all(text(r, 2000) for r in self.reasons)
                and (not self.eligible or (self.native_state == 'PASSED'
                     and not self.reasons and all(i.state != 'PENDING' for i in self.items))))

    @property
    def sha256(self):
        return local_text_digest(json.dumps(asdict(self), ensure_ascii=False, sort_keys=True, separators=(',', ':')))


@dataclass(frozen=True, slots=True)
class LocalRevisionRevalidation:
    report: RevisionRevalidationReport
    note: str
    confirmed: bool
    decision: str
    saved_at: datetime

    def __post_init__(self):
        require(type(self.report) is RevisionRevalidationReport and text(self.note, MAX_LOCAL_NOTE)
                and self.confirmed is True and self.decision in {'CONFIRMED', 'ISSUES_FOUND'})
        validate_aware_datetime(self.saved_at, 'saved_at')


class LocalRevalidationStore(Protocol):
    def records(self, origin: str) -> tuple[LocalRevisionRevalidation, ...]: ...

    def append(self, record: LocalRevisionRevalidation) -> None: ...


def revalidate_revision(review, revision, current, draft, *, latest_version=None):
    """Rebuild only the existing native structure, never infer new factual claims."""
    original, body = review.draft.body_text, revision.body_text
    bundle = review.customer_evidence
    value = current.planning_input
    operation = next((o for o in value.change_plan_report.operations if o.change_id == draft.change_ref), None)
    opportunity = next((o for o in value.opportunity_report.opportunities if o.recommendation_id == draft.opportunity_ref), None)
    scope_ok = bool(bundle and operation and opportunity and current.plan_bound
        and snapshot_digest(current) == bundle.snapshot_sha256
        and revision.frozen_evidence_sha256 == bundle.snapshot_sha256
        and revision.observed_evidence_sha256 == bundle.snapshot_sha256
        and bundle.matches_native(value.site_content, value.opportunity_report, operation))
    native_claims = tuple(c for b in draft.blocks for c in
        (b.claims if isinstance(b, ParagraphBlock) else b.items if isinstance(b, BulletListBlock) else ()))
    view_ok = (render_draft_body_text(draft) == original
        and len(native_claims) == len(review.draft.claims)
        and all((c.claim_id, ' '.join(c.text.split()), c.claim_type.value, c.page_refs, c.source_refs, c.customer_refs)
                == (v.claim_id, v.text, v.claim_type, v.page_refs, v.source_refs, v.customer_refs)
                for c, v in zip(native_claims, review.draft.claims)))
    active = {e.supplement.evidence_id: e for e in current.active_evidence}
    source_ok = {}
    for source in bundle.sources if bundle else ():
        record = active.get(source.evidence_id)
        source_ok[source.evidence_id] = bool(scope_ok and record
            and record.evidence_version == source.evidence_version
            and record.supplement.source_locator == source.source_locator
            and record.supplement.source_label == source.source_label
            and record.supplement.requirement_ids == source.requirement_ids
            and record.supplement.content == source.content
            and local_text_digest(record.supplement.content) == source.content_sha256
            and record.supplement.content[source.span_start:source.span_end] == source.quote)
    all_sources_ok = bool(source_ok) and all(source_ok.values())
    last = review.draft.claims[-1] if review.draft.claims else None
    prefix = original[:-len(last.text)] if last and original.endswith(last.text) else None
    replacement = body[len(prefix):] if prefix is not None and body.startswith(prefix) else None
    # This syntax admits a manual-review candidate only. Neither these words
    # nor native token checks prove that the sentence contains no factual claim.
    cta_only = bool(last and last.claim_type == 'CALL_TO_ACTION'
        and not (last.page_refs or last.source_refs or last.customer_refs)
        and original.count(last.text) == 1 and replacement and len(replacement) <= 300
        and re.fullmatch(r'(?:Ask|Contact|Prepare|Send|Discuss|Request|Confirm|Review) [A-Za-z0-9 ,\x27-]+[.?]', replacement))
    shape_ok = body == original or cta_only
    reasons = []
    if not scope_ok or not all_sources_ok:
        reasons.append('当前 Intake、来源、locator、证据版本或适用范围与冻结绑定不一致；需要重新准备并审核证据。')
    if not view_ok:
        reasons.append('原陈述与原生 Draft 引用不一致；拒绝将 E 事实转换为 P/S。')
    if not shape_ok:
        reasons.append('修改超出唯一末尾 CTA 的替换规则，可能包含新增事实、条件或范围变化；不能自动沿用旧引用。')
    native_state = 'NOT_RUN'
    if shape_ok and scope_ok and all_sources_ok and view_ok:
        sections, offset = [], 0
        for heading, count in zip(draft.ordered_headings, draft.section_block_counts):
            blocks = []
            for block in draft.blocks[offset:offset + count]:
                claims = block.claims if isinstance(block, ParagraphBlock) else block.items
                specs = tuple(DraftClaimSpecification(
                    replacement if c.claim_id == last.claim_id else c.text,
                    c.claim_type, c.page_refs, c.source_refs, c.customer_refs, c.proposal) for c in claims)
                blocks.append(ParagraphSpecification(block.kind, specs) if isinstance(block, ParagraphBlock)
                              else BulletListSpecification(block.kind, specs))
            sections.append(NewResourceSectionSpecification(heading, tuple(blocks)))
            offset += count
        rebuilt, error = finalize_draft_item(1, ContentDraftSpecification(
            draft.change_ref, draft.draft_type, sections=tuple(sections)), operation, opportunity,
            value.site_content, value.opportunity_report, customer_evidence=bundle)
        native_state = 'PASSED' if rebuilt and not error and render_draft_body_text(rebuilt) == body else 'BLOCKED'
        if native_state != 'PASSED':
            reasons.append('原生技术校验未通过（' + (error or 'BODY_ROUNDTRIP_MISMATCH') + '）；不能作为纯 CTA 修改完成核验。')
    original_parts, parts = original.split('\n\n'), body.split('\n\n')
    items = []
    for claim in review.draft.claims:
        positions = [i for i, p in enumerate(original_parts) if claim.text in p]
        unchanged = bool(len(positions) == 1 and positions[0] < len(parts)
            and original_parts[positions[0]] == parts[positions[0]])
        # A verified trailing substitution preserves every preceding byte,
        # including other claims in the CTA's paragraph.
        if cta_only and claim is not last:
            unchanged = True
        refs = claim.page_refs + claim.source_refs + claim.customer_refs
        bound = bool(shape_ok and unchanged and scope_ok and view_ok and all_sources_ok
            and all(source_ok.get(ref.split('.')[0], False) for ref in claim.customer_refs))
        details = []
        if bound:
            for source in bundle.sources:
                if any(r.split('.')[0] == source.evidence_id for r in claim.customer_refs):
                    details.append(f'{source.evidence_id} · v{source.evidence_version} · {source.source_locator} · '
                        f'{", ".join(source.requirement_ids)} · [{source.span_start}, {source.span_end}] · SHA256 {source.content_sha256}')
                    details.extend(f'{f.fact_ref} · [{f.start}, {f.end}] · {f.quote}'
                                   for f in source.facts if f.fact_ref in claim.customer_refs)
            details.extend(f'{p.evidence_id} · {p.url}' for p in review.page_evidence if p.evidence_id in claim.page_refs)
            details.extend(f'{s.source_id} · {s.url} · UNVERIFIED_EXTERNAL_CONTEXT' for s in review.source_evidence if s.source_id in claim.source_refs)
        state = ('BINDING_RECHECKED' if bound and refs else 'EDITORIAL_UNCHANGED' if bound else
                 'MANUAL_CTA_REVIEW' if cta_only and claim is last and native_state == 'PASSED' else 'PENDING')
        reason = {'BINDING_RECHECKED': '陈述与上下文未变；来源和版本绑定已重新核对，语义真实性仍需人工判断。',
                  'EDITORIAL_UNCHANGED': '原编辑性文字未变，无事实引用。',
                  'MANUAL_CTA_REVIEW': '末尾 CTA 改写已通过技术检查；人工须确认只是请求或建议，没有新事实或范围变化。',
                  'PENDING': '陈述、上下文或证据绑定变化，旧引用不适用于修订稿；请核对原文与当前全文。'}[state]
        revised_text = (replacement if cta_only and claim is last else claim.text if unchanged else
                        parts[positions[0]] if len(positions) == 1 and positions[0] < len(parts) else '(陈述已删除或无法定位)')
        items.append(RevisionCheckItem(claim.claim_id, claim.text, revised_text, state, refs if bound else (), tuple(details), reason))
    if not shape_ok:
        items.append(RevisionCheckItem('REVISION_DIFF', original, body, 'PENDING', (), (),
            '存在未映射的修订内容；本功能不推断其语义支持，也不自动分配 P/S/E。'))
    return RevisionRevalidationReport(RULE_VERSION, revision.origin_sha256, revision.version,
        latest_version if latest_version is not None else revision.version,
        revision.body_sha256, snapshot_digest(current), native_state,
        not reasons and native_state == 'PASSED', tuple(items), tuple(reasons))
