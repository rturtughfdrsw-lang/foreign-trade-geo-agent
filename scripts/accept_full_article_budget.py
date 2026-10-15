"""Substantive six-chapter OFFLINE Mock stress test; never issues a LIVE permit."""
import argparse
from dataclasses import replace
from datetime import UTC, datetime, timedelta
import hashlib
import json
import math
from pathlib import Path

from scripts import accept_autonomous_interpretation as native
from foreign_trade_geo_agent.core import content_draft as cd
from foreign_trade_geo_agent.storage.serialization import _decode
from foreign_trade_geo_agent.web.experiment import code_hashes


# Independently scripted provider response. None of this prose is an input
# interpretation option. Technical entailment still requires a human reviewer.
ANALYSIS = (
    (
        'Begin with the part and its fixture together rather than the bare component. The larger fixture scenario excludes NCX7 on the supplied table and static-load proposal, while NCX10 stays a conditional candidate. A nominal fit leaves tool access, clamp locations and the intended path unresolved. Selecting the larger machine on table size alone would skip those checks. Ask the supplier to annotate the intended setup so that the shortlist records why a candidate remains under consideration.',
        'The smaller fixture scenario keeps both models in the discussion, so the useful comparison shifts to the actual configuration and operation. Check the quoted control, spindle, coolant arrangement and magazine layout against the configuration represented by the records. Separately quoted options need their own application review; the base-machine trial cannot establish their behavior. An option list becomes useful when each requested item is linked to a machining need and an explicit verification question.',
        'Treat travels, table surface and combined static load as different screening questions. The fixture can fit on a surface while the tool path or access remains unresolved, and the centered static proposal does not settle an off-center cutting setup. Keep the model names beside each selected record rather than pooling the specifications into a generic machine description. A conditional shortlist should state which drawing, fixture and configuration checks remain open before it becomes an order recommendation.',
    ),
    (
        'An unloaded spindle rating describes a bench condition rather than the interaction between a cutting tool and a workpiece. Motor nameplate power likewise leaves the torque curve unresolved for application review. The purchasing question is therefore whether the intended operation has representative loaded evidence, especially where the buyer expects material removal behavior that is not measured by the bench procedure. Keep the rating as a configuration fact while requesting the records needed to assess the proposed cut.',
        'Compare like records before drawing a ranking. Different unloaded protocols and a motor nameplate describe different aspects of the equipment; combining them into a claim of stronger cutting performance would exceed the supplied evidence. The warm-up procedure is also a condition attached to the observations, rather than a thermal drift characterization. When requesting a loaded trial, retain the tool, material, coolant and setup alongside the result so that the buyer can judge whether the test addresses the intended operation.',
        'For the enquiry, identify the operation that makes spindle behavior important and request the applicable torque records and loaded-cycle observations. Ask how the proposed configuration differs from the tested base machine and how the supplier intends to resolve those differences. A useful response connects the configuration to the representative test instead of replacing that test with a higher headline rating. The buyer can then keep the choice conditional until the relevant application evidence is available for review.',
    ),
    (
        'The aluminum record is a recipe tied to a particular drawing, fixture, tool and coolant arrangement. It is useful as a starting point for discussion when those conditions match the intended work, but it does not establish an interchangeable setting for every aluminum part. Thin walls and deep cavities are outside the recorded application. Explain the actual geometry in the enquiry and ask which aspects of the recorded setup carry over and which require a new representative trial.',
        'The matched aluminum trial offers a narrower comparison than a general throughput claim. Its timing excludes loading and comes from a small sample, so the buyer should define the complete production cycle before comparing it with an internal target. Loading, tool changes and the required part checks should be discussed explicitly where they belong to that target. Keep the observed trial timing attached to its drawing and recipe; do not use it as a contractual production limit.',
        'The steel record applies to NCX10 and an unhardened material with its own fixture and tool. It supplies no matched NCX7 steel comparison, and the dossier establishes no suitability conclusion for hardened steel, titanium or unattended production. This distinction changes the next step: a buyer with an unrepresented application needs a scoped trial request rather than a broad assurance of compatibility. Send the intended material condition and geometry so that the supplier can propose evidence for that application.',
    ),
    (
        'A measured coupon result is an observation under a stated method, not an automatic acceptance verdict. The recorded feature is outer width, and the comparator uncertainty is assumed rather than a calibration certification. The proposed acceptance criterion introduces a separate contractual question: how the parties will decide conformity when uncertainty matters. Keep the observation, proposed threshold and unresolved decision rule distinct, so that an apparent fit within a proposed tolerance does not become an agreed guarantee.',
        'Start the acceptance discussion with the drawing revision and the features that matter to the buyer. Outer-width results do not establish bore position, surface finish or process capability. Equal observed coupon deviations also do not establish equal production accuracy between machines. Request a measurement plan for the intended features, including method, conditions and the basis for interpreting results. The aim is to agree what evidence answers the purchasing question, rather than to reuse a convenient coupon result for a different feature.',
        'The proposed factory procedure can become a negotiating document when preparation, repeated pieces, measurement and disposition are made explicit. Connect the actual quoted configuration to that procedure and record what happens when a result is disputed or requires correction. Site acceptance needs its own agreement about utilities, installed configuration and the representative piece. A factory record can inform that conversation while leaving the site-specific conditions and signoff unresolved until the parties settle them.',
    ),
    (
        'Build the RFQ around the application evidence needed for a decision: drawing revision, material, critical tolerances, fixture layout, tool list, target cycle and utilities. Submission starts a supplier review; it does not mean the proposed application has been accepted. Ask for a response that identifies the configuration under review, the applicable records and any remaining testing. This creates a practical basis for comparing offers without treating a generic specification sheet as an application approval.',
        'Separate proposed procedures from agreed obligations. The dossier describes buyer drawing approval, supplier setup and measurement records, joint disposition and correction followed by re-test. These points should be negotiated with the configuration and acceptance schedule, including who supplies the test inputs and who decides whether correction is satisfactory. Avoid assuming that the existence of a proposed procedure authorizes shipment release. The final agreement needs an explicit account of the parties responsible for each decision.',
        'Define the cycle boundary in the enquiry and carry the same boundary into negotiation. A bench observation excluding loading answers a different question from a production target that includes handling and tool changes. Where a target remains unresolved, label it as a negotiating item and ask for representative evidence. Keep the drawing, configuration, setup record and proposed acceptance terms together so that a later change can be reviewed against the same purchasing basis rather than silently inheriting an earlier conclusion.',
    ),
    (
        'Read the dispatch proposal from its triggering conditions, then distinguish it from arrival at the destination. Deposit and signed configuration start the proposed schedule, while options may change it and international transit is excluded. The base proposal also excludes freight, import duties, rigging and site utilities. These distinctions affect what the buyer must arrange and what still belongs in the quotation. Request the applicable trade term and destination scope before using the dispatch proposal in a project schedule.',
        'The training proposal covers English remote sessions for designated operators on base operation and maintenance. Advanced programming and on-site commissioning require separate agreement. Match the proposed sessions to the people and tasks involved in handover, and ask which needs remain outside that scope. Utility readiness belongs in the preparation discussion as well. A useful training plan states the intended audience and outstanding arrangements instead of turning a limited remote proposal into a promise of complete site readiness.',
        'An initial support response is different from a repair or recovery commitment. Keep the diagnostic ticket requirement and support calendar alongside that proposal, and negotiate parts, travel, exclusions and any warranty terms in writing. The dossier register identifies the fictional document scope; it is not independent technical authentication. Maintain the applicable revisions with the quotation and ask the supplier to identify changed configurations or terms, so that commercial decisions remain tied to the records actually reviewed.',
    ),
)


