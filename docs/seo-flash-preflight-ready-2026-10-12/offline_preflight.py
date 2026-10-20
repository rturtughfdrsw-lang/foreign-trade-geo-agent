"""Case-local offline audit. Reuses the existing freeze/executor; no LIVE path.

Run from the repository root using the venv Python. Exclusive output creation.
This file is an audit recipe, not a new runtime or authorization mechanism.
"""
import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path
import shutil
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import httpx
from scripts.accept_autonomous_interpretation import FactsOnlyReviewer
from foreign_trade_geo_agent.core import content_draft as cd
from foreign_trade_geo_agent.core.evidence_intake import snapshot_digest
from foreign_trade_geo_agent.storage.serialization import _decode, _encode
from foreign_trade_geo_agent.storage.web_experiment import WebExperimentLedger
from foreign_trade_geo_agent.web.mvp_application import MVPApplicationService
from foreign_trade_geo_agent.web.generation import MockArticleExecutor, canonical
from foreign_trade_geo_agent.web.experiment import (
    freeze, FrozenWebExecutor, FrozenWebGeneration, code_hashes,
)
from foreign_trade_geo_agent.workflows.content_draft import ContentDraftWorkflow, inspect_candidate_output

OUT = Path(__file__).resolve().parent
OLD = ROOT / 'docs/seo-prompt-contract-fix-2026-10-12/final-v2'
HISTORY = ROOT / 'docs/seo-flash-quality-live-2026-10-12'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def save(path, value):
    with path.open('xb') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2).encode())


