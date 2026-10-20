"""Isolated one-shot operator experiment; never a production/Web entry point.

No argument means offline help. Live use is bound to this request and deadline.
All production adapters, gates, prompts and validators remain unchanged.
"""
import asyncio
from datetime import UTC, datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

import httpx

from foreign_trade_geo_agent.adapters.deepseek_content_draft import DeepSeekContentDraftWriter
from foreign_trade_geo_agent.adapters.retained_deepseek import (
    ENDPOINT, OneShotTransport, retain_response, restrict_directory, save_bytes, require,
)
from foreign_trade_geo_agent.core import content_draft as cd
from foreign_trade_geo_agent.core.content_draft_review import render_draft_body_text
from foreign_trade_geo_agent.core.history import ArtifactType
from foreign_trade_geo_agent.storage.serialization import _decode, _encode, encode_artifact
from foreign_trade_geo_agent.storage.web_experiment import WebExperimentLedger
from foreign_trade_geo_agent.workflows.content_draft import ContentDraftWorkflow, _parse_specification

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
PRE = HERE.parent / 'seo-model-comparison-preflight-2026-10-11'
REQUEST_SHA = '991361f0eb58bfeb7fd557374faca7aae0093fd19a8e215586ca4c37593d8abc'
BUNDLE_SHA = 'c9b777110bb522d6ca47934acc8d6ddc8ac496b7b14f6055664a5b1431769957'
DEADLINE = datetime.fromisoformat('2026-10-11T14:30:00+08:00')
PERMIT = 'PRO-TEST-991361F0-20261011-143000'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save_json(path, value):
    save_bytes(path, json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode() + b'\n')


async def validate_candidate(value, text, output):
    operation = value.change_plan_report.operations[0]
    result = {'parser': 'NOT_RUN', 'validator_finalizer': 'NOT_RUN', 'trusted_human_signoff': False}
    try:
        _parse_specification(text, expected_change_ref=operation.change_id, operation=operation)
        result['parser'] = 'PASS'
    except ValueError as exc:
        result.update(parser='FAIL', parser_error=str(exc))

    class CapturedWriter:
        async def write_content_draft(self, prompt):
            return cd.ContentDraftGeneration('deepseek', 'deepseek-v4-pro',
                cd.ContentDraftGenerationStatus.SUCCESS, text, None)

    workflow = ContentDraftWorkflow(CapturedWriter(), max_repair_attempts=0)
    report = await workflow.run(value)
    success = report.status is cd.ContentDraftStatus.SUCCESS
    result.update(workflow_status=report.status.value, error=report.error,
                  validator_finalizer=('PASS' if success else 'FAIL') if result['parser'] == 'PASS' else 'NOT_REACHED',
                  requires_human_review=report.requires_human_review,
                  diagnostics={name: _encode(getattr(workflow, name)) for name in (
                      'last_numeric_grounding_violation', 'last_claim_type_violation',
                      'last_block_budget_violation', 'last_competitor_mention_violation')})
    save_bytes(output / 'native-report.json', encode_artifact(ArtifactType.CONTENT_DRAFT, report).encode())
    save_json(output / 'native-result.json', result)
    if success:
        save_bytes(output / 'article-body.md', (render_draft_body_text(report.drafts[0]) + '\n').encode())
    else:
        save_bytes(output / 'rejected-candidate.txt', text.encode())
    return success, report.error


