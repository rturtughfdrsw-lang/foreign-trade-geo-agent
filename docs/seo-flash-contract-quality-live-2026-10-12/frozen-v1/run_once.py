"""One authorized frozen-v1 experiment. No prompt/code repair or regeneration.

Default mode is read-only verification. --execute-once consumes the fixed local
ledger reservation before the single exact-byte POST. Never rerun after a claim.
"""
import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
import hashlib
import inspect
import json
import os
from pathlib import Path
import sqlite3
import sys
import time

import httpx

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from scripts.accept_autonomous_interpretation import FactsOnlyReviewer, persist_replay
from scripts.local_env import load_api_keys
from scripts.web_deepseek_experiment import live_ledger
from foreign_trade_geo_agent.adapters.retained_deepseek import (
    OneShotTransport, receive_candidate, restrict_directory, save_bytes, contains_secret,
)
from foreign_trade_geo_agent.core import content_draft as cd
from foreign_trade_geo_agent.core.draft_candidate_review import CandidateDecision
from foreign_trade_geo_agent.core.evidence_intake import IntakeSnapshot, Supplement, snapshot_digest, validate_assessment
from foreign_trade_geo_agent.storage.content_draft_review import SQLiteLocalDraftReviewStore
from foreign_trade_geo_agent.storage.serialization import _decode, _encode
from foreign_trade_geo_agent.web.experiment import code_hashes
from foreign_trade_geo_agent.web.generation import MockArticleExecutor
from foreign_trade_geo_agent.workflows import content_draft as workflow
from foreign_trade_geo_agent.workflows.content_draft_review import test_only_revalidate_candidate

OUT = Path(__file__).resolve().parent
FROZEN = ROOT / 'docs/seo-draft-contract-offline-2026-10-12/frozen-v1'
REQUEST = '9273e145beaacb122e57261294143c1a9df0cd4faba8554a03609c194e86ab0f'
BUNDLE = 'ad96bbb5d8fee7d35fee5832d51cea96d65bce607e08e8b9fa09868ed875a9cf'
PERMIT = 'WEB-TEST-FLASH-FROZEN-V1-2026-10-12-ONE-SHOT'
sha = lambda raw: hashlib.sha256(raw).hexdigest()


