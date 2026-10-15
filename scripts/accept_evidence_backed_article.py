"""Offline positive/negative acceptance through the existing SEO MVP boundaries.

Scripted planning/review/writing exercises contracts; it does not measure a real
model's writing ability. No production transports, credentials or live permits.
"""
import argparse
import asyncio
from dataclasses import replace
from datetime import UTC, datetime
import json
from pathlib import Path
import time
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from scripts import accept_rich_buyer_guide as previous
from scripts import novacnc_buyer_fixture as fixture
from foreign_trade_geo_agent.core.change_plan import ArticleSectionBrief
from foreign_trade_geo_agent.core.evidence_intake import (
    ReviewedInterpretation, require, snapshot_digest, EvidenceTask, CustomerSubmission, CustomerContext,
    SemanticAssessment, RequirementDecision, SupportVerdict, ArticleScopeCoverage,
)
from foreign_trade_geo_agent.storage.evidence_intake import SQLiteEvidenceIntakeStore
from foreign_trade_geo_agent.storage.serialization import _encode
from foreign_trade_geo_agent.web.app import create_app
from foreign_trade_geo_agent.web.generation import MockArticleExecutor
from foreign_trade_geo_agent.web.mvp_application import MVPApplicationService
from foreign_trade_geo_agent.workflows.evidence_intake import reviewed_draft_input, EvidenceIntakeWorkflow, EvidenceIntakeDraftAdmission
from foreign_trade_geo_agent.workflows.content_draft import ContentDraftWorkflow
from foreign_trade_geo_agent.workflows.change_plan import ChangePlanWorkflow
from foreign_trade_geo_agent.adapters.retained_intake_plan import RetainedIntakePlanWriter


# Analyst-authored scope for this fictional case, never a keyword classifier.
QUESTIONS = (
    (fixture.HEADINGS[2], 'Which configuration should enter the shortlist?',
     'Compare nominal dimensions, combined loads and conditional model choices.', ('F1', 'F5'),
     'Fixture clearance and dynamic loads remain unassessed.', 'Send the fixture layout for configuration review.'),
    (fixture.HEADINGS[3], 'What do spindle ratings establish under the recorded conditions?',
     'Separate unloaded ratings and nameplate power from cutting capability.', ('F2',),
     'Loaded cutting capability remains unassessed.', 'Request a representative loaded trial and torque records.'),
    (fixture.HEADINGS[0], 'Does the supplied trial represent the intended material and cycle?',
     'Match material, geometry, tooling, coolant, path and sample limits.', ('F3',),
     'Other applications require new representative trials.', 'Submit the intended material, drawing and complete cycle.'),
    (fixture.HEADINGS[4], 'What do measured results establish for acceptance?',
     'Interpret methods, sample and environment before using a result as a criterion.', ('F4',),
     'The samples do not establish production capability.', 'Agree a representative measurement and uncertainty procedure.'),
    (fixture.HEADINGS[1], 'What needs agreement before the purchase order?',
     'Turn RFQ and proposed acceptance terms into explicit responsibilities.', ('F6',),
     'Proposed criteria require written agreement.', 'Send the RFQ fields and negotiate acceptance responsibilities.'),
    (fixture.HEADINGS[5], 'What delivery and support terms apply to the quoted configuration?',
     'Check triggers, exclusions, document versions, training and support proposals.', ('F7', 'F8'),
     'The proposals are not signed commitments.', 'Confirm the configuration register and commercial terms in writing.'),
)
EXPLANATIONS = (
    'Nominal table dimensions and centered static load can narrow a shortlist. Fixture clearance and dynamic loads remain unassessed. Send the fixture layout for configuration review.',
    'Unloaded speed and motor nameplate power describe different conditions from a cutting cycle. Loaded cutting capability remains unassessed. Request a representative loaded trial and torque records.',
    'Match the trial material, tool, coolant and path before applying its observations to an enquiry. Other applications require new representative trials. Submit the intended material, drawing and complete cycle.',
    'Read measured deviation alongside the method, environment and small sample before setting acceptance criteria. The samples do not establish production capability. Agree a representative measurement and uncertainty procedure.',
    'Treat the RFQ and acceptance schedule as inputs to negotiation. Proposed criteria require written agreement. Send the RFQ fields and negotiate acceptance responsibilities.',
    'Read delivery triggers and support exclusions against the quoted base configuration and document validity. The proposals are not signed commitments. Confirm the configuration register and commercial terms in writing.',
)
DIRECT_FACTS = ('FIT-LARGE', 'SPINDLE-LEGACY', 'AL-CUT', 'NCX7-COUPON', 'FAT-CRITERION', 'DELIVERY')


