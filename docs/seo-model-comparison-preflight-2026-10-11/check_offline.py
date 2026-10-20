"""Read-only preflight: local artifacts and MockTransport only; no live mode.

Run from the repository root with .venv/Scripts/python.exe <this file>.
The Pro-shaped mock contains historical Flash text, never a Pro sample.
"""
import asyncio
import copy
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
from unittest.mock import patch

import httpx

from foreign_trade_geo_agent.adapters.deepseek_content_draft import DeepSeekContentDraftWriter
from foreign_trade_geo_agent.adapters.retained_deepseek import OneShotTransport
from foreign_trade_geo_agent.core import content_draft as cd
from foreign_trade_geo_agent.storage.serialization import _decode
from foreign_trade_geo_agent.web.generation import MockArticleExecutor, canonical
from foreign_trade_geo_agent.workflows.content_draft import ContentDraftWorkflow

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
WORD_PATTERN = r"\b[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*\b"


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load(path):
    return json.loads(path.read_bytes())


def claims_in(draft):
    return [claim for section in draft['draft']['sections']
            for block in section['blocks'] for claim in block.get('claims', block.get('items', []))]


async def replay(value, text, model):
    class CapturedWriter:
        async def write_content_draft(self, prompt):
            return cd.ContentDraftGeneration('deepseek', model, cd.ContentDraftGenerationStatus.SUCCESS, text, None)
    return await ContentDraftWorkflow(CapturedWriter(), max_repair_attempts=0).run(value)


