"""Fixed offline NovaCNC scope/intake acceptance; no model, transport or CMS.

This is an analyst-authored business fixture, NOT a general sufficiency
detector. Consent below is simulated, never consent to alter a real task.
All new engineering records are fictional SYNTHETIC data. No semantic
reviewer is installed and no Draft permission is produced.
"""
import argparse
import asyncio
from dataclasses import replace
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from foreign_trade_geo_agent.adapters.customer_evidence import text_document
from foreign_trade_geo_agent.adapters.retained_intake_plan import RetainedIntakePlanWriter
from foreign_trade_geo_agent.core import change_plan as cp
from foreign_trade_geo_agent.core.content_opportunity import (
    ContentOpportunitySourceMaterial, ContentOpportunitySpecification,
    finalize_content_opportunity,
)
from foreign_trade_geo_agent.core.evidence_intake import (
    CustomerContext, CustomerSubmission, EvidenceRequirement, EvidenceTask,
    IntakeSnapshot, ScopeAdjustment, require, snapshot_digest,
)
from foreign_trade_geo_agent.storage.evidence_intake import SQLiteEvidenceIntakeStore
from foreign_trade_geo_agent.storage.serialization import _decode, _encode
from foreign_trade_geo_agent.workflows.change_plan import ChangePlanWorkflow
from foreign_trade_geo_agent.workflows.evidence_intake import EvidenceIntakeWorkflow

ROOT = Path(__file__).resolve().parents[1]
FROZEN = ROOT / 'docs/seo-model-comparison-preflight-2026-10-11/baseline/snapshot.json'
FROZEN_SHA256 = 'c9edae44515a6a54e6d74873a45f8298545808ffce81cf62e44f6a57d50e6963'
NOW = datetime(2026, 10, 11, 8, 0, tzinfo=UTC)  # fixture clock, not actual review time
PROJECT = 'SYNTHETIC-NOVACNC-SCOPE-ACCEPTANCE'
GUIDE_TITLE = 'NovaCNC machining center buyer guide'
NOTE_TITLE = 'Spindle test conditions and scope'
GUIDE_GOAL = ('SYNTHETIC ONLY: prepare a machining center buyer guide covering spindle performance, '
              'application fit, machining tolerance, acceptance criteria and documentation scope. '
              'These five questions are a case-specific analyst proposal requiring customer confirmation.')
NOTE_GOAL = ('SYNTHETIC ONLY: explain the supplied spindle test conditions and scope; '
             'do not offer whole-machine selection, cutting performance or acceptance conclusions.')
SUBJECTS = ('spindle performance', 'application fit', 'machining tolerance',
            'acceptance criteria', 'documentation scope')

# No universal purchasing schema: requirements describe only this proposed brief.
NEEDS = (
    ('Spindle parameter, exact model, duty, test conditions and limitations',
     'Explain the stated rating and its limits without treating it as cutting performance'),
    ('Customer-confirmed workpiece material, geometry, tooling, cutting cycle and applicable machine configuration',
     'Explain which intended application is being evaluated and which remain unassessed'),
    ('Model/configuration-specific test piece, measured characteristic, method, material, conditions, results and exclusions',
     'Distinguish a measured result from a guarantee for the intended workpiece'),
    ('Proposed procurement acceptance procedure, representative load, measurement method, responsibilities and unresolved criteria',
     'Explain what buyer and supplier must agree before using a test as acceptance evidence'),
    ('Applicable technical document revisions, model/options scope, verified certificates if claimed, and confirmed support terms if covered',
     'Identify the records and commercial terms that apply, without inventing certification or service promises'),
)

# Independent fictional records; NOT proof that the guide is commercially ready.
EXTRA_RECORDS = (
    ('E2', 'F2', 'application-request-v1',
     'SYNTHETIC ONLY: NCX7 application request lists aluminum housings and intermittent milling with fixture A; '
     'tooling and cutting cycle remain unconfirmed; no suitability or production result is established.'),
    ('E3', 'F3', 'test-piece-report-v1',
     'SYNTHETIC ONLY: NCX7 aluminum coupon measured +/-0.02 mm at 20 C under NOVA-MEASURE-A protocol; '
     'fixture A only; no other material, geometry or production guarantee.'),
    ('E4', 'F4', 'acceptance-proposal-v1',
     'SYNTHETIC ONLY: NCX7 acceptance proposal uses an aluminum coupon and fixture A under NOVA-ACCEPT-A protocol; '
     'buyer and supplier must confirm tooling, measurement method and criteria; this is not an agreed acceptance record.'),
    ('E5', 'F5', 'document-register-v1',
     'SYNTHETIC ONLY: NCX7 document register revision A lists the spindle bench note and coupon report for fixture A; '
     'certificate authority and service terms are unconfirmed; no certification or support promise is established.'),
)


