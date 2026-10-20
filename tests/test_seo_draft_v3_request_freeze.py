"""Offline-only freeze construction/checks; no provider, parser or validator edits.

Helpers live here because this task permits one test module and six documents,
not a new production entry point. Sources are read, never regenerated or written.
Manifest filenames are repository-relative, including externally retained inputs.
"""
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
import unittest

from foreign_trade_geo_agent.core.content_draft import ContentDraftInput
from foreign_trade_geo_agent.core import content_draft as cd
from foreign_trade_geo_agent.core.draft_selection_contract import (
    canonical_json, evidence_digest, plan_digest, selection_digest, validate_selection,
)
from foreign_trade_geo_agent.storage.draft_selection_contract import decode_selection_artifact
from foreign_trade_geo_agent.storage.serialization import _decode

ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'docs/seo-draft-contract-v3-integration'
DEST = 'docs/seo-draft-contract-v3-flash-preflight'
SOURCE_ANCHOR = 'ccafe59f3044a432f2a36a9ba856c16366b5cbff8eccd235adfa428738cf08ec'
SOURCE_NAMES = (
    'artifact-sha256.json', 'verification.json', 'selection-artifact.json',
    'synthetic-input.json', 'writer-projection.json', 'prompt-v3-material.json',
    'experiment-config.json',
)
PACKAGE_NAMES = {'request.json', 'experiment-config.json', 'manifest.json',
                 'manifest.sha256', 'request-body.sha256', 'report.md'}


def require(condition, code):
    if not condition:
        raise ValueError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return canonical_json(value).encode('utf-8')


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'DUPLICATE_KEY')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda _: require(False, 'JSON_CONSTANT'))


def read_sources():
    directory = ROOT / SOURCE
    sources = {name: (directory / name).read_bytes() for name in SOURCE_NAMES}
    require(sha(sources['artifact-sha256.json']) == SOURCE_ANCHOR, 'SOURCE_MANIFEST_HASH')
    for name, digest in strict_json(sources['artifact-sha256.json']).items():
        require(sha((directory / name).read_bytes()) == digest, 'SOURCE_FILE_HASH')
    return sources


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)


def check_boundary(prompt, projection, selection, value):
    """Scan decoded strings, including planning context, before exact byte binding."""
    require(prompt['writer_projection'] == projection, 'PROJECTION_BINDING')
    text = '\n'.join(strings(prompt))
    selected = {r for s in selection.sections for r in s.selected_facts}
    require(set(re.findall(r'E[1-9][0-9]{0,2}\.F[0-9]{2}', text)) <= selected,
            'UNSELECTED_FACT_LEAK')
    for source in value.customer_evidence.sources:
        require(source.content not in text, 'FULL_SOURCE_LEAK')
        for fact in source.facts:
            if fact.fact_ref not in selected:
                require(fact.quote not in text, 'UNSELECTED_FACT_LEAK')
    for reason in selection.fact_reasons:
        require(reason.reason not in text, 'SELECTION_REASON_LEAK')
    forbidden = {'fact_reasons', 'optional_facts', 'selection_reason', 'customer_evidence',
                 'fact_bank', 'audit_artifact', 'test_file', 'historical_failed_output'}
    require(not forbidden.intersection(strings(prompt)), 'PRIVATE_FIELD_LEAK')
    require(len(projection['sections']) == len(selection.sections), 'SECTION_COUNT')
    facts = {f.fact_ref: (s, f) for s in value.customer_evidence.sources for f in s.facts}
    for section, budget in zip(projection['sections'], selection.sections):
        require(section['section_id'] == budget.section_id, 'SECTION_ID')
        expected = []
        for ref in budget.selected_facts:
            source, fact = facts[ref]
            expected.append(dict(fact_ref=ref, quote=fact.quote, source=source.evidence_id,
                version=source.evidence_version, source_sha256=source.content_sha256,
                location=dict(locator=source.source_locator, start=fact.start, end=fact.end),
                requirement_ids=list(fact.requirement_ids)))
        require(section['selected_facts'] == expected, 'SELECTED_FACT_PROJECTION')


