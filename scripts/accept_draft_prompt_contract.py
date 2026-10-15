"""Independent offline prompt repair acceptance/freeze. Never loads keys or issues LIVE permits."""
import argparse
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import hashlib
import inspect
import json
from pathlib import Path

from scripts import accept_autonomous_interpretation as native
from scripts.accept_full_article_budget import ANALYSIS, measure
from foreign_trade_geo_agent.adapters import deepseek_content_draft as adapter
from foreign_trade_geo_agent.core import content_draft as cd, draft_customer_evidence as ce
from foreign_trade_geo_agent.storage.serialization import _decode
from foreign_trade_geo_agent.workflows import content_draft as workflow
from foreign_trade_geo_agent.web.experiment import code_hashes
from foreign_trade_geo_agent.web.generation import MockArticleExecutor


ROOT = Path(__file__).resolve().parents[1]
HISTORY = ROOT / 'docs/seo-flash-quality-live-2026-10-12'

# Independent, qualitative provider RESPONSE. These paragraphs never become
# supplied interpretation options or production prompt text.
FOLLOW_UP = (
    ('The option list leaves applicability unresolved.',
     'Ask which requested options need separate setup checks.',
     'Compare the requested control, coolant arrangement and magazine layout with the configuration represented by the trial. An option belongs in the enquiry when it answers an identified operation need.'),
    ('The warm-up procedure does not characterize thermal drift.',
     'Request a loaded trial recording tool, material and coolant conditions.',
     'A motor nameplate and an unloaded spindle observation answer different questions. Keep those records separate when deciding which application evidence to request.'),
    ('The matched cycle sample excludes loading and does not settle production throughput.',
     'Define handling, tool changes and inspection in the target cycle.',
     'Compare the cycle boundary before comparing a trial with an internal production target. The recorded timing can inform a test request without becoming a contractual limit.'),
    ('Outer-width observations leave other features and production capability unresolved.',
     'Submit the critical drawing features and propose a measurement decision rule.',
     'A proposed acceptance threshold and a recorded coupon result have different roles. Discuss uncertainty and disposition with the intended drawing before treating a measured deviation as an acceptance verdict.'),
    ('A proposed procedure does not settle shipment-release responsibilities.',
     'Ask who records setup, agrees disposition and authorizes correction and re-test.',
     'Put the drawing revision, configuration and acceptance schedule beside the quotation. Assign the unresolved decisions explicitly so that a configuration change triggers a review of the purchasing basis.'),
    ('Initial response is not a repair or recovery commitment.',
     'Request the support calendar and negotiate parts, travel and destination scope in writing.',
     'Distinguish dispatch triggers from arrival, remote training from site commissioning, and ticket response from recovery. Each boundary changes what the buyer must arrange before handover.'),
)


