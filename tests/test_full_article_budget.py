"""Finite article capacity without weakening evidence or review authority."""
import unittest
import asyncio
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from foreign_trade_geo_agent.core import content_draft as cd
from foreign_trade_geo_agent.core import draft_customer_evidence as ce
from foreign_trade_geo_agent.core.content_draft_review import MAX_LOCAL_BODY
from foreign_trade_geo_agent.adapters.deepseek_content_draft import content_draft_request_payload
from foreign_trade_geo_agent.adapters.retained_deepseek import MAX_RESPONSE_BYTES
from foreign_trade_geo_agent.adapters.deepseek_content_draft import DeepSeekContentDraftWriter
from foreign_trade_geo_agent.storage.serialization import _decode, _encode
from foreign_trade_geo_agent.storage.content_draft_review import SQLiteLocalDraftReviewStore
from foreign_trade_geo_agent.workflows.content_draft import ContentDraftWorkflow, inspect_candidate_output, _parse_specification
from foreign_trade_geo_agent.workflows.content_draft_review import test_only_revalidate_candidate
from foreign_trade_geo_agent.core.draft_candidate_review import digest, effective_decisions
from foreign_trade_geo_agent.core.evidence_intake import IntakeSnapshot, SemanticAssessment
from foreign_trade_geo_agent.web.app import create_app
from scripts import accept_full_article_budget as case


class FullGuideStressTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name)/'guide'
        cls.result = case.prepare(cls.root)
        cls.rich = cls.root/'native/B-rich-evidence'
        cls.value = _decode(json.loads((cls.rich/'frozen-native-input.json').read_bytes()),cd.ContentDraftInput)
        cls.reviewed = _decode(json.loads((cls.rich/'native-reviewed-input.json').read_bytes()),cd.ContentDraftInput)
        cls.response = json.loads((cls.rich/'mock-response.json').read_bytes())
        cls.raw = json.dumps(cls.response,separators=(',',':'))
        cls.key = json.loads((cls.rich/'generation-state.json').read_bytes())['binding_sha256']
        cls.output = cls.rich/'generation'/cls.key
        cls.history = SQLiteLocalDraftReviewStore(cls.output/'local-review.sqlite3').revisions(digest(cls.raw))
        cls.snapshot = _decode(json.loads((cls.rich/'snapshot.json').read_bytes()),IntakeSnapshot)
        cls.assessment = _decode(json.loads((cls.rich/'04-test-only-review.json').read_bytes())['assessment'],SemanticAssessment)

    def inspect(self, response, value=None):
        value = value or self.value
        return inspect_candidate_output(value,json.dumps(response,separators=(',',':')),
            current_snapshot_sha256=value.customer_evidence.snapshot_sha256)

    def native_run(self, response, value=None):
        raw = json.dumps(response,separators=(',',':'))
        class Writer:
            async def write_content_draft(self,prompt):
                return cd.ContentDraftGeneration('synthetic','test',cd.ContentDraftGenerationStatus.SUCCESS,raw,None)
        return asyncio.run(ContentDraftWorkflow(Writer(),max_repair_attempts=0).run(value or self.value))

    def test_complete_distinct_guide_native_chain_and_pending_review(self):
        b=self.result['budgets']
        self.assertGreater(b['article_words_whitespace'],1500)
        self.assertEqual((b['claims'],b['blocks'],b['sections']),(25,19,6))
        self.assertGreater(b['mock_output_chars'],16000)
        self.assertEqual(self.result['offline_contract'],'OFFLINE_CONTRACT_READY')
        checked=self.inspect(self.response)
        self.assertFalse(checked.errors)
        self.assertEqual(checked.state,'PENDING_SEMANTIC_REVIEW')
        self.assertEqual(len([c for c in checked.claims if c.proposal]),18)
        self.assertFalse(self.value.customer_evidence.interpretations)
        self.assertEqual(self.native_run(self.response).error,'INTERPRETATION_PENDING_REVIEW')
        report=self.native_run(self.response,self.reviewed)
        self.assertEqual(report.status,cd.ContentDraftStatus.SUCCESS)
        self.assertEqual(_decode(_encode(report),cd.ContentDraftReport),report)
        self.assertEqual(len(report.drafts[0].blocks),19)
        self.assertEqual(len(self.reviewed.customer_evidence.interpretations),18)
        self.assertEqual((self.result['low_status'],self.result['low_writer_calls']),('BLOCKED',0))
        self.assertFalse(self.result['production_authorized'])

    def boundary_layout(self):
        response=deepcopy(self.response)
        for i,section in enumerate(response['draft']['sections']):
            direct=section['blocks'][0]['claims'][0]
            original=[b['claims'][-1] for b in section['blocks'][:3]]
            analyses=[]
            for j in range(7 if i<5 else 6):
                claim=deepcopy(original[j%3])
                claim['text']+=' '+('Confirm scope.','Review setup.','Request records.','Check applicability.',
                    'Discuss conditions.','Record questions.','Retain the response.')[j]
                analyses.append(claim)
            claims=[direct,*analyses]
            if i==5:
                claims.append(deepcopy(self.response['draft']['sections'][-1]['blocks'][-1]['claims'][0]))
            section['blocks']=[dict(kind='PARAGRAPH',claims=claims[j:j+2]) for j in range(0,8,2)]
        return response

    def test_exact_structural_limits_and_one_above_reject(self):
        exact=self.boundary_layout()
        check=self.inspect(exact)
        self.assertEqual(len(check.claims),48)
        self.assertNotIn('BLOCK_BUDGET',check.errors)
        self.assertNotIn('CLAIM_BUDGET',check.errors)
        self.assertFalse(check.errors)
        over=deepcopy(exact)
        over['draft']['sections'][0]['blocks'][0]['claims'].append(deepcopy(over['draft']['sections'][0]['blocks'][1]['claims'][0]))
        self.assertIn('CLAIM_BUDGET',self.inspect(over).errors)
        over=deepcopy(exact)
        over['draft']['sections'][0]['blocks'].append(dict(kind='BULLET_LIST',items=[deepcopy(over['draft']['sections'][0]['blocks'][0]['claims'][0])]))
        self.assertIn('BLOCK_BUDGET',self.inspect(over).errors)

    def test_exact_interpretation_length_and_premise_limit(self):
        response=deepcopy(self.response)
        claim=response['draft']['sections'][0]['blocks'][0]['claims'][1]
        # Valid canonical prose at precisely the limit, with existing evidence.
        claim['text']+=' '+('scope ' * 300)
        claim['text']=claim['text'][:ce.MAX_INTERPRETATION_CHARS-1].rstrip()+'.'
        claim['text']+='.'*(ce.MAX_INTERPRETATION_CHARS-len(claim['text']))
        self.assertEqual(len(claim['text']),1200)
        self.assertFalse(self.inspect(response).errors)
        interpretation=ce.DraftInterpretation(claim['text'],tuple(claim['customer_refs']),
            claim['proposal']['limitation'],claim['proposal']['procurement_action'],ce.InterpretationProposal(**claim['proposal']))
        self.assertEqual(len(interpretation.text),1200)
        claim['text']+='x'
        self.assertIn('CLAIM_BUDGET',str(self.inspect(response).errors))
        refs=tuple(self.value.customer_evidence.quote_map())[:20]
        self.assertEqual(len(replace(interpretation,fact_refs=refs).fact_refs),20)
        with self.assertRaises(ValueError):
            replace(interpretation,fact_refs=tuple(self.value.customer_evidence.quote_map())[:21])

    def test_exact_raw_char_byte_bounds_and_invalid_or_truncated_json(self):
        op=self.value.change_plan_report.operations[0]
        exact=self.raw+' '*(cd.MAX_RAW_OUTPUT_CHARS-len(self.raw))
        self.assertEqual(len(exact),cd.MAX_RAW_OUTPUT_CHARS)
        self.assertEqual(len(_parse_specification(exact,expected_change_ref='C1',operation=op).sections),6)
        with self.assertRaisesRegex(ValueError,'OUTPUT_TOO_LARGE'):
            _parse_specification(exact+' ',expected_change_ref='C1',operation=op)
        # A deliberately invalid JSON exercises byte gate precedence separately.
        exact_bytes='😀'*(cd.MAX_RAW_OUTPUT_BYTES//4)
        with self.assertRaisesRegex(ValueError,'JSON_FORMAT'):
            _parse_specification(exact_bytes,expected_change_ref='C1',operation=op)
        with self.assertRaisesRegex(ValueError,'OUTPUT_TOO_LARGE'):
            _parse_specification(exact_bytes+'x',expected_change_ref='C1',operation=op)
        with self.assertRaisesRegex(ValueError,'JSON_FORMAT'):
            _parse_specification(self.raw[:-1],expected_change_ref='C1',operation=op)

    def test_long_review_restart_web_and_markdown_preserve_entire_body(self):
        app=create_app(mvp_dir=self.rich,db_path=self.rich/'read.sqlite3',live_db_path=self.rich/'never.sqlite3')
        last=self.response['draft']['sections'][-1]['blocks'][-1]['claims'][0]['text']
        with TestClient(app,base_url='http://127.0.0.1') as client:
            page=client.get('/mvp/candidate?key='+self.key)
            markdown=client.get('/mvp/candidate.md?key='+self.key)
            self.assertEqual((page.status_code,markdown.status_code),(200,200))
            self.assertIn(b'maxlength="64000"',page.content)
            self.assertIn(last.encode(),page.content)
            self.assertIn(last.encode(),markdown.content)
            for ref in self.value.customer_evidence.quote_map():
                self.assertIn(ref.encode(),markdown.content)
        history=SQLiteLocalDraftReviewStore(self.output/'local-review.sqlite3').revisions(digest(self.raw))
        self.assertEqual(history[0].body_text.encode(),self.raw.encode())
        self.assertEqual(len(history[-1].candidate_decisions),18)
        self.assertIn(last,(self.output/'native-replay-review.md').read_text(encoding='utf-8'))

    def test_approved_long_text_premises_and_versions_cannot_reuse_old_review(self):
        for mutation in ('text','refs','reasoning','plan'):
            value=self.value
            response=deepcopy(self.response)
            claim=response['draft']['sections'][0]['blocks'][0]['claims'][1]
            if mutation=='text': claim['text']+=' Recheck scope.'
            elif mutation=='refs': claim['customer_refs'].pop()
            elif mutation=='reasoning': claim['proposal']['reasoning']+=' Recheck scope.'
            else: value=replace(value,customer_evidence=replace(value.customer_evidence,plan_version=value.customer_evidence.plan_version+1))
            check=self.inspect(response,value)
            self.assertFalse(effective_decisions(check,self.history[-1]))
            if mutation != 'plan':
                self.assertNotEqual(self.native_run(response,self.reviewed).status,cd.ContentDraftStatus.SUCCESS)
            else:
                # The changed version must be supplied to the checker; replaying
                # the unchanged original input would correctly still succeed.
                self.assertEqual(check.binding_sha256, self.inspect(response,value).binding_sha256)

    def test_long_claim_does_not_relax_numeric_source_or_label_safety(self):
        for mutation in ('numeric','model','editorial','ps'):
            response=deepcopy(self.response)
            claim=response['draft']['sections'][0]['blocks'][0]['claims'][1]
            if mutation=='numeric': claim['text']='It carries 99999 kg. '+claim['text']
            elif mutation=='model': claim['text']='NCX7 supports 650 kg for dynamic cutting. '+claim['text']
            elif mutation=='editorial': claim.update(claim_type='EDITORIAL_TRANSITION',customer_refs=[]);claim.pop('proposal')
            else: claim['page_refs']=['P1']
            self.assertTrue(self.inspect(response).errors)

    def test_input_material_and_request_envelope_exact_and_over_bound(self):
        prompt=cd.build_content_draft_prompt(self.value,'C1')
        async def run(material,system='Return JSON only.'):
            calls=[]
            def handler(request):
                calls.append(request.content)
                return httpx.Response(200,json={'choices':[{'message':{'content':'{}'},'finish_reason':'stop'}]})
            with patch.dict('os.environ',{'DEEPSEEK_API_KEY':'OFFLINE-TEST'}),patch.object(cd.ContentDraftPrompt,'material_json',return_value=material),patch.object(DeepSeekContentDraftWriter,'build_system_prompt',return_value=system):
                result=await DeepSeekContentDraftWriter(transport=httpx.MockTransport(handler)).write_content_draft(prompt)
            return result,calls
        result,calls=asyncio.run(run('x'*cd.MAX_USER_MATERIAL_CHARS))
        self.assertEqual(result.status,cd.ContentDraftGenerationStatus.SUCCESS)
        self.assertEqual(len(calls),1)
        result,calls=asyncio.run(run('x'*(cd.MAX_USER_MATERIAL_CHARS+1)))
        self.assertEqual(result.failure_kind,cd.ContentDraftGenerationFailureKind.INPUT_TOO_LARGE)
        self.assertFalse(calls)
        multibyte='😀'*(cd.MAX_USER_MATERIAL_BYTES//4)
        self.assertEqual(asyncio.run(run(multibyte))[0].status,cd.ContentDraftGenerationStatus.SUCCESS)
        self.assertFalse(asyncio.run(run(multibyte+'x'))[1])
        # Escaped quote expansion can exceed the envelope despite legal material.
        self.assertFalse(asyncio.run(run('"'*cd.MAX_USER_MATERIAL_CHARS))[1])

    def test_no_live_authorization_and_token_estimates_are_not_usage(self):
        p=json.loads((self.root/'real-request-preflight.json').read_bytes())
        self.assertFalse(p['permit_issued'])
        self.assertEqual(p['actual_spending_authorized'],0)
        self.assertEqual(p['status'],'BLOCKED_TOKEN_BOUND_CONFIRMATION')
        self.assertIsNone(self.result['budgets']['actual_usage'])
        self.assertGreater(self.result['budgets']['estimate_safety_margin_output_tokens'],0)

    def test_historical_v1_sqlite_artifact_reads_without_touching_original(self):
        from foreign_trade_geo_agent.storage.sqlite import SQLiteHistoryReader
        old=Path('docs/seo-autonomous-interpretation-2026-10-11/final-v2')
        summary=json.loads((old/'readiness.json').read_bytes())
        source=old/'B-rich-evidence/generation'/summary['request_sha256']/'history.sqlite3'
        # Generation binding differs from request hash; locate the retained DB.
        source=next((old/'B-rich-evidence/generation').glob('*/history.sqlite3'))
        with TemporaryDirectory() as temporary:
            destination=Path(temporary)/'history.sqlite3'
            shutil.copyfile(source,destination)
            artifact=SQLiteHistoryReader(destination).get_artifact(summary['test_review_replay']['artifact_id'])
            self.assertEqual(artifact.payload_version,1)
            self.assertEqual(artifact.payload.status,cd.ContentDraftStatus.SUCCESS)
            self.assertEqual(len(artifact.payload.drafts[0].blocks),6)

    def test_exact_request_envelope_char_and_byte_limits_and_one_above(self):
        prompt=cd.build_content_draft_prompt(self.value,'C1')
        async def run(system,material):
            calls=[]
            def handler(request):
                calls.append(request.content)
                return httpx.Response(200,json={'choices':[{'message':{'content':'{}'},'finish_reason':'stop'}]})
            with patch.dict('os.environ',{'DEEPSEEK_API_KEY':'OFFLINE-TEST'}),patch.object(cd.ContentDraftPrompt,'material_json',return_value=material),patch.object(DeepSeekContentDraftWriter,'build_system_prompt',return_value=system):
                result=await DeepSeekContentDraftWriter(transport=httpx.MockTransport(handler)).write_content_draft(prompt)
            return result,calls
        def envelope(system,material):
            return json.dumps(content_draft_request_payload(system,material),ensure_ascii=False,separators=(',',':'))
        overhead=len(envelope('',''))
        characters=cd.MAX_INPUT_ENVELOPE_CHARS-overhead
        material='"'*(characters//2)+'x'*(characters%2)
        self.assertEqual(len(envelope('',material)),cd.MAX_INPUT_ENVELOPE_CHARS)
        self.assertEqual(asyncio.run(run('',material))[0].status,cd.ContentDraftGenerationStatus.SUCCESS)
        self.assertFalse(asyncio.run(run('',material+'x'))[1])
        system='中'*(cd.MAX_SYSTEM_PROMPT_BYTES//3)+'x'*(cd.MAX_SYSTEM_PROMPT_BYTES%3)
        quotes=cd.MAX_INPUT_ENVELOPE_BYTES-cd.MAX_SYSTEM_PROMPT_BYTES-cd.MAX_USER_MATERIAL_BYTES-overhead
        emoji_bytes=cd.MAX_USER_MATERIAL_BYTES-quotes
        material='😀'*(emoji_bytes//4)+'x'*(emoji_bytes%4)+'"'*quotes
        self.assertEqual(len(envelope(system,material).encode()),cd.MAX_INPUT_ENVELOPE_BYTES)
        result,calls=asyncio.run(run(system,material))
        self.assertEqual(result.status,cd.ContentDraftGenerationStatus.SUCCESS)
        self.assertEqual(len(calls),1)
        # Same legal material byte count, but another ASCII character must be escaped.
        material=material.replace('x','"',1) if 'x' in material else material.replace('😀','""""',1)
        self.assertFalse(asyncio.run(run(system,material))[1])

    def test_long_incomplete_and_oversize_response_retention_are_never_success(self):
        from foreign_trade_geo_agent.adapters.retained_deepseek import receive_candidate
        async def attempt(raw):
            with TemporaryDirectory() as temporary:
                output=Path(temporary)
                metadata={}
                calls=[]
                def handler(request):
                    calls.append(request.content)
                    return httpx.Response(200,content=raw)
                with self.assertRaises(ValueError):
                    await receive_candidate(self.value,b'{}',httpx.MockTransport(handler),'OFFLINE-TEST',
                        output=output,metadata=metadata,validator=lambda v,t: self.fail('incomplete must not validate'),
                        detail=lambda *args: {})
                self.assertEqual(len(calls),1)
                self.assertEqual((output/'response-body.bin').read_bytes(),raw[:MAX_RESPONSE_BYTES])
                return metadata
        body=json.dumps({'model':'deepseek-flash','choices':[{'message':{'content':self.raw},'finish_reason':'length'}],
            'usage':{'prompt_tokens':100,'completion_tokens':16384,'total_tokens':16484}}).encode()
        incomplete=asyncio.run(attempt(body))
        self.assertEqual(incomplete['finish_reason'],'length')
        self.assertEqual(incomplete['usage']['completion_tokens'],16384)
        oversize=asyncio.run(attempt(b'x'*(MAX_RESPONSE_BYTES+1)))
        self.assertFalse(oversize['response_complete'])
        self.assertTrue(oversize['response_budget_exceeded'])


class FullArticleBudgetTests(unittest.TestCase):
    def test_finite_headroom_for_six_chapters_and_review_retention(self):
        self.assertEqual(cd.MAX_BLOCKS_PER_DRAFT, 24)
        self.assertEqual(cd.MAX_CLAIMS_PER_DRAFT, 48)
        self.assertEqual(ce.MAX_INTERPRETATION_CHARS, 1200)
        self.assertEqual(cd.MAX_CLAIM_CHARS, 300)  # legacy facts/P/S unchanged
        self.assertEqual(MAX_LOCAL_BODY, cd.MAX_RAW_OUTPUT_CHARS)
        self.assertGreater(MAX_RESPONSE_BYTES, cd.MAX_RAW_OUTPUT_BYTES)

    def test_request_explicit_json_mode_and_bounded_tokens(self):
        request = content_draft_request_payload('Return JSON only.', '{}')
        self.assertEqual(request['response_format'], {'type': 'json_object'})
        self.assertEqual(request['max_tokens'], 16384)
        self.assertEqual(request['temperature'], 0)
        self.assertEqual(request['thinking'], {'type': 'disabled'})
