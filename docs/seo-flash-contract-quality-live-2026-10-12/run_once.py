"""Case-local authorized launcher. No source changes, re-freeze or retries.

Execution uses an identical copy because scope checks append TEST audit records
to SQLite. The original authorized package remains byte-for-byte unchanged.
"""
import asyncio
from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.accept_autonomous_interpretation import FactsOnlyReviewer
from scripts.web_deepseek_experiment import compose, live_ledger
from foreign_trade_geo_agent.adapters.retained_deepseek import restrict_directory, save_bytes
from foreign_trade_geo_agent.core import content_draft as cd
from foreign_trade_geo_agent.core.evidence_intake import Supplement, snapshot_digest, validate_assessment
from foreign_trade_geo_agent.storage.serialization import _decode, _encode
from foreign_trade_geo_agent.web.experiment import code_hashes
from foreign_trade_geo_agent.web.generation import canonical, MockArticleExecutor
from foreign_trade_geo_agent.workflows.content_draft import _parse_specification, inspect_candidate_output

OUT = Path(__file__).resolve().parent
FROZEN = ROOT / 'docs/seo-flash-request-preflight-2026-10-12/final-v2'
REQUEST = '8fd2b8834c9aa50f4ebaeba6229b4a9b01b59d033effa8637cce5ed223428431'
DELIVERY = 'e797983c2d20d63b6f57491c377142a57aa05886f58bd8b7abdc27447adb094a'
BUNDLE = 'e114a55bd2e55c80a3f8b869f9e00d90acdefb4da376837515bb28e75ab4ca01'
PERMIT = 'WEB-TEST-FLASH-E-CONTRACT-2026-10-12-ONE-SHOT'
sha = lambda raw: hashlib.sha256(raw).hexdigest()

def write(name, value):
    save_bytes(OUT / name, canonical(value))

def verify():
    manifest = (FROZEN / 'artifact-sha256.json').read_bytes()
    assert sha(manifest) == DELIVERY == (FROZEN / 'bundle.sha256').read_text().strip()
    entries = json.loads(manifest)
    assert all(sha((FROZEN/n).read_bytes()) == h for n,h in entries.items())
    assert json.loads((FROZEN/'source-sha256.json').read_bytes()) == code_hashes()
    ready = json.loads((FROZEN/'readiness.json').read_bytes())
    assert datetime.now(UTC) < datetime.fromisoformat(ready['preparation_valid_until'])
    native = FROZEN/'native/B-rich-evidence/web-experiment'
    assert sha((native/'bundle.json').read_bytes()) == BUNDLE
    inside = json.loads((native/'bundle.json').read_bytes())
    assert inside['code'] == code_hashes()
    assert all(sha((native/n).read_bytes()) == h for n,h in inside['files'].items())
    raw = (FROZEN/'request.FROZEN-NOT-AUTHORIZED.json').read_bytes()
    assert sha(raw) == REQUEST and raw == (native/'request.json').read_bytes()
    req = json.loads(raw)
    assert {k:v for k,v in req.items() if k != 'messages'} == dict(model='deepseek-flash',temperature=0,
        thinking={'type':'disabled'},response_format={'type':'json_object'},max_tokens=16384)
    assert [m['role'] for m in req['messages']] == ['system','user']
    system,user = [m['content'] for m in req['messages']]
    assert system.encode() == (FROZEN/'system-prompt.txt').read_bytes()
    assert user.encode() == (FROZEN/'user-material.json').read_bytes()
    assert 'E CANDIDATE MODE' in system and 'PENDING_SEMANTIC_REVIEW' in system
    assert all(s not in system for s in ('Every claim is exactly {"text","claim_type","page_refs","source_refs"}',
        'must cite at least one P page','Keep every claim short and lexically grounded','supersedes'))
    value = _decode(json.loads((native/'native-input.json').read_bytes()), cd.ContentDraftInput)
    assert MockArticleExecutor.request_for(value) == raw
    assert value.propose_interpretations and not value.customer_evidence.interpretations
    assert len(value.customer_evidence.sources) == 7 and sum(len(s.facts) for s in value.customer_evidence.sources) == 43
    material = json.loads(user)
    assert set(material['contract']['customer_refs']) == set(value.customer_evidence.quote_map())
    assert len(material['change']['new_resource']['section_briefs']) == 6
    assert value.change_plan_report.operations[0].new_resource_spec.proposed_title == "How to Choose a CNC Machining Center: A Practical Buyer's Guide"
    cost = (65536 * .3 + 16384 * 1.2)/1e6
    assert cost == .0393216 and cost <= .05
    return raw, dict(checked_at=datetime.now(UTC).isoformat(),request_sha256=REQUEST,
        delivery_bundle_sha256=DELIVERY,execution_bundle_sha256=BUNDLE,artifact_files=len(entries),
        source_files=len(code_hashes()),parameters=req | {'messages':'verified exact frozen bytes'},
        owner_authorization='Current project-owner message: exact three hashes, one Flash request, USD 0.05 planning budget; estimated token/cost risks accepted.',
        token_count_exact=False,planning_peak_cache_miss_cost_usd=cost,planning_budget_usd=.05,
        official_price_source='https://api-docs.deepseek.com/quick_start/pricing/',
        official_parameters_source='https://api-docs.deepseek.com/api/create-chat-completion',
        official_model_version='DeepSeek-V4.1-Flash',official_checked_at='2026-10-12T03:43:00+00:00',
        timeout_seconds=60,retries=0,fallback=0,repairs=0,production_authorized=False,
        wordpress_authorized=False,human_signoff=False)

