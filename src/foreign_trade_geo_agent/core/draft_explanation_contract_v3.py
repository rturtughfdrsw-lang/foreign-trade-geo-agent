"""Offline procurement relation prototype. PASS never means semantic approval.

No workflow, storage, adapter or I/O dependencies and no production wiring.
Explicit relations and controlled visible realization replace word-count scoring.
Free-text causal validity still requires human review; keywords cannot grant PASS.
"""
from collections import Counter
from dataclasses import asdict, dataclass, fields
import json
import re

from . import content_draft as cd
from .draft_candidate_review import inspect_specification
from .draft_selection_contract import (
    DraftSelectionContract, canonical_json, refs, require, selection_digest,
    text_digest, valid_hash, valid_text, validate_selection,
)

VERSION = 'seo-draft-explanation-v3-offline'
OBJECTS = {
    'machine_shortlist': 'machine shortlist', 'acceptance_test': 'acceptance test',
    'rfq_requirement': 'RFQ requirement', 'configuration_decision': 'configuration decision',
}
OWNERS = {'buyer', 'supplier', 'both parties'}
ACTIONS = {'provide', 'review', 'agree', 'test'}
MAX_SIDECAR = 300000
# Negative diagnostics only: never used as positive evidence of meaning.
FAILURE_LANGUAGE = re.compile(r'\b(?:failed|fails|failure|unsuitable|incapable|cannot accommodate)\b', re.I)
GENERIC_LANGUAGE = re.compile(r'\b(?:this is important|this should be considered)\b', re.I)


@dataclass(frozen=True, slots=True)
class EvidenceReferenceV3:
    fact_ref: str
    source_quote: str


@dataclass(frozen=True, slots=True)
class DecisionRelationV3:
    change: str
    rationale: str


@dataclass(frozen=True, slots=True)
class VerificationRelationV3:
    action: str
    recipient: str
    next_decision: str
    purpose: str


@dataclass(frozen=True, slots=True)
class ExplanationAnnotationV3:
    claim_id: str
    section_id: str
    selected_fact_refs: tuple[str, ...]
    text_sha256: str
    buyer_implication: str
    non_applicability: str
    verification_action: str
    evidence_reference: tuple[EvidenceReferenceV3, ...]
    evidence_basis: str
    decision_object: str
    decision: DecisionRelationV3
    boundary_type: str
    boundary_condition: str
    verification_owner: str
    verification_artifact: str
    verification: VerificationRelationV3


@dataclass(frozen=True, slots=True)
class ExplanationSidecarV3:
    contract_version: str
    selection_sha256: str
    evidence_snapshot_sha256: str
    plan_sha256: str
    candidate_hash: str
    explanations: tuple[ExplanationAnnotationV3, ...]


@dataclass(frozen=True, slots=True)
class ExplanationCheckV3:
    status: str
    state: str
    errors: tuple[str, ...]
    diagnostics: tuple[str, ...]

    @property
    def production_authorized(self) -> bool:
        return False

    @property
    def semantic_approved(self) -> bool:
        return False


def _text(value, maximum=300):
    return valid_text(value, maximum) and value == ' '.join(value.split())


def _shape(sidecar):
    require(type(sidecar) is ExplanationSidecarV3, 'V3_INPUT')
    require(sidecar.contract_version == VERSION, 'V3_VERSION')
    require(all(valid_hash(h) for h in (sidecar.selection_sha256,
        sidecar.evidence_snapshot_sha256, sidecar.plan_sha256, sidecar.candidate_hash)), 'V3_HASH_SHAPE')
    require(type(sidecar.explanations) is tuple and 1 <= len(sidecar.explanations) <= 48
        and all(type(a) is ExplanationAnnotationV3 for a in sidecar.explanations), 'V3_ANNOTATIONS')
    require(len({a.claim_id for a in sidecar.explanations}) == len(sidecar.explanations), 'V3_DUPLICATE_CLAIM')
    for a in sidecar.explanations:
        require(refs((a.claim_id,), r'CL[1-9][0-9]?') and refs((a.section_id,), r'S[1-9][0-9]?')
            and refs(a.selected_fact_refs, r'E[1-9][0-9]{0,2}\.F[0-9]{2}', 20)
            and bool(a.selected_fact_refs) and valid_hash(a.text_sha256), 'V3_ANNOTATION_SHAPE')
        require(all(_text(p, 1200) for p in (a.buyer_implication, a.non_applicability, a.verification_action)),
                'V3_VISIBLE_TEXT')
        require(type(a.evidence_reference) is tuple and 1 <= len(a.evidence_reference) <= 20
            and all(type(e) is EvidenceReferenceV3 and refs((e.fact_ref,), r'E[1-9][0-9]{0,2}\.F[0-9]{2}')
                and valid_text(e.source_quote, 1200) for e in a.evidence_reference)
            and len({e.fact_ref for e in a.evidence_reference}) == len(a.evidence_reference), 'V3_EVIDENCE_SHAPE')
        require(type(a.decision) is DecisionRelationV3 and type(a.verification) is VerificationRelationV3,
                'V3_RELATION_SHAPE')
        require(all(_text(p) for p in (a.evidence_basis, a.decision.change, a.decision.rationale,
            a.boundary_condition, a.verification_artifact, a.verification.purpose)), 'V3_RELATION_TEXT')
        require(type(a.decision_object) is str and a.decision_object in OBJECTS, 'V3_DECISION_OBJECT')
        require(type(a.boundary_type) is str and a.boundary_type in {'unknown', 'condition_change'}, 'V3_BOUNDARY_TYPE')
        require(type(a.verification_owner) is str and a.verification_owner in OWNERS
            and type(a.verification.recipient) is str and a.verification.recipient in OWNERS, 'V3_VERIFICATION_ROLE')
        require(type(a.verification.action) is str and a.verification.action in ACTIONS
            and type(a.verification.next_decision) is str and a.verification.next_decision in OBJECTS,
                'V3_VERIFICATION_RELATION')
    require(len(canonical_json(asdict(sidecar)).encode('utf-8')) <= MAX_SIDECAR, 'V3_SIDECAR_SIZE')


