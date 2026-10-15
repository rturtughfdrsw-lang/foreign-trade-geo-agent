"""Run the offline tests and retain observed results. Never run live scripts."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

from build_mock import HERE, ROOT, encode, sha
from offline_mock import verify


def run(baseline_file=None):
    command = [sys.executable, '-m', 'unittest', 'discover', '-s', str(HERE),
               '-p', 'test_offline_mock.py', '-v']
    completed = subprocess.run(command, cwd=ROOT, capture_output=True)
    log = completed.stdout + completed.stderr
    (HERE / 'verification.log').write_bytes(log)
    print(log.decode('utf-8', errors='replace'))
    result = verify()
    count = re.search(rb'Ran (\d+) tests', log)
    result['tests'] = dict(command=command, exit_code=completed.returncode,
        count=int(count[1]) if count else None, status='PASS' if completed.returncode == 0 else 'FAIL',
        full_suite='NOT_RUN_DESIGN_ONLY', log='verification.log')
    if baseline_file:
        baseline = json.loads(Path(baseline_file).read_bytes())
        changed = [name for name, expected in baseline.items()
                   if not (ROOT / name).is_file() or sha((ROOT / name).read_bytes()) != expected]
        current = subprocess.check_output(['git', 'ls-files', '-c', '-o', '--exclude-standard', '-z'], cwd=ROOT)
        added = sorted(set(current.decode().split('\0')) - set(baseline) - {''})
        unexpected = [p for p in added if not p.startswith('docs/seo-draft-contract-v2-design/')]
        result['workspace_preservation'] = dict(existing_files_checked=len(baseline),
            changed_existing_files=changed, unexpected_added_files=unexpected,
            added_files=added, status='PASS' if not changed and not unexpected else 'FAIL')
    result['artifact_sha256'] = {p.name: sha(p.read_bytes()) for p in sorted(HERE.iterdir())
        if p.is_file() and p.name not in ('verification.json', 'verification.log')}
    (HERE / 'verification.json').write_bytes(encode(result))
    if completed.returncode or result.get('workspace_preservation', {}).get('status') == 'FAIL':
        raise SystemExit(1)
    print(json.dumps(dict(tests=result['tests']['count'], mock=result['new_mock']['design_status'],
        claims=result['new_mock']['claims'], blocks=result['new_mock']['blocks'],
        routing=result['section_routing'], explanations=result['explanation_contract_structure'],
        old=result['historical_frozen_v1']['state'], network_attempts=result['network_attempts']), indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline-file', help='Optional local hash snapshot captured before this design task.')
    run(parser.parse_args().baseline_file)
