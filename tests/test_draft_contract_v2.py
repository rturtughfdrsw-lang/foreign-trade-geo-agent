from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from foreign_trade_geo_agent.core.content_draft import build_content_draft_prompt
from foreign_trade_geo_agent.storage.draft_selection_contract import (
    encode_selection_artifact, decode_selection_artifact, write_selection_artifact,
)
from foreign_trade_geo_agent.workflows.draft_contract_v2 import build_offline_writer_material
from tests.draft_v2_fixtures import fixture, explanation_fixture, DESIGN, HISTORY, change_section
from foreign_trade_geo_agent.core.draft_selection_contract import text_digest, selection_digest
from foreign_trade_geo_agent.workflows.draft_contract_v2 import inspect_offline_candidate
from foreign_trade_geo_agent.workflows.content_draft import inspect_candidate_output


class ArtifactAndProjectionTests(unittest.TestCase):
    def setUp(self):
        self.value, self.contract = fixture()

    def view(self, contract=None):
        return build_offline_writer_material(contract or self.contract, self.value,
            current_snapshot_sha256=self.value.customer_evidence.snapshot_sha256)

    def test_artifact_round_trip(self):
        raw = encode_selection_artifact(self.contract)
        self.assertEqual(decode_selection_artifact(raw), self.contract)
        self.assertEqual(encode_selection_artifact(decode_selection_artifact(raw)), raw)
        artifact = json.loads(raw)
        self.assertEqual(artifact['payload_version'], 2)
        self.assertEqual(artifact['payload']['plan_sha256'], self.contract.plan_sha256)
        self.assertEqual(len(artifact['payload']['fact_reasons']), 43)

    def test_artifact_rejects_duplicates_unknown_fields_versions_and_hash_tampering(self):
        original = json.loads(encode_selection_artifact(self.contract))
        for mutate in (lambda a: a.update(payload_version=1), lambda a: a.update(extra='secret'),
                       lambda a: a['payload'].update(plan_sha256='0'*64),
                       lambda a: a.update(payload_version=True),
                       lambda a: a['payload']['sections'][0].update(claim_budget=True)):
            artifact = json.loads(json.dumps(original))
            mutate(artifact)
            with self.subTest(artifact=artifact.keys()), self.assertRaises(ValueError):
                decode_selection_artifact(json.dumps(artifact))
        with self.assertRaises(ValueError):
            decode_selection_artifact('{"payload_version":2,"payload_version":2}')
        with self.assertRaises(ValueError):
            decode_selection_artifact(' ' * 300000)

    def test_append_only_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'selection.json'
            write_selection_artifact(path, self.contract)
            raw = path.read_bytes()
            with self.assertRaises(FileExistsError):
                write_selection_artifact(path, self.contract)
            self.assertEqual(path.read_bytes(), raw)
            self.assertEqual(decode_selection_artifact(raw.decode()), self.contract)

    def test_projection_has_exact_selected_only_provenance(self):
        material = self.view()
        selected = {r for s in self.contract.sections for r in s.selected_facts}
        projected = {f['fact_ref']: f for s in material['sections'] for f in s['selected_facts']}
        self.assertEqual(set(projected), selected)
        raw = json.dumps(material)
        for source in self.value.customer_evidence.sources:
            for fact in source.facts:
                if fact.fact_ref in selected:
                    item = projected[fact.fact_ref]
                    self.assertEqual(item['quote'], fact.quote)
                    self.assertEqual(item['source'], source.evidence_id)
                    self.assertEqual(item['version'], source.evidence_version)
                    self.assertEqual(item['location'], dict(locator=source.source_locator, start=fact.start, end=fact.end))
                    self.assertEqual(item['source_sha256'], source.content_sha256)
                else:
                    self.assertNotIn(fact.fact_ref, raw)
                    self.assertNotIn(fact.quote, raw)
        self.assertNotIn('fact_reasons', raw)
        for reason in self.contract.fact_reasons:
            self.assertNotIn(reason.reason, raw)
        self.assertNotIn('customer_evidence', material)
        for s, view in zip(self.contract.sections, material['sections']):
            self.assertEqual(view['required_limitation'], s.required_limitation)

    def test_projection_preserves_ps_and_v1_material_unchanged(self):
        prompt = build_content_draft_prompt(self.value, 'C1')
        before = prompt.material_json()
        material = self.view()
        old = json.loads(before)
        for key in ('pages', 'sources', 'change', 'opportunity', 'writing_brief'):
            self.assertEqual(material[key], old[key])
        self.assertEqual(material['validator_contract']['claim_budget'], old['contract']['claim_budget'])
        self.assertEqual(prompt.material_json(), before)
        material['sections'][0]['selected_facts'].clear()
        self.assertTrue(self.view()['sections'][0]['selected_facts'])

    def test_projection_fails_before_exposing_stale_material(self):
        with self.assertRaisesRegex(ValueError, 'PLAN_HASH'):
            self.view(replace(self.contract, plan_sha256='0'*64))


