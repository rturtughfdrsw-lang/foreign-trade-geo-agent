"""Independent final audit. Reads existing results; never invokes the launcher."""
from dataclasses import replace
from datetime import UTC, datetime
import hashlib
import inspect
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
sys.path.insert(0, str(ROOT))
from scripts.web_deepseek_experiment import live_ledger
from foreign_trade_geo_agent.adapters.retained_deepseek import save_bytes
from foreign_trade_geo_agent.core import content_draft as cd
from foreign_trade_geo_agent.core.draft_customer_evidence import InterpretationProposal
from foreign_trade_geo_agent.storage.content_draft_review import SQLiteLocalDraftReviewStore
from foreign_trade_geo_agent.storage.serialization import _decode, _encode
from foreign_trade_geo_agent.web.experiment import code_hashes
from foreign_trade_geo_agent.web.generation import MockArticleExecutor
from foreign_trade_geo_agent.workflows import content_draft as workflow

sha = lambda raw: hashlib.sha256(raw).hexdigest()
FROZEN = ROOT/'docs/seo-draft-contract-offline-2026-10-12/frozen-v1'
REQUEST = '9273e145beaacb122e57261294143c1a9df0cd4faba8554a03609c194e86ab0f'
BUNDLE = 'ad96bbb5d8fee7d35fee5832d51cea96d65bce607e08e8b9fa09868ed875a9cf'
checks = {}
ready = json.loads((FROZEN/'readiness.json').read_bytes())
manifest = json.loads((FROZEN/'artifact-sha256.json').read_bytes())
checks['bundle_hash_exact'] = sha((FROZEN/'artifact-sha256.json').read_bytes()) == BUNDLE == (FROZEN/'bundle.sha256').read_text().strip()
checks['82_frozen_artifacts_unchanged'] = len(manifest) == 82 and all(sha((FROZEN/n).read_bytes()) == h for n,h in manifest.items())
checks['175_source_files_unchanged'] = len(ready['code_sha256']) == 175 and code_hashes() == ready['code_sha256']
functions = dict(parse_claim=workflow._parse_claim, parse_specification=workflow._parse_specification,
    validate_claim_evidence=cd._validate_claim_evidence, article_quality_findings=cd.article_quality_findings,
    finalize_draft_item=cd.finalize_draft_item, interpretation_proposal=InterpretationProposal)
summary = json.loads((FROZEN/'parser-validator-source-summary.json').read_bytes())
checks['six_parser_validator_summaries_match'] = all(sha(inspect.getsource(functions[n]).encode()) == s['source_sha256'] for n,s in summary.items())
raw = (OUT/'request.json').read_bytes()
checks['request_bytes_exact'] = sha(raw) == REQUEST and raw == (FROZEN/'request.FROZEN-NOT-AUTHORIZED.json').read_bytes()
request = json.loads(raw)
checks['parameters_exact'] = {k:v for k,v in request.items() if k != 'messages'} == dict(model='deepseek-flash',temperature=0,thinking={'type':'disabled'},response_format={'type':'json_object'},max_tokens=16384)
body = (OUT/'response-body.bin').read_bytes()
provider = json.loads(body)
text = (OUT/'model-output.txt').read_bytes()
result = json.loads((OUT/'execution-summary.json').read_bytes())
checks['raw_http_json_same_bytes'] = body == (OUT/'response.json').read_bytes() and sha(body) == result['response_sha256'] and result['response_complete'] and result['response_saved'] and not result['response_budget_exceeded']
checks['model_json_text_exact'] = provider['choices'][0]['message']['content'].encode() == text == (OUT/'model-output.json').read_bytes() == (OUT/'rejected-candidate.txt').read_bytes() and sha(text) == result['model_text_sha256']
checks['usage_finish_model_exact'] = provider['usage'] == result['raw_usage'] and provider['model'] == result['actual_model'] == 'deepseek-flash' and provider['choices'][0]['finish_reason'] == result['finish_reason'] == 'stop'
value = _decode(json.loads((OUT/'native-input.json').read_bytes()), cd.ContentDraftInput)
original = _decode(json.loads((OUT/'frozen-native-input.json').read_bytes()), cd.ContentDraftInput)
checks['only_test_review_timestamp_changed'] = replace(value,customer_evidence=replace(value.customer_evidence,reviewed_at=original.customer_evidence.reviewed_at)) == original
checks['native_request_reconstruction_exact'] = MockArticleExecutor.request_for(value) == raw
value = replace(value,customer_evidence=replace(value.customer_evidence,reviewed_at=datetime.now(UTC)))
candidate = workflow.inspect_candidate_output(value,text.decode(),current_snapshot_sha256=value.customer_evidence.snapshot_sha256)
checks['native_parser_validator_reproduced_exactly'] = _encode(candidate) == json.loads((OUT/'candidate-validation.json').read_bytes()) and candidate.state == 'DETERMINISTICALLY_REJECTED'
journal = SQLiteLocalDraftReviewStore((OUT/'local-review.sqlite3').resolve())
revisions = journal.revisions(sha(text))
checks['original_candidate_stored_once_without_approval'] = len(revisions) == 1 and revisions[0].body_text.encode() == text and revisions[0].status == 'PENDING_REVIEW' and not revisions[0].candidate_decisions
ledger = live_ledger()
row = ledger.read(result['permit'])
checks['fixed_permit_consumed_exact_binding'] = row[1:5] == (BUNDLE,str(OUT.resolve()),REQUEST,'LIVE') and row[7] is not None
with sqlite3.connect('file:'+ledger.path.as_posix()+'?mode=ro',uri=True) as db:
    checks['unique_reservation_for_request'] = db.execute('SELECT count(*) FROM permits WHERE request=?',(REQUEST,)).fetchone()[0] == 1
