"""Review projections of native specifications, never admitted DraftItems.

The raw provider output stays in the existing append-only local Draft revision
journal. This module performs deterministic checks, not semantic certification.
"""
from dataclasses import asdict, dataclass
from enum import Enum
import hashlib
import json
import re

from . import content_draft as cd
from .draft_customer_evidence import InterpretationProposal


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def candidate_binding(value, raw):
    # Full task/Plan graph, all source bytes/versions/offsets and raw output.
    # Timestamps changing during fresh review do not change the evidence.
    bundle = asdict(value.customer_evidence)
    for key in ('reviewed_at', 'reviewer_id', 'interpretations'):
        bundle.pop(key)
    data = [asdict(value.site_content), asdict(value.opportunity_report),
            asdict(value.change_plan_report), bundle, asdict(value.writing_brief), raw]
    return digest(json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':'),
        default=lambda v: v.value if isinstance(v, Enum) else v.isoformat()))


@dataclass(frozen=True, slots=True)
class CandidateDecision:
    binding_sha256: str
    claim_id: str
    decision: str
    note: str

    def __post_init__(self):
        if (type(self.binding_sha256) is not str or len(self.binding_sha256) != 64 or any(c not in '0123456789abcdef' for c in self.binding_sha256)
                or self.decision not in {'APPROVE', 'REJECT', 'REQUEST_CHANGES'}
                or type(self.claim_id) is not str or re.fullmatch(r'CL[1-9][0-9]?', self.claim_id) is None
                or type(self.note) is not str or not self.note.strip() or len(self.note) > 2000
                or any(ord(c) < 32 and c not in "\n\r\t" for c in self.note)):
            raise ValueError('CANDIDATE_DECISION_INVALID')


@dataclass(frozen=True, slots=True)
class CandidateClaimCheck:
    claim_id: str
    text: str
    claim_type: str
    refs: tuple[str, ...]
    proposal: InterpretationProposal | None
    deterministic_error: str | None
    evidence_details: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CandidateCheck:
    binding_sha256: str
    raw_sha256: str
    state: str
    errors: tuple[str, ...]
    claims: tuple[CandidateClaimCheck, ...]
    source_documents: tuple[str, ...]
    production_authorized: bool = False


def inspect_specification(value, raw, spec, *, current_snapshot_sha256):
    """Only native NEW_RESOURCE specifications; never constructs an admitted Draft."""
    error = cd.stable_content_draft_input_error(value)
    if error or value.customer_evidence is None or value.writing_brief is None:
        raise ValueError(error or 'CUSTOMER_EVIDENCE_INVALID')
    bundle = value.customer_evidence
    operation = value.change_plan_report.operations[0]
    resource = operation.new_resource_spec
    errors = []
    if current_snapshot_sha256 != bundle.snapshot_sha256:
        errors.append('STALE_EVIDENCE_SNAPSHOT')
    if (spec.change_ref != operation.change_id or spec.draft_type is not cd.ContentDraftType.NEW_RESOURCE_DRAFT
            or resource is None or tuple(s.outline_heading for s in spec.sections) != resource.outline_headings):
        raise ValueError('NEW_RESOURCE_INVALID')
    blocks = tuple(b for s in spec.sections for b in s.blocks)
    if not blocks or len(blocks) > cd.MAX_BLOCKS_PER_DRAFT:
        errors.append('BLOCK_BUDGET')
    evidence = cd._build_evidence_context(operation, value.site_content, value.opportunity_report)
    context = dict(page_ids=evidence.page_ids, source_ids=evidence.source_ids,
        allowed_pages=evidence.allowed_pages, allowed_sources=evidence.allowed_sources,
        page_text_by_id=evidence.page_text_by_id,
        first_party_text=evidence.first_party_text + ' ' + ' '.join(s.quote for s in bundle.sources),
        first_party_entities=evidence.first_party_entities | frozenset(token.casefold()
            for source in bundle.sources for token in cd._MODEL_TOKEN_RE.findall(source.quote)), customer_quote_by_id=bundle.quote_map(),
        customer_binding=bundle, proposal_only=True)
    claims, views, seen, preview_blocks = [], [], set(), []
    for section, brief in zip(spec.sections, resource.section_briefs):
        if not section.blocks or sum(b.kind is cd.DraftBlockKind.PARAGRAPH for b in section.blocks) > cd.MAX_PARAGRAPHS_PER_DRAFT:
            errors.append('BLOCK_BUDGET')
        for block in section.blocks:
            group = block.claims if isinstance(block, cd.ParagraphSpecification) else block.items
            maximum = cd.MAX_CLAIMS_PER_BLOCK if isinstance(block, cd.ParagraphSpecification) else cd.MAX_BULLET_ITEMS
            if not group or len(group) > maximum:
                errors.append('CLAIM_BUDGET')
            # Read-only shape used by the same article quality check. These are
            # specifications, not trusted DraftClaims or a persisted DraftItem.
            preview_blocks.append(cd.ParagraphBlock(block.kind, group))
            for claim in group:
                claims.append(claim)
                problem = cd._validate_claim_evidence(claim, **context)
                if claim.proposal is not None and claim.proposal.procurement_question != brief.reader_question:
                    problem = problem or 'PROCUREMENT_QUESTION_MISMATCH'
                if (claim.claim_type is cd.DraftClaimType.EVIDENCE_BASED_INTERPRETATION
                        and claim.proposal is None):
                    problem = problem or 'PROPOSAL_METADATA_REQUIRED'
                if isinstance(block, cd.BulletListSpecification) and len(claim.text) > cd.MAX_BULLET_ITEM_CHARS:
                    problem = problem or 'CLAIM_BUDGET'
                identity = ' '.join(claim.text.casefold().split())
                if identity in seen:
                    problem = problem or 'DUPLICATE_CLAIM'
                seen.add(identity)
                details = []
                for ref in claim.customer_refs:
                    for source in bundle.sources:
                        for fact in source.facts:
                            if fact.fact_ref == ref:
                                details.append(f'{ref} · v{source.evidence_version} · {source.source_label} · '
                                    f'{source.source_locator} · SHA256 {source.content_sha256} · '
                                    f'[{fact.start}:{fact.end}] · {fact.quote}')
                views.append(CandidateClaimCheck(f'CL{len(claims)}', claim.text, claim.claim_type.value,
                    claim.customer_refs, claim.proposal, problem, tuple(details)))
                if problem:
                    errors.append(f'CL{len(claims)}: {problem}')
    if len(claims) > cd.MAX_CLAIMS_PER_DRAFT:
        errors.append('CLAIM_BUDGET')
    if not bundle.reference_selection_valid(r for c in claims for r in c.customer_refs):
        errors.append('CUSTOMER_EVIDENCE_COVERAGE')
    errors.extend(cd.article_quality_findings(operation, tuple(preview_blocks),
        tuple(len(s.blocks) for s in spec.sections), bundle))
    return CandidateCheck(candidate_binding(value, raw), digest(raw),
        'DETERMINISTICALLY_REJECTED' if errors else 'PENDING_SEMANTIC_REVIEW',
        tuple(dict.fromkeys(errors)), tuple(views), tuple(
            f'{s.evidence_id} · v{s.evidence_version} · {s.source_label} · {s.source_locator} · SHA256 {s.content_sha256}\n{s.content}'
            for s in bundle.sources))


def effective_decisions(check, revision):
    """Old review cannot survive raw text, premises, source or context edits."""
    if revision is None or digest(revision.body_text) != check.raw_sha256 or check.errors:
        return {}
    return {d.claim_id: d for d in revision.candidate_decisions if d.binding_sha256 == check.binding_sha256}
