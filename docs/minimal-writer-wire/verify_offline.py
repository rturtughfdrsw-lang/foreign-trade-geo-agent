"""Reproducible local verification/artifacts; external sockets and DNS are blocked.

Run with .venv/Scripts/python.exe docs/minimal-writer-wire/verify_offline.py
{new,related,full,artifacts,integrity}. Writes only beneath this new directory.
"""
from contextlib import redirect_stdout, redirect_stderr
from dataclasses import asdict
import hashlib
import ipaddress
import json
from pathlib import Path
import socket
import sys
import time
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
blocked = []


def write_json(path, value):
    from foreign_trade_geo_agent.core.draft_selection_contract import canonical_json
    path.write_text(canonical_json(value)+'\n', encoding='utf-8')


def allowed(host):
    if host in {'localhost', 'localhost.'}:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


original_connect = socket.socket.connect
original_connect_ex = socket.socket.connect_ex
original_resolve = socket.getaddrinfo
original_sendto = socket.socket.sendto


def check(host):
    if not allowed(host):
        blocked.append('external_network_blocked')
        raise OSError('OFFLINE_EXTERNAL_NETWORK_BLOCKED')


def connect(sock, address):
    if isinstance(address, tuple): check(address[0])
    return original_connect(sock,address)


def connect_ex(sock, address):
    if isinstance(address, tuple): check(address[0])
    return original_connect_ex(sock,address)


def resolve(host, *args, **kwargs):
    if host is not None: check(host)
    return original_resolve(host,*args,**kwargs)


def sendto(sock, data, *args):
    if args and isinstance(args[-1],tuple): check(args[-1][0])
    return original_sendto(sock,data,*args)


def tests(mode):
    modules = ['tests.test_minimal_writer_wire']
    if mode == 'related':
        modules += ['tests.test_draft_selection_contract','tests.test_draft_explanation_contract',
                    'tests.test_draft_explanation_contract_v3','tests.test_draft_contract_v2',
                    'tests.test_draft_contract_v3_experiment','tests.test_draft_v3_real_output_repair',
                    'tests.test_seo_draft_v3_request_freeze','tests.test_content_draft_numeric_boundaries',
                    'tests.test_content_draft_core','tests.test_content_draft_workflow']
    suite = (unittest.defaultTestLoader.discover(str(ROOT/'tests'),pattern='test_*.py') if mode == 'full'
             else unittest.defaultTestLoader.loadTestsFromNames(modules))
    start = time.monotonic()
    with (HERE/(mode+'-tests.log')).open('w',encoding='utf-8') as log, redirect_stdout(log), redirect_stderr(log):
        result = unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    code = 0 if result.wasSuccessful() else 1
    summary = dict(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors),
        skipped=len(result.skipped), exit_code=code, seconds=round(time.monotonic()-start,3),
        failure_ids=[t.id() for t,_ in result.failures], error_ids=[t.id() for t,_ in result.errors],
        blocked_external_network_attempts=len(blocked),real_api_calls=0,
        command='unittest discover -s tests -p test_*.py -v' if mode == 'full' else 'unittest '+' '.join(modules)+' -v',
        network_guard='External socket connect/connect_ex/sendto/getaddrinfo denied; loopback permitted for unit tests.')
    write_json(HERE/(mode+'-tests.json'),summary)
    print(json.dumps(summary,ensure_ascii=False))
    return code


