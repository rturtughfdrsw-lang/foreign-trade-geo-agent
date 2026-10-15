"""Offline real failure replay and explicitly synthetic model-wire regressions."""
from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path
import tempfile
import unittest

from foreign_trade_geo_agent.core.draft_selection_contract import canonical_json, text_digest
from foreign_trade_geo_agent.workflows import draft_contract_v3_experiment as v3
from tests.draft_explanation_v3_fixtures import fixture_v3
from tests.test_seo_draft_v3_request_freeze import (
    ROOT, DEST, PACKAGE_NAMES, read_sources, source_context, verify_package, sha,
)


class V3RealRepairTests(unittest.TestCase):
    def setUp(self):
        self.value, self.selection, self.raw, self.sidecar = fixture_v3()

    def wire(self):
        side = json.loads(canonical_json(asdict(self.sidecar)))
        side['candidate_hash'] = None
        for a in side['explanations']:
            a['text_sha256'] = None
        return dict(contract_version=v3.VERSION, candidate=json.loads(self.raw),
            v3_sidecar=side, sidecar_hash=None, semantic_approved=False, production_authorized=False)

    def assemble(self, body):
        self.assertTrue(hasattr(v3, 'assemble_model_v3_output'), 'Missing deterministic model-wire hash boundary')
        return v3.assemble_model_v3_output(self.value, self.selection, canonical_json(body),
            current_snapshot_sha256=self.selection.evidence_snapshot_sha256)

    def test_synthetic_null_hashes_assemble_and_full_chain_pending_only(self):
        body = self.wire()
        before = deepcopy(body)
        result = self.assemble(body)
        self.assertEqual(body, before)
        complete = json.loads(result)
        self.assertEqual(complete['candidate'], body['candidate'])
        self.assertEqual(complete['v3_sidecar']['candidate_hash'], text_digest(self.raw))
        for a, old in zip(complete['v3_sidecar']['explanations'], body['v3_sidecar']['explanations']):
            self.assertEqual({k: v for k, v in a.items() if k != 'text_sha256'},
                             {k: v for k, v in old.items() if k != 'text_sha256'})
        result = v3.run_offline_v3_experiment(self.value, self.selection, result,
            current_snapshot_sha256=self.selection.evidence_snapshot_sha256)
        self.assertTrue(result.accepted, result.errors)
        self.assertFalse(result.semantic_approved)
        self.assertFalse(result.production_authorized)

    def test_wrong_or_precomputed_hashes_are_not_repaired(self):
        for invalid in ('', '0'*64, False, 0):
            for location in ('sidecar', 'candidate', 'text'):
                with self.subTest(value=invalid, location=location):
                    b = self.wire()
                    if location == 'sidecar': b['sidecar_hash'] = invalid
                    elif location == 'candidate': b['v3_sidecar']['candidate_hash'] = invalid
                    else: b['v3_sidecar']['explanations'][0]['text_sha256'] = invalid
                    with self.assertRaisesRegex(ValueError, 'MODEL_HASH_PLACEHOLDER'):
                        self.assemble(b)

    def test_semantic_and_native_defects_still_reject(self):
        mutations = {
            'extra_type': lambda b: b.update(type='json_object'),
            'decision_object': lambda b: b['v3_sidecar']['explanations'][0].update(decision_object={'label': 'machine shortlist'}),
            'next_decision': lambda b: b['v3_sidecar']['explanations'][0]['verification'].update(next_decision={'label': 'machine shortlist'}),
            'recipient': lambda b: b['v3_sidecar']['explanations'][0]['verification'].update(recipient='buyer and supplier'),
            'empty_hash_missing': lambda b: b['v3_sidecar']['explanations'][0].pop('text_sha256'),
            'quote': lambda b: b['v3_sidecar']['explanations'][0]['evidence_reference'][0].update(source_quote='Invented evidence.'),
            'selected_refs': lambda b: b['v3_sidecar']['explanations'][0].update(selected_fact_refs=['E999.F01']),
            'binding': lambda b: b['v3_sidecar']['explanations'][0].update(claim_id='CL99'),
            'duplicate': lambda b: b['v3_sidecar']['explanations'].append(deepcopy(b['v3_sidecar']['explanations'][0])),
            'boundary': lambda b: b['v3_sidecar']['explanations'][0].update(non_applicability='Unresolved.'),
            'context': lambda b: b['v3_sidecar'].update(plan_sha256='0'*64),
            'authority': lambda b: b.update(semantic_approved=True),
            'production': lambda b: b.update(production_authorized=0),
            'native_id': lambda b: b['candidate']['draft']['sections'][0]['blocks'][0]['claims'][0].update(claim_id='CL1'),
            'source_namespace': lambda b: b['candidate']['draft']['sections'][0]['blocks'][0]['claims'][0].update(source_refs=['E2']),
            'missing_direct': lambda b: b['candidate']['draft']['sections'][0]['blocks'].pop(0),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                b = self.wire(); mutate(b)
                with self.assertRaises(ValueError): self.assemble(b)
        b = self.wire()
        for s in b['candidate']['draft']['sections']:
            for block in s['blocks']:
                for c in block.get('claims', block.get('items', [])):
                    c.pop('proposal', None)
        with self.assertRaises(ValueError): self.assemble(b)

    def test_prompt_native_example_is_parseable_and_selected_boundary_preserved(self):
        from foreign_trade_geo_agent.workflows.draft_contract_v2 import build_offline_writer_material
        from foreign_trade_geo_agent.workflows.content_draft import _parse_specification
        from tests.test_seo_draft_v3_request_freeze import check_boundary
        self.assertTrue(hasattr(v3, 'build_model_prompt_v3_material'), 'Missing explicit native wire schema')
        projection = build_offline_writer_material(self.selection, self.value,
            current_snapshot_sha256=self.selection.evidence_snapshot_sha256)
        prompt = v3.build_model_prompt_v3_material(projection)
        check_boundary(prompt, prompt['writer_projection'], self.selection, self.value)
        example = prompt['response_contract']['native_shape_example']
        op = self.value.change_plan_report.operations[0]
        spec = _parse_specification(canonical_json(example), expected_change_ref=op.change_id, operation=op)
        self.assertIsNotNone(spec.sections[0].blocks[0].claims[0].proposal)

    def test_original_real_bytes_remain_rejected_without_mutation(self):
        p = ROOT / DEST / 'real-v3-experiment-2026-10-13/model-output.txt'
        before = p.read_bytes()
        self.assertEqual(sha(before), 'a456ea3f966233e51d06e815796d0427b4391a0f9ba21b0fbbfc22e5179133b4')
        with self.assertRaisesRegex(ValueError, 'V3_EXPERIMENT_ENVELOPE_FIELDS'):
            v3._envelope(before.decode())
        with self.assertRaises(ValueError): self.assemble(json.loads(before))
        self.assertEqual(p.read_bytes(), before)

    def test_real_numeric_paraphrase_cannot_be_hidden_by_hash_assembly(self):
        original = json.loads((ROOT / DEST / 'real-v3-experiment-2026-10-13/model-output.txt').read_bytes())
        b = self.wire()
        first = next(c for block in b['candidate']['draft']['sections'][0]['blocks']
            for c in block.get('claims', block.get('items', [])) if c['claim_type'] == 'EVIDENCE_BASED_INTERPRETATION')
        first['text'] = original['candidate']['draft']['sections'][0]['claims'][0]['text']
        with self.assertRaisesRegex(ValueError, 'NUMERIC_CONTEXT_NOT_PRESERVED'):
            self.assemble(b)

    def test_stale_context_and_invalid_json_do_not_reach_assembly(self):
        self.assertTrue(hasattr(v3, 'assemble_model_v3_output'))
        for raw, snapshot in [(canonical_json(self.wire()), '0'*64),
                              ('{"candidate":{},"candidate":{}}', self.selection.evidence_snapshot_sha256),
                              ('{"candidate":NaN}', self.selection.evidence_snapshot_sha256)]:
            with self.subTest(raw=raw[:30]), self.assertRaises(ValueError):
                v3.assemble_model_v3_output(self.value, self.selection, raw,
                    current_snapshot_sha256=snapshot)

    def test_isolated_diagnosis_enumerates_masked_failures(self):
        from scripts.diagnose_v3_real_output import diagnose
        r = diagnose()
        self.assertEqual(r['isolated_layer2']['error'], 'UNKNOWN_CHANGE_REFERENCE')
        self.assertEqual(r['isolated_layer3_codec']['result'], 'FAIL')
        self.assertEqual(len(r['explanations']), 19)
        self.assertEqual(r['counts']['HASH_MISMATCH'], 21)
        self.assertEqual(r['counts']['ENUM_STRING_REQUIRED'], 50)
        self.assertEqual(r['counts']['NUMERIC_CONTEXT_NOT_PRESERVED_IF_PROPOSAL_PRESENT'], 13)
        self.assertTrue(all(a['exact_quotes'] and a['refs_match'] for a in r['explanations']))

    def test_strict_package_rejects_nested_results_but_external_results_do_not_conflict(self):
        sources = read_sources()
        with tempfile.TemporaryDirectory() as tmp:
            frozen = Path(tmp) / 'frozen'; frozen.mkdir()
            for name in PACKAGE_NAMES:
                (frozen / name).write_bytes((ROOT / DEST / name).read_bytes())
            anchor = sha((frozen / 'manifest.json').read_bytes())
            self.assertTrue(verify_package(frozen, anchor, sources)['valid'])
            (Path(tmp) / 'results').mkdir()
            self.assertTrue(verify_package(frozen, anchor, sources)['valid'])
            (frozen / 'results').mkdir()
            with self.assertRaisesRegex(ValueError, 'PACKAGE_FILE_SET'):
                verify_package(frozen, anchor, sources)


if __name__ == '__main__':
    unittest.main()
