"""Final local verification; never sends requests or renews authorization."""
from pathlib import Path
import json
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from execute_once import OUT,ROOT,BASE,PACKAGE,REQUEST_HASH,MANIFEST_HASH,PERMIT,LEDGER,history_fingerprint,write
from tests.test_seo_draft_v3_request_freeze import sha,strict_json,require,PACKAGE_NAMES,read_sources,source_context
from foreign_trade_geo_agent.core.draft_selection_contract import selection_digest,plan_digest
from foreign_trade_geo_agent.adapters.retained_deepseek import save_bytes

def summarize(path,style):
    raw=path.read_bytes(); b=strict_json(raw); sections=b['candidate']['draft']['sections']
    claims=[c for s in sections for c in s['claims']] if style=='legacy-v3' else [
        c for s in sections for block in s['blocks'] for c in block.get('claims',block.get('items',[]))]
    return dict(model_output_sha256=sha(raw),sections=len(sections),claims=len(claims),
        blocks=None if style=='legacy-v3' else sum(len(s['blocks']) for s in sections),
        direct_facts=sum(c['claim_type']=='OBSERVED_PRODUCT_FACT' for c in claims),
        interpretations=sum(c['claim_type']=='EVIDENCE_BASED_INTERPRETATION' for c in claims),
        cta=sum(c['claim_type']=='CALL_TO_ACTION' for c in claims),
        proposals=sum('proposal' in c for c in claims))

def run():
    checks=strict_json((OUT/'preflight-verification.json').read_bytes())
    require(sha((PACKAGE/'request.json').read_bytes())==REQUEST_HASH and
        sha((PACKAGE/'manifest.json').read_bytes())==MANIFEST_HASH,'FROZEN_AUTHORIZATION_HASH')
    require({p.name for p in PACKAGE.iterdir()}==PACKAGE_NAMES,'PACKAGE_FILE_SET')
    require(all(sha((PACKAGE/n).read_bytes())==h for n,h in checks['frozen_fingerprint'].items()),'FROZEN_DRIFT')
    manifest=strict_json((PACKAGE/'manifest.json').read_bytes())
    require(all(sha((ROOT/e['filename']).read_bytes())==e['sha256'] and
        (ROOT/e['filename']).stat().st_size==e['size'] for e in manifest['files']),'SOURCE_DRIFT')
    history=history_fingerprint()
    sources=read_sources(); _,_,_,selection,value=source_context(sources)
    raw=(OUT/'model-output.txt').read_bytes(); body=strict_json(raw)
    provider=strict_json((OUT/'response-body.bin').read_bytes())
    require(provider['choices'][0]['message']['content'].encode()==raw==(OUT/'model-output.json').read_bytes(),
        'RAW_BYTES_CHANGED')
    require((OUT/'request.json').read_bytes()==(PACKAGE/'request.json').read_bytes(),'REQUEST_COPY')
    require(body['v3_sidecar']['selection_sha256']==selection_digest(selection) and
        body['v3_sidecar']['evidence_snapshot_sha256']==selection.evidence_snapshot_sha256 and
        body['v3_sidecar']['plan_sha256']==plan_digest(value),'OUTPUT_CONTEXT_HASH')
    for k in ['semantic_approved','production_authorized']: require(body[k] is False,'AUTHORITY')
    reception=strict_json((OUT/'reception.json').read_bytes())
    require(reception['request_count']==1 and reception['http_status']==200 and reception['finish_reason']=='stop',
        'RECEPTION')
    require(reception['response_sha256']==sha((OUT/'response-body.bin').read_bytes()) and
        reception['model_text_sha256']==sha(raw),'RESPONSE_HASH')
    layers=strict_json((OUT/'validation-layers.json').read_bytes())
    require([l['result'] for l in layers['layers']]==['PASS','PASS','NOT_RUN','NOT_RUN'] and
        layers['state']=='REJECTED' and layers['semantic_approved'] is False and layers['production_authorized'] is False,
        'FORMAL_LAYERS')
    require(not (OUT/'assembled-envelope.json').exists(),'UNAUTHORIZED_ASSEMBLED_ARTIFACT')
    require(strict_json((OUT/'assembly-diagnostics.json').read_bytes())['error']=='V3_CLAIM_BINDING','ASSEMBLY')
    row=LEDGER.validate(PERMIT,MANIFEST_HASH,PACKAGE,REQUEST_HASH,'LIVE')
    require(row[7] is not None,'PERMIT_NOT_CONSUMED')
    try: LEDGER.validate(PERMIT,MANIFEST_HASH,PACKAGE,REQUEST_HASH,'LIVE',unclaimed=True)
    except ValueError: second_attempt_rejected=True
    else: raise ValueError('CONSUMED_PERMIT_ACCEPTED')
    claims=[c for s in body['candidate']['draft']['sections'] for block in s['blocks'] for c in block.get('claims',[])]
    reading=(OUT/'article-reading-view.md').read_text(encoding='utf-8')
    lines=[l for l in reading.splitlines() if l and not l.startswith(('>','##'))]
    require(lines==[c['text'] for c in claims],'READING_VIEW_TEXT_CHANGED')
    log=(OUT/'offline-tests.log').read_text(encoding='utf-8-sig')
    require('Ran 76 tests in 15.157s' in log and '\nOK\n' in log,'TEST_EVIDENCE')
    comparison=dict(
        v2=summarize(ROOT/'docs/seo-draft-v2-flash-quality-live-2026-10-12/model-output.txt','v2'),
        previous_v3=summarize(ROOT/'docs/seo-draft-contract-v3-flash-preflight/real-v3-experiment-2026-10-13/model-output.txt','legacy-v3'),
        repaired_v3=summarize(OUT/'model-output.txt','v3'),
        scope='Single controlled observation, not adherence rate or attribution to one prompt change')
    require(comparison['v2']['model_output_sha256']=='ece11a7e83225e5a2e4d449b2a8621f9b759aa496b0faefdc45a3622ff8996d6','V2_HASH')
    require(comparison['previous_v3']['model_output_sha256']=='a456ea3f966233e51d06e815796d0427b4391a0f9ba21b0fbbfc22e5179133b4','OLD_V3_HASH')
    write('comparison-metrics.json',comparison)
    result=dict(result='PASS',request_sha256=REQUEST_HASH,manifest_sha256=MANIFEST_HASH,
        response_sha256=sha((OUT/'response-body.bin').read_bytes()),model_output_sha256=sha(raw),assembled_sha256=None,
        frozen_six_files_unchanged=True,manifest_bound_files=len(manifest['files']),
        historical_files_unchanged=len(history),source_context_revalidated=True,raw_response_content_exact=True,
        reading_view_text_exact=True,permit_consumed=True,consumed_permit_rejected=second_attempt_rejected,
        actual_http_posts=1,unit_tests_run=76,unit_test_result='OK',full_suite_run=False,
        formal_layers=[l['result'] for l in layers['layers']],technical_contract='FAIL',
        article_quality='PARTIALLY_IMPROVED',human_semantic_review='PENDING',commercial_draft='NOT_READY',
        production_delivery='NO_GO',semantic_approved=False,production_authorized=False)
    write('verification.json',result)
    index={p.relative_to(OUT).as_posix():sha(p.read_bytes()) for p in OUT.rglob('*')
        if p.is_file() and '__pycache__' not in p.parts and p.name!='artifact-sha256.json'}
    write('artifact-sha256.json',index)
    print(json.dumps(result,indent=2))
    print(json.dumps(comparison,indent=2))

if __name__=='__main__': run()
