"""Isolated authorized experiment; default is offline verification, never retry."""
import asyncio
from dataclasses import asdict
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import sys
import tempfile
import time

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import prepare_seo_draft_v2_flash_preflight as frozen
from scripts.local_env import load_api_keys
from foreign_trade_geo_agent.adapters.retained_deepseek import (
    OneShotTransport, receive_candidate, restrict_directory, save_bytes, ENDPOINT,
)
from foreign_trade_geo_agent.core import content_draft as cd
from foreign_trade_geo_agent.storage.serialization import _decode
from foreign_trade_geo_agent.storage.draft_selection_contract import decode_selection_artifact

OUT = Path(__file__).resolve().parent
PACKAGE = ROOT / 'docs/seo-draft-v2-flash-experiment-preflight'
MANIFEST = '5bfc54d91e5c0ba24b3043ef10871e937a84a9ad2abae968ad0fd86f06f85754'
REQUEST = '67556e8190c96aa554dd7cadbfc40c30a4e96513e23de6e5c27c29426e4dea40'


def write(name, value):
    save_bytes(OUT / name, (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))


def verify():
    verified = frozen.verify_manifest(PACKAGE, MANIFEST)
    request = (PACKAGE / 'request-body-template.json').read_bytes()
    assert frozen.sha(request) == REQUEST, 'REQUEST_HASH_MISMATCH'
    value = _decode(json.loads((PACKAGE / 'native-input.json').read_bytes()), cd.ContentDraftInput)
    selection = decode_selection_artifact((PACKAGE / 'selection-artifact.json').read_text(encoding='utf-8'))
    config = json.loads((PACKAGE / 'experiment-config.json').read_bytes())
    assert frozen.selection_digest(selection) == config['selection_sha256']
    assert value.customer_evidence.snapshot_sha256 == config['evidence_snapshot_sha256']
    assert selection.plan_sha256 == config['plan_sha256']
    assert {k: v for k, v in json.loads(request).items() if k != 'messages'} == frozen.PARAMETERS
    hashes = {name: frozen.sha((PACKAGE / name).read_bytes()) for name in (
        'manifest.json', 'request-body-template.json', 'selection-artifact.json',
        'evidence-snapshot.json', 'plan.json', 'source-integrity.json')}
    return request, value, selection, dict(**verified, checked_at=datetime.now(UTC).isoformat(),
        file_sha256=hashes, domain_bindings={k: config[k] for k in (
            'selection_sha256', 'evidence_snapshot_sha256', 'plan_sha256')},
        source_files=len(frozen.source_integrity()), source_unchanged=True,
        parameters=frozen.PARAMETERS, timeout_seconds=60,
        owner_authorization='Current user: one exact frozen request; no retry/fallback/repair.',
        public_documentation_lookups=1, deepseek_api_requests_before_execution=0)


def cost(usage, started_at):
    keys = ('prompt_tokens', 'completion_tokens', 'total_tokens',
            'prompt_cache_hit_tokens', 'prompt_cache_miss_tokens')
    valid = type(usage) is dict and all(type(usage.get(k)) is int and 0 <= usage[k] <= 1_000_000 for k in keys)
    valid = valid and usage['total_tokens'] == usage['prompt_tokens'] + usage['completion_tokens']
    valid = valid and usage['prompt_tokens'] == usage['prompt_cache_hit_tokens'] + usage['prompt_cache_miss_tokens']
    valid = valid and usage['completion_tokens'] <= 16384
    # At this experiment's UTC afternoon time neither weekday peak window applies.
    peak = started_at.weekday() < 5 and (1 <= started_at.hour < 4 or 6 <= started_at.hour < 10)
    rates = dict(cache_hit=.006, cache_miss=.3, output=1.2) if peak else dict(cache_hit=.003, cache_miss=.15, output=.6)
    estimate = ((usage['prompt_cache_hit_tokens'] * rates['cache_hit']
        + usage['prompt_cache_miss_tokens'] * rates['cache_miss']
        + usage['completion_tokens'] * rates['output']) / 1e6) if valid else None
    return dict(usage=usage, usage_valid=bool(valid), currency='USD', estimated_total_usd=estimate,
        rates_per_million=rates, period='PEAK' if peak else 'OFF_PEAK',
        formula='(cache_hit*hit_rate + cache_miss*miss_rate + completion*output_rate)/1000000',
        official_price_verified=True, source='https://api-docs.deepseek.com/quick_start/pricing/',
        source_checked_date='2026-10-12', estimate_only=True, invoice_verified=False,
        further_experiments_authorized=False)


async def offline_check():
    raw, value, selection, verification = verify()
    candidate, sidecar, result = frozen.parse_experiment_response(
        (PACKAGE / 'synthetic-response-envelope.json').read_text(encoding='utf-8'), value, selection)
    assert result.state == 'PENDING_SEMANTIC_REVIEW'
    observed = []
    async def handler(request):
        observed.append(request.content)
        return httpx.Response(200, json={'ok': True})
    guard = OneShotTransport(httpx.MockTransport(handler), raw, request_limit=cd.MAX_INPUT_ENVELOPE_BYTES)
    async with httpx.AsyncClient(transport=guard, follow_redirects=False) as client:
        await client.post(ENDPOINT, content=raw)
        try:
            await client.post(ENDPOINT, content=raw)
        except ValueError as exc:
            assert str(exc) == 'SINGLE_REQUEST_GUARD'
        else:
            raise AssertionError('SECOND_REQUEST_NOT_BLOCKED')
    assert observed == [raw] and guard.calls == 1
    print(json.dumps(dict(offline_check='PASS', real_api_calls=0,
        frozen_verification=verification, synthetic_parser_validator=result.state,
        mocked_exact_byte_requests=1, mocked_second_request='BLOCKED'), indent=2))


