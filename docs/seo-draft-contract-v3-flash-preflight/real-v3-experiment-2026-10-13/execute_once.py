"""Explicitly authorized one-shot experiment. Never regenerates frozen inputs."""
import asyncio
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import httpx
from scripts.local_env import load_api_keys
from tests.test_seo_draft_v3_request_freeze import (
    read_sources, source_context, strict_json, sha, require, check_config,
    selection_digest, plan_digest,
)
from foreign_trade_geo_agent.adapters.retained_deepseek import (
    OneShotTransport, receive_candidate, restrict_directory, save_bytes, contains_secret,
)
from foreign_trade_geo_agent.core import content_draft as cd

OUT = Path(__file__).resolve().parent
PACKAGE = OUT.parent
REQUEST_HASH = 'd9bd075042613882b47dad0d2e56b7a1bb5aabdffda7b1f9abfbf12dac70a7ae'
MANIFEST_HASH = '589c090c0bff0d1e38f7615eb2b61b4ad568e36a723a172227e000f3f9d834f5'

def write(name, value):
    save_bytes(OUT / name, json.dumps(value, ensure_ascii=False, indent=2).encode('utf-8'))

def preflight():
    raw = (PACKAGE / 'request.json').read_bytes()
    manifest = (PACKAGE / 'manifest.json').read_bytes()
    require(sha(raw) == REQUEST_HASH, 'REQUEST_HASH')
    require(sha(manifest) == MANIFEST_HASH, 'MANIFEST_HASH')
    require((PACKAGE / 'manifest.sha256').read_bytes() == (MANIFEST_HASH + '  manifest.json\n').encode(), 'MANIFEST_ANCHOR')
    for entry in strict_json(manifest)['files']:
        content = (ROOT / entry['filename']).read_bytes()
        require(len(content) == entry['size'] and sha(content) == entry['sha256'], 'BOUND_FILE_HASH')
    sources = read_sources()
    old, prompt, projection, selection, value = source_context(sources)
    config = strict_json((PACKAGE / 'experiment-config.json').read_bytes())
    check_config(config)
    hashes = dict(request=sha(raw), manifest=sha(manifest), selection=selection_digest(selection),
        snapshot=selection.evidence_snapshot_sha256, plan=plan_digest(value), prompt=sha(sources['prompt-v3-material.json']))
    for name in ('selection', 'snapshot', 'plan', 'prompt'):
        require(hashes[name] == config[name + '_hash'], 'CONTEXT_HASH')
    request = strict_json(raw)
    require({k:v for k,v in request.items() if k != 'messages'} == dict(model='deepseek-flash',
        temperature=0, thinking={'type':'disabled'}, response_format={'type':'json_object'}, max_tokens=16384), 'PARAMETERS')
    require(request['messages'] == [dict(role='system', content=prompt['instructions']),
        dict(role='user', content=sources['prompt-v3-material.json'].decode('utf-8'))], 'PROMPT_BYTES')
    require(config['timeout'] == 60 and config['retries'] == 0 and config['fallback_allowed'] is False
        and config['repair_allowed'] is False and config['redirects_allowed'] is False, 'TRANSPORT_CONFIG')
    return raw, value, dict(result='PASS', hashes=hashes, manifest_entries_checked=10,
        integration_files_checked=len(strict_json(sources['artifact-sha256.json'])),
        snapshot_scope='Frozen snapshot binding consistency; no independent original snapshot reconstruction',
        parameters={k:v for k,v in request.items() if k != 'messages'}, timeout_seconds=60,
        original_package_files={p.name:sha(p.read_bytes()) for p in PACKAGE.iterdir() if p.is_file()},
        authorization='Current project owner message: one REAL_V3_FLASH_EXPERIMENT for exact request and manifest hashes',
        semantic_approved=False, production_authorized=False)

async def execute():
    raw, value, checks = preflight()
    require(not (OUT / 'started.json').exists(), 'ATTEMPT_ALREADY_STARTED_NO_RETRY')
    restrict_directory(OUT)
    load_api_keys('DEEPSEEK_API_KEY', project_root=ROOT)
    key = os.environ.get('DEEPSEEK_API_KEY', '').strip()
    require(bool(key), 'CREDENTIALS_UNAVAILABLE')
    write('preflight-verification.json', checks)
    write('started.json', dict(started_at=datetime.now(UTC).isoformat(), request_sha256=sha(raw),
        maximum_requests=1, retries=0, semantic_approved=False, production_authorized=False))
    meta = dict(state='REJECTED', semantic_approved=False, production_authorized=False,
        retries=0, fallback=0, model_switches=0, repairs=0, wordpress_calls=0,
        usage=None, finish_reason=None, response_sha256=None, response_bytes=None)

    class CapturingTransport(OneShotTransport):
        async def handle_async_request(self, request):
            response = await super().handle_async_request(request)
            headers = []
            withheld = []
            for name, val in response.headers.raw:
                line = name + b': ' + val
                if name.lower() in {b'set-cookie', b'cookie', b'authorization', b'proxy-authorization'} or contains_secret(line, key):
                    withheld.append(name.decode('ascii', errors='replace'))
                else:
                    headers.append(line)
            prefix = response.http_version.encode('ascii') + b' ' + str(response.status_code).encode() + b' ' + response.reason_phrase.encode('ascii') + b'\r\n'
            save_bytes(OUT / 'response-http-headers.bin', prefix + b'\r\n'.join(headers) + b'\r\n\r\n')
            meta['withheld_sensitive_header_names'] = withheld
            return response

    guard = CapturingTransport(httpx.AsyncHTTPTransport(retries=0, trust_env=False), raw,
        request_limit=cd.MAX_INPUT_ENVELOPE_BYTES)
    started = time.perf_counter()
    try:
        # This callback only retains reception success. All five validation layers
        # run separately on stored output after the network client is closed.
        await asyncio.wait_for(receive_candidate(value, raw, guard, key, output=OUT, metadata=meta,
            validator=lambda v,t: None, detail=lambda v,t,c: {'category':c}, timeout=60.0), timeout=60.0)
        meta['reception_success'] = True
    except Exception as exc:
        meta['reception_success'] = False
        meta['error_type'] = type(exc).__name__
        allowed = {'OUTPUT_INCOMPLETE','PROVIDER_HTTP_FAILURE','PROVIDER_ENVELOPE_INVALID',
            'PROVIDER_JSON_FORMAT','RESPONSE_BUDGET_EXCEEDED','ENCODED_RESPONSE_REFUSED','SECRET_OUTPUT_REFUSED'}
        meta['error_code'] = str(exc) if type(exc) is ValueError and str(exc) in allowed else 'SAFE_FAILURE_NO_RETRY'
    finally:
        meta.update(latency_seconds=round(time.perf_counter()-started,6), request_count=guard.calls,
            finished_at=datetime.now(UTC).isoformat())
        write('reception.json', meta)
        write('usage.json', meta['usage'])
        if (OUT / 'response-body.bin').exists():
            save_bytes(OUT / 'response-body.sha256', (sha((OUT / 'response-body.bin').read_bytes()) + '  response-body.bin\n').encode())
        print(json.dumps(meta, indent=2))

if __name__ == '__main__':
    if sys.argv[1:] == ['--execute-once']:
        asyncio.run(execute())
    else:
        print(json.dumps(preflight()[2], indent=2))
