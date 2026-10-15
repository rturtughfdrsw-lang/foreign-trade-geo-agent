"""Offline comparison materials only. No transport, permit, reviewer or execution."""
from copy import deepcopy
from dataclasses import asdict
import difflib
import hashlib
import json
from pathlib import Path

from foreign_trade_geo_agent.adapters.deepseek_content_draft import (
    DeepSeekContentDraftWriter, content_draft_request_payload,
)
from foreign_trade_geo_agent.core import content_draft as cd
from foreign_trade_geo_agent.storage.serialization import _decode
from foreign_trade_geo_agent.web.generation import MockArticleExecutor
from foreign_trade_geo_agent.workflows.content_draft import inspect_candidate_output


ROOT = Path(__file__).resolve().parents[1]
HISTORY = ROOT / 'docs/seo-flash-contract-quality-live-2026-10-12'


def historical_input():
    # Stable offline contract replay, not renewed evidence review or live authority.
    return _decode(json.loads((HISTORY / 'native-input.json').read_bytes()), cd.ContentDraftInput)


def legal_mock():
    """Explicit synthetic counterfactual, never overwrite or approve the real output."""
    response = deepcopy(json.loads((HISTORY / 'model-output.txt').read_bytes()))
    sections = response['draft']['sections']
    # Move whole facts; topic similarity does not override native requirements.
    spindle_comparison = sections[1]['blocks'][1]['claims'].pop(0)
    sections[0]['blocks'][1]['claims'].append(spindle_comparison)
    warm_up = sections[3]['blocks'][0]['claims'].pop(0)
    sections[1]['blocks'][1]['claims'].insert(0, warm_up)
    options = sections[0]['blocks'][2]['items'].pop()
    sections[5]['blocks'][2]['claims'].insert(0, options)
    analyses = [next(c for b in s['blocks'] for c in b.get('claims', b.get('items', []))
                     if c['claim_type'] == 'EVIDENCE_BASED_INTERPRETATION') for s in sections]
    bodies = (
        'Exclude NCX7 for the larger supplied fixture on nominal width and static load; '
        'keep NCX10 conditional. The smaller fixture leaves both candidates in scope, '
        'but path and tool reach need checking. Unloaded ratings do not rank removal '
        'or cycle performance; only the aluminum drawing has matched trials, which '
        'cannot establish durability or lifetime cost.',
        'Unloaded speed and motor nameplate power answer different questions; neither '
        'settles loaded cutting behaviour. Record the proposed warm-up and coolant '
        'conditions in a loaded trial request without treating warm-up as thermal-drift characterization.',
        'The aluminum cycle observations share a drawing and recipe but exclude loading. '
        'Define handling, tool changes and inspection before comparing them with a production target. '
        'The steel setup applies to NCX10 only; changed material condition or geometry needs '
        'a scoped trial rather than an inferred model ranking.',
        'Compare the aluminum outer-width observations with the proposed drawing A criterion '
        'under the recorded method and assumed uncertainty. Agree the conformity decision rule '
        'before treating a measured value as an acceptance verdict. The steel observation uses '
        'a different method and fixture and does not establish conformity to that aluminum criterion.',
        'Use the RFQ fields to define the configuration and acceptance basis, then assign who '
        'records setup, agrees disposition and authorizes correction and re-test. Define loading '
        'and tool changes in cycle criteria before using bench timing in a purchase agreement.',
        'Separate the deposit and signed-configuration trigger for dispatch from the proposed '
        'training, support and warranty terms. Ask for destination scope and the support calendar; '
        'ticket response is not recovery time. Check quoted options against the tested base '
        'configuration and negotiate applicability separately.',
    )
    refs = (
        ['E5.F01', 'E5.F02', 'E5.F03', 'E5.F04', 'E2.F02', 'E2.F03', 'E2.F06', 'E2.F07'],
        ['E1.F01', 'E3.F01', 'E3.F02', 'E3.F03', 'E3.F04'],
        [f'E4.F{i:02}' for i in range(1, 9)],
        ['E3.F05', 'E3.F06', 'E3.F07', 'E4.F07', 'E6.F03'],
        [f'E6.F{i:02}' for i in range(1, 7)],
        ['E2.F09', 'E5.F05', *[f'E7.F{i:02}' for i in range(1, 8)]],
    )
    reasons = (
        'Nominal envelope excludes one setup; model comparisons also need matched trial boundaries.',
        'Unloaded speed, nameplate power and warm-up have distinct evidential roles.',
        'Match drawing and recipe, then define the production cycle boundary; steel evidence is not paired.',
        'Method, feature, fixture and uncertainty determine whether observations address the proposed criterion.',
        'RFQ inputs, cycle boundaries and release responsibilities require explicit agreement.',
        'Dispatch triggers do not condition every proposed term; options and recovery need separate review.',
    )
    for analysis, body, premises, reasoning in zip(analyses, bodies, refs, reasons):
        p = analysis['proposal']
        p['reasoning'] = reasoning
        analysis['text'] = body + ' ' + p['limitation'] + ' ' + p['procurement_action']
        analysis['customer_refs'] = premises
    return response


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def check(value, response):
    return inspect_candidate_output(value, response if isinstance(response, str) else json.dumps(response),
                                    current_snapshot_sha256=value.customer_evidence.snapshot_sha256)