async def prepare():
    prior_ready = read(OLD / 'readiness.json')
    assert prior_ready['code_sha256'] == code_hashes()
    assert all(sha((OLD / n).read_bytes()) == h for n, h in read(OLD / 'artifact-sha256.json').items())
    old_rich = OLD / 'native/B-rich-evidence'
    value = _decode(read(old_rich / 'web-experiment/native-input.json'), cd.ContentDraftInput)
    snapshot = _decode(read(old_rich / 'web-experiment/snapshot.json'),
                       __import__('foreign_trade_geo_agent.core.evidence_intake', fromlist=['IntakeSnapshot']).IntakeSnapshot)
    assert value.propose_interpretations and not value.customer_evidence.interpretations
    assert len(value.customer_evidence.sources) == 7
    assert sum(len(s.facts) for s in value.customer_evidence.sources) == 43
    assert snapshot.plan_bound and len(value.change_plan_report.operations[0].new_resource_spec.section_briefs) == 6
    facts = read(OLD / 'native/customer-materials/facts.json')
    reviewer = FactsOnlyReviewer(facts, tuple(e.supplement for e in snapshot.active_evidence))
    # Existing exact fixture/scope/validity review, with no interpretation approval.
    assessment = reviewer.assess(snapshot, now=datetime.now(UTC))
    assert assessment.snapshot_sha256 == snapshot_digest(snapshot) and not assessment.interpretations
    raw = MockArticleExecutor.request_for(value)
    assert raw == (OLD / 'request.FROZEN-NOT-AUTHORIZED.json').read_bytes()
    request = json.loads(raw)
    system, user = [m['content'] for m in request['messages']]
    assert system.encode() == (OLD / 'system-prompt.txt').read_bytes()
    assert user.encode() == (OLD / 'user-material.json').read_bytes()
    assert 'E CANDIDATE MODE' in system
    forbidden = ['Every claim is exactly {"text","claim_type","page_refs","source_refs"}',
                 'must cite at least one P page', 'Keep every claim short and lexically grounded',
                 'E CANDIDATE RULE supersedes']
    assert all(f not in system for f in forbidden)
    assert {k: v for k, v in request.items() if k != 'messages'} == dict(
        model='deepseek-flash', temperature=0, thinking={'type': 'disabled'},
        response_format={'type': 'json_object'}, max_tokens=16384)

    frozen = OUT / 'frozen'
    frozen.mkdir()
    package = frozen / 'package'
    package.mkdir()
    for name in ['session.json', 'interactive-intake.sqlite3', 'candidate/history.sqlite3']:
        target = package / name
        target.parent.mkdir(exist_ok=True)
        shutil.copyfile(old_rich / name, target)
    shutil.copytree(OLD / 'native/customer-materials', frozen / 'customer-materials')
    for name in ['task-plan-brief.json', 'output-contract.json', 'schema-examples.json', 'facts-source-map.json']:
        shutil.copyfile(OLD / name, frozen / name)
    service = MVPApplicationService(package)
    service.scope_reviewer = reviewer
    mock_text = json.dumps(read(old_rich / 'mock-response.json'), ensure_ascii=False, separators=(',', ':'))
    # An existing legal response is reused once; no new article is generated.
    service.generation_executor = MockArticleExecutor(task=snapshot.task, template=value,
        transport=httpx.MockTransport(lambda r: (_ for _ in ()).throw(AssertionError('FREEZE_MUST_NOT_SEND'))))
    bundle = freeze(service)
    native = package / 'web-experiment'
    assert (native / 'request.json').read_bytes() == raw
    new_value = _decode(read(native / 'native-input.json'), cd.ContentDraftInput)
    assert new_value.change_plan_report == value.change_plan_report
    assert new_value.writing_brief == value.writing_brief
    assert new_value.customer_evidence.sources == value.customer_evidence.sources
    assert new_value.customer_evidence.snapshot_sha256 == value.customer_evidence.snapshot_sha256
    assert new_value.customer_evidence.reviewed_at > value.customer_evidence.reviewed_at
    for name, content in [('request.FROZEN-NOT-AUTHORIZED.json', raw),
                          ('system-prompt.txt', system.encode()), ('user-material.json', user.encode())]:
        (frozen / name).write_bytes(content)
    save(frozen / 'source-sha256.json', code_hashes())
    save(frozen / 'binding-audit.json', dict(
        previous_source_and_artifact_hashes_match=True, request_reconstructed_byte_for_byte=True,
        old_request_sha256=sha(raw), request_sha256=sha(raw), native_bundle_sha256=bundle,
        documents=7, facts=43, sections=6, input_interpretations=0,
        task=_encode(snapshot.task), snapshot_sha256=snapshot_digest(snapshot),
        native_scope_sha256=new_value.customer_evidence.native_scope_sha256,
        task_version=snapshot.task.task_version, plan_version=snapshot.plan_version,
        evidence_version=snapshot.evidence_version, snapshot_revision=snapshot.revision,
        task_plan_evidence_brief_unchanged=True, old_contract_fragments_absent=forbidden,
        old_test_review_at=value.customer_evidence.reviewed_at.isoformat(),
        fresh_test_review_at=new_value.customer_evidence.reviewed_at.isoformat(),
        refresh='Existing FactsOnlyReviewer + require_generation_scope; exact snapshot, scope, source versions and dossier validity checked; no human or LIVE authority.',
        authenticated_human_signoff=False, live_permit_issued=False, wordpress_authorized=False))

    # Frozen files are never exercised in place: only the disposable MOCK copy mutates.
    scratch = OUT / 'mock-only'
    shutil.copytree(package, scratch)
    mock_service = MVPApplicationService(scratch)
    mock_service.scope_reviewer = reviewer
    ledger = WebExperimentLedger(scratch / 'MOCK-only-ledger.sqlite3')
    ledger.initialize()
    expiry = datetime.now(UTC) + timedelta(minutes=10)
    ledger.issue('NEW-OFFLINE-MOCK-ONLY', bundle, scratch, sha(raw), 'MOCK', expiry)
    calls = []
    def handler(req):
        assert ledger.read('NEW-OFFLINE-MOCK-ONLY')[7] is not None
        assert req.content == raw and str(req.url) == 'https://api.deepseek.com/chat/completions'
        calls.append(sha(req.content))
        return httpx.Response(200, json={'model': 'deepseek-flash', 'choices': [
            {'message': {'content': mock_text}, 'finish_reason': 'stop'}]})
    executor = FrozenWebExecutor(scratch, bundle, ledger, 'NEW-OFFLINE-MOCK-ONLY',
                                 transport=httpx.MockTransport(handler))
    mock_service.generation_executor = executor
    mock_service.generation = FrozenWebGeneration(mock_service)
    session, _, store, _, _ = mock_service._load()
    current = mock_service._current(store, session)
    loaded, loaded_raw = executor.load(current)
    assert loaded_raw == raw
    mock_service.generation.start(bundle, (bundle, expiry))
    await asyncio.gather(*tuple(mock_service.generation.tasks))
    state = mock_service.generation.view()
    assert state['generation_state'] == 'PENDING_REVIEW', state
    assert state['attempt']['candidate_state'] == 'PENDING_SEMANTIC_REVIEW'
    assert not state['attempt']['candidate_errors']
    assert state['attempt']['real_requests'] == 0 and len(calls) == executor.calls == 1
    assert state['attempt']['usage'] is None  # No invented Mock or actual token usage.
    mock_service.generation.start(bundle, (bundle, expiry))
    assert executor.calls == 1
    output = scratch / 'generation' / bundle
    assert (output / 'request.json').read_bytes() == raw
    assert sha((output / 'response-body.bin').read_bytes()) == state['attempt']['response_sha256']
    assert (output / 'local-review.sqlite3').is_file()
    assert not (output / 'history.sqlite3').exists() and mock_service.generation.selected() is None
    class CapturedWriter:
        async def write_content_draft(self, prompt):
            return cd.ContentDraftGeneration('synthetic', 'offline-reuse',
                cd.ContentDraftGenerationStatus.SUCCESS, mock_text, None)
    formal = await ContentDraftWorkflow(CapturedWriter(), max_repair_attempts=0).run(loaded)
    assert formal.error == 'INTERPRETATION_PENDING_REVIEW' and not formal.drafts
    historical_text = (HISTORY / 'model-output.txt').read_text(encoding='utf-8')
    replay = inspect_candidate_output(loaded, historical_text,
        current_snapshot_sha256=loaded.customer_evidence.snapshot_sha256)
    assert replay.state == 'DETERMINISTICALLY_REJECTED'
    save(frozen / 'mock-only-result.json', dict(
        executor='FrozenWebExecutor + FrozenWebGeneration + OneShotTransport + httpx.MockTransport',
        state=state['generation_state'], candidate_state=state['attempt']['candidate_state'],
        candidate_errors=state['attempt']['candidate_errors'], request_sha256=sha(raw),
        native_bundle_sha256=bundle, request_count=1, second_start_calls=executor.calls,
        response_complete=state['attempt']['response_complete'], usage=None, usage_is_not_invented=True,
        response_sha256=state['attempt']['response_sha256'], local_pending_review_saved=True,
        formal_error=formal.error, formal_drafts=0, history_draft_artifacts=0,
        historical_response_state=replay.state, historical_errors=replay.errors,
        historical_raw_sha256=sha(historical_text.encode()), source_refs_repaired=0,
        fixture_source='final-v2/native/B-rich-evidence/mock-response.json; unchanged reuse',
        fixture_sha256=sha((old_rich / 'mock-response.json').read_bytes()),
        retention_directory=output.relative_to(ROOT).as_posix(),
        real_requests=0, wordpress_requests=0, live_permits_issued=0,
        mock_permits_issued=1, production_gate_invoked=False))
    old_request = read(HISTORY / 'request.json')
    old_input = ''.join(m['content'] for m in old_request['messages'])
    input_text = system + user
    historical_usage = read(HISTORY / 'result.json')['usage']
    newer = ROOT / 'docs/seo-flash-contract-quality-live-2026-10-12'
    newer_result = read(newer / 'execution-summary.json')
    assert (newer / 'request.json').read_bytes() == raw
    for filename, field in [('request.json', 'request_sha256'),
                            ('response-body.bin', 'response_sha256'),
                            ('model-output.txt', 'model_text_sha256')]:
        assert sha((newer / filename).read_bytes()) == newer_result[field]
    def measure(text):
        return dict(characters=len(text), utf8_bytes=len(text.encode()), ascii_only=text.isascii(),
                    official_typical_estimated_tokens=len(text) * .3)
    stress = 65536
    save(frozen / 'token-cost-budget.json', dict(
        system=measure(system), user_material=measure(user), input=measure(input_text),
        full_request_json=measure(raw.decode()),
        full_request_note='HTTP JSON escaping/parameter characters are measured separately; not all are model input tokens.',
        historical=dict(usage=historical_usage, input_characters=len(old_input),
            request_bytes=len((HISTORY / 'request.json').read_bytes()),
            result_sha256=sha((HISTORY / 'result.json').read_bytes()),
            scaled_current_input_estimate=historical_usage['prompt_tokens'] * len(input_text) / len(old_input)),
        exact_current_input_tokens=None, current_server_usage=None,
        prior_identical_request_observation=dict(
            directory=newer.relative_to(ROOT).as_posix(),
            summary_sha256=sha((newer / 'execution-summary.json').read_bytes()),
            request_sha256=sha(raw), usage=newer_result['usage'],
            http_status=newer_result['http_status'], finish_reason=newer_result['finish_reason'],
            validator=newer_result['validator'], candidate_errors=newer_result['candidate_errors'],
            meaning='Measured 7,747 input tokens for these exact request bytes in a pre-existing experiment; future framing/tokenizer/alias stability is not guaranteed.'),
        matched_hosted_tokenizer_and_chat_template='UNVERIFIED', exact_token_bound_verified=False,
        official_typical_rule='0.3 token per English character; approximate, varies by model; not an upper bound.',
        input_stress_scenario_tokens=stress, stress_is_mathematical_bound=False,
        stress_basis='65,536 is >7x the current official character estimate and >8x the size-scaled historical usage; discretionary conservative scenario, no provider guarantee.',
        max_output_tokens=16384, official_context_length_label='1M',
        context_for_conservative_arithmetic=1000000, context_label_precision='Official page gives 1M, no integer. Use 1,000,000 only for conservative scenario arithmetic.',
        total_stress_context_tokens=stress+16384,
        remaining_stress_context_tokens=1000000-stress-16384,
        estimated_token_feasibility='PASS', owner_acceptance_required=True, owner_acceptance_received=False,
        usd_per_million=dict(peak_cache_hit=.006, peak_cache_miss=.3, peak_output=1.2,
                             off_peak_cache_hit=.003, off_peak_cache_miss=.15, off_peak_output=.6),
        max_output_typical_input_peak_cache_miss_usd=(len(input_text)*.3*.3+16384*1.2)/1000000,
        stress_peak_cache_miss_usd=(stress*.3+16384*1.2)/1000000,
        proposed_budget_usd=.05, actual_spending_authorized_usd=0,
        input_tokens_at_proposed_budget_with_max_output=(.05*1000000-16384*1.2)/.3,
        strict_cost_upper_bound_verified=False, api_billing_hard_cap=False,
        cache_hit_assumed=False, off_peak_assumed=False,
        risk='Token framing/tokenizer/model alias/prices can change. Server usage is authoritative; local estimates and timeout/response caps cannot cap server billing. Timeout may occur after processing; do not retry.',
        account_balance_queried=False))
    print(json.dumps(dict(request_sha256=sha(raw), native_bundle_sha256=bundle,
        input_characters=len(input_text), mock_state=state['generation_state'],
        real_requests=0), indent=2))


if __name__ == '__main__':
    # No credentials or real HTTP transport can be loaded by this audit recipe.
    with patch('httpx.AsyncHTTPTransport', side_effect=AssertionError('NO LIVE HTTP')), \
         patch('httpx.HTTPTransport', side_effect=AssertionError('NO LIVE HTTP')):
        asyncio.run(prepare())
