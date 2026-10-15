"""Evidence-backed diagnostics of immutable stored wire. Never an admission path."""
from collections import Counter
from dataclasses import asdict,fields
from datetime import datetime
import json
from pathlib import Path
import re
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from execute_once import OUT,ROOT,BASE,PACKAGE,write,history_fingerprint,LEDGER,PERMIT,REQUEST_HASH,MANIFEST_HASH
from tests.test_seo_draft_v3_request_freeze import read_sources,source_context,sha,strict_json,require
from foreign_trade_geo_agent.adapters.retained_deepseek import save_bytes
from foreign_trade_geo_agent.core import content_draft as cd
from foreign_trade_geo_agent.core.draft_selection_contract import canonical_json
from foreign_trade_geo_agent.core.draft_candidate_review import inspect_specification
from foreign_trade_geo_agent.core.draft_explanation_contract_v3 import (
    ExplanationAnnotationV3,ExplanationSidecarV3,OBJECTS,OWNERS,ACTIONS,
)
from foreign_trade_geo_agent.workflows.content_draft import _parse_specification
from foreign_trade_geo_agent.workflows.draft_contract_v3_experiment import _envelope,ENVELOPE_FIELDS

def run():
    _,_,_,selection,value=source_context(read_sources())
    raw=(OUT/'model-output.txt').read_bytes(); response=(OUT/'response-body.bin').read_bytes()
    b=strict_json(raw); provider=strict_json(response)
    require(provider['choices'][0]['message']['content'].encode()==raw,'RESPONSE_CONTENT_BYTES')
    save_bytes(OUT/'model-output.json',raw)
    save_bytes(OUT/'request.json',(PACKAGE/'request.json').read_bytes())
    save_bytes(OUT/'request-body.sha256',(PACKAGE/'request-body.sha256').read_bytes())
    findings=[]; sections=[]; claims=[]; path_by_id={}; article=[]; rows=[]
    def add(path,code,**detail): findings.append(dict(path=path,code=code,**detail))
    def keys(obj,expected,path):
        for k in sorted(set(obj)-set(expected)): add(path+'.'+k,'EXTRA_FIELD')
        for k in sorted(set(expected)-set(obj)): add(path+'.'+k,'MISSING_FIELD')
    keys(b,ENVELOPE_FIELDS,'$')
    keys(b['candidate'],{'draft'},'$.candidate')
    keys(b['candidate']['draft'],{'change_ref','draft_type','sections'},'$.candidate.draft')
    side=b['v3_sidecar']
    keys(side,{f.name for f in fields(ExplanationSidecarV3)},'$.v3_sidecar')
    null_paths=['$.sidecar_hash','$.v3_sidecar.candidate_hash']
    if b['sidecar_hash'] is not None: add('$.sidecar_hash','MODEL_NULL_REQUIRED')
    if side['candidate_hash'] is not None: add('$.v3_sidecar.candidate_hash','MODEL_NULL_REQUIRED')
    facts={f.fact_ref:f.quote for s in value.customer_evidence.sources for f in s.facts}
    for si,(section,budget) in enumerate(zip(b['candidate']['draft']['sections'],selection.sections)):
        sp=f'$.candidate.draft.sections[{si}]'
        keys(section,{'outline_heading','blocks'},sp)
        article.extend(['## '+section['outline_heading'],''])
        current=[]
        for bi,block in enumerate(section['blocks']):
            key='claims' if block['kind']=='PARAGRAPH' else 'items'
            keys(block,{'kind',key},sp+f'.blocks[{bi}]')
            for ci,c in enumerate(block[key]):
                cid=f'CL{len(claims)+1}'; cp=sp+f'.blocks[{bi}].{key}[{ci}]'
                claims.append(c); current.append(c); path_by_id[cid]=(cp,c,si)
                expected={'text','claim_type','customer_refs','page_refs','source_refs'}
                if c['claim_type']=='EVIDENCE_BASED_INTERPRETATION': expected.add('proposal')
                keys(c,expected,cp)
                if c['page_refs']: add(cp+'.page_refs','E_CLAIM_REQUIRES_EMPTY_PAGE_REFS')
                if c['source_refs']: add(cp+'.source_refs','E_CLAIM_REQUIRES_EMPTY_SOURCE_REFS')
                for ri,ref in enumerate(c['customer_refs']):
                    if ref not in budget.selected_facts: add(cp+f'.customer_refs[{ri}]','FACT_NOT_SELECTED')
                if c['claim_type']=='OBSERVED_PRODUCT_FACT' and (len(c['customer_refs'])!=1 or facts.get(c['customer_refs'][0])!=c['text']):
                    add(cp+'.text','DIRECT_QUOTE_MISMATCH')
                if 'proposal' in c:
                    p=c['proposal']; keys(p,{'procurement_question','reasoning','assumptions','limitation','procurement_action'},cp+'.proposal')
                    for k,v in [('procurement_question',budget.question),('limitation',budget.required_limitation),
                                ('procurement_action',budget.verification_action)]:
                        if p[k]!=v: add(cp+'.proposal.'+k,'PROPOSAL_SECTION_BINDING')
                    for k,text in [('text',c['text'])]+[('proposal.'+k,p[k]) for k in ['reasoning','assumptions','limitation','procurement_action']]:
                        bad=[]
                        for sentence in re.split(r'(?<=[.!?])\s+',text):
                            quantities=[e for e in cd.extract_numeric_expressions(sentence) if not re.fullmatch(r'[a-z][a-z0-9_-]*',e)]
                            if quantities and not any(sentence in facts[r] for r in c['customer_refs']): bad.append(sentence)
                        if bad: add(cp+'.'+k,'NUMERIC_CONTEXT_NOT_PRESERVED',sentences=bad)
                article.extend([c['text'],''])
        kinds=Counter(c['claim_type'] for c in current)
        used={r for c in current for r in c['customer_refs']}
        direct={r for c in current if c['claim_type']=='OBSERVED_PRODUCT_FACT' for r in c['customer_refs']}
        if kinds['EVIDENCE_BASED_INTERPRETATION']<budget.explanation_budget:
            add(sp+'.blocks','EXPLANATION_MINIMUM',actual=kinds['EVIDENCE_BASED_INTERPRETATION'],required=budget.explanation_budget)
        if not set(budget.required_direct_facts)<=direct: add(sp+'.blocks','REQUIRED_DIRECT_FACT_MISSING')
        if used!=set(budget.selected_facts): add(sp+'.blocks','SECTION_ROUTING')
        if section['outline_heading']!=budget.heading: add(sp+'.outline_heading','SECTION_HEADING')
        sections.append(dict(section_id=budget.section_id,claims=len(current),blocks=len(section['blocks']),
            kinds=dict(kinds),selected_refs=sorted(used),selected_set_matches=used==set(budget.selected_facts),
            required_directs_present=set(budget.required_direct_facts)<=direct,
            explanation_minimum=budget.explanation_budget,explanation_actual=kinds['EVIDENCE_BASED_INTERPRETATION']))
    interpretations={cid:(cp,c,si) for cid,(cp,c,si) in path_by_id.items() if c['claim_type']=='EVIDENCE_BASED_INTERPRETATION'}
    for ai,a in enumerate(side['explanations']):
        ap=f'$.v3_sidecar.explanations[{ai}]'; keys(a,{f.name for f in fields(ExplanationAnnotationV3)},ap)
        start=len(findings); cid=a['claim_id']; target=path_by_id.get(cid)
        null_paths.append(ap+'.text_sha256')
        if a['text_sha256'] is not None: add(ap+'.text_sha256','MODEL_NULL_REQUIRED')
        if cid not in interpretations: add(ap+'.claim_id','V3_CLAIM_BINDING',actual=cid,
            target_type=target[1]['claim_type'] if target else None)
        # Position pairing is exclusively a diagnostic association. No ID or text is changed.
        actual=[(k,t) for k,t in interpretations.items() if t[2]==ai][0]
        actual_id,(cp,c,si)=actual; budget=selection.sections[si]
        if cid!=actual_id: add(cp,'INTERPRETATION_ANNOTATION_MISSING',actual_interpretation=actual_id)
        for key,val,allowed in [('decision_object',a['decision_object'],OBJECTS),
            ('verification.next_decision',a['verification']['next_decision'],OBJECTS),
            ('verification.recipient',a['verification']['recipient'],OWNERS),('verification_owner',a['verification_owner'],OWNERS),
            ('verification.action',a['verification']['action'],ACTIONS),('boundary_type',a['boundary_type'],{'unknown','condition_change'})]:
            if type(val) is not str or val not in allowed: add(ap+'.'+key,'ENUM_STRING_REQUIRED')
        keys(a['decision'],{'change','rationale'},ap+'.decision')
        keys(a['verification'],{'action','recipient','next_decision','purpose'},ap+'.verification')
        refs_ok=set(a['selected_fact_refs'])==set(c['customer_refs'])=={e['fact_ref'] for e in a['evidence_reference']}
        quotes_ok=all(facts.get(e['fact_ref'])==e['source_quote'] for e in a['evidence_reference'])
        if not refs_ok: add(ap+'.selected_fact_refs','V3_PREMISE_BINDING')
        if not quotes_ok: add(ap+'.evidence_reference','V3_EVIDENCE_BINDING')
        expected=dict(
            buyer_implication=f"{a['evidence_basis']} Therefore, the buyer should {a['decision']['change']} for the {OBJECTS[a['decision_object']]}, because {a['decision']['rationale']}.",
            non_applicability=f"{a['boundary_condition']} {budget.required_limitation} The conclusion remains {'unresolved' if a['boundary_type']=='unknown' else 'conditional on the recorded setup'}.",
            verification_action=f"The {a['verification_owner']} should {a['verification']['action']} the {a['verification_artifact']} for the {a['verification']['recipient']} to decide the {OBJECTS[a['verification']['next_decision']]}: {a['verification']['purpose']}. {budget.verification_action}")
        formula_ok=True
        for k,text in expected.items():
            if a[k]!=text: formula_ok=False; add(ap+'.'+k,'V3_REALIZATION_MISMATCH',expected=text)
        joined=' '.join(a[k] for k in ['buyer_implication','non_applicability','verification_action'])
        if joined!=c['text']: add(cp+'.text','V3_BODY_BINDING',annotation_path=ap)
        # Identify precisely which visible part differs, rather than conflating it with hashes.
        for k in ['buyer_implication','non_applicability','verification_action']:
            if a[k] not in c['text']: add(ap+'.'+k,'VISIBLE_PART_NOT_IN_CLAIM',claim_path=cp+'.text')
        rows.append(dict(annotation_claim_id=cid,actual_interpretation_id=actual_id,section_id=a['section_id'],
            exact_target=cid==actual_id,refs_match=refs_ok,quotes_exact=quotes_ok,
            formula_parts_match=formula_ok,body_matches=joined==c['text'],multi_fact=len(c['customer_refs'])>1,
            full_chain=False if len(findings)>start else True,findings=findings[start:]))
    _,candidate=_envelope(raw.decode()); op=value.change_plan_report.operations[0]
    spec=_parse_specification(candidate,expected_change_ref=op.change_id,operation=op)
    native=inspect_specification(value,candidate,spec,current_snapshot_sha256=selection.evidence_snapshot_sha256)
    for c in native.claims:
        if c.deterministic_error:
            add(path_by_id[c.claim_id][0]+'.text',c.deterministic_error,native_claim_id=c.claim_id,
                note='Original native read-only inspection; error may concern proposal as well.')
    write('native-diagnostic-only.json',dict(scope='DIAGNOSTIC_ONLY_NOT_FORMAL_LAYER_4',errors=list(native.errors),
        state=native.state,claims=[asdict(c) for c in native.claims],semantic_approved=False,production_authorized=False))
    kinds=Counter(c['claim_type'] for c in claims)
    metrics=dict(sections=len(sections),claims=len(claims),blocks=sum(s['blocks'] for s in sections),kinds=dict(kinds),
        selected_fact_refs_unique=len({r for c in claims for r in c['customer_refs']}),
        direct_exact_quotes=sum(c['claim_type']=='OBSERVED_PRODUCT_FACT' and len(c['customer_refs'])==1 and c['text']==facts.get(c['customer_refs'][0]) for c in claims),
        proposals_complete=sum(c['claim_type']=='EVIDENCE_BASED_INTERPRETATION' and set(c.get('proposal',{}))=={'procurement_question','reasoning','assumptions','limitation','procurement_action'} for c in claims),
        annotations=len(rows),correct_target_annotations=sum(r['exact_target'] for r in rows),
        full_v3_chains=sum(r['full_chain'] for r in rows),null_hash_placeholders=len(null_paths),
        article_words=len(re.findall(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*",' '.join(c['text'] for c in claims))),
        per_section=sections,diagnostic_finding_counts=dict(Counter(f['code'] for f in findings)))
    write('contract-diagnostics.json',dict(scope='DIAGNOSTIC_ONLY_NOT_ADMISSION',metrics=metrics,findings=findings,
        annotations=rows,hash_placeholders=null_paths,semantic_approved=False,production_authorized=False))
    save_bytes(OUT/'article-reading-view.md',('> SYNTHETIC / TEST ONLY — REJECTED, unmodified candidate text. AI pre-review only; human review pending.\n\n'+'\n'.join(article)).encode())
    save_bytes(OUT/'violation-paths.md',('# Read-only violation paths\n\nNo repaired candidate; zero-based JSON indices. Diagnostic findings are not formal layer results.\n\n'+
        '\n'.join('- `'+f['path']+'` — `'+f['code']+'`' for f in findings)+'\n').encode())
    usage=provider['usage']; meta=strict_json((OUT/'reception.json').read_bytes())
    require(usage['prompt_tokens']==usage['prompt_cache_hit_tokens']+usage['prompt_cache_miss_tokens'] and
        usage['total_tokens']==usage['prompt_tokens']+usage['completion_tokens'],'USAGE_INCONSISTENT')
    # 04:30 UTC is outside both weekday peak windows; no public-holiday inference needed.
    finished=datetime.fromisoformat(meta['finished_at'])
    peak=finished.weekday()<5 and (1<=finished.hour<4 or 6<=finished.hour<10)
    rates=dict(input_hit=0.006,input_miss=0.3,output=1.2) if peak else dict(input_hit=0.003,input_miss=0.15,output=0.6)
    cost=(usage['prompt_cache_hit_tokens']*rates['input_hit']+usage['prompt_cache_miss_tokens']*rates['input_miss']+
        usage['completion_tokens']*rates['output'])/1_000_000
    write('cost-estimate.json',dict(usage=usage,usd_per_million_tokens=rates,period='peak' if peak else 'off-peak',
        estimated_usd=round(cost,9),billed_amount_verified=False,account_balance_queried=False,budget_usd=0.05,
        source='https://api-docs.deepseek.com/quick_start/pricing/',request_sha256=REQUEST_HASH,
        response_sha256=sha(response),model_output_sha256=sha(raw)))
    write('provider-usage.json',usage)
    history=history_fingerprint()
    checks=strict_json((OUT/'preflight-verification.json').read_bytes())
    require(all(sha((PACKAGE/p).read_bytes())==h for p,h in checks['frozen_fingerprint'].items()),'FROZEN_CHANGED')
    row=LEDGER.read(PERMIT)
    require(row[7] is not None,'PERMIT_NOT_CONSUMED')
    write('post-execution-integrity.json',dict(historical_files_unchanged=len(history),frozen_six_files_unchanged=True,
        manifest_bound_files_unchanged=all(sha((ROOT/e['filename']).read_bytes())==e['sha256'] for e in strict_json((PACKAGE/'manifest.json').read_bytes())['files']),
        response_content_exact=True,request_count=meta['request_count'],permit_consumed_at=row[7],
        semantic_approved=False,production_authorized=False))
    print(json.dumps(metrics,indent=2))

if __name__=='__main__': run()