def render_parts(a: ExplanationAnnotationV3, section) -> dict[str, str]:
    """Controlled realization binds the proposed relations to reader-visible text.

    This is not an inference engine. Source quote relevance and slot semantics
    remain review obligations even when every relation is present.
    """
    status = 'unresolved' if a.boundary_type == 'unknown' else 'conditional on the recorded setup'
    return dict(
        buyer_implication=f'{a.evidence_basis} Therefore, the buyer should {a.decision.change} '
            f'for the {OBJECTS[a.decision_object]}, because {a.decision.rationale}.',
        non_applicability=f'{a.boundary_condition} {section.required_limitation} '
            f'The conclusion remains {status}.',
        verification_action=f'The {a.verification_owner} should {a.verification.action} the '
            f'{a.verification_artifact} for the {a.verification.recipient} to decide the '
            f'{OBJECTS[a.verification.next_decision]}: {a.verification.purpose}. {section.verification_action}')


def _spec_projection(spec):
    require(type(spec) is cd.ContentDraftSpecification and not spec.blocks and not spec.cells
        and spec.anchor_text is None and not spec.insertion_claims, 'V3_SPEC_BINDING')
    sections = []
    for section in spec.sections:
        blocks = []
        for block in section.blocks:
            key = 'claims' if type(block) is cd.ParagraphSpecification else 'items'
            require(type(block) in {cd.ParagraphSpecification, cd.BulletListSpecification}, 'V3_SPEC_BINDING')
            claims = []
            for c in getattr(block, key):
                claim = asdict(c)
                if c.proposal is None:
                    claim.pop('proposal')
                claims.append(claim)
            blocks.append(dict(kind=block.kind, **{key: claims}))
        sections.append(dict(outline_heading=section.outline_heading, blocks=blocks))
    return dict(draft=dict(change_ref=spec.change_ref, draft_type=spec.draft_type, sections=sections))


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'V3_DUPLICATE_KEY')
        result[key] = value
    return result


def _json(raw, maximum):
    require(type(raw) is str and len(raw) <= maximum and len(raw.encode('utf-8')) <= maximum, 'V3_JSON_SIZE')
    return json.loads(raw, object_pairs_hook=_strict_object,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('V3_JSON_NUMBER')))