async def execute():
    raw, checks = verify()
    assert not (OUT/'attempt-started.json').exists(), 'ATTEMPT_ALREADY_STARTED'
    ledger = live_ledger()
    assert ledger.path.is_file(), 'FIXED_LEDGER_MISSING'
    with sqlite3.connect('file:'+ledger.path.as_posix()+'?mode=ro',uri=True) as db:
        rows = db.execute('SELECT permit FROM permits WHERE bundle=? OR request=? OR permit=?',
            (BUNDLE,REQUEST,PERMIT)).fetchall()
    assert not rows, 'BUNDLE_REQUEST_OR_PERMIT_ALREADY_ARMED_OR_CONSUMED'
    restrict_directory(OUT)
    work = OUT/'execution-input'
    shutil.copytree(FROZEN/'native/B-rich-evidence',work)
    # Exact material and bundle copies, no call to freeze().
    assert all(sha((work/'web-experiment'/n).read_bytes()) == h for n,h in
        json.loads((work/'web-experiment/bundle.json').read_bytes())['files'].items())
    assert sha((work/'web-experiment/bundle.json').read_bytes()) == BUNDLE
    facts = json.loads((FROZEN/'customer-materials/facts.json').read_bytes())
    supplements = tuple(_decode(x,Supplement) for x in json.loads((FROZEN/'customer-materials/documents.json').read_bytes()))
    reviewer = FactsOnlyReviewer(facts,supplements)
    # Check credentials exist without printing them, before consuming authority.
    from scripts.local_env import load_api_keys
    import os
    load_api_keys('DEEPSEEK_API_KEY',project_root=ROOT)
    assert os.environ.get('DEEPSEEK_API_KEY','').strip(), 'CREDENTIALS_UNAVAILABLE'
    checks.update(permit_previously_absent=True,reviewer='FactsOnlyReviewer / TEST_ONLY_NOT_HUMAN_SIGNOFF',
        execution_copy='Exact frozen copy; append-only TEST scope checks confined to copied SQLite.',
        raw_retention_access='Current Windows account only; inherited ACL disabled before request')
    expiry = datetime.now(UTC) + timedelta(minutes=10)
    ledger.issue(PERMIT,BUNDLE,work,REQUEST,'LIVE',expiry)
    app = compose(work,BUNDLE,ledger,PERMIT,scope_reviewer=reviewer)
    service = app.state.mvp_service
    executor,store,value,loaded,binding = service.generation._prepare()
    assert binding == BUNDLE and loaded == raw
    session = service._load()[0]
    current = service._current(store,session)
    now = datetime.now(UTC)
    assessment = service.require_generation_scope(current)
    validate_assessment(current,assessment,now=datetime.now(UTC))
    assert snapshot_digest(current) == value.customer_evidence.snapshot_sha256 and current.plan_bound
    assert cd.stable_content_draft_input_error(value) is None
    assert MockArticleExecutor.request_for(value) == raw
    assert all(e.supplement == s for e,s in zip(current.active_evidence,supplements))
    assert not ledger.read(PERMIT)[7]
    verify()  # Final original hashes, code, expiry and exact payload before claim.
    checks.update(snapshot_sha256=snapshot_digest(current),reviewed_at=assessment.reviewed_at.isoformat(),
        reviewer_id=assessment.reviewer_id,native_input_validation='PASS',generation_scope='PASS',
        execution_expiry=expiry.isoformat(),permit=PERMIT)
    write('preflight.json',checks)
    write('attempt-started.json',dict(started_at=datetime.now(UTC).isoformat(),permit=PERMIT,
        request_sha256=REQUEST,max_requests=1,no_retry=True))
    started = time.perf_counter()
    service.generation.start(BUNDLE,(BUNDLE,expiry))
    tasks = tuple(service.generation.tasks)
    assert len(tasks) == 1
    await asyncio.gather(*tasks)
    elapsed = time.perf_counter()-started
    output = service.generation.root/BUNDLE
    result = json.loads((output/'result.json').read_bytes())
    assert ledger.read(PERMIT)[7] is not None
    summary = dict(result,latency_seconds=round(elapsed,6),
        latency_definition='End-to-end start through response retention and native candidate check',
        completed_at=datetime.now(UTC).isoformat(),output_directory=str(output),
        finalizer='NOT_RUN; candidate-only experiment',retry=0,fallback=0)
    if (output/'response-body.bin').exists() and result.get('response_complete'):
        body = json.loads((output/'response-body.bin').read_bytes())
        summary['actual_model'] = body.get('model')
        summary['raw_usage'] = body.get('usage')
    if (output/'model-output.txt').exists():
        text = (output/'model-output.txt').read_text(encoding='utf-8')
        operation = value.change_plan_report.operations[0]
        try:
            _parse_specification(text,expected_change_ref=operation.change_id,operation=operation)
            summary['parser'] = 'PASS'
        except Exception as exc:
            summary.update(parser='FAIL',parser_error_type=type(exc).__name__,parser_error=str(exc))
        if summary.get('parser') == 'PASS':
            check = inspect_candidate_output(value,text,current_snapshot_sha256=snapshot_digest(current))
            write('candidate-validation.json',_encode(check))
            summary.update(validator=check.state,candidate_errors=list(check.errors))
    assert summary.get('real_requests',0) <= 1
    write('execution-summary.json',summary)
    print(json.dumps(summary,indent=2,ensure_ascii=False))

if __name__ == '__main__':
    if sys.argv[1:] == ['--execute-once']:
        asyncio.run(execute())
    else:
        print(json.dumps(verify()[1],indent=2,ensure_ascii=False))