def scope():
    return dict(article_type='Procurement decision guide',
        search_intent='Commercial investigation: compare conditional choices and prepare a verifiable enquiry.',
        reader_problem='Shortlist equipment for a defined application and agree how suitability and commercial obligations will be verified.',
        section_briefs=tuple(ArticleSectionBrief(*q) for q in QUESTIONS))


class RichReviewer(previous.DossierReviewer):
    """Fixture-specific approved inferences, explicitly not human signoff."""
    def assess(self, snapshot, *, now):
        assessment = super().assess(snapshot, now=now)
        decisions = {d.requirement_id: d for d in assessment.decisions}
        interpretations = tuple(ReviewedInterpretation(text,
            tuple(dict.fromkeys(s for rid in question[3] for s in decisions[rid].spans)), question[4], question[5])
            for question, text in zip(QUESTIONS, EXPLANATIONS))
        return replace(assessment, interpretations=interpretations)


def response_for(value, facts):
    by_quote = {f.quote: f.fact_ref for s in value.customer_evidence.sources for f in s.facts}
    sections = []
    for brief, interpretation, key in zip(value.change_plan_report.operations[0].new_resource_spec.section_briefs,
                                           value.customer_evidence.interpretations, DIRECT_FACTS):
        quote = next(f['quote'] for f in facts if f['fact_id'] == key)
        def claim(text, kind, refs=()):
            return dict(text=text, claim_type=kind, page_refs=[], source_refs=[], customer_refs=list(refs))
        claims = [claim(quote, 'OBSERVED_PRODUCT_FACT', (by_quote[quote],)),
                  claim(interpretation.text, 'EVIDENCE_BASED_INTERPRETATION', interpretation.fact_refs)]
        sections.append(dict(outline_heading=brief.heading, blocks=[dict(kind='PARAGRAPH', claims=claims)]))
    sections[-1]['blocks'][0]['claims'].append(claim(
        'Send the workpiece drawing, material, fixture layout, target cycle and acceptance priorities to request a scoped quotation and representative trial proposal.',
        'CALL_TO_ACTION'))
    return dict(draft=dict(change_ref='C1', draft_type='NEW_RESOURCE_DRAFT', sections=sections))


