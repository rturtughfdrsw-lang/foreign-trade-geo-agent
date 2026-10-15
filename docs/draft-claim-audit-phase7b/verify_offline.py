"""Offline verification; never invokes historical live execution entries."""
from contextlib import ExitStack
from dataclasses import asdict
import importlib.util
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
OUT = Path(__file__).resolve().parent
A6 = OUT.parent / 'real-llm-draft-phase7a6'
spec = importlib.util.spec_from_file_location('phase7a6_prompt', A6 / 'prompt.py')
candidate = importlib.util.module_from_spec(spec)
sys.modules['phase7a6_prompt'] = candidate
spec.loader.exec_module(candidate)
e = candidate.previous
sys.modules['prompt'] = candidate.base
for directory in reversed((OUT, A6, candidate.A5, candidate.base.A3)):
    sys.path.insert(0, str(directory))
from claim_audit import Claim, Scope, Status, audit

MODULES = ('test_claim_audit', 'test_composition_prompt', 'test_json_prompt_contract',
    'test_prompt_boundary', 'test_experiment', 'tests.test_evidence_bound_draft_admission_phase7a1',
    'tests.test_phase6_e2e', 'tests.test_editorial_review_v1')


def run():
    e.OUT = OUT
    before = e.load('baseline-before.json')
    assert e.baseline() == before
    for name, digest in e.phase2.strict((A6/'live-artifact-manifest.json').read_bytes())['files'].items():
        assert e.sha((A6/name).read_bytes()) == digest
    log = io.StringIO()
    replays = {}
    with e.OfflineGuard() as network, ExitStack() as stack:
        blocked = e.guards(stack)
        blocked.append(stack.enter_context(patch.object(e.httpx.HTTPTransport, 'handle_request', side_effect=AssertionError('P7B_NO_HTTP'))))
        blocked.append(stack.enter_context(patch.object(e, 'read_key', side_effect=AssertionError('P7B_NO_CREDENTIALS'))))
        counts = {m:unittest.defaultTestLoader.loadTestsFromName(m).countTestCases() for m in MODULES}
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromNames(MODULES))
        value, ready = e.load_admitted()
        assert e.admission.require_ready(value, ready) == ready
        claims = tuple(Claim(c.claim_id,c.claim_text,Scope(c.applicable_scope.category,c.applicable_scope.subject),c.evidence_refs) for c in value.required_claims)
        scopes = tuple(Scope(s.category,s.subject) for s in value.allowed_scope)
        for phase in ('phase7a5','phase7a6'):
            path = OUT.parent/('real-llm-draft-'+phase)/'article.md'
            raw = path.read_bytes()
            replay = audit(claims,scopes,raw.decode('utf-8'))
            assert replay.status is Status.REJECTED
            expected = 'two synthetic configurations' if phase == 'phase7a5' else 'two configurations'
            assert any(f.code == 'UNSUPPORTED_CLAIM' and f.signal == expected for f in replay.findings)
            assert path.read_bytes() == raw
            replays[phase] = dict(source=str(path), result=asdict(replay), unchanged=True)
    preserved = e.baseline() == before
    success = result.wasSuccessful() and preserved and network.attempts == 0 and all(x.call_count == 0 for x in blocked)
    summary = dict(tests_run=result.testsRun, failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped), modules=counts,
        historical_replays_passed=True, require_ready_recomputed=True, network_attempts=network.attempts,
        forbidden_calls=sum(x.call_count for x in blocked), real_api_calls=0,production_writer_calls=0,wordpress_calls=0,
        deployment=False,git_commit=False,git_push=False,existing_files_unchanged=preserved,full_suite_run=False,
        outcome='OFFLINE_PASS' if success else 'OFFLINE_FAIL')
    e.save('offline-tests.log',log.getvalue().encode())
    e.save('offline-tests.json',summary)
    e.save('historical-replay.json',replays)
    print(json.dumps(summary,indent=2))
    return success


if __name__ == '__main__':
    sys.exit(0 if run() else 1)
