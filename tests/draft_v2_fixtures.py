"""Read-only conversion of frozen synthetic design fixtures to V2 contracts."""
from dataclasses import replace
import json
from pathlib import Path

from foreign_trade_geo_agent.core.content_draft import ContentDraftInput
from foreign_trade_geo_agent.core.draft_selection_contract import (
    DraftSelectionContract, SectionEvidenceBudget, FactSelectionReason,
    evidence_digest, plan_digest,
)
from foreign_trade_geo_agent.storage.serialization import _decode

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / 'docs/seo-draft-contract-v2-design'
HISTORY = ROOT / 'docs/seo-flash-contract-quality-live-2026-10-12/frozen-v1'


def fixture():
    value = _decode(json.loads((HISTORY / 'native-input.json').read_bytes()), ContentDraftInput)
    design = json.loads((DESIGN / 'contract-v2.json').read_bytes())
    sections = tuple(SectionEvidenceBudget(
        section_id=s['section_id'], heading=s['heading'], question=s['reader_question'],
        requirement_ids=tuple(s['requirement_ids']), required_sources=tuple(s['required_sources']),
        required_facts=tuple(s['required_facts']), optional_facts=tuple(s['optional_facts']),
        selected_facts=tuple(s['selected_facts']), required_direct_facts=tuple(s['required_direct_facts']),
        claim_budget=s['claim_max'], block_budget=s['block_max'], explanation_budget=s['explanation_count'],
        direct_fact_budget=s['direct_max'], cta_budget=int(s['section_id'] == 'S6'),
        required_limitation=s['limitation'], verification_action=s['procurement_action'],
    ) for s in design['sections'])
    reasons = tuple(FactSelectionReason(f['fact_ref'], f['priority'], f['reason'],
                    tuple(f['assigned_sections'])) for f in design['fact_priorities'])
    contract = DraftSelectionContract('seo-draft-selection-v2', value.customer_evidence.snapshot_sha256,
        evidence_digest(value.customer_evidence), plan_digest(value), sections, reasons)
    return value, contract


def change_section(contract, index=0, **updates):
    sections = list(contract.sections)
    sections[index] = replace(sections[index], **updates)
    return replace(contract, sections=tuple(sections))


def explanation_fixture(contract, raw=None):
    from foreign_trade_geo_agent.core.draft_explanation_contract import ExplanationContract, ExplanationAnnotation
    from foreign_trade_geo_agent.core.draft_selection_contract import selection_digest, text_digest
    raw = raw or (DESIGN / 'mock-response.json').read_text(encoding='utf-8')
    original = json.loads((DESIGN / 'explanation-annotations.json').read_bytes())
    annotations = {(a['section_id'], a['block_index'], a['claim_index']): a for a in original['explanations']}
    items, number = [], 0
    for si, section in enumerate(json.loads(raw)['draft']['sections'], 1):
        for bi, block in enumerate(section['blocks']):
            for ci, claim in enumerate(block.get('claims', block.get('items', []))):
                number += 1
                if claim['claim_type'] != 'EVIDENCE_BASED_INTERPRETATION':
                    continue
                a = annotations[(f'S{si}', bi, ci)]
                items.append(ExplanationAnnotation(f'CL{number}', f'S{si}', tuple(claim['customer_refs']),
                    text_digest(claim['text']), a['buyer_implication'], a['non_applicability'], a['verification_action']))
    return raw, ExplanationContract('seo-draft-explanation-v2', selection_digest(contract),
        contract.evidence_snapshot_sha256, contract.plan_sha256, text_digest(raw), tuple(items))