async def structured_low_control(directory, initial_input, first_source):
    directory.mkdir()
    store = SQLiteEvidenceIntakeStore.create(directory / 'intake.sqlite3')
    class LowReviewer:
        def assess(self, snapshot, *, now):
            require(len(snapshot.active_evidence) == 1 and snapshot.active_evidence[0].supplement == first_source)
            return SemanticAssessment(snapshot_digest(snapshot), 'SYNTHETIC-LOW-REVIEW', now,
                tuple(RequirementDecision(r.requirement_id, SupportVerdict.MISSING,
                    'Only an unloaded spindle speed note is available; provide ' + r.required_fact)
                    for r in snapshot.task.requirements), ArticleScopeCoverage(True,
                    'The full purchasing scope is explicit; the source note cannot satisfy its obligations.'))
    flow = EvidenceIntakeWorkflow(store, reviewer=LowReviewer())
    task = EvidenceTask('SYNTHETIC-LOW-STRUCTURED', previous.CUSTOMER, 'LOW-GUIDE', 1,
        fixture.GOAL, previous.requirements(), **scope())
    current = flow.register(task, initial_input)
    current = flow.submit(task.project_id, task.task_id, CustomerSubmission('LOW-E1', snapshot_digest(current), (first_source,)),
        customer=CustomerContext(task.customer_id, 'SYNTHETIC-OPERATOR', datetime.now(UTC)))
    current = (await flow.replan(task.project_id, task.task_id, expected_sha256=snapshot_digest(current),
        planner=ChangePlanWorkflow(RetainedIntakePlanWriter()), now=datetime.now(UTC))).snapshot
    result = flow.check(task.project_id, task.task_id, now=datetime.now(UTC))
    never = previous.NeverDraft()
    report = await ContentDraftWorkflow(never, intake_admission=EvidenceIntakeDraftAdmission(store,
        task.project_id, task.task_id, expected_snapshot_sha256=snapshot_digest(current))).run(current.planning_input)
    require(result.status.value == 'BLOCKED' and never.calls == 0 and report.error == 'INTAKE_EXECUTION_BLOCKED')
    previous.save(directory / 'scope-and-evidence-review.json', result)
    previous.save(directory / 'snapshot.json', current)
    previous.save(directory / 'draft-blocked.json', dict(report=_encode(report), writer_calls=never.calls))
    return result


def exercise_web(directory, snapshot, reviewer, value, facts):
    requests = []
    response = response_for(value, facts)
    previous.save(directory / 'mock-writer-response.json', response)
    def handler(request):
        requests.append(request.content)
        return httpx.Response(200, json={'model': 'deepseek-flash', 'choices': [dict(
            message={'content': json.dumps(response)}, finish_reason='stop')]})
    app = create_app(mvp_dir=directory, db_path=directory / 'demo.sqlite3', live_db_path=directory / 'live.sqlite3')
    service = app.state.mvp_service
    service.scope_reviewer = reviewer
    service.generation_executor = MockArticleExecutor(task=snapshot.task, template=value, transport=httpx.MockTransport(handler))
    pages = directory / 'web'
    pages.mkdir()
    with TestClient(app, base_url='http://127.0.0.1') as client:
        for route in ('/mvp', '/mvp/evidence', '/mvp/generate'):
            result = client.get(route)
            require(result.status_code == 200)
            (pages / (route.rsplit('/', 1)[-1] + '.html')).write_bytes(result.content)
        view = service.generation.view()
        require(view['generation_allowed'])
        key = view['binding_sha256']
        require(client.post('/mvp/generate', data={'csrf_token': app.state.csrf_token, 'binding_sha256': key}).status_code == 200)
        for _ in range(200):
            client.get('/mvp/generate')
            if service.generation.view()['generation_state'] != 'RUNNING':
                break
            time.sleep(.01)
        previous.save(directory / 'generation-state.json', service.generation.view())
        require(service.generation.view()['generation_state'] == 'SUCCEEDED')
        article = service.article()
        page = client.get('/mvp/article')
        require(page.status_code == 200 and article['version_matches'])
        (pages / 'article.html').write_bytes(page.content)
        markdown = service.markdown()
        (directory / 'article-review.md').write_text(markdown, encoding='utf-8')
        require(MVPApplicationService(directory).article()['origin_sha256'] == article['origin_sha256'])
        review = article['review']
        require(not review.draft.quality_findings)
        require(all(ref in markdown and ref.encode() in page.content for ref in value.customer_evidence.quote_map()))
        previous.save(directory / 'claim-evidence-bindings.json', review.draft.claims)
        client.post('/mvp/generate', data={'csrf_token': app.state.csrf_token, 'binding_sha256': key})
        require(len(requests) == 1)
        class ChangedInterpretationReviewer:
            def assess(self, current, *, now):
                return replace(reviewer.assess(current, now=now), interpretations=())
        service.scope_reviewer = ChangedInterpretationReviewer()
        require(not service.generation.view()['generation_allowed'])
        service.scope_reviewer = None
        require(not service.generation.view()['generation_allowed'])
    (directory / 'mock-request.json').write_bytes(requests[0])
    return dict(mock_requests=len(requests), request_bytes=len(requests[0]),
        request_sha256=previous.sha(requests[0]), parser_validator_finalizer_sqlite_markdown_web='PASS',
        sqlite_reopen=True, duplicate_blocked=True, reviewer_revocation_blocked=True, interpretation_revocation_blocked=True,
        claim_count=len(review.draft.claims), interpretation_count=sum(c.claim_type == 'EVIDENCE_BASED_INTERPRETATION' for c in review.draft.claims),
        quality_findings=review.draft.quality_findings, real_model_calls=0, wordpress_calls=0)


