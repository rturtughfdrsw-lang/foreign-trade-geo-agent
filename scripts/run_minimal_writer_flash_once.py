"""Exact authorized TEST-only request; persistent one-attempt marker, no retries."""
import asyncio
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import httpx
from scripts import prepare_minimal_writer_flash_preflight as frozen
from scripts.local_env import load_api_keys
from foreign_trade_geo_agent.adapters.retained_deepseek import (
    ENDPOINT, OneShotTransport, contains_secret, receive_candidate, restrict_directory, save_bytes,
)
from foreign_trade_geo_agent.core import content_draft as cd

OUT = ROOT/'docs/minimal-writer-flash-results'
REQUEST_HASH = '3578587e2e55a941710aafb1eb8e5fc2b616697d3682753590adc385618540d4'
MANIFEST_HASH = 'ec19fb23760d34b3af17f9bad66cc70c6860de8a422f7cbd111f7ad3649541dd'
PRICE_URL = 'https://api-docs.deepseek.com/quick_start/pricing/'


def write(directory, name, data):
    save_bytes(directory/name, json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')+b'\n')


def preflight():
    verified = frozen.verify_package(frozen.DEST, MANIFEST_HASH)
    raw = (frozen.DEST/'request.json').read_bytes()
    frozen.require(frozen.sha(raw) == REQUEST_HASH, 'AUTHORIZED_REQUEST_HASH')
    sources = {n:(frozen.DEST/n).read_bytes() for n in frozen.INPUT_PATHS}
    value,selection,manifest = frozen.context(sources)
    material = frozen.strict((frozen.DEST/'writer-material.json').read_bytes())
    frozen.check_boundary(material,value,selection,manifest)
    frozen.require(len(material['facts'])==25 and len(material['slots'])==12, 'FROZEN_COUNTS')
    return raw,value,dict(verified, selected_facts=25, explanation_slots=12,
        workspace='Current Local; frozen uncommitted inputs and source bytes verified, not Git HEAD',
        state='VERIFIED_TEST_ONLY', frozen_authorization_flags_unchanged=True)


def current_baseline():
    names=subprocess.check_output(['git','ls-files','-z','--cached','--others','--exclude-standard'],cwd=ROOT)
    return {name:frozen.sha((ROOT/name).read_bytes()) for part in names.split(b'\0')
            if part and (name:=part.decode('utf-8')) and (ROOT/name).is_file()
            and not name.startswith('docs/minimal-writer-flash-results/')}


def historical_integrity():
    directory=ROOT/'docs/minimal-writer-flash-preflight-verification'
    before=json.loads((directory/'baseline.json').read_text(encoding='utf-8'))['files']
    permitted={'scripts/prepare_minimal_writer_flash_preflight.py',
               'scripts/verify_minimal_writer_flash_offline.py','tests/test_seo_draft_v3_request_freeze.py'}
    changed=[n for n,h in before.items() if not (ROOT/n).is_file() or frozen.sha((ROOT/n).read_bytes())!=h]
    frozen.require(not set(changed)-permitted,'HISTORICAL_INTEGRITY_FAILED')
    return dict(baseline_files=len(before),unchanged=len(before)-len(changed),
                permitted_historical_changes=changed,unexpected_changes=[])


def budget_check(prices, raw):
    frozen.require(prices['official_url']==PRICE_URL and prices['verified'] is True, 'OFFICIAL_PRICE_REQUIRED')
    verified_at=datetime.fromisoformat(prices['verified_at_utc'])
    frozen.require(verified_at.tzinfo is not None and timedelta(0)<=datetime.now(UTC)-verified_at<timedelta(hours=24),
                   'PRICE_VERIFICATION_STALE')
    rates=prices['peak_usd_per_million']
    frozen.require(rates==dict(input_cache_hit=0.006,input_cache_miss=0.3,output=1.2), 'PRICE_TERMS_CHANGED')
    # English ASCII request ~16K bytes; 65K input reserve is >3x byte-based framing scenario.
    frozen.require(len(raw)+1024<65536,'INPUT_COST_RESERVE_INSUFFICIENT')
    cost=(65536*rates['input_cache_miss']+16384*rates['output'])/1000000
    frozen.require(cost<=0.05,'AUTHORIZED_BUDGET_EXCEEDED')
    return dict(input_token_planning_reserve=65536,max_output_tokens=16384,
        peak_all_cache_miss_planning_usd=round(cost,8),authorized_budget_usd=0.05,
        reasonable_conservative_estimate=True,exact_tokenizer_bound=False)


async def dry_run(raw):
    seen=[]
    async def handler(request):
        seen.append(request.content)
        return httpx.Response(200,json={'dry_run':True})
    guard=OneShotTransport(httpx.MockTransport(handler),raw,request_limit=cd.MAX_INPUT_ENVELOPE_BYTES)
    async with httpx.AsyncClient(transport=guard,follow_redirects=False,trust_env=False,timeout=60) as client:
        await client.post(ENDPOINT,content=raw,headers={'Content-Type':'application/json'})
        try:
            await client.post(ENDPOINT,content=raw)
        except ValueError as exc:
            frozen.require(str(exc)=='SINGLE_REQUEST_GUARD','DRY_RUN_SECOND_REQUEST_GUARD')
        else:
            raise ValueError('DRY_RUN_SECOND_REQUEST_NOT_REJECTED')
    frozen.require(seen==[raw] and guard.calls==1,'DRY_RUN_BYTES')
    return dict(result='PASS',transport='httpx.MockTransport',exact_sent_bytes=True,
        request_sha256=frozen.sha(seen[0]),request_bytes=len(raw),second_send_rejected=True,real_api_calls=0)


def claim_attempt(directory):
    # Durable exclusive file, before network construction. Uncertainty consumes authorization.
    write(directory,'attempt-started.json',dict(started_at_utc=datetime.now(UTC).isoformat(),
        request_sha256=REQUEST_HASH,manifest_sha256=MANIFEST_HASH,maximum_attempts=1,
        authorization='Project owner explicitly authorized this exact one-time TEST-only request; USD 0.05 ceiling',
        retry_allowed=False,semantic_approved=False,production_authorized=False))


async def execute(directory=OUT):
    raw,value,checks=preflight()
    frozen.require(not any((directory/n).exists() for n in (
        'attempt-started.json','response-body.bin','model-output.txt','reception.json')), 'NO_SECOND_ATTEMPT')
    prices=json.loads((directory/'official-pricing.json').read_text(encoding='utf-8'))
    budget=budget_check(prices,raw)
    dry=json.loads((directory/'dry-run.json').read_text(encoding='utf-8'))
    frozen.require(dry['result']=='PASS' and dry['request_sha256']==REQUEST_HASH
                   and dry['exact_sent_bytes'] is True and dry['real_api_calls']==0,'DRY_RUN_REQUIRED')
    baseline=json.loads((directory/'baseline-before.json').read_text(encoding='utf-8'))
    frozen.require(all((ROOT/n).is_file() and frozen.sha((ROOT/n).read_bytes())==h for n,h in baseline.items()),
                   'WORKSPACE_DRIFT_BEFORE_SEND')
    historical_integrity()
    load_api_keys('DEEPSEEK_API_KEY',project_root=ROOT)
    key=os.environ.get('DEEPSEEK_API_KEY','').strip()
    frozen.require(bool(key),'CREDENTIALS_UNAVAILABLE')
    frozen.require(not contains_secret(raw,key),'SECRET_IN_REQUEST_REFUSED')
    restrict_directory(directory)
    checks.update(budget=budget,api_key_present=True,parameters=frozen.PARAMETERS,
                  timeout=60,retries=0,fallback=False,repair=False,redirects=False)
    write(directory,'pre-send-verification.json',checks)
    claim_attempt(directory)
    meta=dict(http_status=None,finish_reason=None,usage=None,response_sha256=None,
        request_sha256=REQUEST_HASH,manifest_sha256=MANIFEST_HASH,real_api_calls=0,
        retries=0,fallback=False,repair=False,redirects=False,wordpress_calls=0,
        semantic_approved=False,production_authorized=False)

    class CapturingTransport(OneShotTransport):
        async def handle_async_request(self,request):
            response=await super().handle_async_request(request)
            lines,withheld=[],[]
            for name,val in response.headers.raw:
                line=name+b': '+val
                if name.lower() in {b'set-cookie',b'cookie',b'authorization',b'proxy-authorization'} or contains_secret(line,key):
                    withheld.append(name.decode('ascii',errors='replace'))
                else:
                    lines.append(line)
            status=f'{response.http_version} {response.status_code} {response.reason_phrase}\r\n'.encode('ascii',errors='replace')
            save_bytes(directory/'response-http-headers.bin',status+b'\r\n'.join(lines)+b'\r\n\r\n')
            meta['withheld_sensitive_header_names']=withheld
            return response

    guard=CapturingTransport(httpx.AsyncHTTPTransport(retries=0,trust_env=False),raw,
        request_limit=cd.MAX_INPUT_ENVELOPE_BYTES)
    started=time.perf_counter()
    try:
        # No native validation on the network path; stored-byte evaluation follows.
        await asyncio.wait_for(receive_candidate(value,raw,guard,key,output=directory,metadata=meta,
            validator=lambda *_:None,detail=lambda *_:None,timeout=60.0),timeout=60.0)
        meta['reception_success']=True
    except Exception as exc:
        meta['reception_success']=False
        meta['error_type']=type(exc).__name__
        allowed={'OUTPUT_INCOMPLETE','PROVIDER_HTTP_FAILURE','PROVIDER_ENVELOPE_INVALID',
                 'PROVIDER_JSON_FORMAT','RESPONSE_BUDGET_EXCEEDED','ENCODED_RESPONSE_REFUSED','SECRET_OUTPUT_REFUSED'}
        meta['error_code']=str(exc) if type(exc) is ValueError and str(exc) in allowed else 'SAFE_FAILURE_NO_RETRY'
        meta['timeout']=isinstance(exc,(TimeoutError,httpx.TimeoutException))
    finally:
        meta.update(latency_seconds=round(time.perf_counter()-started,6),real_api_calls=guard.calls,
                    finished_at_utc=datetime.now(UTC).isoformat())
        write(directory,'reception.json',meta)
        write(directory,'usage.json',meta['usage'])
        if (directory/'response-body.bin').exists():
            save_bytes(directory/'response-body.sha256',
                (frozen.sha((directory/'response-body.bin').read_bytes())+'  response-body.bin\n').encode('ascii'))
    return meta


async def prepare():
    raw,_,checks=preflight()
    frozen.require(not OUT.exists(),'RESULT_DIRECTORY_ALREADY_EXISTS')
    history=historical_integrity()
    baseline=current_baseline()
    dry=await dry_run(raw)
    OUT.mkdir()
    restrict_directory(OUT)
    write(OUT,'baseline-before.json',baseline)
    write(OUT,'offline-precheck.json',dict(checks,historical_integrity=history))
    write(OUT,'dry-run.json',dry)
    return dry


if __name__=='__main__':
    try:
        if sys.argv[1:]==['--dry-run']:
            result=asyncio.run(prepare())
        elif sys.argv[1:]==['--execute-authorized-once']:
            result=asyncio.run(execute())
        else:
            raise ValueError('EXPLICIT_MODE_REQUIRED')
        # No raw exceptions, response payloads, headers, environment or credential data.
        print(json.dumps({k:result[k] for k in result if k in {
            'result','request_sha256','request_bytes','real_api_calls','http_status','finish_reason',
            'reception_success','latency_seconds','error_type','error_code','timeout','response_sha256','usage'}}))
    except Exception as exc:
        print(json.dumps(dict(stopped=True,error_type=type(exc).__name__,no_automatic_retry=True)))
        raise SystemExit(1)
