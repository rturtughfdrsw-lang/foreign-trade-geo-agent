"""Explicit offline V2 utilities. No writer, runtime wiring, retries or delivery."""
from collections import Counter
from dataclasses import dataclass
import json

from foreign_trade_geo_agent.core.content_draft import ContentDraftInput, build_content_draft_prompt
from foreign_trade_geo_agent.core.draft_selection_contract import (
    DraftSelectionContract, selection_digest, validate_selection, budget_diagnostics, require,
)
from foreign_trade_geo_agent.core.content_draft import ParagraphSpecification, DraftClaimType, MAX_RAW_OUTPUT_CHARS, MAX_RAW_OUTPUT_BYTES
from foreign_trade_geo_agent.core.draft_candidate_review import inspect_specification
from foreign_trade_geo_agent.core.draft_explanation_contract import ExplanationContract, validate_explanations
from .content_draft import _parse_specification


def build_offline_writer_material(contract: DraftSelectionContract, value: ContentDraftInput, *,
                                  current_snapshot_sha256: str) -> dict:
    """Project a validated artifact to a selected-only view; never call a Writer.

Reuses the unchanged V1 material builder for P/S planning context and validator
metadata. The complete E bank, source quotes and audit reasons never leave this
function. The original evidence bundle remains intact for validation.
"""
    diagnostics = validate_selection(contract, value, current_snapshot_sha256=current_snapshot_sha256)
    old = json.loads(build_content_draft_prompt(value, value.customer_evidence.change_ref).material_json())
    material = {key: old[key] for key in ('change', 'opportunity', 'pages', 'sources', 'writing_brief') if key in old}
    material.update(contract_version=contract.contract_version, selection_sha256=selection_digest(contract),
        evidence_snapshot_sha256=contract.evidence_snapshot_sha256, plan_sha256=contract.plan_sha256,
        offline_only=True, production_authorized=False, budget_diagnostics=list(diagnostics))
    validator_contract = old['contract']
    selected = {r for s in contract.sections for r in s.selected_facts}
    validator_contract['customer_refs'] = sorted(selected)
    material['validator_contract'] = validator_contract
    facts = {f.fact_ref: (source, f) for source in value.customer_evidence.sources for f in source.facts}
    material['sections'] = []
    for section in contract.sections:
        selected_facts = []
        for ref in section.selected_facts:
            source, fact = facts[ref]
            selected_facts.append(dict(fact_ref=ref, quote=fact.quote, source=source.evidence_id,
                version=source.evidence_version, source_sha256=source.content_sha256,
                location=dict(locator=source.source_locator, start=fact.start, end=fact.end),
                requirement_ids=list(fact.requirement_ids)))
        material['sections'].append(dict(section_id=section.section_id, heading=section.heading,
            question=section.question, requirement_ids=list(section.requirement_ids),
            required_sources=list(section.required_sources), required_facts=list(section.required_facts),
            required_direct_facts=list(section.required_direct_facts), selected_facts=selected_facts,
            claim_budget=section.claim_budget, block_budget=section.block_budget,
            explanation_budget=section.explanation_budget, direct_fact_budget=section.direct_fact_budget,
            cta_budget=section.cta_budget, required_limitation=section.required_limitation,
            verification_action=section.verification_action))
    material['explanation_requirements'] = dict(
        fields=['explanation_claim_id', 'section_id', 'selected_fact_refs', 'buyer_implication',
                'non_applicability', 'verification_action'],
        visible_body_binding=True, selected_facts_only=True, semantic_review_required=True)
    return material


@dataclass(frozen=True, slots=True)
class OfflineCandidateCheck:
    state: str
    errors: tuple[str, ...]
    claims: int
    blocks: int
    budget_diagnostics: tuple[str, ...]
    selection_valid: bool
    routing_valid: bool
    explanation_structure_valid: bool

    @property
    def production_authorized(self) -> bool:
        return False

    @property
    def semantic_approved(self) -> bool:
        return False