def load_frozen():
    raw = FROZEN.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == FROZEN_SHA256)
    return _decode(json.loads(raw), IntakeSnapshot)


class FixedScopePlanWriter:
    """Analyst-selected points through the EXISTING native parser/finalizer."""
    def __init__(self, title, subjects):
        self.title, self.subjects = title, subjects

    async def write_change_plan(self, prompt):
        points = [next(c for c in prompt.content_point_candidates_for('R1') if c.text == s)
                  for s in self.subjects]
        body = {'opportunity_operations': {'R1': {'primary_operation': {
            'source_action_code': 'CREATE_SUPPORTING_RESOURCE', 'operation_type': 'CREATE_NEW_RESOURCE',
            'page_bindings': [{'page_ref': 'P1', 'suggested_source': True}],
            'source_refs': list(prompt.input.opportunities.opportunities[0].source_refs),
            'resource_purpose': 'SUPPORTING_RESOURCE', 'proposed_title': self.title,
            'content_points': [{'intent': 'EXPLAIN', 'subject_ref': p.candidate_id} for p in points],
            'comparison_table_brief': None}, 'secondary_operation': None}}}
        return cp.ChangePlanGeneration('synthetic', 'fixed-scope-acceptance-not-model',
            cp.ChangePlanGenerationStatus.SUCCESS, json.dumps(body), None)


async def native_input(title, subjects):
    old = load_frozen().planning_input
    old_opp = old.opportunity_report.opportunities[0]
    # New task's explicitly synthetic label/topic context. This replaces no old S1
    # and is NOT a verified technical source or a source of customer parameters.
    materials = [ContentOpportunitySourceMaterial('S1', 'Test conditions and scope',
        '; '.join(('Buyer questions and next steps', subjects[0], title)), False)]
    if len(subjects) > 1:
        materials.append(ContentOpportunitySourceMaterial('S2', subjects[1], '; '.join(subjects[1:]), False))
    sources = tuple(replace(old.opportunity_report.sources[0], source_id=m.source_id, title=m.title,
        url=f'https://synthetic-context.example/novacnc-scope/{m.source_id}') for m in materials)
    opportunity = finalize_content_opportunity(1, ContentOpportunitySpecification(
        old_opp.opportunity_type, old_opp.priority, subjects[0], old_opp.action_codes,
        old_opp.page_refs, tuple(m.source_id for m in materials)))
    report = replace(old.opportunity_report, opportunities=(opportunity,),
        sources=sources, source_materials=tuple(materials))
    plan = await ChangePlanWorkflow(FixedScopePlanWriter(title, subjects)).run(
        old.site_content, report)
    require(plan.status is cp.ChangePlanStatus.SUCCESS)
    return replace(old, opportunity_report=report, change_plan_report=plan)


def requirements(subjects=SUBJECTS):
    from foreign_trade_geo_agent.core.evidence_intake import SupplementMethod
    return tuple(EvidenceRequirement(f'F{i+1}', i, *NEEDS[i],
        'Current P/S only name topics; E1 is an unloaded spindle bench statement and cannot establish this purchasing decision.',
        (SupplementMethod.TEXT_DOCUMENT, SupplementMethod.CUSTOMER_FACT)) for i in range(len(subjects)))


def customer():
    return CustomerContext('SYNTHETIC-NOVACNC', 'SYNTHETIC-SIMULATED-CUSTOMER-NOT-SIGNOFF', NOW)


async def replan(flow, current):
    return await flow.replan(PROJECT, current.task.task_id, expected_sha256=snapshot_digest(current),
        planner=ChangePlanWorkflow(RetainedIntakePlanWriter()), now=NOW)


async def single_e1_case(flow, task_id):
    value = await native_input(GUIDE_TITLE, SUBJECTS)
    current = flow.register(EvidenceTask(PROJECT, customer().customer_id, task_id, 1, GUIDE_GOAL, requirements()), value)
    # Preserve the historical E1 bytes, locator, declared owner and hash exactly.
    e1 = load_frozen().active_evidence[0].supplement
    submitted = flow.submit(PROJECT, task_id, CustomerSubmission('SYNTHETIC-E1', snapshot_digest(current), (e1,)),
                            customer=customer())
    return await replan(flow, submitted)


def supplements():
    return tuple(text_document(evidence_id=eid, requirement_ids=(fid,),
        payload=(f'SYNTHETIC UTF-8 fictional NovaCNC record; document {doc}; model NCX7; revision A; '
                 'scope fixture A only; not engineering evidence.\n' + quote + '\nSYNTHETIC ONLY; no human signoff.').encode(),
        source_label=f'SYNTHETIC NovaCNC {doc}', source_locator=f'synthetic:novacnc/NCX7/{doc}#statement',
        declared_source_owner='FICTIONAL NovaCNC') for eid, fid, doc, quote in EXTRA_RECORDS)


