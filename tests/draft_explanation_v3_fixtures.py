"""Synthetic-only, read-only historical inputs plus new procurement chains."""
from dataclasses import replace
import json
from pathlib import Path

from foreign_trade_geo_agent.core.draft_explanation_contract_v3 import (
    VERSION, DecisionRelationV3, EvidenceReferenceV3, ExplanationAnnotationV3,
    ExplanationSidecarV3, VerificationRelationV3, render_parts,
)
from foreign_trade_geo_agent.core.draft_selection_contract import canonical_json, selection_digest, text_digest
from foreign_trade_geo_agent.workflows.content_draft import _parse_specification
from tests.draft_v2_fixtures import fixture, explanation_fixture

ROOT = Path(__file__).resolve().parents[1]
LIVE = ROOT / 'docs/seo-draft-v2-flash-quality-live-2026-10-12'

# basis, decision object, proposed change, causal rationale, boundary condition,
# artifact, purpose. Each row is a separate reviewable relation, not keyword score.
CHAINS = (
    ('The supplied fixture record is tied to a particular envelope and load.', 'machine_shortlist',
     'retain only conditional candidates for the supplied fixture',
     'the nominal machine limits screen the setup without establishing operating clearance',
     'Clearance and dynamic-load checks are not available.', 'fixture layout and clearance review',
     'whether the intended setup can proceed to a representative trial'),
    ('Nominal travel and centered static load describe separate screening conditions.', 'configuration_decision',
     'request separate access and operating-load checks',
     'a nominal envelope match does not resolve off-center loading or tool access',
     'Changed fixture orientation requires a fresh access and load review.', 'access and operating-load review',
     'which unresolved operating checks must precede configuration confirmation'),
    ('The spindle records describe unloaded bench conditions.', 'acceptance_test',
     'require a representative loaded cutting trial',
     'an unloaded rating does not measure cutting behavior under the intended operation',
     'The intended material and tooling have no matched loaded result.', 'matched loaded trial record',
     'whether the recorded test represents the intended material and tooling'),
    ('The motor information is nameplate documentation.', 'configuration_decision',
     'separate the nameplate record from loaded measurements',
     'a motor rating is not measured cutting power or an application ranking',
     'A changed motor configuration requires renewed checking.', 'configuration and torque record',
     'whether loaded measurements support the proposed motor configuration'),
    ('The supplied application record concerns the stated material and drawing.', 'machine_shortlist',
     'scope a representative part trial before application selection',
     'the recorded material and geometry limit which application the trial can represent',
     'Different material or geometry falls outside the recorded trial.', 'representative part trial plan',
     'which material and geometry differences the new trial must resolve'),
    ('The drawing trial timings exclude loading and use a small sample.', 'rfq_requirement',
     'define the complete production cycle before comparing alternatives',
     'excluded operating steps prevent bench timings from settling the purchasing cycle target',
     'A complete production cycle has not been demonstrated.', 'complete cycle boundary record',
     'which loading and operating steps the RFQ cycle must include'),
    ('The measured observation and proposed criterion share a drawing context.', 'acceptance_test',
     'agree a measurement decision rule before accepting the observation',
     'a recorded value and a proposed limit do not themselves define disposition',
     'The measurement decision rule has not been agreed.', 'measurement method and decision rule',
     'how the result will be assessed against the proposed criterion'),
    ('The supplied measurement record concerns an outer-width feature.', 'acceptance_test',
     'specify records for each intended critical feature',
     'an outer-width observation does not settle bore position or surface finish',
     'Different features need an agreed representation and measurement basis.', 'critical feature measurement plan',
     'which additional features need representative measurement before acceptance'),
    ('The proposed enquiry fields describe inputs for supplier review.', 'rfq_requirement',
     'resolve the intended operating inputs before defining purchasing criteria',
     'the supplier needs a scoped drawing and cycle boundary to evaluate the request',
     'The production cycle criteria remain unagreed.', 'scoped RFQ input register',
     'which operating inputs require agreement before the purchase enquiry'),
    ('The proposed acceptance sequence separates approval, recording and disposition.', 'acceptance_test',
     'record the responsibilities for correction and renewed testing',
     'an observed result needs an agreed disposition process before release',
     'A changed test drawing requires the acceptance arrangement to be revisited.', 'acceptance responsibility register',
     'who records measurements and how correction leads to renewed testing'),
    ('The proposed delivery and training terms depend on a signed configuration.', 'configuration_decision',
     'check options and training scope before relying on the proposed schedule',
     'a changed configuration can alter delivery scope and require separate agreement',
     'Options or training requirements outside the base scope change the proposal.', 'configuration and training scope register',
     'which options and training items need separate confirmation'),
    ('The proposed support response and warranty carry conditions and exclusions.', 'rfq_requirement',
     'request written commercial scope rather than assume restoration commitments',
     'an initial response proposal does not promise restoration and exclusions affect coverage',
     'Final commercial commitments remain unsigned.', 'support calendar and warranty scope record',
     'which response and coverage terms require written agreement'),
)


