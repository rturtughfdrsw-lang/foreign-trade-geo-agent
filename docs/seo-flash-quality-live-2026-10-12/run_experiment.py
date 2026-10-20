"""Single authorized experiment. Exact frozen bytes; never repair or retry."""
import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import httpx
from scripts.local_env import load_api_keys
from scripts.web_deepseek_experiment import live_ledger
from foreign_trade_geo_agent.adapters.retained_deepseek import (
    OneShotTransport, receive_candidate, restrict_directory, save_bytes,
)
from foreign_trade_geo_agent.core import content_draft as cd
from foreign_trade_geo_agent.core.evidence_intake import snapshot_digest
from foreign_trade_geo_agent.storage.evidence_intake import SQLiteEvidenceIntakeStore
from foreign_trade_geo_agent.storage.serialization import _decode, _encode
from foreign_trade_geo_agent.web.experiment import FrozenWebExecutor, code_hashes
from foreign_trade_geo_agent.web.generation import canonical, MockArticleExecutor, retain_review_candidate
from foreign_trade_geo_agent.workflows.content_draft import _parse_specification, inspect_candidate_output

FROZEN = ROOT / 'docs/seo-full-article-budget-2026-10-11/final-v2'
RICH = FROZEN / 'native/B-rich-evidence'
OUT = Path(__file__).resolve().parent
PERMIT = 'WEB-TEST-FLASH-QUALITY-2026-10-12-ONE-SHOT'

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def write(name, data):
    save_bytes(OUT / name, canonical(data))

def preflight():
    ready = json.loads((FROZEN/'readiness.json').read_bytes())
    manifest = json.loads((FROZEN/'artifact-sha256.json').read_bytes())
    assert all(sha((FROZEN/n).read_bytes()) == h for n,h in manifest.items()), 'FROZEN_ARTIFACT_CHANGED'
    assert ready['code_sha256'] == code_hashes(), 'FROZEN_CODE_CHANGED'
    prep = json.loads((FROZEN/'real-request-preflight.json').read_bytes())
    assert datetime.now(UTC) < datetime.fromisoformat(prep['preparation_valid_until']), 'FREEZE_EXPIRED'
    raw = (FROZEN/'request.FROZEN-NOT-AUTHORIZED.json').read_bytes()
    assert sha(raw) == ready['request_sha256'], 'REQUEST_CHANGED'
    request = json.loads(raw)
    assert {k:v for k,v in request.items() if k != 'messages'} == {
        'model':'deepseek-flash', 'temperature':0, 'thinking':{'type':'disabled'},
        'response_format':{'type':'json_object'}, 'max_tokens':16384}, 'PARAMETERS_CHANGED'
    assert request['messages'][0]['content'].encode() == (FROZEN/'system-prompt.txt').read_bytes()
    assert request['messages'][1]['content'].encode() == (FROZEN/'user-material.json').read_bytes()
    value = _decode(json.loads((RICH/'web-experiment/native-input.json').read_bytes()), cd.ContentDraftInput)
    session = json.loads((RICH/'session.json').read_bytes())
    current = SQLiteEvidenceIntakeStore(RICH/'interactive-intake.sqlite3').latest(session['project_id'],session['task_id'])
    assert snapshot_digest(current) == value.customer_evidence.snapshot_sha256, 'CURRENT_SNAPSHOT_CHANGED'
    assert current.plan_bound and len(value.customer_evidence.sources) == 7
    assert sum(len(s.facts) for s in value.customer_evidence.sources) == 43
    assert MockArticleExecutor.request_for(value) == raw, 'REBUILT_REQUEST_CHANGED'
    value = replace(value, customer_evidence=replace(value.customer_evidence, reviewed_at=datetime.now(UTC)))
    assert cd.stable_content_draft_input_error(value) is None, 'NATIVE_INPUT_INVALID'
    assert MockArticleExecutor.request_for(value) == raw, 'FRESH_REVIEW_CHANGED_REQUEST'
    return ready, value, current, raw, dict(status='FROZEN_INPUT_VERIFIED',
        checked_at=datetime.now(UTC).isoformat(), artifact_files_checked=len(manifest),
        code_files_checked=len(ready['code_sha256']), mismatches=[], request_sha256=sha(raw),
        bundle_sha256=ready['bundle_sha256'], snapshot_sha256=snapshot_digest(current),
        task_version=value.customer_evidence.task_version, plan_version=value.customer_evidence.plan_version,
        evidence_version=value.customer_evidence.evidence_version, documents=7, facts=43,
        sections=6, exact_token_count_before_request=None, token_budget_uncertainty_retained=True,
        raw_request_bytes=len(raw), max_output_tokens=16384, timeout_seconds=60, retries=0,
        authorization='Current user request: one real Flash SYNTHETIC quality experiment only',
        production_authorized=False, wordpress_authorized=False)