async def execute(raw, value, transport, key, output, deadline, *, timeout=60):
    """Exact one-shot I/O with injected transport; caller owns durable claim.

    Mock tests can lower timeout. Live entry always uses 60 seconds and the
    fixed deadline. No network retries, redirects, alternative models or repair.
    """
    metadata = {'state': 'FAILED_TEST_ONLY', 'request_sha256': sha(raw), 'request_count': 0,
                'automatic_retries': 0, 'model_repair_requests': 0, 'response_complete': False,
                'production_authorized': False, 'wordpress_authorized': False,
                'trusted_human_signoff': False, 'started_at': datetime.now(UTC).isoformat()}
    guard = None
    started = time.monotonic()
    try:
        require(sha(raw) == REQUEST_SHA and len(raw) == 11413, 'FROZEN_REQUEST_CHANGED')
        require(0 < timeout <= 60 and datetime.now(UTC) < deadline, 'AUTHORIZATION_EXPIRED')
        require(cd.stable_content_draft_input_error(value) is None, 'NATIVE_INPUT_INVALID')
        guard = OneShotTransport(transport, raw, expires_at=deadline)

        async def receive():
            chunks, size, complete, received = [], 0, False, False
            try:
                async with httpx.AsyncClient(transport=guard, timeout=timeout, trust_env=False,
                        follow_redirects=False, headers={'Authorization': 'Bearer ' + key,
                                                       'Accept-Encoding': 'identity'}) as client:
                    async with client.stream('POST', ENDPOINT, content=raw,
                                             headers={'Content-Type': 'application/json'}) as response:
                        received = True
                        metadata.update(http_status=response.status_code,
                            content_encoded=response.headers.get('content-encoding', 'identity') != 'identity')
                        if response.is_stream_consumed:
                            size = len(response.content)
                            chunks.append(response.content[:65536])
                            require(size <= 65536, 'RESPONSE_BUDGET_EXCEEDED')
                        else:
                            async for chunk in response.aiter_raw():
                                chunks.append(chunk[:max(0, 65536 - size)])
                                size += len(chunk)
                                require(size <= 65536, 'RESPONSE_BUDGET_EXCEEDED')
                        complete = True
            finally:
                if received:
                    retain_response(output, metadata, b''.join(chunks), key, complete=complete)
            return b''.join(chunks)

        remaining = (deadline - datetime.now(UTC)).total_seconds()
        response_raw = await asyncio.wait_for(receive(), timeout=min(timeout, remaining))
        metadata['response_received_at'] = datetime.now(UTC).isoformat()
        body = json.loads(response_raw)
        require(type(body) is dict, 'PROVIDER_ENVELOPE_INVALID')
        choices = body.get('choices')
        finish = choices[0].get('finish_reason') if type(choices) is list and choices and type(choices[0]) is dict else None
        metadata['finish_reason'] = finish if type(finish) is str and len(finish) <= 128 else None
        usage = body.get('usage')
        if type(usage) is dict:
            metadata['usage'] = {k: v for k, v in usage.items() if k in {
                'prompt_tokens', 'completion_tokens', 'total_tokens', 'prompt_cache_hit_tokens',
                'prompt_cache_miss_tokens'} and type(v) is int and 0 <= v <= 1000000}
            details = usage.get('completion_tokens_details')
            if type(details) is dict and type(details.get('reasoning_tokens')) is int:
                metadata['reasoning_tokens'] = details['reasoning_tokens']
        extracted = DeepSeekContentDraftWriter._extract_text(body)
        if extracted is not None:
            save_bytes(output / 'model-output.txt', extracted[0].encode())
            metadata.update(model_text_sha256=sha(extracted[0].encode()), finish_reason=extracted[1])
        require(metadata['http_status'] == 200, 'PROVIDER_HTTP_FAILURE')
        require(body.get('model') == 'deepseek-v4-pro' and type(body.get('choices')) is list
                and len(body['choices']) == 1, 'PROVIDER_ENVELOPE_INVALID')
        metadata['returned_model'] = body['model']
        metadata['provider_created'] = body.get('created') if type(body.get('created')) is int else None
        fingerprint = body.get('system_fingerprint')
        metadata['system_fingerprint'] = fingerprint if type(fingerprint) is str and len(fingerprint) <= 200 else None
        require(extracted is not None and extracted[1] == 'stop', 'OUTPUT_INCOMPLETE')
        success, error = await validate_candidate(value, extracted[0], output)
        metadata['native_error'] = error
        require(success, 'NATIVE_VALIDATION_FAILED')
        metadata['state'] = 'SUCCEEDED_TEST_ONLY'
    except BaseException as exc:
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        safe_errors = {'FROZEN_REQUEST_CHANGED', 'AUTHORIZATION_EXPIRED', 'NATIVE_INPUT_INVALID',
            'RESPONSE_BUDGET_EXCEEDED', 'ENCODED_RESPONSE_REFUSED', 'SECRET_OUTPUT_REFUSED',
            'PROVIDER_HTTP_FAILURE', 'PROVIDER_ENVELOPE_INVALID', 'OUTPUT_INCOMPLETE', 'NATIVE_VALIDATION_FAILED'}
        metadata['failure'] = str(exc) if type(exc) is ValueError and str(exc) in safe_errors else type(exc).__name__
        candidate = output / 'model-output.txt'
        if candidate.exists() and not (output / 'rejected-candidate.txt').exists():
            save_bytes(output / 'rejected-candidate.txt', candidate.read_bytes())
    finally:
        metadata.update(request_count=guard.calls if guard else 0,
                        completed_at=datetime.now(UTC).isoformat(), elapsed_seconds=time.monotonic() - started)
        save_json(output / 'result.json', metadata)
    return metadata