def artifacts():
    from foreign_trade_geo_agent.adapters.minimal_writer_wire import build_request_material
    from foreign_trade_geo_agent.core import minimal_writer_wire as mw
    from foreign_trade_geo_agent.core.draft_selection_contract import canonical_json
    from foreign_trade_geo_agent.workflows.minimal_writer_experiment import run_minimal_experiment,render_review
    from tests.minimal_writer_fixtures import cnc_fixture,industry_fixture
    summaries = {}
    for name, factory in [('cnc',cnc_fixture),('pump',lambda:industry_fixture('pump')),
                          ('packaging',lambda:industry_fixture('packaging'))]:
        value,selection,manifest,wire = factory()
        snapshot = selection.evidence_snapshot_sha256
        r = run_minimal_experiment(value,selection,manifest,wire,current_snapshot_sha256=snapshot)
        if not r.ready_for_review: raise ValueError(r.errors)
        directory = HERE/'synthetic'/name
        directory.mkdir(parents=True,exist_ok=True)
        for filename, data in [('native-input.json',asdict(value)),('selection.json',asdict(selection)),
                               ('manifest.json',asdict(manifest)),('result.json',asdict(r)),
                               ('request-material.json',build_request_material(value,selection,manifest,current_snapshot_sha256=snapshot))]:
            write_json(directory/filename,data)
        for filename,raw in [('wire.json',wire),('candidate.json',r.candidate_json),('bindings.json',r.bindings_json),
                             ('review.md',render_review(r))]:
            (directory/filename).write_text(raw,encoding='utf-8')
        bindings = mw.decode_bindings(r.bindings_json).bindings
        summaries[name] = dict(sections=len(selection.sections),claims=len(bindings),
            blocks=sum(len(s['blocks']) for s in json.loads(r.candidate_json)['draft']['sections']),
            direct=sum(b.kind=='direct_fact' for b in bindings),explanations=sum(b.kind=='explanation' for b in bindings),
            minimal_wire=r.minimal_wire,native_parser=r.native_parser,native_validator=r.native_validator,
            semantic_review=r.semantic_review,semantic_approved=False,production_authorized=False,
            candidate_hash=r.candidate_hash,sidecar_hash=r.sidecar_hash)
        if name == 'cnc':
            examples = {}
            for label in ('refusal','numeric-context','known-conflict','semantic-risk'):
                obj = json.loads(wire)
                a = obj['slots'][0]
                if label == 'refusal':
                    obj['slots'][0] = dict(slot_id=a['slot_id'],status='insufficient_evidence',missing_information='The intended fixture layout is unavailable.')
                elif label == 'numeric-context':
                    a.update(premise_refs=['E2.F03'],buyer_implication='The fixture runs at 400 kg under a dynamic load.')
                elif label == 'known-conflict':
                    a['buyer_implication'] = 'NCX10 fits the complete fixture and is suitable for machining.'
                else:
                    a['buyer_implication'] = 'The fixture note establishes compatibility for the intended production process.'
                bad = run_minimal_experiment(value,selection,manifest,canonical_json(obj),current_snapshot_sha256=snapshot)
                examples[label] = dict(wire=obj,result=asdict(bad))
            write_json(directory/'counterexamples.json',examples)
    write_json(HERE/'synthetic-results.json',summaries)
    print(json.dumps(summaries,ensure_ascii=False))
    return 0


def integrity():
    before = json.loads((HERE/'baseline.json').read_text(encoding='utf-8'))['files']
    changed, missing = [], []
    for filename,digest in before.items():
        path = ROOT/filename
        if not path.is_file(): missing.append(filename)
        elif hashlib.sha256(path.read_bytes()).hexdigest() != digest: changed.append(filename)
    result = dict(baseline_files=len(before),changed=changed,missing=missing,
                  unchanged=len(before)-len(changed)-len(missing),real_api_calls=0)
    write_json(HERE/'integrity.json',result)
    print(json.dumps(result,ensure_ascii=False))
    return int(bool(changed or missing))


if __name__ == '__main__':
    mode = sys.argv[1]
    with (patch.object(socket.socket,'connect',connect),patch.object(socket.socket,'connect_ex',connect_ex),
          patch.object(socket.socket,'sendto',sendto),patch.object(socket,'getaddrinfo',resolve)):
        code = tests(mode) if mode in {'new','related','full'} else artifacts() if mode == 'artifacts' else integrity()
    raise SystemExit(code)
