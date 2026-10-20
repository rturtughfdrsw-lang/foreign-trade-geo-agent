"""Offline native scope acceptance; never loads credentials or calls a provider.

The reviewer and consent are explicitly scripted TEST-only decisions. E1 bytes
come from the previous frozen baseline; E2-E5 are never loaded into this run.
"""
import argparse
import asyncio
from dataclasses import replace
from datetime import UTC, datetime
import json
from pathlib import Path
from uuid import uuid4

import httpx
import uvicorn

from scripts import accept_seo_task_scope as case
from scripts.prepare_web_mvp import prepare as prepare_fixture
from foreign_trade_geo_agent.core import content_draft as cd
from foreign_trade_geo_agent.core.evidence_intake import (
    ArticleScopeCoverage, EvidenceTask, SemanticAssessment, RequirementDecision,
    EvidenceSpan, SupportVerdict, CustomerContext, CustomerSubmission,
    require, snapshot_digest,
)
from foreign_trade_geo_agent.core.history import AnalysisRunInput, ArtifactRecord, ArtifactType, RunStatus, WorkflowRun
from foreign_trade_geo_agent.storage.serialization import _encode, _decode
from foreign_trade_geo_agent.storage.sqlite import SQLiteHistoryStore, SQLiteHistoryReader
from foreign_trade_geo_agent.web.app import create_app
from foreign_trade_geo_agent.web.article_scope import TestScopeProposal
from foreign_trade_geo_agent.web.generation import MockArticleExecutor, canonical, digest
from foreign_trade_geo_agent.web.experiment import freeze


class CaseScopeReviewer:
    """Analyst-scripted acceptance for this fixture only; never human signoff."""
    def assess(self, snapshot, *, now):
        expected = case.load_frozen().active_evidence[0].supplement
        require(len(snapshot.active_evidence) == 1
                and snapshot.active_evidence[0].supplement == expected)
        material = snapshot.active_evidence[0].supplement
        quote = material.content.split('\n')[1]
        start = material.content.index(quote)
        decisions = tuple(RequirementDecision(r.requirement_id,
            SupportVerdict.SUPPORTED if r.requirement_id == 'F1' else SupportVerdict.MISSING,
            'TEST-only: supplied spindle statement supports its stated conditions and limits only.'
                if r.requirement_id == 'F1' else 'No applicable customer evidence supplied for this purchasing question.',
            (EvidenceSpan('E1', start, start + len(quote), quote),) if r.requirement_id == 'F1' else ())
            for r in snapshot.task.requirements)
        op = snapshot.planning_input.change_plan_report.operations[0]
        aligned = (snapshot.task.goal == case.NOTE_GOAL and op.new_resource_spec.proposed_title == case.NOTE_TITLE
                   and tuple(p.subject for p in op.content_points) == case.SUBJECTS[:1]
                   and tuple(r.requirement_id for r in snapshot.task.requirements) == ('F1',))
        broad = (snapshot.task.goal == case.GUIDE_GOAL and op.new_resource_spec.proposed_title == case.GUIDE_TITLE
                 and tuple(p.subject for p in op.content_points) == case.SUBJECTS)
        require(aligned or broad)
        # Full guide's obligations are correctly listed but F2-F5 are missing.
        # The legacy F1-only/title mismatch is tested separately at core admission.
        return SemanticAssessment(snapshot_digest(snapshot), 'SYNTHETIC-CASE-SCOPE-REVIEW-NOT-HUMAN', now,
            decisions, ArticleScopeCoverage(True,
                'TEST-only explicit review: goal, title, EXPLAIN points and listed obligations describe the same scope. '
                'Coverage still requires every fact obligation; this is not real customer or human signoff.'))


def write_json(path, value):
    path.write_bytes(canonical(_encode(value)))


