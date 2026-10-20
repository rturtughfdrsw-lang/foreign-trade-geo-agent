"""Create-only local synthetic integration package; no live request capability."""
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))

from foreign_trade_geo_agent.core.draft_explanation_contract_v3 import VERSION, encode_sidecar_v3
from foreign_trade_geo_agent.core.draft_selection_contract import canonical_json, selection_digest, text_digest
from foreign_trade_geo_agent.storage.draft_selection_contract import encode_selection_artifact, decode_selection_artifact
from foreign_trade_geo_agent.storage.serialization import _encode
from foreign_trade_geo_agent.workflows.content_draft import inspect_candidate_output
from foreign_trade_geo_agent.workflows.draft_contract_v3_experiment import run_offline_v3_experiment
from tests.draft_explanation_v3_fixtures import fixture_v3, replay_original
from tests.draft_v2_fixtures import HISTORY


def package_files():
    value, selection, candidate, sidecar = fixture_v3()
    artifact = encode_selection_artifact(selection)
    selection = decode_selection_artifact(artifact)
    sidecar_raw = encode_sidecar_v3(sidecar)
    envelope = canonical_json(dict(contract_version=VERSION, candidate=json.loads(candidate),
        v3_sidecar=json.loads(sidecar_raw), sidecar_hash=text_digest(sidecar_raw),
        semantic_approved=False, production_authorized=False))
    result = run_offline_v3_experiment(value, selection, envelope,
        current_snapshot_sha256=value.customer_evidence.snapshot_sha256)
    if not result.accepted or result.state != 'PENDING_SEMANTIC_REVIEW':
        raise ValueError('OFFLINE_V3_SYNTHETIC_REJECTED')
    stages = {stage.name: stage for stage in result.stages}
    config = dict(contract_version=VERSION, state='OFFLINE_ONLY',
        selection_hash=selection_digest(selection), snapshot_hash=selection.evidence_snapshot_sha256,
        plan_hash=selection.plan_sha256, candidate_hash=text_digest(candidate),
        sidecar_hash=text_digest(sidecar_raw), envelope_hash=text_digest(envelope),
        semantic_approved=False, production_authorized=False, human_review_required=True,
        synthetic_only=True, runtime_registered=False, network_allowed=False,
        real_api_calls=0, deepseek_requests=0, real_wordpress_calls=0,
        candidate_hash_scope='SHA256 canonical native candidate UTF-8 JSON, excluding envelope and sidecar',
        sidecar_hash_scope='SHA256 canonical complete sidecar UTF-8 JSON',
        selected_fact_count=len({r for s in selection.sections for r in s.selected_facts}),
        sections=len(selection.sections), explanation_chains=len(sidecar.explanations))
    input_data = dict(state='OFFLINE_ONLY', synthetic_only=True, native_input=_encode(value),
        selection_artifact=json.loads(artifact), current_snapshot_sha256=value.customer_evidence.snapshot_sha256,
        fixture_origin='tests.draft_explanation_v3_fixtures.fixture_v3; historical synthetic inputs read-only',
        semantic_approved=False, production_authorized=False)
    frozen = (HISTORY / 'model-output.txt').read_bytes()
    frozen_text = frozen.decode('utf-8')
    native_v1 = inspect_candidate_output(value, frozen_text,
        current_snapshot_sha256=value.customer_evidence.snapshot_sha256)
    rejected_v1 = run_offline_v3_experiment(value, selection, frozen_text,
        current_snapshot_sha256=value.customer_evidence.snapshot_sha256)
    v2 = replay_original()
    if native_v1.state != 'DETERMINISTICALLY_REJECTED' or rejected_v1.accepted or v2['state'] != 'REJECTED':
        raise ValueError('HISTORICAL_REJECTION_CHANGED')
    replay = dict(original_v2=v2, frozen_v1=dict(native_state=native_v1.state,
        native_errors=native_v1.errors, integration_state=rejected_v1.state,
        integration_errors=rejected_v1.errors, source_sha256_before=text_digest(frozen_text),
        source_sha256_after=text_digest((HISTORY/'model-output.txt').read_bytes().decode('utf-8')),
        repaired=False, api_calls=0))
    files = {
        'experiment-config.json': canonical_json(config), 'selection-artifact.json': artifact,
        'synthetic-input.json': canonical_json(input_data), 'synthetic-output.json': envelope,
        'synthetic-candidate.json': candidate, 'v3-sidecar.json': sidecar_raw,
        'writer-projection.json': stages['writer-projection'].payload_json,
        'prompt-v3-material.json': stages['prompt-v3-material'].payload_json,
        'v3-contract-result.json': stages['v3-contract-result'].payload_json,
        'native-validation-result.json': stages['native-validation-result'].payload_json,
        'pipeline-result.json': canonical_json(dict(state=result.state, errors=result.errors,
            accepted_for_semantic_review=result.accepted, semantic_approved=False,
            production_authorized=False, human_review_required=True, real_api_calls=0)),
        'replay.json': canonical_json(replay),
    }
    entries = []
    for number, stage in enumerate(result.stages, 1):
        name = f'stages/{number:02}-{stage.name}.json'
        files[name] = canonical_json(dict(step=stage.name, state=stage.state,
            payload=json.loads(stage.payload_json)))
        entries.append(dict(filename=name, sha256=text_digest(files[name]), state=stage.state))
    files['stage-index.json'] = canonical_json(entries)
    article = ['# Synthetic offline v3 article', '', 'Human semantic review required.', '']
    for section in json.loads(candidate)['draft']['sections']:
        article += ['## ' + section['outline_heading'], '']
        for block in section['blocks']:
            for claim in block.get('claims', block.get('items', [])):
                article += [claim['text'], '']
    files['synthetic-article.md'] = '\n'.join(article)
    return files


def write_package(directory):
    """Preflight all destinations; conflicting existing artifacts are never replaced."""
    directory = Path(directory)
    files = package_files()
    for name, raw in files.items():
        path = directory / name
        if path.is_symlink() or (path.exists() and path.read_bytes() != raw.encode('utf-8')):
            raise ValueError('OFFLINE_V3_EXISTING_ARTIFACT_CHANGED')
    for name, raw in files.items():
        path = directory / name
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('xb') as stream:
                stream.write(raw.encode('utf-8'))
    return dict(state='PENDING_SEMANTIC_REVIEW', files=len(files), real_api_calls=0,
        semantic_approved=False, production_authorized=False)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=HERE)
    args = parser.parse_args()
    print(json.dumps(write_package(args.output_dir), indent=2))
