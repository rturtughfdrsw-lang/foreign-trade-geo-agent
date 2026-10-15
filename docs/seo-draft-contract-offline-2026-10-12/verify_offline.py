"""Read-only independent verification of this offline delivery; no transport."""
import hashlib
import json
from pathlib import Path

from foreign_trade_geo_agent.adapters.deepseek_content_draft import DeepSeekContentDraftWriter
from foreign_trade_geo_agent.core import content_draft as cd
from foreign_trade_geo_agent.storage.serialization import _decode
from foreign_trade_geo_agent.web.experiment import code_hashes
from foreign_trade_geo_agent.web.generation import MockArticleExecutor
from foreign_trade_geo_agent.workflows.content_draft import _parse_specification, inspect_candidate_output


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
FROZEN = OUT / 'frozen-v1'
HISTORY = ROOT / 'docs/seo-flash-quality-live-2026-10-12'


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    baseline = read(OUT / 'session-baseline-sha256.json')
    changed = [name for name, digest in baseline.items() if sha(ROOT / name) != digest]
    assert set(changed) == {'scripts/accept_draft_prompt_contract.py',
                            'tests/test_draft_prompt_contract_acceptance.py'}, changed
    manifest = read(FROZEN / 'artifact-sha256.json')
    assert all(sha(FROZEN / name) == digest for name, digest in manifest.items())
    assert sha(FROZEN / 'artifact-sha256.json') == (FROZEN / 'bundle.sha256').read_text().strip()
    ready = read(FROZEN / 'readiness.json')
    assert ready['code_sha256'] == code_hashes()
    rich = FROZEN / 'native/B-rich-evidence'
    value = _decode(read(rich / 'frozen-native-input.json'), cd.ContentDraftInput)
    original = _decode(read(HISTORY / 'native-input.json'), cd.ContentDraftInput)
    reviewed = _decode(read(rich / 'native-reviewed-input.json'), cd.ContentDraftInput)
    assert value.change_plan_report == original.change_plan_report
    assert value.customer_evidence.sources == original.customer_evidence.sources
    assert not value.customer_evidence.interpretations
    assert not value.writing_brief == original.writing_brief  # New isolated snapshot binding.
    from dataclasses import replace
    assert replace(value.writing_brief, snapshot_sha256=original.writing_brief.snapshot_sha256) == original.writing_brief
    raw_request = (FROZEN / 'request.FROZEN-NOT-AUTHORIZED.json').read_bytes()
    assert raw_request == MockArticleExecutor.request_for(value)
    request = json.loads(raw_request)
    assert request['messages'][0]['content'] == (FROZEN / 'system-prompt.txt').read_text(encoding='utf-8')
    assert request['messages'][1]['content'] == (FROZEN / 'user-material.json').read_text(encoding='utf-8')
    historical_request = read(HISTORY / 'request.json')
    assert DeepSeekContentDraftWriter.build_system_prompt() == historical_request['messages'][0]['content'].split('\nE CANDIDATE RULE')[0]
    raw = (rich / 'mock-response.json').read_text(encoding='utf-8')
    operation = value.change_plan_report.operations[0]
    spec = _parse_specification(raw, expected_change_ref='C1', operation=operation)
    candidate = inspect_candidate_output(value, raw, current_snapshot_sha256=value.customer_evidence.snapshot_sha256)
    assert candidate.state == 'PENDING_SEMANTIC_REVIEW' and not candidate.errors
    assert all(c.evidence_details for c in candidate.claims if c.refs)
    opportunity = value.opportunity_report.opportunities[0]
    draft, error = cd.finalize_draft_item(1, spec, operation, opportunity,
        value.site_content, value.opportunity_report, customer_evidence=value.customer_evidence)
    assert draft is None and error == 'INTERPRETATION_PENDING_REVIEW'
    draft, approved_error = cd.finalize_draft_item(1, spec, operation, opportunity,
        value.site_content, value.opportunity_report, customer_evidence=reviewed.customer_evidence)
    assert draft is not None and approved_error is None
    old_raw = (HISTORY / 'model-output.txt').read_text(encoding='utf-8')
    old_spec = _parse_specification(old_raw, expected_change_ref='C1', operation=operation)
    old_claims = [c for s in old_spec.sections for b in s.blocks
                  for c in getattr(b, 'claims', getattr(b, 'items', ()))]
    assert len(old_claims) == 48 and all(not c.customer_refs and not c.proposal for c in old_claims)
    old_check = inspect_candidate_output(value, old_raw, current_snapshot_sha256=value.customer_evidence.snapshot_sha256)
    assert old_check.state == 'DETERMINISTICALLY_REJECTED'
    assert 'CUSTOMER_EVIDENCE_COVERAGE' in old_check.errors
    low = read(FROZEN / 'native/A-low-evidence/scope-and-evidence-review.json')
    assert low['status'] == 'BLOCKED' and ready['low_writer_calls'] == 0
    result = dict(baseline_files=len(baseline), changed_existing_files=changed,
        historical_docs_unchanged=True, production_source_files_unchanged=True,
        frozen_artifacts_verified=len(manifest), frozen_code_files_verified=len(ready['code_sha256']),
        request_reconstructed_byte_for_byte=True, request_sha256=sha(FROZEN / 'request.FROZEN-NOT-AUTHORIZED.json'),
        bundle_sha256=sha(FROZEN / 'artifact-sha256.json'),
        original_response_sha256=sha(HISTORY / 'response-body.bin'),
        original_model_text_sha256=sha(HISTORY / 'model-output.txt'),
        historical_parser='PASS', historical_validator=old_check.state,
        historical_missing_customer_refs=48, historical_repairs=0,
        plan_and_sources_identical=True, writing_brief_only_snapshot_binding_differs=True,
        candidate_state=candidate.state, unreviewed_finalizer_error=error,
        test_reviewed_finalizer='PASS', low_gaps=[dict(id=g['requirement']['requirement_id'],
            missing=g['requirement']['required_fact'], reason=g['reason_code']) for g in low['gaps']],
        real_model_requests=0, wordpress_requests=0, permit_issued=False)
    (OUT / 'independent-verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
