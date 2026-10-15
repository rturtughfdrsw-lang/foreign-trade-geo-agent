"""Read preserved outputs only: descriptive diagnostics, no Validator or Finalizer."""
from collections import Counter
from datetime import UTC, datetime
import json
from pathlib import Path
import re
import sys

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
sys.path.insert(0, str(ROOT))
from scripts import prepare_seo_draft_v2_flash_preflight as p
from foreign_trade_geo_agent.adapters.retained_deepseek import save_bytes
from foreign_trade_geo_agent.core import content_draft as cd
from foreign_trade_geo_agent.storage.serialization import _decode
from foreign_trade_geo_agent.workflows.content_draft import _parse_specification

PACKAGE = ROOT / 'docs/seo-draft-v2-flash-experiment-preflight'
BASE = p.HISTORY
WORD = re.compile(r"\b[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*\b")


def write(name, value):
    raw = value.encode('utf-8') if type(value) is str else (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    save_bytes(OUT / name, raw)


value = _decode(json.loads((PACKAGE / 'native-input.json').read_bytes()), cd.ContentDraftInput)
selection = json.loads((PACKAGE / 'selection-artifact.json').read_bytes())['payload']
facts = {f.fact_ref: f for source in value.customer_evidence.sources for f in source.facts}
envelope_raw = (OUT / 'model-output.json').read_bytes()
provider = json.loads((OUT / 'response-body.bin').read_bytes())
assert provider['choices'][0]['message']['content'].encode('utf-8') == envelope_raw
envelope = json.loads(envelope_raw, object_pairs_hook=p._strict_object)
baseline_raw = (BASE / 'model-output.txt').read_bytes()
assert p.sha(baseline_raw) == p.FROZEN_V1_OUTPUT_HASH
drafts = {'frozen-v1': json.loads(baseline_raw)['draft'], 'v2': envelope['candidate']['draft']}
summary = json.loads((OUT / 'execution-summary.json').read_bytes())
metrics, indices, routing = {}, {}, {}

for label, draft in drafts.items():
    claims, rows = [], []
    for si, section in enumerate(draft['sections'], 1):
        contract = selection['sections'][si - 1]
        brief = value.change_plan_report.operations[0].new_resource_spec.section_briefs[si - 1]
        local = []
        for bi, block in enumerate(section['blocks'], 1):
            for c in block.get('claims', block.get('items', [])):
                item = dict(c, claim_id=f'CL{len(claims)+1}', section_id=f'S{si}', block=bi)
                claims.append(item)
                local.append(item)
        used = {r for c in local for r in c['customer_refs']}
        sources = {r.split('.')[0] for r in used}
        required = set(brief.supporting_evidence)
        outside = [dict(claim_id=c['claim_id'], fact_refs=[r for r in c['customer_refs']
            if r in facts and not set(facts[r].requirement_ids) & set(brief.requirement_ids)]) for c in local]
        outside = [c for c in outside if c['fact_refs']]
        kinds = Counter(c['claim_type'] for c in local)
        rows.append(dict(section_id=f'S{si}', heading=section['outline_heading'],
            required_source_ids=sorted(required), actual_source_ids=sorted(sources),
            extra_sources=sorted(sources-required), missing_sources=sorted(required-sources),
            outside_requirement_claims=outside, selected_refs=contract['selected_facts'],
            refs_outside_v2_selection=sorted(used-set(contract['selected_facts'])),
            missing_v2_selected_refs=sorted(set(contract['selected_facts'])-used),
            missing_v2_required_direct_refs=sorted(set(contract['required_direct_facts'])-
                {r for c in local if c['claim_type']=='OBSERVED_PRODUCT_FACT' for r in c['customer_refs']}),
            claims=len(local), blocks=len(section['blocks']), claim_types=dict(kinds),
            v2_explanation_minimum=contract['explanation_budget'],
            observed_explanations=kinds['EVIDENCE_BASED_INTERPRETATION']))
    used = {r for c in claims for r in c['customer_refs']}
    interpretations = [c for c in claims if c['claim_type']=='EVIDENCE_BASED_INTERPRETATION']
    identities = {}
    duplicates = []
    for c in claims:
        key = ' '.join(c['text'].casefold().split())
        if key in identities:
            duplicates.append([identities[key], c['claim_id']])
        identities[key] = c['claim_id']
    metrics[label] = dict(sections=len(draft['sections']), blocks=sum(len(s['blocks']) for s in draft['sections']),
        claims=len(claims), claim_types=dict(Counter(c['claim_type'] for c in claims)),
        unique_valid_evidence_refs=len(used & set(facts)), invalid_refs=sorted(used-set(facts)),
        valid_ref_occurrences=sum(r in facts for c in claims for r in c['customer_refs']),
        claims_with_legal_nonempty_refs=sum(bool(c['customer_refs']) and set(c['customer_refs'])<=set(facts) for c in claims),
        wrong_ps_claims=sum(bool(c['page_refs'] or c['source_refs']) for c in claims),
        direct_quotes_exact=sum(c['claim_type']=='OBSERVED_PRODUCT_FACT' and len(c['customer_refs'])==1
            and c['text']==facts[c['customer_refs'][0]].quote for c in claims),
        sections_with_extra_source=sum(bool(r['extra_sources']) for r in rows),
        outside_requirement_claims=sum(len(r['outside_requirement_claims']) for r in rows),
        body_words=len(WORD.findall(' '.join(c['text'] for c in claims))),
        interpretation_words=len(WORD.findall(' '.join(c['text'] for c in interpretations))),
        interpretation_word_counts=[len(WORD.findall(c['text'])) for c in interpretations],
        explicit_annotation_count=len(envelope['explanations']) if label=='v2' else 0,
        duplicate_claim_pairs=duplicates,
        scope='Identifier/routing counters only; no semantic correctness or Validator approval implied.')
    indices[label], routing[label] = claims, rows

annotations = []
v2claims = {c['claim_id']: c for c in indices['v2']}
for a in envelope['explanations']:
    parts = [a[k] for k in ('buyer_implication','non_applicability','verification_action')]
    counts = [len(WORD.findall(x)) for x in parts]
    actual = v2claims.get(a['explanation_claim_id'])
    annotations.append(dict(**a, part_word_counts=counts, total_words=sum(counts),
        minima_satisfied=all(n>=m for n,m in zip(counts,(20,12,20))),
        annotated_claim_type=actual['claim_type'] if actual else None,
        visible_body_matches=bool(actual and ' '.join(parts)==actual['text'])))

# Supplemental native-Parser diagnosis only. No repeat response adapter, Validator or Finalizer.
operation = value.change_plan_report.operations[0]
native_raw = p.canonical_json(envelope['candidate'])
try:
    _parse_specification(native_raw, expected_change_ref=operation.change_id, operation=operation)
    native_parser = 'PASS'
except ValueError as exc:
    native_parser = 'FAIL: ' + str(exc)
diagnostic = dict(original_experiment_parser=summary['parser'],
    original_error=summary.get('failure'), native_parser_readonly_diagnostic=native_parser,
    envelope_keys_exact=set(envelope)=={'candidate','explanations'}, duplicate_keys=False,
    first_identifiable_adapter_failure='EXPLANATION_PART_DEPTH',
    evidence='First annotation CL6 has word counts 40/7/7; required minima are 20/12/20.',
    validator='NOT_RUN', finalizer='NOT_RUN', annotation_diagnostics=annotations,
    no_output_repair=True, no_validator_invocation=True)
write('parser-diagnostics.json', diagnostic)
write('comparison-metrics.json', metrics)
write('section-routing-comparison.json', routing)
write('claims-comparison.json', indices)
article = ['# V2 preserved model prose', '> SYNTHETIC / TEST ONLY. Rejected response; Parser failed. Reading view only; no finalization or approval.']
for si, section in enumerate(drafts['v2']['sections'], 1):
    article.append('## ' + section['outline_heading'])
    for c in indices['v2']:
        if c['section_id']==f'S{si}':
            article.append(f"[{c['claim_id']} / {c['claim_type']}]\n\n{c['text']}")
write('article-reading-view.md', '\n\n'.join(article)+'\n')
verified = p.verify_manifest(PACKAGE, '5bfc54d91e5c0ba24b3043ef10871e937a84a9ad2abae968ad0fd86f06f85754')
write('post-execution-integrity.json', dict(**verified, checked_at=datetime.now(UTC).isoformat(),
    source_unchanged=True, source_files=len(p.source_integrity()), request_copy_sha256=p.sha((OUT/'request.json').read_bytes()),
    raw_response_sha256=p.sha((OUT/'response-body.bin').read_bytes()),
    model_output_sha256=p.sha(envelope_raw), baseline_unchanged=True))
print(json.dumps(dict(metrics=metrics, native_parser=native_parser,
    first_failure=diagnostic['first_identifiable_adapter_failure'], integrity=verified), indent=2))
