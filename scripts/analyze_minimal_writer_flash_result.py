"""Offline stored-byte diagnostics only. Never repairs output or calls a provider."""
from collections import Counter
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal
import json
import re

from scripts.run_minimal_writer_flash_once import OUT, ROOT, REQUEST_HASH, MANIFEST_HASH, frozen, write, preflight
from foreign_trade_geo_agent.core import content_draft as cd, minimal_writer_wire as mw
from foreign_trade_geo_agent.workflows.minimal_writer_experiment import run_minimal_experiment, render_review


def analyze():
    _,_,_=preflight()
    sources={n:(frozen.DEST/n).read_bytes() for n in frozen.INPUT_PATHS}
    value,selection,manifest=frozen.context(sources)
    reception=json.loads((OUT/'reception.json').read_bytes())
    response=(OUT/'response-body.bin').read_bytes()
    frozen.require(frozen.sha(response)==reception['response_sha256'],'RESPONSE_INTEGRITY')
    provider=mw.strict_json(response.decode('utf-8'),256*1024)
    output=(OUT/'model-output.txt').read_bytes()
    frozen.require(frozen.sha(output)==reception['model_text_sha256'],'MODEL_TEXT_INTEGRITY')
    frozen.require(provider['choices'][0]['message']['content'].encode('utf-8')==output,'PROVIDER_CONTENT_BINDING')
    text=output.decode('utf-8')
    result=run_minimal_experiment(value,selection,manifest,text,current_snapshot_sha256=selection.evidence_snapshot_sha256)
    write(OUT,'native-experiment-result.json',asdict(result))
    body=mw.strict_json(text)
    expected={s.slot_id:s for s in manifest.slots if s.kind=='explanation'}
    sections={s.section_id:s for s in selection.sections}
    facts=value.customer_evidence.quote_map()
    diagnostics=[]
    views=['# Real DeepSeek Flash output — TEST ONLY / UNVALIDATED',
           'Exact model field texts below. AI-assisted review only; not an admitted native article.']
    for answer in body.get('slots',[]):
        sid=answer.get('slot_id'); slot=expected.get(sid)
        errors=[]
        try:
            mw.decode_wire(frozen.encode(dict(request_id=body['request_id'],slots=[answer])).decode())
        except ValueError as exc:
            errors.append(str(exc))
        lengths={k:len(answer[k]) for k in ('buyer_implication','assumptions','boundary_condition','verification_action')
                 if type(answer.get(k)) is str}
        over={k:n for k,n in lengths.items() if n>(150 if k in {'boundary_condition','verification_action'} else 300)}
        if slot:
            refs=answer.get('premise_refs',[])
            if not set(refs)<=set(slot.allowed_fact_refs): errors.append('MW_PREMISE_OUTSIDE_SLOT')
            section=sections[slot.section_id]
            if answer.get('status')=='answered' and (answer.get('boundary_condition')!=section.required_limitation
                or answer.get('verification_action')!=section.verification_action): errors.append('MW_PLAN_BOUNDARY_CONFLICT')
            combined=' '.join(answer.get(k,'') for k in ('buyer_implication','assumptions','boundary_condition','verification_action'))
            if len(combined)>slot.budget: errors.append('MW_TEXT_BUDGET')
        else:
            errors.append('MW_REQUIRED_SLOT_SET')
            refs=[]; combined=''
        # Diagnostic predicates from native numeric policy, on ORIGINAL fields.
        # No candidate assembled, repaired, admitted or marked Native Validator PASS.
        numeric_sentences=[]
        for field in ('buyer_implication','assumptions','boundary_condition','verification_action'):
            for sentence in re.split(r'(?<=[.!?])\s+',answer.get(field,'')):
                quantities=[e for e in cd.extract_numeric_expressions(sentence) if not re.fullmatch(r'[a-z][a-z0-9_-]*',e)]
                if quantities and not any(sentence in facts.get(r,'') for r in refs):
                    numeric_sentences.append(dict(field=field,text=sentence,expressions=quantities,
                        diagnostic='Native numeric-context predicate would reject this newly composed quantity sentence'))
        evidence='\n'.join(cd._normalized_text(facts.get(r,'')) for r in refs)
        grounding=cd._validate_numeric_grounding(cd._normalized_text(combined),evidence)
        diagnostics.append(dict(slot_id=sid,status=answer.get('status'),exact_answer_fields=set(answer)==mw.ANSWER_FIELDS,
            field_characters=lengths,over_limit_fields=over,independent_wire_errors=errors,
            premise_refs=refs,allowed_fact_refs=list(slot.allowed_fact_refs) if slot else [],
            refs_allowed=bool(slot) and set(refs)<=set(slot.allowed_fact_refs),
            boundary_exact=bool(slot) and answer.get('boundary_condition')==sections[slot.section_id].required_limitation,
            action_exact=bool(slot) and answer.get('verification_action')==sections[slot.section_id].verification_action,
            combined_characters=len(combined),numeric_context_diagnostic=numeric_sentences,
            isolated_native_grounding_predicate=grounding,
            numeric_diagnostic_scope='Isolated predicates on raw model text; not a full Native Validator result'))
        views.append('\n## '+str(sid)+' — '+(slot.reader_subquestion if slot else 'Unknown slot'))
        views.append('Premises: '+', '.join(refs))
        for field in ('buyer_implication','assumptions','boundary_condition','verification_action','missing_information'):
            if field in answer: views.append('\n'+field+':\n\n'+answer[field])
        views.append('\nAllowed source comparison:')
        if slot:
            for ref in slot.allowed_fact_refs: views.append('- '+ref+': '+facts[ref])
    ids=[a.get('slot_id') for a in body.get('slots',[])]
    technical=dict(TECHNICAL='PASS' if reception['reception_success'] and result.ready_for_review else 'FAIL',
        json='PASS',top_level_exact_fields=set(body)=={'request_id','slots'},request_id_exact=body.get('request_id')==mw.request_id(manifest),
        slot_coverage=dict(expected=len(expected),observed=len(ids),missing=sorted(set(expected)-set(ids)),
                           unknown=sorted(set(ids)-set(expected)),duplicate=[n for n,c in Counter(ids).items() if c>1]),
        slot_status_counts=dict(Counter(a.get('status') for a in body['slots'])),
        wire=result.minimal_wire,native_parser=result.native_parser,native_validator=result.native_validator,
        native_candidate_assembled=bool(result.candidate_json),first_failure=result.errors[0] if result.errors else None,
        original_errors=list(result.errors),slots=diagnostics,
        overlength_slots=sum(bool(d['over_limit_fields']) for d in diagnostics),
        numeric_context_diagnostic_slots=sum(bool(d['numeric_context_diagnostic']) for d in diagnostics),
        native_validation_not_bypassed=True,model_text_sha256=frozen.sha(output),response_sha256=frozen.sha(response),
        request_sha256=REQUEST_HASH,manifest_sha256=MANIFEST_HASH,semantic_approved=False,production_authorized=False)
    write(OUT,'technical-validation.json',technical)
    (OUT/'slot-reading-view.md').write_text('\n\n'.join(views)+'\n',encoding='utf-8')
    if result.candidate_json:
        (OUT/'native-candidate.json').write_bytes(result.candidate_json.encode('utf-8'))
        (OUT/'explanation-bindings.json').write_bytes(result.bindings_json.encode('utf-8'))
        (OUT/'native-review.md').write_text(render_review(result),encoding='utf-8')
    usage=provider.get('usage')
    write(OUT,'usage-full.json',usage)
    p=usage['prompt_tokens']; c=usage['completion_tokens']
    hit=usage.get('prompt_cache_hit_tokens',0); miss=usage.get('prompt_cache_miss_tokens',p-hit)
    peak=(Decimal(hit)*Decimal('0.006')+Decimal(miss)*Decimal('0.3')+Decimal(c)*Decimal('1.2'))/Decimal(1000000)
    off=peak/2
    start=json.loads((OUT/'attempt-started.json').read_bytes())['started_at_utc']
    dt=datetime.fromisoformat(start); hour=dt.hour+dt.minute/60+dt.second/3600
    is_peak=dt.weekday()<5 and (1<=hour<4 or 6<=hour<10)
    cost=dict(usage=usage,peak_usd=str(peak),off_peak_usd=str(off),start_utc=start,
        schedule_peak=is_peak,estimated_charge_usd=str(peak if is_peak else off),
        basis='Current official USD rates times provider usage; no independent billing invoice inspected',
        public_holiday_caveat='Peak upper estimate remains safe if a public holiday discount applies',
        authorized_budget_usd=0.05,within_budget=peak<=Decimal('0.05'),real_api_calls=reception['real_api_calls'])
    write(OUT,'cost-record.json',cost)
    before=json.loads((OUT/'baseline-before.json').read_bytes())
    changed=[n for n,h in before.items() if not (ROOT/n).is_file() or frozen.sha((ROOT/n).read_bytes())!=h]
    integrity=dict(baseline_files=len(before),unchanged=len(before)-len(changed),changed=changed,
        frozen_verification=frozen.verify_package(frozen.DEST,MANIFEST_HASH),old_results_unchanged=not changed)
    write(OUT,'integrity-after.json',integrity)
    frozen.require(not changed,'POST_EXECUTION_WORKSPACE_DRIFT')
    print(json.dumps(dict(TECHNICAL=technical['TECHNICAL'],first_failure=technical['first_failure'],
        overlength_slots=technical['overlength_slots'],numeric_context_diagnostic_slots=technical['numeric_context_diagnostic_slots'],
        estimated_charge_usd=cost['estimated_charge_usd'],real_api_calls=reception['real_api_calls'],unchanged=len(before))))


if __name__=='__main__': analyze()
