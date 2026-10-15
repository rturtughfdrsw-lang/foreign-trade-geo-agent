"""Guarded offline verification only. No credential reads or model calls."""
from contextlib import ExitStack
from dataclasses import asdict
import difflib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
import prompt as candidate

e = candidate.previous
OUT = candidate.OUT
MODULES = ('test_json_prompt_contract', 'test_prompt_boundary', 'test_experiment',
           'tests.test_evidence_bound_draft_admission_phase7a1',
           'tests.test_phase6_e2e', 'tests.test_editorial_review_v1')


def run():
    e.OUT = OUT  # New artifacts only; all historical paths remain unchanged.
    sys.path.insert(0, str(OUT))
    sys.path.insert(1, str(candidate.A3))
    before = e.load('baseline-before.json')
    if e.baseline() != before:
        raise ValueError('P7A5_EXISTING_FILE_DRIFT')
    for directory in (candidate.A3, OUT.parent / 'real-llm-draft-phase7a4'):
        verification = e.phase2.strict((directory / 'verification.json').read_bytes())
        manifest = (e.phase2.strict((directory / 'artifact-manifest.json').read_bytes())['files']
                    if directory.name.endswith('a4') else verification['artifact_sha256'])
        for name, expected in manifest.items():
            if e.sha((directory / name).read_bytes()) != expected:
                raise ValueError('P7A5_HISTORICAL_ARTIFACT_DRIFT')
    log = io.StringIO()
    with e.OfflineGuard() as network, ExitStack() as stack:
        blocked = e.guards(stack)
        blocked.append(stack.enter_context(patch.object(e.httpx.HTTPTransport, 'handle_request',
            side_effect=AssertionError('P7A5_REAL_HTTP_FORBIDDEN'))))
        blocked.append(stack.enter_context(patch.object(e, 'read_key',
            side_effect=AssertionError('P7A5_CREDENTIAL_READ_FORBIDDEN'))))
        counts = {name: unittest.defaultTestLoader.loadTestsFromName(name).countTestCases()
                  for name in MODULES}
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromNames(MODULES))
        value, ready = e.load_admitted()
        if e.admission.require_ready(value, ready) != ready:
            raise ValueError('P7A5_READY_REVALIDATION')
    preserved = e.baseline() == before
    success = result.wasSuccessful() and preserved and network.attempts == 0 and all(
        mocked.call_count == 0 for mocked in blocked)
    summary = dict(tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors),
        skipped=len(result.skipped), modules=counts, network_attempts=network.attempts,
        forbidden_calls=sum(mocked.call_count for mocked in blocked), real_api_calls=0,
        production_writer_calls=0, wordpress_calls=0, deployment=False, git_commit=False,
        git_push=False, existing_files_unchanged=preserved, full_suite_run=False,
        a3_regression_candidate='Phase7A5 candidate; original A.3 test assertions unchanged',
        credential_reads=0, outcome='OFFLINE_PASS' if success else 'OFFLINE_FAIL')
    e.save('offline-tests.log', log.getvalue().encode('utf-8'))
    e.save('offline-tests.json', summary)
    if success:
        messages = candidate.messages()
        original = e.phase2.strict((candidate.A3 / 'prompt.json').read_bytes())
        e.save('prompt.json', messages)
        e.save('prompt.diff', ''.join(difflib.unified_diff(
            original[0]['content'].splitlines(keepends=True),
            messages[0]['content'].splitlines(keepends=True),
            fromfile='Phase7A3/system', tofile='Phase7A5/system')).encode('utf-8'))
        e.save('request.json', dict(**e.PARAMETERS, messages=messages))
        e.save('admission-revalidation.json', dict(admission_status=ready.status.value,
            require_ready_recomputed=True, result=asdict(ready), semantic_approved=False,
            production_authorized=False, live_execution_authorized=False))
        e.save('live-request-proposal.json', dict(status='NOT_SENT_AWAITING_SEPARATE_USER_AUTHORIZATION',
            test_only=True, endpoint=e.ENDPOINT, parameters=e.PARAMETERS, maximum_http_requests=1,
            retries=0, fallback=False, repair=False, parser_unchanged=True,
            stop_on_layer1_failure=True, continue_layers_2_to_4_only_after_layer1_pass=True,
            prompt_sha256=e.sha((OUT / 'prompt.json').read_bytes()),
            request_sha256=e.sha((OUT / 'request.json').read_bytes()),
            semantic_approved=False, production_authorized=False, live_execution_authorized=False))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return success


if __name__ == '__main__':
    sys.exit(0 if run() else 1)