class OfflineReplayTests(unittest.TestCase):
    def setUp(self):
        self.value, self.contract = fixture()
        self.raw, self.sidecar = explanation_fixture(self.contract)

    def check(self, response=None, contract=None, sidecar=None):
        raw = self.raw if response is None else json.dumps(response)
        sidecar = sidecar or replace(self.sidecar, candidate_sha256=text_digest(raw))
        return inspect_offline_candidate(self.value, raw, contract or self.contract, sidecar,
            current_snapshot_sha256=self.value.customer_evidence.snapshot_sha256)

    def test_v2_mock_38_claims_20_blocks_pending_only(self):
        result = self.check()
        self.assertEqual((result.claims, result.blocks), (38, 20))
        self.assertTrue(result.selection_valid and result.routing_valid and result.explanation_structure_valid)
        self.assertEqual(result.state, 'PENDING_SEMANTIC_REVIEW')
        self.assertEqual(result.errors, ())
        self.assertEqual(result.budget_diagnostics, ())
        self.assertFalse(result.production_authorized)

    def test_frozen_v1_bytes_and_original_rejections_preserved(self):
        raw = (HISTORY / 'model-output.txt').read_bytes().decode('utf-8')
        self.assertEqual(text_digest(raw), '880c9ab66f4380fe34cabf6bf4aeacf8afe5b968049950931d0a6126f3bb2747')
        native = inspect_candidate_output(self.value, raw,
            current_snapshot_sha256=self.value.customer_evidence.snapshot_sha256)
        result = inspect_offline_candidate(self.value, raw, self.contract, self.sidecar,
            current_snapshot_sha256=self.value.customer_evidence.snapshot_sha256)
        self.assertEqual(native.state, 'DETERMINISTICALLY_REJECTED')
        self.assertEqual(result.state, native.state)
        self.assertIn('CLAIM_BUDGET', native.errors)
        self.assertTrue(set(native.errors) <= set(result.errors))
        self.assertTrue(any('SECTION_' in e for e in native.errors))
        self.assertEqual(result.claims, 50)

    def test_49_actual_claims_rejected(self):
        body = json.loads(self.raw)
        remaining = 11
        for section in body['draft']['sections']:
            for block in section['blocks']:
                while len(block['claims']) < 4 and remaining:
                    block['claims'].append(dict(block['claims'][0]))
                    remaining -= 1
        self.assertEqual(remaining, 0)
        check = self.check(body)
        self.assertEqual(check.claims, 49)
        self.assertIn('CLAIM_BUDGET', check.errors)
        self.assertEqual(check.state, 'DETERMINISTICALLY_REJECTED')

    def test_25_actual_blocks_rejected(self):
        body = json.loads(self.raw)
        block = body['draft']['sections'][0]['blocks'][-1]
        body['draft']['sections'][0]['blocks'].extend([block] * 5)
        check = self.check(body)
        self.assertEqual(check.blocks, 25)
        self.assertIn('BLOCK_BUDGET', check.errors)

    def test_unknown_fact_rejected(self):
        body = json.loads(self.raw)
        body['draft']['sections'][0]['blocks'][0]['claims'][0]['customer_refs'] = ['E9.F99']
        self.assertIn('OFFLINE_FACT_NOT_SELECTED', self.check(body).errors)

    def test_required_fact_and_required_direct_usage_rejected(self):
        body = json.loads(self.raw)
        body['draft']['sections'][0]['blocks'][0]['claims'].pop(0)
        # Explanation still cites the fact: required_direct must independently fail.
        self.assertIn('OFFLINE_REQUIRED_FACT_COVERAGE', self.check(body).errors)

    def test_cross_section_source_rejected(self):
        body = json.loads(self.raw)
        body['draft']['sections'][1]['blocks'][0]['claims'][0]['customer_refs'] = ['E5.F03']
        result = self.check(body)
        self.assertIn('OFFLINE_SECTION_SOURCE_EQUALITY', result.errors)
        self.assertFalse(result.routing_valid)

    def test_explanation_unselected_reference_in_candidate_rejected(self):
        body = json.loads(self.raw)
        body['draft']['sections'][0]['blocks'][2]['claims'][0]['customer_refs'].append('E2.F02')
        result = self.check(body)
        self.assertIn('OFFLINE_FACT_NOT_SELECTED', result.errors)
        self.assertIn('EXPLANATION_PREMISE_BINDING', result.errors)

    def test_invalid_selection_never_reaches_native_parser(self):
        from unittest.mock import patch
        with patch('foreign_trade_geo_agent.workflows.draft_contract_v2._parse_specification') as parser:
            check = self.check(contract=replace(self.contract, plan_sha256='0'*64))
            parser.assert_not_called()
        self.assertFalse(check.selection_valid)
        self.assertEqual(check.state, 'DETERMINISTICALLY_REJECTED')

    def test_candidate_hash_mismatch(self):
        self.assertIn('EXPLANATION_HASH_BINDING', self.check(
            sidecar=replace(self.sidecar, candidate_sha256='0'*64)).errors)

    def test_malformed_and_oversized_candidates_fail_closed(self):
        for raw in ('not JSON', '{}', ' ' * 64001, '\ud800'):
            result = inspect_offline_candidate(self.value, raw, self.contract, self.sidecar,
                current_snapshot_sha256=self.value.customer_evidence.snapshot_sha256)
            self.assertEqual(result.state, 'DETERMINISTICALLY_REJECTED')
            self.assertFalse(result.production_authorized)

    def test_invalid_container_types_and_deep_json_fail_closed(self):
        bodies = []
        for value in (None, 123, True):
            body = json.loads(self.raw)
            body['draft']['sections'] = value
            bodies.append(json.dumps(body))
            body = json.loads(self.raw)
            body['draft']['sections'][0]['blocks'] = value
            bodies.append(json.dumps(body))
        bodies.append('[' * 2000 + '0' + ']' * 2000)
        for raw in bodies:
            with self.subTest(raw=raw[:50]):
                result = inspect_offline_candidate(self.value, raw, self.contract, self.sidecar,
                    current_snapshot_sha256=self.value.customer_evidence.snapshot_sha256)
                self.assertEqual(result.state, 'DETERMINISTICALLY_REJECTED')
                self.assertTrue(set(result.errors) <= {'OFFLINE_CONTRACT_INVALID', 'JSON_FORMAT', 'FIELD_CONTRACT'})

    def test_original_numeric_validator_cannot_be_bypassed(self):
        body = json.loads(self.raw)
        claim = body['draft']['sections'][0]['blocks'][0]['claims'][0]
        claim['text'] += ' Guaranteed output 999999 units.'
        self.assertEqual(self.check(body).state, 'DETERMINISTICALLY_REJECTED')

    def test_soft_cta_target_does_not_reject_two_ctas(self):
        body = json.loads(self.raw)
        block = body['draft']['sections'][-1]['blocks'][-1]
        cta = dict(block['claims'][-1])
        cta['text'] = 'Share your drawing for review.'
        block['claims'].append(cta)
        contract = change_section(self.contract, 5, cta_budget=2, claim_budget=11)
        raw = json.dumps(body)
        sidecar = replace(self.sidecar, candidate_sha256=text_digest(raw), selection_sha256=selection_digest(contract))
        result = self.check(body, contract, sidecar)
        self.assertEqual(result.errors, ())
        self.assertEqual(result.state, 'PENDING_SEMANTIC_REVIEW')
        self.assertIn('SOFT_CTA_NOT_ONE', result.budget_diagnostics)

    def test_soft_explanation_target_does_not_reject_eleven(self):
        body = json.loads(self.raw)
        body['draft']['sections'][0]['blocks'].pop(-1)
        contract = change_section(self.contract, explanation_budget=1)
        annotations = {a.text_sha256: a for a in self.sidecar.explanations}
        items, number = [], 0
        for si, section in enumerate(body['draft']['sections'], 1):
            for block in section['blocks']:
                for claim in block['claims']:
                    number += 1
                    if claim['claim_type'] == 'EVIDENCE_BASED_INTERPRETATION':
                        items.append(replace(annotations[text_digest(claim['text'])], explanation_claim_id=f'CL{number}'))
        sidecar = replace(self.sidecar, candidate_sha256=text_digest(json.dumps(body)),
            selection_sha256=selection_digest(contract), explanations=tuple(items))
        result = self.check(body, contract, sidecar)
        self.assertEqual(result.errors, ())
        self.assertEqual(result.state, 'PENDING_SEMANTIC_REVIEW')
        self.assertIn('SOFT_EXPLANATIONS_UNDER_12', result.budget_diagnostics)
