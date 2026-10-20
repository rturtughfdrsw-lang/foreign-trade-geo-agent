"""Versioned explanation annotations: visible structure, never semantic approval."""
from dataclasses import dataclass
import re

from .content_draft import ContentDraftSpecification, DraftClaimType, ParagraphSpecification
from .draft_selection_contract import (
    DraftSelectionContract, refs, require, selection_digest, text_digest, valid_hash, valid_text,
)

WORD = re.compile(r"\b[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*\b")


@dataclass(frozen=True, slots=True)
class ExplanationAnnotation:
    explanation_claim_id: str
    section_id: str
    selected_fact_refs: tuple[str, ...]
    text_sha256: str
    buyer_implication: str
    non_applicability: str
    verification_action: str

    def __post_init__(self):
        require(refs((self.explanation_claim_id,), r'CL[1-9][0-9]?')
            and refs((self.section_id,), r'S[1-9][0-9]?')
            and refs(self.selected_fact_refs, r'E[1-9][0-9]{0,2}\.F[0-9]{2}', 20)
            and bool(self.selected_fact_refs) and valid_hash(self.text_sha256), 'EXPLANATION_ANNOTATION_INVALID')
        parts = (self.buyer_implication, self.non_applicability, self.verification_action)
        require(all(valid_text(p) and p == ' '.join(p.split()) for p in parts), 'EXPLANATION_PART_INVALID')
        # These are bounded structural proxies for the English design profile,
        # not judgments of purchasing value, causal validity or applicability.
        require(all(len(WORD.findall(p)) >= n for p, n in zip(parts, (20, 12, 20))), 'EXPLANATION_PART_DEPTH')
        body = ' '.join(parts)
        require(60 <= len(WORD.findall(body)) <= 160 and len(body) <= 1200, 'EXPLANATION_LENGTH')


@dataclass(frozen=True, slots=True)
class ExplanationContract:
    contract_version: str
    selection_sha256: str
    evidence_snapshot_sha256: str
    plan_sha256: str
    candidate_sha256: str
    explanations: tuple[ExplanationAnnotation, ...]

    def __post_init__(self):
        require(type(self.contract_version) is str and self.contract_version == 'seo-draft-explanation-v2',
                'EXPLANATION_VERSION')
        require(all(valid_hash(h) for h in (self.selection_sha256, self.evidence_snapshot_sha256,
            self.plan_sha256, self.candidate_sha256)), 'EXPLANATION_HASH_INVALID')
        require(type(self.explanations) is tuple and len(self.explanations) <= 48
            and all(type(a) is ExplanationAnnotation for a in self.explanations)
            and len({a.explanation_claim_id for a in self.explanations}) == len(self.explanations),
            'EXPLANATION_ANNOTATIONS_INVALID')


def validate_explanations(sidecar: ExplanationContract, selection: DraftSelectionContract,
                          raw: str, specification: ContentDraftSpecification) -> None:
    """Validate against the native specification parsed from raw by the caller.

This pure domain check never parses provider JSON or admits a DraftItem.
Caller must use the native parser for the exact candidate bytes being bound.
"""
    require(type(sidecar) is ExplanationContract and type(selection) is DraftSelectionContract
            and type(raw) is str and type(specification) is ContentDraftSpecification, 'EXPLANATION_INPUT')
    require(sidecar.candidate_sha256 == text_digest(raw)
        and sidecar.selection_sha256 == selection_digest(selection)
        and sidecar.evidence_snapshot_sha256 == selection.evidence_snapshot_sha256
        and sidecar.plan_sha256 == selection.plan_sha256, 'EXPLANATION_HASH_BINDING')
    expected, number = {}, 0
    for si, section in enumerate(specification.sections, 1):
        for block in section.blocks:
            for claim in block.claims if isinstance(block, ParagraphSpecification) else block.items:
                number += 1
                if claim.claim_type is DraftClaimType.EVIDENCE_BASED_INTERPRETATION:
                    expected[f'CL{number}'] = (f'S{si}', claim)
    sections = {s.section_id: s for s in selection.sections}
    for annotation in sidecar.explanations:
        require(annotation.explanation_claim_id in expected, 'EXPLANATION_CLAIM_BINDING')
        sid, claim = expected[annotation.explanation_claim_id]
        require(annotation.section_id == sid and sid in sections, 'EXPLANATION_CLAIM_BINDING')
        section = sections[sid]
        require(set(annotation.selected_fact_refs) <= set(section.selected_facts), 'EXPLANATION_FACT_NOT_SELECTED')
        require(set(annotation.selected_fact_refs) == set(claim.customer_refs), 'EXPLANATION_PREMISE_BINDING')
        body = ' '.join((annotation.buyer_implication, annotation.non_applicability, annotation.verification_action))
        require(body == claim.text and annotation.text_sha256 == text_digest(claim.text), 'EXPLANATION_BODY_BINDING')
        require(section.required_limitation in annotation.non_applicability
            and section.verification_action in annotation.verification_action, 'EXPLANATION_BOUNDARY_PLACEMENT')
    require({a.explanation_claim_id for a in sidecar.explanations} == set(expected), 'EXPLANATION_COVERAGE')