def selected_mock(value):
    """A question-led response with only necessary quotes and genuine premises."""
    response = legal_mock()
    selected = (
        ['E5.F01', 'E5.F02', 'E2.F02', 'E2.F03', 'E2.F06', 'E2.F07'],
        ['E1.F01', 'E3.F03'],
        ['E4.F01', 'E4.F04', 'E4.F05'],
        ['E3.F05', 'E3.F06', 'E3.F07', 'E6.F03'],
        ['E6.F01', 'E6.F04'],
        ['E7.F01', 'E7.F04', 'E2.F09'],
    )
    quotes = value.customer_evidence.quote_map()
    for i, section in enumerate(response['draft']['sections']):
        analysis = next(c for b in section['blocks'] for c in b.get('claims', b.get('items', []))
                        if c['claim_type'] == 'EVIDENCE_BASED_INTERPRETATION')
        if i == 2:
            analysis['customer_refs'].remove('E4.F07')
        if i == 4:
            analysis['customer_refs'] = ['E6.F01', 'E6.F04', 'E6.F05', 'E6.F06']
            analysis['text'] = ('Keep site readiness and the repeated piece distinct from factory trials. '
                                + analysis['text'])
        if i == 5:
            analysis['customer_refs'] = ['E2.F09', 'E5.F05', 'E7.F01', 'E7.F02',
                                         'E7.F03', 'E7.F04', 'E7.F05']
        direct = [dict(text=quotes[r], claim_type='OBSERVED_PRODUCT_FACT',
                       page_refs=[], source_refs=[], customer_refs=[r]) for r in selected[i]]
        section['blocks'] = [dict(kind='PARAGRAPH', claims=direct[n:n+4])
                             for n in range(0, len(direct), 4)]
        section['blocks'].append(dict(kind='PARAGRAPH', claims=[analysis]))
    response['draft']['sections'][-1]['blocks'][-1]['claims'].append(dict(
        text='Send the drawing revision, material condition, fixture layout, target cycle, '
             'acceptance priorities and configuration and delivery inputs for a scoped review.',
        claim_type='CALL_TO_ACTION', page_refs=[], source_refs=[], customer_refs=[]))
    return response


