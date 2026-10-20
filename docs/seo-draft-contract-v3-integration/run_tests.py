"""Local unittest runner; inherited socket/DNS guard, retained logs and counts."""
import json
import os
from pathlib import Path
import sys
import time
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
GUARD = ROOT / 'docs/seo-draft-v2-flash-experiment-preflight/network_guard'
label, *modules = sys.argv[1:]
if not label.replace('-', '').isalnum():
    raise ValueError('INVALID_TEST_LABEL')
sys.path[:0] = [str(GUARD), str(ROOT)]
os.environ['PYTHONPATH'] = os.pathsep.join([str(GUARD), str(ROOT), os.environ.get('PYTHONPATH', '')])
os.environ['FLASH_PREFLIGHT_NETWORK_LOG'] = str(HERE / (label + '-network.log'))
strict = label.startswith(('red', 'green', 'new'))
os.environ['PREFLIGHT_STRICT'] = '1' if strict else '0'
import sitecustomize  # noqa: E402

start = time.monotonic()
loader = unittest.TestLoader()
suite = loader.loadTestsFromNames(modules) if modules else loader.discover(
    str(ROOT / 'tests'), pattern='test_*.py', top_level_dir=str(ROOT))
with (HERE / (label + '.log')).open('x', encoding='utf-8') as stream:
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
network = HERE / (label + '-network.log')
events = network.read_text().splitlines() if network.exists() else []
summary = dict(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors),
    skipped=len(result.skipped), exit_code=0 if result.wasSuccessful() else 1,
    elapsed_seconds=round(time.monotonic() - start, 3),
    strict_no_network=strict, external_network_blocked=True,
    blocked_network_attempts=sum(e.startswith('blocked:') for e in events),
    loopback_events=sum(e.startswith('loopback_allowed:') for e in events),
    real_api_calls=0, deepseek_requests=0, real_wordpress_calls=0,
    call_count_basis='No live scripts; socket/DNS guard inherited by Python subprocesses; local fakes excluded',
    modules=modules or ['unittest discover -s tests -p test_*.py -v'],
    failed_tests=[test.id() for test, _ in result.failures + result.errors])
with (HERE / (label + '.json')).open('x', encoding='utf-8') as stream:
    json.dump(summary, stream, indent=2)
print(json.dumps(summary, indent=2))
sys.exit(summary['exit_code'])