def parse(value, raw):
    op = value.change_plan_report.operations[0]
    return _parse_specification(raw, expected_change_ref=op.change_id, operation=op)


def fixture_v3():
    value, selection = fixture()
    old_raw, _ = explanation_fixture(selection)
    body = json.loads(old_raw)
    facts = {f.fact_ref:f.quote for s in value.customer_evidence.sources for f in s.facts}
    annotations, number = [], 0
    for si, section in enumerate(body['draft']['sections']):
        for block in section['blocks']:
            for claim in block.get('claims', block.get('items', [])):
                number += 1
                if claim['claim_type'] != 'EVIDENCE_BASED_INTERPRETATION':
                    continue
                basis, obj, change, rationale, boundary, artifact, purpose = CHAINS[len(annotations)]
                a = ExplanationAnnotationV3(f'CL{number}', f'S{si+1}', tuple(claim['customer_refs']),
                    '0'*64, '', '', '', tuple(EvidenceReferenceV3(r, facts[r]) for r in claim['customer_refs']),
                    basis, obj, DecisionRelationV3(change, rationale),
                    'unknown' if len(annotations) % 2 == 0 or len(annotations) in {5, 11} else 'condition_change',
                    boundary, 'supplier', artifact, VerificationRelationV3('provide', 'buyer', obj, purpose))
                a = replace(a, **render_parts(a, selection.sections[si]))
                text = ' '.join((a.buyer_implication, a.non_applicability, a.verification_action))
                a = replace(a, text_sha256=text_digest(text))
                claim['text'] = text
                # Keep native proposal fields and fixed limitation/action unchanged.
                annotations.append(a)
    raw = canonical_json(body)
    return value, selection, raw, ExplanationSidecarV3(VERSION, selection_digest(selection),
        selection.evidence_snapshot_sha256, selection.plan_sha256, text_digest(raw), tuple(annotations))


def rebind(raw, sidecar, changed):
    body = json.loads(raw)
    number = 0
    text = ' '.join((changed.buyer_implication, changed.non_applicability, changed.verification_action))
    for section in body['draft']['sections']:
        for block in section['blocks']:
            for claim in block.get('claims', block.get('items', [])):
                number += 1
                if f'CL{number}' == changed.claim_id:
                    claim['text'] = text
    raw = canonical_json(body)
    changed = replace(changed, text_sha256=text_digest(text))
    return raw, replace(sidecar, candidate_hash=text_digest(raw), explanations=tuple(
        changed if a.claim_id == changed.claim_id else a for a in sidecar.explanations))


def replay_original():
    from scripts.prepare_seo_draft_v2_flash_preflight import load_inputs, parse_experiment_response
    original = (LIVE / 'model-output.json').read_bytes()
    before = text_digest(original.decode('utf-8'))
    value, selection = load_inputs()
    try:
        parse_experiment_response(original.decode('utf-8'), value, selection)
    except ValueError as exc:
        error = str(exc)
    else:
        raise AssertionError('Historical parser unexpectedly accepted original bytes')
    return dict(state='REJECTED', original_parser_error=error,
        source_sha256_before=before, source_sha256_after=text_digest((LIVE/'model-output.json').read_text(encoding='utf-8')),
        validator='NOT_RUN', finalizer='NOT_RUN', repaired=False, api_calls=0)