async def execute():
    ready,value,current,raw,checked = preflight()
    assert not (OUT/'started.json').exists(), 'ATTEMPT_ALREADY_STARTED_NO_RETRY'
    write('preflight.json', checked)
    restrict_directory(OUT)
    ledger = live_ledger()
    ledger.initialize()
    restrict_directory(ledger.path.parent)
    expiry = datetime.now(UTC) + timedelta(minutes=10)
    ledger.issue(PERMIT,ready['bundle_sha256'],RICH,sha(raw),'LIVE',expiry)
    executor = FrozenWebExecutor(RICH,ready['bundle_sha256'],ledger,PERMIT)
    value,loaded_raw = executor.load(current)
    assert loaded_raw == raw
    ledger.claim(PERMIT,ready['bundle_sha256'],RICH,sha(raw),'LIVE')
    save_bytes(OUT/'request.json',raw)
    write('native-input.json',_encode(value))
    metadata = dict(checked,state='RUNNING',started_at=datetime.now(UTC).isoformat(),
        permit=PERMIT,max_requests=1,request_count=0,real_requests=0,usage=None)
    write('started.json',metadata)
    started = time.perf_counter()
    guard = None
    try:
        load_api_keys('DEEPSEEK_API_KEY',project_root=ROOT)
        key = os.environ.get('DEEPSEEK_API_KEY','').strip()
        assert key, 'CREDENTIALS_UNAVAILABLE'
        guard = OneShotTransport(httpx.AsyncHTTPTransport(retries=0,trust_env=False),raw,
            expires_at=expiry,request_limit=cd.MAX_INPUT_ENVELOPE_BYTES)

        def validate(native,text):
            operation = native.change_plan_report.operations[0]
            spec = _parse_specification(text,expected_change_ref=operation.change_id,operation=operation)
            metadata['parser']='PASS'
            checked_candidate = inspect_candidate_output(native,text,current_snapshot_sha256=snapshot_digest(current))
            write('candidate-validation.json',_encode(checked_candidate))
            metadata['validator']=checked_candidate.state
            metadata['candidate_errors']=list(checked_candidate.errors)
            retain_review_candidate(native,text,OUT,metadata)
            if checked_candidate.errors:
                metadata['finalizer']='NOT_RUN_VALIDATOR_FAILED'
                raise ValueError('NATIVE_VALIDATION_FAILED')
            draft,error = cd.finalize_draft_item(1,spec,operation,native.opportunity_report.opportunities[0],
                native.site_content,native.opportunity_report,customer_evidence=native.customer_evidence)
            metadata['finalizer']=error or 'PASS'
            metadata['admitted_draft']=draft is not None
            write('finalizer.json',{'error':error,'admitted_draft':draft is not None,
                'human_semantic_approval':False,'production_authorized':False})
            return checked_candidate

        await asyncio.wait_for(receive_candidate(value,raw,guard,key,output=OUT,metadata=metadata,
            validator=validate,detail=lambda v,t,c:{'category':c},timeout=60.0),60.0)
        metadata['state']='PENDING_SEMANTIC_REVIEW'
    except Exception as exc:
        metadata['state']='FAILED_STOPPED_NO_RETRY'
        metadata['error_type']=type(exc).__name__
        metadata['error']=str(exc) if type(exc) in {ValueError,AssertionError} and str(exc) in {
            'NATIVE_VALIDATION_FAILED','CREDENTIALS_UNAVAILABLE','OUTPUT_INCOMPLETE','PROVIDER_HTTP_FAILURE',
            'PROVIDER_ENVELOPE_INVALID','PROVIDER_JSON_FORMAT','RESPONSE_BUDGET_EXCEEDED',
            *[c.value for c in cd.ContentDraftValidationCategory]} else 'SAFE_FAILURE_NO_RETRY'
    finally:
        metadata.update(latency_seconds=round(time.perf_counter()-started,6),
            finished_at=datetime.now(UTC).isoformat(),request_count=guard.calls if guard else 0,
            real_requests=guard.calls if guard else 0)
        write('result.json',metadata)
        print(json.dumps(metadata,indent=2))

if __name__ == '__main__':
    if sys.argv[1:] == ['--execute-once']:
        asyncio.run(execute())
    else:
        print(json.dumps(preflight()[-1],indent=2))