checks['one_request_no_retry_fallback_repair'] = result['real_requests'] == result['request_count'] == 1 and result['retries'] == result['fallback'] == result['repairs'] == 0
events = json.loads((OUT/'stage-order.json').read_bytes())
checks['required_stage_order'] = [e['stage'] for e in events] == ['SINGLE_POST_BEGIN','PROVIDER_RESPONSE_RETAINED','JSON_PARSER_PASS','CANDIDATE_VALIDATOR','CANDIDATE_REVIEW_STORAGE','STOP_VALIDATOR_REJECTED']
provider_record = json.loads((OUT/'provider-result.json').read_bytes())
checks['pre_parser_record_has_usage_finish_latency'] = provider_record['raw_usage'] == provider['usage'] and provider_record['finish_reason'] == 'stop' and provider_record['provider_latency_seconds'] == result['provider_latency_seconds']
estimate = json.loads((OUT/'cost-estimate.json').read_bytes())
usage = provider['usage']
expected_cost = (usage['prompt_cache_hit_tokens']*.006 + usage['prompt_cache_miss_tokens']*.3 + usage['completion_tokens']*1.2)/1e6
checks['cost_recomputed'] = estimate['usage'] == usage and estimate['period'] == 'PEAK' and estimate['estimated_total_usd'] == expected_cost and estimate['estimate_only'] and not estimate['billed_amount_verified']
checks['review_replay_finalizer_not_run'] = result['test_only_review_replay'] == result['finalizer'] == 'NOT_RUN_VALIDATOR_REJECTED' and not (OUT/'history.sqlite3').exists() and not (OUT/'test-only-replay.json').exists()
checks['no_production_authority'] = not result['production_authorized'] and not result['wordpress_authorized'] and not candidate.production_authorized
claims = json.loads((OUT/'claims-index.json').read_bytes())
model_claims = [c for s in json.loads(text)['draft']['sections'] for b in s['blocks'] for c in b.get('claims',b.get('items',[]))]
checks['claim_index_matches_original'] = len(claims) == len(model_claims) == len(candidate.claims) == 50 and all(all(item[k] == c[k] for k in c) for item,c in zip(claims,model_claims))
checks['article_views_preserve_all_original_claims'] = all(c['text'] in (OUT/'article-full.md').read_text('utf-8') and c['text'] in (OUT/'article-annotated.md').read_text('utf-8') for c in model_claims)
metrics = json.loads((OUT/'metrics.json').read_bytes())
checks['metrics_match_original'] = metrics['claims'] == 50 and metrics['claims_with_nonempty_valid_customer_refs'] == 49 and metrics['interpretation_proposals'] == 6 and metrics['unique_fact_refs'] == metrics['fact_bank_size'] == 43 and metrics['wrong_ps_ref_count'] == 0
checks['required_deliverables_exist'] = all((OUT/n).is_file() for n in ('report.md','article-full.md','article-annotated.md','candidate-validation.json','cost-estimate.json','human-review.md'))
for label,directory in [('old_contract',ROOT/'docs/seo-flash-quality-live-2026-10-12'),('previous_flash',OUT.parent)]:
    entries=json.loads((directory/'artifact-sha256.json').read_bytes())
    checks[label+'_historical_artifacts_unchanged'] = all((directory/n).is_file() and sha((directory/n).read_bytes()) == h for n,h in entries.items())
acl = subprocess.run(['icacls',str(OUT)],capture_output=True,check=True,text=True,encoding='utf-8',errors='replace').stdout
checks['private_directory_no_inherited_access'] = '(I)' not in acl and '(OI)(CI)(F)' in acl
result = dict(status='PASS' if all(checks.values()) else 'FAIL',checked_at=datetime.now(UTC).isoformat(),checks=checks,
    real_requests=1,retries=0,fallback=0,repairs=0,wordpress_requests=0,source_changes=0,
    validator=candidate.state,validator_errors=list(candidate.errors),candidate_revisions=len(revisions),candidate_decisions=0,
    tests=dict(command='python -m unittest tests.test_draft_prompt_contract tests.test_flash_draft_replay tests.test_autonomous_interpretation -v',run=37,failures=0,errors=0,full_suite_run=False,provenance='Observed tool output in this session before live request; not rerun by this audit.'),
    preparation_failures=dict(count=2,scope='New case-local helper attribute references, before any HTTP; corrected without changing frozen code.'))
save_bytes(OUT/'verification.json',(json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode())
files = {p.relative_to(OUT).as_posix():sha(p.read_bytes()) for p in sorted(OUT.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.name not in {'artifact-sha256.json','artifact-manifest.sha256'}}
encoded = (json.dumps(files,ensure_ascii=False,indent=2)+'\n').encode()
save_bytes(OUT/'artifact-sha256.json',encoded)
save_bytes(OUT/'artifact-manifest.sha256',(sha(encoded)+'\n').encode())
print(json.dumps(result,ensure_ascii=False,indent=2))
assert all(checks.values()), 'FINAL_AUDIT_FAILED'
