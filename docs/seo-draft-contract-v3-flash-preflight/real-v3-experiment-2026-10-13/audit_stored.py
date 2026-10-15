"""Post-rejection observations only; never repairs or invokes admission layers."""
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tests.test_seo_draft_v3_request_freeze import read_sources, source_context, sha
from foreign_trade_geo_agent.core.draft_explanation_contract_v3 import OBJECTS, OWNERS
from foreign_trade_geo_agent.adapters.retained_deepseek import save_bytes

OUT = Path(__file__).resolve().parent

def write(name, value):
    save_bytes(OUT / name, json.dumps(value, ensure_ascii=False, indent=2).encode('utf-8'))

def run():
    _, _, _, selection, value = source_context(read_sources())
    raw = (OUT / 'model-output.txt').read_bytes()
    body = json.loads(raw)
    facts = {f.fact_ref:f.quote for s in value.customer_evidence.sources for f in s.facts}
    annotations = body['v3_sidecar']['explanations']
    claims = {c['claim_id']:c for s in body['candidate']['draft']['sections'] for c in s['claims']}
    rows = []
    for a in annotations:
        budget = next(s for s in selection.sections if s.section_id == a['section_id'])
        c = claims[a['claim_id']]
        obj = a['decision_object']
        expected_boundary = f"{a['boundary_condition']} {budget.required_limitation} The conclusion remains {'unresolved' if a['boundary_type']=='unknown' else 'conditional on the recorded setup'}."
        rows.append(dict(claim=a['claim_id'], section=a['section_id'],
            selected_refs_only=all(r in budget.selected_facts for r in a['selected_fact_refs']),
            exact_evidence_quotes=all(facts.get(e['fact_ref']) == e['source_quote'] for e in a['evidence_reference']),
            evidence_ref_set_matches=set(a['selected_fact_refs']) == set(c['customer_refs']) == {e['fact_ref'] for e in a['evidence_reference']},
            decision_object_present='decision_object' in a,
            decision_object_valid=type(obj) is str and obj in OBJECTS,
            owner_enum_valid=a['verification_owner'] in OWNERS,
            recipient_enum_valid=a['verification']['recipient'] in OWNERS,
            artifact=a['verification_artifact'],
            artifact_external_existence_verified=False,
            boundary_type=a['boundary_type'], boundary_realization_matches=a['non_applicability']==expected_boundary,
            text_parts_match=c['text']==' '.join(a[k] for k in ('buyer_implication','non_applicability','verification_action')),
            text_hash_matches=a['text_sha256']==sha(c['text'].encode()), native_proposal_present='proposal' in c))
    write('explanation-audit.json', dict(scope='Read-only observations after Layer 1 rejection; not Layers 2-4 results or semantic approval',
        output_sha256=sha(raw), requested_chain_target=12, observed_chains=len(annotations),
        per_section=dict(Counter(a['section_id'] for a in annotations)),
        minimum_two_per_section_satisfied=True, fully_contract_conforming_chains=0,
        fully_conforming_basis='Every annotation has an invalid decision_object type and empty text_sha256',
        rows=rows, semantic_approved=False, production_authorized=False))
    write('failure-taxonomy.json', dict(
        A_contract_failure=dict(status='OBSERVED', findings=[
            'Layer 1: unexpected top-level type key; V3_EXPERIMENT_ENVELOPE_FIELDS.',
            'Read-only: draft contains title/sections rather than native change_ref/draft_type/sections; sections contain heading/claims rather than outline_heading/blocks.',
            'Read-only: all 19 interpretations omit required native proposal metadata and all 19 decision_object/next_decision values are objects rather than enum strings.',
            'Read-only: sidecar_hash, candidate_hash and all 19 text_sha256 values are empty.',
            'Read-only: 12 recipients use buyer and supplier outside the allowed enum; all 19 boundary realizations differ from the exact required template.',
            'Read-only: no OBSERVED_PRODUCT_FACT claims satisfy required direct-fact reservations.']),
        B_instruction_following_failure=dict(status='OBSERVED', findings=[
            'Did not preserve native schema/proposal metadata, hash requirements, enum representation, or exact visible templates.',
            'Produced 19 explanations rather than the requested 12-chain target; count alone is not a v3 failure because implementation reserves at least two per section.',
            'All 19 source quote groups exactly match selected evidence; no unselected fact reference observed.',
            'semantic_approved and production_authorized remained false.']),
        C_reasoning_quality_failure=dict(status='OBSERVED_CONCERNS_NOT_SEMANTIC_APPROVAL', findings=[
            'CL1 rationale attaches centered static-loading qualification jointly to travels and table loads; selected evidence attaches it to table loads, while travel requires separate fixture/tool clearance checks. Condition attribution is overbroad.',
            'CL3-CL4 make buyer review loaded-trial/torque records for supplier decision, but identify no owner to perform the trial or produce missing records; this does not establish a complete verification workflow.',
            'CL6, CL8 and CL10 discuss setup/measurement conditions yet every annotation chooses unknown and no condition_change; unresolved evidence and changed-condition applicability are not clearly distinguished.',
            'CL1-CL2 visible recipient says configuration review while structured recipient says supplier.',
            'All verification artifacts are proposed inputs/actions within synthetic evidence; no actual supplier, record existence, completed trial, or signed agreement was verified.',
            'Historical CL21 different coupon counts error was not reproduced: CL9 says three coupons per machine and CL10 says three consecutive coupons. No numeric magnitude reversal observed in this read-only comparison; this is not Native Validator PASS.']),
        D_parser_validator_issue=dict(status='NO_IMPLEMENTATION_DEFECT_ESTABLISHED', findings=[
            'Layer 1 rejects a genuinely extra key according to the unchanged exact envelope contract.',
            'Native parser, v3 contract inspector and Native Validator were not run after Layer 1 failure; cannot claim their pass/fail or diagnose a defect from this run.',
            'Frozen prompt retains OFFLINE synthetic hash_creator wording and does not embed the full native draft/block schema; this is a possible prompt-contract clarity limitation, not a demonstrated parser defect. No input was changed.']),
        semantic_approved=False, production_authorized=False))
    meta = json.loads((OUT/'reception.json').read_bytes())
    validation = json.loads((OUT/'validation-layers.json').read_bytes())
    write('execution-summary.json',dict(completion='REAL_V3_EXPERIMENT_COMPLETE',state=validation['state'],
        request_count=meta['request_count'], http_status=meta['http_status'], finish_reason=meta['finish_reason'],
        latency_seconds=meta['latency_seconds'], usage=meta['usage'], response_bytes=meta['response_bytes'],
        response_sha256=meta['response_sha256'], model_output_sha256=meta['model_text_sha256'],
        layers=validation['layers'], cost=dict(currency='USD',suggested_budget=0.05, actual_billed_usd=None,
        reason='Response contains token usage but no billed amount; no billing or pricing API request made. No unsupported cost estimate.'),
        retries=0,fallback=0,model_switches=0,repairs=0,second_request=False,
        semantic_approved=False,production_authorized=False,wordpress_calls=0,deployment=False,
        git_commit=False,git_push=False,stopped=True))
    assert (OUT/'model-output.txt').read_bytes() == raw
    print(json.dumps(dict(chains=len(rows),counts={k:sum(r[k] for r in rows) for k in (
        'selected_refs_only','exact_evidence_quotes','decision_object_valid','owner_enum_valid',
        'recipient_enum_valid','boundary_realization_matches','text_parts_match','text_hash_matches','native_proposal_present')},
        output_unchanged=True),indent=2))

if __name__ == '__main__':
    run()
