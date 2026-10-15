"""Build exact-text reading views and counters; never alter the live output."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
sys.path.insert(0, str(ROOT))
from foreign_trade_geo_agent.adapters.retained_deepseek import save_bytes
from foreign_trade_geo_agent.core import content_draft as cd
from foreign_trade_geo_agent.storage.serialization import _decode


def write(name, value):
    raw = value.encode() if isinstance(value, str) else (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()
    save_bytes(OUT / name, raw)


FROZEN = ROOT / 'docs/seo-draft-contract-offline-2026-10-12/frozen-v1'
material = json.loads((FROZEN / 'user-material.json').read_bytes())
facts = {f['fact_ref']: f for s in material['customer_evidence']['sources'] for f in s['facts']}
text = (OUT / 'model-output.txt').read_text('utf-8')
response = json.loads((OUT / 'response-body.bin').read_bytes())
assert response['choices'][0]['message']['content'] == text
draft = json.loads(text)['draft']
validation = json.loads((OUT / 'candidate-validation.json').read_bytes())
checks = {c['claim_id']: c for c in validation['claims']}
title = material['change']['new_resource']['proposed_title']
article = ['# ' + title,
    '> SYNTHETIC / TEST ONLY. Original live frozen-v1 candidate; Validator rejected. Title from frozen Plan. All body claims are verbatim, in original order. This is a reading view, not a finalized or approved draft.']
annotated = ['# Frozen-v1 live output: exact claims and evidence',
    '> AI audit annotations are separate from unchanged model prose. Deterministic checks do not certify semantic correctness.']
claims, sections = [], []
for si, (section, brief) in enumerate(zip(draft['sections'], material['change']['new_resource']['section_briefs']), 1):
    article.append('## ' + section['outline_heading'])
    annotated.append(f"## S{si}: {section['outline_heading']}")
    annotated.append(f"Question: {brief['reader_question']}\n\nRequired sources: {', '.join(brief['supporting_evidence'])}; requirements: {', '.join(brief['requirement_ids'])}.")
    refs = set()
    outside = []
    for bi, block in enumerate(section['blocks'], 1):
        group = block.get('claims', block.get('items', []))
        article.append(' '.join(c['text'] for c in group) if block['kind'] == 'PARAGRAPH' else '\n'.join('- ' + c['text'] for c in group))
        for c in group:
            cid = f'CL{len(claims) + 1}'
            check = checks[cid]
            claims.append(dict(c, claim_id=cid, section=si, block=bi, native_error=check['deterministic_error']))
            refs.update(c['customer_refs'])
            bad = [r for r in c['customer_refs'] if r in facts and not set(facts[r]['requirement_ids']) & set(brief['requirement_ids'])]
            if bad:
                outside.append(dict(claim_id=cid, fact_refs=bad))
            annotated.append(f"### {cid} / S{si} B{bi} / {c['claim_type']}\n\n{c['text']}")
            annotated.append('Audit metadata: refs=' + (', '.join(c['customer_refs']) or '(none)')
                + '; native claim error=' + (check['deterministic_error'] or '(none; not semantic approval)')
                + '; outside section requirements=' + (', '.join(bad) or '(none)') + '.')
            if 'proposal' in c:
                annotated.append('Original proposal metadata:\n\n```json\n' + json.dumps(c['proposal'], ensure_ascii=False, indent=2) + '\n```')
            if c['customer_refs']:
                annotated.append('Bound evidence (source offset and exact premise):\n\n' + '\n\n'.join(check['evidence_details']))
    actual_sources = {r.split('.')[0] for r in refs}
    sections.append(dict(section=si, heading=section['outline_heading'],
        required_requirements=brief['requirement_ids'], required_source_ids=brief['supporting_evidence'],
        actual_source_ids=sorted(actual_sources), extra_source_ids=sorted(actual_sources-set(brief['supporting_evidence'])),
        missing_source_ids=sorted(set(brief['supporting_evidence'])-actual_sources), outside_question=outside))
write('article-full.md', '\n\n'.join(article) + '\n')
write('article-annotated.md', '\n\n'.join(annotated) + '\n')
write('claims-index.json', claims)
write('section-routing-diagnostics.json', sections)
used = {r for c in claims for r in c['customer_refs']}
interpretations = [c for c in claims if c['claim_type'] == 'EVIDENCE_BASED_INTERPRETATION']
body = '\n\n'.join(c['text'] for c in claims)
word_re = r"\b[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*\b"
metrics = dict(sections=len(draft['sections']), blocks=sum(len(s['blocks']) for s in draft['sections']),
    claims=len(claims), claim_limit=cd.MAX_CLAIMS_PER_DRAFT,
    claim_types=dict(Counter(c['claim_type'] for c in claims)),
    claims_with_nonempty_valid_customer_refs=sum(bool(c['customer_refs']) and set(c['customer_refs']) <= set(facts) for c in claims),
    e_ref_claims_without_claim_error=sum(bool(c['customer_refs']) and not c['native_error'] for c in claims),
    invalid_fact_refs=sorted(used-set(facts)), wrong_ps_claims=sum(bool(c['page_refs'] or c['source_refs']) for c in claims),
    wrong_ps_ref_count=sum(len(c['page_refs']) + len(c['source_refs']) for c in claims),
    unique_fact_refs=len(used & set(facts)), fact_bank_size=len(facts), fact_coverage=len(used & set(facts))/len(facts),
    missing_fact_refs=sorted(set(facts)-used),
    direct_quotes_exact=sum(c['claim_type'] == 'OBSERVED_PRODUCT_FACT' and len(c['customer_refs']) == 1 and c['text'] == facts[c['customer_refs'][0]]['quote'] for c in claims),
    interpretation_proposals=sum('proposal' in c for c in interpretations), multi_fact_interpretations=sum(len(c['customer_refs']) > 1 for c in interpretations),
    interpretation_claims_without_native_claim_error=sum(c['native_error'] is None for c in interpretations),
    native_claim_errors={c['claim_id']: c['native_error'] for c in claims if c['native_error']},
    body_words=len(re.findall(word_re, body)),
    title_headings_and_body_words=len(re.findall(word_re, title + ' ' + ' '.join(s['outline_heading'] for s in draft['sections']) + ' ' + body)),
    body_interpretation_words=len(re.findall(word_re, ' '.join(c['text'] for c in interpretations))),
    output_bytes=len(text.encode()), response_bytes=len((OUT/'response-body.bin').read_bytes()),
    note='Identifier validity, exact quotes and global fact coverage are different from correct section routing, semantic validity and whole-candidate admission. Full 43-fact coverage is descriptive, not a quota in frozen-v1.')
write('metrics.json', metrics)
write('interpretation-proposals.json', interpretations)
value = _decode(json.loads((OUT/'native-input.json').read_bytes()), cd.ContentDraftInput)
ev = cd._build_evidence_context(value.change_plan_report.operations[0], value.site_content, value.opportunity_report)
first_party_text = ev.first_party_text + ' ' + ' '.join(s.quote for s in value.customer_evidence.sources)
c = claims[39]
write('competitor-diagnostic.json', dict(claim_id=c['claim_id'], native_error=c['native_error'],
    title_case_runs=cd._TITLE_CASE_RUN_RE.findall(c['text']),
    native_matched_literal=cd._has_competitor_mention(c['text'], first_party_text=first_party_text),
    ai_reading='RFQ is a procurement acronym, not a competitor name. This diagnostic does not change the rejection or authorize bypass.',
    source_modified=False, candidate_modified=False))

# Compare exact model texts, not formatted reports or obsolete validator verdicts.
comparisons = []
for label, directory in [('old_contract', ROOT/'docs/seo-flash-quality-live-2026-10-12'),
                         ('previous_flash', OUT.parent), ('frozen_v1', OUT)]:
    original = (directory/'model-output.txt').read_bytes()
    other = json.loads(original)['draft']
    groups = [c for s in other['sections'] for b in s['blocks'] for c in b.get('claims', b.get('items', []))]
    other_input = _decode(json.loads((directory/'native-input.json').read_bytes()), cd.ContentDraftInput)
    wire = json.loads((directory/'request.json').read_bytes())
    comparisons.append(dict(label=label, directory=directory.relative_to(ROOT).as_posix(),
        request_sha256=hashlib.sha256((directory/'request.json').read_bytes()).hexdigest(),
        model_text_sha256=hashlib.sha256(original).hexdigest(), claims=len(groups),
        valid_e_ref_claims=sum(bool(c.get('customer_refs')) and set(c['customer_refs']) <= set(facts) for c in groups),
        interpretations=sum(c['claim_type']=='EVIDENCE_BASED_INTERPRETATION' for c in groups),
        proposals=sum('proposal' in c for c in groups),
        body_words=len(re.findall(word_re, ' '.join(c['text'] for c in groups))),
        title_headings_body_words=len(re.findall(word_re, title + ' ' + ' '.join(s['outline_heading'] for s in other['sections']) + ' ' + ' '.join(c['text'] for c in groups))),
        customer_sources_equal=other_input.customer_evidence.sources==value.customer_evidence.sources,
        change_plan_equal=other_input.change_plan_report==value.change_plan_report,
        writing_brief_equal=other_input.writing_brief==value.writing_brief,
        system_prompt_equal=wire['messages'][0]['content']==material.get('__never__', json.loads((OUT/'request.json').read_bytes())['messages'][0]['content']),
        user_material_equal=wire['messages'][1]['content']==json.loads((OUT/'request.json').read_bytes())['messages'][1]['content']))
write('historical-comparison.json', comparisons)
print(json.dumps(dict(metrics=metrics, comparison=comparisons, competitor=json.loads((OUT/'competitor-diagnostic.json').read_bytes())), ensure_ascii=False, indent=2))