def write(name, value):
    save_bytes(OUT / name, (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode())


def verify():
    ready = json.loads((FROZEN / 'readiness.json').read_bytes())
    manifest_raw = (FROZEN / 'artifact-sha256.json').read_bytes()
    assert sha(manifest_raw) == BUNDLE == (FROZEN / 'bundle.sha256').read_text().strip()
    manifest = json.loads(manifest_raw)
    assert all(sha((FROZEN / name).read_bytes()) == digest for name, digest in manifest.items())
    assert ready['code_sha256'] == code_hashes()
    raw = (FROZEN / 'request.FROZEN-NOT-AUTHORIZED.json').read_bytes()
    assert sha(raw) == REQUEST == ready['request_sha256']
    req = json.loads(raw)
    assert {k: v for k, v in req.items() if k != 'messages'} == dict(
        model='deepseek-flash', temperature=0, thinking={'type': 'disabled'},
        response_format={'type': 'json_object'}, max_tokens=16384)
    assert [m['role'] for m in req['messages']] == ['system', 'user']
    system, user = [m['content'] for m in req['messages']]
    assert system.encode() == (FROZEN / 'system-prompt.txt').read_bytes()
    assert user.encode() == (FROZEN / 'user-material.json').read_bytes()
    native = FROZEN / 'native/B-rich-evidence/web-experiment'
    assert raw == (native / 'request.json').read_bytes()
    native_manifest = json.loads((native / 'bundle.json').read_bytes())
    assert sha((native / 'bundle.json').read_bytes()) == ready['native_frozen_bundle_sha256']
    assert native_manifest['code'] == code_hashes()
    assert all(sha((native / name).read_bytes()) == digest for name, digest in native_manifest['files'].items())
    preflight = json.loads((FROZEN / 'real-request-preflight.json').read_bytes())
    assert datetime.now(UTC) < datetime.fromisoformat(preflight['preparation_valid_until'])
    value = _decode(json.loads((native / 'native-input.json').read_bytes()), cd.ContentDraftInput)
    assert MockArticleExecutor.request_for(value) == raw
    assert value.propose_interpretations and not value.customer_evidence.interpretations
    assert len(value.customer_evidence.sources) == ready['documents'] == 7
    assert sum(len(s.facts) for s in value.customer_evidence.sources) == ready['facts'] == 43
    import foreign_trade_geo_agent.core.draft_customer_evidence as ce
    functions = dict(parse_claim=workflow._parse_claim, parse_specification=workflow._parse_specification,
        validate_claim_evidence=cd._validate_claim_evidence, article_quality_findings=cd.article_quality_findings,
        finalize_draft_item=cd.finalize_draft_item, interpretation_proposal=ce.InterpretationProposal)
    summaries = json.loads((FROZEN / 'parser-validator-source-summary.json').read_bytes())
    assert all(sha(inspect.getsource(functions[name]).encode()) == summary['source_sha256']
               for name, summary in summaries.items())
    snapshot = _decode(json.loads((native / 'snapshot.json').read_bytes()), IntakeSnapshot)
    assert snapshot_digest(snapshot) == value.customer_evidence.snapshot_sha256
    facts = json.loads((FROZEN / 'native/customer-materials/facts.json').read_bytes())
    supplements = tuple(_decode(x, Supplement) for x in
        json.loads((FROZEN / 'native/customer-materials/documents.json').read_bytes()))
    reviewer = FactsOnlyReviewer(facts, supplements)
    now = datetime.now(UTC)
    assessment = reviewer.assess(snapshot, now=now)
    validate_assessment(snapshot, assessment, now=now)
    # Fresh TEST review metadata only, as in FrozenWebExecutor.load; no request,
    # fact, premise, Plan, brief, source version or snapshot changes.
    value = replace(value, customer_evidence=replace(value.customer_evidence, reviewed_at=now))
    assert cd.stable_content_draft_input_error(value) is None
    assert MockArticleExecutor.request_for(value) == raw
    return raw, value, snapshot, reviewer, dict(
        checked_at=now.isoformat(), request_sha256=REQUEST, bundle_sha256=BUNDLE,
        native_bundle_sha256=ready['native_frozen_bundle_sha256'], artifact_files=len(manifest),
        source_files=len(ready['code_sha256']), documents=7, facts=43,
        task_plan_brief_evidence_prompt_validator_unchanged=True,
        parameters={k: v for k, v in req.items() if k != 'messages'}, timeout_seconds=60,
        owner_authorization='Current user explicitly authorizes one exact frozen-v1 Flash quality experiment.',
        public_verification='Official DeepSeek search-index documentation checked 2026-10-12; direct web fetch timed out.',
        price_source='https://api-docs.deepseek.com/quick_start/pricing/',
        parameter_source='https://api-docs.deepseek.com/api/create-chat-completion',
        usd_per_million_peak=dict(cache_hit=.006, cache_miss=.3, output=1.2),
        usd_per_million_off_peak=dict(cache_hit=.003, cache_miss=.15, output=.6),
        exact_tokenizer_verified=False, input_65536_output_16384_peak_scenario_usd=.0393216,
        scenario_is_not_proven_bound_or_billing_cap=True, retries=0, fallback=0, repairs=0,
        production_authorized=False, wordpress_authorized=False, human_signoff=False)


def cost(usage, started_at):
    peak = started_at.weekday() < 5 and (1 <= started_at.hour < 4 or 6 <= started_at.hour < 10)
    rates = dict(cache_hit=.006, cache_miss=.3, output=1.2) if peak else dict(cache_hit=.003, cache_miss=.15, output=.6)
    required = ('prompt_cache_hit_tokens', 'prompt_cache_miss_tokens', 'completion_tokens')
    valid = type(usage) is dict and all(type(usage.get(k)) is int and usage[k] >= 0 for k in required)
    estimate = sum(usage[k] * rates[r] for k, r in zip(required, rates)) / 1e6 if valid else None
    return dict(currency='USD', estimate_only=True, billed_amount_verified=False,
        usage=usage, period='PEAK' if peak else 'OFF_PEAK', usd_per_million=rates,
        estimated_total_usd=estimate, request_started_at=started_at.isoformat(),
        formula='(cache_hit_tokens*cache_hit_rate + cache_miss_tokens*cache_miss_rate + completion_tokens*output_rate)/1000000',
        source='https://api-docs.deepseek.com/quick_start/pricing/')


async def execute():
    raw, value, snapshot, reviewer, preflight = verify()
    assert not (OUT / 'attempt-started.json').exists(), 'ATTEMPT_ALREADY_RESERVED'
    ledger = live_ledger()
    assert ledger.path.is_file(), 'FIXED_LEDGER_MISSING'
    with sqlite3.connect('file:' + ledger.path.as_posix() + '?mode=ro', uri=True) as db:
        assert not db.execute('SELECT permit FROM permits WHERE bundle=? OR request=? OR permit=?',
            (BUNDLE, REQUEST, PERMIT)).fetchall(), 'EXACT_REQUEST_ALREADY_RESERVED'
    load_api_keys('DEEPSEEK_API_KEY', project_root=ROOT)
    key = os.environ.get('DEEPSEEK_API_KEY', '').strip()
    assert key, 'CREDENTIALS_UNAVAILABLE'
    restrict_directory(OUT)
    write('preflight.json', preflight)
    save_bytes(OUT / 'request.json', raw)
    save_bytes(OUT / 'frozen-native-input.json', (FROZEN / 'native/B-rich-evidence/web-experiment/native-input.json').read_bytes())
    write('native-input.json', _encode(value))
    expiry = datetime.now(UTC) + timedelta(minutes=10)
    verify()
    ledger.issue(PERMIT, BUNDLE, OUT, REQUEST, 'LIVE', expiry)
    write('attempt-started.json', dict(started_at=datetime.now(UTC).isoformat(), permit=PERMIT,
        request_sha256=REQUEST, bundle_sha256=BUNDLE, max_requests=1, no_retry=True))
    ledger.claim(PERMIT, BUNDLE, OUT, REQUEST, 'LIVE')
    metadata = dict(request_sha256=REQUEST, bundle_sha256=BUNDLE, permit=PERMIT,
        production_authorized=False, wordpress_authorized=False, retries=0, fallback=0, repairs=0)
    events = []
    def event(stage, **fields):
        events.append(dict(stage=stage, at=datetime.now(UTC).isoformat(), **fields))
    started_at = datetime.now(UTC)
    started = time.perf_counter()

    class ObservedTransport(httpx.AsyncBaseTransport):
        def __init__(self):
            self.inner = httpx.AsyncHTTPTransport(retries=0, trust_env=False)
        async def handle_async_request(self, request):
            response = await self.inner.handle_async_request(request)
            # Credential-free response headers only. No request headers, cookies,
            # authorization values or raw credential-bearing exceptions persist.
            headers = {n: response.headers[n] for n in ('content-type', 'content-encoding', 'date', 'x-request-id') if n in response.headers}
            record = dict(status_code=response.status_code, http_version=response.http_version,
                response_headers=headers, captured_at=datetime.now(UTC).isoformat(),
                header_policy='Allowlist; sensitive headers omitted, body retained verbatim.')
            assert not contains_secret(json.dumps(record).encode(), key)
            write('http-response.json', record)
            return response
        async def aclose(self):
            await self.inner.aclose()

    guard = OneShotTransport(ObservedTransport(), raw, expires_at=expiry, request_limit=cd.MAX_INPUT_ENVELOPE_BYTES)

    async def validator(native, text):
        # receive_candidate has already fsynced original response and model text.
        body_raw = (OUT / 'response-body.bin').read_bytes()
        save_bytes(OUT / 'response.json', body_raw)
        body = json.loads(body_raw)  # Provider envelope, not model JSON.
        assert body['choices'][0]['message']['content'] == text
        metadata.update(raw_usage=body.get('usage'), actual_model=body.get('model'),
            provider_latency_seconds=round(time.perf_counter() - started, 6),
            latency_definition='POST start through complete body retention and provider-envelope extraction; excludes native parsing/validation.')
        write('provider-result.json', metadata)
        write('cost-estimate.json', cost(body.get('usage'), started_at))
        event('PROVIDER_RESPONSE_RETAINED', raw_json=True, model_text=True, usage_cost_latency=True)
        operation = native.change_plan_report.operations[0]
        try:
            workflow._parse_specification(text, expected_change_ref=operation.change_id, operation=operation)
        except Exception as exc:
            metadata.update(parser='FAIL', parser_error=str(exc) if type(exc) is ValueError else type(exc).__name__)
            write('candidate-validation.json', dict(parser='FAIL', error=metadata['parser_error'], validator='NOT_RUN'))
            event('JSON_PARSER_FAIL')
            raise
        metadata['parser'] = 'PASS'
        event('JSON_PARSER_PASS')
        check = workflow.inspect_candidate_output(native, text, current_snapshot_sha256=snapshot_digest(snapshot))
        write('candidate-validation.json', _encode(check))
        metadata.update(validator=check.state, candidate_errors=list(check.errors))
        event('CANDIDATE_VALIDATOR', state=check.state)
        journal = SQLiteLocalDraftReviewStore((OUT / 'local-review.sqlite3').resolve())
        revision = journal.append(origin_sha256=sha(text.encode()), expected_version=0, original_body=text,
            body_text=text, note='Exact live frozen-v1 output; no human or semantic approval.',
            status='PENDING_REVIEW', frozen_evidence_sha256=snapshot_digest(snapshot),
            observed_evidence_sha256=snapshot_digest(snapshot), saved_at=datetime.now(UTC))
        event('CANDIDATE_REVIEW_STORAGE', version=revision.version)
        metadata['candidate_stored'] = True
        if check.errors:
            save_bytes(OUT / 'rejected-candidate.txt', text.encode())
            metadata.update(test_only_review_replay='NOT_RUN_VALIDATOR_REJECTED', finalizer='NOT_RUN_VALIDATOR_REJECTED')
            event('STOP_VALIDATOR_REJECTED')
        else:
            proposed = tuple(c for c in check.claims if c.proposal is not None)
            if not proposed:
                metadata.update(test_only_review_replay='NOT_RUN_NO_PROPOSALS', finalizer='NOT_RUN_NO_PROPOSALS')
            else:
                decisions = tuple(CandidateDecision(check.binding_sha256, c.claim_id, 'APPROVE',
                    'TEST-only simulated review for replay; not human signoff or production approval.') for c in proposed)
                revision = journal.append(origin_sha256=sha(text.encode()), expected_version=revision.version,
                    original_body=text, body_text=text, note='TEST-only replay decisions, not human signoff.',
                    status='PENDING_REVIEW', frozen_evidence_sha256=snapshot_digest(snapshot),
                    observed_evidence_sha256=snapshot_digest(snapshot), saved_at=datetime.now(UTC), candidate_decisions=decisions)
                event('TEST_ONLY_REVIEW_REPLAY', proposals=len(proposed), human_signoff=False)
                now = datetime.now(UTC)
                reviewed, draft = test_only_revalidate_candidate(snapshot, reviewer.assess(snapshot, now=now),
                    native, text, revision, now=now)
                write('test-only-replay.json', dict(mode='TEST_ONLY_NOT_HUMAN_SIGNOFF',
                    production_authorized=False, reviewed_input=_encode(reviewed), draft=_encode(draft)))
                metadata.update(test_only_review_replay='PASS_TEST_ONLY', finalizer='PASS_TEST_ONLY')
                event('NATIVE_FINALIZER_PASS_TEST_ONLY')
                write('native-persistence.json', await asyncio.to_thread(persist_replay, OUT, reviewed, draft))
        return check

    try:
        event('SINGLE_POST_BEGIN')
        await asyncio.wait_for(receive_candidate(value, raw, guard, key, output=OUT,
            metadata=metadata, validator=validator, detail=lambda v, t, c: {'category': c}, timeout=60), timeout=60)
    except BaseException as exc:
        metadata.update(execution_error_type=type(exc).__name__, execution_failed=True,
            test_only_review_replay=metadata.get('test_only_review_replay', 'NOT_RUN'),
            finalizer=metadata.get('finalizer', 'NOT_RUN'))
        event('EXECUTION_STOP', exception_type=type(exc).__name__)
        if (OUT / 'response-body.bin').exists() and not (OUT / 'response.json').exists():
            save_bytes(OUT / 'response.json', (OUT / 'response-body.bin').read_bytes())
        if not (OUT / 'cost-estimate.json').exists():
            write('cost-estimate.json', cost(metadata.get('usage'), started_at))
    finally:
        metadata.update(real_requests=guard.calls, request_count=guard.calls,
            started_at=started_at.isoformat(), completed_at=datetime.now(UTC).isoformat(),
            end_to_end_seconds=round(time.perf_counter() - started, 6))
        write('execution-summary.json', metadata)
        write('stage-order.json', events)
        verify()
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    if sys.argv[1:] == ['--execute-once']:
        asyncio.run(execute())
    else:
        print(json.dumps(verify()[-1], ensure_ascii=False, indent=2))
