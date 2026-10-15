"""Prepare/check local next-request artifacts. No transport or live execution."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from foreign_trade_geo_agent.core import content_draft as cd
from foreign_trade_geo_agent.core.draft_selection_contract import canonical_json
from foreign_trade_geo_agent.workflows.draft_contract_v3_experiment import (
    build_model_prompt_v3_material, assemble_model_v3_output, run_offline_v3_experiment,
    _envelope,
)
from foreign_trade_geo_agent.workflows.content_draft import _parse_specification
from foreign_trade_geo_agent.core.draft_explanation_contract_v3 import decode_sidecar_v3, inspect_explanations_v3
from foreign_trade_geo_agent.core.draft_candidate_review import inspect_specification
from tests.test_seo_draft_v3_request_freeze import read_sources, source_context, check_boundary, PACKAGE_NAMES


def encoded(value):
    return canonical_json(value).encode('utf-8')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError('NEXT_ARTIFACT_CHANGED')
    else:
        with path.open('xb') as stream:
            stream.write(raw)


def build():
    _, _, projection, selection, value = source_context(read_sources())
    material = build_model_prompt_v3_material(projection)
    check_boundary(material, material['writer_projection'], selection, value)
    request = dict(model='deepseek-flash', temperature=0, thinking={'type': 'disabled'},
        response_format={'type': 'json_object'}, max_tokens=16384, messages=[
            dict(role='system', content=material['instructions']),
            dict(role='user', content=canonical_json(material))])
    raw = encoded(request)
    for text, max_chars, max_bytes in (
        (request['messages'][0]['content'], cd.MAX_SYSTEM_PROMPT_CHARS, cd.MAX_SYSTEM_PROMPT_BYTES),
        (request['messages'][1]['content'], cd.MAX_USER_MATERIAL_CHARS, cd.MAX_USER_MATERIAL_BYTES),
        (raw.decode(), cd.MAX_INPUT_ENVELOPE_CHARS, cd.MAX_INPUT_ENVELOPE_BYTES),
    ):
        assert len(text) <= max_chars and len(text.encode()) <= max_bytes
    package = HERE / 'next-frozen'
    results = HERE / 'next-results'
    assert not results.is_relative_to(package)
    inputs = {
        HERE / 'next-inputs/prompt.json': encoded(material),
        HERE / 'next-inputs/output-contract.json': encoded(material['response_contract']),
        package / 'request.json': raw,
        package / 'request-body.sha256': (sha(raw) + '  request.json\n').encode(),
        package / 'experiment-config.json': encoded(dict(state='FROZEN_NOT_AUTHORIZED',
            model_wire_version=material['model_wire_version'], semantic_approved=False,
            production_authorized=False, network_allowed=False, live_authorized=False,
            model='deepseek-flash', temperature=0, thinking='disabled', response_format='json_object',
            max_tokens=16384, timeout=60, retries=0, fallback_allowed=False, repair_allowed=False,
            redirects_allowed=False, selection_sha256=material['writer_projection']['selection_sha256'],
            snapshot_sha256=selection.evidence_snapshot_sha256, plan_sha256=selection.plan_sha256,
            result_directory=results.relative_to(ROOT).as_posix(),
            assembler='assemble_model_v3_output', raw_response_must_be_retained=True)),
    }
    references = [
        ROOT / 'docs/seo-draft-contract-v3-integration/selection-artifact.json',
        ROOT / 'docs/seo-draft-contract-v3-integration/synthetic-input.json',
        ROOT / 'docs/seo-draft-contract-v3-flash-preflight/manifest.json',
        ROOT / 'src/foreign_trade_geo_agent/workflows/draft_contract_v3_experiment.py',
        ROOT / 'src/foreign_trade_geo_agent/workflows/content_draft.py',
        ROOT / 'src/foreign_trade_geo_agent/core/draft_explanation_contract_v3.py',
        ROOT / 'src/foreign_trade_geo_agent/core/draft_candidate_review.py',
        ROOT / 'src/foreign_trade_geo_agent/core/content_draft.py',
        ROOT / 'src/foreign_trade_geo_agent/core/draft_selection_contract.py',
    ]
    manifest_inputs = {**{p: p.read_bytes() for p in references}, **inputs}
    manifest = encoded(dict(version='v3-model-null-output-hashes-1', state='FROZEN_NOT_AUTHORIZED',
        files=[dict(filename=p.relative_to(ROOT).as_posix(), sha256=sha(data), size=len(data))
               for p, data in sorted(manifest_inputs.items())],
        exclusions=['manifest.json', 'manifest.sha256', 'report.md', 'external next-results/']))
    inputs.update({package / 'manifest.json': manifest,
        package / 'manifest.sha256': (sha(manifest) + '  manifest.json\n').encode(),
        package / 'report.md': b'# Next v3 experiment inputs\n\nFROZEN_NOT_AUTHORIZED. No live request performed.\nOutput hashes use the explicit null model wire; validators remain unchanged.\nStore results in ../next-results/<unique-run-id>/, never inside this directory.\n'})
    for p, data in inputs.items():
        save(p, data)
    assert {p.name for p in package.iterdir()} == PACKAGE_NAMES
    for entry in json.loads(manifest)['files']:
        data = (ROOT / entry['filename']).read_bytes()
        assert sha(data) == entry['sha256'] and len(data) == entry['size']

    # Explicit synthetic positive path on the SAME frozen context, not model output.
    synthetic = json.loads((ROOT / 'docs/seo-draft-contract-v3-integration/synthetic-output.json').read_bytes())
    synthetic['sidecar_hash'] = None
    synthetic['v3_sidecar']['candidate_hash'] = None
    for a in synthetic['v3_sidecar']['explanations']:
        a['text_sha256'] = None
    model_wire = canonical_json(synthetic)
    assembled = assemble_model_v3_output(value, selection, model_wire,
        current_snapshot_sha256=selection.evidence_snapshot_sha256)
    body, candidate = _envelope(assembled)
    operation = value.change_plan_report.operations[0]
    spec = _parse_specification(candidate, expected_change_ref=operation.change_id, operation=operation)
    sidecar = decode_sidecar_v3(canonical_json(body['v3_sidecar']))
    contract = inspect_explanations_v3(sidecar, selection, candidate, spec, value,
        current_snapshot_sha256=selection.evidence_snapshot_sha256)
    native = inspect_specification(value, candidate, spec, current_snapshot_sha256=selection.evidence_snapshot_sha256)
    assert contract.status == 'PASS' and not native.errors
    replay = run_offline_v3_experiment(value, selection, assembled,
        current_snapshot_sha256=selection.evidence_snapshot_sha256)
    assert replay.accepted
    save(HERE / 'synthetic/model-wire.json', model_wire.encode())
    save(HERE / 'synthetic/assembled-envelope.json', assembled.encode())
    save(HERE / 'synthetic/result.json', encoded(dict(synthetic_only=True,
        real_model_pass=False, layer1='PASS', layer2='PASS', layer3=contract.status,
        layer4='PASS', state=replay.state, semantic_approved=False, production_authorized=False,
        sections=len(spec.sections), explanations=len(sidecar.explanations),
        stages=[asdict(s) for s in replay.stages])))
    summary = dict(state='FROZEN_NOT_AUTHORIZED', request_sha256=sha(raw), manifest_sha256=sha(manifest),
        request_bytes=len(raw), prompt_bytes=len(encoded(material)), system_chars=len(material['instructions']),
        exact_six_files=True, source_refs_verified=len(manifest_inputs), selected_boundary_pass=True,
        synthetic_layers_1_to_4='PASS', real_model_pass=False, api_calls=0,
        semantic_approved=False, production_authorized=False, results_outside_frozen=True)
    save(HERE / 'next-preflight.json', encoded(summary))
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    build()
