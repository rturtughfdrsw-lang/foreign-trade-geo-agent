"""Read-only model-output evaluation. No transport, repair, or admission."""
from dataclasses import asdict
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tests.test_seo_draft_v3_request_freeze import read_sources, source_context, sha, strict_json
from foreign_trade_geo_agent.core.draft_selection_contract import canonical_json, text_digest
from foreign_trade_geo_agent.core.draft_explanation_contract_v3 import decode_sidecar_v3, inspect_explanations_v3
from foreign_trade_geo_agent.core.draft_candidate_review import inspect_specification
from foreign_trade_geo_agent.workflows.content_draft import _parse_specification
from foreign_trade_geo_agent.workflows.draft_contract_v3_experiment import _envelope, _error_code, _native_code, _v3_code
from foreign_trade_geo_agent.adapters.retained_deepseek import save_bytes

OUT = Path(__file__).resolve().parent

def write(name, value):
    save_bytes(OUT / name, json.dumps(value, ensure_ascii=False, indent=2).encode('utf-8'))

def run():
    old, prompt, projection, selection, value = source_context(read_sources())
    meta = strict_json((OUT / 'reception.json').read_bytes())
    layers = []
    body = candidate = spec = None
    output_path = OUT / 'model-output.txt'
    output = output_path.read_bytes().decode('utf-8') if output_path.exists() else None
    try:
        if not meta.get('reception_success') or output is None:
            raise ValueError('RESPONSE_NOT_COMPLETE')
        body, candidate = _envelope(output)
        layers.append(dict(layer=1, name='JSON envelope parse', result='PASS', errors=[]))
    except Exception as exc:
        layers.append(dict(layer=1, name='JSON envelope parse', result='FAIL', errors=[_error_code(exc)]))
    if candidate is not None:
        try:
            operation = value.change_plan_report.operations[0]
            spec = _parse_specification(candidate, expected_change_ref=operation.change_id, operation=operation)
            layers.append(dict(layer=2, name='native candidate parser', result='PASS', errors=[]))
        except Exception as exc:
            layers.append(dict(layer=2, name='native candidate parser', result='FAIL', errors=[_error_code(exc)]))
    else:
        layers.append(dict(layer=2, name='native candidate parser', result='NOT_RUN', reason='Layer 1 failed'))
    if spec is not None:
        errors = []
        sidecar_raw = canonical_json(body['v3_sidecar'])
        if body['sidecar_hash'] != text_digest(sidecar_raw):
            errors.append('V3_EXPERIMENT_SIDECAR_HASH')
        try:
            sidecar = decode_sidecar_v3(sidecar_raw)
            result = inspect_explanations_v3(sidecar, selection, candidate, spec, value,
                current_snapshot_sha256=selection.evidence_snapshot_sha256)
            errors.extend(_v3_code(e) for e in result.errors)
            diagnostics = list(result.diagnostics)
        except Exception as exc:
            errors.append(_error_code(exc))
            diagnostics = []
        layers.append(dict(layer=3, name='Explanation Contract v3', result='FAIL' if errors else 'PASS',
            errors=errors, diagnostics=diagnostics,
            implementation_note='Unmodified v3 inspector internally reuses native checks after shape/hash checks'))
        try:
            native = inspect_specification(value, candidate, spec,
                current_snapshot_sha256=selection.evidence_snapshot_sha256)
            errors = [_native_code(e) for e in native.errors]
            layers.append(dict(layer=4, name='Native Validator', result='FAIL' if errors else 'PASS', errors=errors))
            write('native-claim-checks.json', [asdict(c) for c in native.claims])
        except Exception as exc:
            layers.append(dict(layer=4, name='Native Validator', result='FAIL', errors=[_error_code(exc)]))
    else:
        for number, name in ((3, 'Explanation Contract v3'), (4, 'Native Validator')):
            layers.append(dict(layer=number, name=name, result='NOT_RUN', reason='No parsed native specification'))
    state = 'PENDING_SEMANTIC_REVIEW' if all(l['result'] == 'PASS' for l in layers) else 'REJECTED'
    layers.append(dict(layer=5, name='Review state', state=state, semantic_approved=False, production_authorized=False))
    result = dict(state=state, layers=layers, model_output_sha256=sha(output_path.read_bytes()) if output_path.exists() else None,
        semantic_approved=False, production_authorized=False, finalizer_run=False, output_modified=False)
    write('validation-layers.json', result)
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    run()
