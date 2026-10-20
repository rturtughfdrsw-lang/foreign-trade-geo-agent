"""Stored-byte offline assembly. No Writer, Gate, persistence or delivery path."""
from dataclasses import dataclass
import json
import re

from foreign_trade_geo_agent.core import minimal_writer_wire as mw
from foreign_trade_geo_agent.core.content_draft import MAX_CLAIMS_PER_BLOCK
from foreign_trade_geo_agent.core.draft_candidate_review import inspect_specification
from foreign_trade_geo_agent.core.draft_selection_contract import canonical_json, require, text_digest
from foreign_trade_geo_agent.core.minimal_writer_wire import (
    decode_wire, encode_wire, decode_bindings, encode_bindings,
)
from .content_draft import _parse_specification


@dataclass(frozen=True, slots=True)
class MinimalExperimentResult:
    minimal_wire: str
    native_parser: str
    native_validator: str
    errors: tuple[str, ...]
    candidate_json: str = ''
    bindings_json: str = ''
    candidate_hash: str = ''
    sidecar_hash: str = ''
    refused_slots: tuple[str, ...] = ()
    semantic_review: str = 'PENDING'
    # Every returned candidate is for inspection only, including rejected candidates.
    review_risks: tuple[str, ...] = (
        'Premise relevance and factual relationships require human comparison with the bound source quotes.',
        'Distinct goal text does not prove distinct purchasing value.',
        'Assumptions, hidden contradictions, suitability and verification responsibility require human review.',
    )

    @property
    def ready_for_review(self):
        return (self.minimal_wire, self.native_parser, self.native_validator) == ('PASS', 'PASS', 'PASS') and not self.errors

    @property
    def semantic_approved(self):
        return False

    @property
    def production_authorized(self):
        return False


def _local_error(exc):
    code = str(exc) if type(exc) is ValueError else ''
    return code if re.fullmatch(r'[A-Z][A-Z0-9_]{0,95}', code) else 'MW_INVALID_INPUT'


def _assemble(value, selection, manifest, wire):
    answers = {a.slot_id: a for a in wire.slots}
    sources = {f.fact_ref: (s, f) for s in value.customer_evidence.sources for f in s.facts}
    sections, bindings, number = [], [], 0
    for section in selection.sections:
        claims = []
        slots = tuple(s for s in manifest.slots if s.section_id == section.section_id)
        used = set()
        for slot in slots:
            proposal = None
            if slot.kind == 'direct_fact':
                references = slot.allowed_fact_refs
                text = sources[references[0]][1].quote
                kind = 'OBSERVED_PRODUCT_FACT'
            elif slot.kind == 'cta':
                references, text, kind = (), slot.plan_text, 'CALL_TO_ACTION'
            else:
                answer = answers[slot.slot_id]
                references, text, kind = answer.premise_refs, mw.answer_text(answer), 'EVIDENCE_BASED_INTERPRETATION'
                # Native question remains the approved parent question; subquestion stays in Manifest.
                proposal = dict(procurement_question=section.question, reasoning=answer.buyer_implication,
                    assumptions=answer.assumptions, limitation=answer.boundary_condition,
                    procurement_action=answer.verification_action)
            used.update(references)
            claim = dict(text=text, claim_type=kind, page_refs=[], source_refs=[], customer_refs=list(references))
            if proposal is not None:
                claim['proposal'] = proposal
            claims.append(claim)
            number += 1
            evidence = []
            for ref in references:
                source, fact = sources[ref]
                evidence.append(mw.SourceQuote(ref, fact.quote, source.evidence_version,
                    source.content_sha256, source.source_locator, fact.start, fact.end))
            bindings.append(mw.SlotBinding(slot.slot_id, slot.section_id, slot.kind, f'CL{number}',
                text, text_digest(text), tuple(evidence)))
        # Actual used refs, not allowed refs, must cover the frozen section selection.
        require(used == set(section.selected_facts), 'MW_ACTUAL_SELECTED_COVERAGE')
        blocks = [dict(kind='PARAGRAPH', claims=claims[i:i+MAX_CLAIMS_PER_BLOCK])
                  for i in range(0, len(claims), MAX_CLAIMS_PER_BLOCK)]
        sections.append(dict(outline_heading=section.heading, blocks=blocks))
    candidate = canonical_json(dict(draft=dict(change_ref=value.change_plan_report.operations[0].change_id,
        draft_type='NEW_RESOURCE_DRAFT', sections=sections)))
    side = mw.ExplanationBindings(mw.BINDING_VERSION, wire.request_id, mw.manifest_digest(manifest),
        manifest.selection_sha256, manifest.plan_sha256, manifest.evidence_sha256, manifest.snapshot_sha256,
        text_digest(encode_wire(wire)), text_digest(candidate), tuple(bindings))
    return candidate, encode_bindings(side)


