"""Read-only extraction/diagnosis; never edits the model response or native code."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
sys.path.insert(0,str(ROOT))
from foreign_trade_geo_agent.core import content_draft as cd
from foreign_trade_geo_agent.adapters.retained_deepseek import save_bytes

def save(name,value):
    raw = value.encode() if isinstance(value,str) else (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()
    save_bytes(OUT/name,raw)

summary = json.loads((OUT/'execution-summary.json').read_bytes())
native = Path(summary['output_directory'])
for name in ('request.json','response-body.bin','model-output.txt','rejected-candidate.txt','native-input.json'):
    if (native/name).exists():
        save_bytes(OUT/name,(native/name).read_bytes())
response = json.loads((OUT/'response-body.bin').read_bytes())
text = (OUT/'model-output.txt').read_text('utf-8')
assert response['choices'][0]['message']['content'] == text
draft = json.loads(text)['draft']
material = json.loads((ROOT/'docs/seo-flash-request-preflight-2026-10-12/final-v2/user-material.json').read_bytes())
facts = {f['fact_ref']:f for s in material['customer_evidence']['sources'] for f in s['facts']}
validation = json.loads((OUT/'candidate-validation.json').read_bytes())
by_id = {c['claim_id']:c for c in validation['claims']}
title = material['change']['new_resource']['proposed_title']
article = ['# '+title, '> SYNTHETIC / TEST ONLY. Original DeepSeek candidate; Validator rejected. Title from frozen Plan; every body claim is unchanged. No human approval or production authority.']
annotated = ['# SYNTHETIC / TEST ONLY — original claim locations']
claims, sections = [], []
for si,(section,brief) in enumerate(zip(draft['sections'],material['change']['new_resource']['section_briefs']),1):
    article.append('## '+section['outline_heading'])
    annotated.append(f"## S{si}: {section['outline_heading']}")
    section_refs=set()
    outside=[]
    for bi,block in enumerate(section['blocks'],1):
        group=block.get('claims',block.get('items',[]))
        article.append(' '.join(c['text'] for c in group) if block['kind']=='PARAGRAPH' else '\n'.join('- '+c['text'] for c in group))
        for c in group:
            cid=f'CL{len(claims)+1}'
            claims.append(dict(c,claim_id=cid,section=si,block=bi,native_error=by_id[cid]['deterministic_error']))
            section_refs.update(c.get('customer_refs',[]))
            bad=[r for r in c.get('customer_refs',[]) if not set(facts[r]['requirement_ids']) & set(brief['requirement_ids'])]
            if bad: outside.append(dict(claim_id=cid,fact_refs=bad))
            annotated.append(f"**{cid} · S{si}/B{bi} · {c['claim_type']} · {', '.join(c.get('customer_refs',[]))}**\n\n{c['text']}")
    sections.append(dict(section=si,heading=section['outline_heading'],required_requirements=brief['requirement_ids'],
        required_source_ids=brief['supporting_evidence'],actual_source_ids=sorted({r.split('.')[0] for r in section_refs}),outside_question=outside))
save('article-full.md','\n\n'.join(article)+'\n')
save('article-annotated.md','\n\n'.join(annotated)+'\n')
save('claims-index.json',claims)
used={r for c in claims for r in c.get('customer_refs',[])}
interpretations=[c for c in claims if c['claim_type']=='EVIDENCE_BASED_INTERPRETATION']
body='\n\n'.join(c['text'] for c in claims)
word_re=r"\b[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*\b"
metrics=dict(sections=len(draft['sections']),blocks=sum(len(s['blocks']) for s in draft['sections']),claims=len(claims),
    claim_types=dict(Counter(c['claim_type'] for c in claims)),
    claims_with_nonempty_valid_customer_refs=sum(bool(c.get('customer_refs')) and set(c['customer_refs'])<=set(facts) for c in claims),
    invalid_fact_refs=sorted(used-set(facts)),wrong_ps_claims=sum(bool(c['page_refs'] or c['source_refs']) for c in claims),
    factual_claims_without_valid_evidence=sum(c['claim_type'] in {'OBSERVED_PRODUCT_FACT','EVIDENCE_BASED_INTERPRETATION'} and not (set(c.get('customer_refs',[])) & set(facts)) for c in claims),
    unreferenced_nonfactual_claims=sum(not c.get('customer_refs') for c in claims),
    unique_fact_refs=len(used),missing_fact_refs=sorted(set(facts)-used),
    direct_quotes_exact=sum(c['claim_type']=='OBSERVED_PRODUCT_FACT' and len(c['customer_refs'])==1 and c['text']==facts[c['customer_refs'][0]]['quote'] for c in claims),
    interpretation_proposals=len([c for c in interpretations if 'proposal' in c]),
    multi_fact_interpretations=sum(len(c['customer_refs'])>1 for c in interpretations),
    interpretation_claims_without_native_claim_error=sum(c['native_error'] is None for c in interpretations),
    native_claim_errors={c['claim_id']:c['native_error'] for c in claims if c['native_error']},
    body_words=len(re.findall(word_re,body)),
    title_headings_and_body_words=len(re.findall(word_re,title+' '+' '.join(s['outline_heading'] for s in draft['sections'])+' '+body)),
    output_bytes=len(text.encode()),response_bytes=len((OUT/'response-body.bin').read_bytes()),
    body_interpretation_words=len(re.findall(word_re,' '.join(c['text'] for c in interpretations))),
    note='Valid ref identifiers and claim-level checks do not certify semantic relevance or article admission. Word counts use the same regex as the previous experiment.')
save('metrics.json',metrics)
save('section-routing-diagnostics.json',sections)
diagnostics=[]
for n in (7,19):
    c=claims[n-1]
    evidence='\n'.join(cd._normalized_text(facts[r]['quote']) for r in c['customer_refs'])
    diagnostics.append(dict(claim_id=c['claim_id'],native_error=c['native_error'],text=c['text'],
        exact_single_source_quote=len(c['customer_refs'])==1 and c['text']==facts[c['customer_refs'][0]]['quote'],
        expressions=[dict(expression=e,bare=cd._is_bare_number(e),present=cd._numeric_expression_is_present(e,evidence))
            for e in cd.extract_numeric_expressions(c['text'])]))
save('numeric-diagnostics.json',diagnostics)
usage=response['usage']
hit,miss,completion=(usage[k] for k in ('prompt_cache_hit_tokens','prompt_cache_miss_tokens','completion_tokens'))
save('cost-estimate.json',dict(currency='USD',usage=usage,
    peak_usd=(hit*.006+miss*.3+completion*1.2)/1e6,
    off_peak_usd=(hit*.003+miss*.15+completion*.6)/1e6,
    applicable_estimate='peak: Monday 2026-10-12 03:46 UTC, inside 01:00-04:00 UTC window',
    invoice_verified=False,account_balance_queried=False,
    source='https://api-docs.deepseek.com/quick_start/pricing/'))
save('interpretation-proposals.json',interpretations)
print(json.dumps(metrics,indent=2))
