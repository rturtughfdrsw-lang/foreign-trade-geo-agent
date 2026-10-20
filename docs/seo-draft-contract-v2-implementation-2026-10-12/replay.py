"""Read historical synthetic bytes, export V2 audit artifacts, replay offline."""
from dataclasses import asdict, replace
import json
import os
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path[:0] = [str(HERE / 'network_guard'), str(ROOT)]
os.environ['DRAFT_V2_NETWORK_LOG'] = str(HERE / 'replay-blocked-network.log')
import sitecustomize  # noqa: E402

from tests.draft_v2_fixtures import fixture, explanation_fixture, HISTORY
from foreign_trade_geo_agent.core.draft_selection_contract import text_digest, canonical_json
from foreign_trade_geo_agent.storage.draft_selection_contract import (
    encode_selection_artifact, decode_selection_artifact,
    encode_explanation_contract, decode_explanation_contract,
)
from foreign_trade_geo_agent.workflows.draft_contract_v2 import build_offline_writer_material, inspect_offline_candidate
from foreign_trade_geo_agent.workflows.content_draft import inspect_candidate_output


def save_once(name, raw):
    path = HERE / name
    data = raw.encode('utf-8')
    if path.exists():
        assert path.read_bytes() == data, 'EXISTING_ARTIFACT_DIFFERS'
        return
    with path.open('xb') as stream:
        stream.write(data)


value, selection = fixture()
raw, sidecar = explanation_fixture(selection)
selection_raw = encode_selection_artifact(selection)
sidecar_raw = encode_explanation_contract(sidecar)
selection = decode_selection_artifact(selection_raw)
sidecar = decode_explanation_contract(sidecar_raw)
snapshot = value.customer_evidence.snapshot_sha256
material = build_offline_writer_material(selection, value, current_snapshot_sha256=snapshot)
mock = inspect_offline_candidate(value, raw, selection, sidecar, current_snapshot_sha256=snapshot)
frozen_raw = (HISTORY / 'model-output.txt').read_bytes().decode('utf-8')
frozen = inspect_candidate_output(value, frozen_raw, current_snapshot_sha256=snapshot)
assert text_digest(frozen_raw) == '880c9ab66f4380fe34cabf6bf4aeacf8afe5b968049950931d0a6126f3bb2747'
assert frozen.state == 'DETERMINISTICALLY_REJECTED' and 'CLAIM_BUDGET' in frozen.errors
assert mock.state == 'PENDING_SEMANTIC_REVIEW' and not mock.errors
assert (mock.claims, mock.blocks) == (38, 20)
assert mock.selection_valid and mock.routing_valid and mock.explanation_structure_valid

negative_cases = {}
for name in ('49_claims', '25_blocks', 'illegal_fact', 'missing_required_direct', 'cross_section_source',
             'explanation_unselected_fact', 'candidate_hash_mismatch', 'plan_hash_mismatch'):
    body = json.loads(raw)
    contract, annotations = selection, sidecar
    if name == '49_claims':
        left = 11
        for section in body['draft']['sections']:
            for block in section['blocks']:
                while len(block['claims']) < 4 and left:
                    block['claims'].append(dict(block['claims'][0]))
                    left -= 1
        assert left == 0
    elif name == '25_blocks':
        body['draft']['sections'][0]['blocks'].extend([body['draft']['sections'][0]['blocks'][-1]] * 5)
    elif name == 'illegal_fact':
        body['draft']['sections'][0]['blocks'][0]['claims'][0]['customer_refs'] = ['E9.F99']
    elif name == 'missing_required_direct':
        body['draft']['sections'][0]['blocks'][0]['claims'].pop(0)
    elif name == 'cross_section_source':
        body['draft']['sections'][1]['blocks'][0]['claims'][0]['customer_refs'] = ['E5.F03']
    elif name == 'explanation_unselected_fact':
        body['draft']['sections'][0]['blocks'][2]['claims'][0]['customer_refs'].append('E2.F02')
    elif name == 'plan_hash_mismatch':
        contract = replace(selection, plan_sha256='0'*64)
    candidate = json.dumps(body)
    annotations = replace(sidecar, candidate_sha256='0'*64 if name == 'candidate_hash_mismatch' else text_digest(candidate))
    result = inspect_offline_candidate(value, candidate, contract, annotations, current_snapshot_sha256=snapshot)
    assert result.state == 'DETERMINISTICALLY_REJECTED', name
    negative_cases[name] = asdict(result)

result = dict(status='OFFLINE_SELECTION_CONTRACT_READY', mock=asdict(mock),
    frozen_v1=dict(sha256=text_digest(frozen_raw), state=frozen.state, errors=list(frozen.errors)),
    negative_cases=negative_cases, real_api_calls=0, real_wordpress_calls=0,
    production_gate_modified=False, production_authorized=False, semantic_approved=False,
    selected_unique_facts=len({r for s in selection.sections for r in s.selected_facts}),
    next_live_experiment='NOT_AUTHORIZED')
save_once('selection-artifact.json', selection_raw)
save_once('explanation-sidecar.json', sidecar_raw)
save_once('writer-material.json', canonical_json(material))
save_once('replay.json', json.dumps(result, ensure_ascii=False, indent=2))
print(json.dumps(dict(status=result['status'], claims=mock.claims, blocks=mock.blocks,
    candidate_state=mock.state, negative_cases=len(negative_cases), real_api_calls=0, real_wordpress_calls=0)))
