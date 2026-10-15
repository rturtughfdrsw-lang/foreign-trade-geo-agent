"""Offline only; authored cases do not prove real-model boundary compliance."""
from contextlib import ExitStack
from dataclasses import asdict
import difflib
import importlib.util
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
OUT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('phase7a6_prompt', OUT / 'prompt.py')
candidate = importlib.util.module_from_spec(spec)
sys.modules['phase7a6_prompt'] = candidate
spec.loader.exec_module(candidate)
e = candidate.previous
MODULES = ('test_composition_prompt', 'test_json_prompt_contract', 'test_prompt_boundary',
           'test_experiment', 'tests.test_evidence_bound_draft_admission_phase7a1',
           'tests.test_phase6_e2e', 'tests.test_editorial_review_v1')


def run():
    e.OUT = OUT
    # Preserve the original A.5/A.3 regression contract, including their exact
    # historical system-delta assertions. A.6 tests verify the additional delta.
    sys.modules['prompt'] = candidate.base
    sys.path.insert(0, str(OUT))
    sys.path.insert(1, str(candidate.A5))
    sys.path.insert(2, str(candidate.base.A3))
    before = e.load('baseline-before.json')
    if e.baseline() != before:
        raise ValueError('P7A6_EXISTING_FILE_DRIFT')
    old_manifest = e.phase2.strict((candidate.A5 / 'live-artifact-manifest.json').read_bytes())
    for name, digest in old_manifest['files'].items():
        if e.sha((candidate.A5 / name).read_bytes()) != digest:
            raise ValueError('P7A6_A5_ARTIFACT_DRIFT')
    log = io.StringIO()
    with e.OfflineGuard() as network, ExitStack() as stack:
        blocked = e.guards(stack)
        blocked.append(stack.enter_context(patch.object(e.httpx.HTTPTransport, 'handle_request',
            side_effect=AssertionError('P7A6_REAL_HTTP_FORBIDDEN'))))
        blocked.append(stack.enter_context(patch.object(e, 'read_key',
            side_effect=AssertionError('P7A6_CREDENTIAL_READ_FORBIDDEN'))))
        counts = {name:unittest.defaultTestLoader.loadTestsFromName(name).countTestCases()
                  for name in MODULES}
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromNames(MODULES))
        value, ready = e.load_admitted()
        if e.admission.require_ready(value, ready) != ready:
            raise ValueError('P7A6_READY_REVALIDATION')
    preserved = e.baseline() == before
    success = result.wasSuccessful() and preserved and network.attempts == 0 and all(
        blocked_call.call_count == 0 for blocked_call in blocked)
    summary = dict(tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors),
        skipped=len(result.skipped), modules=counts, network_attempts=network.attempts,
        forbidden_calls=sum(call.call_count for call in blocked), real_api_calls=0,
        production_writer_calls=0, wordpress_calls=0, deployment=False, git_commit=False,
        git_push=False, existing_files_unchanged=preserved, full_suite_run=False,
        credential_reads=0, outcome='OFFLINE_PASS' if success else 'OFFLINE_FAIL',
        regression_targets=dict(a6='New candidate and authored expectations',
            a5_a3='Original unmodified A.5/A.3 assertions against preserved A.5 prompt; A.6 retention checked separately'))
    e.save('offline-tests.log', log.getvalue().encode('utf-8'))
    e.save('offline-tests.json', summary)
    if success:
        cases = sys.modules['test_composition_prompt'].CASES
        e.save('offline-cases.json', dict(kind='AUTHORED_EXPECTATIONS_NOT_MODEL_OUTPUT',
            generated_by_llm=False, model_compliance_verified=False, cases=cases))
        messages = candidate.messages()
        original = e.phase2.strict((candidate.A5 / 'prompt.json').read_bytes())
        e.save('prompt.json', messages)
        e.save('prompt.diff', ''.join(difflib.unified_diff(
            original[0]['content'].splitlines(keepends=True), messages[0]['content'].splitlines(keepends=True),
            fromfile='Phase7A5/system', tofile='Phase7A6/system')).encode('utf-8'))
        e.save('request.json', dict(**e.PARAMETERS, messages=messages))
        e.save('admission-revalidation.json', dict(admission_status=ready.status.value,
            require_ready_recomputed=True, result=asdict(ready), semantic_approved=False,
            production_authorized=False, live_execution_authorized=False))
        e.save('live-request-proposal.json', dict(status='NOT_SENT_AWAITING_SEPARATE_USER_AUTHORIZATION',
            test_only=True, endpoint=e.ENDPOINT, parameters=e.PARAMETERS, maximum_http_requests=1,
            retries=0, fallback=False, repair=False, output_filtering=False,
            stop_at_first_failed_layer=True, layers=[1,2,3,4],
            prompt_sha256=e.sha((OUT/'prompt.json').read_bytes()),
            request_sha256=e.sha((OUT/'request.json').read_bytes()), semantic_approved=False,
            production_authorized=False, live_execution_authorized=False))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return success


if __name__ == '__main__':
    sys.exit(0 if run() else 1)
