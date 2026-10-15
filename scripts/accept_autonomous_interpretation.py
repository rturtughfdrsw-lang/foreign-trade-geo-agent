"""Offline native candidate -> explicit TEST review -> native replay.

No real model, balance, WordPress, live permit or authenticated human signoff.
Mock texts are independently scripted outputs, never inference input options.
"""
import argparse
import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from datetime import timedelta
import hashlib
import json
from pathlib import Path
import time
from unittest.mock import patch
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient

from scripts import accept_evidence_backed_article as scope_case
from scripts import accept_rich_buyer_guide as prior
from foreign_trade_geo_agent.core import content_draft as cd
from foreign_trade_geo_agent.core.evidence_intake import ArticleScopeCoverage, snapshot_digest, require
from foreign_trade_geo_agent.core.history import ArtifactRecord, ArtifactType, WorkflowRun, RunStatus
from foreign_trade_geo_agent.core.content_draft_review import ContentDraftReviewRequest
from foreign_trade_geo_agent.storage.serialization import _encode
from foreign_trade_geo_agent.storage.sqlite import SQLiteHistoryStore, SQLiteHistoryReader
from foreign_trade_geo_agent.workflows.evidence_intake import reviewed_draft_input
from foreign_trade_geo_agent.workflows.content_draft import ContentDraftWorkflow
from foreign_trade_geo_agent.workflows.content_draft_review import test_only_revalidate_candidate, ContentDraftReviewWorkflow
from foreign_trade_geo_agent.web.app import create_app
from foreign_trade_geo_agent.web.generation import MockArticleExecutor
from foreign_trade_geo_agent.web.candidate_review import LocalCandidateReview
from foreign_trade_geo_agent.reporting.content_draft_review import render_content_draft_review_markdown
from foreign_trade_geo_agent.web.experiment import freeze, FrozenWebExecutor, FrozenWebGeneration, code_hashes
from foreign_trade_geo_agent.storage.web_experiment import WebExperimentLedger


class FactsOnlyReviewer(prior.DossierReviewer):
    def assess(self, snapshot, *, now):
        return replace(super().assess(snapshot, now=now), interpretations=(),
            scope_coverage=ArticleScopeCoverage(True, 'Synthetic explicit scope matches all eight obligations.'))


# These are the simulated provider RESPONSE, not supplied reviewed options.
NEW_ANALYSIS = (
    'Exclude NCX7 for the larger fixture because its table width and static-load proposal are exceeded; keep NCX10 conditional on application checks. ',
    'An unloaded rating does not measure the tool-workpiece interaction needed for a purchasing decision. ',
    'A matched recipe is a useful starting point only when the intended part shares its recorded setup. ',
    'A result inside a proposed tolerance is not an agreed acceptance verdict; measurement uncertainty and the decision rule must be settled first. ',
    'The proposed procedure needs agreed responsibility for setup, disposition and repeat testing. ',
    'Separate dispatch triggers, remote training and initial response from arrival and recovery obligations. ',
)


def candidate_scope():
    # Explicit scope for the synthetic comparison: the measurement question
    # needs both trial records and proposed acceptance terms. This remains the
    # same native task/Plan, with the requirement map reviewed before writing.
    scope = scope_case.scope()
    sections = list(scope['section_briefs'])
    sections[3] = replace(sections[3], requirement_ids=('F4', 'F6'),
        explanation_goal='Compare recorded methods and uncertainty with proposed acceptance conditions and decision rules.')
    return {**scope, 'section_briefs': tuple(sections)}


def mock_response(value, facts):
    bundle = value.customer_evidence
    sections = []
    for brief, text, fact_id in zip(value.change_plan_report.operations[0].new_resource_spec.section_briefs,
                                    NEW_ANALYSIS, scope_case.DIRECT_FACTS):
        refs = tuple(f.fact_ref for source in bundle.sources for f in source.facts
                     if set(f.requirement_ids) & set(brief.requirement_ids))
        quote = next(f['quote'] for f in facts if f['fact_id'] == fact_id)
        direct_ref = next(r for r, q in bundle.quote_map().items() if q == quote)
        def claim(body, kind, refs=()):
            return dict(text=body, claim_type=kind, page_refs=[], source_refs=[], customer_refs=list(refs))
        analysis = claim(text + brief.limitations + ' ' + brief.procurement_action,
                         'EVIDENCE_BASED_INTERPRETATION', refs)
        analysis['proposal'] = dict(procurement_question=brief.reader_question,
            reasoning=text.strip(), assumptions='The buyer must confirm that the intended configuration and application match the recorded premises.',
            limitation=brief.limitations, procurement_action=brief.procurement_action)
        sections.append(dict(outline_heading=brief.heading, blocks=[dict(kind='PARAGRAPH', claims=[
            claim(quote, 'OBSERVED_PRODUCT_FACT', (direct_ref,)), analysis])]))
    sections[-1]['blocks'][0]['claims'].append(claim(
        'Send the drawing, material, fixture layout and acceptance priorities to request a scoped quotation.', 'CALL_TO_ACTION'))
    return dict(draft=dict(change_ref='C1', draft_type='NEW_RESOURCE_DRAFT', sections=sections))


