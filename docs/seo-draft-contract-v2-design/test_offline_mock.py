"""Offline positive and adversarial examples for the proposed contract only."""
from copy import deepcopy
import json
import unittest

from build_mock import HISTORY, MATERIAL, encode, sha
from offline_mock import check, inspect_native, load, prohibit_network


class ContractV2MockTests(unittest.TestCase):
    def setUp(self):
        self.plan, self.raw, self.annotations = load()
        self.response = json.loads(self.raw)
        self.material = json.loads(MATERIAL.read_bytes())
        self.facts = {f['fact_ref']: f for s in self.material['customer_evidence']['sources'] for f in s['facts']}
        self.guard = prohibit_network()
        self.attempts = self.guard.__enter__()
        self.addCleanup(self.guard.__exit__, None, None, None)

    def evaluate(self, rebind=True):
        raw = encode(self.response)
        if rebind:
            self.annotations.update(candidate_sha256=sha(raw), contract_sha256=sha(encode(self.plan)))
        return check(raw, self.plan, self.annotations)

    def assertRejected(self, code):
        result = self.evaluate()
        self.assertEqual(result['design_status'], 'REJECTED')
        self.assertTrue(any(code in e for e in result['errors']), result['errors'])
        return result

    def analysis(self, si=0):
        return self.response['draft']['sections'][si]['blocks'][-1]['claims'][0]

    def direct(self, ref):
        return dict(text=self.facts[ref]['quote'], claim_type='OBSERVED_PRODUCT_FACT',
                    customer_refs=[ref], page_refs=[], source_refs=[])

    def test_legal_subset_passes_native_and_three_part_structure(self):
        result = self.evaluate()
        self.assertEqual(result['design_status'], 'PASS', result['errors'])
        self.assertEqual((result['claims'], result['blocks'], result['explanation_count']), (38, 20, 12))
        self.assertEqual(result['native_state'], 'PENDING_SEMANTIC_REVIEW')
        self.assertEqual(result['semantic_review'], 'HUMAN_REVIEW_REQUIRED')
        self.assertFalse(result['production_authorized'])
        self.assertEqual(self.attempts, [])

    def test_original_frozen_v1_is_rejected_without_mutation(self):
        raw = (HISTORY / 'model-output.txt').read_bytes()
        result = inspect_native(raw)
        self.assertEqual(sha(raw), '880c9ab66f4380fe34cabf6bf4aeacf8afe5b968049950931d0a6126f3bb2747')
        self.assertEqual(result.state, 'DETERMINISTICALLY_REJECTED')
        for error in ('CLAIM_BUDGET', 'SECTION_FACT_OUTSIDE_QUESTION: Read spindle and cutting trial evidence',
                      'SECTION_FACT_OUTSIDE_QUESTION: Specify representative acceptance tests',
                      'SECTION_QUESTION_EVIDENCE_INCOMPLETE: Agree delivery training and support'):
            self.assertIn(error, result.errors)
        self.assertEqual(raw, (HISTORY / 'model-output.txt').read_bytes())

    def test_forty_nine_claims_hit_unchanged_native_cap(self):
        # Preserve a legal per-block shape so claim count is an independent failure.
        claims = [deepcopy(self.direct('E2.F01')) for _ in range(49)]
        sections = self.response['draft']['sections']
        for section in sections:
            section['blocks'] = []
        for i in range(0, len(claims), 4):
            sections[(i//4) % 6]['blocks'].append(dict(kind='PARAGRAPH', claims=claims[i:i+4]))
        result = self.assertRejected('CLAIM_BUDGET')
        self.assertEqual(result['claims'], 49)

    def test_twenty_five_blocks_hit_unchanged_native_cap(self):
        self.response['draft']['sections'][0]['blocks'].extend(
            [dict(kind='PARAGRAPH', claims=[self.direct('E2.F02')]) for _ in range(5)])
        result = self.assertRejected('BLOCK_BUDGET')
        self.assertEqual(result['blocks'], 25)

    def test_s2_cannot_borrow_e5_f03_as_a_direct_fact(self):
        self.response['draft']['sections'][1]['blocks'][0]['claims'][0] = self.direct('E5.F03')
        self.assertRejected('SECTION_FACT_OUTSIDE_QUESTION')

    def test_s4_cannot_borrow_e5_f04_as_an_interpretation_premise(self):
        self.analysis(3)['customer_refs'].append('E5.F04')
        self.assertRejected('SECTION_FACT_OUTSIDE_QUESTION')

    def test_s6_e2_is_required_locally_despite_global_use(self):
        for block in self.response['draft']['sections'][5]['blocks']:
            block['claims'] = [c for c in block['claims'] if c['customer_refs'] != ['E2.F09']]
            for claim in block['claims']:
                claim['customer_refs'] = [r for r in claim['customer_refs'] if r != 'E2.F09']
        self.assertRejected('S6:SOURCE_ROUTING')

    def test_required_direct_fact_cannot_be_replaced_by_premise_only(self):
        del self.response['draft']['sections'][0]['blocks'][0]['claims'][0]
        self.assertRejected('S1:SELECTED_COVERAGE')

    def test_optional_is_not_writer_permission_until_selected(self):
        self.response['draft']['sections'][0]['blocks'][1]['claims'].append(self.direct('E2.F02'))
        self.assertRejected('S1:FACT_NOT_SELECTED')

    def test_planner_can_select_a_routed_optional_with_budget(self):
        self.plan['sections'][0]['selected_facts'].append('E2.F02')
        self.response['draft']['sections'][0]['blocks'][1]['claims'].append(self.direct('E2.F02'))
        result = self.evaluate()
        self.assertEqual(result['design_status'], 'PASS', result['errors'])
        self.assertEqual(result['claims'], 39)

    def test_optional_selection_without_actual_use_is_rejected(self):
        self.plan['sections'][0]['selected_facts'].append('E2.F02')
        self.assertRejected('S1:SELECTED_COVERAGE')

    def test_plan_cannot_retag_fact_to_admit_topic_similarity(self):
        self.plan['sections'][1]['optional_facts'].append('E5.F03')
        self.assertRejected('S2:PLAN_FACT_ROUTING')

    def test_every_fact_has_a_priority_and_omission_reason(self):
        priorities = self.plan['fact_priorities']
        self.assertEqual({f['fact_ref'] for f in priorities}, set(self.facts))
        self.assertEqual(sum(f['selected'] for f in priorities), 25)
        self.assertTrue(all(f['reason'] and f['priority'] in ('P0', 'P1', 'P2') for f in priorities))

    def test_required_fact_must_be_selected_before_writing(self):
        self.plan['sections'][0]['selected_facts'].remove('E5.F01')
        self.assertRejected('S1:PLAN_SELECTION')

    def test_missing_explanation_annotation_is_rejected(self):
        self.annotations['explanations'].pop()
        self.assertRejected('EXPLANATION_ANNOTATIONS_INCOMPLETE')

    def test_duplicate_annotation_location_is_rejected(self):
        self.annotations['explanations'].append(deepcopy(self.annotations['explanations'][0]))
        self.assertRejected('EXPLANATION_LOCATION')

    def test_each_explanation_part_is_required(self):
        for part in ('buyer_implication', 'non_applicability', 'verification_action'):
            original = deepcopy(self.annotations)
            with self.subTest(part=part):
                self.annotations['explanations'][0][part] = ''
                self.assertRejected('EXPLANATION_PART_DEPTH')
            self.annotations = original

    def test_fact_plus_short_reminder_is_insufficient(self):
        item = self.annotations['explanations'][0]
        sp = self.plan['sections'][0]
        item.update(buyer_implication='This matters for purchasing.',
                    non_applicability=sp['limitation'], verification_action=sp['procurement_action'])
        claim = self.response['draft']['sections'][0]['blocks'][item['block_index']]['claims'][0]
        claim['text'] = ' '.join(item[k] for k in ('buyer_implication', 'non_applicability', 'verification_action'))
        item['text_sha256'] = sha(claim['text'].encode())
        result = self.assertRejected('EXPLANATION_PART_DEPTH')
        self.assertEqual(result['native_state'], 'PENDING_SEMANTIC_REVIEW')
        self.assertFalse(any('EXPLANATION_BODY_BINDING' in e for e in result['errors']))

    def test_metadata_cannot_substitute_for_visible_explanation(self):
        self.analysis()['text'] = 'Check suitability. ' + self.plan['sections'][0]['limitation']
        self.assertRejected('EXPLANATION_BODY_BINDING')

    def test_correct_limitation_and_action_need_correct_part_placement(self):
        item = self.annotations['explanations'][0]
        item['non_applicability'], item['verification_action'] = item['verification_action'], item['non_applicability']
        self.assertRejected('EXPLANATION_BOUNDARY_PLACEMENT')

    def test_numeric_fact_tampering_is_still_rejected(self):
        self.response['draft']['sections'][0]['blocks'][0]['claims'][0]['text'] = self.facts['E2.F01']['quote'].replace('700 mm', '701 mm')
        result = self.assertRejected('CL1:')
        self.assertEqual(result['native_state'], 'DETERMINISTICALLY_REJECTED')

    def test_ps_cannot_replace_e_references(self):
        self.analysis().update(page_refs=['P1'], source_refs=['S1'], customer_refs=[])
        result = self.assertRejected('CL')
        self.assertEqual(result['native_state'], 'DETERMINISTICALLY_REJECTED')

    def test_interpretation_cannot_omit_proposal(self):
        self.analysis().pop('proposal')
        result = self.evaluate()
        self.assertEqual(result['design_status'], 'REJECTED')
        self.assertNotEqual(result['native_state'], 'PENDING_SEMANTIC_REVIEW')

    def test_snapshot_and_candidate_hash_are_bound(self):
        self.annotations['snapshot_sha256'] = '0'*64
        self.assertRejected('ANNOTATION_BINDING')
        self.plan, self.raw, self.annotations = load()
        self.annotations['candidate_sha256'] = '0'*64
        self.assertIn('ANNOTATION_BINDING', self.evaluate(rebind=False)['errors'])

    def test_plan_input_hash_cannot_be_rebound_to_another_snapshot(self):
        self.plan['snapshot_sha256'] = '0'*64
        self.assertRejected('PLAN_INPUT_BINDING')

    def test_budget_cannot_be_relaxed_in_design_file(self):
        self.plan['budgets']['claim_hard'] = 50
        self.assertRejected('PLAN_BUDGET_CONTRACT')

    def test_repeat_quote_is_not_a_claim_budget_workaround(self):
        self.response['draft']['sections'][0]['blocks'][1]['claims'].append(self.direct('E2.F01'))
        result = self.evaluate()
        self.assertEqual(result['design_status'], 'REJECTED')
        self.assertNotEqual(result['native_state'], 'PENDING_SEMANTIC_REVIEW')


if __name__ == '__main__':
    unittest.main()