def source_context(sources):
    require(set(sources) == set(SOURCE_NAMES), 'MISSING_SOURCE')
    require(sha(sources['artifact-sha256.json']) == SOURCE_ANCHOR, 'SOURCE_MANIFEST_HASH')
    source_manifest = strict_json(sources['artifact-sha256.json'])
    for name in SOURCE_NAMES[1:]:
        require(sha(sources[name]) == source_manifest[name], 'SOURCE_FILE_HASH')
    old = strict_json(sources['experiment-config.json'])
    require(strict_json(sources['verification.json'])['final_state'] ==
            'OFFLINE_V3_INTEGRATION_READY', 'SOURCE_NOT_READY')
    selection = decode_selection_artifact(sources['selection-artifact.json'].decode('utf-8'))
    data = strict_json(sources['synthetic-input.json'])
    value = _decode(data['native_input'], ContentDraftInput)
    validate_selection(selection, value, current_snapshot_sha256=data['current_snapshot_sha256'])
    require(data['selection_artifact']['payload'] == strict_json(encode(asdict(selection))),
            'INPUT_SELECTION_BINDING')
    require(old['selection_hash'] == selection_digest(selection) and
            old['snapshot_hash'] == selection.evidence_snapshot_sha256 and
            old['plan_hash'] == plan_digest(value) and
            selection.evidence_sha256 == evidence_digest(value.customer_evidence), 'CONTEXT_HASH')
    require(old['semantic_approved'] is False and old['production_authorized'] is False,
            'SOURCE_AUTHORITY')
    prompt = strict_json(sources['prompt-v3-material.json'])
    projection = strict_json(sources['writer-projection.json'])
    require(prompt['contract_version'] == old['contract_version'], 'CONTRACT_VERSION')
    check_boundary(prompt, projection, selection, value)
    return old, prompt, projection, selection, value


def check_config(config):
    for key in ('live_authorized', 'production_authorized', 'semantic_approved', 'network_allowed'):
        require(config.get(key) is False, 'AUTHORIZATION_FLAG')
    expected = dict(model='deepseek-flash', temperature=0, thinking='disabled',
                    response_format='json_object', max_tokens=16384, timeout=60,
                    contract_version='v3', state='FROZEN_NOT_AUTHORIZED')
    for key, value in expected.items():
        require(key in config, 'MISSING_CONFIG')
        require(type(config[key]) is type(value) and config[key] == value, 'CONFIG_VALUE')


