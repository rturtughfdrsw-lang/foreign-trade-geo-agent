"""Case-local audit: existing freezer/executor, copied evidence, MOCK only.

Run from repository root. Exclusive output; never reads keys or live ledger.
This is an audit artifact, not another freezing or authorization implementation.
"""
import asyncio
from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path
import shutil
import sys
from unittest.mock import patch

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT))
import httpx
from scripts.accept_autonomous_interpretation import FactsOnlyReviewer
from foreign_trade_geo_agent.core import content_draft as cd
from foreign_trade_geo_agent.core.evidence_intake import Supplement, snapshot_digest
from foreign_trade_geo_agent.storage.serialization import _decode, _encode
from foreign_trade_geo_agent.storage.web_experiment import WebExperimentLedger
from foreign_trade_geo_agent.web.mvp_application import MVPApplicationService
from foreign_trade_geo_agent.web.experiment import freeze, FrozenWebExecutor, code_hashes
from foreign_trade_geo_agent.web.generation import canonical, MockArticleExecutor
from foreign_trade_geo_agent.workflows.content_draft import inspect_candidate_output, ContentDraftWorkflow

HERE = Path(__file__).resolve().parent
OLD = ROOT / 'docs/seo-prompt-contract-fix-2026-10-12/final-v2'
HISTORY = ROOT / 'docs/seo-flash-quality-live-2026-10-12'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as f:
        f.write(canonical(value))


