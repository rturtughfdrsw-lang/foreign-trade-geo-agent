"""Offline experiment boundary tests, including stale inputs and hostile outputs."""
from copy import deepcopy
from dataclasses import asdict, replace
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from scripts import prepare_seo_draft_v2_flash_preflight as p
from tests.draft_v2_fixtures import explanation_fixture
from foreign_trade_geo_agent.core.draft_selection_contract import canonical_json


class FlashPreflightTests(unittest.TestCase):
    def setUp(self):
        self.value, self.selection = p.load_inputs()
        self.baseline = json.loads((p.HISTORY / 'request.json').read_bytes())

    def envelope(self):
        raw, sidecar = explanation_fixture(self.selection)
        return dict(candidate=json.loads(raw), explanations=[
            {k: v for k, v in asdict(a).items() if k != 'text_sha256'} for a in sidecar.explanations])

    def check_response(self, body):
        return p.parse_experiment_response(canonical_json(body), self.value, self.selection)

    def package(self, directory):
        p.prepare(directory)
        return p.freeze(directory)

    def test_request_is_stable_and_baseline_parameters_identical(self):
        a, material = p.build_request(self.value, self.selection, self.baseline)
        b, _ = p.build_request(self.value, self.selection, deepcopy(self.baseline))
        self.assertEqual(a, b)
        request = json.loads(a)
        self.assertEqual({k: v for k, v in request.items() if k != 'messages'}, p.PARAMETERS)
        old = json.loads(self.baseline['messages'][1]['content'])
        for key in ('change', 'opportunity', 'pages', 'sources', 'writing_brief'):
            self.assertEqual(old[key], material[key])

    def test_changed_model_or_added_parameter_is_rejected(self):
        for key, value in [('model', 'other'), ('temperature', 1), ('stream', True)]:
            baseline = deepcopy(self.baseline)
            baseline[key] = value
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'BASELINE_PARAMETERS'):
                p.build_request(self.value, self.selection, baseline)

    def test_request_contains_selected_customer_facts_only_and_no_reasons(self):
        raw, material = p.build_request(self.value, self.selection, self.baseline)
        selected = {r for s in self.selection.sections for r in s.selected_facts}
        projected = {f['fact_ref'] for s in material['sections'] for f in s['selected_facts']}
        self.assertEqual(selected, projected)
        for source in self.value.customer_evidence.sources:
            self.assertNotIn(source.content, raw.decode())
            for fact in source.facts:
                if fact.fact_ref not in selected:
                    self.assertNotIn(fact.fact_ref, raw.decode())
                    # Request JSON contains escaped strings; inspect decoded content too.
                    self.assertNotIn(fact.quote, canonical_json(material))
        for reason in self.selection.fact_reasons:
            self.assertNotIn(reason.reason, canonical_json(material))

    def test_extra_bank_and_reason_fields_rejected(self):
        _, material = p.build_request(self.value, self.selection, self.baseline)
        for key in ('fact_bank', 'selection_reason', 'customer_evidence'):
            changed = deepcopy(material)
            changed[key] = 'leak'
            with self.subTest(key=key), self.assertRaises(ValueError):
                p.assert_writer_boundary(changed, self.selection, self.value)

    def test_unselected_quote_hidden_in_planning_context_rejected(self):
        selected = {r for s in self.selection.sections for r in s.selected_facts}
        fact = next(f for s in self.value.customer_evidence.sources for f in s.facts if f.fact_ref not in selected)
        _, material = p.build_request(self.value, self.selection, self.baseline)
        material['writing_brief']['instructions'].append(fact.quote)
        # Simulate a projection regression, even if exact projection equality agrees.
        with patch.object(p, 'build_offline_writer_material', return_value=deepcopy(material)):
            with self.assertRaisesRegex(ValueError, 'UNSELECTED_FACT_LEAK'):
                p.assert_writer_boundary(material, self.selection, self.value)

    def test_stale_snapshot_plan_or_evidence_rejected(self):
        for field in ('evidence_snapshot_sha256', 'plan_sha256', 'evidence_sha256'):
            with self.subTest(field=field):
                changed = replace(self.selection, **{field: '0' * 64})
                with self.assertRaises(ValueError):
                    p.build_request(self.value, changed, self.baseline)

    def test_prompt_prioritizes_procurement_and_explicit_boundaries(self):
        self.assertTrue(p.SYSTEM.startswith('You write an English procurement decision guide'))
        for phrase in ('FIRST PRIORITY: procurement decision value', 'ONLY customer factual authority',
                       'selected_facts', 'Do not widen numerical meaning', 'certifications, customer cases, performance guarantees',
                       'Evidence (selected facts)', 'Interpretation (why', 'Boundary (when', 'Verification (what',
                       'this helps buyers', 'this is important', 'why', 'at most 48 claims and 24 blocks'):
            self.assertIn(phrase, p.SYSTEM)
        self.assertNotIn('E999', p.SYSTEM)
        self.assertLessEqual(len(p.SYSTEM), p.cd.MAX_SYSTEM_PROMPT_CHARS)

    def test_prepare_stable_and_refuses_changed_or_sealed_file(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            p.prepare(path)
            before = {x.name: x.read_bytes() for x in path.iterdir()}
            p.prepare(path)
            self.assertEqual(before, {x.name: x.read_bytes() for x in path.iterdir()})
            digest = p.freeze(path)
            self.assertTrue(p.verify_manifest(path, digest)['valid'])
            with self.assertRaisesRegex(ValueError, 'ALREADY_SEALED'):
                p.prepare(path)

    def test_prepare_will_not_overwrite_changed_request(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            p.prepare(path)
            target = path / 'request-body-template.json'
            target.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'EXISTING_FILE_CHANGED'):
                p.prepare(path)
            self.assertEqual(target.read_bytes(), b'changed')

    def test_manifest_entries_have_required_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            self.package(path)
            manifest = json.loads((path / 'manifest.json').read_bytes())
            for entry in manifest['files']:
                self.assertEqual(set(entry), {'filename', 'sha256', 'size', 'created_time', 'version'})
                self.assertTrue(entry['created_time'].endswith('+08:00'))
                self.assertEqual(entry['version'], p.VERSION)

    def test_any_file_change_addition_or_deletion_invalidates_manifest(self):
        for mode in ('change', 'add', 'delete', 'nested_manifest'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temp:
                path = Path(temp)
                digest = self.package(path)
                if mode == 'change':
                    (path / 'task.json').write_bytes(b'changed')
                elif mode == 'add':
                    (path / 'extra.txt').write_bytes(b'extra')
                elif mode == 'nested_manifest':
                    (path / 'extra').mkdir()
                    (path / 'extra/manifest.json').write_bytes(b'extra')
                else:
                    (path / 'task.json').unlink()
                with self.assertRaises(ValueError):
                    p.verify_manifest(path, digest)

    def test_manifest_rewrite_cannot_reauthorize_with_original_trusted_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            digest = self.package(path)
            raw = (path / 'manifest.json').read_bytes() + b' '
            (path / 'manifest.json').write_bytes(raw)
            (path / 'manifest.sha256').write_text(p.sha(raw) + '  manifest.json\n', encoding='ascii')
            with self.assertRaisesRegex(ValueError, 'MANIFEST_CHANGED'):
                p.verify_manifest(path, digest)

    def test_anchor_change_invalidates_experiment(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            digest = self.package(path)
            (path / 'manifest.sha256').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'ANCHOR_CHANGED'):
                p.verify_manifest(path, digest)

    def test_divergent_local_inputs_are_rejected_before_sealing(self):
        for name in ('task.json', 'plan.json', 'evidence-snapshot.json', 'explanation-contract.json',
                     'system-prompt.txt', 'user-prompt.txt', 'experiment-config.json', 'token-budget.json'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp:
                path = Path(temp)
                p.prepare(path)
                (path / name).write_bytes(b'changed')
                with self.assertRaisesRegex(ValueError, 'PACKAGE_INPUT_CHANGED'):
                    p.freeze(path)
                self.assertFalse((path / 'manifest.json').exists())

    def test_changed_source_code_invalidates_experiment(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            digest = self.package(path)
            changed = p.source_integrity()
            changed['scripts/prepare_seo_draft_v2_flash_preflight.py'] = '0' * 64
            with patch.object(p, 'source_integrity', return_value=changed):
                with self.assertRaisesRegex(ValueError, 'SOURCE_CHANGED'):
                    p.verify_manifest(path, digest)

    def test_parser_validator_and_explanation_pass_on_existing_synthetic_mock(self):
        candidate, sidecar, check = self.check_response(self.envelope())
        self.assertEqual(check.state, 'PENDING_SEMANTIC_REVIEW')
        self.assertEqual(check.errors, ())
        self.assertEqual((check.claims, check.blocks), (38, 20))
        self.assertTrue(check.selection_valid and check.routing_valid and check.explanation_structure_valid)
        self.assertFalse(check.production_authorized or check.semantic_approved)
        self.assertEqual(sidecar.candidate_sha256, p.sha(candidate.encode()))
        self.assertEqual(sidecar.selection_sha256, p.selection_digest(self.selection))
        for a in sidecar.explanations:
            body = ' '.join((a.buyer_implication, a.non_applicability, a.verification_action))
            self.assertEqual(a.text_sha256, p.sha(body.encode()))

    def test_annotation_claim_section_refs_and_visible_body_are_binding(self):
        mutations = [('explanation_claim_id', 'CL1'), ('section_id', 'S6'),
                     ('selected_fact_refs', ['E7.F05']),
                     ('buyer_implication', 'This entirely different reasoning answers another question and changes the purchasing implication while claiming to use exactly the same evidence.')]
        for field, changed in mutations:
            with self.subTest(field=field):
                body = self.envelope()
                body['explanations'][0][field] = changed
                _, _, check = self.check_response(body)
                self.assertEqual(check.state, 'DETERMINISTICALLY_REJECTED')

    def test_missing_duplicate_extra_annotation_rejected(self):
        for mode in ('missing', 'duplicate', 'extra_field', 'model_hash'):
            with self.subTest(mode=mode):
                body = self.envelope()
                if mode == 'missing':
                    body['explanations'].pop()
                elif mode == 'duplicate':
                    body['explanations'].append(body['explanations'][0])
                else:
                    body['explanations'][0]['candidate_sha256' if mode == 'model_hash' else 'reasoning'] = 'unexpected'
                try:
                    _, _, check = self.check_response(body)
                except ValueError:
                    continue
                self.assertEqual(check.state, 'DETERMINISTICALLY_REJECTED')

    def test_unselected_fact_and_cross_section_reference_rejected(self):
        for ref in ('E2.F02', 'E7.F01', 'E99.F99'):
            with self.subTest(ref=ref):
                body = self.envelope()
                body['candidate']['draft']['sections'][0]['blocks'][0]['claims'][0]['customer_refs'] = [ref]
                _, _, check = self.check_response(body)
                self.assertEqual(check.state, 'DETERMINISTICALLY_REJECTED')

    def test_malformed_containers_duplicate_keys_and_size_are_sanitized(self):
        malformed = ['[]', 'null', '{"candidate":{},"candidate":{},"explanations":[]}',
                     '{"candidate":{},"explanations":NaN}', '[' * 2000 + ']' * 2000,
                     'x' * (p.cd.MAX_RAW_OUTPUT_CHARS + 1), '\ud800',
                     '{"candidate":{},"explanations":{}}']
        for raw in malformed:
            with self.subTest(length=len(raw)), self.assertRaisesRegex(ValueError, '^PREFLIGHT_RESPONSE_INVALID$'):
                p.parse_experiment_response(raw, self.value, self.selection)

    def test_native_parser_schema_is_not_weakened_by_envelope(self):
        for mutation in ('extra_top', 'extra_native', 'extra_claim'):
            body = self.envelope()
            if mutation == 'extra_top':
                body['approval'] = True
            elif mutation == 'extra_native':
                body['candidate']['sidecar'] = {}
            else:
                body['candidate']['draft']['sections'][0]['blocks'][0]['claims'][0]['extra'] = True
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.check_response(body)

    def test_no_network_api_wordpress_and_v1_files_unchanged(self):
        before = {x.relative_to(p.HISTORY).as_posix(): p.sha(x.read_bytes())
                  for x in p.HISTORY.rglob('*') if x.is_file()}
        with tempfile.TemporaryDirectory() as temp, \
             patch.object(socket, 'create_connection', side_effect=AssertionError('NETWORK_FORBIDDEN')) as conn, \
             patch.object(socket, 'getaddrinfo', side_effect=AssertionError('DNS_FORBIDDEN')) as dns, \
             patch('httpx.Client.send', side_effect=AssertionError('API_FORBIDDEN')) as http, \
             patch('httpx.AsyncClient.send', side_effect=AssertionError('API_FORBIDDEN')) as async_http:
            digest = self.package(Path(temp))
            self.assertTrue(p.verify_manifest(Path(temp), digest)['valid'])
            self.check_response(self.envelope())
            for method in (conn, dns, http, async_http):
                method.assert_not_called()
        after = {x.relative_to(p.HISTORY).as_posix(): p.sha(x.read_bytes())
                 for x in p.HISTORY.rglob('*') if x.is_file()}
        self.assertEqual(before, after)
        self.assertEqual(p.sha((p.HISTORY / 'model-output.txt').read_bytes()), p.FROZEN_V1_OUTPUT_HASH)

    def test_budget_is_estimated_not_precise_or_authorized(self):
        request, _ = p.build_request(self.value, self.selection, self.baseline)
        budget = p.budget_for(request)
        self.assertTrue(budget['estimated'])
        self.assertIsNone(budget['exact_input_tokens'])
        self.assertEqual(budget['tokenizer_api_calls'], 0)
        self.assertFalse(budget['current_prices_verified'])
        self.assertFalse(budget['recommended_budget']['authorization_granted'])
        self.assertEqual(budget['max_output_tokens'], self.baseline['max_tokens'])


if __name__ == '__main__':
    unittest.main()