def build_bundle(sources):
    """Only envelope serialization is new; the user message preserves prompt bytes."""
    old, prompt, _, _, _ = source_context(sources)
    config = dict(model='deepseek-flash', temperature=0, thinking='disabled',
        response_format='json_object', max_tokens=16384, timeout=60, contract_version='v3',
        explanation_contract_version=old['contract_version'], state='FROZEN_NOT_AUTHORIZED',
        network_allowed=False, live_authorized=False, semantic_approved=False,
        production_authorized=False, selection_hash=old['selection_hash'],
        snapshot_hash=old['snapshot_hash'], plan_hash=old['plan_hash'],
        prompt_hash=sha(sources['prompt-v3-material.json']),
        writer_projection_hash=sha(sources['writer-projection.json']),
        selection_artifact_hash=sha(sources['selection-artifact.json']),
        prompt_hash_scope='SHA256 original prompt-v3-material.json file bytes',
        timeout_scope='Transport seconds; not a provider JSON field',
        retries=0, fallback_allowed=False, repair_allowed=False, redirects_allowed=False)
    check_config(config)
    request = dict(model=config['model'], temperature=config['temperature'],
        thinking={'type': config['thinking']}, response_format={'type': config['response_format']},
        max_tokens=config['max_tokens'], messages=[
            {'role': 'system', 'content': prompt['instructions']},
            {'role': 'user', 'content': sources['prompt-v3-material.json'].decode('utf-8')}])
    raw = encode(request)
    for text, chars_limit, bytes_limit in (
        (request['messages'][0]['content'], cd.MAX_SYSTEM_PROMPT_CHARS, cd.MAX_SYSTEM_PROMPT_BYTES),
        (request['messages'][1]['content'], cd.MAX_USER_MATERIAL_CHARS, cd.MAX_USER_MATERIAL_BYTES),
        (raw.decode('utf-8'), cd.MAX_INPUT_ENVELOPE_CHARS, cd.MAX_INPUT_ENVELOPE_BYTES),
    ):
        require(len(text) <= chars_limit and len(text.encode('utf-8')) <= bytes_limit, 'INPUT_SIZE')
    files = {'request.json': raw, 'experiment-config.json': encode(config),
             'request-body.sha256': (sha(raw) + '  request.json\n').encode('ascii')}
    inputs = {f'{SOURCE}/{name}': body for name, body in sources.items()}
    inputs.update({f'{DEST}/{name}': body for name, body in files.items()})
    manifest = dict(version='seo-draft-v3-request-freeze-1', filename_base='repository_root',
        state='FROZEN_NOT_AUTHORIZED', network_allowed=False,
        files=[dict(filename=name, sha256=sha(body), size=len(body))
               for name, body in sorted(inputs.items())],
        exclusions=['manifest.json (self)', 'manifest.sha256 (self anchor)', 'report.md (not an input)'])
    files['manifest.json'] = encode(manifest)
    files['manifest.sha256'] = (sha(files['manifest.json']) + '  manifest.json\n').encode('ascii')
    return files


def verify_package(directory, trusted_manifest_hash, sources=None):
    """No repair/reseal path. The trusted anchor must come from outside the package."""
    directory = Path(directory)
    require({p.name for p in directory.iterdir()} == PACKAGE_NAMES, 'PACKAGE_FILE_SET')
    require(all((directory / name).is_file() and not (directory / name).is_symlink()
                for name in PACKAGE_NAMES), 'PACKAGE_FILE_TYPE')
    raw = (directory / 'manifest.json').read_bytes()
    require(sha(raw) == trusted_manifest_hash, 'MANIFEST_HASH')
    require((directory / 'manifest.sha256').read_bytes() ==
            (trusted_manifest_hash + '  manifest.json\n').encode('ascii'), 'MANIFEST_ANCHOR')
    config = strict_json((directory / 'experiment-config.json').read_bytes())
    check_config(config)
    sources = read_sources() if sources is None else sources
    old, prompt, projection, selection, value = source_context(sources)
    request = strict_json((directory / 'request.json').read_bytes())
    candidate_prompt = strict_json(request['messages'][1]['content'])
    check_boundary(candidate_prompt, candidate_prompt['writer_projection'], selection, value)
    require(request['messages'][0]['content'] == prompt['instructions'], 'SYSTEM_PROMPT_CHANGED')
    require(request['messages'][1]['content'].encode('utf-8') == sources['prompt-v3-material.json'],
            'PROMPT_BYTES_CHANGED')
    expected = build_bundle(sources)
    for name, body in expected.items():
        require((directory / name).read_bytes() == body, 'PACKAGE_HASH_MISMATCH')
    return dict(valid=True, state='FROZEN_NOT_AUTHORIZED', request_hash=sha(expected['request.json']),
                manifest_hash=sha(expected['manifest.json']), network_allowed=False)