def full_mock(value, facts):
    response = native.mock_response(value, facts)
    for index, section in enumerate(response['draft']['sections']):
        direct, template = section['blocks'][0]['claims'][:2]
        brief = value.change_plan_report.operations[0].new_resource_spec.section_briefs[index]
        blocks = []
        for paragraph, prose in enumerate(ANALYSIS[index]):
            claim = json.loads(json.dumps(template))
            if paragraph == 0:
                limit, action = brief.limitations, brief.procurement_action
            else:
                limit = ('Application evidence remains conditional on the recorded setup.' if paragraph == 1
                         else 'The proposed purchasing conclusion requires application review.')
                action = ('Request the applicable setup and configuration records.' if paragraph == 1
                          else 'Ask for a written response to the unresolved verification questions.')
            claim['text'] = prose + ' ' + limit + ' ' + action
            claim['proposal'].update(limitation=limit, procurement_action=action)
            blocks.append(dict(kind='PARAGRAPH', claims=([direct, claim] if paragraph == 0 else [claim])))
        section['blocks'] = blocks
    section['blocks'].append(dict(kind='PARAGRAPH', claims=[dict(
        text='Send the current drawing revision, material condition, fixture layout, target cycle and acceptance priorities to request an application review and a scoped quotation.',
        claim_type='CALL_TO_ACTION', page_refs=[], source_refs=[], customer_refs=[])]))
    return response


