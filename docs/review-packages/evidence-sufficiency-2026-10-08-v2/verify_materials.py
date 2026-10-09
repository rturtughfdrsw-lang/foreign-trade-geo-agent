"""Review package integrity only; standard library, no network or approvals."""
from pathlib import Path
import hashlib
import json
import re
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.stdout.reconfigure(encoding='utf-8')

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')

def read(name):
    return json.loads((HERE / name).read_text(encoding='utf-8'))

def check_span(text, span):
    assert type(span['start']) is int and type(span['end']) is int
    assert 0 <= span['start'] < span['end'] <= len(text)
    assert text[span['start']:span['end']] == span['quote']
    assert sha(text.encode('utf-8')) == span['field_sha256']
    assert sha(span['quote'].encode('utf-8')) == span['quote_sha256']

def verify():
    binding, manifest, review = read('binding.json'), read('manifest.json'), read('review-record.template.json')
    digest = sha(canonical(binding))
    assert manifest['binding_canonical_sha256'] == review['binding_canonical_sha256'] == digest
    for name, expected in binding['bound_files_sha256'].items():
        assert sha((HERE / name).read_bytes()) == expected, name
    for name, expected in binding['snapshot_files_sha256'].items():
        assert sha((HERE / name).read_bytes()) == expected, name
    assert set(binding['snapshot_files_sha256']) == {p.relative_to(HERE).as_posix() for p in (HERE / 'snapshots').iterdir()}
    for name, expected in manifest['package_files_sha256'].items():
        path = ROOT / name
        assert sha(path.read_bytes()) == expected, name
    actual_package = {p.relative_to(ROOT).as_posix() for p in HERE.rglob('*') if p.is_file() and p.name not in {'manifest.json', 'verification.json'}}
    entry = 'docs/evidence-sufficiency-owner-review-package-2026-10-08.md'
    assert set(manifest['package_files_sha256']) == actual_package | {entry}
    assert digest in (ROOT / entry).read_text(encoding='utf-8')
    provenance = read('source-provenance.json')
    for kind, identity in provenance['original_artifacts'].items():
        raw = (HERE / 'snapshots' / (kind + '.json')).read_bytes()
        assert sha(raw) == identity['payload_json_utf8_sha256']
        assert sha(canonical(json.loads(raw))) == identity['canonical_payload_sha256']
        assert identity['payload_version'] == 1
    assert provenance['historical_deployment_commit'] is None
    assert provenance['engineering_author_or_qualification'] is None
    coverage, task, candidate = read('coverage.json'), read('task.json'), read('planning-candidate.json')
    ids = [o['obligation_id'] for o in coverage['obligations']]
    assert ids == task['required_obligation_ids'] == ['O1', 'O2', 'O3', 'O4', 'O5', 'O6']
    assert candidate['point_obligation_map'] == {'operations[0].content_points[0]': ids}
    packet = read('snapshots/site_content.json')
    field = packet['pages'][2]['structured_content'][0]['text']
    assert packet['pages'][2]['evidence_id'] == 'P3'
    assert packet['pages'][2]['content_truncated'] is True
    assert packet['pages'][2]['structured_content_truncated'] is False
    source = (HERE / 'snapshots/solutions.astro').read_bytes().decode('utf-8')
    for o in coverage['obligations']:
        assert o['page_ref'] == 'P3' and o['field_path'] == 'pages[2].structured_content[0].text'
        check_span(field, o['artifact_span'])
        check_span(source, o['corroborating_source_span'])
        assert o['candidate_answer_proposition'] == o['artifact_span']['quote'] == o['corroborating_source_span']['quote']
        assert o['human_support_verdict'] == 'NOT_REVIEWED' and o['human_reason'] is None
    check_span((HERE / 'snapshots/DemoDisclosure.astro').read_bytes().decode('utf-8'), coverage['disclosure']['span'])
    specs = candidate['specifications']
    assert candidate['status'] == 'BLOCKED_NOT_FINALIZED'
    assert candidate['formal_opportunity_report'] is candidate['formal_plan_report'] is None
    assert specs['opportunity']['source_refs'] == specs['plan']['source_refs'] == []
    assert specs['plan']['operation_type'] == 'EXPAND_SECTION'
    assert specs['plan']['locator']['target_heading'] == specs['opportunity']['topic'] == packet['pages'][2]['h1'][0]
    assert len(specs['plan']['content_points']) == 1
    assert specs['plan']['content_points'][0] == {'intent': 'EXPLAIN', 'subject': packet['pages'][2]['title'], 'origin_ref': 'P3'}
    assert candidate['comparison_operations'] == binding['selected_source_refs'] == []
    probe = read('planning-validation.json')
    assert probe['opportunity_specification_error'] == 'SOURCE_REFERENCE_REQUIRED'
    assert probe['opportunity_finalizer_calls'] == probe['plan_finalizer_calls'] == probe['provider_calls'] == probe['wordpress_calls'] == 0
    assert not probe['new_opportunity_report_created'] and not probe['new_plan_report_created']
    assert binding['formal_plan_digest'] is None and binding['approval'] == 'NOT_REVIEWED'
    assert review['overall_verdict'] == review['status'] == 'NOT_REVIEWED'
    assert not review['runtime_approval_valid'] and review['executable_plan_rebinding_required']
    assert len(review['owner_decisions']) == 8
    for d in review['owner_decisions']:
        assert d['decision'] == 'NOT_REVIEWED'
        assert all(d[k] is None for k in ('reason', 'reviewer', 'confirmed_at', 'trusted_message_or_record'))
    for o in review['obligation_verdicts']:
        assert o['verdict'] == 'NOT_REVIEWED'
        assert all(o[k] is None for k in ('reason', 'reviewer', 'confirmed_at'))
    for key in ('reviewer_identity', 'reviewer_authority_provenance', 'source_use_authorization', 'scope_authorization', 'technical_certification', 'reviewed_at', 'expires_at', 're_review_rule_confirmation'):
        assert review[key] is None
    assert all(not manifest[k] for k in ('owner_review_complete', 'engineering_facts_certified', 'legal_matching_plan_available', 'gate_implemented', 'draft_quality_passed'))
    links = 0
    link_paths = []
    docs = [ROOT / entry, ROOT / 'docs/evidence-sufficiency-review-brief-2026-10-08.md', *HERE.glob('*.md')]
    for doc in docs:
        content = doc.read_text(encoding='utf-8')
        assert not any(line.endswith((' ', '\t')) for line in content.splitlines()), doc.name
        for target in re.findall(r'\[[^\]]+\]\(([^)]+)\)', content):
            if '://' not in target:
                resolved = (doc.parent / target.split('#')[0]).resolve()
                # The result file is created below after checks succeed; check
                # every other link now, then this output link after writing.
                if resolved != HERE / 'verification.json':
                    assert resolved.is_file(), target
                link_paths.append(resolved)
                links += 1
    preservation = read('preservation.json')
    assert preservation['preservation'] == 'VERIFIED'
    assert preservation['production_and_formal_tests_modified_this_round'] is False
    assert preservation['unchanged_workspace_paths'] + 1 == preservation['baseline_workspace_paths']
    assert preservation['authorized_existing_doc_change'] == ['docs/evidence-sufficiency-review-brief-2026-10-08.md']
    result = {
        'integrity': 'VERIFIED_ONLY_NOT_AUTHORIZATION_OR_SUFFICIENCY',
        'binding_canonical_sha256': digest,
        'snapshot_files_verified': len(binding['snapshot_files_sha256']),
        'original_artifact_identities_verified': len(provenance['original_artifacts']),
        'exact_spans_verified': 13, 'document_links_verified': links,
        'package_files_verified': len(manifest['package_files_sha256']),
        'preservation_record_integrity': 'VERIFIED; external preservation was run separately this round',
        'this_round_preserved_workspace_paths': preservation['unchanged_workspace_paths'],
        'this_round_preserved_database_files': preservation['unchanged_database_files'],
        'this_round_preserved_legacy_package_files': preservation['unchanged_legacy_package_files'],
        'planning_probe_result': probe['opportunity_specification_error'],
        'owner_decisions': '8 NOT_REVIEWED', 'obligation_verdicts': '6 NOT_REVIEWED',
        'legal_matching_plan': 'NOT_AVAILABLE', 'gate': 'NOT_IMPLEMENTED',
        'real_draft_quality': 'NOT_PASSED', 'decision': 'NO_GREEN',
    }
    (HERE / 'verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    assert all(path.is_file() for path in link_paths)
    print(json.dumps(result, ensure_ascii=False))

if __name__ == '__main__':
    verify()
