"""Read-only extraction from the completed response; no provider calls or fixes."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]
FROZEN=ROOT/'docs/seo-full-article-budget-2026-10-11/final-v2'
def save(name,value):
    with (OUT/name).open('x',encoding='utf-8',newline='\n') as f:
        f.write(value if isinstance(value,str) else json.dumps(value,ensure_ascii=False,indent=2)+'\n')

response_raw=(OUT/'response-body.bin').read_bytes()
response=json.loads(response_raw)
text=(OUT/'model-output.txt').read_text('utf-8')
assert response['choices'][0]['message']['content']==text
draft=json.loads(text)['draft']
material=json.loads((FROZEN/'user-material.json').read_bytes())
title='How to Choose a CNC Machining Center: A Practical Buyer\'s Guide'
article=[f'# {title}',
    '> SYNTHETIC / TEST ONLY — 原始失败候选的只读排版。标题取自冻结 Plan；正文逐条来自原始模型输出，未润色、未补证据、未修复引用。Validator 已拒绝，禁止作为合格稿交付。']
annotated=[f'# SYNTHETIC / TEST ONLY — rejected candidate with claim locations']
claims=[]
for si,section in enumerate(draft['sections'],1):
    article.append('## '+section['outline_heading'])
    annotated.append(f"## S{si}: {section['outline_heading']}")
    for bi,block in enumerate(section['blocks'],1):
        group=block.get('claims',block.get('items',[]))
        article.append(' '.join(c['text'] for c in group) if block['kind']=='PARAGRAPH'
            else '\n'.join('- '+c['text'] for c in group))
        for c in group:
            claims.append(dict(c,claim_id=f'CL{len(claims)+1}',section=si,block=bi))
            annotated.append(f"**CL{len(claims)} · S{si}/B{bi} · {c['claim_type']}**\n\n{c['text']}")
save('article-full.md','\n\n'.join(article)+'\n')
save('article-annotated.md','\n\n'.join(annotated)+'\n')
save('claims-index.json',claims)

# Explicit editorial crosswalk for diagnosis only. These refs were NOT generated
# by the model, NOT inserted into its candidate, and do NOT repair its binding.
refs=['E2.F01','E2.F05','E2.F02','E2.F06','E2.F03','E2.F07','E2.F04','E2.F08','E2.F09','E5.F01','E5.F02',None,
      'E1.F01','E3.F03','E3.F01','E3.F02','E3.F04','E5.F03',None,
      'E4.F01','E4.F02','E4.F03','E4.F06','E4.F08',None,
      'E3.F05','E3.F06','E3.F07','E4.F07','E4.F04','E4.F05','E5.F04',None,
      'E6.F01','E6.F02','E6.F03','E6.F04','E6.F05','E6.F06','E5.F05',
      'E7.F01','E7.F02','E7.F03','E7.F04','E7.F05','E7.F06','E7.F07',None]
assert len(refs)==len(claims)==48
facts={f['fact_ref']:f for s in material['customer_evidence']['sources'] for f in s['facts']}
assert set(r for r in refs if r)==set(facts)
crosswalk=[dict(claim_id=c['claim_id'],model_text=c['text'],model_customer_refs=c.get('customer_refs',[]),
    diagnostic_source_only=r,source_quote=facts[r]['quote'] if r else None,
    status='EDITORIAL_CROSSWALK_ONLY_NOT_MODEL_BINDING_NOT_APPROVAL') for c,r in zip(claims,refs)]
save('editorial-source-crosswalk.json',crosswalk)
body='\n\n'.join(c['text'] for c in claims)
word_re=r"\b[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*\b"
metrics=dict(sections=len(draft['sections']),blocks=sum(len(s['blocks']) for s in draft['sections']),
    claims=len(claims),claim_types=dict(Counter(c['claim_type'] for c in claims)),
    claims_with_customer_refs=sum(bool(c.get('customer_refs')) for c in claims),
    interpretation_proposals=sum('proposal' in c for c in claims),
    facts_in_editorial_crosswalk=len(facts),model_fact_binding_count=0,
    body_words_same_regex_as_historical=len(re.findall(word_re,body)),
    title_headings_and_body_words=len(re.findall(word_re,title+' '+ ' '.join(s['outline_heading'] for s in draft['sections'])+' '+body)),
    body_whitespace_words=len(body.split()),body_chars=len(body),
    output_chars=len(text),output_bytes=len(text.encode('utf-8')),
    note='Counts only; no automatic quality scoring. Editorial crosswalk is not successful evidence coverage.')
save('metrics.json',metrics)
usage=response['usage']
hit,miss,completion=(usage[k] for k in ('prompt_cache_hit_tokens','prompt_cache_miss_tokens','completion_tokens'))
save('cost-estimate.json',dict(currency='USD',off_peak_usd=(hit*.003+miss*.15+completion*.6)/1e6,
    peak_equivalent_usd=(hit*.006+miss*.3+completion*1.2)/1e6,
    usage=usage,price_source='https://api-docs.deepseek.com/quick_start/pricing/',
    invoice_verified=False,account_balance_queried=False))
print(json.dumps(metrics,indent=2))
print((OUT/'cost-estimate.json').read_text())