def measure(text):
    """Deliberately labelled heuristic, never DeepSeek tokenizer or API usage."""
    return dict(chars=len(text), utf8_bytes=len(text.encode('utf-8')),
        approximate_tokens_low=math.ceil(len(text) / 4),
        approximate_tokens_high=math.ceil(len(text) / 2),
        method='CHARACTER_HEURISTIC_2_TO_4_CHARS_PER_TOKEN_NOT_A_PROVEN_BOUND',
        exact_tokens=None, server_usage=None)


def prepare(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    result = native.prepare(directory / 'native', response_factory=full_mock)
    rich = directory / 'native/B-rich-evidence'
    value = _decode(json.loads((rich/'frozen-native-input.json').read_bytes()), cd.ContentDraftInput)
    response = json.loads((rich/'mock-response.json').read_bytes())
    raw = json.dumps(response, ensure_ascii=False, separators=(',', ':'))
    request = json.loads((directory/'native/flash-request.FROZEN-NOT-AUTHORIZED.json').read_bytes())
    user, system = request['messages'][1]['content'], request['messages'][0]['content']
    material = json.loads(user)
    prose = '\n\n'.join(c['text'] for s in response['draft']['sections'] for b in s['blocks'] for c in b['claims'])
    article = '\n\n'.join('## '+s['outline_heading']+'\n\n'+'\n\n'.join(' '.join(c['text'] for c in b['claims']) for b in s['blocks']) for s in response['draft']['sections'])
    (directory/'mock-article.md').write_text('# SYNTHETIC / Mock response — not model quality evidence\n\n'+article, encoding='utf-8')
    (directory/'system-prompt.txt').write_bytes(system.encode())
    (directory/'user-material.json').write_bytes(user.encode())
    (directory/'request.FROZEN-NOT-AUTHORIZED.json').write_bytes((directory/'native/flash-request.FROZEN-NOT-AUTHORIZED.json').read_bytes())
    # Disjoint component measurement; wrappers are measured by subtraction.
    components = dict(task_plan_brief={k: material[k] for k in ('change','opportunity','writing_brief')},
        customer_facts=[s['facts'] for s in material['customer_evidence']['sources']],
        source_references=[{k:v for k,v in s.items() if k != 'facts'} for s in material['customer_evidence']['sources']],
        input_interpretations=material['customer_evidence']['interpretations'],
        planning_context={k:material[k] for k in ('pages','sources')})
    measured = {k: measure(json.dumps(v,ensure_ascii=False,separators=(',',':'))) for k,v in components.items()}
    measured['input_json_metadata_and_wrappers'] = measure(' ' * (len(user)-sum(v['chars'] for v in measured.values())))
    measured['system_prompt'] = measure(system)
    measured['output_body'] = measure(prose)
    measured['output_json_refs_proposals_and_metadata'] = measure(' ' * (len(raw)-len(prose)))
    output_estimate = math.ceil(len(raw)/2)
    budgets = dict(result['budgets'], article_words_whitespace=len(prose.split()), article_body_chars=len(prose),
        old_mock_words=368, sections=6, candidate_interpretations=18,
        components=measured, input_total=measure(system+user), output_total=measure(raw),
        estimate_safety_margin_output_tokens=cd.MAX_PROVIDER_TOKENS-output_estimate,
        tokenizer='NO_CONFIRMED_APPLICABLE_DEEPSEEK_TOKENIZER', actual_usage=None,
        no_claim_that_bytes_equal_tokens=True)
    native.prior.save(directory/'budgets.json', budgets)
    now = datetime.now(UTC)
    preflight = dict(status='BLOCKED_TOKEN_BOUND_CONFIRMATION', model='deepseek-flash',
        endpoint='https://api.deepseek.com/chat/completions', max_requests=1, retries=0,
        temperature=0, thinking='disabled', response_format={'type':'json_object'},
        max_output_tokens=cd.MAX_PROVIDER_TOKENS, timeout_seconds=60,
        created_at=now.isoformat(), preparation_valid_until=(now+timedelta(hours=24)).isoformat(),
        price_source='https://api-docs.deepseek.com/quick_start/pricing/',
        public_price_checked_date='2026-10-11', currency='USD',
        peak_cache_miss_input_per_million=0.3, peak_output_per_million=1.2,
        assumed_input_token_ceiling=65536,
        conditional_peak_estimate_usd=(65536*0.3+cd.MAX_PROVIDER_TOKENS*1.2)/1000000,
        proposed_cost_limit_usd=0.05, actual_spending_authorized=0, permit_issued=False,
        cost_is_provider_estimate_not_account_hard_cap=True,
        authorization_before_checks=[
            'Confirm applicable tokenizer or explicitly accept the documented approximate token budget and its uncertainty.',
            'Recheck public model alias, context/output limits and prices; bind the exact frozen request and code hashes.',
            'Check current evidence, Plan, scope review and the preparation validity; refresh test review timestamp without changing request bytes.',
            'Obtain a NEW explicit authorization for this bundle only: one Flash request, no retries, 60 seconds, proposed USD 0.05 limit.',
            'Authorize only SYNTHETIC quality testing and private response retention, never WordPress or production delivery.'],
        retention=dict(raw='response-body.bin', model_text='model-output.txt', usage='result.json or failed.json',
            deterministic_failure='rejected-candidate.txt', pending_review='local-review.sqlite3',
            oversized_response='bounded partial response with response_complete=false; never a successful full response',
            secret_bearing_response='withheld with explicit safe failure, never stored'),
        quality_approval='All new interpretations remain PENDING_SEMANTIC_REVIEW; TEST decisions cannot authorize production.')
    native.prior.save(directory/'real-request-preflight.json', preflight)
    old = Path('docs/seo-autonomous-interpretation-2026-10-11/final-v2/B-rich-evidence/mock-response.json')
    summary = dict(offline_contract='OFFLINE_CONTRACT_READY', real_request_preflight=preflight['status'],
        real_writing_quality='REAL_WRITING_QUALITY_UNTESTED', production='PRODUCTION_NO_GO',
        low_status=result['low_status'], low_writer_calls=result['low_writer_calls'],
        rich_candidate_state=result['candidate_state'], parser_validator_finalizer_sqlite_markdown_web='PASS',
        mock_only=True, real_model_requests=0, wordpress_requests=0, production_authorized=False,
        documents=7, facts=43, input_preapproved_interpretations=0,
        new_candidates=result['new_model_candidates'], budgets=budgets,
        request_sha256=hashlib.sha256((directory/'request.FROZEN-NOT-AUTHORIZED.json').read_bytes()).hexdigest(),
        bundle_sha256=result['frozen_bundle_sha256'], historical_368_word_mock_sha256=hashlib.sha256(old.read_bytes()).hexdigest(),
        code_sha256=code_hashes(), authenticated_human_signoff=False)
    native.prior.save(directory/'readiness.json', summary)
    native.prior.save(directory/'artifact-sha256.json', {p.relative_to(directory).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(directory.rglob('*')) if p.is_file()})
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    result = prepare(parser.parse_args().output_dir)
    print(json.dumps({k:v for k,v in result.items() if k not in {'code_sha256','budgets'}}, indent=2))