async def narrow_after_consent(flow, store, old):
    """Fixed TEST-only new-task handoff; require an actual current ScopeConsent.

    Intake deliberately cannot rewrite a resource title/outline. Recollect E1
    under a new task; carry neither semantic verdict nor Draft permission.
    """
    current = store.latest(PROJECT, old.task.task_id)
    require(current == old and not current.plan_bound and bool(current.scope_consents)
            and current.task.goal == NOTE_GOAL and current.point_subjects == SUBJECTS[:1]
            and tuple(r.requirement_id for r in current.task.requirements) == ('F1',))
    consent = current.scope_consents[-1]
    previous = store.get_revision(PROJECT, old.task.task_id, old.revision - 1)
    require(consent.previous_snapshot_sha256 == snapshot_digest(previous)
            and consent.adjustment.customer_consents is True)
    value = await native_input(NOTE_TITLE, SUBJECTS[:1])
    new = flow.register(EvidenceTask(PROJECT, customer().customer_id, 'SPINDLE-NOTE', 1, NOTE_GOAL,
                                    current.task.requirements), value)
    e1 = next(e.supplement for e in current.active_evidence if e.supplement.evidence_id == 'E1')
    submitted = flow.submit(PROJECT, new.task.task_id, CustomerSubmission('SYNTHETIC-E1-RESUBMITTED',
        snapshot_digest(new), (e1,)), customer=customer())
    candidate = await replan(flow, submitted)
    lineage = {'synthetic_simulated_consent_only': True,
        'production_scope_change_authorized': False,
        'parent_task_id': current.task.task_id, 'parent_task_version': current.task.task_version,
        'parent_plan_version': current.plan_version, 'parent_evidence_version': current.evidence_version,
        'parent_snapshot_sha256': snapshot_digest(current), 'scope_consent': consent,
        'new_task_id': candidate.snapshot.task.task_id, 'new_snapshot_sha256': snapshot_digest(candidate.snapshot),
        'old_review_transferred': False, 'draft_authorized': False}
    return candidate, lineage


async def prepare(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)

    def save(name, value):
        (directory / name).write_text(json.dumps(_encode(value), ensure_ascii=False, indent=2), encoding='utf-8')

    save('guide-requirements.json', requirements())
    with TemporaryDirectory() as temp:
        store = SQLiteEvidenceIntakeStore.create(Path(temp) / 'intake.sqlite3')
        flow = EvidenceIntakeWorkflow(store)  # no semantic reviewer / no permission
        broad = await single_e1_case(flow, 'KEEP-GUIDE')
        save('01-guide-only-E1.json', broad)
        save('02-customer-request.json', flow.customer_request(PROJECT, 'KEEP-GUIDE', now=NOW))
        added = supplements()
        save('synthetic-supplements.json', added)
        submitted = flow.submit(PROJECT, 'KEEP-GUIDE', CustomerSubmission('SYNTHETIC-E2-E5',
            snapshot_digest(broad.snapshot), added), customer=customer())
        full = await replan(flow, submitted)
        save('03-guide-more-materials-unreviewed.json', full)

        original = await single_e1_case(flow, 'GUIDE-TO-NOTE')
        adjustment = ScopeAdjustment(NOTE_GOAL, ('F1',),
            'SYNTHETIC simulated explicit customer agreement to explain only spindle test scope.', True)
        narrowed = flow.submit(PROJECT, 'GUIDE-TO-NOTE', CustomerSubmission('SYNTHETIC-SCOPE-CONSENT',
            snapshot_digest(original.snapshot), scope_adjustment=adjustment), customer=customer())
        save('04-consented-old-task-unbound.json', narrowed)
        note, lineage = await narrow_after_consent(flow, store, narrowed)
        save('05-new-note-plan-unreviewed.json', note)
        save('06-lineage.json', lineage)
        save('original-guide-before-consent.json', original)
        save('07-append-only-history.json', tuple(store.get_revision(PROJECT, 'GUIDE-TO-NOTE', i)
                                                for i in range(1, narrowed.revision + 1)))
    summary = {'synthetic_only': True, 'no_human_signoff': True, 'production_logic_changed': False,
        'original_frozen_snapshot_sha256': FROZEN_SHA256,
        'single_E1_status': broad.check.status.value,
        'single_E1_gaps': {g.requirement.requirement_id: g.reason_code for g in broad.check.gaps},
        'additional_materials_status': full.check.status.value,
        'additional_materials_are_not_sufficiency_proof': True,
        'note_status': note.check.status.value, 'note_title': NOTE_TITLE,
        'provider_calls': 0, 'wordpress_calls': 0, 'draft_authorized': False}
    save('acceptance-summary.json', summary)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True, help='NEW local output directory')
    print(json.dumps(asyncio.run(prepare(parser.parse_args().output_dir)), ensure_ascii=False, indent=2))
