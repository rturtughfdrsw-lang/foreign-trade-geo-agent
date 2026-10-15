"""Generate a hand-authored, synthetic v2 design example. No provider clients."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
HISTORY = ROOT / 'docs/seo-flash-contract-quality-live-2026-10-12/frozen-v1'
MATERIAL = ROOT / 'docs/seo-draft-contract-offline-2026-10-12/frozen-v1/user-material.json'


def encode(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


# required facts, optional facts, direct facts, direct ceiling, block ceiling.
ROWS = [
    (['E2.F01', 'E2.F03', 'E2.F05', 'E2.F07', 'E5.F01'],
     ['E2.F02', 'E2.F06', 'E5.F02'], None, 6, 4),
    (['E1.F01', 'E3.F01', 'E3.F02', 'E3.F03'], ['E3.F04'], None, 5, 3),
    (['E4.F01', 'E4.F04', 'E4.F05', 'E4.F08'], ['E4.F02', 'E4.F03', 'E4.F06'], None, 5, 3),
    (['E3.F05', 'E3.F07', 'E4.F01', 'E6.F03'], ['E3.F06', 'E4.F07', 'E6.F02'],
     ['E3.F05', 'E3.F07', 'E6.F03'], 5, 3),
    (['E6.F01', 'E6.F04', 'E6.F05'], ['E6.F06'], None, 4, 3),
    (['E2.F09', 'E5.F05', 'E7.F01', 'E7.F03', 'E7.F04', 'E7.F05'],
     ['E7.F02', 'E7.F06', 'E7.F07'], None, 7, 4),
]

# Each entry: genuine premises, buyer implication, non-applicability,
# concrete verification extension, short proposal reasoning.
EXPLANATIONS = [
    [
        (['E2.F01', 'E2.F03', 'E2.F05', 'E2.F07', 'E5.F01'],
         'For the larger fixture case, exclude NCX7 from that shortlist and retain NCX10 only as a conditional candidate. This changes which configuration deserves further application review before the buyer invests in a machining trial.',
         'That exclusion concerns the supplied fixture case, not every smaller part or alternative setup. Fixture clearance and dynamic loads remain unassessed.',
         'Ask the supplier to check the proposed orientation, travel access and operating load against the intended drawing before agreeing which configuration proceeds to a representative trial.',
         'The fixture case supplies an exclusion; nominal envelopes alone do not establish operating fit.'),
        (['E2.F01', 'E2.F03', 'E2.F05', 'E2.F07'],
         'Nominal travel and static load are different purchasing checks. Treat them as separate screening inputs so a candidate is not accepted merely because its nominal working envelope appears compatible with the intended part.',
         'A different fixture orientation or an off-center operating load requires a fresh review; the nominal screening conclusion does not settle these conditions. Fixture clearance and dynamic loads remain unassessed.',
         'Have the buyer identify tool access and the supplier document unresolved operating checks, then use that review to decide the scope of the subsequent application trial.',
         'Nominal screening and operating verification answer different purchasing questions.'),
    ],
    [
        (['E1.F01', 'E3.F03'],
         'Use the unloaded spindle records to identify what was rated under the recorded bench conditions. They do not establish which candidate should be purchased for a loaded cutting application or a production cycle target.',
         'The rating comparison cannot be carried into a different spindle configuration or loaded process without representative evidence. Loaded cutting capability remains unassessed.',
         'Have the supplier identify the tested configuration and record the intended material, tooling and operation so the buyer can judge whether the loaded trial answers the purchasing question.',
         'Unloaded rating evidence cannot settle loaded application selection.'),
        (['E3.F01', 'E3.F02'],
         'Treat motor nameplate information as a configuration input, separate from the unloaded spindle records. Purchasing a cutting process requires evidence about the intended operation rather than treating nameplate power as measured cutting power.',
         'This reasoning does not supply a torque curve or an application performance ranking, and a changed motor configuration requires renewed checking. Loaded cutting capability remains unassessed.',
         'Ask the supplier to distinguish nameplate documentation from loaded measurements and identify the operating conditions in the records before using them to justify the configuration choice.',
         'Nameplate power is not measured cutting power and cannot replace loaded records.'),
    ],
    [
        (['E4.F01', 'E4.F08'],
         'Application screening starts with the supplied drawing and material boundary. A buyer should use that boundary to specify a representative part trial before treating the recorded application as a reason to shortlist a production configuration.',
         'Thin walls, deep cavities and the other listed applications are outside the supplied suitability conclusion; a different part is not automatically established to work. Other applications require new representative trials.',
         'Have the buyer mark geometry and material differences and ask the supplier to propose a representative setup; agree which differences the new trial must resolve before making the application choice.',
         'Recorded geometry and material boundaries constrain the application conclusion.'),
        (['E4.F04', 'E4.F05'],
         'The drawing trial timings are useful inputs to a cycle discussion, but they do not justify choosing a production machine on throughput alone. The buyer needs the complete intended cycle defined before comparing purchasing alternatives.',
         'A production process that includes loading cannot be treated as identical to the recorded trial boundary, and the small sample does not establish a general advantage. Other applications require new representative trials.',
         'Ask the buyer to identify loading and operating steps, then have the supplier document the representative cycle boundary so both parties can decide what a meaningful comparison should measure.',
         'Trial timing boundaries and small samples prevent a general throughput ranking.'),
    ],
    [
        (['E3.F05', 'E3.F07', 'E4.F01', 'E6.F03'],
         'Keep the recorded outer-width observation separate from the proposed acceptance criterion. Their shared drawing and fixture context helps define a comparison, but the buyer still needs an agreed measurement decision rule before treating an observation as acceptance.',
         'This comparison does not establish bore position, surface finish or performance on another drawing; neither the common setup nor an uncertainty assumption provides that extension. The samples do not establish production capability.',
         'Have the supplier document the measured feature and uncertainty basis, and have both parties agree how the recorded result will be assessed against the proposed criterion before authorizing an acceptance decision.',
         'Shared drawing context supports comparison, not automatic acceptance or broader capability.'),
        (['E3.F07', 'E4.F01', 'E6.F03'],
         'Define acceptance around the intended feature rather than treating a coupon result as a universal machine guarantee. This affects which records the buyer requests and which features must be represented in the agreed acceptance procedure.',
         'A different geometry or a different feature needs its own agreed representation and measurement basis; the supplied outer-width check cannot settle every application. The samples do not establish production capability.',
         'Ask the buyer to name the critical features and ask the supplier to document the measurement method; agree the decision rule and how unresolved features will be tested before release.',
         'Feature-specific observations require a matching acceptance and measurement procedure.'),
    ],
    [
        (['E6.F01', 'E6.F04'],
         'Use the proposed enquiry fields to define what the supplier is being asked to evaluate. A complete cycle target needs an agreed boundary before it can become a purchasing criterion, so the buyer should resolve operating inputs early.',
         'A bench timing is not a contractual production limit, and an enquiry without an agreed cycle boundary cannot settle that obligation. Proposed criteria require written agreement.',
         'Ask the buyer to identify loading and tool-change steps and the supplier to record assumptions, then agree what the cycle criterion includes before using it in the purchase order.',
         'Enquiry inputs and cycle boundaries must precede agreement on production obligations.'),
        (['E6.F05'],
         'Acceptance responsibilities affect the purchase decision because the parties need to know who approves the drawing, records the setup and resolves a failed check. Use the proposed roles to structure that agreement before shipment release is considered.',
         'The proposed roles do not establish that either party has already accepted the procedure or authorized release, and unresolved corrections still need agreed disposition. Proposed criteria require written agreement.',
         'Have both parties identify the responsible people and record the correction and re-test process, then confirm which evidence and decisions are needed before the agreed release step can proceed.',
         'Proposed approval and correction roles need explicit agreement before release decisions.'),
    ],
    [
        (['E2.F09', 'E5.F05', 'E7.F01'],
         'Separate configuration review from dispatch planning. The buyer should confirm whether the quotation concerns the tested base arrangement or separately quoted options before using the proposed dispatch schedule to plan procurement and application verification.',
         'Optional equipment is not validated by the base fixture records, and the dispatch proposal excludes international transit; a different configuration needs its own review. The proposals are not signed commitments.',
         'Ask the supplier to identify the quoted configuration and schedule exclusions, then have both parties agree the applicable dispatch basis before treating it as an input to the purchasing timetable.',
         'Configuration differences and dispatch exclusions constrain procurement planning.'),
        (['E7.F03', 'E7.F04', 'E7.F05'],
         'Assess training, support response and parts warranty as separate purchasing obligations. Each addresses a different operating need, so the buyer should check their individual scope before deciding what additional arrangements the intended operation requires.',
         'Remote training does not settle commissioning, an initial support response does not promise restoration, and parts coverage retains its own exclusions rather than the dispatch trigger. The proposals are not signed commitments.',
         'Have the buyer identify operator and service needs and ask the supplier to confirm each scope and exclusion, then resolve the remaining arrangements in the commercial agreement before purchase.',
         'Training, support response and warranty have separate scopes and cannot be merged into a single commitment.'),
    ],
]


def build():
    material = json.loads(MATERIAL.read_bytes())
    native = json.loads((HISTORY / 'native-input.json').read_bytes())
    facts = {f['fact_ref']: f for s in material['customer_evidence']['sources'] for f in s['facts']}
    briefs = material['change']['new_resource']['section_briefs']
    plan = dict(version='draft-contract-v2-design', test_only=True, production_authorized=False,
                baseline_input_sha256=sha((HISTORY / 'native-input.json').read_bytes()),
                material_sha256=sha(MATERIAL.read_bytes()),
                snapshot_sha256=native['customer_evidence']['snapshot_sha256'],
                budgets=dict(claim_hard=48, block_hard=24, claim_target=43, block_target=20,
                             direct_max=30, explanations=12, cta=1, transitions=0), sections=[])
    sections, annotations = [], []
    for si, (brief, row, examples) in enumerate(zip(briefs, ROWS, EXPLANATIONS), 1):
        required, optional, direct, direct_max, block_max = row
        direct = required if direct is None else direct
        plan['sections'].append(dict(section_id=f'S{si}', heading=brief['heading'],
            reader_question=brief['reader_question'], requirement_ids=brief['requirement_ids'],
            required_sources=brief['supporting_evidence'], required_facts=required,
            optional_facts=optional, selected_facts=required, required_direct_facts=direct,
            direct_max=direct_max, explanation_count=2, claim_max=direct_max+2+(si == 6),
            block_max=block_max, limitation=brief['limitations'], procurement_action=brief['procurement_action']))
        claims = [dict(text=facts[r]['quote'], claim_type='OBSERVED_PRODUCT_FACT',
                       page_refs=[], source_refs=[], customer_refs=[r]) for r in direct]
        blocks = [dict(kind='PARAGRAPH', claims=claims[i:i+4]) for i in range(0, len(claims), 4)]
        for refs, implication, applicability, action, reasoning in examples:
            action = brief['procurement_action'] + ' ' + action
            text = ' '.join((implication, applicability, action))
            claim = dict(text=text, claim_type='EVIDENCE_BASED_INTERPRETATION', page_refs=[],
                         source_refs=[], customer_refs=refs, proposal=dict(
                             procurement_question=brief['reader_question'], reasoning=reasoning,
                             assumptions='The intended application is evaluated within the cited conditions; changed conditions require renewed agreement or verification.',
                             limitation=brief['limitations'], procurement_action=brief['procurement_action']))
            blocks.append(dict(kind='PARAGRAPH', claims=[claim]))
            annotations.append(dict(section_id=f'S{si}', block_index=len(blocks)-1, claim_index=0,
                text_sha256=sha(text.encode()), buyer_implication=implication,
                non_applicability=applicability, verification_action=action))
        sections.append(dict(outline_heading=brief['heading'], blocks=blocks))
    selected_all = {r for s in plan['sections'] for r in s['selected_facts']}
    optional_all = {r for s in plan['sections'] for r in s['optional_facts']}
    excluded = {
        'E2.F04': 'Magazine detail is deferred until tool layout is specified; it does not change the fixture shortlist in this guide.',
        'E2.F08': 'Magazine detail is deferred until tool layout is specified; it does not change the fixture shortlist in this guide.',
        'E5.F03': 'F5 selection reminder cannot route to F2; S2 reasons from its own unloaded and nameplate records.',
        'E5.F04': 'F5 selection reminder cannot route to F4/F6; S4 reasons from its own observation and acceptance premises.',
    }
    optional_reasons = {
        'E2.F02': 'Table dimensions can expand the fixture discussion; the selected explicit fixture exclusion already answers this branch.',
        'E2.F06': 'Table dimensions can expand the fixture discussion; the selected explicit fixture exclusion already answers this branch.',
        'E5.F02': 'The smaller fixture branch can be added if the intended application requires that distinct shortlist.',
        'E3.F04': 'Warm-up detail can be selected for a thermal setup discussion; no thermal performance claim is made here.',
        'E4.F02': 'Tooling recipe detail can be added if it changes the intended application comparison.',
        'E4.F03': 'Recipe parameters can be added for process replication; this guide makes no universal cutting recommendation.',
        'E4.F06': 'The steel recipe can support a separate steel branch; this example keeps the matched aluminum comparison.',
        'E3.F06': 'The second coupon observation can expand the comparison; no model accuracy ranking is made here.',
        'E4.F07': 'The steel measurement needs a separate measurement context; this example focuses the acceptance discussion on drawing A.',
        'E6.F02': 'Detailed proposed warm-up/setup can be added when negotiating the complete acceptance procedure.',
        'E6.F06': 'Site acceptance can be expanded as another responsibility branch after the factory release discussion.',
        'E7.F02': 'Destination cost allocation can expand the commercial section; no landed-cost estimate is made here.',
        'E7.F06': 'Parts logistics can expand the service branch; no stock or shipping commitment is made here.',
        'E7.F07': 'Register provenance can be displayed if document reconciliation becomes a reader decision; evidence binding still retains versions.',
    }
    plan['fact_priorities'] = [dict(fact_ref=r,
        priority='P0' if r in selected_all else 'P1' if r in optional_all else 'P2',
        selected=r in selected_all,
        assigned_sections=[s['section_id'] for s in plan['sections'] if r in s['selected_facts']],
        reason=('Required decision premise or necessary scope/source witness for the assigned reader question.'
                if r in selected_all else optional_reasons.get(r, excluded.get(r, 'Deferred pending a distinct reader decision.'))))
        for r in facts]
    sections[-1]['blocks'][-1]['claims'].append(dict(
        text='Send the drawing revision, material condition, fixture layout, target cycle, acceptance priorities and configuration and delivery inputs for a scoped review.',
        claim_type='CALL_TO_ACTION', page_refs=[], source_refs=[], customer_refs=[]))
    response = dict(draft=dict(change_ref='C1', draft_type='NEW_RESOURCE_DRAFT', sections=sections))
    raw_plan, raw_response = encode(plan), encode(response)
    sidecar = dict(version=plan['version'], test_only=True, candidate_sha256=sha(raw_response),
        contract_sha256=sha(raw_plan), snapshot_sha256=plan['snapshot_sha256'], explanations=annotations)
    for name, raw in [('contract-v2.json', raw_plan), ('mock-response.json', raw_response),
                      ('explanation-annotations.json', encode(sidecar))]:
        (HERE / name).write_bytes(raw)
    article = ['# Synthetic v2 mock reading view',
               '> Hand-authored offline example. Pending semantic review; no human signoff or delivery authorization.']
    for section in sections:
        article.append('## ' + section['outline_heading'])
        for block in section['blocks']:
            article.append(' '.join(c['text'] for c in block['claims']))
    (HERE / 'mock-article.md').write_text('\n\n'.join(article) + '\n', encoding='utf-8')
    return response


if __name__ == '__main__':
    build()
    print('Created local synthetic fixtures; no provider or delivery operation.')
