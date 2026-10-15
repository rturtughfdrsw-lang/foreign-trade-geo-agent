"""Guarded offline checks; writes only inside this new experiment directory."""
from contextlib import ExitStack
import io
import unittest
from unittest.mock import patch
import experiment as e

before = e.baseline()
modules = ('test_experiment', 'tests.test_evidence_bound_draft_admission_phase7a1',
           'tests.test_phase6_e2e', 'tests.test_editorial_review_v1')
log = io.StringIO()
with e.OfflineGuard() as network, ExitStack() as stack:
    blocked = e.guards(stack)
    stack.enter_context(patch.object(e.httpx.HTTPTransport, 'handle_request',
        side_effect=AssertionError('P7A2_REAL_HTTP_FORBIDDEN')))
    counts = {name: unittest.defaultTestLoader.loadTestsFromName(name).countTestCases() for name in modules}
    result = unittest.TextTestRunner(stream=log, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromNames(modules))
    e.check(network.attempts == 0 and all(m.call_count == 0 for m in blocked), 'P7A2_OFFLINE_SIDE_EFFECT')
e.check(e.baseline() == before, 'P7A2_OFFLINE_BASELINE_DRIFT')
e.save('offline-final-tests.log', log.getvalue().encode('utf-8'))
e.save('offline-final-tests.json', dict(tests_run=result.testsRun, failures=len(result.failures),
    errors=len(result.errors), skipped=len(result.skipped), modules=counts,
    real_api_calls=0, network_attempts=network.attempts, full_suite_run=False,
    baseline_unchanged=True))
print(log.getvalue())
e.check(result.wasSuccessful(), 'P7A2_OFFLINE_TEST_FAILURE')