async def check():
    manifest_raw = (HERE / 'manifest.json').read_bytes()
    manifest = json.loads(manifest_raw)
    require(sha(manifest_raw) == (HERE / 'manifest.sha256').read_text().strip(), 'MANIFEST_CHANGED')
    for name, expected in manifest['files'].items():
        path = (HERE / name).resolve()
        require(path.is_relative_to(HERE) and sha(path.read_bytes()) == expected, 'ARTIFACT_CHANGED:' + name)
    for name, expected in manifest['code'].items():
        require(sha((ROOT / name).read_bytes()) == expected, 'CODE_CHANGED:' + name)
    for name, expected in manifest['dependencies'].items():
        require(importlib.metadata.version(name) == expected, 'DEPENDENCY_VERSION_CHANGED:' + name)

    baseline = HERE / 'baseline'
    historical = load(baseline / 'bundle.json')
    historical_raw = (baseline / 'bundle.json').read_bytes()
    require(sha(historical_raw) == (baseline / 'bundle.sha256').read_text().strip(), 'HISTORICAL_BUNDLE_CHANGED')
    for name, expected in historical['files'].items():
        require(sha((baseline / name).read_bytes()) == expected, 'HISTORICAL_INPUT_CHANGED:' + name)
    acceptance = load(baseline / 'acceptance-verification.json')
    flash_raw = (baseline / 'request.json').read_bytes()
    response_raw = (baseline / 'response-body.bin').read_bytes()
    text_raw = (baseline / 'model-output.txt').read_bytes()
    require(sha(flash_raw) == acceptance['request_sha256'], 'FLASH_REQUEST_CHANGED')
    require(sha(response_raw) == acceptance['response_sha256'], 'FLASH_RESPONSE_CHANGED')
    require(sha(text_raw) == manifest['flash_model_text_sha256'], 'FLASH_TEXT_CHANGED')
    envelope = json.loads(response_raw)
    extracted = DeepSeekContentDraftWriter._extract_text(envelope)
    require(extracted is not None and extracted[1] == 'stop'
            and extracted[0].encode() == text_raw, 'FLASH_TEXT_MISMATCH')
    require(envelope['model'] == 'deepseek-flash' and envelope['usage']['total_tokens'] == 3097, 'FLASH_BASELINE_MISMATCH')

    flash = json.loads(flash_raw)
    pro_raw = (HERE / 'request-v4-pro.json').read_bytes()
    pro = json.loads(pro_raw)
    require(pro_raw == flash_raw.replace(b'"model":"deepseek-flash"', b'"model":"deepseek-v4-pro"', 1), 'BYTE_DELTA_CHANGED')
    require(pro_raw == canonical(pro), 'REQUEST_SERIALIZATION_CHANGED')
    expected = copy.deepcopy(flash)
    expected['model'] = 'deepseek-v4-pro'
    require(pro == expected and pro['messages'] == flash['messages'], 'MORE_THAN_MODEL_CHANGED')
    require(pro['temperature'] == 0 and pro['thinking'] == {'type': 'disabled'}
            and pro['max_tokens'] == 3000 and len(pro_raw) <= 16000, 'PARAMETERS_CHANGED')
    value = _decode(load(baseline / 'native-input.json'), cd.ContentDraftInput)
    require(cd.stable_content_draft_input_error(value) is None, 'NATIVE_INPUT_INVALID')
    require(MockArticleExecutor.request_for(value) == flash_raw, 'CURRENT_PROMPT_DIFFERS')
    material = json.loads(pro['messages'][1]['content'])
    quote = material['customer_evidence']['sources'][0]['quote']
    source = value.customer_evidence.sources[0]
    require(source.content[source.span_start:source.span_end] == quote
            and source.evidence_id == 'E1' and source.requirement_ids == ('F1',), 'E1_MAPPING_CHANGED')

    # Only an injected MockTransport is used; all normal httpx network I/O fails.
    def reject_network(*args, **kwargs):
        raise RuntimeError('OFFLINE_NETWORK_FORBIDDEN')

    with patch.object(httpx.AsyncHTTPTransport, 'handle_async_request', reject_network), \
            patch.object(httpx.HTTPTransport, 'handle_request', reject_network):
        native_flash = await replay(value, text_raw.decode(), 'deepseek-flash')
        require(native_flash.status is cd.ContentDraftStatus.SUCCESS, 'FLASH_NATIVE_REPLAY_FAILED')
        # Test response contract compatibility only. This is historical Flash prose.
        mock_pro = copy.deepcopy(envelope)
        mock_pro['model'] = 'deepseek-v4-pro'
        calls = []

        def respond(request):
            calls.append(sha(request.content))
            require(request.content == pro_raw, 'MOCK_REQUEST_CHANGED')
            return httpx.Response(200, json=mock_pro)

        guard = OneShotTransport(httpx.MockTransport(respond), pro_raw)
        async with httpx.AsyncClient(transport=guard, trust_env=False, follow_redirects=False, timeout=60) as client:
            response = await client.post('https://api.deepseek.com/chat/completions', content=pro_raw,
                                         headers={'Content-Type': 'application/json'})
            candidate = response.json()
            require(candidate.get('model') == pro['model'] and len(candidate.get('choices', [])) == 1,
                    'PRO_ENVELOPE_INVALID')
            pro_text = DeepSeekContentDraftWriter._extract_text(candidate)
            require(pro_text is not None and pro_text[1] == 'stop', 'PRO_MOCK_INCOMPLETE')
            native_pro = await replay(value, pro_text[0], 'deepseek-v4-pro')
            require(native_pro.status is cd.ContentDraftStatus.SUCCESS, 'PRO_MODEL_METADATA_REJECTED')
            try:
                await client.post('https://api.deepseek.com/chat/completions', content=pro_raw)
            except ValueError as exc:
                require(str(exc) == 'SINGLE_REQUEST_GUARD', 'UNEXPECTED_REPEAT_REJECTION')
            else:
                raise ValueError('MOCK_REPEAT_NOT_BLOCKED')
        require(len(calls) == guard.calls == 1, 'MOCK_CALL_COUNT_INVALID')

        invalid = json.loads(text_raw)
        e_claim = next(c for c in claims_in(invalid) if c.get('customer_refs') == ['E1'])
        e_claim['text'] = e_claim['text'].replace('7200 rpm', '7300 rpm')
        rejected = await replay(value, json.dumps(invalid), 'deepseek-v4-pro')
        require(rejected.status is not cd.ContentDraftStatus.SUCCESS, 'MODIFIED_E_QUOTE_NOT_REJECTED')

    claims = claims_in(json.loads(text_raw))
    exact_source = [{'claim_id': 'CL' + str(i), 'whitespace_words': len(c['text'].split())}
                    for i, c in enumerate(claims, 1)
                    if c['text'] in material['sources'][0]['content'] and not c.get('customer_refs')]
    require(sum(c['whitespace_words'] for c in exact_source) == 73, 'BASELINE_COPY_METRIC_CHANGED')
    e_claims = [c for c in claims if c.get('customer_refs')]
    require(len(e_claims) == 1 and e_claims[0]['text'] == quote
            and not e_claims[0]['page_refs'] and not e_claims[0]['source_refs'], 'E1_NOT_INDEPENDENT')
    usage = envelope['usage']
    # CNY per million; zero cache benefit assumed for the conservative budget.
    input_budget, output_budget = Decimal(16000), Decimal(3000)
    divisor = Decimal(1000000)
    peak = (input_budget * Decimal('9') + output_budget * Decimal('27')) / divisor
    off_peak = (input_budget * Decimal('4.5') + output_budget * Decimal('13.5')) / divisor
    historical_estimate = (Decimal(usage['prompt_cache_hit_tokens']) * Decimal('.02')
                           + Decimal(usage['prompt_cache_miss_tokens'])
                           + Decimal(usage['completion_tokens']) * Decimal(4)) / divisor
    prior_changes = [name for name, expected in historical['code'].items()
                     if not (ROOT / name).exists() or sha((ROOT / name).read_bytes()) != expected]
    return {
        'status': 'READY_FOR_NEW_EXPLICIT_ONE_SHOT_AUTHORIZATION',
        'verified_at': datetime.now(timezone.utc).isoformat(),
        'manifest_sha256': sha(manifest_raw), 'request_sha256': sha(pro_raw), 'request_bytes': len(pro_raw),
        'only_request_difference': 'model: deepseek-flash -> deepseek-v4-pro',
        'current_native_request_matches_flash': True,
        'native_flash_replay': native_flash.status.value,
        'pro_shaped_mock_native_replay': native_pro.status.value,
        'mock_pro_text_origin': 'historical Flash; not a Pro generation or quality result',
        'changed_E_quote_rejected': True, 'changed_E_quote_error': rejected.error,
        'mock_http_attempts': len(calls), 'repeat_mock_request_rejected': True,
        'historical_code_changes': prior_changes,
        'flash_body_word_pattern': WORD_PATTERN,
        'flash_body_words_including_title_and_headings': len(re.findall(WORD_PATTERN, (baseline / 'article-body.md').read_text(encoding='utf-8'))),
        'flash_claim_words': sum(len(re.findall(WORD_PATTERN, c['text'])) for c in claims),
        'flash_claims': len(claims), 'flash_exact_S1_claims': exact_source,
        'flash_exact_S1_whitespace_words': 73,
        'flash_call_to_action_claims': sum(c['claim_type'] == 'CALL_TO_ACTION' for c in claims),
        'flash_actual_usage': usage, 'flash_usage_estimate_cny': str(historical_estimate),
        'pro_input_token_budget_estimate': int(input_budget), 'pro_max_tokens': int(output_budget),
        'pro_peak_budget_estimate_cny': str(peak), 'pro_off_peak_budget_estimate_cny': str(off_peak),
        'budget_is_not_account_spending_cap': True,
        'production_adapter_configurable': False,
        'existing_retained_runner_accepts_pro': False,
        'live_runner_implemented_or_armed': False,
        'quality_evaluation': 'not performed for Pro; no Pro sample exists',
        'trusted_human_signoff': False,
        'real_deepseek_requests_this_preflight': 0, 'balance_queries_this_preflight': 0,
        'wordpress_requests_this_preflight': 0,
    }


if __name__ == '__main__':
    print(json.dumps(asyncio.run(check()), ensure_ascii=False, indent=2))