async def live_once(expected_runner_sha):
    require(sha(Path(__file__).read_bytes()) == expected_runner_sha, 'RUNNER_CHANGED')
    require(datetime.now(UTC) < DEADLINE and (DEADLINE - datetime.now(UTC)).total_seconds() > 60,
            'AUTHORIZATION_EXPIRED_OR_INSUFFICIENT_WINDOW')
    # Recheck every frozen input, source hash and dependency; no credentials.
    spec = importlib.util.spec_from_file_location('frozen_preflight', PRE / 'check_offline.py')
    preflight = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(preflight)
    checked = await preflight.check()
    require(checked['manifest_sha256'] == BUNDLE_SHA, 'FROZEN_BUNDLE_CHANGED')
    raw = (PRE / 'request-v4-pro.json').read_bytes()
    require(sha(raw) == REQUEST_SHA, 'FROZEN_REQUEST_CHANGED')
    value = _decode(json.loads((PRE / 'baseline/native-input.json').read_bytes()), cd.ContentDraftInput)
    output = HERE / 'attempt'
    require(not output.exists(), 'ATTEMPT_ALREADY_RESERVED')
    local_app = Path(os.environ['LOCALAPPDATA'])
    ledger = WebExperimentLedger(local_app / 'foreign-trade-geo-agent/web-experiment/permits.sqlite3')
    ledger.initialize()
    restrict_directory(ledger.path.parent)
    ledger.issue(PERMIT, BUNDLE_SHA, output, REQUEST_SHA, 'LIVE', DEADLINE)
    ledger.claim(PERMIT, BUNDLE_SHA, output, REQUEST_SHA, 'LIVE')
    # Durable consumption above precedes directory, credentials and HTTP.
    output.mkdir(exist_ok=False)
    restrict_directory(output)
    save_bytes(output / 'request.json', raw)
    save_json(output / 'authorization.json', {
        'source': 'explicit project-owner user message in this chat', 'scope': 'TEST_ONLY_V4_PRO_SINGLE_POST',
        'permit': PERMIT, 'bundle_sha256': BUNDLE_SHA, 'request_sha256': REQUEST_SHA,
        'deadline': DEADLINE.isoformat(), 'runner_sha256': expected_runner_sha,
        'ledger_claimed_at': ledger.read(PERMIT)[7], 'max_requests': 1,
        'balance_queries_authorized': False, 'wordpress_authorized': False,
        'production_authorized': False, 'trusted_human_signoff': False})
    save_json(output / 'preexecution.json', checked)
    from dotenv import dotenv_values
    key = os.environ.get('DEEPSEEK_API_KEY') or dotenv_values(ROOT / '.env').get('DEEPSEEK_API_KEY')
    if not isinstance(key, str) or not key.strip():
        save_json(output / 'result.json', {'state': 'FAILED_TEST_ONLY', 'request_count': 0,
            'failure': 'CREDENTIAL_NOT_CONFIGURED', 'permit_consumed': True})
        return {'state': 'FAILED_TEST_ONLY', 'request_count': 0}
    require((DEADLINE - datetime.now(UTC)).total_seconds() > 60, 'AUTHORIZATION_EXPIRED_OR_INSUFFICIENT_WINDOW')
    result = await execute(raw, value, httpx.AsyncHTTPTransport(retries=0, trust_env=False), key,
                           output, DEADLINE, timeout=60)
    return {k: result.get(k) for k in ('state', 'request_count', 'finish_reason', 'usage', 'failure', 'native_error')}


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--live-once':
        print(json.dumps(asyncio.run(live_once(sys.argv[2])), ensure_ascii=False, indent=2))
    else:
        print('Offline default. This fixed experiment requires --live-once <reviewed runner SHA-256>.')
