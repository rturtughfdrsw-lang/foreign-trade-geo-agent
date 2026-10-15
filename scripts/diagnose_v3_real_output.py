"""Read-only historical diagnosis. Structural views are never admission inputs.

Run with python -m scripts.diagnose_v3_real_output. Writes only to the new external
diagnosis directory; original response, frozen artifacts and validators stay intact.
"""
from collections import Counter
from dataclasses import fields, asdict
import json
from pathlib import Path
import re

from foreign_trade_geo_agent.core import content_draft as cd
from foreign_trade_geo_agent.core.draft_candidate_review import inspect_specification
from foreign_trade_geo_agent.core.draft_explanation_contract_v3 import (
    ExplanationAnnotationV3, ExplanationSidecarV3, OBJECTS, OWNERS, ACTIONS,
    decode_sidecar_v3, inspect_explanations_v3, DecisionRelationV3,
    EvidenceReferenceV3, VerificationRelationV3,
)
from foreign_trade_geo_agent.core.draft_selection_contract import canonical_json, text_digest
from foreign_trade_geo_agent.workflows.content_draft import _parse_specification
from foreign_trade_geo_agent.workflows.draft_contract_v3_experiment import _envelope, ENVELOPE_FIELDS
from tests.test_seo_draft_v3_request_freeze import read_sources, source_context, ROOT, DEST

ORIGINAL = ROOT / DEST / 'real-v3-experiment-2026-10-13'
OUT = ROOT / 'docs/seo-draft-v3-repair-2026-10-13'


