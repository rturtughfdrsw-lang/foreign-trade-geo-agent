"""Isolated offline verification logs; never writes historical verification files."""
from contextlib import redirect_stdout, redirect_stderr
import hashlib
import ipaddress
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
HERE = ROOT/'docs/minimal-writer-flash-preflight-verification'
HERE.mkdir(parents=True, exist_ok=True)
blocked = []
original_connect, original_connect_ex = socket.socket.connect, socket.socket.connect_ex
original_resolve, original_sendto = socket.getaddrinfo, socket.socket.sendto


def save(name, value):
    (HERE/name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def check(host):
    if host in {'localhost', 'localhost.'}:
        return
    try:
        if ipaddress.ip_address(host).is_loopback:
            return
    except ValueError:
        pass
    blocked.append('external_network_blocked')
    raise OSError('OFFLINE_EXTERNAL_NETWORK_BLOCKED')


def connect(sock, address):
    if isinstance(address, tuple): check(address[0])
    return original_connect(sock, address)


def connect_ex(sock, address):
    if isinstance(address, tuple): check(address[0])
    return original_connect_ex(sock, address)


def resolve(host, *args, **kwargs):
    if host is not None: check(host)
    return original_resolve(host, *args, **kwargs)


def sendto(sock, data, *args):
    if args and isinstance(args[-1], tuple): check(args[-1][0])
    return original_sendto(sock, data, *args)


def baseline():
    names = subprocess.check_output(['git','ls-files','-z','--cached','--others','--exclude-standard'], cwd=ROOT)
    files = {}
    for raw in names.split(b'\0'):
        if not raw: continue
        name = raw.decode('utf-8')
        path = ROOT/name
        if path.is_file() and not name.startswith('docs/minimal-writer-flash-preflight'):
            files[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    require_new = HERE/'baseline.json'
    if require_new.exists(): raise ValueError('BASELINE_ALREADY_EXISTS')
    save('baseline.json', dict(files=files, real_api_calls=0))
    print(json.dumps(dict(baseline_files=len(files))))
    return 0


def integrity():
    files = json.loads((HERE/'baseline.json').read_text(encoding='utf-8'))['files']
    changed, missing = [], []
    for name, digest in files.items():
        path = ROOT/name
        if not path.is_file(): missing.append(name)
        elif hashlib.sha256(path.read_bytes()).hexdigest() != digest: changed.append(name)
    # The two new tools were created immediately before taking the baseline.
    permitted = ['tests/test_seo_draft_v3_request_freeze.py',
                 'scripts/prepare_minimal_writer_flash_preflight.py',
                 'scripts/verify_minimal_writer_flash_offline.py']
    result = dict(baseline_files=len(files), unchanged=len(files)-len(changed)-len(missing),
        changed=changed, missing=missing, permitted_changes=permitted,
        unexpected_changes=sorted(set(changed)-set(permitted)), real_api_calls=0)
    save('integrity.json', result)
    print(json.dumps(result))
    return int(bool(result['unexpected_changes'] or missing))


def tests(mode):
    modules = ['tests.test_minimal_writer_flash_preflight']
    if mode in {'related', 'historical-fix'}:
        modules = (['tests.test_seo_draft_v3_request_freeze'] if mode == 'historical-fix' else modules + [
            'tests.test_minimal_writer_wire', 'tests.test_draft_selection_contract',
            'tests.test_draft_explanation_contract','tests.test_draft_explanation_contract_v3',
            'tests.test_draft_contract_v2','tests.test_draft_contract_v3_experiment',
            'tests.test_draft_v3_real_output_repair','tests.test_seo_draft_v3_request_freeze',
            'tests.test_content_draft_numeric_boundaries','tests.test_content_draft_core',
            'tests.test_content_draft_workflow'])
    suite = (unittest.defaultTestLoader.discover(str(ROOT/'tests'), pattern='test_*.py') if mode == 'full'
             else unittest.defaultTestLoader.loadTestsFromNames(modules))
    start = time.monotonic()
    with (HERE/(mode+'-tests.log')).open('w', encoding='utf-8') as log, redirect_stdout(log), redirect_stderr(log):
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    code = 0 if result.wasSuccessful() else 1
    summary = dict(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors),
        skipped=len(result.skipped), expected_failures=len(result.expectedFailures),
        unexpected_successes=len(result.unexpectedSuccesses), exit_code=code,
        seconds=round(time.monotonic()-start,3), failure_ids=[t.id() for t,_ in result.failures],
        error_ids=[t.id() for t,_ in result.errors], blocked_external_network_attempts=len(blocked),
        real_api_calls=0, modules=modules if mode != 'full' else None,
        command='unittest discover -s tests -p test_*.py -v' if mode == 'full' else 'unittest '+' '.join(modules)+' -v',
        network_guard='External socket connect/connect_ex/sendto/getaddrinfo denied; loopback permitted for local fixtures.')
    save(mode+'-tests.json', summary)
    print(json.dumps(summary))
    return code


if __name__ == '__main__':
    mode = sys.argv[1]
    with (patch.object(socket.socket,'connect',connect), patch.object(socket.socket,'connect_ex',connect_ex),
          patch.object(socket.socket,'sendto',sendto), patch.object(socket,'getaddrinfo',resolve)):
        code = baseline() if mode == 'baseline' else integrity() if mode == 'integrity' else tests(mode)
    raise SystemExit(code)
