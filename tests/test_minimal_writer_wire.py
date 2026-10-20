"""Offline acceptance and adversarial binding checks. No semantic certification."""
from copy import deepcopy
from dataclasses import asdict, replace
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from foreign_trade_geo_agent.core import minimal_writer_wire as mw
from foreign_trade_geo_agent.adapters.minimal_writer_wire import build_request_material
from foreign_trade_geo_agent.core.draft_selection_contract import canonical_json, text_digest, evidence_digest
from foreign_trade_geo_agent.workflows import minimal_writer_experiment as experiment
from tests.minimal_writer_fixtures import cnc_fixture, industry_fixture

ROOT = Path(__file__).resolve().parents[1]


class MinimalWriterTests(unittest.TestCase):
    def setUp(self):
        self.value, self.selection, self.manifest, self.wire = cnc_fixture()
        self.body = json.loads(self.wire)
        self.snapshot = self.selection.evidence_snapshot_sha256

    def run_body(self, body=None, **kwargs):
        return experiment.run_minimal_experiment(kwargs.get('value', self.value),
            kwargs.get('selection', self.selection), kwargs.get('manifest', self.manifest),
            self.wire if body is None else canonical_json(body),
            current_snapshot_sha256=kwargs.get('snapshot', self.snapshot))

    def assert_failed(self, body, code):
        result = self.run_body(body)
        self.assertFalse(result.ready_for_review)
        self.assertIn(code, result.errors)
        self.assertEqual(result.native_parser, 'NOT_RUN')
        return result

    def test_six_sections_twelve_independent_authored_slots_25_facts(self):
        result = self.run_body()
        self.assertTrue(result.ready_for_review, result.errors)
        self.assertEqual((result.minimal_wire, result.native_parser, result.native_validator), ('PASS',)*3)
        body = json.loads(result.candidate_json)
        side = mw.decode_bindings(result.bindings_json)
        self.assertEqual(len(body['draft']['sections']), 6)
        self.assertEqual(len(side.bindings), 38)
        self.assertEqual(sum(len(s['blocks']) for s in body['draft']['sections']), 13)
        self.assertEqual(sum(b.kind == 'direct_fact' for b in side.bindings), 25)
        self.assertEqual(sum(b.kind == 'explanation' for b in side.bindings), 12)
        self.assertEqual(len({s.decision_goal for s in self.manifest.slots if s.kind == 'explanation'}), 12)
        self.assertEqual(result.semantic_review, 'PENDING')
        self.assertFalse(result.semantic_approved)
        self.assertFalse(result.production_authorized)
        self.assertEqual(self.manifest.origin, mw.TEST_ORIGIN)

    def test_missing_slot(self):
        self.body['slots'].pop()
        self.assert_failed(self.body, 'MW_REQUIRED_SLOT_SET')

    def test_duplicate_slot(self):
        self.body['slots'].append(deepcopy(self.body['slots'][0]))
        self.assert_failed(self.body, 'MW_DUPLICATE_SLOT')

    def test_extra_slot(self):
        a = deepcopy(self.body['slots'][0]); a['slot_id'] = 'S9-E1'
        self.body['slots'].append(a)
        self.assert_failed(self.body, 'MW_REQUIRED_SLOT_SET')

    def test_unknown_slot(self):
        self.body['slots'][0]['slot_id'] = 'S1-E9'
        self.assert_failed(self.body, 'MW_REQUIRED_SLOT_SET')

    def test_cross_task_request_id(self):
        self.body['request_id'] = 'MW-'+'0'*64
        self.assert_failed(self.body, 'MW_REQUEST_BINDING')

    def test_unselected_fact_ref(self):
        self.body['slots'][0]['premise_refs'] = ['E2.F02']
        self.assert_failed(self.body, 'MW_PREMISE_OUTSIDE_SLOT')

    def test_cross_section_reference(self):
        self.body['slots'][0]['premise_refs'] = ['E7.F01']
        self.assert_failed(self.body, 'MW_PREMISE_OUTSIDE_SLOT')

    def test_extra_semantic_approval_is_rejected(self):
        for location in ('envelope', 'slot'):
            with self.subTest(location=location):
                body = deepcopy(self.body)
                (body if location == 'envelope' else body['slots'][0])['semantic_approved'] = True
                self.assert_failed(body, 'MW_EXACT_FIELDS')

    def test_native_claim_id_hash_source_quote_and_slot_kind_are_not_model_fields(self):
        for field in ('claim_id', 'hash', 'source_quote', 'kind', 'production_authorized', 'proposal', 'v3_sidecar'):
            with self.subTest(field=field):
                b = deepcopy(self.body); b['slots'][0][field] = 'forbidden'
                self.assert_failed(b, 'MW_EXACT_FIELDS')

    def test_illegal_types(self):
        for field, bad in [('status', True), ('status', {}), ('premise_refs', 'E5.F01'),
                           ('premise_refs', [True]), ('buyer_implication', 7), ('assumptions', None)]:
            with self.subTest(field=field, value=bad):
                b = deepcopy(self.body); b['slots'][0][field] = bad
                self.assertFalse(self.run_body(b).ready_for_review)

    def test_duplicate_premise_and_empty_premise(self):
        for refs in ([], ['E5.F01', 'E5.F01']):
            b = deepcopy(self.body); b['slots'][0]['premise_refs'] = refs
            self.assertFalse(self.run_body(b).ready_for_review)

    def test_duplicate_json_keys_and_constants(self):
        for raw in ('{"request_id":"x","request_id":"y","slots":[]}', '{"slots":NaN}', '{', '[]'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                mw.decode_wire(raw)

    def test_total_wire_budget(self):
        with self.assertRaisesRegex(ValueError, 'MW_RAW_BUDGET'):
            mw.decode_wire(' '*(mw.MAX_WIRE_BYTES+1))

    def test_field_budget(self):
        self.body['slots'][0]['buyer_implication'] = 'x'*301
        self.assert_failed(self.body, 'MW_ANSWER_FIELDS')

    def test_manifest_text_budget(self):
        slots = tuple(replace(s, budget=50) if s.slot_id == 'S1-E1' else s for s in self.manifest.slots)
        manifest = replace(self.manifest, slots=slots)
        self.body['request_id'] = mw.request_id(manifest)
        result = self.run_body(self.body, manifest=manifest)
        self.assertIn('MW_TEXT_BUDGET', result.errors)

    def test_refusal_is_not_completed_or_filled(self):
        self.body['slots'][0] = dict(slot_id='S1-E1', status='insufficient_evidence',
                                    missing_information='The intended fixture layout is unavailable.')
        result = self.assert_failed(self.body, 'MW_INSUFFICIENT_EVIDENCE')
        self.assertEqual(result.refused_slots, ('S1-E1',))
        self.assertEqual(result.candidate_json, '')
        self.assertEqual(mw.encode_wire(mw.decode_wire(canonical_json(self.body))), canonical_json(self.body))

    def test_refusal_cannot_hide_answer_or_approval(self):
        self.body['slots'][0] = dict(slot_id='S1-E1', status='insufficient_evidence',
                                    missing_information='Missing.', buyer_implication='Pretend completed.')
        self.assert_failed(self.body, 'MW_EXACT_FIELDS')

    def test_same_text_and_assumptions_in_body_binding_and_review(self):
        result = self.run_body()
        side = mw.decode_bindings(result.bindings_json)
        claims = [c for s in json.loads(result.candidate_json)['draft']['sections']
                  for b in s['blocks'] for c in b['claims']]
        self.assertEqual([b.text for b in side.bindings], [c['text'] for c in claims])
        review = experiment.render_review(result)
        for b in side.bindings:
            self.assertEqual(b.text_sha256, text_digest(b.text))
            self.assertIn(b.text, review)
        for c in claims:
            if 'proposal' in c:
                self.assertIn(c['proposal']['assumptions'], c['text'])
                self.assertEqual(c['proposal']['reasoning'], self.body['slots'][
                    [s['slot_id'] for s in self.body['slots']].index(next(b.slot_id for b in side.bindings if b.text == c['text']))]['buyer_implication'])

    def test_source_quote_versions_hashes_offsets_exact(self):
        result = self.run_body()
        bank = {f.fact_ref: (s, f) for s in self.value.customer_evidence.sources for f in s.facts}
        for b in mw.decode_bindings(result.bindings_json).bindings:
            for q in b.evidence:
                s, f = bank[q.fact_ref]
                self.assertEqual(q.source_quote, s.content[q.start:q.end])
                self.assertEqual(q.source_quote, f.quote)
                self.assertEqual(q.content_sha256, text_digest(s.content))
                self.assertEqual(q.source_version, s.evidence_version)

    def test_manifest_codec_freezes_exact_authored_content(self):
        self.assertEqual(mw.decode_manifest(mw.encode_manifest(self.manifest)), self.manifest)
        body = json.loads(mw.encode_manifest(self.manifest))
        body['slots'][0]['semantic_approved'] = True
        with self.assertRaisesRegex(ValueError, 'MW_EXACT_FIELDS'):
            mw.decode_manifest(canonical_json(body))

    def test_actual_premises_must_cover_selected_assignments(self):
        self.body['slots'][7]['premise_refs'] = ['E3.F05']
        self.assert_failed(self.body, 'MW_ACTUAL_SELECTED_COVERAGE')

    def test_duplicate_interpretation_text_is_native_rejected(self):
        for field in ('buyer_implication', 'assumptions'):
            self.body['slots'][1][field] = self.body['slots'][0][field]
        result = self.run_body(self.body)
        self.assertEqual(result.native_validator, 'FAIL')
        self.assertIn('DUPLICATE_CLAIM', ' '.join(result.errors))

    def test_manifest_missing_explanation_cannot_use_native_lower_minimum(self):
        slots = [s for s in self.manifest.slots if s.slot_id != 'S1-E2']
        result = self.run_body(manifest=replace(self.manifest, slots=tuple(slots)))
        self.assertIn('MW_SECTION_BUDGET', result.errors)

    def test_binding_hash_and_text_hash_edit_are_rejected(self):
        r = self.run_body()
        with self.assertRaisesRegex(ValueError, 'MW_SIDECAR_HASH'):
            experiment.verify_assembled(self.value,self.selection,self.manifest,self.wire,r.candidate_json,r.bindings_json,
                '0'*64,current_snapshot_sha256=self.snapshot)
        body = json.loads(r.bindings_json); body['bindings'][0]['text'] += ' edited'
        with self.assertRaisesRegex(ValueError, 'MW_BINDING_FIELDS'):
            mw.decode_bindings(canonical_json(body))

    def test_direct_facts_display_once_across_sections(self):
        side = mw.decode_bindings(self.run_body().bindings_json)
        direct = [b.evidence[0].fact_ref for b in side.bindings if b.kind == 'direct_fact']
        self.assertEqual(len(direct), len(set(direct)))
        self.assertEqual(direct.count('E4.F01'), 1)
        self.assertTrue(any(b.section_id == 'S4' and b.kind == 'explanation'
                            and any(q.fact_ref == 'E4.F01' for q in b.evidence) for b in side.bindings))

    def test_duplicate_direct_manifest_is_rejected(self):
        slots = list(self.manifest.slots)
        target = next(i for i,s in enumerate(slots) if s.section_id == 'S4' and s.kind == 'direct_fact')
        slots[target] = replace(slots[target], allowed_fact_refs=('E4.F01',))
        result = self.run_body(manifest=replace(self.manifest, slots=tuple(slots)))
        self.assertIn('MW_DIRECT_SET', result.errors)

    def test_known_suitability_overstatement_is_rejected_without_appending_boundary(self):
        self.body['slots'][0]['buyer_implication'] = 'NCX10 fits the complete fixture and is suitable for machining.'
        self.assert_failed(self.body, 'MW_KNOWN_PLAN_CONFLICT')

    def test_limitation_and_action_conflict(self):
        for field in ('boundary_condition', 'verification_action'):
            b = deepcopy(self.body); b['slots'][0][field] = 'Skip the required review.'
            self.assert_failed(b, 'MW_PLAN_BOUNDARY_CONFLICT')

    def test_hidden_semantic_error_is_pending_not_certified(self):
        # Allowed quote != semantic proof: deliberately weak/unrelated conclusion evades known phrases.
        self.body['slots'][0]['buyer_implication'] = 'The fixture note establishes compatibility for the intended production process.'
        result = self.run_body(self.body)
        self.assertTrue(result.ready_for_review, result.errors)
        self.assertEqual(result.semantic_review, 'PENDING')
        self.assertFalse(result.semantic_approved)
        self.assertIn('human', ' '.join(result.review_risks))
        self.assertIn('Source comparison', experiment.render_review(result))

    def test_numeric_context_error_is_original_native_error(self):
        self.body['slots'][0]['premise_refs'] = ['E2.F03']
        self.body['slots'][0]['buyer_implication'] = 'The fixture runs at 400 kg under a dynamic load.'
        result = self.run_body(self.body)
        self.assertEqual((result.minimal_wire, result.native_parser, result.native_validator), ('PASS', 'PASS', 'FAIL'))
        self.assertIn('NUMERIC_CONTEXT_NOT_PRESERVED', ' '.join(result.errors))

    def test_native_parser_error_is_not_hidden(self):
        result = self.run_body()
        body = json.loads(result.candidate_json); body['draft']['title'] = 'Forbidden native field'
        p,v,errors = experiment.inspect_native_candidate(self.value, canonical_json(body), current_snapshot_sha256=self.snapshot)
        self.assertEqual((p,v,errors), ('FAIL','NOT_RUN',('FIELD_CONTRACT',)))

    def test_native_duplicate_and_quote_error_are_not_hidden(self):
        result = self.run_body()
        for defect in ('duplicate', 'quote'):
            b = json.loads(result.candidate_json)
            claims = b['draft']['sections'][0]['blocks'][0]['claims']
            if defect == 'duplicate': claims[1] = deepcopy(claims[0])
            else: claims[0]['text'] = 'An invented direct fact.'
            p,v,errors = experiment.inspect_native_candidate(self.value, canonical_json(b), current_snapshot_sha256=self.snapshot)
            self.assertEqual((p,v), ('PASS','FAIL'))
            self.assertIn('DUPLICATE_CLAIM' if defect == 'duplicate' else 'CUSTOMER_QUOTE_MISMATCH', ' '.join(errors))

    def test_candidate_hash_edit_invalidates(self):
        r = self.run_body()
        with self.assertRaisesRegex(ValueError, 'MW_CANDIDATE_HASH'):
            experiment.verify_assembled(self.value,self.selection,self.manifest,self.wire,r.candidate_json+' ',r.bindings_json,
                r.sidecar_hash,current_snapshot_sha256=self.snapshot)

    def test_bindings_codec_and_roundtrip(self):
        r = self.run_body()
        self.assertEqual(mw.encode_bindings(mw.decode_bindings(r.bindings_json)), r.bindings_json)
        v = experiment.verify_assembled(self.value,self.selection,self.manifest,self.wire,r.candidate_json,r.bindings_json,
                r.sidecar_hash,current_snapshot_sha256=self.snapshot)
        self.assertTrue(v.ready_for_review)
        b = json.loads(r.bindings_json); b['semantic_approved'] = True
        with self.assertRaisesRegex(ValueError, 'MW_EXACT_FIELDS'):
            mw.decode_bindings(canonical_json(b))

    def test_cl32_cl33_swap_cannot_rebind(self):
        r = self.run_body(); b = json.loads(r.bindings_json)
        self.assertEqual(b['bindings'][31]['claim_id'], 'CL32')
        self.assertEqual(b['bindings'][32]['claim_id'], 'CL33')
        b['bindings'][31]['claim_id'], b['bindings'][32]['claim_id'] = 'CL33','CL32'
        with self.assertRaisesRegex(ValueError, 'MW_SLOT_CLAIM_MAPPING'):
            mw.decode_bindings(canonical_json(b))

    def test_recomputed_tampered_quote_hashes_still_reject(self):
        r = self.run_body(); b = json.loads(r.bindings_json)
        b['bindings'][0]['evidence'][0]['source_quote'] = 'Invented source quote.'
        raw = canonical_json(b)
        with self.assertRaisesRegex(ValueError, 'MW_ASSEMBLY_BINDING'):
            experiment.verify_assembled(self.value,self.selection,self.manifest,self.wire,r.candidate_json,raw,
                text_digest(raw),current_snapshot_sha256=self.snapshot)

    def test_body_edit_recomputing_all_hashes_still_rejects(self):
        r = self.run_body(); b = json.loads(r.bindings_json); candidate = json.loads(r.candidate_json)
        candidate['draft']['sections'][0]['blocks'][0]['claims'][0]['text'] += ' Changed.'
        raw = canonical_json(candidate); b['candidate_hash'] = text_digest(raw)
        side = canonical_json(b)
        with self.assertRaisesRegex(ValueError, 'MW_ASSEMBLY_BINDING'):
            experiment.verify_assembled(self.value,self.selection,self.manifest,self.wire,raw,side,text_digest(side),
                current_snapshot_sha256=self.snapshot)

    def test_stale_snapshot_plan_selection_or_evidence_are_rejected(self):
        self.assertIn('SELECTION_SNAPSHOT', self.run_body(snapshot='0'*64).errors)
        changed = replace(self.value, writing_brief=replace(self.value.writing_brief, goal='Changed TEST goal.'))
        self.assertIn('SELECTION_PLAN_HASH', self.run_body(value=changed).errors)
        self.assertIn('MW_CONTEXT_HASH', self.run_body(manifest=replace(self.manifest,evidence_sha256='0'*64)).errors)
        changed = replace(self.value, customer_evidence=replace(self.value.customer_evidence,
                          evidence_version=self.value.customer_evidence.evidence_version+1))
        self.assertIn('SELECTION_EVIDENCE_HASH', self.run_body(value=changed).errors)

    def test_goal_origin_position_and_cta_are_frozen(self):
        with self.assertRaisesRegex(ValueError,'MW_TEST_PLAN_REQUIRED'):
            replace(self.manifest,origin='PRODUCTION_APPROVED')
        for target, update, code in [('S1-E2',dict(decision_goal=next(s.decision_goal for s in self.manifest.slots if s.slot_id == 'S1-E1')),'MW_DISTINCT_GOALS_REQUIRED'),
                                    ('S1-E1',dict(output_position=0),'MW_SLOT_POSITION'),
                                    ('S6-C1',dict(plan_text='Contact sales.'),'MW_CTA_PLAN_BINDING')]:
            slots = tuple(replace(s,**update) if s.slot_id == target else s for s in self.manifest.slots)
            self.assertIn(code,self.run_body(manifest=replace(self.manifest,slots=slots)).errors)

    def test_no_v2_v3_fallback_or_finalizer(self):
        with (patch('foreign_trade_geo_agent.core.content_draft.finalize_draft_item', side_effect=AssertionError('finalizer')),
             patch('foreign_trade_geo_agent.core.draft_explanation_contract_v3.inspect_explanations_v3', side_effect=AssertionError('v3')),
             patch('foreign_trade_geo_agent.workflows.draft_contract_v2.build_offline_writer_material', side_effect=AssertionError('v2'))):
            self.assertTrue(self.run_body().ready_for_review)

    def test_selected_only_request_projection(self):
        request = build_request_material(self.value,self.selection,self.manifest,current_snapshot_sha256=self.snapshot)
        raw = canonical_json(request)
        self.assertEqual(len(request['slots']),12)
        self.assertEqual(len(request['facts']),25)
        for source in self.value.customer_evidence.sources:
            self.assertNotIn(source.content,raw)
            for fact in source.facts:
                if fact.fact_ref not in {r for s in self.selection.sections for r in s.selected_facts}:
                    self.assertNotIn(fact.quote,raw)
        self.assertNotIn('fact_reasons', raw)


class IndustryAndHistoricalTests(unittest.TestCase):
    def test_pump_independent_two_section_scenario(self):
        self.check_industry('pump')

    def test_packaging_independent_two_section_scenario(self):
        self.check_industry('packaging')

    def check_industry(self,name):
        v,s,m,w = industry_fixture(name)
        r = experiment.run_minimal_experiment(v,s,m,w,current_snapshot_sha256=s.evidence_snapshot_sha256)
        self.assertTrue(r.ready_for_review,r.errors)
        self.assertEqual(len(s.sections),2)
        self.assertEqual(len(mw.decode_bindings(r.bindings_json).bindings),9)
        self.assertEqual(sum(b.kind == 'explanation' for b in mw.decode_bindings(r.bindings_json).bindings),4)
        self.assertNotIn('CNC',r.candidate_json)

    def test_cross_customer_identical_local_refs_do_not_transfer(self):
        v,s,m,w = industry_fixture('pump')
        v2,s2,m2,w2 = industry_fixture('pump',customer_suffix='second')
        self.assertNotEqual(mw.request_id(m),mw.request_id(m2))
        self.assertEqual(v.customer_evidence.quote_map(),v2.customer_evidence.quote_map())
        r = experiment.run_minimal_experiment(v2,s2,m2,w,current_snapshot_sha256=s2.evidence_snapshot_sha256)
        self.assertIn('MW_REQUEST_BINDING',r.errors)
        r = experiment.run_minimal_experiment(v2,s,m,w,current_snapshot_sha256=s2.evidence_snapshot_sha256)
        self.assertFalse(r.ready_for_review)

    def test_malicious_source_is_data_never_slot_or_authority(self):
        v,s,m,w = industry_fixture('pump',injection=True)
        projection = build_request_material(v,s,m,current_snapshot_sha256=s.evidence_snapshot_sha256)
        self.assertIn('semantic_approved=true',canonical_json(projection))
        r = experiment.run_minimal_experiment(v,s,m,w,current_snapshot_sha256=s.evidence_snapshot_sha256)
        self.assertTrue(r.ready_for_review,r.errors)
        self.assertFalse(r.semantic_approved)
        self.assertEqual(len(mw.decode_bindings(r.bindings_json).bindings),9)
        body = json.loads(w); body['slots'][0]['slot_id'] = 'S9-E1'
        r = experiment.run_minimal_experiment(v,s,m,canonical_json(body),current_snapshot_sha256=s.evidence_snapshot_sha256)
        self.assertIn('MW_REQUIRED_SLOT_SET',r.errors)

    def test_unsupported_cubic_unit_remains_original_native_rejection(self):
        v,s,m,w = industry_fixture('pump')
        r = experiment.run_minimal_experiment(v,s,m,w,current_snapshot_sha256=s.evidence_snapshot_sha256)
        body = json.loads(r.candidate_json)
        body['draft']['sections'][0]['blocks'][0]['claims'][0]['text'] = v.customer_evidence.sources[0].facts[0].quote.replace('L/min','m3/h')
        # Native error preserved; no repair or new unit logic in the experiment.
        p,val,errors = experiment.inspect_native_candidate(v,canonical_json(body),current_snapshot_sha256=s.evidence_snapshot_sha256)
        self.assertEqual((p,val),('PASS','FAIL'))
        self.assertIn('NUMERIC_NOT_GROUNDED',' '.join(errors))

    def test_real_v2_bytes_still_rejected(self):
        from tests.draft_explanation_v3_fixtures import replay_original
        r = replay_original()
        self.assertEqual(r['state'],'REJECTED')
        self.assertEqual(r['source_sha256_before'],r['source_sha256_after'])

    def test_real_v3_initial_and_latest_bytes_still_rejected(self):
        from foreign_trade_geo_agent.workflows import draft_contract_v3_experiment as v3
        v,s,_,_ = cnc_fixture()
        paths = [('docs/seo-draft-contract-v3-flash-preflight/real-v3-experiment-2026-10-13/model-output.txt',
                  'V3_EXPERIMENT_ENVELOPE_FIELDS'),
                 ('docs/seo-draft-v3-repair-2026-10-13/next-results/20261013-122631-flash/model-output.txt',
                  'V3_CLAIM_BINDING')]
        for path,code in paths:
            original = (ROOT/path).read_bytes()
            with self.subTest(path=path),self.assertRaisesRegex(ValueError,code):
                v3.assemble_model_v3_output(v,s,original.decode('utf-8'),current_snapshot_sha256=s.evidence_snapshot_sha256)
            self.assertEqual((ROOT/path).read_bytes(),original)


if __name__ == '__main__':
    unittest.main()