def persist_replay(output, value, draft):
    """Same native HistoryStore and Review used by ordinary Mock generation."""
    history = SQLiteHistoryStore(output / 'history.sqlite3')
    now, run_id, artifact_id = datetime.now(UTC), str(uuid4()), str(uuid4())
    history.create_run(WorkflowRun(run_id, 'https://novacnc.example:443', 'offline_candidate_replay',
        now, None, RunStatus.RUNNING, None, None))
    class CapturedWriter:
        async def write_content_draft(self, prompt):
            return cd.ContentDraftGeneration('synthetic', 'offline-replay', cd.ContentDraftGenerationStatus.SUCCESS,
                (output / 'model-output.txt').read_text(encoding='utf-8'), None)
    report = asyncio.run(ContentDraftWorkflow(CapturedWriter(), max_repair_attempts=0).run(value))
    require(report.status is cd.ContentDraftStatus.SUCCESS and report.drafts[0] == draft)
    for kind, payload in ((ArtifactType.SITE_CONTENT, value.site_content),
            (ArtifactType.CONTENT_OPPORTUNITY, value.opportunity_report),
            (ArtifactType.CHANGE_PLAN, value.change_plan_report), (ArtifactType.CONTENT_DRAFT, report)):
        history.append_artifact(ArtifactRecord(artifact_id if kind is ArtifactType.CONTENT_DRAFT else str(uuid4()),
            run_id, kind, 1, now, payload))
    history.finish_run(run_id, status=RunStatus.SUCCEEDED, completed_at=datetime.now(UTC))
    reader = SQLiteHistoryReader(output / 'history.sqlite3')
    require(reader.get_artifact(artifact_id).payload == report)
    view = ContentDraftReviewWorkflow(history_reader=reader).review(ContentDraftReviewRequest(run_id, artifact_id, 'D1'))
    (output / 'native-replay-review.md').write_text(render_content_draft_review_markdown(view), encoding='utf-8')
    return dict(run_id=run_id, artifact_id=artifact_id, native_status=report.status.value)


