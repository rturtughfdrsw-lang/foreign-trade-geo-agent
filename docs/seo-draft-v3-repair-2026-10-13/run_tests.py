"""Offline regression runner, external sockets blocked in this process/children."""
import json
import os
from pathlib import Path
import sys
import time
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
GUARD = ROOT / 'docs/seo-draft-contract-v3-design/network_guard'
sys.path[:0] = [str(GUARD), str(ROOT)]
os.environ['PYTHONPATH'] = os.pathsep.join([str(GUARD), str(ROOT), os.environ.get('PYTHONPATH', '')])
label, *modules = sys.argv[1:]
assert label.isalnum()
os.environ['DRAFT_V3_NETWORK_LOG'] = str(HERE / (label + '-network.log'))
import sitecustomize

suite = unittest.TestLoader().loadTestsFromNames(modules) if modules else unittest.TestLoader().discover(
    str(ROOT / 'tests'), pattern='test_*.py', top_level_dir=str(ROOT))
start = time.monotonic()
with (HERE / (label + '.log')).open('w', encoding='utf-8') as stream:
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
summary = dict(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors),
    skipped=len(result.skipped), failed_tests=[t.id() for t, _ in result.failures + result.errors],
    elapsed_seconds=round(time.monotonic() - start, 3), external_network_blocked=True,
    modules=modules or ['unittest discover -s tests -p test_*.py -v'], exit_code=int(not result.wasSuccessful()))
(HERE / (label + '.json')).write_text(json.dumps(summary, indent=2), encoding='utf-8')
print(json.dumps(summary, indent=2))
sys.exit(summary['exit_code'])
