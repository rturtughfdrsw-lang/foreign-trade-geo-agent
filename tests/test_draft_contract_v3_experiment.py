"""Offline v3 integration, independent sidecar and unchanged native review path."""
from dataclasses import asdict, replace
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from foreign_trade_geo_agent.core.draft_explanation_contract_v3 import (
    VERSION, encode_sidecar_v3, render_parts,
)
from foreign_trade_geo_agent.core.draft_selection_contract import canonical_json, text_digest
from foreign_trade_geo_agent.storage.draft_selection_contract import (
    encode_selection_artifact, decode_selection_artifact,
)
from foreign_trade_geo_agent.workflows.content_draft import inspect_candidate_output
from foreign_trade_geo_agent.workflows.draft_contract_v2 import build_offline_writer_material
from foreign_trade_geo_agent.workflows.draft_contract_v3_experiment import (
    run_offline_v3_experiment, MAX_ENVELOPE_BYTES,
)
from tests.draft_explanation_v3_fixtures import fixture_v3, rebind, LIVE, replay_original
from tests.draft_v2_fixtures import HISTORY


def synthetic_envelope(raw, sidecar):
    encoded = encode_sidecar_v3(sidecar)
    return dict(contract_version=VERSION, candidate=json.loads(raw),
        v3_sidecar=json.loads(encoded), sidecar_hash=text_digest(encoded),
        semantic_approved=False, production_authorized=False)