def prepare(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    before = previous.protected_hashes()
    facts, supplements = previous.package(directory / 'customer-materials')
    with patch('httpx.AsyncHTTPTransport', side_effect=AssertionError('NO LIVE HTTP AUTHORIZED')), \
         patch('httpx.HTTPTransport', side_effect=AssertionError('NO LIVE HTTP AUTHORIZED')):
        asyncio.run(previous.old_control(directory / 'A-low-evidence-legacy'))
        rich = directory / 'B-rich-evidence'
        rich.mkdir()
        snapshot, assessment, reviewer, store = asyncio.run(previous.prepare_native(
            rich, facts, supplements, scope=scope(), reviewer_factory=RichReviewer))
        low = asyncio.run(structured_low_control(directory / 'A-low-evidence', store.get_revision(
            snapshot.task.project_id, snapshot.task.task_id, 1).planning_input, supplements[0]))
        value = reviewed_draft_input(snapshot, assessment, now=datetime.now(UTC))
        previous.save(rich / 'complete-draft-input.json', value)
        prompt = previous.cd.build_content_draft_prompt(value, 'C1')
        (rich / 'writer-material.json').write_text(prompt.material_json(), encoding='utf-8')
        require(set(value.customer_evidence.quote_map().values()) == {f['quote'] for f in facts})
        web = exercise_web(rich, snapshot, reviewer, value, facts)
    require(before == previous.protected_hashes())
    summary = dict(status='READY', readiness_scope='OFFLINE_CONTRACTS_ONLY_NEXT_EXPERIMENT_NEEDS_NEW_AUTHORIZATION',
        next_flash_experiment='READY_FOR_REVIEWED_INTERPRETATIONS_ONLY',
        autonomous_interpretation_generation='BLOCKED', autonomous_blocker_layer='Evidence contract',
        low_status=low.status.value, low_missing=[dict(id=g.requirement.requirement_id, fact=g.requirement.required_fact,
            intended_use=g.requirement.intended_use) for g in low.gaps], rich_status='READY',
        document_count=len(supplements), reviewed_fact_count=len(facts), writer_fact_count=len(value.customer_evidence.quote_map()),
        section_count=len(value.change_plan_report.operations[0].new_resource_spec.section_briefs),
        headings=value.change_plan_report.operations[0].new_resource_spec.outline_headings, complete_input=True,
        task_snapshot_sha256=snapshot_digest(snapshot), mechanics=web, historical_files_unchanged=True,
        real_model_quality_measured=False, production_authorized=False, human_signoff=False,
        limitation='Interpretations are reviewer-approved options; arbitrary new model inference is rejected and needs review.')
    previous.save(directory / 'readiness.json', summary)
    previous.save(directory / 'artifact-sha256.json', {p.relative_to(directory).as_posix(): previous.sha(p.read_bytes())
        for p in sorted(directory.rglob('*')) if p.is_file()})
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    print(json.dumps(prepare(parser.parse_args().output_dir), ensure_ascii=False, indent=2))
