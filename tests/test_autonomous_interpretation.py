"""New reasoning can be proposed and retained without self-issued authority."""
import asyncio
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import shutil
import time
import httpx

from scripts import accept_autonomous_interpretation as case
from foreign_trade_geo_agent.core import content_draft as cd
from foreign_trade_geo_agent.core.content_draft_review import LocalDraftRevision
from foreign_trade_geo_agent.core.draft_candidate_review import CandidateDecision, effective_decisions
from foreign_trade_geo_agent.core.evidence_intake import IntakeSnapshot, SemanticAssessment
from foreign_trade_geo_agent.storage.serialization import _decode, _encode
from foreign_trade_geo_agent.storage.content_draft_review import SQLiteLocalDraftReviewStore
from foreign_trade_geo_agent.workflows.content_draft import ContentDraftWorkflow, inspect_candidate_output
from foreign_trade_geo_agent.workflows.content_draft_review import test_only_revalidate_candidate
from foreign_trade_geo_agent.workflows.evidence_intake import EvidenceIntakeDraftAdmission
from foreign_trade_geo_agent.storage.evidence_intake import SQLiteEvidenceIntakeStore
from foreign_trade_geo_agent.web.app import create_app
from foreign_trade_geo_agent.web.candidate_review import LocalCandidateReview
from foreign_trade_geo_agent.web.generation import MockArticleExecutor
from fastapi.testclient import TestClient


class AutonomousInterpretationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name) / 'case'
        cls.result = case.prepare(cls.root)
        cls.rich = cls.root / 'B-rich-evidence'
        cls.value = _decode(json.loads((cls.rich / 'frozen-native-input.json').read_bytes()), cd.ContentDraftInput)
        cls.reviewed = _decode(json.loads((cls.rich / 'native-reviewed-input.json').read_bytes()), cd.ContentDraftInput)
        cls.snapshot = _decode(json.loads((cls.rich / 'snapshot.json').read_bytes()), IntakeSnapshot)
        cls.assessment = _decode(json.loads((cls.rich / '04-test-only-review.json').read_bytes())['assessment'], SemanticAssessment)
        cls.response = json.loads((cls.rich / 'mock-response.json').read_bytes())
        cls.key = json.loads((cls.rich / 'generation-state.json').read_bytes())['binding_sha256']
        cls.output = cls.rich / 'generation' / cls.key
        cls.raw = (cls.output / 'model-output.txt').read_text(encoding='utf-8')
        cls.history = SQLiteLocalDraftReviewStore(cls.output / 'local-review.sqlite3').revisions(case.hashlib.sha256(cls.raw.encode()).hexdigest())

    def check_response(self, response, value=None, snapshot=None):
        value = value or self.value
        return inspect_candidate_output(value, json.dumps(response, ensure_ascii=False, separators=(',', ':')),
            current_snapshot_sha256=snapshot or value.customer_evidence.snapshot_sha256)

    def run_native(self, response, value=None):
        class Writer:
            async def write_content_draft(self, prompt):
                return cd.ContentDraftGeneration('synthetic', 'test', cd.ContentDraftGenerationStatus.SUCCESS,
                    json.dumps(response, separators=(',', ':')), None)
        return asyncio.run(ContentDraftWorkflow(Writer(), max_repair_attempts=0).run(value or self.value))

    def test_zero_preapproved_options_new_candidates_independent_multi_fact_replay(self):
        self.assertFalse(self.assessment.interpretations)
        self.assertFalse(self.value.customer_evidence.interpretations)
        check = self.check_response(self.response)
        self.assertEqual(check.state, 'PENDING_SEMANTIC_REVIEW')
        self.assertFalse(check.errors)
        candidates = [c for c in check.claims if c.proposal]
        self.assertEqual(len(candidates), 6)
        self.assertTrue(all(len(c.refs) >= 2 and c.evidence_details for c in candidates))
        self.assertIn('Exclude NCX7', candidates[0].text)
        self.assertIn('keep NCX10 conditional', candidates[0].text)
        self.assertIn('E2', {r.split('.')[0] for r in candidates[0].refs})
        self.assertIn('E5', {r.split('.')[0] for r in candidates[0].refs})
        self.assertTrue({'E3', 'E6'} <= {r.split('.')[0] for r in candidates[3].refs})
        self.assertIn('not an agreed acceptance verdict', candidates[3].text)
        self.assertEqual({r for c in check.claims for r in c.refs}, set(self.value.customer_evidence.quote_map()))
        self.assertEqual(self.result['test_review_replay']['native_status'], 'success')
        self.assertEqual(self.run_native(self.response, self.reviewed).status, cd.ContentDraftStatus.SUCCESS)

    def test_unreviewed_candidate_never_admitted_and_explicit_reviews_are_test_only(self):
        self.assertEqual(self.run_native(self.response).error, 'INTERPRETATION_PENDING_REVIEW')
        self.assertFalse(self.result['production_authorized'])
        self.assertFalse(self.result['authenticated_human_signoff'])
        self.assertTrue(all(i.proposal for i in self.reviewed.customer_evidence.interpretations))
        admission = EvidenceIntakeDraftAdmission(SQLiteEvidenceIntakeStore(self.rich / 'interactive-intake.sqlite3'),
            self.snapshot.task.project_id, self.snapshot.task.task_id)
        self.assertIsNotNone(admission.rejection_reason(self.reviewed))

    def test_low_evidence_still_blocks_writer(self):
        self.assertEqual((self.result['low_status'], self.result['low_writer_calls']), ('BLOCKED', 0))

    def test_forged_review_authority_and_unknown_fields_rejected_by_native_parser(self):
        for key in ('approved', 'review_status', 'production_authorized', 'signature', 'reviewer_id'):
            response = deepcopy(self.response)
            response['draft']['sections'][0]['blocks'][0]['claims'][1]['proposal'][key] = True
            with self.assertRaisesRegex(ValueError, 'FIELD_CONTRACT'):
                self.check_response(response)

    def test_unknown_fact_and_changed_direct_quote_rejected(self):
        for refs, body, expected in ((['E1.F99'], None, 'UNKNOWN_CUSTOMER_REFERENCE'),
                (None, 'The supplied equipment handles any steel workpiece.', 'CUSTOMER_QUOTE_MISMATCH')):
            response = deepcopy(self.response)
            claim = response['draft']['sections'][0]['blocks'][0]['claims'][0]
            if refs:
                claim['customer_refs'] = refs
            if body:
                claim['text'] = body
            self.assertIn(expected, str(self.check_response(response).errors))

    def test_wrong_numeric_unit_subject_and_condition_cannot_use_joined_fact_catalogue(self):
        for text in ('The fixture carries 99999 kg.', 'The fixture carries 520 lb.',
                     'NCX7 supports 650 kg for dynamic cutting.', 'NCX10 supports 400 kg off-center.'):
            response = deepcopy(self.response)
            claim = response['draft']['sections'][0]['blocks'][0]['claims'][1]
            claim['text'] = text + ' ' + claim['proposal']['limitation'] + ' ' + claim['proposal']['procurement_action']
            errors = str(self.check_response(response).errors)
            self.assertTrue('NUMERIC_NOT_GROUNDED' in errors or 'NUMERIC_CONTEXT_NOT_PRESERVED' in errors, errors)

    def test_model_reasoning_metadata_cannot_hide_new_numbers_or_promotion(self):
        for reasoning in ('It delivers 99999 rpm.', 'It is guaranteed to cut all materials.'):
            response = deepcopy(self.response)
            response['draft']['sections'][0]['blocks'][0]['claims'][1]['proposal']['reasoning'] = reasoning
            self.assertTrue(self.check_response(response).errors)

    def test_omitted_limit_premise_and_changed_reasoning_invalidate_approval(self):
        for field in ('text', 'premise', 'assumptions', 'reasoning', 'limitation', 'procurement_action'):
            response = deepcopy(self.response)
            claim = response['draft']['sections'][0]['blocks'][0]['claims'][1]
            if field == 'text':
                claim['text'] = claim['text'].replace(claim['proposal']['limitation'], '')
            elif field == 'premise':
                claim['customer_refs'].pop()
            else:
                claim['proposal'][field] += ' Reconfirm.'
            check = self.check_response(response)
            self.assertEqual(effective_decisions(check, self.history[-1]), {})
            self.assertNotEqual(self.run_native(response, self.reviewed).status, cd.ContentDraftStatus.SUCCESS)

    def test_stale_task_plan_evidence_and_source_versions_invalidate_all_old_reviews(self):
        bundle = self.value.customer_evidence
        for updated in (replace(bundle, task_version=bundle.task_version+1),
                        replace(bundle, plan_version=bundle.plan_version+1),
                        replace(bundle, evidence_version=bundle.evidence_version+1),
                        replace(bundle, sources=(replace(bundle.sources[0], evidence_version=bundle.sources[0].evidence_version-1), *bundle.sources[1:]))):
            check = self.check_response(self.response, replace(self.value, customer_evidence=updated))
            self.assertEqual(effective_decisions(check, self.history[-1]), {})
        check = self.check_response(self.response, snapshot='a'*64)
        self.assertIn('STALE_EVIDENCE_SNAPSHOT', check.errors)
        self.assertFalse(effective_decisions(check, self.history[-1]))

    def test_semantic_negative_examples_remain_pending_then_explicit_reject_blocks_replay(self):
        # Deterministic matching cannot prove semantic entailment. These claims
        # get NO delivery eligibility even if all lexical checks pass.
        for text in ('The recorded setup establishes cutting capability for hardened alloys.',
                     'An unloaded rating establishes strong torque during heavy cutting.',
                     'The proposed acceptance schedule is an effective contractual commitment.',
                     'The smaller machine shares every capability of the larger machine.'):
            response = deepcopy(self.response)
            claim = response['draft']['sections'][0]['blocks'][0]['claims'][1]
            claim['text'] = text + ' ' + claim['proposal']['limitation'] + ' ' + claim['proposal']['procurement_action']
            raw = json.dumps(response, separators=(',', ':'))
            check = self.check_response(response)
            self.assertFalse(check.production_authorized)
            self.assertNotEqual(self.run_native(response).status, cd.ContentDraftStatus.SUCCESS)
            # Exact reviewer rejection is appendable even for a semantic error
            # that deterministic checks cannot establish.
            with TemporaryDirectory() as temp:
                store = SQLiteLocalDraftReviewStore(Path(temp) / 'review.sqlite3')
                revision = store.append(origin_sha256=check.raw_sha256, expected_version=0, original_body=raw,
                    body_text=raw, note='Reject: unsupported inference or missing applicability premise.',
                    status='CHANGES_REQUESTED', frozen_evidence_sha256=self.value.customer_evidence.snapshot_sha256,
                    observed_evidence_sha256=self.value.customer_evidence.snapshot_sha256, saved_at=datetime.now(UTC),
                    candidate_decisions=(CandidateDecision(check.binding_sha256, 'CL2', 'REJECT', 'Unsupported semantic conclusion.'),))
                with self.assertRaises(ValueError):
                    test_only_revalidate_candidate(self.snapshot, self.assessment, self.value, raw, revision, now=datetime.now(UTC))

    def test_editorial_and_cta_fact_laundering_rejected_neutral_transition_allowed(self):
        for kind in ('EDITORIAL_TRANSITION', 'CALL_TO_ACTION', 'GENERAL_TECHNICAL_CONTEXT'):
            response = deepcopy(self.response)
            response['draft']['sections'][0]['blocks'][0]['claims'].append(dict(
                text='The equipment handles every steel workpiece.', claim_type=kind, page_refs=[], source_refs=[], customer_refs=[]))
            self.assertTrue(self.check_response(response).errors)
        response = deepcopy(self.response)
        response['draft']['sections'][0]['blocks'][0]['claims'].append(dict(
            text='The next section considers the purchasing decision.', claim_type='EDITORIAL_TRANSITION',
            page_refs=[], source_refs=[], customer_refs=[]))
        self.assertFalse(self.check_response(response).errors)

    def test_review_journal_keeps_original_rejection_change_request_and_approvals(self):
        self.assertEqual(self.history[0].body_text, self.raw)
        self.assertFalse(self.history[0].candidate_decisions)
        self.assertEqual([r.candidate_decisions[0].decision for r in self.history[1:3]], ['REJECT', 'REQUEST_CHANGES'])
        self.assertEqual(len(self.history[-1].candidate_decisions), 6)
        self.assertTrue(all(r.body_text == self.raw for r in self.history))
        self.assertEqual(_decode(_encode(self.history[-1]), LocalDraftRevision), self.history[-1])

    def test_web_readonly_restart_and_markdown_show_all_premises_and_reject_browser_authority(self):
        app = create_app(mvp_dir=self.rich, db_path=self.rich/'read.sqlite3', live_db_path=self.rich/'never.sqlite3')
        with TestClient(app, base_url='http://127.0.0.1') as client:
            page = client.get('/mvp/candidate?key='+self.key)
            self.assertEqual(page.status_code, 200)
            markdown = client.get('/mvp/candidate.md?key='+self.key)
            self.assertEqual(markdown.status_code, 200)
            for ref in self.value.customer_evidence.quote_map():
                self.assertIn(ref.encode(), page.content)
                self.assertIn(ref.encode(), markdown.content)
            self.assertIn(b'APPROVE', page.content)
            self.assertEqual(client.post('/mvp/candidate', data={'csrf_token':app.state.csrf_token,
                'production_authorized':'true'}).status_code, 422)
            self.assertEqual(client.get('/mvp/candidate?key=../../secret').status_code, 409)

    def test_output_budgets_are_bounded_and_deeper_layout_has_structural_room(self):
        response = deepcopy(self.response)
        for section in response['draft']['sections']:
            section['blocks'].append(dict(kind='PARAGRAPH', claims=[dict(
                text='Consider the following questions before proceeding.', claim_type='EDITORIAL_TRANSITION',
                page_refs=[], source_refs=[], customer_refs=[])]))
        errors = str(self.check_response(response).errors)
        self.assertNotIn('BLOCK_BUDGET', errors)
        self.assertNotIn('CLAIM_BUDGET', errors)
        self.assertEqual(self.result['budgets']['max_output_tokens'], cd.MAX_PROVIDER_TOKENS)
        self.assertLess(self.result['budgets']['request_bytes'], cd.MAX_INPUT_ENVELOPE_BYTES)
        self.assertEqual(self.result['next_real_quality_experiment'], 'REQUIRES_SEPARATE_FULL_ARTICLE_PREFLIGHT')

    def test_rejected_transport_output_is_retained_visible_and_edit_resets_every_decision(self):
        with TemporaryDirectory() as temp:
            root = Path(temp) / 'rich'
            shutil.copytree(self.rich, root, ignore=shutil.ignore_patterns('generation'))
            response = deepcopy(self.response)
            response['draft']['sections'][0]['blocks'][0]['claims'][1]['customer_refs'][0] = 'E1.F99'
            raw = json.dumps(response, separators=(',', ':'))
            facts = json.loads((self.root/'customer-materials/facts.json').read_bytes())
            reviewer = case.FactsOnlyReviewer(facts, tuple(e.supplement for e in self.snapshot.active_evidence))
            app = create_app(mvp_dir=root, db_path=root/'demo2.sqlite3', live_db_path=root/'never.sqlite3')
            service = app.state.mvp_service
            service.scope_reviewer = reviewer
            service.generation_executor = MockArticleExecutor(task=self.snapshot.task, template=self.value,
                transport=httpx.MockTransport(lambda r: httpx.Response(200, json={'model':'deepseek-flash',
                    'choices':[{'message':{'content':raw},'finish_reason':'stop'}]})))
            with TestClient(app, base_url='http://127.0.0.1') as client:
                client.get('/mvp/generate')
                key = service.generation.view()['binding_sha256']
                client.post('/mvp/generate', data={'csrf_token':app.state.csrf_token,'binding_sha256':key})
                for _ in range(200):
                    if service.generation.view()['generation_state'] != 'RUNNING':
                        break
                    time.sleep(.01)
                self.assertEqual(service.generation.view()['generation_state'], 'PENDING_REVIEW')
                page = client.get('/mvp/candidate?key='+key)
                self.assertIn(b'UNKNOWN_CUSTOMER_REFERENCE', page.content)
                candidate = LocalCandidateReview(service)
                view = candidate.load(key)
                self.assertEqual(view['candidate_original'], raw)
                fixed_raw = json.dumps(self.response, separators=(',', ':'))
                revision = candidate.save(key=key, version='1', binding=view['candidate_check'].binding_sha256,
                    claim_id='', decision='EDIT', note='Correct invalid reference, retain original output.', body_text=fixed_raw)
                self.assertFalse(revision.candidate_decisions)
                updated = candidate.load(key)
                self.assertFalse(updated['candidate_check'].errors)
                self.assertEqual(updated['candidate_original'], raw)
                self.assertEqual(updated['candidate_history'][0].body_text, raw)
                self.assertFalse(updated['candidate_decisions'])

    def test_legacy_freeze_snapshot_hash_and_optional_serialization_remain_compatible(self):
        from foreign_trade_geo_agent.core.evidence_intake import snapshot_digest
        folder = Path('docs/seo-evidence-backed-mvp-final-2026-10-11')
        old = _decode(json.loads((folder/'B-rich-evidence/snapshot.json').read_bytes()), IntakeSnapshot)
        expected = json.loads((folder/'readiness.json').read_bytes())['task_snapshot_sha256']
        self.assertEqual(snapshot_digest(old), expected)
        self.assertNotIn('propose_interpretations', _encode(old.planning_input))
        legacy_revision = _encode(self.history[0])
        self.assertNotIn('candidate_decisions', legacy_revision)
        self.assertEqual(_decode(legacy_revision, LocalDraftRevision), self.history[0])

    def test_raw_text_is_not_silently_normalized_and_oversize_output_is_not_truncated(self):
        response = deepcopy(self.response)
        claim = response['draft']['sections'][0]['blocks'][0]['claims'][1]
        claim['text'] = claim['text'].replace(' ', '  ', 1)
        self.assertIn('CANDIDATE_TEXT_NOT_CANONICAL', str(self.check_response(response).errors))
        self.assertIn('  ', claim['text'])
        with self.assertRaisesRegex(ValueError, 'OUTPUT_TOO_LARGE'):
            inspect_candidate_output(self.value, self.raw + ' '*cd.MAX_RAW_OUTPUT_CHARS,
                current_snapshot_sha256=self.value.customer_evidence.snapshot_sha256)

    def test_crlf_native_json_is_saved_exactly_without_rewriting_original(self):
        raw = json.dumps(self.response, indent=2).replace('\n', '\r\n')
        check = inspect_candidate_output(self.value, raw,
            current_snapshot_sha256=self.value.customer_evidence.snapshot_sha256)
        self.assertFalse(check.errors)
        with TemporaryDirectory() as temp:
            journal = SQLiteLocalDraftReviewStore(Path(temp)/'review.sqlite3')
            revision = journal.append(origin_sha256=check.raw_sha256, expected_version=0,
                original_body=raw, body_text=raw, note='Original\r\nUnreviewed', status='PENDING_REVIEW',
                frozen_evidence_sha256=self.value.customer_evidence.snapshot_sha256,
                observed_evidence_sha256=self.value.customer_evidence.snapshot_sha256, saved_at=datetime.now(UTC))
            self.assertEqual(journal.revisions(check.raw_sha256)[0].body_text.encode(), raw.encode())
            self.assertEqual(revision.body_sha256, check.raw_sha256)