def inspect_explanations_v3(sidecar, selection, raw, specification, value, *, current_snapshot_sha256):
    """Pure offline inspection; preserves native checks and section reservations.

    The caller supplies a native parsed specification. Exact JSON/spec equality
    independently binds it to raw, so passing a different parsed article fails.
    """
    errors, diagnostics = [], ['V3_SEMANTIC_REVIEW_REQUIRED']
    try:
        _shape(sidecar)
        require(type(selection) is DraftSelectionContract, 'V3_SELECTION_INPUT')
        validate_selection(selection, value, current_snapshot_sha256=current_snapshot_sha256)
        require(canonical_json(_json(raw, cd.MAX_RAW_OUTPUT_BYTES)) ==
                canonical_json(_spec_projection(specification)), 'V3_SPEC_BINDING')
        require(sidecar.candidate_hash == text_digest(raw)
            and sidecar.selection_sha256 == selection_digest(selection)
            and sidecar.evidence_snapshot_sha256 == selection.evidence_snapshot_sha256
            and sidecar.plan_sha256 == selection.plan_sha256, 'V3_HASH_BINDING')
        native = inspect_specification(value, raw, specification, current_snapshot_sha256=current_snapshot_sha256)
        # Native diagnostics are locally generated codes. Never forward source text.
        errors.extend('V3_NATIVE_' + re.sub('[^A-Z0-9_]', '_', e) for e in native.errors)
        require(len(specification.sections) == len(selection.sections), 'V3_SECTION_BINDING')
        expected, number = {}, 0
        for si, (section, budget) in enumerate(zip(specification.sections, selection.sections), 1):
            require(section.outline_heading == budget.heading, 'V3_SECTION_BINDING')
            claims = [c for b in section.blocks for c in (b.claims if type(b) is cd.ParagraphSpecification else b.items)]
            kinds = Counter(c.claim_type for c in claims)
            used = {r for c in claims for r in c.customer_refs}
            direct = {r for c in claims if c.claim_type is cd.DraftClaimType.OBSERVED_PRODUCT_FACT for r in c.customer_refs}
            require(used == set(budget.selected_facts) and set(budget.required_direct_facts) <= direct
                and {r.split('.')[0] for r in used} == set(budget.required_sources), 'V3_SECTION_ROUTING')
            require(len(claims) <= budget.claim_budget and len(section.blocks) <= budget.block_budget
                and kinds[cd.DraftClaimType.OBSERVED_PRODUCT_FACT] <= budget.direct_fact_budget
                and kinds[cd.DraftClaimType.EVIDENCE_BASED_INTERPRETATION] >= budget.explanation_budget
                and kinds[cd.DraftClaimType.CALL_TO_ACTION] <= budget.cta_budget, 'V3_SECTION_RESERVATION')
            for claim in claims:
                number += 1
                if claim.claim_type is cd.DraftClaimType.EVIDENCE_BASED_INTERPRETATION:
                    expected[f'CL{number}'] = (f'S{si}', claim, budget)
        require({a.claim_id for a in sidecar.explanations} == set(expected), 'V3_CLAIM_BINDING')
        facts = {f.fact_ref: f.quote for s in value.customer_evidence.sources for f in s.facts}
        for a in sidecar.explanations:
            sid, claim, budget = expected[a.claim_id]
            require(a.section_id == sid, 'V3_CLAIM_BINDING')
            require(set(a.selected_fact_refs) <= set(budget.selected_facts), 'V3_FACT_NOT_SELECTED')
            require(set(a.selected_fact_refs) == set(claim.customer_refs) ==
                {e.fact_ref for e in a.evidence_reference}, 'V3_PREMISE_BINDING')
            require(all(facts.get(e.fact_ref) == e.source_quote for e in a.evidence_reference), 'V3_EVIDENCE_BINDING')
            parts = render_parts(a, budget)
            require(a.buyer_implication == parts['buyer_implication'], 'V3_DECISION_REALIZATION')
            require(a.non_applicability == parts['non_applicability'], 'V3_BOUNDARY_REALIZATION')
            require(a.verification_action == parts['verification_action'], 'V3_VERIFICATION_REALIZATION')
            body = ' '.join((a.buyer_implication, a.non_applicability, a.verification_action))
            require(len(body) <= 1200 and body == claim.text and a.text_sha256 == text_digest(body), 'V3_BODY_BINDING')
            if GENERIC_LANGUAGE.search(a.buyer_implication):
                errors.append('V3_GENERIC_DECISION_DIAGNOSTIC')
            if a.boundary_type == 'unknown' and FAILURE_LANGUAGE.search(a.boundary_condition):
                errors.append('V3_UNKNOWN_FALSE_DIAGNOSTIC')
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError, OverflowError, UnicodeError) as exc:
        code = str(exc) if type(exc) is ValueError else ''
        errors.append(code if re.fullmatch(r'(?:V3_|SELECTION_)[A-Z0-9_]{1,90}', code) else 'V3_INVALID_INPUT')
    return ExplanationCheckV3('FAIL' if errors else 'PASS',
        'REJECTED' if errors else 'PENDING_SEMANTIC_REVIEW', tuple(dict.fromkeys(errors)), tuple(diagnostics))


def _record(value, cls):
    require(type(value) is dict and set(value) == {f.name for f in fields(cls)}, 'V3_CODEC_FIELDS')
    return dict(value)


def decode_sidecar_v3(raw: str) -> ExplanationSidecarV3:
    """Strict in-memory codec; no file or provider dependencies."""
    try:
        body = _record(_json(raw, MAX_SIDECAR), ExplanationSidecarV3)
        require(type(body['explanations']) is list and 1 <= len(body['explanations']) <= 48, 'V3_ANNOTATIONS')
        annotations = []
        for item in body['explanations']:
            a = _record(item, ExplanationAnnotationV3)
            require(type(a['selected_fact_refs']) is list and len(a['selected_fact_refs']) <= 20
                and type(a['evidence_reference']) is list and len(a['evidence_reference']) <= 20, 'V3_CODEC_LIST')
            a['selected_fact_refs'] = tuple(a['selected_fact_refs'])
            a['evidence_reference'] = tuple(EvidenceReferenceV3(**_record(e, EvidenceReferenceV3)) for e in a['evidence_reference'])
            a['decision'] = DecisionRelationV3(**_record(a['decision'], DecisionRelationV3))
            a['verification'] = VerificationRelationV3(**_record(a['verification'], VerificationRelationV3))
            annotations.append(ExplanationAnnotationV3(**a))
        body['explanations'] = tuple(annotations)
        sidecar = ExplanationSidecarV3(**body)
        _shape(sidecar)
        return sidecar
    except (ValueError, TypeError, KeyError, RecursionError, OverflowError, UnicodeError):
        raise ValueError('V3_SIDECAR_INVALID') from None


def encode_sidecar_v3(sidecar: ExplanationSidecarV3) -> str:
    _shape(sidecar)
    return canonical_json(asdict(sidecar))