def diagnose():
    _, _, _, selection, value = source_context(read_sources())
    raw = (ORIGINAL / 'model-output.txt').read_bytes()
    response = (ORIGINAL / 'response-body.bin').read_bytes()
    assert json.loads(response)['choices'][0]['message']['content'].encode() == raw
    b = json.loads(raw)
    findings, rows, sections = [], [], []

    def add(path, code, **detail):
        findings.append(dict(path=path, code=code, **detail))

    def keys(obj, expected, path):
        for key in sorted(set(obj) - set(expected)):
            add(path + '.' + key, 'EXTRA_FIELD')
        for key in sorted(set(expected) - set(obj)):
            add(path + '.' + key, 'MISSING_FIELD')

    def attempt(fn):
        try:
            fn()
            return dict(result='PASS')
        except ValueError as exc:
            return dict(result='FAIL', error=str(exc))

    layer1 = attempt(lambda: _envelope(raw.decode()))
    candidate = canonical_json(b['candidate'])
    op = value.change_plan_report.operations[0]
    layer2 = attempt(lambda: _parse_specification(candidate, expected_change_ref=op.change_id, operation=op))
    layer3 = attempt(lambda: decode_sidecar_v3(canonical_json(b['v3_sidecar'])))
    keys(b, ENVELOPE_FIELDS, '$')
    keys(b['candidate'], {'draft'}, '$.candidate')
    keys(b['candidate']['draft'], {'change_ref', 'draft_type', 'sections'}, '$.candidate.draft')
    side = b['v3_sidecar']
    keys(side, {f.name for f in fields(ExplanationSidecarV3)}, '$.v3_sidecar')
    for path, actual, expected in (
        ('$.sidecar_hash', b['sidecar_hash'], text_digest(canonical_json(side))),
        ('$.v3_sidecar.candidate_hash', side['candidate_hash'], text_digest(candidate)),
        ('$.v3_sidecar.selection_sha256', side['selection_sha256'], text_digest(canonical_json(asdict(selection)))),
        ('$.v3_sidecar.evidence_snapshot_sha256', side['evidence_snapshot_sha256'], selection.evidence_snapshot_sha256),
        ('$.v3_sidecar.plan_sha256', side['plan_sha256'], selection.plan_sha256),
    ):
        if actual != expected:
            add(path, 'HASH_MISMATCH', actual=actual, expected=expected)
    facts = {f.fact_ref: f.quote for s in value.customer_evidence.sources for f in s.facts}
    annotations = {a['claim_id']: (i, a) for i, a in enumerate(side['explanations'])}
    native_sections = []
    for si, (s, budget) in enumerate(zip(b['candidate']['draft']['sections'], selection.sections)):
        sp = f'$.candidate.draft.sections[{si}]'
        keys(s, {'outline_heading', 'blocks'}, sp)
        used = {r for c in s['claims'] for r in c['customer_refs']}
        direct = {r for c in s['claims'] if c['claim_type'] == 'OBSERVED_PRODUCT_FACT' for r in c['customer_refs']}
        missing = sorted(set(budget.required_direct_facts) - direct)
        if missing:
            add(sp + '.claims', 'MISSING_REQUIRED_DIRECT_FACTS', refs=missing)
        if used != set(budget.selected_facts):
            add(sp + '.claims', 'SECTION_ROUTING')
        if len(s['claims']) > budget.claim_budget:
            add(sp + '.claims', 'SECTION_CLAIM_BUDGET')
        sections.append(dict(section_id=budget.section_id, claims=len(s['claims']),
            claim_budget=budget.claim_budget, missing_direct_facts=missing,
            selected_set_matches=used == set(budget.selected_facts)))
        native_claims = []
        for ci, c in enumerate(s['claims']):
            cp = sp + f'.claims[{ci}]'
            start = len(findings)
            keys(c, {'text', 'claim_type', 'page_refs', 'source_refs', 'customer_refs', 'proposal'}, cp)
            if c['page_refs']:
                add(cp + '.page_refs', 'E_CLAIM_REQUIRES_EMPTY_PAGE_REFS')
            if c['source_refs']:
                add(cp + '.source_refs', 'E_CLAIM_REQUIRES_EMPTY_SOURCE_REFS')
                for ri, ref in enumerate(c['source_refs']):
                    if not re.fullmatch(r'S[1-9][0-9]*', ref):
                        add(cp + f'.source_refs[{ri}]', 'UNKNOWN_SOURCE_REFERENCE', actual=ref)
            if len(c['text']) > cd.MAX_INTERPRETATION_CHARS:
                add(cp + '.text', 'CLAIM_BUDGET', chars=len(c['text']))
            numeric_error = cd._validate_numeric_grounding(c['text'], '\n'.join(
                cd._normalized_text(facts[r]) for r in c['customer_refs']))
            if numeric_error:
                add(cp + '.text', numeric_error)
            # Independent check of the existing proposal numeric-context rule;
            # no proposal is invented just to reach this normally masked branch.
            numeric_sentences = []
            for sentence in re.split(r'(?<=[.!?])\s+', c['text']):
                quantities = [e for e in cd.extract_numeric_expressions(sentence)
                              if not re.fullmatch(r'[a-z][a-z0-9_-]*', e)]
                if quantities and not any(sentence in facts[r] for r in c['customer_refs']):
                    numeric_sentences.append(sentence)
            if numeric_sentences:
                add(cp + '.text', 'NUMERIC_CONTEXT_NOT_PRESERVED_IF_PROPOSAL_PRESENT', sentences=numeric_sentences)
            ai, a = annotations[c['claim_id']]
            ap = f'$.v3_sidecar.explanations[{ai}]'
            keys(a, {f.name for f in fields(ExplanationAnnotationV3)}, ap)
            keys(a['decision'], {'change', 'rationale'}, ap + '.decision')
            keys(a['verification'], {'action', 'recipient', 'next_decision', 'purpose'}, ap + '.verification')
            for key, val, allowed in (
                ('decision_object', a['decision_object'], OBJECTS),
                ('verification.next_decision', a['verification']['next_decision'], OBJECTS),
                ('verification.recipient', a['verification']['recipient'], OWNERS),
                ('verification_owner', a['verification_owner'], OWNERS),
                ('verification.action', a['verification']['action'], ACTIONS),
                ('boundary_type', a['boundary_type'], {'unknown', 'condition_change'}),
            ):
                if type(val) is not str or val not in allowed:
                    add(ap + '.' + key, 'ENUM_STRING_REQUIRED', actual=val)
            if a['text_sha256'] != text_digest(c['text']):
                add(ap + '.text_sha256', 'HASH_MISMATCH')
            refs_ok = (set(a['selected_fact_refs']) == set(c['customer_refs']) ==
                       {e['fact_ref'] for e in a['evidence_reference']})
            selected_ok = set(a['selected_fact_refs']) <= set(budget.selected_facts)
            quotes_ok = all(facts.get(e['fact_ref']) == e['source_quote'] for e in a['evidence_reference'])
            if not (refs_ok and selected_ok and quotes_ok):
                add(ap + '.evidence_reference', 'EVIDENCE_BINDING')
            # Use literal labels only to diagnose realization independently of
            # the enum type failure. This does not normalize the sidecar.
            label = a['decision_object'].get('label') if isinstance(a['decision_object'], dict) else OBJECTS.get(a['decision_object'])
            next_label = a['verification']['next_decision'].get('label') if isinstance(a['verification']['next_decision'], dict) else OBJECTS.get(a['verification']['next_decision'])
            if label not in OBJECTS.values():
                add(ap + '.decision_object.label', 'UNSUPPORTED_DISPLAY_LABEL', actual=label)
            if next_label not in OBJECTS.values():
                add(ap + '.verification.next_decision.label', 'UNSUPPORTED_DISPLAY_LABEL', actual=next_label)
            expected_parts = dict(
                buyer_implication=f"{a['evidence_basis']} Therefore, the buyer should {a['decision']['change']} for the {label}, because {a['decision']['rationale']}.",
                non_applicability=f"{a['boundary_condition']} {budget.required_limitation} The conclusion remains {'unresolved' if a['boundary_type']=='unknown' else 'conditional on the recorded setup'}.",
                verification_action=f"The {a['verification_owner']} should {a['verification']['action']} the {a['verification_artifact']} for the {a['verification']['recipient']} to decide the {next_label}: {a['verification']['purpose']}. {budget.verification_action}")
            for key, expected in expected_parts.items():
                if a[key] != expected:
                    add(ap + '.' + key, 'REALIZATION_MISMATCH', expected=expected)
            for key, val in [(k, a[k]) for k in ('evidence_basis', 'boundary_condition', 'verification_artifact')] + [
                ('decision.change', a['decision']['change']), ('decision.rationale', a['decision']['rationale']),
                ('verification.purpose', a['verification']['purpose'])]:
                if not isinstance(val, str) or not val.strip() or len(val) > 300 or val != ' '.join(val.split()):
                    add(ap + '.' + key, 'RELATION_TEXT', chars=len(val))
            for key in ('buyer_implication', 'non_applicability', 'verification_action'):
                if not a[key].strip() or len(a[key]) > 1200 or a[key] != ' '.join(a[key].split()):
                    add(ap + '.' + key, 'VISIBLE_TEXT')
            if c['text'] != ' '.join(a[k] for k in ('buyer_implication', 'non_applicability', 'verification_action')):
                add(ap, 'BODY_BINDING')
            rows.append(dict(claim_id=c['claim_id'], section_id=a['section_id'],
                claim_path=cp, annotation_path=ap, findings=findings[start:],
                refs_match=refs_ok, selected_only=selected_ok, exact_quotes=quotes_ok,
                numeric_context_issue=bool(numeric_sentences)))
            native_claims.append(cd.DraftClaimSpecification(c['text'], cd.DraftClaimType(c['claim_type']),
                tuple(c['page_refs']), tuple(c['source_refs']), tuple(c['customer_refs']), None))
        # Budget-bounded diagnostic grouping, never persisted as a candidate.
        # Original has no blocks, so its actual block layout is unknowable.
        native_sections.append(cd.NewResourceSectionSpecification(s['heading'], tuple(
            cd.ParagraphSpecification(cd.DraftBlockKind.PARAGRAPH, tuple(native_claims[i:i+4]))
            for i in range(0, len(native_claims), 4))))
    spec = cd.ContentDraftSpecification(op.change_id, cd.ContentDraftType.NEW_RESOURCE_DRAFT,
                                        sections=tuple(native_sections))
    native = inspect_specification(value, candidate, spec, current_snapshot_sha256=selection.evidence_snapshot_sha256)
    typed = []
    for original in side['explanations']:
        a = dict(original)
        a['selected_fact_refs'] = tuple(a['selected_fact_refs'])
        a['evidence_reference'] = tuple(EvidenceReferenceV3(**e) for e in a['evidence_reference'])
        a['decision'] = DecisionRelationV3(**a['decision'])
        a['verification'] = VerificationRelationV3(**a['verification'])
        typed.append(ExplanationAnnotationV3(**a))
    typed_side = ExplanationSidecarV3(**{**side, 'explanations': tuple(typed)})
    inspected = inspect_explanations_v3(typed_side, selection, candidate, spec, value,
                                      current_snapshot_sha256=selection.evidence_snapshot_sha256)
    return dict(scope='DIAGNOSTIC_ONLY_NOT_ADMISSION', output_sha256=text_digest(raw.decode()),
        response_sha256=__import__('hashlib').sha256(response).hexdigest(),
        official=dict(layer1=layer1, layer2='NOT_RUN', layer3='NOT_RUN', layer4='NOT_RUN', state='REJECTED'),
        isolated_layer2=layer2, isolated_layer3_codec=layer3,
        isolated_layer3_inspector=dict(result=inspected.status, errors=inspected.errors,
            note='Dataclass view preserves all original field values including invalid types and hashes; same diagnostic spec as Layer 4; not admission.'),
        isolated_layer4=dict(result='FAIL' if native.errors else 'PASS', errors=native.errors,
            note='Diagnostic spec only: input change_ref/type, original headings, groups of <=4 claims per paragraph; exact text/refs, proposal=None. Original block layout unknowable. No original parser/validator PASS or repaired candidate.'),
        sections=sections, explanations=rows, findings=findings,
        counts=dict(Counter(f['code'] for f in findings)),
        semantic_approved=False, production_authorized=False, finalizer_run=False)


if __name__ == '__main__':
    result = diagnose()
    OUT.mkdir(exist_ok=True)
    (OUT / 'diagnosis.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('official', 'isolated_layer2', 'isolated_layer3_codec', 'isolated_layer4', 'counts')}, indent=2))