class V3RequestFreezeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = read_sources()

    def package(self, directory):
        files = build_bundle(self.sources)
        for name, raw in files.items():
            (Path(directory) / name).write_bytes(raw)
        (Path(directory) / 'report.md').write_text('Test-only report', encoding='utf-8')
        return sha(files['manifest.json'])

    def test_request_deterministic_and_original_prompt_bytes(self):
        a = build_bundle(self.sources)
        b = build_bundle(dict(reversed(list(self.sources.items()))))
        self.assertEqual(a, b)
        request = strict_json(a['request.json'])
        self.assertEqual(request['messages'][1]['content'].encode(), self.sources['prompt-v3-material.json'])
        self.assertEqual(set(request), {'model', 'temperature', 'thinking', 'response_format', 'max_tokens', 'messages'})
        self.assertEqual(request['thinking'], {'type': 'disabled'})
        self.assertEqual(request['response_format'], {'type': 'json_object'})

    def test_manifest_integrity_metadata_and_no_self_hash(self):
        files = build_bundle(self.sources)
        manifest = strict_json(files['manifest.json'])
        entries = manifest['files']
        self.assertEqual(len(entries), 10)
        expected = {f'{SOURCE}/{n}': b for n, b in self.sources.items()}
        expected.update({f'{DEST}/{n}': files[n] for n in ('request.json', 'experiment-config.json', 'request-body.sha256')})
        self.assertEqual({e['filename'] for e in entries}, set(expected))
        for entry in entries:
            self.assertEqual(set(entry), {'filename', 'sha256', 'size'})
            self.assertEqual(entry['sha256'], sha(expected[entry['filename']]))
            self.assertEqual(entry['size'], len(expected[entry['filename']]))
        with tempfile.TemporaryDirectory() as temp:
            anchor = self.package(temp)
            self.assertTrue(verify_package(temp, anchor, self.sources)['valid'])

    def test_hash_mismatch_reject_for_each_bound_file(self):
        for name in ('request.json', 'experiment-config.json', 'manifest.json', 'manifest.sha256', 'request-body.sha256'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp:
                anchor = self.package(temp)
                path = Path(temp) / name
                path.write_bytes(path.read_bytes() + b' ')
                with self.assertRaises(ValueError):
                    verify_package(temp, anchor, self.sources)

    def test_original_anchor_rejects_locally_rehashed_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            anchor = self.package(temp)
            path = Path(temp) / 'manifest.json'
            path.write_bytes(path.read_bytes() + b' ')
            (Path(temp) / 'manifest.sha256').write_text(sha(path.read_bytes()) + '  manifest.json\n')
            with self.assertRaisesRegex(ValueError, 'MANIFEST_HASH'):
                verify_package(temp, anchor, self.sources)

    def test_each_source_hash_mismatch_rejects(self):
        for name in self.sources:
            with self.subTest(name=name):
                changed = dict(self.sources)
                changed[name] += b' '
                with self.assertRaisesRegex(ValueError, 'SOURCE_.*HASH'):
                    build_bundle(changed)

    def test_selected_facts_leakage_reject(self):
        _, prompt, projection, selection, value = source_context(self.sources)
        selected = {r for s in selection.sections for r in s.selected_facts}
        fact = next(f for s in value.customer_evidence.sources for f in s.facts if f.fact_ref not in selected)
        for leak in (fact.fact_ref, fact.quote):
            with self.subTest(leak_type='ref' if leak == fact.fact_ref else 'quote'):
                bad = deepcopy(prompt)
                bad['writer_projection']['writing_brief']['instructions'].append(leak)
                with self.assertRaisesRegex(ValueError, 'UNSELECTED_FACT_LEAK'):
                    check_boundary(bad, bad['writer_projection'], selection, value)

    def test_fact_in_wrong_section_reject(self):
        _, prompt, _, selection, value = source_context(self.sources)
        bad = deepcopy(prompt)
        sections = bad['writer_projection']['sections']
        sections[0]['selected_facts'].append(sections[1]['selected_facts'][0])
        with self.assertRaisesRegex(ValueError, 'SELECTED_FACT_PROJECTION'):
            check_boundary(bad, bad['writer_projection'], selection, value)

    def test_selection_reason_and_private_artifact_reject(self):
        _, prompt, _, selection, value = source_context(self.sources)
        bad = deepcopy(prompt)
        bad['extra'] = selection.fact_reasons[0].reason
        with self.assertRaisesRegex(ValueError, 'SELECTION_REASON_LEAK'):
            check_boundary(bad, bad['writer_projection'], selection, value)
        for key in ('audit_artifact', 'test_file', 'historical_failed_output'):
            bad = deepcopy(prompt)
            bad[key] = 'forbidden'
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'PRIVATE_FIELD_LEAK'):
                check_boundary(bad, bad['writer_projection'], selection, value)

    def test_extra_request_content_rejected_even_if_not_a_known_leak(self):
        with tempfile.TemporaryDirectory() as temp:
            anchor = self.package(temp)
            path = Path(temp) / 'request.json'
            request = strict_json(path.read_bytes())
            material = strict_json(request['messages'][1]['content'])
            material['unknown_attachment'] = 'arbitrary text'
            request['messages'][1]['content'] = encode(material).decode()
            path.write_bytes(encode(request))
            with self.assertRaisesRegex(ValueError, 'PROMPT_BYTES_CHANGED'):
                verify_package(temp, anchor, self.sources)

    def test_authorization_flag_reject(self):
        for key in ('live_authorized', 'production_authorized', 'semantic_approved', 'network_allowed'):
            for value in (True, 1, 'false', None):
                with self.subTest(key=key, value=value), tempfile.TemporaryDirectory() as temp:
                    anchor = self.package(temp)
                    path = Path(temp) / 'experiment-config.json'
                    config = strict_json(path.read_bytes())
                    config[key] = value
                    path.write_bytes(encode(config))
                    with self.assertRaisesRegex(ValueError, 'AUTHORIZATION_FLAG'):
                        verify_package(temp, anchor, self.sources)

    def test_missing_config_reject(self):
        with tempfile.TemporaryDirectory() as temp:
            anchor = self.package(temp)
            (Path(temp) / 'experiment-config.json').unlink()
            with self.assertRaisesRegex(ValueError, 'PACKAGE_FILE_SET'):
                verify_package(temp, anchor, self.sources)
        for key in ('model', 'temperature', 'thinking', 'response_format', 'max_tokens', 'timeout'):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as temp:
                anchor = self.package(temp)
                path = Path(temp) / 'experiment-config.json'
                config = strict_json(path.read_bytes())
                del config[key]
                path.write_bytes(encode(config))
                with self.assertRaisesRegex(ValueError, 'MISSING_CONFIG'):
                    verify_package(temp, anchor, self.sources)

    def test_duplicate_json_keys_reject(self):
        with self.assertRaisesRegex(ValueError, 'DUPLICATE_KEY'):
            strict_json('{"model":"one","model":"two"}')

    def test_frozen_real_package_matches_deterministic_sources(self):
        files = build_bundle(self.sources)
        # Historical results coexist beneath DEST. Verify original frozen bytes
        # in an isolated six-file copy; do not regenerate or move history.
        with tempfile.TemporaryDirectory() as temp:
            for name in PACKAGE_NAMES:
                shutil.copyfile(ROOT / DEST / name, Path(temp) / name)
            result = verify_package(temp, sha(files['manifest.json']), self.sources)
        self.assertFalse(result['network_allowed'])
        self.assertEqual(result['state'], 'FROZEN_NOT_AUTHORIZED')

    def test_extra_directory_inside_frozen_package_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            anchor = self.package(temp)
            (Path(temp) / 'results').mkdir()
            with self.assertRaisesRegex(ValueError, '^PACKAGE_FILE_SET$'):
                verify_package(temp, anchor, self.sources)

    def test_results_sibling_does_not_change_frozen_package(self):
        with tempfile.TemporaryDirectory() as temp:
            package = Path(temp) / 'frozen'
            package.mkdir()
            anchor = self.package(package)
            (Path(temp) / 'results').mkdir()
            self.assertTrue(verify_package(package, anchor, self.sources)['valid'])


if __name__ == '__main__':
    unittest.main()