def inspect_native_candidate(value, candidate_json, *, current_snapshot_sha256):
    """Preserve original parser error tokens and original Candidate Validator findings."""
    op = value.change_plan_report.operations[0]
    try:
        spec = _parse_specification(candidate_json, expected_change_ref=op.change_id, operation=op)
    except ValueError as exc:
        return 'FAIL', 'NOT_RUN', (str(exc),)
    try:
        native = inspect_specification(value, candidate_json, spec,
                                        current_snapshot_sha256=current_snapshot_sha256)
    except ValueError as exc:
        return 'PASS', 'FAIL', (str(exc),)
    return 'PASS', 'FAIL' if native.errors else 'PASS', native.errors


def run_minimal_experiment(value, selection, manifest, model_output: str, *, current_snapshot_sha256):
    """No generation, repair, human decisions or admitted DraftItem creation."""
    try:
        mw.validate_manifest(manifest, value, selection, current_snapshot_sha256=current_snapshot_sha256)
        wire = decode_wire(model_output)
        refused = mw.validate_wire(wire, manifest, selection)
        if refused:
            return MinimalExperimentResult('FAIL', 'NOT_RUN', 'NOT_RUN', ('MW_INSUFFICIENT_EVIDENCE',),
                                           refused_slots=refused)
        candidate, bindings = _assemble(value, selection, manifest, wire)
    except (ValueError, TypeError, KeyError, AttributeError, IndexError, RecursionError, OverflowError, UnicodeError) as exc:
        return MinimalExperimentResult('FAIL', 'NOT_RUN', 'NOT_RUN', (_local_error(exc),))
    parser, validator, errors = inspect_native_candidate(value, candidate,
        current_snapshot_sha256=current_snapshot_sha256)
    return MinimalExperimentResult('PASS', parser, validator, errors, candidate, bindings,
                                    text_digest(candidate), text_digest(bindings))


def verify_assembled(value, selection, manifest, model_output, candidate_json, bindings_json,
                     sidecar_hash, *, current_snapshot_sha256):
    """Rebuild from frozen inputs; even recomputed tampered hashes grant no authority."""
    side = decode_bindings(bindings_json)
    require(text_digest(bindings_json) == sidecar_hash, 'MW_SIDECAR_HASH')
    require(side.candidate_hash == text_digest(candidate_json), 'MW_CANDIDATE_HASH')
    result = run_minimal_experiment(value, selection, manifest, model_output,
                                     current_snapshot_sha256=current_snapshot_sha256)
    require(result.ready_for_review, result.errors[0] if result.errors else 'MW_NOT_REVIEWABLE')
    require(candidate_json == result.candidate_json and bindings_json == result.bindings_json, 'MW_ASSEMBLY_BINDING')
    return result


def render_review(result: MinimalExperimentResult) -> str:
    """Convenience review copy from the SAME bound texts, never a second model body."""
    require(bool(result.candidate_json) and bool(result.bindings_json), 'MW_NO_CANDIDATE')
    side = decode_bindings(result.bindings_json)
    candidate = json.loads(result.candidate_json)
    lines = ['# TEST ONLY — Semantic Review PENDING',
             f'Minimal Wire {result.minimal_wire}; Native Parser {result.native_parser}; Native Validator {result.native_validator}.']
    lines.extend('- ' + r for r in result.review_risks)
    for i, section in enumerate(candidate['draft']['sections'], 1):
        lines.append('\n## ' + section['outline_heading'])
        for binding in (b for b in side.bindings if b.section_id == f'S{i}'):
            lines.append(f'\n[{binding.claim_id} / {binding.slot_id}] {binding.text}')
            if binding.kind == 'explanation':
                lines.append('\nSource comparison (human relevance review required):')
                for q in binding.evidence:
                    lines.append(f'- {q.fact_ref} v{q.source_version} [{q.start}:{q.end}] '
                                 f'{q.source_locator} SHA256 {q.content_sha256}: {q.source_quote}')
    return '\n'.join(lines) + '\n'