async def execute():
    assert not (OUT / 'attempt-started.json').exists(), 'ATTEMPT_ALREADY_RESERVED'
    raw, value, selection, verified = verify()
    load_api_keys('DEEPSEEK_API_KEY', project_root=ROOT)
    key = os.environ.get('DEEPSEEK_API_KEY', '').strip()
    assert key, 'CREDENTIALS_UNAVAILABLE'
    restrict_directory(OUT)
    write('preflight.json', verified)
    save_bytes(OUT / 'request.json', raw)
    write('pricing-verification.json', dict(source='https://api-docs.deepseek.com/quick_start/pricing/',
        checked_date='2026-10-12', model='deepseek-flash', current_backend='DeepSeek-V4.1-Flash',
        official_documentation_verified=True, off_peak_usd_per_million=dict(cache_hit=.003, cache_miss=.15, output=.6),
        peak_usd_per_million=dict(cache_hit=.006, cache_miss=.3, output=1.2),
        parameters_supported=True, exact_tokenizer_verified=False))
    verify()  # Last source/package check immediately before reserving the sole attempt.
    write('attempt-started.json', dict(at=datetime.now(UTC).isoformat(), manifest_sha256=MANIFEST,
        request_sha256=REQUEST, max_requests=1, authorization_consumed=True))
    meta = dict(http_status=None, finish_reason=None, usage=None, parser='NOT_RUN', validator='NOT_RUN',
        finalizer='NOT_RUN', semantic_approved=False, commercial_approved=False,
        production_authorized=False, wordpress_calls=0, retries=0, fallback=0, repairs=0,
        experiment_status='REAL_EXPERIMENT_BLOCKED')
    events = []
    started_at = datetime.now(UTC)
    started = time.perf_counter()
    guard = OneShotTransport(httpx.AsyncHTTPTransport(retries=0, trust_env=False), raw,
        request_limit=cd.MAX_INPUT_ENVELOPE_BYTES)

    async def validator(native, text):
        meta['latency_seconds'] = round(time.perf_counter() - started, 6)
        meta['latency_scope'] = 'POST through complete response retention and envelope extraction; before Parser/Validator'
        save_bytes(OUT / 'model-output.json', text.encode('utf-8'))
        body = json.loads((OUT / 'response-body.bin').read_bytes())
        meta['actual_model'] = body.get('model')
        meta['raw_usage'] = body.get('usage')
        billed = cost(body.get('usage'), started_at)
        write('cost-estimate.json', billed)
        if not billed['usage_valid']:
            raise ValueError('USAGE_ANOMALY')
        events.append('RESPONSE_AND_USAGE_SAVED')
        meta['parser'] = 'FAIL'
        candidate, sidecar, check = frozen.parse_experiment_response(text, native, selection)
        meta['parser'] = 'PASS'
        events.append('PARSER_PASS')
        save_bytes(OUT / 'candidate.json', candidate.encode('utf-8'))
        write('explanation-sidecar.json', asdict(sidecar))
        write('candidate-validation.json', asdict(check))
        meta['validator'] = 'FAIL' if check.errors else 'PASS'
        meta['validator_errors'] = list(check.errors)
        meta['candidate_state'] = check.state
        events.append('VALIDATOR_' + meta['validator'])
        if check.errors:
            # Strict stop: never finalize, repair, regenerate or change contracts.
            raise ValueError('VALIDATOR_FAILED')
        meta['experiment_status'] = 'REAL_EXPERIMENT_COMPLETED'
        return check

    try:
        async with asyncio.timeout(60):
            await receive_candidate(value, raw, guard, key, output=OUT, metadata=meta,
                validator=validator, detail=lambda *_: 'UNCHANGED_OUTPUT_NO_REPAIR', timeout=60)
    except Exception as exc:
        # Error classes and locally defined tokens only; never log provider exceptions/credentials.
        safe = {'VALIDATOR_FAILED', 'PREFLIGHT_RESPONSE_INVALID', 'USAGE_ANOMALY',
                'PROVIDER_HTTP_FAILURE', 'PROVIDER_ENVELOPE_INVALID', 'OUTPUT_INCOMPLETE',
                'PROVIDER_JSON_FORMAT', 'SECRET_OUTPUT_REFUSED', 'ENCODED_RESPONSE_REFUSED'}
        meta['failure'] = str(exc) if type(exc) is ValueError and str(exc) in safe else type(exc).__name__
        meta['experiment_status'] = 'REAL_EXPERIMENT_BLOCKED'
        events.append('STOP_NO_RETRY')
    finally:
        meta['request_count'] = guard.calls
        meta['attempt_elapsed_seconds'] = round(time.perf_counter() - started, 6)
        meta['request_started_at'] = started_at.isoformat()
        if not (OUT / 'model-output.json').exists() and (OUT / 'model-output.txt').exists():
            save_bytes(OUT / 'model-output.json', (OUT / 'model-output.txt').read_bytes())
        if not (OUT / 'cost-estimate.json').exists():
            write('cost-estimate.json', cost(meta.get('usage'), started_at))
        write('execution-summary.json', meta)
        write('stage-order.json', events)
    print(json.dumps(meta, indent=2))


if __name__ == '__main__':
    asyncio.run(execute() if sys.argv[1:] == ['--execute-once'] else offline_check())
