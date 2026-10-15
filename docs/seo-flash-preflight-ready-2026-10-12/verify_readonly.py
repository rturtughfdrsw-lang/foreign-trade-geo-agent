"""Read-only verification of this delivery, using existing runtime contracts."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.accept_autonomous_interpretation import FactsOnlyReviewer
from scripts.web_deepseek_experiment import compose
from foreign_trade_geo_agent.core import content_draft as cd
from foreign_trade_geo_agent.core.evidence_intake import IntakeSnapshot, validate_assessment
from foreign_trade_geo_agent.storage.serialization import _decode
from foreign_trade_geo_agent.storage.content_draft_review import SQLiteLocalDraftReviewStore
from foreign_trade_geo_agent.storage.web_experiment import WebExperimentLedger
from foreign_trade_geo_agent.web.experiment import code_hashes
from foreign_trade_geo_agent.web.generation import MockArticleExecutor
from datetime import UTC, datetime
from unittest.mock import patch
import httpx

HERE = Path(__file__).resolve().parent
BUNDLE = HERE / 'frozen'
sha = lambda raw: hashlib.sha256(raw).hexdigest()
read = lambda path: json.loads(path.read_bytes())


def verify():
    baseline = read(HERE / 'baseline-sha256.json')
    assert all((ROOT / n).is_file() and sha((ROOT / n).read_bytes()) == h for n, h in baseline.items())
    manifest_raw = (BUNDLE / 'artifact-sha256.json').read_bytes()
    assert sha(manifest_raw) == (BUNDLE / 'bundle.sha256').read_text().strip()
    manifest = json.loads(manifest_raw)
    assert all(sha((BUNDLE / n).read_bytes()) == h for n, h in manifest.items())
    assert {p.relative_to(BUNDLE).as_posix() for p in BUNDLE.rglob('*') if p.is_file()} == set(manifest) | {'artifact-sha256.json', 'bundle.sha256'}
    assert read(BUNDLE / 'source-sha256.json') == code_hashes()
    ready = read(BUNDLE / 'readiness.json')
    native = BUNDLE / 'package/web-experiment'
    native_raw = (native / 'bundle.json').read_bytes()
    inside = json.loads(native_raw)
    assert sha(native_raw) == ready['execution_bundle_sha256'] == (native / 'bundle.sha256').read_text().strip()
    assert inside['code'] == code_hashes()
    assert all(sha((native / n).read_bytes()) == h for n, h in inside['files'].items())
    raw = (BUNDLE / 'request.FROZEN-NOT-AUTHORIZED.json').read_bytes()
    value = _decode(read(native / 'native-input.json'), cd.ContentDraftInput)
    assert MockArticleExecutor.request_for(value) == raw == (native / 'request.json').read_bytes()
    assert sha(raw) == ready['request_sha256'] == inside['request_sha256']
    request = json.loads(raw)
    budget = read(BUNDLE / 'token-cost-budget.json')
    for text, name, filename in [(request['messages'][0]['content'], 'system', 'system-prompt.txt'),
                                  (request['messages'][1]['content'], 'user_material', 'user-material.json')]:
        assert text.encode() == (BUNDLE / filename).read_bytes()
        assert budget[name]['characters'] == len(text) and budget[name]['utf8_bytes'] == len(text.encode())
    assert budget['input']['characters'] == 30622 and budget['full_request_json']['utf8_bytes'] == len(raw) == 32544
    assert budget['prior_identical_request_observation']['usage']['prompt_tokens'] == 7747
    expected = (budget['input_stress_scenario_tokens'] * budget['usd_per_million']['peak_cache_miss'] +
                budget['max_output_tokens'] * budget['usd_per_million']['peak_output']) / 1e6
    assert expected == budget['stress_peak_cache_miss_usd'] == .0393216 <= budget['proposed_budget_usd']
    assert not budget['exact_token_bound_verified'] and not budget['stress_is_mathematical_bound']
    assert not budget['strict_cost_upper_bound_verified'] and not budget['api_billing_hard_cap']
    assert not budget['owner_acceptance_received'] and budget['actual_spending_authorized_usd'] == 0
    assert budget['remaining_stress_context_tokens'] == 1000000 - 65536 - 16384
    facts = read(BUNDLE / 'customer-materials/facts.json')
    snapshot = _decode(read(native / 'snapshot.json'), IntakeSnapshot)
    reviewer = FactsOnlyReviewer(facts, tuple(e.supplement for e in snapshot.active_evidence))
    assessment = reviewer.assess(snapshot, now=datetime.now(UTC))
    validate_assessment(snapshot, assessment, now=datetime.now(UTC))
    # Validate the *existing real launch composition* with its Mock-only copy.
    scratch = HERE / 'mock-only'
    ledger = WebExperimentLedger(scratch / 'MOCK-only-ledger.sqlite3')
    with patch('httpx.AsyncHTTPTransport', side_effect=AssertionError('NO LIVE HTTP')), \
         patch('httpx.HTTPTransport', side_effect=AssertionError('NO LIVE HTTP')):
        app = compose(scratch, ready['execution_bundle_sha256'], ledger, 'NEW-OFFLINE-MOCK-ONLY',
            transport=httpx.MockTransport(lambda r: (_ for _ in ()).throw(AssertionError('READ ONLY'))),
            scope_reviewer=reviewer)
        assert app.state.mvp_service.generation_executor.calls == 0
    mock = read(BUNDLE / 'mock-only-result.json')
    assert mock['formal_drafts'] == 0 and mock['formal_error'] == 'INTERPRETATION_PENDING_REVIEW'
    assert mock['historical_response_state'] == 'DETERMINISTICALLY_REJECTED'
    text = (BUNDLE / 'mock-drill/model-output.txt').read_text(encoding='utf-8')
    records = SQLiteLocalDraftReviewStore(BUNDLE / 'mock-drill/local-review.sqlite3').revisions(sha(text.encode()))
    assert len(records) == 1 and records[0].status == 'PENDING_REVIEW'
    assert records[0].body_text == text and not records[0].candidate_decisions
    assert not ready['live_permit_issued'] and not ready['owner_risk_acceptance']
    assert not ready['REAL_FLASH_INSTRUCTION_FOLLOWING_UNTESTED']
    assert not ready['REAL_WRITING_QUALITY_UNTESTED'] and ready['PRODUCTION_NO_GO']
    assert read(BUNDLE / 'current-state-reconciliation.json')['validator'] == 'DETERMINISTICALLY_REJECTED'
    print(json.dumps(dict(status='PASS', artifact_files=len(manifest), source_files=len(code_hashes()),
        baseline_files_unchanged=len(baseline), request_sha256=sha(raw), bundle_sha256=sha(manifest_raw),
        execution_bundle_sha256=sha(native_raw), pending_sqlite_reopened=True,
        existing_compose_checked_with_exact_reviewer=True, real_requests=0, wordpress_requests=0, live_permits=0), indent=2))


if __name__ == '__main__':
    verify()
