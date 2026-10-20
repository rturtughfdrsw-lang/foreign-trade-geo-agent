"""Request freeze and adversarial checks, with synthetic answers used ONLY locally."""
from copy import deepcopy
from dataclasses import asdict, replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import prepare_minimal_writer_flash_preflight as pf
from foreign_trade_geo_agent.core import minimal_writer_wire as mw
from foreign_trade_geo_agent.core.draft_selection_contract import selection_digest
from foreign_trade_geo_agent.workflows import minimal_writer_experiment as experiment
from tests.minimal_flash_fixtures import isolated_flash_package


class MinimalFlashPreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = pf.read_sources()
        cls.codes = pf.code_bindings()
        cls.criteria = (pf.DEST/'success-criteria.md').read_bytes()

    def setUp(self):
        self.enterContext(isolated_flash_package())
        self.value, self.selection, self.manifest = pf.context(self.sources)
        self.raw, self.material, self.user = pf.build_request(self.value, self.selection, self.manifest)
        self.snapshot = self.selection.evidence_snapshot_sha256

    def package(self, directory):
        files = pf.build_bundle(self.sources, self.codes, self.criteria)
        for name, body in files.items():
            (Path(directory)/name).write_bytes(body)
        (Path(directory)/'report.md').write_text('Local test report', encoding='utf-8')
        return pf.sha(files['manifest.json'])

    def wire(self):
        # Explicitly isolated fake output: never imported/read by request builder.
        body = json.loads((pf.ROOT/(pf.SOURCE+'wire.json')).read_bytes())
        body['request_id'] = mw.request_id(self.manifest)
        next(a for a in body['slots'] if a['slot_id'] == 'S4-E2')['premise_refs'].append('E3.F07')
        return body

    def run_wire(self, body):
        return experiment.run_minimal_experiment(self.value, self.selection, self.manifest,
            pf.encode(body).decode('utf-8'), current_snapshot_sha256=self.snapshot)

    def test_same_input_same_request_bytes_and_hash(self):
        a = pf.build_bundle(self.sources, self.codes, self.criteria)
        b = pf.build_bundle(dict(reversed(list(self.sources.items()))),
                            dict(reversed(list(self.codes.items()))), self.criteria)
        self.assertEqual(a, b)
        self.assertEqual(pf.sha(a['request.json']), pf.sha(b['request.json']))
        self.assertEqual(a['request-body.sha256'], (pf.sha(self.raw)+'  request.json\n').encode())

    def test_request_parameters_and_transport_config_exact(self):
        body = pf.strict(self.raw)
        self.assertEqual({k:v for k,v in body.items() if k != 'messages'}, pf.PARAMETERS)
        files = pf.build_bundle(self.sources, self.codes, self.criteria)
        config = pf.strict(files['experiment-config.json'])
        self.assertEqual((config['timeout'],config['retries'],config['fallback']), (60,0,False))
        self.assertEqual(config['endpoint'], 'https://api.deepseek.com/chat/completions')
        for field in ('network_allowed','live_authorized','semantic_approved','production_authorized',
                      'customer_approved_subquestions','repair','redirects'):
            self.assertIs(config[field], False)
        self.assertIs(config['test_only'], True)

    def test_prompt_files_match_request_content_bytes(self):
        files = pf.build_bundle(self.sources, self.codes, self.criteria)
        body = pf.strict(files['request.json'])
        for index, name in enumerate(('system-prompt.txt','user-prompt.txt')):
            self.assertEqual(body['messages'][index]['content'].encode(), files[name])
        self.assertEqual(pf.strict(files['writer-material.json']), pf.strict(files['user-prompt.txt'])['writer_material'])
        self.assertEqual(pf.strict(files['wire-schema.json']), pf.strict(files['user-prompt.txt'])['wire_schema'])

    def test_existing_sources_unchanged_and_route_adjustment_minimal(self):
        original = mw.decode_manifest(self.sources['original-slot-manifest.json'].decode())
        self.assertEqual(self.manifest.origin, mw.TEST_ORIGIN)
        self.assertEqual(self.manifest.author, original.author)
        for old, new in zip(original.slots, self.manifest.slots, strict=True):
            if old.slot_id == 'S4-E2':
                self.assertEqual(new, replace(old, allowed_fact_refs=old.allowed_fact_refs+('E3.F07',)))
            else:
                self.assertEqual(old, new)
        self.assertEqual(self.manifest.selection_sha256, selection_digest(self.selection))
        self.assertEqual(pf.strict(self.sources['minimal-native-input.json']), pf.strict(pf.encode(asdict(self.value))))

    def test_twelve_distinct_goals_explicit_evidence_and_character_limits(self):
        slots = self.material['slots']
        self.assertEqual(len(slots), 12)
        self.assertEqual(len({s['decision_goal'] for s in slots}), 12)
        self.assertEqual(len({s['reader_subquestion'] for s in slots}), 12)
        facts = {f['fact_ref']: f['quote'] for f in self.material['facts']}
        self.assertEqual(len(facts),25)
        for slot in slots:
            self.assertTrue(set(slot['allowed_fact_refs']) <= facts.keys())
            self.assertEqual(slot['budget'],1200)
            self.assertLessEqual(len(slot['boundary_condition']),150)
            self.assertLessEqual(len(slot['verification_action']),150)
            self.assertLessEqual(300+300+len(slot['boundary_condition'])+len(slot['verification_action'])+3,slot['budget'])
        self.assertIn('outer width',facts['E3.F07'])
        self.assertIn('E3.F07',next(s for s in slots if s['slot_id']=='S4-E2')['allowed_fact_refs'])

    def test_native_assembly_budget_and_no_validator_bypass(self):
        with (patch.object(experiment,'_parse_specification',wraps=experiment._parse_specification) as parser,
              patch.object(experiment,'inspect_specification',wraps=experiment.inspect_specification) as validator):
            result = self.run_wire(self.wire())
        self.assertTrue(result.ready_for_review, result.errors)
        self.assertEqual((parser.call_count,validator.call_count),(1,1))
        candidate = json.loads(result.candidate_json)
        bindings = mw.decode_bindings(result.bindings_json).bindings
        self.assertEqual(len(bindings),38)
        self.assertEqual(sum(len(s['blocks']) for s in candidate['draft']['sections']),13)
        self.assertEqual(sum(s.kind=='direct_fact' for s in bindings),25)
        self.assertEqual(sum(s.kind=='explanation' for s in bindings),12)
        self.assertEqual(bindings[-1].kind,'cta')
        self.assertFalse(result.semantic_approved)
        self.assertFalse(result.production_authorized)

    def test_selected_only_no_full_sources_or_internal_audit_reasons(self):
        pf.check_boundary(self.material,self.value,self.selection,self.manifest)
        text = self.raw.decode()
        selected = {r for s in self.selection.sections for r in s.selected_facts}
        for source in self.value.customer_evidence.sources:
            self.assertNotIn(source.content,self.user)
            for fact in source.facts:
                if fact.fact_ref not in selected:
                    self.assertNotIn(fact.fact_ref,text)
                    self.assertNotIn(fact.quote,text)
        for reason in self.selection.fact_reasons:
            self.assertNotIn(reason.reason,text)

    def test_builder_reads_only_allowlisted_inputs_never_answer_files(self):
        paths = []
        original = Path.read_bytes
        def recorded(path):
            paths.append(path.relative_to(pf.ROOT).as_posix())
            return original(path)
        with patch.object(Path,'read_bytes',recorded):
            sources = pf.read_sources()
            value,selection,manifest = pf.context(sources)
            pf.build_request(value,selection,manifest)
        self.assertEqual(set(paths),set(pf.INPUT_PATHS.values()))
        self.assertFalse(any(p.startswith('tests/') or p.endswith(('wire.json','candidate.json','model-output.txt')) for p in paths))

    def test_no_synthetic_positive_answer_in_prompt(self):
        for answer in self.wire()['slots']:
            self.assertNotIn(answer['buyer_implication'], self.user)
            self.assertNotIn(answer['assumptions'], self.user)
        self.assertEqual(set(pf.strict(self.user.encode())), {'writer_material','wire_schema'})

    def test_exact_projection_rejects_extra_and_permission_fields(self):
        for field in ('extra','semantic_approved','production_authorized','network_allowed','live_authorized',
                      'fact_reasons','historical_failed_output','candidate','bindings'):
            with self.subTest(field=field):
                material = deepcopy(self.material); material[field] = 'forbidden'
                with self.assertRaisesRegex(ValueError,'PREFLIGHT_EXACT_PROJECTION'):
                    pf.check_boundary(material,self.value,self.selection,self.manifest)

    def test_unselected_fact_and_unknown_request_slot_rejected(self):
        material = deepcopy(self.material)
        material['facts'].append(dict(fact_ref='E2.F02',quote='Unselected'))
        with self.assertRaisesRegex(ValueError,'PREFLIGHT_EXACT_PROJECTION'):
            pf.check_boundary(material,self.value,self.selection,self.manifest)
        material = deepcopy(self.material); material['slots'][0]['slot_id']='S9-E1'
        with self.assertRaisesRegex(ValueError,'PREFLIGHT_EXACT_PROJECTION'):
            pf.check_boundary(material,self.value,self.selection,self.manifest)

    def test_frozen_package_verifies_and_reconstructs_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as temp:
            anchor = self.package(temp)
            self.assertTrue(pf.verify_package(temp,anchor,current_sources=self.sources,current_codes=self.codes)['valid'])
        anchor = pf.sha(pf.build_bundle(self.sources,self.codes,self.criteria)['manifest.json'])
        self.assertTrue(pf.verify_package(pf.DEST,anchor)['valid'])

    def test_old_request_rejects_selection_change(self):
        changed = replace(self.selection,fact_reasons=(replace(self.selection.fact_reasons[0],reason='Changed TEST reason.'),
                                                      *self.selection.fact_reasons[1:]))
        with self.assertRaisesRegex(ValueError,'MW_CONTEXT_HASH'):
            pf.build_request(self.value,changed,self.manifest)
        self.source_drift('selection.json')

    def test_old_request_rejects_snapshot_change(self):
        value = replace(self.value,customer_evidence=replace(self.value.customer_evidence,snapshot_sha256='0'*64))
        with self.assertRaisesRegex(ValueError,'SELECTION_SNAPSHOT'):
            pf.build_request(value,self.selection,self.manifest)
        self.source_drift('evidence-snapshot.json')

    def test_old_request_rejects_plan_change(self):
        value = replace(self.value,writing_brief=replace(self.value.writing_brief,goal='Changed TEST goal.'))
        with self.assertRaisesRegex(ValueError,'SELECTION_PLAN_HASH'):
            pf.build_request(value,self.selection,self.manifest)
        self.source_drift('native-input.json')

    def test_old_request_rejects_slot_manifest_change(self):
        slots = tuple(replace(s,decision_goal='Changed TEST decision.') if s.slot_id=='S1-E1' else s
                      for s in self.manifest.slots)
        manifest = replace(self.manifest,slots=slots)
        changed,_,_ = pf.build_request(self.value,self.selection,manifest)
        self.assertNotEqual(self.raw,changed)
        self.assertNotEqual(pf.sha(self.raw),pf.sha(changed))
        with tempfile.TemporaryDirectory() as temp:
            anchor = self.package(temp)
            (Path(temp)/'slot-manifest.json').write_text(mw.encode_manifest(manifest),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'PREFLIGHT_FROZEN_BYTES'):
                pf.verify_package(temp,anchor,current_sources=self.sources,current_codes=self.codes)

    def source_drift(self,name):
        # Whitespace-only change also invalidates exact frozen source bytes.
        changed = dict(self.sources); changed[name] += b' '
        with tempfile.TemporaryDirectory() as temp:
            anchor = self.package(temp)
            with self.assertRaisesRegex(ValueError,'PREFLIGHT_FROZEN_BYTES'):
                pf.verify_package(temp,anchor,current_sources=changed,current_codes=self.codes)

    def test_extra_directory_or_file_rejected(self):
        for directory in (False,True):
            with self.subTest(directory=directory),tempfile.TemporaryDirectory() as temp:
                anchor = self.package(temp); path=Path(temp)/'results'
                path.mkdir() if directory else path.write_text('extra')
                with self.assertRaisesRegex(ValueError,'PREFLIGHT_FILE_SET'):
                    pf.verify_package(temp,anchor,current_sources=self.sources,current_codes=self.codes)

    def test_each_bound_frozen_file_tamper_rejected(self):
        files=pf.build_bundle(self.sources,self.codes,self.criteria)
        for name in files:
            with self.subTest(name=name),tempfile.TemporaryDirectory() as temp:
                anchor=self.package(temp); path=Path(temp)/name
                path.write_bytes(path.read_bytes()+b' ')
                with self.assertRaises(ValueError):
                    pf.verify_package(temp,anchor,current_sources=self.sources,current_codes=self.codes)

    def test_resealed_manifest_does_not_inherit_original_anchor(self):
        with tempfile.TemporaryDirectory() as temp:
            anchor=self.package(temp); path=Path(temp)/'manifest.json'
            path.write_bytes(path.read_bytes()+b' ')
            (Path(temp)/'manifest.sha256').write_text(pf.sha(path.read_bytes())+'  manifest.json\n')
            with self.assertRaisesRegex(ValueError,'PREFLIGHT_MANIFEST_ANCHOR'):
                pf.verify_package(temp,anchor,current_sources=self.sources,current_codes=self.codes)

    def test_code_drift_rejected(self):
        codes=dict(self.codes); codes[next(iter(codes))]='0'*64
        with tempfile.TemporaryDirectory() as temp:
            anchor=self.package(temp)
            with self.assertRaisesRegex(ValueError,'PREFLIGHT_FROZEN_BYTES'):
                pf.verify_package(temp,anchor,current_sources=self.sources,current_codes=codes)

    def test_config_or_request_extra_fields_rejected(self):
        for name in ('experiment-config.json','request.json'):
            for key in ('extra','production_authorized','live_authorized','fallback','retries'):
                with self.subTest(name=name,key=key),tempfile.TemporaryDirectory() as temp:
                    anchor=self.package(temp); path=Path(temp)/name; obj=pf.strict(path.read_bytes())
                    obj[key]=True; path.write_bytes(pf.encode(obj))
                    with self.assertRaisesRegex(ValueError,'PREFLIGHT_FROZEN_BYTES'):
                        pf.verify_package(temp,anchor,current_sources=self.sources,current_codes=self.codes)

    def test_results_path_is_sibling_and_uncreated(self):
        target=(pf.ROOT/pf.RESULTS).resolve()
        self.assertFalse(target.is_relative_to(pf.DEST.resolve()))
        self.assertFalse(target.exists())

    def test_model_unknown_slot_extra_permission_and_unselected_fact_rejected(self):
        for kind,code in (('slot','MW_REQUIRED_SLOT_SET'),('permission','MW_EXACT_FIELDS'),
                          ('extra','MW_EXACT_FIELDS'),('fact','MW_PREMISE_OUTSIDE_SLOT')):
            with self.subTest(kind=kind):
                body=self.wire()
                if kind=='slot': body['slots'][0]['slot_id']='S9-E1'
                elif kind=='permission': body['semantic_approved']=True
                elif kind=='extra': body['slots'][0]['unknown']='extra'
                else: body['slots'][0]['premise_refs']=['E2.F02']
                result=self.run_wire(body)
                self.assertIn(code,result.errors)
                self.assertEqual(result.native_parser,'NOT_RUN')
                self.assertEqual(result.candidate_json,'')

    def test_python_preserves_all_model_semantic_text_exactly(self):
        body=self.wire(); result=self.run_wire(body)
        self.assertTrue(result.ready_for_review,result.errors)
        side=mw.decode_bindings(result.bindings_json)
        claims=[c for s in json.loads(result.candidate_json)['draft']['sections']
                for b in s['blocks'] for c in b['claims']]
        answers={a['slot_id']:a for a in body['slots']}
        for binding,claim in zip(side.bindings,claims,strict=True):
            if binding.kind!='explanation': continue
            answer=answers[binding.slot_id]
            text=' '.join(answer[k] for k in ('buyer_implication','assumptions','boundary_condition','verification_action'))
            self.assertEqual(claim['text'],text)
            self.assertEqual(binding.text,text)
            self.assertEqual(claim['proposal']['reasoning'],answer['buyer_implication'])
            self.assertEqual(claim['proposal']['assumptions'],answer['assumptions'])

    def test_boundary_mismatch_or_empty_semantics_not_repaired(self):
        for field in ('boundary_condition','buyer_implication','assumptions','verification_action'):
            body=self.wire(); body['slots'][0][field]=''
            result=self.run_wire(body)
            self.assertFalse(result.ready_for_review)
            self.assertEqual(result.candidate_json,'')
        body=self.wire(); body['slots'][0]['boundary_condition']='Invented replacement.'
        self.assertIn('MW_PLAN_BOUNDARY_CONFLICT',self.run_wire(body).errors)

    def test_insufficient_evidence_is_preserved_and_not_filled(self):
        body=self.wire()
        body['slots'][0]=dict(slot_id='S1-E1',status='insufficient_evidence',missing_information='The intended fixture layout is unavailable.')
        result=self.run_wire(body)
        self.assertEqual(result.refused_slots,('S1-E1',))
        self.assertIn('MW_INSUFFICIENT_EVIDENCE',result.errors)
        self.assertEqual((result.candidate_json,result.native_parser,result.native_validator),('','NOT_RUN','NOT_RUN'))

    def test_native_numeric_rejection_is_preserved(self):
        body=self.wire(); body['slots'][0].update(premise_refs=['E2.F03'],
            buyer_implication='The fixture runs at 400 kg under a dynamic load.')
        result=self.run_wire(body)
        self.assertEqual((result.minimal_wire,result.native_parser,result.native_validator),('PASS','PASS','FAIL'))
        self.assertIn('NUMERIC_CONTEXT_NOT_PRESERVED',' '.join(result.errors))

    def test_historical_v2_v3_original_rejections_unchanged(self):
        from tests.draft_explanation_v3_fixtures import replay_original
        from foreign_trade_geo_agent.workflows import draft_contract_v3_experiment as v3
        result=replay_original()
        self.assertEqual(result['state'],'REJECTED')
        self.assertEqual(result['source_sha256_before'],result['source_sha256_after'])
        for path,code in (
            ('docs/seo-draft-contract-v3-flash-preflight/real-v3-experiment-2026-10-13/model-output.txt','V3_EXPERIMENT_ENVELOPE_FIELDS'),
            ('docs/seo-draft-v3-repair-2026-10-13/next-results/20261013-122631-flash/model-output.txt','V3_CLAIM_BINDING')):
            before=(pf.ROOT/path).read_bytes()
            with self.subTest(path=path),self.assertRaisesRegex(ValueError,code):
                v3.assemble_model_v3_output(self.value,self.selection,before.decode(),current_snapshot_sha256=self.snapshot)
            self.assertEqual((pf.ROOT/path).read_bytes(),before)

    def test_no_live_execution_or_fixture_import_in_freeze_tool(self):
        source=(pf.ROOT/'scripts/prepare_minimal_writer_flash_preflight.py').read_text(encoding='utf-8')
        self.assertNotIn('from tests.',source)
        self.assertNotIn('import httpx',source)
        self.assertNotIn('load_dotenv',source)
        self.assertNotIn('os.environ',source)
        self.assertNotIn('requests.post',source)
        self.assertIn('no live mode exists',source)


if __name__=='__main__':
    unittest.main()
