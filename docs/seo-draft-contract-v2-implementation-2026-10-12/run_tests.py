"""Run unittest under an external-network guard, recording actual outcomes."""
import json
import os
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
GUARD = HERE / 'network_guard'
sys.path[:0] = [str(GUARD), str(ROOT)]
os.environ['PYTHONPATH'] = os.pathsep.join([str(GUARD), str(ROOT), os.environ.get('PYTHONPATH', '')])
label, *modules = sys.argv[1:]
network_log = HERE / (label + '-blocked-network.log')
os.environ['DRAFT_V2_NETWORK_LOG'] = str(network_log)
import sitecustomize  # noqa: E402

loader = unittest.TestLoader()
suite = (loader.loadTestsFromNames(modules) if modules else
         loader.discover(str(ROOT / 'tests'), pattern='test_*.py', top_level_dir=str(ROOT)))
with (HERE / (label + '.log')).open('w', encoding='utf-8') as stream:
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
summary = dict(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors),
    skipped=len(result.skipped), exit_code=0 if result.wasSuccessful() else 1,
    external_network_blocked=True,
    blocked_network_attempts=len(network_log.read_text().splitlines()) if network_log.exists() else 0,
    real_api_calls=0, real_wordpress_calls=0,
    modules=modules or ['unittest discover -s tests -p test_*.py -v'],
    failed_tests=[test.id() for test, _ in result.failures + result.errors])
(HERE / (label + '.json')).write_text(json.dumps(summary, indent=2), encoding='utf-8')
print(json.dumps(summary, indent=2))
sys.exit(summary['exit_code'])