def inspect_offline_candidate(value: ContentDraftInput, raw: str, selection: DraftSelectionContract,
                              explanations: ExplanationContract, *, current_snapshot_sha256: str) -> OfflineCandidateCheck:
    """Replay stored bytes only, retaining all native errors and V1 Gate behavior."""
    errors, counts = [], Counter()
    claim_total = block_total = 0
    selection_valid = routing_valid = structure_valid = False
    try:
        validate_selection(selection, value, current_snapshot_sha256=current_snapshot_sha256)
        selection_valid = True
        require(type(raw) is str and len(raw) <= MAX_RAW_OUTPUT_CHARS
            and len(raw.encode('utf-8')) <= MAX_RAW_OUTPUT_BYTES, 'OFFLINE_CANDIDATE_SIZE')
        operation = value.change_plan_report.operations[0]
        spec = _parse_specification(raw, expected_change_ref=operation.change_id, operation=operation)
        native = inspect_specification(value, raw, spec, current_snapshot_sha256=current_snapshot_sha256)
        errors.extend(native.errors)
        require(len(spec.sections) == len(selection.sections), 'OFFLINE_SECTION_COUNT')
        routing_errors = []
        for section, budget in zip(spec.sections, selection.sections):
            claims = [c for b in section.blocks for c in (b.claims if isinstance(b, ParagraphSpecification) else b.items)]
            block_total += len(section.blocks)
            claim_total += len(claims)
            kinds = Counter(c.claim_type for c in claims)
            counts.update(kinds)
            used = {r for c in claims for r in c.customer_refs}
            direct = {r for c in claims if c.claim_type is DraftClaimType.OBSERVED_PRODUCT_FACT for r in c.customer_refs}
            if not used <= set(budget.selected_facts):
                routing_errors.append('OFFLINE_FACT_NOT_SELECTED')
            if (not set(budget.required_facts) <= used or used != set(budget.selected_facts)
                    or not set(budget.required_direct_facts) <= direct):
                routing_errors.append('OFFLINE_REQUIRED_FACT_COVERAGE')
            if {r.split('.')[0] for r in used} != set(budget.required_sources):
                routing_errors.append('OFFLINE_SECTION_SOURCE_EQUALITY')
            if len(claims) > budget.claim_budget or len(section.blocks) > budget.block_budget:
                errors.append('OFFLINE_SECTION_BUDGET')
            if (kinds[DraftClaimType.OBSERVED_PRODUCT_FACT] > budget.direct_fact_budget
                    or kinds[DraftClaimType.EVIDENCE_BASED_INTERPRETATION] < budget.explanation_budget
                    or kinds[DraftClaimType.CALL_TO_ACTION] > budget.cta_budget):
                errors.append('OFFLINE_SECTION_RESERVATION')
        errors.extend(routing_errors)
        routing_valid = not routing_errors and not any('SECTION_' in e for e in native.errors)
        if claim_total > 48:
            errors.append('CLAIM_BUDGET')
        if block_total > 24:
            errors.append('BLOCK_BUDGET')
        validate_explanations(explanations, selection, raw, spec)
        structure_valid = True
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError) as exc:
        # Only locally-defined error tokens, never candidate/provider text.
        code = str(exc) if isinstance(exc, ValueError) else ''
        errors.append(code if code.isascii() and code.replace('_', '').isalnum() and len(code) <= 96
                      else 'OFFLINE_CONTRACT_INVALID')
    diagnostics = budget_diagnostics(counts[DraftClaimType.OBSERVED_PRODUCT_FACT],
        counts[DraftClaimType.EVIDENCE_BASED_INTERPRETATION], counts[DraftClaimType.CALL_TO_ACTION])
    return OfflineCandidateCheck('DETERMINISTICALLY_REJECTED' if errors else 'PENDING_SEMANTIC_REVIEW',
        tuple(dict.fromkeys(errors)), claim_total, block_total, diagnostics,
        selection_valid, routing_valid, structure_valid)
