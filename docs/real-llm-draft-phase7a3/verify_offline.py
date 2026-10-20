"""Offline test runner. No live request builder or sender is provided."""
from contextlib import ExitStack
import hashlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import prompt as candidate

e = candidate.previous
OUT = candidate.OUT
MODULES = ('test_prompt_boundary', 'test_experiment',
           'tests.test_evidence_bound_draft_admission_phase7a1',
           'tests.test_phase6_e2e', 'tests.test_editorial_review_v1')


def inventory():
    # Exclude only our new artifacts; preserve A.2 including its consumed attempt.
    result = e.baseline()
    result['current']['files'] = {k: v for k, v in result['current']['files'].items()
        if not k.startswith('docs/real-llm-draft-phase7a3/')}
    result['phase7a2'] = {p.relative_to(candidate.PREVIOUS).as_posix(): e.sha(p.read_bytes())
        for p in candidate.PREVIOUS.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    return result


def run(label):
    before = inventory()
    log = io.StringIO()
    with e.OfflineGuard() as network, ExitStack() as stack:
        blocked = e.guards(stack)
        blocked.append(stack.enter_context(patch.object(e.httpx.HTTPTransport, 'handle_request',
            side_effect=AssertionError('P7A3_REAL_HTTP_FORBIDDEN'))))
        blocked.append(stack.enter_context(patch.object(e, 'read_key',
            side_effect=AssertionError('P7A3_CREDENTIAL_READ_FORBIDDEN'))))
        counts = {name: unittest.defaultTestLoader.loadTestsFromName(name).countTestCases() for name in MODULES}
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromNames(MODULES))
    preserved = inventory() == before
    value = dict(tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors),
        skipped=len(result.skipped), modules=counts, network_attempts=network.attempts,
        forbidden_calls=sum(m.call_count for m in blocked), real_api_calls=0,
        production_writer_calls=0, wordpress_calls=0, deployment=False, git_commit=False,
        git_push=False, existing_files_unchanged=preserved, full_suite_run=False,
        inventory_sha256=hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest(),
        phase7a2_hashes=before['phase7a2'])
    (OUT / (label + '.log')).write_text(log.getvalue(), encoding='utf-8')
    (OUT / (label + '.json')).write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in value.items() if k != 'phase7a2_hashes'}, indent=2))
    return result.wasSuccessful() and preserved and network.attempts == 0 and value['forbidden_calls'] == 0


if __name__ == '__main__':
    sys.exit(0 if run(sys.argv[1] if len(sys.argv) > 1 else 'offline-final-tests') else 1)