def prepare(directory, *, response_factory=None):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    protected = prior.protected_hashes()
    facts, supplements = prior.package(directory / 'customer-materials')
    rich = directory / 'B-rich-evidence'
    rich.mkdir()
    with patch('httpx.AsyncHTTPTransport', side_effect=AssertionError('NO LIVE HTTP')), \
         patch('httpx.HTTPTransport', side_effect=AssertionError('NO LIVE HTTP')):
        snapshot, assessment, reviewer, store = asyncio.run(prior.prepare_native(rich, facts, supplements,
            scope=candidate_scope(), reviewer_factory=FactsOnlyReviewer))
        require(not assessment.interpretations)
        low = asyncio.run(scope_case.structured_low_control(directory / 'A-low-evidence',
            store.get_revision(snapshot.task.project_id, snapshot.task.task_id, 1).planning_input, supplements[0]))
        value = reviewed_draft_input(snapshot, assessment, now=datetime.now(UTC), propose_interpretations=True)
        response = (response_factory or mock_response)(value, facts)
        raw = json.dumps(response, ensure_ascii=False, separators=(',', ':'))
        prior.save(rich / 'frozen-native-input.json', value)
        prior.save(rich / 'mock-response.json', response)
        requests = []
        def handler(request):
            requests.append(request.content)
            return httpx.Response(200, json={'model': 'deepseek-flash', 'choices': [dict(
                message={'content': raw}, finish_reason='stop')]})
        app = create_app(mvp_dir=rich, db_path=rich / 'demo.sqlite3', live_db_path=rich / 'live.sqlite3')
        service = app.state.mvp_service
        service.scope_reviewer = reviewer
        service.generation_executor = MockArticleExecutor(task=snapshot.task, template=value,
            transport=httpx.MockTransport(handler))
        with TestClient(app, base_url='http://127.0.0.1') as client:
            client.get('/mvp/generate')
            state = service.generation.view()
            require(state['generation_allowed'])
            key = state['binding_sha256']
            client.post('/mvp/generate', data=dict(csrf_token=app.state.csrf_token, binding_sha256=key))
            for _ in range(200):
                state = service.generation.view()
                if state['generation_state'] != 'RUNNING':
                    break
                time.sleep(.01)
            prior.save(rich / 'generation-state.json', state)
            require(state['generation_state'] == 'PENDING_REVIEW')
            candidate = LocalCandidateReview(service)
            view = candidate.load(key)
            require(not view['candidate_check'].errors)
            for endpoint, filename in (('/mvp/candidate?key='+key, 'candidate-pending.html'),
                                       ('/mvp/candidate.md?key='+key, 'candidate-pending.md')):
                page = client.get(endpoint)
                require(page.status_code == 200)
                (rich / filename).write_bytes(page.content)
            # Reject and request changes are historical, then exact explicit
            # synthetic approvals exercise replay. These are not human signoff.
            proposals = tuple(c for c in view['candidate_check'].claims if c.proposal)
            for decision in ('REJECT', 'REQUEST_CHANGES'):
                view = candidate.load(key)
                candidate.save(key=key, version=str(view['candidate_latest'].version),
                    binding=view['candidate_check'].binding_sha256, claim_id=proposals[0].claim_id,
                    decision=decision, note='SYNTHETIC offline decision lifecycle test.', body_text=raw)
            for claim in proposals:
                view = candidate.load(key)
                result = client.post('/mvp/candidate', data=dict(csrf_token=app.state.csrf_token,
                    key=key, version=str(view['candidate_latest'].version), binding=view['candidate_check'].binding_sha256,
                    claim_id=claim.claim_id, decision='APPROVE', note='SYNTHETIC TEST-only review of exact premises and scope; not human signoff.',
                    body_text=raw), follow_redirects=False)
                require(result.status_code == 303)
            view = candidate.load(key)
            reviewed, draft = test_only_revalidate_candidate(snapshot, reviewer.assess(snapshot, now=datetime.now(UTC)),
                value, raw, view['candidate_latest'], now=datetime.now(UTC))
            replay = persist_replay(service.generation.root / key, reviewed, draft)
            (rich / 'candidate-reviewed.html').write_bytes(client.get('/mvp/candidate?key='+key).content)
            (rich / 'candidate-reviewed.md').write_bytes(client.get('/mvp/candidate.md?key='+key).content)
            prior.save(rich / 'native-reviewed-input.json', reviewed)
            prior.save(rich / 'review-history.json', view['candidate_history'])
            client.post('/mvp/generate', data=dict(csrf_token=app.state.csrf_token, binding_sha256=key))
            require(len(requests) == 1)
            # Exercise the future isolated experiment runner with MOCK only.
            # No LIVE permit, credentials or production admission are created.
            frozen_bundle = freeze(service)
            ledger = WebExperimentLedger(rich / 'frozen-MOCK-only-ledger.sqlite3')
            ledger.initialize()
            frozen_manifest = json.loads((rich / 'web-experiment/bundle.json').read_bytes())
            ledger.issue('SYNTHETIC-MOCK-PREFLIGHT', frozen_bundle, rich,
                frozen_manifest['request_sha256'], 'MOCK', datetime.now(UTC)+timedelta(minutes=5))
            service.generation_executor = FrozenWebExecutor(rich, frozen_bundle, ledger, 'SYNTHETIC-MOCK-PREFLIGHT',
                transport=httpx.MockTransport(handler))
            service.generation = FrozenWebGeneration(service)
            client.get('/mvp/generate')
            frozen_state = service.generation.view()
            require(frozen_state['generation_allowed'])
            client.post('/mvp/generate', data=dict(csrf_token=app.state.csrf_token, binding_sha256=frozen_bundle))
            for _ in range(200):
                frozen_state = service.generation.view()
                if frozen_state['generation_state'] != 'RUNNING':
                    break
                time.sleep(.01)
            prior.save(rich / 'frozen-mock-preflight.json', frozen_state)
            require(frozen_state['generation_state'] == 'PENDING_REVIEW'
                and frozen_state['attempt']['real_requests'] == 0 and len(requests) == 2)
            require(client.get('/mvp/candidate?key='+frozen_bundle).status_code == 200)
    require(protected == prior.protected_hashes())
    request = requests[0]
    request_data = json.loads(request)
    budgets = dict(request_bytes=len(request), request_chars=len(request.decode()),
        material_chars=len(cd.build_content_draft_prompt(value, 'C1').material_json()),
        mock_output_bytes=len(raw.encode()), mock_output_chars=len(raw),
        claims=sum(len(b.get('claims', b.get('items', []))) for s in response['draft']['sections'] for b in s['blocks']),
        blocks=sum(len(s['blocks']) for s in response['draft']['sections']),
        max_claims=cd.MAX_CLAIMS_PER_DRAFT, max_blocks=cd.MAX_BLOCKS_PER_DRAFT,
        max_output_tokens=request_data['max_tokens'], max_raw_output_chars=cd.MAX_RAW_OUTPUT_CHARS,
        output_token_count='UNKNOWN_NO_DEEPSEEK_TOKENIZER_OR_USAGE',
        deeper_layout=dict(sections=6, fact_plus_two_analysis_claims_and_cta=19,
            two_paragraphs_per_section_and_cta=13, state=('WITHIN_STRUCTURAL_BUDGET'
                if cd.MAX_CLAIMS_PER_DRAFT >= 19 and cd.MAX_BLOCKS_PER_DRAFT >= 13 else 'BLOCKED_BY_CURRENT_CLAIM_AND_BLOCK_BUDGET')),
        bounded_request=True, no_silent_truncation=True)
    prior.save(directory / 'budgets.json', budgets)
    # Exact request is frozen for inspection only; no executor, key or permit.
    (directory / 'flash-request.FROZEN-NOT-AUTHORIZED.json').write_bytes(request)
    price_snapshot = Path('docs/seo-model-comparison-preflight-2026-10-11/official-api-notes.md')
    cost = dict(status='PROVISIONAL_OFFLINE_ASSUMPTIONS_NOT_CURRENT_QUOTE', currency='CNY',
        price_source=str(price_snapshot), price_source_sha256=hashlib.sha256(price_snapshot.read_bytes()).hexdigest(),
        peak_input_cache_miss_per_million=2, peak_output_per_million=8,
        assumed_input_token_budget=32768, max_output_tokens=request_data['max_tokens'], max_requests=1,
        provisional_peak_estimate_cny=(32768*2+request_data['max_tokens']*8)/1000000,
        actual_token_count='UNKNOWN', tokenizer_bound_verified=False, current_price_verified=False,
        actual_spending_authorized=0, real_permit_issued=False, retry_count=0, timeout_seconds=60)
    prior.save(directory / 'flash-cost-preflight.json', cost)
    summary = dict(offline_chain='READY', next_real_quality_experiment='REQUIRES_SEPARATE_FULL_ARTICLE_PREFLIGHT',
        low_status=low.status.value, low_writer_calls=0, documents=7, facts=43,
        input_preapproved_interpretations=0, new_model_candidates=len(proposals),
        candidate_state='PENDING_SEMANTIC_REVIEW', test_review_replay=replay,
        binding_sha256=view['candidate_check'].binding_sha256, raw_sha256=hashlib.sha256(raw.encode()).hexdigest(),
        request_sha256=hashlib.sha256(request).hexdigest(), budgets=budgets,
        frozen_bundle_sha256=frozen_bundle, frozen_mock_retention_preflight='PASS', cost_preflight=cost,
        real_model_requests=0, wordpress_requests=0, production_authorized=False, authenticated_human_signoff=False,
        limits=['Mock output is scripted, not a DeepSeek writing result.',
            'Semantic accuracy, premise completeness, commercial value and CTA need human judgment.',
            'Broad task-to-question-map autonomy remains out of scope; scope is explicit.',
            'Full six-chapter quality experiment needs output feasibility and current price/cost preflight.'],
        comparison=dict(control='Previous 170-word low-evidence article', treatment='Seven synthetic documents and 43 facts; autonomous interpretation candidates',
            dimensions=['accuracy','explanation depth','purchasing value','repetition','structure','CTA'],
            single_variable_experiment=False),
        code_sha256=code_hashes(),
        historical_freezes_unchanged=True)
    prior.save(directory / 'readiness.json', summary)
    prior.save(directory / 'artifact-sha256.json', {p.relative_to(directory).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(directory.rglob('*')) if p.is_file()})
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    print(json.dumps(prepare(parser.parse_args().output_dir), ensure_ascii=False, indent=2))
