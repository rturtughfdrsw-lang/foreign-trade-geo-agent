"""Generate local synthetic review artifacts; never requests or delivery payloads."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from foreign_trade_geo_agent.core.draft_explanation_contract_v3 import (
    decode_sidecar_v3, encode_sidecar_v3, inspect_explanations_v3,
)
from tests.draft_explanation_v3_fixtures import fixture_v3, parse, replay_original, LIVE


def write(name, value):
    raw = value if type(value) is str else json.dumps(value, ensure_ascii=False, indent=2)+'\n'
    (HERE/name).write_text(raw, encoding='utf-8')


def preservation():
    baseline = json.loads((HERE/'baseline-sha256.json').read_text(encoding='utf-8'))
    changed = []
    for name, expected in baseline.items():
        path = ROOT/name
        actual = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        if actual != expected:
            changed.append(dict(path=name, before=expected, after=actual))
    write('preservation.json', dict(preserved_files=len(baseline), changed_files=changed,
        existing_production_files_changed=any(c['path'].startswith('src/') for c in changed)))
    if changed:
        raise SystemExit('BLOCKED: preserved file changed; inspect preservation.json')


def main():
    preservation()
    value, selection, raw, sidecar = fixture_v3()
    check = inspect_explanations_v3(sidecar, selection, raw, parse(value, raw), value,
        current_snapshot_sha256=value.customer_evidence.snapshot_sha256)
    if check.status != 'PASS' or check.state != 'PENDING_SEMANTIC_REVIEW':
        raise SystemExit('BLOCKED: synthetic chain rejected')
    write('synthetic-candidate.json', raw)
    write('explanation-sidecar-v3.json', encode_sidecar_v3(sidecar))
    if decode_sidecar_v3((HERE/'explanation-sidecar-v3.json').read_text(encoding='utf-8')) != sidecar:
        raise SystemExit('BLOCKED: sidecar roundtrip')
    write('synthetic-check.json', dict(asdict(check), semantic_approved=check.semantic_approved,
        production_authorized=check.production_authorized, test_only=True, api_calls=0))
    article = ['# SYNTHETIC / TEST ONLY — procurement review example',
        '', 'PENDING_SEMANTIC_REVIEW. No human approval or production authority.', '']
    number = 0
    for section in json.loads(raw)['draft']['sections']:
        article += ['## '+section['outline_heading'], '']
        for block in section['blocks']:
            for claim in block.get('claims', block.get('items', [])):
                number += 1
                article += [f"[CL{number} / {claim['claim_type']}]", '', claim['text'], '']
    write('synthetic-article.md', '\n'.join(article))
    replay = replay_original()
    # No conversion, fake v3 annotations, ID repair or prose edits for the old output.
    try:
        decode_sidecar_v3((LIVE/'model-output.json').read_text(encoding='utf-8'))
    except ValueError as exc:
        replay.update(v3_wire_state='REJECTED', v3_wire_error=str(exc),
            v3_wire_reason='Original v2 envelope contains no v3 relation sidecar; no migration or repair attempted.')
    else:
        raise SystemExit('BLOCKED: v2 envelope accepted as v3')
    write('replay.json', replay)
    preservation()
    names = ('audit.md', 'design.md', 'prompt-v3-proposal.md', 'synthetic-candidate.json',
        'explanation-sidecar-v3.json', 'synthetic-check.json', 'synthetic-article.md', 'replay.json')
    write('artifact-sha256.json', {n: hashlib.sha256((HERE/n).read_bytes()).hexdigest() for n in names})
    print(json.dumps(dict(synthetic=check.state, historical=replay['state'], api_calls=0,
        preserved_files=json.loads((HERE/'preservation.json').read_text())['preserved_files'])))


if __name__ == '__main__':
    main()
