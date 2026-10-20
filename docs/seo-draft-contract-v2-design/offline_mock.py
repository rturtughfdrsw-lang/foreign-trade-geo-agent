"""Design-only checks layered on the unchanged native candidate validator.

This module is not imported by the application. Structural PASS never authorizes
semantic approval, finalization, provider calls, or delivery.
"""
from collections import Counter
from contextlib import contextmanager
import json
import re
from unittest.mock import patch

from build_mock import HERE, HISTORY, MATERIAL, encode, sha
from foreign_trade_geo_agent.core import content_draft as cd
from foreign_trade_geo_agent.storage.serialization import _decode
from foreign_trade_geo_agent.workflows.content_draft import inspect_candidate_output

EXPECTED_BUDGETS = dict(claim_hard=48, block_hard=24, claim_target=43, block_target=20,
                        direct_max=30, explanations=12, cta=1, transitions=0)
PARTS = ('buyer_implication', 'non_applicability', 'verification_action')
WORD = re.compile(r"\b[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*\b")


@contextmanager
def prohibit_network():
    attempts = []
    def deny(*args, **kwargs):
        attempts.append(True)
        raise AssertionError('OFFLINE_NETWORK_FORBIDDEN')
    with patch('socket.create_connection', deny), patch('socket.socket.connect', deny), \
            patch('socket.socket.connect_ex', deny), patch('socket.getaddrinfo', deny):
        yield attempts


def load():
    return (json.loads((HERE / 'contract-v2.json').read_bytes()),
            (HERE / 'mock-response.json').read_bytes(),
            json.loads((HERE / 'explanation-annotations.json').read_bytes()))


def inspect_native(raw):
    value = _decode(json.loads((HISTORY / 'native-input.json').read_bytes()), cd.ContentDraftInput)
    return inspect_candidate_output(value, raw.decode('utf-8'),
                                    current_snapshot_sha256=value.customer_evidence.snapshot_sha256)