class OfflineV3IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.value, selection, cls.raw, cls.sidecar = fixture_v3()
        # Start at the actual persisted Selection Artifact boundary.
        cls.selection = decode_selection_artifact(encode_selection_artifact(selection))

    def envelope(self):
        return synthetic_envelope(self.raw, self.sidecar)

    def run_chain(self, envelope=None, *, raw=None, selection=None, snapshot=None):
        return run_offline_v3_experiment(self.value, selection or self.selection,
            canonical_json(self.envelope() if envelope is None else envelope) if raw is None else raw,
            current_snapshot_sha256=snapshot or self.value.customer_evidence.snapshot_sha256)

    def assert_rejected(self, result, code=None):
        self.assertEqual(result.state, 'OFFLINE_ONLY')
        self.assertFalse(result.accepted)
        self.assertTrue(result.errors)
        self.assertFalse(result.semantic_approved)
        self.assertFalse(result.production_authorized)
        if code:
            self.assertIn(code, result.errors)

    def replace_annotation(self, **updates):
        annotation = replace(self.sidecar.explanations[0], **updates)
        sidecar = replace(self.sidecar, explanations=(annotation, *self.sidecar.explanations[1:]))
        # Raw dict is intentional: malformed sidecars must reach the integration codec.
        envelope = self.envelope()
        envelope['v3_sidecar'] = asdict(sidecar)
        envelope['sidecar_hash'] = text_digest(canonical_json(envelope['v3_sidecar']))
        return envelope

    def test_positive_complete_chain_pending_review_only(self):
        result = self.run_chain()
        self.assertEqual(result.state, 'PENDING_SEMANTIC_REVIEW')
        self.assertTrue(result.accepted)
        self.assertEqual(result.errors, ())
        self.assertFalse(result.semantic_approved)
        self.assertFalse(result.production_authorized)
        self.assertEqual(len(json.loads(self.raw)['draft']['sections']), 6)
        self.assertEqual(len(self.sidecar.explanations), 12)
        self.assertEqual([s.name for s in result.stages], [
            'selection', 'writer-projection', 'prompt-v3-material', 'synthetic-envelope',
            'v3-sidecar', 'native-parser', 'v3-contract-result', 'native-validation-result'])
        for stage in result.stages:
            self.assertIn(stage.state, {'OFFLINE_ONLY', 'PENDING_SEMANTIC_REVIEW'})
        native = json.loads(result.stages[-1].payload_json)
        self.assertEqual(native['state'], 'PENDING_SEMANTIC_REVIEW')
        self.assertEqual(native['errors'], [])
        self.assertEqual((native['sections'], native['claims'], native['blocks']), (6, 38, 20))

    def test_missing_v3_sidecar_rejected(self):
        envelope = self.envelope()
        del envelope['v3_sidecar']
        self.assert_rejected(self.run_chain(envelope), 'V3_EXPERIMENT_ENVELOPE_FIELDS')

    def test_unselected_fact_rejected(self):
        self.assert_rejected(self.run_chain(self.replace_annotation(selected_fact_refs=('E2.F02',))),
            'V3_FACT_NOT_SELECTED')

    def test_body_without_decision_rejected_even_with_updated_hashes(self):
        annotation = replace(self.sidecar.explanations[0],
            buyer_implication='Check the recorded limits before selecting equipment.')
        raw, sidecar = rebind(self.raw, self.sidecar, annotation)
        self.assert_rejected(self.run_chain(synthetic_envelope(raw, sidecar)), 'V3_DECISION_REALIZATION')

    def test_empty_verification_owner_rejected(self):
        self.assert_rejected(self.run_chain(self.replace_annotation(verification_owner='')),
            'V3_SIDECAR_INVALID')

    def test_unknown_presented_as_failure_rejected_even_with_visible_binding(self):
        annotation = replace(self.sidecar.explanations[0],
            boundary_condition='The untested fixture failed clearance.')
        annotation = replace(annotation, **render_parts(annotation, self.selection.sections[0]))
        raw, sidecar = rebind(self.raw, self.sidecar, annotation)
        self.assert_rejected(self.run_chain(synthetic_envelope(raw, sidecar)), 'V3_UNKNOWN_FALSE_DIAGNOSTIC')

    def test_sidecar_digest_and_context_hash_errors_rejected(self):
        envelope = self.envelope()
        envelope['sidecar_hash'] = '0' * 64
        self.assert_rejected(self.run_chain(envelope), 'V3_EXPERIMENT_SIDECAR_HASH')
        for key in ('selection_sha256', 'evidence_snapshot_sha256', 'plan_sha256', 'candidate_hash'):
            with self.subTest(key=key):
                envelope = self.envelope()
                envelope['v3_sidecar'][key] = '0' * 64
                envelope['sidecar_hash'] = text_digest(canonical_json(envelope['v3_sidecar']))
                self.assert_rejected(self.run_chain(envelope), 'V3_EXPERIMENT_CONTEXT_HASH')

    def test_modified_candidate_does_not_rebind_hash_automatically(self):
        envelope = self.envelope()
        envelope['candidate']['draft']['sections'][0]['blocks'][0]['claims'][0]['text'] += ' Changed.'
        self.assert_rejected(self.run_chain(envelope), 'V3_EXPERIMENT_CONTEXT_HASH')

    def test_original_v2_envelope_still_rejected_without_repairs(self):
        path = LIVE / 'model-output.json'
        original = path.read_bytes()
        self.assert_rejected(self.run_chain(raw=original.decode('utf-8')), 'V3_EXPERIMENT_ENVELOPE_FIELDS')
        original_check = replay_original()
        self.assertEqual(original_check['original_parser_error'], 'PREFLIGHT_RESPONSE_INVALID')
        self.assertEqual(path.read_bytes(), original)

    def test_frozen_v1_native_rejection_preserved(self):
        path = HISTORY / 'model-output.txt'
        original = path.read_bytes()
        self.assertEqual(text_digest(original.decode('utf-8')),
            '880c9ab66f4380fe34cabf6bf4aeacf8afe5b968049950931d0a6126f3bb2747')
        native = inspect_candidate_output(self.value, original.decode('utf-8'),
            current_snapshot_sha256=self.value.customer_evidence.snapshot_sha256)
        self.assertEqual(native.state, 'DETERMINISTICALLY_REJECTED')
        self.assertIn('CLAIM_BUDGET', native.errors)
        self.assert_rejected(self.run_chain(raw=original.decode('utf-8')))
        self.assertEqual(path.read_bytes(), original)

    def test_envelope_cannot_grant_either_authority(self):
        for flags in ({'semantic_approved': True}, {'production_authorized': True},
            {'semantic_approved': True, 'production_authorized': True},
            {'semantic_approved': 0}, {'production_authorized': 'false'}):
            with self.subTest(flags=flags):
                envelope = self.envelope()
                envelope.update(flags)
                self.assert_rejected(self.run_chain(envelope), 'V3_EXPERIMENT_AUTHORITY')

    def test_sidecar_cannot_add_approval_fields(self):
        for field in ('semantic_approved', 'production_authorized'):
            with self.subTest(field=field):
                envelope = self.envelope()
                envelope['v3_sidecar'][field] = True
                envelope['sidecar_hash'] = text_digest(canonical_json(envelope['v3_sidecar']))
                self.assert_rejected(self.run_chain(envelope), 'V3_SIDECAR_INVALID')

    def test_v2_projection_reused_unchanged_and_prompt_selected_only(self):
        before = canonical_json(asdict(self.value))
        result = self.run_chain()
        projection = json.loads(result.stages[1].payload_json)
        self.assertEqual(projection, build_offline_writer_material(self.selection, self.value,
            current_snapshot_sha256=self.value.customer_evidence.snapshot_sha256))
        prompt = json.loads(result.stages[2].payload_json)
        self.assertEqual(prompt['writer_projection'], projection)
        self.assertEqual(prompt['contract_version'], VERSION)
        self.assertFalse(prompt['semantic_approved'])
        self.assertFalse(prompt['production_authorized'])
        selected = {r for s in self.selection.sections for r in s.selected_facts}
        for source in self.value.customer_evidence.sources:
            self.assertNotIn(source.content, result.stages[2].payload_json)
            for fact in source.facts:
                if fact.fact_ref not in selected:
                    self.assertNotIn(fact.fact_ref, result.stages[2].payload_json)
                    self.assertNotIn(fact.quote, result.stages[2].payload_json)
        for reason in self.selection.fact_reasons:
            self.assertNotIn(reason.reason, result.stages[2].payload_json)
        self.assertEqual(canonical_json(asdict(self.value)), before)

    def test_native_schema_excludes_v3_fields(self):
        result = self.run_chain()
        candidate = json.loads(result.stages[5].payload_json)['candidate']
        self.assertEqual(set(candidate), {'draft'})
        for section in candidate['draft']['sections']:
            for block in section['blocks']:
                for claim in block.get('claims', block.get('items', [])):
                    for field in ('decision_object', 'boundary_type', 'verification_owner', 'verification_artifact'):
                        self.assertNotIn(field, claim)
        envelope = self.envelope()
        envelope['candidate']['draft']['sections'][0]['blocks'][0]['claims'][0]['decision_object'] = 'machine_shortlist'
        envelope['v3_sidecar']['candidate_hash'] = text_digest(canonical_json(envelope['candidate']))
        envelope['sidecar_hash'] = text_digest(canonical_json(envelope['v3_sidecar']))
        self.assert_rejected(self.run_chain(envelope), 'FIELD_CONTRACT')

    def test_native_validator_failure_not_hidden_by_v3_sidecar(self):
        envelope = self.envelope()
        envelope['candidate']['draft']['sections'][0]['blocks'][0]['claims'][0]['text'] = 'The machine is guaranteed suitable.'
        envelope['v3_sidecar']['candidate_hash'] = text_digest(canonical_json(envelope['candidate']))
        envelope['sidecar_hash'] = text_digest(canonical_json(envelope['v3_sidecar']))
        result = self.run_chain(envelope)
        self.assert_rejected(result)
        self.assertTrue(any(e.startswith('V3_NATIVE_') for e in result.errors), result.errors)
        self.assertIn('native-validation-result', [s.name for s in result.stages])

    def test_native_parser_and_validator_are_called(self):
        from foreign_trade_geo_agent.workflows import draft_contract_v3_experiment as module
        with patch.object(module, '_parse_specification', wraps=module._parse_specification) as parser, \
                patch.object(module, 'inspect_specification', wraps=module.inspect_specification) as validator:
            result = self.run_chain()
        self.assertTrue(result.accepted)
        parser.assert_called_once()
        validator.assert_called_once()

    def test_persisted_failure_diagnostics_drop_native_free_text_suffixes(self):
        from foreign_trade_geo_agent.workflows import draft_contract_v3_experiment as module
        from foreign_trade_geo_agent.core.draft_explanation_contract_v3 import ExplanationCheckV3
        native = inspect_candidate_output(self.value, self.raw,
            current_snapshot_sha256=self.value.customer_evidence.snapshot_sha256)
        native = replace(native, errors=('SECTION_FACT_OUTSIDE_QUESTION: SECRET_HEADING',
            'CL1: UNSUPPORTED_CLAIM: SECRET_DETAIL'))
        explanation = ExplanationCheckV3('FAIL', 'REJECTED',
            ('V3_NATIVE_SECTION_FACT_OUTSIDE_QUESTION__SECRET_HEADING',
             'V3_NATIVE_CL1__UNSUPPORTED_CLAIM__SECRET_DETAIL'), ())
        with patch.object(module, 'inspect_specification', return_value=native), \
                patch.object(module, 'inspect_explanations_v3', return_value=explanation):
            result = self.run_chain()
        self.assert_rejected(result, 'V3_EXPERIMENT_NATIVE_CL1_UNSUPPORTED_CLAIM')
        self.assertIn('V3_NATIVE_CL1_UNSUPPORTED_CLAIM', result.errors)
        self.assertNotIn('SECRET', canonical_json(asdict(result)))

    def test_bad_selection_and_stale_snapshot_fail_before_projection(self):
        for kwargs in ({'selection': replace(self.selection, plan_sha256='0'*64)}, {'snapshot': '0'*64}):
            with self.subTest(kwargs=kwargs):
                result = self.run_chain(**kwargs)
                self.assert_rejected(result)
                self.assertNotIn('writer-projection', [s.name for s in result.stages])

    def test_strict_envelope_unknown_duplicate_nonfinite_version_and_size_rejected(self):
        for raw in ('{"candidate":{},"candidate":{}}', '{"candidate":NaN}',
            ' ' * (MAX_ENVELOPE_BYTES + 1), '{broken provider secret'):
            with self.subTest(size=len(raw)):
                result = self.run_chain(raw=raw)
                self.assert_rejected(result)
                self.assertNotIn('provider secret', str(result.errors))
        for update in ({'contract_version': 'seo-draft-explanation-v2'}, {'extra': 'secret'}):
            envelope = self.envelope()
            envelope.update(update)
            self.assert_rejected(self.run_chain(envelope))

    def test_success_is_deterministic_and_stage_snapshots_are_independent(self):
        first, second = self.run_chain(), self.run_chain()
        self.assertEqual(first, second)
        material = json.loads(first.stages[1].payload_json)
        material['sections'][0]['selected_facts'].clear()
        self.assertEqual(first, second)

    def test_production_does_not_import_experimental_workflow(self):
        root = Path(__file__).resolve().parents[1] / 'src/foreign_trade_geo_agent'
        for path in root.rglob('*.py'):
            if path.name != 'draft_contract_v3_experiment.py':
                self.assertNotIn('draft_contract_v3_experiment', path.read_text(encoding='utf-8'), str(path))


