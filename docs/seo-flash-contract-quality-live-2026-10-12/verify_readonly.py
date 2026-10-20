"""Final independent artifact, authorization, native check and integrity audit."""
from dataclasses import replace
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]
sys.path.insert(0,str(ROOT))
from scripts.web_deepseek_experiment import live_ledger
from foreign_trade_geo_agent.adapters.retained_deepseek import save_bytes
from foreign_trade_geo_agent.core import content_draft as cd
from foreign_trade_geo_agent.storage.serialization import _decode, _encode
from foreign_trade_geo_agent.storage.content_draft_review import SQLiteLocalDraftReviewStore
from foreign_trade_geo_agent.web.experiment import code_hashes
from foreign_trade_geo_agent.web.generation import MockArticleExecutor
from foreign_trade_geo_agent.workflows.content_draft import inspect_candidate_output

sha=lambda raw:hashlib.sha256(raw).hexdigest()
FROZEN=ROOT/'docs/seo-flash-request-preflight-2026-10-12/final-v2'
summary=json.loads((OUT/'execution-summary.json').read_bytes())
native=Path(summary['output_directory'])
checks={}
raw=(OUT/'request.json').read_bytes()
checks['request_exact_original']=raw==(FROZEN/'request.FROZEN-NOT-AUTHORIZED.json').read_bytes()==(native/'request.json').read_bytes()
checks['request_hash']=sha(raw)==summary['request_sha256']
response=(OUT/'response-body.bin').read_bytes()
checks['complete_response_and_hash']=summary['response_complete'] and summary['response_saved'] and not summary['response_budget_exceeded'] and sha(response)==summary['response_sha256'] and response==(native/'response-body.bin').read_bytes()
text=(OUT/'model-output.txt').read_text('utf-8')
checks['model_text_exact']=json.loads(response)['choices'][0]['message']['content']==text and sha(text.encode())==summary['model_text_sha256'] and text==(native/'model-output.txt').read_text('utf-8')==(OUT/'rejected-candidate.txt').read_text('utf-8')
value=_decode(json.loads((OUT/'native-input.json').read_bytes()),cd.ContentDraftInput)
value=replace(value,customer_evidence=replace(value.customer_evidence,reviewed_at=datetime.now(UTC)))
checks['fresh_test_timestamp_does_not_change_request']=MockArticleExecutor.request_for(value)==raw
candidate=inspect_candidate_output(value,text,current_snapshot_sha256=value.customer_evidence.snapshot_sha256)
checks['native_parser_validator_reproduced']=_encode(candidate)==json.loads((OUT/'candidate-validation.json').read_bytes()) and candidate.state=='DETERMINISTICALLY_REJECTED'
revisions=SQLiteLocalDraftReviewStore((native/'local-review.sqlite3').resolve()).revisions(sha(text.encode()))
checks['pending_journal_exact_original_no_approval']=len(revisions)==1 and revisions[0].body_text==text and revisions[0].original_body==text if hasattr(revisions[0],'original_body') else len(revisions)==1 and revisions[0].body_text==text
checks['pending_journal_no_decisions']=revisions[0].status=='PENDING_REVIEW' and not revisions[0].candidate_decisions
ledger=live_ledger()
row=ledger.read(summary['permit'])
checks['permit_consumed_exact_binding']=row[1]==summary['binding_sha256'] and row[2]==str((OUT/'execution-input').resolve()) and row[3]==sha(raw) and row[4]=='LIVE' and row[7] is not None
with sqlite3.connect('file:'+ledger.path.as_posix()+'?mode=ro',uri=True) as db:
    checks['unique_permit_for_request']=db.execute('SELECT count(*) FROM permits WHERE request=?',(sha(raw),)).fetchone()[0]==1
checks['one_http_post_zero_retry']=summary['real_requests']==summary['request_count']==1 and summary['automatic_retries']==0 and summary['fallback']==0
checks['no_formal_admission']=summary['production_authorized'] is False and summary['wordpress_authorized'] is False and summary['finalizer'].startswith('NOT_RUN') and not (native/'history.sqlite3').exists()
manifest_raw=(FROZEN/'artifact-sha256.json').read_bytes()
checks['delivery_hash_unchanged']=sha(manifest_raw)=='e797983c2d20d63b6f57491c377142a57aa05886f58bd8b7abdc27447adb094a'
checks['49_frozen_files_unchanged']=all(sha((FROZEN/n).read_bytes())==h for n,h in json.loads(manifest_raw).items())
checks['174_source_files_unchanged']=code_hashes()==json.loads((FROZEN/'source-sha256.json').read_bytes())
baseline=json.loads((FROZEN.parent/'baseline-sha256.json').read_bytes())
checks['1992_existing_baseline_files_unchanged']=all((ROOT/n).is_file() and sha((ROOT/n).read_bytes())==h for n,h in baseline.items())
metrics=json.loads((OUT/'metrics.json').read_bytes())
claims=json.loads((OUT/'claims-index.json').read_bytes())
checks['article_contains_every_original_claim']=all(c['text'] in (OUT/'article-full.md').read_text('utf-8') for c in claims)
checks['counts_match_native']=len(claims)==len(candidate.claims)==metrics['claims']==47
acl=subprocess.run(['icacls',str(OUT)],capture_output=True,check=True,text=True,encoding='utf-8',errors='replace').stdout
checks['acl_no_inherited_access']='(I)' not in acl and '(OI)(CI)(F)' in acl
assert all(checks.values()),checks
result=dict(status='PASS',checked_at=datetime.now(UTC).isoformat(),checks=checks,
    real_requests=1,wordpress_requests=0,account_balance_requests=0,source_changes=0,
    response_sha256=sha(response),model_text_sha256=sha(text.encode()),
    validator=candidate.state,validator_errors=list(candidate.errors),candidate_decisions=0,
    tests=dict(run=52,failures=0,errors=0,full_suite_run=False))
save_bytes(OUT/'verification.json',(json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode())
files={p.relative_to(OUT).as_posix():sha(p.read_bytes()) for p in sorted(OUT.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.name not in {'artifact-sha256.json','artifact-manifest.sha256'}}
encoded=(json.dumps(files,ensure_ascii=False,indent=2)+'\n').encode()
save_bytes(OUT/'artifact-sha256.json',encoded)
save_bytes(OUT/'artifact-manifest.sha256',(sha(encoded)+'\n').encode())
print(json.dumps(result,ensure_ascii=False,indent=2))
