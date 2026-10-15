"""Owner-authorized exact repaired-v3 TEST experiment; default is offline preflight.

Uses existing one-shot transport/retention and fixed TEST-only SQLite ledger.
Never regenerates frozen inputs. No retry, repair, fallback, or production path.
"""
import asyncio
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
import httpx
from scripts.local_env import load_api_keys
from tests.test_seo_draft_v3_request_freeze import (
    read_sources, source_context, strict_json, sha, require, PACKAGE_NAMES,
    check_boundary, selection_digest, plan_digest, evidence_digest,
)
from foreign_trade_geo_agent.adapters.retained_deepseek import (
    OneShotTransport, receive_candidate, restrict_directory, save_bytes, contains_secret,
)
from foreign_trade_geo_agent.storage.web_experiment import WebExperimentLedger
from foreign_trade_geo_agent.core import content_draft as cd
from foreign_trade_geo_agent.core.draft_selection_contract import canonical_json
from foreign_trade_geo_agent.workflows.draft_contract_v3_experiment import (
    build_model_prompt_v3_material, assemble_model_v3_output,
)

OUT = Path(__file__).resolve().parent
BASE = OUT.parent.parent
PACKAGE = BASE / 'next-frozen'
REQUEST_HASH = 'be6b56286855a884ef9cdb69b25892d210ee0577f479651bbbd4cd740a1c81b9'
MANIFEST_HASH = '1145fcfa8196b601a72e12e809e5f112ac75e595d14c7519f6aa9874019cae78'
PERMIT = 'WEB-TEST-REPAIRED-V3-' + REQUEST_HASH
LEDGER = WebExperimentLedger(Path(os.environ['LOCALAPPDATA']) /
    'foreign-trade-geo-agent/web-experiment/permits.sqlite3')

def write(name, value):
    save_bytes(OUT / name, json.dumps(value, ensure_ascii=False, indent=2).encode('utf-8'))

def history_fingerprint():
    baseline = strict_json((BASE / 'preservation-before.json').read_bytes())
    require(all(sha((ROOT / p).read_bytes()) == digest for p, digest in baseline.items()),
        'HISTORICAL_EVIDENCE_CHANGED')
    return baseline

def ledger_rows():
    if not LEDGER.path.exists():
        return []
    with sqlite3.connect('file:' + LEDGER.path.as_posix() + '?mode=ro', uri=True) as db:
        return db.execute('SELECT permit,bundle,request,claimed FROM permits WHERE request=? OR bundle=? OR permit=?',
            (REQUEST_HASH, MANIFEST_HASH, PERMIT)).fetchall()