def check(raw, plan, annotations):
    errors = []
    def fail(code):
        errors.append(code)
    material = json.loads(MATERIAL.read_bytes())
    native = json.loads((HISTORY / 'native-input.json').read_bytes())
    facts = {f['fact_ref']: f for s in material['customer_evidence']['sources'] for f in s['facts']}
    briefs = material['change']['new_resource']['section_briefs']
    if plan.get('budgets') != EXPECTED_BUDGETS:
        fail('PLAN_BUDGET_CONTRACT')
    if (plan.get('version') != 'draft-contract-v2-design' or plan.get('test_only') is not True
            or plan.get('production_authorized') is not False):
        fail('PLAN_MODE')
    if (plan.get('baseline_input_sha256') != sha((HISTORY / 'native-input.json').read_bytes())
            or plan.get('material_sha256') != sha(MATERIAL.read_bytes())
            or plan.get('snapshot_sha256') != native['customer_evidence']['snapshot_sha256']):
        fail('PLAN_INPUT_BINDING')
    if (annotations.get('candidate_sha256') != sha(raw)
            or annotations.get('contract_sha256') != sha(encode(plan))
            or annotations.get('snapshot_sha256') != plan.get('snapshot_sha256')
            or annotations.get('version') != plan.get('version')
            or annotations.get('test_only') is not True):
        fail('ANNOTATION_BINDING')
    try:
        inspection = inspect_native(raw)
        native_state = inspection.state
        native_errors = list(inspection.errors)
    except ValueError:
        native_state, native_errors = 'SCHEMA_REJECTED', ['NATIVE_SCHEMA_REJECTED']
    if native_state != 'PENDING_SEMANTIC_REVIEW':
        errors.extend(native_errors or ['NATIVE_REJECTED'])
    draft = json.loads(raw)['draft']
    sections = draft['sections']
    if len(plan['sections']) != len(briefs) or len(sections) != len(briefs):
        fail('SECTION_COUNT')
    counts, explanation_locations = Counter(), set()
    total_blocks = 0
    for si, (section, sp, brief) in enumerate(zip(sections, plan['sections'], briefs), 1):
        sid = f'S{si}'
        if (sp['section_id'] != sid or sp['heading'] != brief['heading']
                or section['outline_heading'] != brief['heading']
                or sp['reader_question'] != brief['reader_question']
                or sp['requirement_ids'] != brief['requirement_ids']
                or sp['required_sources'] != brief['supporting_evidence']
                or sp['limitation'] != brief['limitations']
                or sp['procurement_action'] != brief['procurement_action']):
            fail(sid + ':PLAN_SECTION_BINDING')
        required, optional, selected = (set(sp[k]) for k in
                                       ('required_facts', 'optional_facts', 'selected_facts'))
        for key in ('required_facts', 'optional_facts', 'selected_facts', 'required_direct_facts'):
            if len(sp[key]) != len(set(sp[key])):
                fail(sid + ':PLAN_DUPLICATE_FACT')
        if (not required or required & optional or not required <= selected
                or not selected <= required | optional or not set(sp['required_direct_facts']) <= required):
            fail(sid + ':PLAN_SELECTION')
        selected_requirements = set()
        for ref in required | optional | selected:
            if (ref not in facts or ref.split('.')[0] not in sp['required_sources']
                    or not set(facts[ref]['requirement_ids']) & set(sp['requirement_ids'])):
                fail(sid + ':PLAN_FACT_ROUTING')
            if ref in selected and ref in facts:
                selected_requirements.update(facts[ref]['requirement_ids'])
        if ({r.split('.')[0] for r in selected} != set(sp['required_sources'])
                or not set(sp['requirement_ids']) <= selected_requirements):
            fail(sid + ':PLAN_COVERAGE')
        if sp['explanation_count'] != 2 or sp['claim_max'] != sp['direct_max']+2+(si == 6):
            fail(sid + ':PLAN_RESERVATION')
        blocks = section['blocks']
        total_blocks += len(blocks)
        claims, used, direct = [], set(), set()
        section_counts = Counter()
        for bi, block in enumerate(blocks):
            for ci, claim in enumerate(block.get('claims', block.get('items', []))):
                claims.append(claim)
                refs = set(claim['customer_refs'])
                used.update(refs)
                counts[claim['claim_type']] += 1
                section_counts[claim['claim_type']] += 1
                if not refs <= selected:
                    fail(sid + ':FACT_NOT_SELECTED')
                if claim['claim_type'] == 'OBSERVED_PRODUCT_FACT':
                    direct.update(refs)
                if claim['claim_type'] == 'EVIDENCE_BASED_INTERPRETATION':
                    explanation_locations.add((sid, bi, ci))
                    p = claim.get('proposal', {})
                    if (p.get('procurement_question') != sp['reader_question']
                            or p.get('limitation') != sp['limitation']
                            or p.get('procurement_action') != sp['procurement_action']):
                        fail(sid + ':EXPLANATION_PROPOSAL_BINDING')
        if not required <= used or used != selected or not set(sp['required_direct_facts']) <= direct:
            fail(sid + ':SELECTED_COVERAGE')
        if {r.split('.')[0] for r in used} != set(sp['required_sources']):
            fail(sid + ':SOURCE_ROUTING')
        if (len(blocks) > sp['block_max'] or len(claims) > sp['claim_max']
                or section_counts['OBSERVED_PRODUCT_FACT'] > sp['direct_max']):
            fail(sid + ':SECTION_BUDGET')
        if section_counts['EVIDENCE_BASED_INTERPRETATION'] != sp['explanation_count']:
            fail(sid + ':EXPLANATION_RESERVATION')
    total_claims = sum(counts.values())
    if (total_claims > cd.MAX_CLAIMS_PER_DRAFT or total_blocks > cd.MAX_BLOCKS_PER_DRAFT
            or total_claims > EXPECTED_BUDGETS['claim_target'] or total_blocks > EXPECTED_BUDGETS['block_target']
            or counts['OBSERVED_PRODUCT_FACT'] > 30 or counts['EVIDENCE_BASED_INTERPRETATION'] != 12
            or counts['CALL_TO_ACTION'] != 1 or counts['EDITORIAL_TRANSITION'] != 0):
        fail('DESIGN_BUDGET')
    if (sum(s['block_max'] for s in plan['sections']) > 20
            or sum(len(s['required_direct_facts']) for s in plan['sections']) > 30):
        fail('PLAN_INFEASIBLE')
    located = set()
    for item in annotations.get('explanations', []):
        loc = (item.get('section_id'), item.get('block_index'), item.get('claim_index'))
        if loc in located or loc not in explanation_locations:
            fail('EXPLANATION_LOCATION')
            continue
        located.add(loc)
        sid, bi, ci = loc
        si = int(sid[1:])-1
        block = sections[si]['blocks'][bi]
        claim = block.get('claims', block.get('items', []))[ci]
        parts = [item.get(k, '') for k in PARTS]
        if (any(not isinstance(p, str) or p != ' '.join(p.split()) for p in parts)
                or any(len(WORD.findall(p)) < n for p, n in zip(parts, (20, 12, 20)))):
            fail(sid + ':EXPLANATION_PART_DEPTH')
        joined = ' '.join(parts)
        if joined != claim['text'] or item.get('text_sha256') != sha(claim['text'].encode()):
            fail(sid + ':EXPLANATION_BODY_BINDING')
        if not 60 <= len(WORD.findall(joined)) <= 160 or len(joined) > 1200:
            fail(sid + ':EXPLANATION_LENGTH')
        sp = plan['sections'][si]
        if (sp['limitation'] not in parts[1] or sp['procurement_action'] not in parts[2]):
            fail(sid + ':EXPLANATION_BOUNDARY_PLACEMENT')
    if located != explanation_locations:
        fail('EXPLANATION_ANNOTATIONS_INCOMPLETE')
    errors = list(dict.fromkeys(errors))
    return dict(design_status='PASS' if not errors else 'REJECTED', native_state=native_state,
        errors=errors, native_errors=native_errors, claims=total_claims, blocks=total_blocks,
        claim_types=dict(counts), explanation_count=len(explanation_locations),
        structure_only=True, semantic_review='HUMAN_REVIEW_REQUIRED', production_authorized=False)


