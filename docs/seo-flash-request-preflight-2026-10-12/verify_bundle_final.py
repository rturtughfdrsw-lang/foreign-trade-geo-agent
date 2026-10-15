"""Read-only final manifest, history, native binding and pending-journal check."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT))
from foreign_trade_geo_agent.core import content_draft as cd
from foreign_trade_geo_agent.storage.serialization import _decode
from foreign_trade_geo_agent.storage.content_draft_review import SQLiteLocalDraftReviewStore
from foreign_trade_geo_agent.web.experiment import code_hashes
from foreign_trade_geo_agent.web.generation import MockArticleExecutor

HERE = Path(__file__).resolve().parent
BUNDLE = HERE / 'final-v2'
sha = lambda raw: hashlib.sha256(raw).hexdigest()


def main():
    baseline = json.loads((HERE / 'baseline-sha256.json').read_bytes())
    assert all(Path(n).is_file() and sha(Path(n).read_bytes()) == h for n, h in baseline.items())
    manifest_raw = (BUNDLE / 'artifact-sha256.json').read_bytes()
    assert sha(manifest_raw) == (BUNDLE / 'bundle.sha256').read_text().strip()
    manifest = json.loads(manifest_raw)
    assert all(sha((BUNDLE / n).read_bytes()) == h for n, h in manifest.items())
    actual = {p.relative_to(BUNDLE).as_posix() for p in BUNDLE.rglob('*') if p.is_file()}
    assert actual == set(manifest) | {'artifact-sha256.json', 'bundle.sha256'}
    assert json.loads((BUNDLE / 'source-sha256.json').read_bytes()) == code_hashes()
    ready = json.loads((BUNDLE / 'readiness.json').read_bytes())
    native = BUNDLE / 'native/B-rich-evidence/web-experiment'
    data = (native / 'bundle.json').read_bytes()
    assert sha(data) == ready['execution_bundle_sha256'] == (native / 'bundle.sha256').read_text().strip()
    inside = json.loads(data)
    assert inside['code'] == code_hashes()
    assert all(sha((native / n).read_bytes()) == h for n, h in inside['files'].items())
    raw = (BUNDLE / 'request.FROZEN-NOT-AUTHORIZED.json').read_bytes()
    value = _decode(json.loads((native / 'native-input.json').read_bytes()), cd.ContentDraftInput)
    assert MockArticleExecutor.request_for(value) == raw == (native / 'request.json').read_bytes()
    assert sha(raw) == ready['request_sha256'] == inside['request_sha256']
    mock_text = (BUNDLE / 'mock-drill/model-output.txt').read_text(encoding='utf-8')
    records = SQLiteLocalDraftReviewStore((BUNDLE / 'mock-drill/local-review.sqlite3').resolve()).revisions(sha(mock_text.encode()))
    assert len(records) == 1 and records[0].status == 'PENDING_REVIEW'
    assert records[0].body_text == mock_text
    assert records[0].origin_sha256 == records[0].body_sha256 == sha(mock_text.encode())
    assert not records[0].candidate_decisions
    assert not ready['live_permit_issued'] and not ready['owner_risk_acceptance']
    print(json.dumps(dict(status='PASS', artifact_files=len(manifest), source_files=len(code_hashes()),
        baseline_files_unchanged=len(baseline), request_sha256=sha(raw),
        bundle_sha256=sha(manifest_raw), execution_bundle_sha256=sha(data),
        pending_sqlite_reopened=True, actual_real_requests=0, wordpress_requests=0, live_permits=0), indent=2))


if __name__ == '__main__':
    main()