def main():
    bundle = HERE / 'frozen-v1'
    bundle.mkdir(exist_ok=False)
    rich = bundle / 'native/B-rich-evidence'
    rich.mkdir(parents=True)
    prior = OLD / 'native/B-rich-evidence'
    ready = json.loads((OLD / 'readiness.json').read_bytes())
    manifest = json.loads((OLD / 'artifact-sha256.json').read_bytes())
    assert ready['code_sha256'] == code_hashes()
    assert all(sha((OLD / n).read_bytes()) == h for n, h in manifest.items())
    assert sha((OLD / 'artifact-sha256.json').read_bytes()) == (OLD / 'bundle.sha256').read_text().strip()
    for name in ('session.json', 'interactive-intake.sqlite3'):
        shutil.copyfile(prior / name, rich / name)
    (rich / 'candidate').mkdir()
    shutil.copyfile(prior / 'candidate/history.sqlite3', rich / 'candidate/history.sqlite3')
    shutil.copytree(OLD / 'native/customer-materials', bundle / 'customer-materials')
    for name in ('task-plan-brief.json', 'facts-source-map.json', 'output-contract.json', 'schema-examples.json'):
        shutil.copyfile(OLD / name, bundle / name)
    value = _decode(json.loads((prior / 'web-experiment/native-input.json').read_bytes()), cd.ContentDraftInput)
    service = MVPApplicationService(rich)
    facts = json.loads((bundle / 'customer-materials/facts.json').read_bytes())
    supplements = tuple(_decode(x, Supplement) for x in json.loads((bundle / 'customer-materials/documents.json').read_bytes()))
    service.scope_reviewer = FactsOnlyReviewer(facts, supplements)
    service.generation_executor = MockArticleExecutor(task=_decode(json.loads((prior / 'snapshot.json').read_bytes())['task'],
        __import__('foreign_trade_geo_agent.core.evidence_intake', fromlist=['EvidenceTask']).EvidenceTask),
        template=value, transport=httpx.MockTransport(lambda r: (_ for _ in ()).throw(AssertionError('FREEZE MUST NOT SEND'))))
    # Existing compliant TEST review validates exact dossier, versions and scope;
    # fresh timestamp is not human approval or permission to make a model call.
    execution_bundle = freeze(service)
    session, _, store, _, _ = service._load()
    current = service._current(store, session)
    raw = (rich / 'web-experiment/request.json').read_bytes()
    assert raw == (OLD / 'request.FROZEN-NOT-AUTHORIZED.json').read_bytes()
    request = json.loads(raw)
    system, user = (m['content'] for m in request['messages'])
    assert [m['role'] for m in request['messages']] == ['system', 'user']
    assert {k: v for k, v in request.items() if k != 'messages'} == dict(
        model='deepseek-flash', temperature=0, thinking={'type': 'disabled'},
        response_format={'type': 'json_object'}, max_tokens=16384)
    assert 'E CANDIDATE MODE' in system and 'PENDING_SEMANTIC_REVIEW' in system
    forbidden = ('Every claim is exactly {"text","claim_type","page_refs","source_refs"}',
        'must cite at least one P page', 'Keep every claim short and lexically grounded', 'supersedes')
    assert all(s not in system for s in forbidden)
    assert value.propose_interpretations and not value.customer_evidence.interpretations
    assert len(value.customer_evidence.sources) == 7
    assert sum(len(s.facts) for s in value.customer_evidence.sources) == 43
    material = json.loads(user)
    assert len(material['contract']['customer_refs']) == 43
    assert len(material['change']['new_resource']['section_briefs']) == 6
    assert 'PLANNING_CONTEXT_ONLY' in material['contract']['page_source_role']
    historical = _decode(json.loads((HISTORY / 'native-input.json').read_bytes()), cd.ContentDraftInput)
    assert value.change_plan_report == historical.change_plan_report
    assert value.customer_evidence.sources == historical.customer_evidence.sources
    assert snapshot_digest(current) == value.customer_evidence.snapshot_sha256
    assert current.plan_bound and current.task == service.generation_executor.task
    for name, data in [('request.FROZEN-NOT-AUTHORIZED.json', raw),
                       ('system-prompt.txt', system.encode()), ('user-material.json', user.encode())]:
        with (bundle / name).open('xb') as f:
            f.write(data)
    save(bundle / 'source-sha256.json', code_hashes())
    shutil.copyfile(HERE / 'official-verification.json', bundle / 'official-verification.json')

    old_request = json.loads((HISTORY / 'request.json').read_bytes())
    old_input = ''.join(m['content'] for m in old_request['messages'])
    usage = json.loads((HISTORY / 'response-body.bin').read_bytes())['usage']
    text = system + user
    def measure(s):
        return dict(characters=len(s), utf8_bytes=len(s.encode()),
            official_english_ratio_estimate=round(len(s) * .3, 1),
            ratio_is_approximate_not_bound=True)
    tokens = dict(system=measure(system), user=measure(user), complete_request_json=measure(raw.decode()),
        input=measure(text), historical_input_characters=len(old_input), historical_observed_usage=usage,
        history_scaled_estimate=round(usage['prompt_tokens'] * len(text) / len(old_input), 1),
        planning_input_tokens=65536, planning_assumption='Conservative scenario: over twice entire current request UTF-8 bytes; not a mathematical token bound.',
        max_output_tokens=16384, planning_total_context_tokens=81920,
        official_context='1M', conservative_context_for_arithmetic=1000000,
        estimated_remaining_context_tokens=1000000-81920,
        status='ESTIMATED_TOKEN_FEASIBILITY', exact_token_bound_verified=False,
        official_tokenizer_url='https://cdn.deepseek.com/api-docs/deepseek_v4_tokenizer.zip',
        official_tokenizer_sha256=sha((HERE / 'official-tokenizer.zip').read_bytes()),
        tokenizer_execution='NOT_RUN: no tokenizers/transformers in project venv; no dependency installation or custom counter.',
        tokenizer_matching='UNVERIFIED for exact V4.1-Flash server framing/version; package config says model_max_length=16384 while current API docs say 1M. Config is not used as API limit.',
        actual_current_request_usage=None, owner_risk_acceptance=False,
        uncertainty='Ratio, historical scaling and planning scenario are estimates. Only future response usage is billed truth; tokenization and service-side framing may differ.')
    save(bundle / 'token-budget.json', tokens)
    peak_cost = (65536 * .3 + 16384 * 1.2) / 1e6
    assert peak_cost <= .05
    cost = dict(currency='USD', input_cache_hit_per_million={'off_peak': .003, 'peak': .006},
        input_cache_miss_per_million={'off_peak': .15, 'peak': .3},
        output_per_million={'off_peak': .6, 'peak': 1.2},
        assumed_cache_hit_tokens=0, input_scenario_tokens=65536, max_output_tokens=16384,
        conservative_peak_scenario_usd=peak_cost, conservative_off_peak_scenario_usd=peak_cost/2,
        approximate_ratio_input_max_output_peak_usd=(len(text)*.3*.3+16384*1.2)/1e6,
        approximate_ratio_input_historical_output_peak_usd=(len(text)*.3*.3+3387*1.2)/1e6,
        proposed_limit_usd=.05, actual_spending_authorized_usd=0,
        strict_cost_upper_bound_verified=False, provider_bill_cap_enforced=False,
        budget_input_break_even_tokens_at_max_output=(.05*1e6-16384*1.2)/.3,
        formula='(input_tokens * peak_cache_miss_price + max_output_tokens * peak_output_price) / 1_000_000',
        peak_hours_utc='Monday-Friday excluding Chinese public holidays: 01:00-04:00 and 06:00-10:00; all other hours off-peak.',
        limitations='USD 0.05 is a proposed owner budget, not an API-enforced billing limit. Token estimate and current public rates are assumptions; timeout does not prove server generation stopped or zero billing.',
        account_balance_queried=False)
    save(bundle / 'cost-budget.json', cost)
    save(bundle / 'request-consistency.json', dict(old_files_checked=len(manifest), old_code_files_checked=len(ready['code_sha256']),
        old_bundle_valid=True, request_identical_to_prompt_fix=True, prompt_mode='E_CANDIDATE', old_ps_conflicts=False,
        documents=7, facts=43, sections=6, supplied_interpretations=0,
        task_and_plan_bound=True, writing_brief_bound=True, native_stable_validation='PASS_BY_EXISTING_FREEZER',
        snapshot_sha256=snapshot_digest(current), task_version=value.customer_evidence.task_version,
        plan_version=value.customer_evidence.plan_version, evidence_version=value.customer_evidence.evidence_version,
        snapshot_revision=value.customer_evidence.snapshot_revision, refreshed_test_review=True,
        human_semantic_signoff=False, live_permit=False, wordpress_permission=False))

    # A single frozen-executor drill reuses the existing legal Mock article.
    # No second article generation, review approval, LIVE permit or WordPress.
    drill = HERE / 'mock-drill'
    drill.mkdir()
    ledger = WebExperimentLedger(drill / 'MOCK-only-ledger.sqlite3')
    ledger.initialize()
    permit = 'MOCK-FLASH-PREFLIGHT-2026-10-12'
    ledger.issue(permit, execution_bundle, rich, sha(raw), 'MOCK', datetime.now(UTC)+timedelta(minutes=5))
    captured = []
    mock_raw = (prior / 'mock-response.json').read_text(encoding='utf-8')
    def handler(req):
        assert req.content == raw and str(req.url) == 'https://api.deepseek.com/chat/completions'
        assert ledger.read(permit)[7] is not None
        captured.append(req.content)
        return httpx.Response(200, json=dict(model='deepseek-flash', choices=[dict(message={'content': mock_raw}, finish_reason='stop')]))
    executor = FrozenWebExecutor(rich, execution_bundle, ledger, permit, transport=httpx.MockTransport(handler))
    native, loaded = executor.load(current)
    assert loaded == raw
    ledger.claim(permit, execution_bundle, rich, sha(raw), 'MOCK')
    metadata = dict(mode='MOCK', request_sha256=sha(raw), usage_is_not_real=True)
    async def run():
        try:
            await executor.execute(native, loaded, drill, metadata)
        except ValueError as exc:
            assert str(exc) == 'INTERPRETATION_PENDING_REVIEW'
        else:
            raise AssertionError('Unreviewed candidate admitted')
        class CapturedWriter:
            async def write_content_draft(self, prompt):
                return cd.ContentDraftGeneration('mock', 'offline', cd.ContentDraftGenerationStatus.SUCCESS, mock_raw, None)
        report = await ContentDraftWorkflow(CapturedWriter(), max_repair_attempts=0).run(native)
        assert report.error == 'INTERPRETATION_PENDING_REVIEW' and not report.drafts
        return report.error
    with patch('httpx.AsyncHTTPTransport', side_effect=AssertionError('NO REAL TRANSPORT')), \
         patch('httpx.HTTPTransport', side_effect=AssertionError('NO REAL TRANSPORT')), \
         patch('scripts.local_env.load_api_keys', side_effect=AssertionError('NO CREDENTIALS')):
        formal_error = asyncio.run(run())
    assert len(captured) == metadata['request_count'] == 1 and metadata['real_requests'] == 0
    assert metadata['candidate_state'] == 'PENDING_SEMANTIC_REVIEW' and not metadata['candidate_errors']
    old_check = inspect_candidate_output(native, (HISTORY / 'model-output.txt').read_text(encoding='utf-8'),
        current_snapshot_sha256=snapshot_digest(current))
    assert old_check.state == 'DETERMINISTICALLY_REJECTED'
    # The durable claim is spent after the Mock; never retry or promote it.
    try:
        ledger.claim(permit, execution_bundle, rich, sha(raw), 'MOCK')
    except ValueError as exc:
        assert str(exc) == 'PERMIT_EXPIRED_OR_CONSUMED'
    else:
        raise AssertionError('Permit reused')
    save(drill / 'result.json', metadata)
    save(bundle / 'mock-only-result.json', dict(executor='FrozenWebExecutor', execution_bundle_sha256=execution_bundle,
        request_bytes_equal=True, request_sha256=sha(raw), requests=1, real_requests=0, wordpress_requests=0,
        candidate_state=metadata['candidate_state'], candidate_errors=[],
        pending_saved=(drill / 'local-review.sqlite3').is_file(), formal_draft_error=formal_error,
        formal_drafts=0, old_response_state=old_check.state, old_response_errors=list(old_check.errors),
        mock_response_sha256=metadata['response_sha256'], mock_raw_response=str((drill / 'response-body.bin').relative_to(ROOT)),
        source_response=str((prior / 'mock-response.json').relative_to(ROOT)),
        second_claim='PERMIT_EXPIRED_OR_CONSUMED', live_permits=0, semantic_approvals=0, production_gate_changes=0))
    save(bundle / 'readiness.json', dict(OFFLINE_E_CANDIDATE_READY=True,
        REAL_REQUEST_PREFLIGHT_READY='READY_CONDITIONAL_ON_EXPLICIT_OWNER_ESTIMATE_RISK_ACCEPTANCE',
        ESTIMATED_TOKEN_FEASIBILITY=True, EXACT_TOKEN_BOUND_VERIFIED=False,
        REAL_FLASH_INSTRUCTION_FOLLOWING_UNTESTED=True, REAL_WRITING_QUALITY_UNTESTED=True,
        PRODUCTION_NO_GO=True, request_sha256=sha(raw), execution_bundle_sha256=execution_bundle,
        live_permit_issued=False, real_requests=0, wordpress_requests=0, owner_risk_acceptance=False,
        checked_at=datetime.now(UTC).isoformat(), preparation_valid_until=(datetime.now(UTC)+timedelta(hours=24)).isoformat(),
        hard_technical_blockers=[], authorization_blockers=['New explicit authorization for outer + execution bundle and exact request.',
            'Owner must explicitly accept estimated token/cost risk and USD 0.05 proposed budget.'],
        future_permit_minutes=10, proposed_budget_usd=.05))
    print(json.dumps(dict(request_sha256=sha(raw), execution_bundle_sha256=execution_bundle,
        characters=len(text), input_estimate=tokens['history_scaled_estimate'], peak_scenario_usd=peak_cost,
        mock='PENDING_SEMANTIC_REVIEW', formal_draft=formal_error), indent=2))


if __name__ == '__main__':
    main()
