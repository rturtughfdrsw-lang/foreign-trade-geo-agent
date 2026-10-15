"""Offline numeric example and real-response counterfactuals; no model approval."""
from copy import deepcopy
from dataclasses import replace
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.prepare_flash_prompt_refinement import historical_input, legal_mock, check, prepare, HISTORY
from foreign_trade_geo_agent.adapters.deepseek_content_draft import DeepSeekContentDraftWriter
from foreign_trade_geo_agent.core import content_draft as cd
from foreign_trade_geo_agent.storage.serialization import _decode, _encode
from tests import test_flash_draft_replay as replay


class FlashPromptRefinementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        replay.HistoricalFlashReplayTests.setUpClass.__func__(cls)

    check = replay.HistoricalFlashReplayTests.check
    def test_rendered_numeric_example_separates_exact_fact_from_analysis(self):
        system = DeepSeekContentDraftWriter.build_system_prompt(
            customer_evidence=True, propose_interpretations=True)
        examples = json.loads(system.split('SCHEMA EXAMPLES (illustrative only):\n')[1])
        direct, analysis = examples[:2]
        self.assertTrue(cd.extract_numeric_expressions(direct['text']))
        self.assertFalse(cd.extract_numeric_expressions(analysis['text']))
        self.assertEqual(direct['customer_refs'], ['E999.F01'])
        self.assertEqual(analysis['customer_refs'], ['E999.F01', 'E999.F02'])
        self.assertLessEqual(len(system), cd.MAX_SYSTEM_PROMPT_CHARS)

    def test_cl7_qualitative_analysis_passes_locally_without_changing_numeric_facts(self):
        response = json.loads(self.raw)
        claims = response['draft']['sections'][0]['blocks'][1]['claims']
        original_facts = deepcopy(claims[:2])
        claims[2]['text'] = (
            'Exclude NCX7 for the larger supplied fixture on nominal width and static load; '
            'keep NCX10 conditional. For the smaller fixture, nominal fit alone does not '
            'settle path or tool reach. Fixture clearance and dynamic loads remain unassessed. '
            'Send the fixture layout for configuration review.')
        check = self.check(response)
        self.assertIsNone(check.claims[6].deterministic_error)
        self.assertEqual(claims[:2], original_facts)
        self.assertEqual(check.state, 'DETERMINISTICALLY_REJECTED')
        self.assertFalse(check.production_authorized)

    def test_quantities_cannot_move_into_new_analysis_or_proposal_metadata(self):
        for field in ('text', 'reasoning', 'assumptions', 'limitation', 'procurement_action'):
            response = json.loads(self.raw)
            analysis = response['draft']['sections'][0]['blocks'][1]['claims'][2]
            analysis['text'] = ('Nominal fit still needs application review. '
                                + analysis['proposal']['limitation'] + ' '
                                + analysis['proposal']['procurement_action'])
            target = analysis if field == 'text' else analysis['proposal']
            old = target[field]
            target[field] = 'The 520 kg fixture should be excluded. ' + old
            if field in ('limitation', 'procurement_action'):
                analysis['text'] = analysis['text'].replace(old, target[field])
            with self.subTest(field=field):
                self.assertEqual(self.check(response).claims[6].deterministic_error,
                                 'NUMERIC_CONTEXT_NOT_PRESERVED')

    def test_native_six_section_mock_is_pending_and_wrong_routes_still_reject(self):
        value, response = historical_input(), legal_mock()
        result = check(value, response)
        self.assertEqual(result.errors, ())
        self.assertEqual(result.state, 'PENDING_SEMANTIC_REVIEW')
        self.assertFalse(result.production_authorized)
        self.assertEqual(len(result.claims), 47)
        for section, ref, error in (
            (1, 'E5.F03', 'SECTION_EVIDENCE_OUTSIDE_QUESTION'),
            (3, 'E3.F04', 'SECTION_FACT_OUTSIDE_QUESTION'),
        ):
            wrong = deepcopy(response)
            analysis = next(c for b in wrong['draft']['sections'][section]['blocks']
                for c in b.get('claims', b.get('items', [])) if c['claim_type'] == 'EVIDENCE_BASED_INTERPRETATION')
            analysis['customer_refs'].append(ref)
            with self.subTest(ref=ref):
                self.assertTrue(any(e.startswith(error) for e in check(value, wrong).errors))
        missing = deepcopy(response)
        section = missing['draft']['sections'][5]
        for block in section['blocks']:
            block['claims'] = [c for c in block['claims'] if c['customer_refs'] != ['E2.F09']]
            for c in block['claims']:
                c['customer_refs'] = [r for r in c['customer_refs'] if r != 'E2.F09']
        self.assertIn('SECTION_QUESTION_EVIDENCE_INCOMPLETE: Agree delivery training and support',
                      check(value, missing).errors)

    def test_freeze_changes_only_prompt_guidance_and_never_overwrites_a_package(self):
        with TemporaryDirectory() as temp:
            output = Path(temp) / 'control'
            ready = prepare(output)
            new = json.loads((output / 'request.FROZEN-NOT-AUTHORIZED.json').read_bytes())
            old = json.loads((HISTORY / 'request.json').read_bytes())
            before, after = (json.loads(r['messages'][1]['content']) for r in (old, new))
            self.assertNotEqual(before['contract']['customer_coverage_rule'], after['contract']['customer_coverage_rule'])
            before['contract']['customer_coverage_rule'] = after['contract']['customer_coverage_rule']
            self.assertEqual(before, after)
            self.assertNotEqual(new['messages'][0], old['messages'][0])
            new.pop('messages')
            old.pop('messages')
            self.assertEqual(new, old)
            self.assertFalse(ready['live_execution_ready'])
            self.assertFalse(ready['permit_issued'])
            with self.assertRaises(FileExistsError):
                prepare(output)

    def test_optional_facts_need_not_be_used_but_required_question_cannot_be_dropped(self):
        value, response = historical_input(), legal_mock()
        items = response['draft']['sections'][0]['blocks'][2]['items']
        items[:] = [c for c in items if c['customer_refs'] not in (['E2.F04'], ['E2.F08'])]
        result = check(value, response)
        self.assertEqual(result.state, 'PENDING_SEMANTIC_REVIEW')
        self.assertEqual(result.errors, ())
        self.assertEqual(len({r for c in result.claims for r in c.refs}), 41)
        # Empty and unknown selections fail even though the bank is optional.
        bundle = value.customer_evidence
        self.assertFalse(bundle.reference_selection_valid(()))
        self.assertFalse(bundle.reference_selection_valid(('E2.F99',)))
        self.assertTrue(bundle.reference_selection_valid(('E2.F02',)))
        mixed = replace(bundle, sources=(replace(bundle.sources[0], facts=()), *bundle.sources[1:]))
        self.assertFalse(mixed.reference_selection_valid(('E2.F02',)))
        self.assertTrue(mixed.reference_selection_valid(tuple(mixed.quote_map())))
        no_question = deepcopy(response)
        for b in no_question['draft']['sections'][0]['blocks']:
            for c in b.get('claims', b.get('items', [])):
                c['customer_refs'] = [r for r in c['customer_refs'] if not r.startswith('E5.')]
        self.assertIn('SECTION_REQUIREMENT_UNANSWERED: Compare configuration and model limits',
                      check(value, no_question).errors)

    def test_finalizer_and_reconstructed_draft_allow_selected_exact_facts(self):
        # Existing TEST-reviewed artifact: exercise Finalizer and DraftItem,
        # without approving this round's new proposals or refreshing review.
        base = HISTORY.parent / 'seo-full-article-budget-2026-10-11/final-v2/native/B-rich-evidence'
        reviewed = _decode(json.loads((base / 'native-reviewed-input.json').read_bytes()), cd.ContentDraftInput)
        from foreign_trade_geo_agent.workflows.content_draft import _parse_specification
        response = json.loads((base / 'mock-response.json').read_bytes())
        operation = reviewed.change_plan_report.operations[0]
        spec = _parse_specification(json.dumps(response), expected_change_ref='C1', operation=operation)
        draft, error = cd.finalize_draft_item(1, spec, operation, reviewed.opportunity_report.opportunities[0],
            reviewed.site_content, reviewed.opportunity_report, customer_evidence=reviewed.customer_evidence)
        self.assertIsNone(error)
        # Add an optional fact backed by the same real source span; retain every
        # exact ref on each existing TEST-reviewed interpretation. More bank
        # evidence must not force a different article.
        bundle = draft.customer_evidence
        source = bundle.sources[1]
        extra = replace(source.facts[0], fact_ref='E2.F99')
        expanded = replace(bundle, sources=(bundle.sources[0],
            replace(source, facts=(*source.facts, extra)), *bundle.sources[2:]))
        # No input-native rebinding is forged: only constructor reconstruction
        # and finalizer quote-selection behavior are under test here.
        selected = replace(draft, customer_evidence=expanded)
        self.assertEqual(selected.blocks, draft.blocks)
        self.assertEqual(_decode(_encode(selected), cd.DraftItem), selected)
        result, error = cd.finalize_draft_item(1, spec, operation, reviewed.opportunity_report.opportunities[0],
            reviewed.site_content, reviewed.opportunity_report, customer_evidence=expanded)
        self.assertIsNone(error)
        self.assertIsNotNone(result)


if __name__ == '__main__':
    unittest.main()