def verify():
    with prohibit_network() as attempts:
        plan, raw, annotations = load()
        valid = check(raw, plan, annotations)
        original = (HISTORY / 'model-output.txt').read_bytes()
        old = inspect_native(original)
        assert sha(original) == '880c9ab66f4380fe34cabf6bf4aeacf8afe5b968049950931d0a6126f3bb2747'
        assert valid['design_status'] == 'PASS', valid['errors']
        assert old.state == 'DETERMINISTICALLY_REJECTED' and 'CLAIM_BUDGET' in old.errors
        response = json.loads(raw)
        routing = []
        for section, sp in zip(response['draft']['sections'], plan['sections']):
            used = {r for b in section['blocks'] for c in b['claims'] for r in c['customer_refs']}
            routing.append(dict(section_id=sp['section_id'], required_sources=sp['required_sources'],
                actual_sources=sorted({r.split('.')[0] for r in used}),
                actual_fact_refs=sorted(used), routing='PASS'))
    return dict(new_mock=valid, historical_frozen_v1=dict(sha256=sha(original),
        state=old.state, errors=list(old.errors), mutated=False),
        claims_hard_limit='PASS', section_routing='PASS', section_routing_details=routing,
        explanation_contract_structure='PASS',
        selected_unique_facts=len({r for s in plan['sections'] for r in s['selected_facts']}),
        network_attempts=len(attempts), real_api_calls=0, wordpress_calls=0,
        production_code_modified=False, production_gate_modified=False,
        finalized_drafts=0, human_signoff=False, commercial_status='NOT_READY')