def prepare(directory):
    directory = Path(directory)
    prepare_fixture(directory)
    session = json.loads((directory / 'session.json').read_bytes())
    history = SQLiteHistoryStore(directory / 'candidate/history.sqlite3')
    reader = SQLiteHistoryReader(directory / 'candidate/history.sqlite3')
    old_request = reader.get_analysis_run_input(session['project_id'])
    audit = next(a.payload for a in reader.list_artifacts(session['project_id']) if a.artifact_type is ArtifactType.SITE_AUDIT)
    value = asyncio.run(case.native_input(case.GUIDE_TITLE, case.SUBJECTS))
    project, task = str(uuid4()), str(uuid4())
    now = datetime.now(UTC)
    history.create_analysis_run(WorkflowRun(project, reader.get_run(session['project_id']).site_key,
        'end_to_end_planning_v1', now, None, RunStatus.RUNNING, None, None),
        AnalysisRunInput(project, old_request.website_url, case.GUIDE_GOAL, 'en', old_request.display_identity))
    for kind, payload in ((ArtifactType.SITE_CONTENT, value.site_content), (ArtifactType.SITE_AUDIT, audit),
            (ArtifactType.CONTENT_OPPORTUNITY, value.opportunity_report), (ArtifactType.CHANGE_PLAN, value.change_plan_report)):
        history.append_artifact(ArtifactRecord(task if kind is ArtifactType.CHANGE_PLAN else str(uuid4()), project, kind, 1, now, payload))
    history.finish_run(project, status=RunStatus.FAILED, completed_at=datetime.now(UTC),
                       failure_kind='content_draft.invalid_input', sanitized_error='INTAKE_EXECUTION_BLOCKED')
    session.update(project_id=project, task_id=task)
    write_json(directory / 'session.json', session)
    app = create_app(mvp_dir=directory, db_path=directory / 'demo.sqlite3', live_db_path=directory / 'live.sqlite3')
    service = app.state.mvp_service
    # _load validates revision 1, so register via its native composition first.
    from foreign_trade_geo_agent.runtime import build_planning_evidence_workflow
    store, planning, planner = build_planning_evidence_workflow(directory / 'candidate/history.sqlite3',
        directory / 'interactive-intake.sqlite3', run_id=project, plan_id=task)
    current = planning.register(project, task, customer_id=case.customer().customer_id, requirements=case.requirements())
    e1 = case.load_frozen().active_evidence[0].supplement
    current = planning.intake.submit(project, task, CustomerSubmission('TEST-ONLY-RETAINED-E1', snapshot_digest(current), (e1,)),
        customer=CustomerContext(current.task.customer_id, 'TEST-ONLY-OPERATOR-NOT-CUSTOMER', now))
    current = asyncio.run(planning.recheck(project, task, expected_sha256=snapshot_digest(current),
        current=current, planner=planner, now=now)).snapshot
    new_value = asyncio.run(case.native_input(case.NOTE_TITLE, case.SUBJECTS[:1]))
    proposal = TestScopeProposal(snapshot_digest(current), EvidenceTask(project, current.task.customer_id,
        'TEST-SPINDLE-NOTE-' + uuid4().hex[:12], 1, case.NOTE_GOAL, current.task.requirements[:1]), new_value)
    write_json(directory / 'test-scope-proposal.json', proposal)
    write_json(directory / 'path-a-original.json', current)
    (directory / 'E1-exact.txt').write_bytes(e1.content.encode('utf-8'))
    return build(directory)


def build(directory):
    directory = Path(directory)
    app = create_app(mvp_dir=directory, db_path=directory / 'demo.sqlite3', live_db_path=directory / 'live.sqlite3')
    service = app.state.mvp_service
    service.scope_reviewer = CaseScopeReviewer()
    raw = json.loads((directory / 'test-scope-proposal.json').read_bytes())
    service.scope.test_proposal = TestScopeProposal(raw['parent_snapshot_sha256'],
        _decode(raw['task'], EvidenceTask), _decode(raw['planning_input'], cd.ContentDraftInput))
    # Even with an executor installed, scope/evidence admission must block A.
    current = service.evidence()['snapshot']
    legacy = _decode(json.loads((directory / 'candidate/03-native-input.json').read_bytes()), cd.ContentDraftInput)
    service.generation_executor = MockArticleExecutor(task=current.task, template=legacy,
        transport=httpx.MockTransport(lambda request: (_ for _ in ()).throw(AssertionError('NO REQUEST AUTHORIZED'))))
    return app


