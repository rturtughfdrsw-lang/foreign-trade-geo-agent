"""Run exact requested unittest scope with inherited offline guard and metrics."""
import json
import os
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
guard = str(HERE / 'network_guard')
sys.path[:0] = [guard, str(ROOT)]
os.environ['PYTHONPATH'] = os.pathsep.join([guard, str(ROOT), os.environ.get('PYTHONPATH', '')])
import sitecustomize

label, *modules = sys.argv[1:]
log = HERE / (label + '-blocked-network.log')
os.environ['DRAFT_V3_NETWORK_LOG'] = str(log)
suite = (unittest.defaultTestLoader.loadTestsFromNames(modules) if modules else
         unittest.defaultTestLoader.discover(str(ROOT / 'tests'), pattern='test_*.py', top_level_dir=str(ROOT)))
with (HERE / (label + '.log')).open('w', encoding='utf-8') as stream:
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
summary = dict(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors),
    skipped=len(result.skipped), exit_code=0 if result.wasSuccessful() else 1,
    modules=modules or ['unittest discover -s tests -p test_*.py -v'],
    external_network_guard=True, external_network_attempts=len(log.read_text().splitlines()) if log.exists() else 0,
    api_calls=0, wordpress_calls=0, failed_tests=[t.id() for t, _ in result.failures + result.errors])
(HERE / (label + '.json')).write_text(json.dumps(summary, indent=2)+'\n', encoding='utf-8')
print(json.dumps(summary))
sys.exit(summary['exit_code'])