def preflight():
    raw = (PACKAGE / 'request.json').read_bytes()
    manifest = (PACKAGE / 'manifest.json').read_bytes()
    require(sha(raw) == REQUEST_HASH, 'REQUEST_HASH')
    require(sha(manifest) == MANIFEST_HASH, 'MANIFEST_HASH')
    require({p.name for p in PACKAGE.iterdir()} == PACKAGE_NAMES, 'PACKAGE_FILE_SET')
    require(all(p.is_file() for p in PACKAGE.iterdir()), 'PACKAGE_FILE_TYPE')
    require(not OUT.resolve().is_relative_to(PACKAGE.resolve()), 'RESULT_DIRECTORY')
    for filename, digest in [('manifest', MANIFEST_HASH), ('request-body', REQUEST_HASH)]:
        target = 'manifest.json' if filename == 'manifest' else 'request.json'
        require((PACKAGE / (filename + '.sha256')).read_bytes() ==
            (digest + '  ' + target + '\n').encode(), 'HASH_ANCHOR')
    entries = strict_json(manifest)['files']
    for e in entries:
        content = (ROOT / e['filename']).read_bytes()
        require(len(content) == e['size'] and sha(content) == e['sha256'], 'BOUND_FILE_HASH')
    _, _, projection, selection, value = source_context(read_sources())
    material = build_model_prompt_v3_material(projection)
    prompt_bytes = (BASE / 'next-inputs/prompt.json').read_bytes()
    require(canonical_json(material).encode() == prompt_bytes, 'PROMPT_SOURCE_DRIFT')
    require(canonical_json(material['response_contract']).encode() ==
        (BASE / 'next-inputs/output-contract.json').read_bytes(), 'CONTRACT_DRIFT')
    check_boundary(material, material['writer_projection'], selection, value)
    request = strict_json(raw)
    require({k:v for k,v in request.items() if k != 'messages'} == dict(model='deepseek-flash',
        temperature=0, thinking={'type':'disabled'}, response_format={'type':'json_object'}, max_tokens=16384),
        'PARAMETERS')
    require(request['messages'] == [dict(role='system', content=material['instructions']),
        dict(role='user', content=prompt_bytes.decode())], 'PROMPT_BYTES')
    config = strict_json((PACKAGE / 'experiment-config.json').read_bytes())
    require(config['timeout'] == 60 and config['retries'] == 0 and
        all(config[k] is False for k in ['fallback_allowed','repair_allowed','redirects_allowed',
            'production_authorized','semantic_approved','network_allowed','live_authorized']), 'CONFIG')
    require(config['assembler'] == assemble_model_v3_output.__name__ and
        config['model_wire_version'] == material['model_wire_version'] == 'v3-model-null-output-hashes-1', 'ASSEMBLER')
    for k, digest in [('selection',selection_digest(selection)), ('snapshot',selection.evidence_snapshot_sha256),
                      ('plan',plan_digest(value))]:
        require(config[k + '_sha256'] == digest, 'CONTEXT_HASH')
    require(config['result_directory'] == OUT.parent.relative_to(ROOT).as_posix(), 'RESULT_BINDING')
    require(not ledger_rows(), 'AUTHORIZATION_ALREADY_ISSUED_OR_CONSUMED')
    require(not any(p.name in {'started.json','reception.json','response-body.bin','permit-consumed.json'}
        for p in OUT.parent.rglob('*')), 'PRIOR_ATTEMPT_NO_RETRY')
    history = history_fingerprint()
    # Conservative planning scenario: one token per serialized request byte plus
    # 2048 framing tokens, all cache misses, full output, peak rates. Not a tokenizer proof.
    input_scenario = len(raw) + 2048
    cost = (input_scenario * 0.3 + 16384 * 1.2) / 1_000_000
    require(cost <= 0.05, 'BUDGET_EXCEEDED')
    return raw, value, selection, dict(result='PASS', request_sha256=sha(raw), manifest_sha256=sha(manifest),
        manifest_entries_checked=len(entries), strict_six_files=sorted(PACKAGE_NAMES),
        selection_sha256=selection_digest(selection), snapshot_sha256=selection.evidence_snapshot_sha256,
        plan_sha256=plan_digest(value), evidence_sha256=evidence_digest(value.customer_evidence),
        prompt_sha256=sha(prompt_bytes), request_bytes=len(raw), sources_bound=True, selected_boundary_pass=True,
        historical_files_unchanged=len(history), frozen_fingerprint={p.name:sha(p.read_bytes()) for p in PACKAGE.iterdir()},
        results_outside_frozen=True, assembler=assemble_model_v3_output.__name__,
        permit_previously_issued=False, prior_attempt_found=False, authorization='Current owner chat, exact new request/manifest only',
        parameters={k:v for k,v in request.items() if k != 'messages'}, timeout=60, retries=0, fallback=0,
        budget=dict(usd=0.05, input_scenario_tokens=input_scenario, output_max_tokens=16384,
            cache='all miss', peak_usd_per_million=dict(input_miss=0.3,input_hit=0.006,output=1.2),
            conservative_planning_usd=round(cost,8), hard_cap=False, tokenizer_bound_proven=False),
        official_sources=['https://api-docs.deepseek.com/quick_start/pricing/',
            'https://api-docs.deepseek.com/api/create-chat-completion/',
            'https://api-docs.deepseek.com/guides/thinking_mode/'],
        semantic_approved=False, production_authorized=False)

async def retention_selftest(value, raw):
    # No credential loading; complete and interrupted mocked streams retained.
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp); restrict_directory(directory)
        save_bytes(directory / 'probe.bin', b'bounded durable write')
        model = (BASE / 'synthetic/model-wire.json').read_text(encoding='utf-8')
        body = json.dumps(dict(model='deepseek-flash',choices=[dict(finish_reason='stop',
            message=dict(content=model))],usage=dict(prompt_tokens=10,completion_tokens=20,total_tokens=30,
                prompt_cache_hit_tokens=0,prompt_cache_miss_tokens=10))).encode()
        guard = OneShotTransport(httpx.MockTransport(lambda req: httpx.Response(200,content=body)),raw,
            request_limit=cd.MAX_INPUT_ENVELOPE_BYTES)
        meta = {}
        await receive_candidate(value,raw,guard,'offline-probe-secret',output=directory,metadata=meta,
            validator=lambda v,t: None,detail=lambda *a: {})
        require(guard.calls == 1 and (directory/'response-body.bin').read_bytes()==body and
            (directory/'model-output.txt').read_bytes()==model.encode(), 'RETENTION_SELFTEST')
        assembled = assemble_model_v3_output(value, source_context(read_sources())[3], model,
            current_snapshot_sha256=value.customer_evidence.snapshot_sha256)
        require(bool(assembled), 'ASSEMBLER_SELFTEST')
        ledger=WebExperimentLedger(directory/'mock.sqlite3'); ledger.initialize()
        ledger.issue('MOCK-ONLY',MANIFEST_HASH,PACKAGE,REQUEST_HASH,'MOCK',datetime.now(UTC)+timedelta(minutes=1))
        ledger.claim('MOCK-ONLY',MANIFEST_HASH,PACKAGE,REQUEST_HASH,'MOCK')
        try:
            ledger.claim('MOCK-ONLY',MANIFEST_HASH,PACKAGE,REQUEST_HASH,'MOCK')
        except ValueError:
            pass
        else:
            raise ValueError('LEDGER_SELFTEST')
    return dict(mock_only=True, real_api_calls=0, raw_response_exact=True, model_content_exact=True,
        durable_exclusive_write=True, directory_restricted=True, assembler_same_context_pass=True,
        existing_ledger_rejects_second_claim=True)