def prepare(directory):
    """Freeze prompt plus explicit fact-selection guidance; never enable execution."""
    directory = Path(directory)
    value = historical_input()
    old_bytes = (HISTORY / 'request.json').read_bytes()
    old = json.loads(old_bytes)
    material = cd.build_content_draft_prompt(value, 'C1').material_json()
    previous_material = json.loads(old['messages'][1]['content'])
    current_material = json.loads(material)
    previous_material['contract']['customer_coverage_rule'] = current_material['contract']['customer_coverage_rule']
    assert previous_material == current_material, 'Only fact-selection guidance may change in user material'
    system = DeepSeekContentDraftWriter.build_system_prompt(
        customer_evidence=True, propose_interpretations=True)
    raw = json.dumps(content_draft_request_payload(system, material),
                     ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    assert raw == MockArticleExecutor.request_for(value)
    new = json.loads(raw)
    assert {k: v for k, v in old.items() if k != 'messages'} == {
        k: v for k, v in new.items() if k != 'messages'}
    assert len(system) <= cd.MAX_SYSTEM_PROMPT_CHARS
    assert len(system.encode()) <= cd.MAX_SYSTEM_PROMPT_BYTES
    assert len(material) <= cd.MAX_USER_MATERIAL_CHARS
    assert len(material.encode()) <= cd.MAX_USER_MATERIAL_BYTES
    assert len(raw) <= cd.MAX_INPUT_ENVELOPE_BYTES
    assert len(raw.decode()) <= cd.MAX_INPUT_ENVELOPE_CHARS
    directory.mkdir(parents=True, exist_ok=False)
    def save(name, item):
        (directory / name).write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding='utf-8')
    (directory / 'request.FROZEN-NOT-AUTHORIZED.json').write_bytes(raw)
    (directory / 'system-prompt.txt').write_text(system, encoding='utf-8')
    (directory / 'user-material.json').write_bytes(material.encode())
    (directory / 'system-prompt.diff').write_text(''.join(difflib.unified_diff(
        old['messages'][0]['content'].splitlines(keepends=True), system.splitlines(keepends=True),
        fromfile='second-live-system', tofile='prompt-only-control-system')), encoding='utf-8')
    mock = selected_mock(value)
    save('mock-response.SYNTHETIC.json', mock)
    original_check = check(value, (HISTORY / 'model-output.txt').read_text(encoding='utf-8'))
    mock_check = check(value, mock)
    assert original_check.state == 'DETERMINISTICALLY_REJECTED'
    assert len(original_check.errors) == 6
    assert mock_check.state == 'PENDING_SEMANTIC_REVIEW' and not mock_check.errors
    save('original-replay.json', asdict(original_check))
    save('mock-validation.json', asdict(mock_check))
    save('section-map.json', [dict(
        heading=b.heading, reader_question=b.reader_question, explanation_goal=b.explanation_goal,
        requirement_ids=b.requirement_ids, supporting_evidence=b.supporting_evidence,
        limitations=b.limitations, procurement_action=b.procurement_action,
        allowed_fact_refs=[f.fact_ref for s in value.customer_evidence.sources
                           if set(s.requirement_ids) & set(b.requirement_ids) for f in s.facts
                           if set(f.requirement_ids) & set(b.requirement_ids)])
        for b in value.change_plan_report.operations[0].new_resource_spec.section_briefs])
    budget = dict(
        system_chars=len(system), system_bytes=len(system.encode()),
        material_chars=len(material), material_bytes=len(material.encode()),
        request_chars=len(raw.decode()), request_bytes=len(raw),
        max_output_tokens=new['max_tokens'], max_requests=1, retries=0, fallback=0,
        proposed_timeout_seconds=60, proposed_response_byte_cap=262144,
        actual_requests=0, authorization_issued=False, spending_authorized_usd=0,
        proposed_budget_usd=0.05, exact_input_tokens=None,
        input_character_heuristic=[(len(system)+len(material))/4, (len(system)+len(material))/2],
        token_estimate_is_not_a_proven_bound=True,
        historical_peak_rates_usd_per_million=dict(input=0.3, output=1.2),
        historical_65536_input_16384_output_scenario_usd=0.0393216,
        current_prices_parameters_and_alias_verified=False)
    save('budget.json', budget)
    readiness = dict(status='FROZEN_SELECTED_FACTS_COMPARISON_NOT_AUTHORIZED',
        request_sha256=sha(raw), historical_request_sha256=sha(old_bytes),
        identical_user_material=False, identical_model_and_parameters=True,
        identical_task_plan_evidence_writing_brief=True, native_input_ref=str(HISTORY / 'native-input.json'),
        changed_wire_fields=['messages[0].content', 'messages[1].content.contract.customer_coverage_rule'],
        historical_raw_model_sha256=sha((HISTORY / 'model-output.txt').read_bytes()),
        original_errors=list(original_check.errors), mock_state=mock_check.state,
        non_prompt_variable='Structured fact-bank coverage now permits a nonempty valid subset; '
                           'Plan question/source coverage and all fact/numeric checks remain unchanged.',
        unresolved='Real-model adherence and semantic quality require a new authorized experiment.',
        live_execution_ready=False,
        before_any_live='Fresh evidence/Plan and code/hash preflight, current official '
                        'model/parameter/price verification, explicit new one-shot authorization required.',
        permit_issued=False, semantic_approval=False, production_authorized=False)
    save('readiness.json', readiness)
    save('artifact-sha256.json', {p.name: sha(p.read_bytes()) for p in sorted(directory.iterdir()) if p.is_file()})
    return readiness


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True, type=Path)
    print(json.dumps(prepare(parser.parse_args().output_dir), indent=2))
