"""Offline validation only. No model, repair, admission or human approval."""
from dataclasses import asdict
from pathlib import Path
import json
import sys
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(Path(__file__).resolve().parent))
from execute_once import OUT, PACKAGE, BASE, write, history_fingerprint
from tests.test_seo_draft_v3_request_freeze import read_sources,source_context,sha,strict_json,require
from foreign_trade_geo_agent.workflows.draft_contract_v3_experiment import (
    assemble_model_v3_output,_envelope,_error_code,
)
from foreign_trade_geo_agent.core.draft_selection_contract import canonical_json,text_digest
from foreign_trade_geo_agent.workflows.content_draft import _parse_specification
from foreign_trade_geo_agent.core.draft_explanation_contract_v3 import decode_sidecar_v3,inspect_explanations_v3
from foreign_trade_geo_agent.core.draft_candidate_review import inspect_specification
from foreign_trade_geo_agent.adapters.retained_deepseek import save_bytes

def run():
    _,_,_,selection,value=source_context(read_sources())
    meta=strict_json((OUT/'reception.json').read_bytes())
    layers=[]; assembled=None; body=candidate=spec=None
    assembly=dict(result='NOT_RUN',semantic_fields_modified=False,semantic_approved=False,production_authorized=False)
    if not meta.get('reception_success'):
        for i,name in enumerate(['Envelope','Native Candidate Parser','Explanation Contract v3','Native Candidate Validator'],1):
            layers.append(dict(layer=i,name=name,result='NOT_RUN',reason='Complete successful reception required'))
    else:
        raw=(OUT/'model-output.txt').read_bytes(); text=raw.decode()
        try:
            assembled=assemble_model_v3_output(value,selection,text,current_snapshot_sha256=selection.evidence_snapshot_sha256)
            assembly.update(result='PASS',raw_sha256=sha(raw),assembled_sha256=sha(assembled.encode()))
            original=strict_json(raw); completed=strict_json(assembled)
            changed=[]
            def compare(a,b,path='$'):
                if type(a) is dict:
                    require(set(a)==set(b),'ASSEMBLY_KEY_CHANGE')
                    for k in a: compare(a[k],b[k],path+'.'+k)
                elif type(a) is list:
                    require(len(a)==len(b),'ASSEMBLY_LENGTH_CHANGE')
                    for i,(x,y) in enumerate(zip(a,b)): compare(x,y,path+f'[{i}]')
                elif a!=b:
                    require(a is None and path.endswith(('.sidecar_hash','.candidate_hash','.text_sha256')),
                        'ASSEMBLY_SEMANTIC_CHANGE')
                    changed.append(path)
            compare(original,completed)
            assembly['changed_paths']=changed
            save_bytes(OUT/'assembled-envelope.json',assembled.encode())
        except Exception as exc:
            assembly.update(result='FAIL',error=_error_code(exc),raw_sha256=sha(raw),assembled_sha256=None,
                note='Assembler returns no legally assembled result on rejection. No substitute envelope persisted.')
        # Wire envelope/native parsing are permissible on the unchanged raw wire.
        # Hash/relation checks require a successful legal assembly.
        try:
            body,candidate=_envelope(assembled if assembled is not None else text)
            layers.append(dict(layer=1,name='Envelope',result='PASS',scope='assembled' if assembled else 'raw null-hash wire'))
        except Exception as exc:
            layers.append(dict(layer=1,name='Envelope',result='FAIL',errors=[_error_code(exc)]))
        if candidate is not None:
            try:
                op=value.change_plan_report.operations[0]
                spec=_parse_specification(candidate,expected_change_ref=op.change_id,operation=op)
                layers.append(dict(layer=2,name='Native Candidate Parser',result='PASS'))
            except Exception as exc:
                layers.append(dict(layer=2,name='Native Candidate Parser',result='FAIL',errors=[_error_code(exc)]))
        else:
            layers.append(dict(layer=2,name='Native Candidate Parser',result='NOT_RUN',reason='Layer 1 failed'))
        layer3_pass=False
        if spec is not None and assembled is not None:
            try:
                side_raw=canonical_json(body['v3_sidecar'])
                require(body['sidecar_hash']==text_digest(side_raw),'V3_EXPERIMENT_SIDECAR_HASH')
                side=decode_sidecar_v3(side_raw)
                result=inspect_explanations_v3(side,selection,candidate,spec,value,
                    current_snapshot_sha256=selection.evidence_snapshot_sha256)
                layer3_pass=result.status=='PASS'
                layers.append(dict(layer=3,name='Explanation Contract v3',result=result.status,
                    errors=list(result.errors),diagnostics=list(result.diagnostics),
                    note='Unmodified inspector internally calls native validator.'))
            except Exception as exc:
                layers.append(dict(layer=3,name='Explanation Contract v3',result='FAIL',errors=[_error_code(exc)]))
        else:
            layers.append(dict(layer=3,name='Explanation Contract v3',result='NOT_RUN',
                reason='No successful legal assembly' if spec is not None else 'Layer 2 failed'))
        if layer3_pass:
            native=inspect_specification(value,candidate,spec,current_snapshot_sha256=selection.evidence_snapshot_sha256)
            layers.append(dict(layer=4,name='Native Candidate Validator',result='FAIL' if native.errors else 'PASS',
                errors=list(native.errors)))
            write('native-claim-checks.json',[asdict(c) for c in native.claims])
        else:
            layers.append(dict(layer=4,name='Native Candidate Validator',result='NOT_RUN',reason='Layer 3 did not pass'))
    state='PENDING_SEMANTIC_REVIEW' if all(l['result']=='PASS' for l in layers) else 'REJECTED'
    write('assembly-diagnostics.json',assembly)
    result=dict(state=state,layers=layers,layer5='PENDING_SEMANTIC_REVIEW' if state!='REJECTED' else 'NOT_RUN',
        semantic_approved=False,production_authorized=False,finalizer_run=False,human_review='PENDING',
        technical_contract='PASS' if state!='REJECTED' else 'FAIL')
    write('validation-layers.json',result)
    history_fingerprint()
    print(json.dumps(result,indent=2))

if __name__=='__main__': run()