def procurement_mock(value, facts):
    response = native.mock_response(value, facts)
    for index, section in enumerate(response['draft']['sections']):
        direct, template = section['blocks'][0]['claims'][:2]
        brief = value.change_plan_report.operations[0].new_resource_spec.section_briefs[index]
        first = deepcopy(template)
        first['text'] = ANALYSIS[index][0] + ' ' + brief.limitations + ' ' + brief.procurement_action
        section['blocks'] = [dict(kind='PARAGRAPH', claims=[direct, first])]
        limitation, action, body = FOLLOW_UP[index]
        second = deepcopy(template)
        second['text'] = body + ' ' + limitation + ' ' + action
        second['proposal'].update(reasoning=body, limitation=limitation, procurement_action=action,
            assumptions='The intended application must be checked against the recorded configuration and scope.')
        section['blocks'].append(dict(kind='PARAGRAPH', claims=[second]))
        if index in (0, 2):
            extra = deepcopy(second)
            extra['text'] = ANALYSIS[index][2] + ' ' + limitation + ' ' + action
            extra['proposal']['reasoning'] = 'Use the cited setup boundaries to identify what must be resolved before selection.'
            section['blocks'].append(dict(kind='PARAGRAPH', claims=[extra]))
    section['blocks'].append(dict(kind='PARAGRAPH', claims=[dict(
        text='Send the current drawing revision, material condition, fixture layout, target cycle and acceptance priorities to request a configuration review and scoped quotation.',
        claim_type='CALL_TO_ACTION', page_refs=[], source_refs=[], customer_refs=[])]))
    return response


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def prepare(directory):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    historical = {p.name: sha(p.read_bytes()) for p in HISTORY.iterdir() if p.is_file()}
    result = native.prepare(directory / 'native', response_factory=procurement_mock)
    rich = directory / 'native/B-rich-evidence'
    value = _decode(json.loads((rich/'frozen-native-input.json').read_bytes()), cd.ContentDraftInput)
    historical_value = _decode(json.loads((HISTORY/'native-input.json').read_bytes()), cd.ContentDraftInput)
    assert value.change_plan_report == historical_value.change_plan_report
    assert value.customer_evidence.sources == historical_value.customer_evidence.sources
    raw_request = MockArticleExecutor.request_for(value)
    request = json.loads(raw_request)
    system, user = (m['content'] for m in request['messages'])
    assert len(system) <= cd.MAX_SYSTEM_PROMPT_CHARS
    assert 'E CANDIDATE MODE' in system and 'supersedes' not in system
    assert raw_request == (directory/'native/flash-request.FROZEN-NOT-AUTHORIZED.json').read_bytes()
    (directory/'request.FROZEN-NOT-AUTHORIZED.json').write_bytes(raw_request)
    (directory/'system-prompt.txt').write_bytes(system.encode())
    (directory/'user-material.json').write_bytes(user.encode())
    save(directory/'schema-examples.json', adapter._E_CANDIDATE_EXAMPLES)
    material = json.loads(user)
    # Freeze the current native selection contract, rather than copying an
    # obsolete all-fact quota into an otherwise self-consistent request.
    coverage = dict(structured_fact_bank='NONEMPTY_VALID_SUBSET',
        legacy_or_mixed='ALL_CUSTOMER_REFS', section_requirements_preserved=True,
        current_instruction=material['contract']['customer_coverage_rule'])
    save(directory/'task-plan-brief.json', dict(task=json.loads((rich/'snapshot.json').read_bytes())['task'],
        change=material['change'], writing_brief=material['writing_brief']))
    save(directory/'facts-source-map.json', material['customer_evidence']['sources'])
    save(directory/'output-contract.json', dict(
        mode='E_CANDIDATE', draft_fields=['change_ref','draft_type','sections'],
        section_fields=['outline_heading','blocks'],
        paragraph_fields=['kind','claims'], bullet_fields=['kind','items'],
        claim_fields=['text','claim_type','page_refs','source_refs','customer_refs'],
        types=['OBSERVED_PRODUCT_FACT','EVIDENCE_BASED_INTERPRETATION','EDITORIAL_TRANSITION','CALL_TO_ACTION'],
        proposal_on='EVIDENCE_BASED_INTERPRETATION only; required for candidates',
        proposal_fields=['procurement_question','reasoning','assumptions','limitation','procurement_action'],
        direct='One exact reviewed quote and one ref; empty P/S arrays; no proposal',
        interpretation='1-20 distinct premises; exact section question; limitation/action verbatim in text; canonical whitespace',
        proposal_lengths=dict(procurement_question=300, reasoning=300, assumptions=300, limitation=150, procurement_action=150),
        bounds=dict(claims=cd.MAX_CLAIMS_PER_DRAFT,blocks=cd.MAX_BLOCKS_PER_DRAFT,
            claims_per_paragraph=cd.MAX_CLAIMS_PER_BLOCK, paragraphs_per_section=cd.MAX_PARAGRAPHS_PER_DRAFT,
            bullet_items=cd.MAX_BULLET_ITEMS,bullet_text=cd.MAX_BULLET_ITEM_CHARS,
            direct_text=cd.MAX_CLAIM_CHARS,interpretation_text=ce.MAX_INTERPRETATION_CHARS),
        coverage=coverage,
        numeric='Exact non-bare expressions; candidate quantities only in complete cited source sentences',
        admission='PENDING_SEMANTIC_REVIEW; no model approval fields; TEST-only review is not production authority'))
    summary_sources = {
        'parse_claim': workflow._parse_claim,
        'parse_specification': workflow._parse_specification,
        'validate_claim_evidence': cd._validate_claim_evidence,
        'article_quality_findings': cd.article_quality_findings,
        'finalize_draft_item': cd.finalize_draft_item,
        'interpretation_proposal': ce.InterpretationProposal,
    }
    save(directory/'parser-validator-source-summary.json', {name:dict(
        file=Path(inspect.getsourcefile(fn)).relative_to(ROOT).as_posix(),
        line=inspect.getsourcelines(fn)[1], source_sha256=sha(inspect.getsource(fn).encode()))
        for name,fn in summary_sources.items()})
    old_raw = (HISTORY/'model-output.txt').read_text(encoding='utf-8')
    original_spec = workflow._parse_specification(old_raw, expected_change_ref='C1', operation=value.change_plan_report.operations[0])
    check = workflow.inspect_candidate_output(value, old_raw, current_snapshot_sha256=value.customer_evidence.snapshot_sha256)
    assert check.state == 'DETERMINISTICALLY_REJECTED'
    assert all(not c.refs and c.proposal is None for c in check.claims)
    save(directory/'historical-failure-replay.json', dict(
        raw_sha256=sha(old_raw.encode()), parser='PASS', validator=check.state,
        errors=check.errors, claims=len(check.claims), sections=len(original_spec.sections),
        customer_ref_repairs=0, proposal_repairs=0))
    old_request = json.loads((HISTORY/'request.json').read_bytes())
    old_system = old_request['messages'][0]['content']
    conflicts = [
        ('old_exact_claim_shape', 'Every claim is exactly {"text","claim_type","page_refs","source_refs"}',
         'E claims specify five base fields plus proposal only for interpretations.'),
        ('p_only_source_rule', 'must cite at least one P page',
         'E facts use exact customer_refs; structured P/S hints are planning context.'),
        ('short_source_vocabulary', 'Keep every claim short and lexically grounded',
         'E analyses may synthesize premises in multi-sentence prose within native lengths.'),
        ('append_override', 'E CANDIDATE RULE supersedes',
         'Select a self-contained contract from native customer_evidence/propose_interpretations.'),
    ]
    assert all(fragment in old_system and fragment not in system for _,fragment,_ in conflicts)
    save(directory/'prompt-conflict-audit.json', dict(
        historical_request_sha256=sha((HISTORY/'request.json').read_bytes()),
        actual_messages_audited=['system','user'],
        conflicts=[dict(id=key, original_fragment=fragment, repair=repair) for key,fragment,repair in conflicts],
        coverage=coverage,
        editorial='Two native allowed transitions retained; natural connections inside analysis.',
        user_material='E scope explicit; reviewed proposal metadata projected; full 43 refs and six sections retained.',
        causality='Historical output matches old schema; no real causal/instruction-following experiment in this run.'))
    response = json.loads((rich/'mock-response.json').read_bytes())
    article = '# SYNTHETIC / SCRIPTED MOCK — not evidence of real writing quality\n\n' + '\n\n'.join(
        '## '+s['outline_heading']+'\n\n'+'\n\n'.join(' '.join(c['text'] for c in b['claims']) for b in s['blocks'])
        for s in response['draft']['sections'])
    (directory/'mock-article.md').write_text(article, encoding='utf-8')
    save(directory/'offline-result.json', result)
    now = datetime.now(UTC)
    preflight = dict(status='BLOCKED_PUBLIC_CONFIGURATION_AND_TOKEN_BOUND_CONFIRMATION',
        model=request['model'], endpoint='https://api.deepseek.com/chat/completions',
        parameters={k:v for k,v in request.items() if k != 'messages'},
        max_requests=1, retries=0, fallback=0, timeout_seconds=60, response_byte_cap=256*1024,
        created_at=now.isoformat(), preparation_valid_until=(now+timedelta(hours=24)).isoformat(),
        authorization=dict(issued=False, expires_at=None, actual_spending_authorized=0,
            required='A new explicit user authorization bound to this request/bundle only; previous permit consumed.',
            proposed_permit_lifetime_minutes=10,
            expired='Do not execute. Recheck evidence/Plan, code and all hashes, public parameters/prices and budget; re-freeze and request fresh authorization.'),
        public_verification=dict(status='NOT_CHECKED_IN_THIS_OFFLINE_RUN', checked_at=None,
            urls=['https://api-docs.deepseek.com/quick_start/pricing/','https://api-docs.deepseek.com/api/create-chat-completion'],
            result='No public-document verification performed by this offline script; current alias, limits, parameter support and prices unverified.'),
        token_budget=dict(input=measure(system+user), output_limit=request['max_tokens'],
            exact_tokenizer=None, usage=None, context_limit_verified=False,
            assumed_input_ceiling=65536, assumed_ceiling_is_not_a_proven_bound=True),
        cost=dict(currency='USD', proposed_limit=0.05, current_price_verified=False,
            historical_peak_input_per_million=0.3, historical_peak_output_per_million=1.2,
            conditional_estimate=(65536*0.3+request['max_tokens']*1.2)/1000000,
            estimate_only=True, account_balance_queried=False),
        retention=dict(raw_response='response-body.bin', model_text='model-output.txt',
            request='request.json', metadata='result.json or failed.json',
            rejected='rejected-candidate.txt plus native diagnostics', candidate='local-review.sqlite3',
            all='Keep full response bytes, finish_reason/model/usage/cache tokens, timestamps and independent SHA256 before native parsing; no repairs.',
            incomplete='Bounded prefix only, response_complete=false; never treat as complete success.',
            secrets='Private current-user directory; refuse secret-bearing responses; never persist keys/headers.',
            transport='Exact frozen bytes, single POST, zero automatic retries/redirects; consume fresh permit before transport.'),
        request_sha256=sha(raw_request), production_authorized=False)
    save(directory/'real-request-preflight.json', preflight)
    assert historical == {p.name: sha(p.read_bytes()) for p in HISTORY.iterdir() if p.is_file()}
    ready = dict(statuses=['PROMPT_CONTRACT_CONFLICT_FIXED','OFFLINE_E_CANDIDATE_READY',
        'REAL_FLASH_INSTRUCTION_FOLLOWING_UNTESTED','REAL_WRITING_QUALITY_UNTESTED','PRODUCTION_NO_GO'],
        real_request_preflight=preflight['status'], real_requests=0, wordpress_requests=0,
        documents=7,facts=43,sections=6,input_interpretations=0,
        candidate_state=result['candidate_state'], low_status=result['low_status'], low_writer_calls=result['low_writer_calls'],
        parser_validator_review_test_revalidation_sqlite_markdown_web='PASS',
        mock_proposals=result['new_model_candidates'],budgets=result['budgets'],
        system_chars=len(system),request_sha256=sha(raw_request),
        native_frozen_bundle_sha256=result['frozen_bundle_sha256'],
        code_sha256=code_hashes(), historical_files_unchanged=True,
        historical_plan_and_sources_identical=True,
        permit_issued=False,authenticated_human_signoff=False,production_authorized=False)
    save(directory/'readiness.json', ready)
    manifest={p.relative_to(directory).as_posix():sha(p.read_bytes()) for p in sorted(directory.rglob('*')) if p.is_file()}
    save(directory/'artifact-sha256.json', manifest)
    (directory/'bundle.sha256').write_text(sha((directory/'artifact-sha256.json').read_bytes())+'\n',encoding='ascii')
    return {k:v for k,v in ready.items() if k not in {'code_sha256','budgets'}}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,required=True)
    print(json.dumps(prepare(parser.parse_args().output_dir),indent=2))