def prepare_brief_and_request(service):
    """Only after TEST-only child creation and exact E1/Plan/scope agreement."""
    view = service.evidence()
    current = view['snapshot']
    require(current.task.goal == case.NOTE_GOAL and view['scope_lineage'] is not None)
    assessment = service.require_generation_scope(current)
    material = current.active_evidence[0].supplement
    from foreign_trade_geo_agent.core.draft_customer_evidence import DraftCustomerEvidence, DraftCustomerSource, native_scope_digest
    span = assessment.decisions[0].spans[0]
    source = DraftCustomerSource('E1', current.active_evidence[0].evidence_version, material.requirement_ids,
        material.source_label, material.source_locator, material.content, material.file_sha256,
        span.start, span.end, span.quote)
    value = current.planning_input
    bundle = DraftCustomerEvidence(current.task.project_id, current.task.customer_id, current.task.task_id,
        current.task.task_version, current.plan_version, current.evidence_version, current.revision,
        snapshot_digest(current), native_scope_digest(value.site_content, value.opportunity_report, value.change_plan_report.operations[0]),
        'C1', assessment.reviewer_id, assessment.reviewed_at, 'TEST_ONLY_SUPPORTED_NOT_HUMAN_SIGNOFF', (source,))
    brief = cd.ArticleWritingBrief(snapshot_digest(current), current.task.goal,
        'Informational: understand exactly what the supplied spindle bench statement establishes and ask the supplier about unresolved test applicability.', (
        'Quote E1 once in full, preserving model, rating, duty, protocol, unloaded bench conditions and limitations. Explain that its stated scope does not establish cutting-load or production performance; do not infer torque, power, accuracy, duration or suitability.',
        'Organize the article around the supplied test conditions and scope, then evidence-supported enquiry questions. Ask which test records apply to the intended loaded cutting cycle and what remains to be evaluated; phrase unresolved matters as questions, never supplier capabilities.',
        'Keep S background concise. Do not stitch S sentences, repeat generic purchasing checklists, invent technical mechanisms or treat unverified topic labels as authoritative technical evidence. Additional technical explanation requires independent applicable evidence and human review.',
        'Use a scope-matched CTA: send the intended application and unresolved test questions to the supplier and request applicable supporting records. No whole-machine recommendation, performance promise, certification or service claim.',
        'Follow all native claim/reference/numeric and block budgets. E remains independent of P/S. If evidence cannot support an explanation, omit the conclusion and retain the question for human review. No length target.',
    ))
    value = replace(value, customer_evidence=bundle, writing_brief=brief)
    require(cd.stable_content_draft_input_error(value) is None)
    def no_request(request):
        raise AssertionError('NO MODEL REQUEST AUTHORIZED')
    service.generation_executor = MockArticleExecutor(task=current.task, template=value, transport=httpx.MockTransport(no_request))
    prepared = service.generation._prepare()
    require(prepared[2].writing_brief == brief)
    write_json(service.directory / 'path-b-new-task.json', current)
    write_json(service.directory / 'writing-brief.json', brief)
    bundle_id = freeze(service)
    manifest = json.loads((service.directory / 'web-experiment/bundle.json').read_bytes())
    summary = {'ready_for_next_isolated_flash_freeze': True, 'frozen_bundle_sha256': bundle_id,
        'request_sha256': manifest['request_sha256'], 'task_id': current.task.task_id,
        'snapshot_sha256': snapshot_digest(current), 'plan_version': current.plan_version,
        'evidence_version': current.evidence_version, 'evidence_ids': ('E1',),
        'brief_sha256': digest((service.directory / 'writing-brief.json').read_bytes()),
        'real_model_calls': 0, 'wordpress_calls': 0, 'customer_consented': False,
        'human_signoff': False, 'production_authorized': False, 'permit_issued': False}
    write_json(service.directory / 'readiness.json', summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--prepare-request', action='store_true')
    parser.add_argument('--port', type=int, default=8021)
    args = parser.parse_args()
    app = build(args.directory) if args.resume else prepare(args.directory)
    if args.prepare_request:
        print(json.dumps(prepare_brief_and_request(app.state.mvp_service), ensure_ascii=False, indent=2))
        return
    uvicorn.run(app, host='127.0.0.1', port=args.port)


if __name__ == '__main__':
    main()