class OfflineV3ArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1] / 'docs/seo-draft-contract-v3-integration/build_artifacts.py'
        spec = importlib.util.spec_from_file_location('offline_v3_artifact_driver', path)
        cls.driver = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.driver)

    def test_persisted_package_replays_full_chain_and_binds_stage_files(self):
        from foreign_trade_geo_agent.core.content_draft import ContentDraftInput
        from foreign_trade_geo_agent.storage.serialization import _decode
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            summary = self.driver.write_package(root)
            self.assertEqual(summary['state'], 'PENDING_SEMANTIC_REVIEW')
            data = json.loads((root / 'synthetic-input.json').read_bytes())
            value = _decode(data['native_input'], ContentDraftInput)
            selection = decode_selection_artifact(canonical_json(data['selection_artifact']))
            raw = (root / 'synthetic-output.json').read_text(encoding='utf-8')
            result = run_offline_v3_experiment(value, selection, raw,
                current_snapshot_sha256=data['current_snapshot_sha256'])
            self.assertTrue(result.accepted)
            for entry in json.loads((root / 'stage-index.json').read_bytes()):
                self.assertEqual(text_digest((root / entry['filename']).read_text(encoding='utf-8')), entry['sha256'])
            config = json.loads((root / 'experiment-config.json').read_bytes())
            self.assertEqual(config['candidate_hash'], text_digest((root / 'synthetic-candidate.json').read_text(encoding='utf-8')))
            self.assertFalse(config['semantic_approved'])
            self.assertFalse(config['production_authorized'])
            validation = json.loads((root / 'native-validation-result.json').read_bytes())
            self.assertEqual(validation['state'], 'PENDING_SEMANTIC_REVIEW')
            self.assertEqual(validation['errors'], [])

    def test_create_only_package_verifies_identical_and_rejects_tampered_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.driver.write_package(root)
            before = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}
            self.driver.write_package(root)
            self.assertEqual(before, {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()})
            (root / 'v3-sidecar.json').write_text('tampered', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'OFFLINE_V3_EXISTING_ARTIFACT_CHANGED'):
                self.driver.write_package(root)
            self.assertEqual((root / 'v3-sidecar.json').read_text(encoding='utf-8'), 'tampered')
            self.assertEqual((root / 'synthetic-output.json').read_bytes(), before['synthetic-output.json'])


if __name__ == '__main__':
    unittest.main()
