"""Final rendered messages and native schema: offline regression of the Flash failure."""
import asyncio
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import httpx

from foreign_trade_geo_agent.adapters.deepseek_content_draft import DeepSeekContentDraftWriter
from foreign_trade_geo_agent.core import content_draft as cd
from foreign_trade_geo_agent.core.draft_customer_evidence import DraftCustomerFact, DraftCustomerSource
from foreign_trade_geo_agent.storage.serialization import _decode
from foreign_trade_geo_agent.web.generation import MockArticleExecutor
from foreign_trade_geo_agent.workflows.content_draft import (
    _parse_specification, inspect_candidate_output,
)
from tests.test_deepseek_content_draft_adapter import _make_prompt


HISTORY = Path(__file__).resolve().parents[1] / 'docs/seo-flash-quality-live-2026-10-12'
OLD_MOCK = HISTORY.parent / 'seo-full-article-budget-2026-10-11/final-v2/native/B-rich-evidence'


def historical_input():
    value = _decode(json.loads((HISTORY / 'native-input.json').read_bytes()), cd.ContentDraftInput)
    return replace(value, customer_evidence=replace(value.customer_evidence, reviewed_at=datetime.now(UTC)))


class DraftPromptContractTests(unittest.TestCase):
    def setUp(self):
        self.value = historical_input()
        self.prompt = cd.build_content_draft_prompt(self.value, 'C1')
        self.system = DeepSeekContentDraftWriter.build_system_prompt(
            customer_evidence=True, propose_interpretations=True)
        self.material = json.loads(self.prompt.material_json())

    def test_real_rich_input_final_messages_have_one_candidate_contract(self):
        request = json.loads(MockArticleExecutor.request_for(self.value))
        self.assertEqual(request['messages'][0]['content'], self.system)
        self.assertEqual(json.loads(request['messages'][1]['content']), self.material)
        self.assertIn('E CANDIDATE MODE', self.system)
        for old in ('Every claim is exactly {"text","claim_type","page_refs","source_refs"}',
                    'must cite at least one P page', 'must appear verbatim in the cited P evidence.', 'supersedes',
                    'Keep every claim short and lexically grounded'):
            self.assertNotIn(old, self.system)
        self.assertIn('"customer_refs"', self.system)
        self.assertIn('"proposal"', self.system)
        self.assertIn('procurement_question', self.system)
        self.assertIn('PENDING_SEMANTIC_REVIEW', self.system)
        self.assertIn('PLANNING_CONTEXT_ONLY', self.material['contract']['page_source_role'])
        self.assertEqual(len(self.material['contract']['customer_refs']), 43)
        self.assertEqual(len(self.material['change']['new_resource']['section_briefs']), 6)
        self.assertEqual(self.material['customer_evidence']['interpretations'], [])
        for actual, maximum in ((len(self.system), cd.MAX_SYSTEM_PROMPT_CHARS),
                (len(self.system.encode()), cd.MAX_SYSTEM_PROMPT_BYTES),
                (len(self.prompt.material_json()), cd.MAX_USER_MATERIAL_CHARS)):
            self.assertLessEqual(actual, maximum)

    def test_analysis_guidance_selects_presentation_without_evading_native_coverage(self):
        for text in ('reader_question', 'evidence bank, not a checklist', 'ceilings, not quotas',
                     'need not all be used', 'premises', 'Do not pad', 'paragraph',
                     'drawing revision', 'conditional candidate', 'measurement uncertainty'):
            self.assertIn(text, self.system)
        self.assertNotIn('Fact -> Meaning -> Limitation -> Action', self.system)
        self.assertNotIn('NovaCNC', self.system)
        self.assertNotIn('NCX7', self.system)
        self.assertIn('coverage', self.material['contract']['customer_coverage_rule'])

    def test_ordinary_ps_contract_remains_independent(self):
        system = DeepSeekContentDraftWriter.build_system_prompt()
        historical_system = json.loads((HISTORY / 'request.json').read_bytes())['messages'][0]['content']
        self.assertEqual(system, historical_system.split('\nE CANDIDATE RULE', 1)[0])
        self.assertIn('Every claim is exactly {"text","claim_type","page_refs","source_refs"}', system)
        self.assertIn('must cite at least one P page', system)
        self.assertNotIn('E CANDIDATE MODE', system)
        self.assertNotIn('proposal=', system)
        prompt = asyncio.run(_make_prompt())
        self.assertNotIn('customer_evidence', json.loads(prompt.material_json()))

    def test_reviewed_e_projects_exact_approved_proposal_and_never_expands_it(self):
        value = _decode(json.loads((OLD_MOCK / 'native-reviewed-input.json').read_bytes()), cd.ContentDraftInput)
        system = DeepSeekContentDraftWriter.build_system_prompt(customer_evidence=True)
        self.assertIn('E REVIEWED MODE', system)
        self.assertNotIn('supersedes', system)
        self.assertNotIn('must cite at least one P page', system)
        self.assertIn('copy the supplied reviewed interpretation', system)
        material = json.loads(cd.build_content_draft_prompt(value, 'C1').material_json())
        for projected, original in zip(material['customer_evidence']['interpretations'], value.customer_evidence.interpretations):
            self.assertEqual(projected['text'], original.text)
            self.assertEqual(projected['fact_refs'], list(original.fact_refs))
            self.assertEqual(projected['proposal']['reasoning'], original.proposal.reasoning)
        self.assertIn('supplied proposal', system)

    def test_reviewed_proposal_projection_does_not_depend_on_optional_writing_brief(self):
        value = _decode(json.loads((OLD_MOCK / 'native-reviewed-input.json').read_bytes()), cd.ContentDraftInput)
        value = replace(value, writing_brief=None)
        material = json.loads(cd.build_content_draft_prompt(value, 'C1').material_json())
        self.assertIn('proposal', material['customer_evidence']['interpretations'][0])

    def test_reviewed_interpretations_without_proposal_keep_legacy_shape(self):
        value = _decode(json.loads((OLD_MOCK / 'native-reviewed-input.json').read_bytes()), cd.ContentDraftInput)
        value = replace(value, customer_evidence=replace(value.customer_evidence,
            interpretations=tuple(replace(i, proposal=None) for i in value.customer_evidence.interpretations)))
        material = json.loads(cd.build_content_draft_prompt(value, 'C1').material_json())
        self.assertTrue(all('proposal' not in i for i in material['customer_evidence']['interpretations']))

    def test_reviewed_mode_allows_only_native_editorial_and_optional_approved_proposal(self):
        value = replace(self.value, propose_interpretations=False)
        system = DeepSeekContentDraftWriter.build_system_prompt(customer_evidence=True)
        material = json.loads(cd.build_content_draft_prompt(value, 'C1').material_json())
        self.assertIn('nonfactual editorial/CTA', material['contract']['customer_claim_rule'])
        self.assertIn('proposal only as specified by the current mode', system)

    def test_candidate_requires_native_customer_evidence_flag(self):
        with self.assertRaisesRegex(ValueError, 'CUSTOMER_EVIDENCE_INVALID'):
            DeepSeekContentDraftWriter.build_system_prompt(propose_interpretations=True)

    def test_ref_minimum_applies_only_to_e_facts_and_interpretations(self):
        self.assertIn('For E-backed facts/interpretations, customer_refs', self.system)
        self.assertIn('all ref arrays empty', self.system)

    def test_legacy_e_with_independent_ps_has_scoped_source_and_numeric_rules(self):
        value = _decode(json.loads((HISTORY.parent / 'seo-e-only-acceptance-2026-10-10/03-native-input.json').read_bytes()), cd.ContentDraftInput)
        prompt = cd.build_content_draft_prompt(value, 'C1')
        material = json.loads(prompt.material_json())
        system = json.loads(MockArticleExecutor.request_for(value))['messages'][0]['content']
        self.assertNotIn('page_source_role', material['contract'])
        self.assertIn('E-backed OBSERVED_PRODUCT_FACT', system)
        self.assertIn('For E-backed facts/interpretations, customer_refs', system)
        self.assertIn('S-only numbers cannot become first-party facts', system)
        self.assertIn('own cited P evidence', system)
        self.assertIn('point-specific', system)
        self.assertEqual(material['contract']['customer_refs'], [s.evidence_id for s in value.customer_evidence.sources])

    def test_embedded_examples_parse_and_validate_with_illustrative_evidence(self):
        marker = 'SCHEMA EXAMPLES (illustrative only):\n'
        self.assertIn(marker, self.system)
        examples = json.loads(self.system.split(marker, 1)[1])
        self.assertEqual(len(examples), 4)  # direct, multi-fact, transition, CTA
        content = examples[0]['text'] + '\nThe proposed setup needs application review.'
        first = examples[0]['text']
        facts = (DraftCustomerFact('E999.F01', 0, len(first), first),
                 DraftCustomerFact('E999.F02', len(first)+1, len(content), content[len(first)+1:]))
        source = DraftCustomerSource('E999', 1, ('DEMO',), 'Illustrative only', 'local:demo',
            content, hashlib.sha256(content.encode()).hexdigest(), 0, len(first), first, facts)
        bundle = replace(self.value.customer_evidence, sources=(source,), interpretations=())
        raw = json.dumps({'draft': {'change_ref': 'C1', 'draft_type': 'NEW_RESOURCE_DRAFT',
            'sections': [{'outline_heading': 'Illustrative only', 'blocks': [{'kind': 'PARAGRAPH', 'claims': examples}]}]}})
        spec = _parse_specification(raw, expected_change_ref='C1')
        for claim in spec.sections[0].blocks[0].claims:
            error = cd._validate_claim_evidence(claim, page_ids=set(), source_ids=set(),
                allowed_pages=set(), allowed_sources=set(), page_text_by_id={}, first_party_text=content,
                first_party_entities=frozenset(), customer_quote_by_id=bundle.quote_map(),
                customer_binding=bundle, proposal_only=True)
            self.assertIsNone(error)
        self.assertFalse(set(bundle.quote_map()) & set(self.value.customer_evidence.quote_map()))
        self.assertEqual(len(self.material['contract']['customer_refs']), 43)

    def test_actual_adapter_sends_the_same_final_messages_once_through_mock(self):
        requests = []
        def handler(request):
            requests.append(json.loads(request.content))
            return httpx.Response(200, json={'choices': [{'message': {'content': '{}'}, 'finish_reason': 'stop'}]})
        with patch.dict('os.environ', {'DEEPSEEK_API_KEY': 'OFFLINE-TEST'}, clear=True):
            writer = DeepSeekContentDraftWriter(transport=httpx.MockTransport(handler))
            result = asyncio.run(writer.write_content_draft(self.prompt))
        self.assertEqual(result.status, cd.ContentDraftGenerationStatus.SUCCESS)
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0], json.loads(MockArticleExecutor.request_for(self.value)))

    def test_original_failed_json_still_parses_and_rejects_without_ref_repair(self):
        raw = (HISTORY / 'model-output.txt').read_text(encoding='utf-8')
        before = hashlib.sha256(raw.encode()).hexdigest()
        spec = _parse_specification(raw, expected_change_ref='C1', operation=self.prompt.operation)
        claims = [c for s in spec.sections for b in s.blocks for c in getattr(b, 'claims', getattr(b, 'items', ()))]
        self.assertEqual(len(claims), 48)
        self.assertTrue(all(not c.customer_refs and c.proposal is None for c in claims))
        check = inspect_candidate_output(self.value, raw,
            current_snapshot_sha256=self.value.customer_evidence.snapshot_sha256)
        self.assertEqual(check.state, 'DETERMINISTICALLY_REJECTED')
        self.assertIn('CUSTOMER_EVIDENCE_COVERAGE', check.errors)
        self.assertTrue(any('CLAIM_TYPE_CONTRACT' in e for e in check.errors))
        self.assertEqual(before, hashlib.sha256((HISTORY / 'model-output.txt').read_bytes()).hexdigest())

    def test_valid_direct_fact_and_multi_fact_candidate_keep_e_safety(self):
        response = json.loads((OLD_MOCK / 'mock-response.json').read_bytes())
        def check(value):
            return inspect_candidate_output(self.value, json.dumps(value, separators=(',', ':')),
                current_snapshot_sha256=self.value.customer_evidence.snapshot_sha256)
        self.assertEqual(check(response).state, 'PENDING_SEMANTIC_REVIEW')
        for mutation in ('quote', 'refs', 'ps', 'numeric', 'approval', 'proposal'):
            changed = deepcopy(response)
            direct, analysis = changed['draft']['sections'][0]['blocks'][0]['claims']
            if mutation == 'quote': direct['text'] += ' Revised.'
            elif mutation == 'refs': direct['customer_refs'] = ['E999.F99']
            elif mutation == 'ps': direct.update(customer_refs=[], page_refs=['P1'], source_refs=['S1'])
            elif mutation == 'numeric': analysis['text'] = 'It carries 99999 kg. ' + analysis['text']
            elif mutation == 'approval': analysis['proposal']['approved'] = True
            else: analysis.pop('proposal')
            with self.subTest(mutation=mutation):
                if mutation == 'approval':
                    with self.assertRaisesRegex(ValueError, 'FIELD_CONTRACT'):
                        check(changed)
                else:
                    self.assertEqual(check(changed).state, 'DETERMINISTICALLY_REJECTED')