async def execute():
    raw,value,selection,checks = preflight()
    probe = await retention_selftest(value,raw)
    restrict_directory(OUT)
    write('preflight-verification.json',checks)
    write('retention-selftest.json',probe)
    # Fixed existing ledger, unique bundle; commit consumption before credentials/HTTP.
    LEDGER.initialize()
    expires = datetime.now(UTC)+timedelta(minutes=10)
    LEDGER.issue(PERMIT,MANIFEST_HASH,PACKAGE,REQUEST_HASH,'LIVE',expires)
    LEDGER.claim(PERMIT,MANIFEST_HASH,PACKAGE,REQUEST_HASH,'LIVE')
    row=LEDGER.read(PERMIT)
    require(row[7] is not None, 'PERMIT_NOT_CONSUMED')
    write('permit-consumed.json',dict(permit=PERMIT,bundle=MANIFEST_HASH,request_sha256=REQUEST_HASH,
        consumed_at=row[7],expires_at=row[5],budget=1,scope='SYNTHETIC / TEST ONLY',production_authorized=False))
    write('started.json',dict(started_at=datetime.now(UTC).isoformat(),request_sha256=REQUEST_HASH,
        maximum_requests=1,retries=0,semantic_approved=False,production_authorized=False))
    meta=dict(state='REJECTED',semantic_approved=False,production_authorized=False,retries=0,fallback=0,
        wordpress_calls=0,usage=None,finish_reason=None,response_sha256=None,http_status=None,
        model_text_sha256=None,request_sha256=REQUEST_HASH)
    guard=None
    start=time.perf_counter()
    try:
        load_api_keys('DEEPSEEK_API_KEY',project_root=ROOT)
        key=os.environ.get('DEEPSEEK_API_KEY','').strip()
        require(bool(key),'CREDENTIALS_UNAVAILABLE')
        guard=OneShotTransport(httpx.AsyncHTTPTransport(retries=0,trust_env=False),raw,
            expires_at=expires,request_limit=cd.MAX_INPUT_ENVELOPE_BYTES)
        await asyncio.wait_for(receive_candidate(value,raw,guard,key,output=OUT,metadata=meta,
            validator=lambda v,t: None,detail=lambda *a: {},timeout=60.0),timeout=60.0)
        meta['reception_success']=True
    except Exception as exc:
        meta['reception_success']=False
        meta['error_type']=type(exc).__name__
        allowed={'OUTPUT_INCOMPLETE','PROVIDER_HTTP_FAILURE','PROVIDER_ENVELOPE_INVALID','PROVIDER_JSON_FORMAT',
            'RESPONSE_BUDGET_EXCEEDED','ENCODED_RESPONSE_REFUSED','SECRET_OUTPUT_REFUSED','CREDENTIALS_UNAVAILABLE'}
        meta['error_code']=str(exc) if type(exc) is ValueError and str(exc) in allowed else 'SAFE_FAILURE_NO_RETRY'
    finally:
        meta.update(latency_seconds=round(time.perf_counter()-start,6),request_count=guard.calls if guard else 0,
            finished_at=datetime.now(UTC).isoformat())
        write('reception.json',meta)
        write('usage.json',meta['usage'])
        if (OUT/'response-body.bin').exists():
            save_bytes(OUT/'response-body.sha256',(sha((OUT/'response-body.bin').read_bytes())+'  response-body.bin\n').encode())
        print(json.dumps(meta,indent=2))
    # Client is closed. This path is local-only and cannot issue another request.
    if meta.get('reception_success'):
        from validate_stored import run
        run()

if __name__=='__main__':
    if sys.argv[1:]==['--execute-once']:
        asyncio.run(execute())
    else:
        raw,value,selection,checks=preflight()
        checks['retention_selftest']=asyncio.run(retention_selftest(value,raw))
        print(json.dumps(checks,indent=2))
