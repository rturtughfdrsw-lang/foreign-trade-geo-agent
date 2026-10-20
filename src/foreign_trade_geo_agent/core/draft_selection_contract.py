"""Provider-independent, offline-only V2 writing selection. Never execution authority.

The complete evidence stays on the planning/validation side. Hashes detect stale
inputs, not human approval. V1 models, payloads and admission rules are untouched.
"""
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
import hashlib
import json
import re

from .content_draft import ContentDraftInput, stable_content_draft_input_error, MAX_CLAIMS_PER_BLOCK, MAX_BULLET_ITEMS
from .draft_customer_evidence import DraftCustomerEvidence

CONTRACT_VERSION = 'seo-draft-selection-v2'
CLAIM_HARD_MAX = 48
BLOCK_HARD_MAX = 24


def require(condition: bool, code: str) -> None:
    if not condition:
        raise ValueError(code)


def valid_text(value: object, maximum: int = 1200) -> bool:
    return (type(value) is str and bool(value.strip()) and len(value) <= maximum
            and not any(ord(c) < 32 and c not in '\n\r\t' for c in value))


def valid_hash(value: object) -> bool:
    return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def refs(value: object, pattern: str, maximum: int = 64) -> bool:
    return (type(value) is tuple and len(value) <= maximum
            and all(type(v) is str and re.fullmatch(pattern, v) for v in value)
            and len(set(value)) == len(value))


def _json_default(value):
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError('CONTRACT_JSON_TYPE')


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(',', ':'), default=_json_default)


def text_digest(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def plan_digest(value: ContentDraftInput) -> str:
    """Bind the complete Plan and its P/S context and writing requirements."""
    require(type(value) is ContentDraftInput, 'SELECTION_INPUT')
    return text_digest(canonical_json([asdict(value.site_content), asdict(value.opportunity_report),
        asdict(value.change_plan_report), asdict(value.writing_brief) if value.writing_brief else None,
        value.target_language, value.propose_interpretations]))


def evidence_digest(bundle: DraftCustomerEvidence) -> str:
    require(type(bundle) is DraftCustomerEvidence, 'SELECTION_EVIDENCE')
    return text_digest(canonical_json(asdict(bundle)))


@dataclass(frozen=True, slots=True)
class FactSelectionReason:
    fact_ref: str
    priority: str
    reason: str
    selected_sections: tuple[str, ...]

    def __post_init__(self):
        require(refs((self.fact_ref,), r'E[1-9][0-9]{0,2}\.F[0-9]{2}')
            and type(self.priority) is str and self.priority in {'P0', 'P1', 'P2'}
            and valid_text(self.reason, 1000) and refs(self.selected_sections, r'S[1-9][0-9]?', 24),
            'SELECTION_AUDIT_INVALID')


@dataclass(frozen=True, slots=True)
class SectionEvidenceBudget:
    section_id: str
    heading: str
    question: str
    requirement_ids: tuple[str, ...]
    required_sources: tuple[str, ...]
    required_facts: tuple[str, ...]
    optional_facts: tuple[str, ...]
    selected_facts: tuple[str, ...]
    required_direct_facts: tuple[str, ...]
    claim_budget: int
    block_budget: int
    explanation_budget: int
    direct_fact_budget: int
    cta_budget: int
    required_limitation: str
    verification_action: str

    def __post_init__(self):
        require(refs((self.section_id,), r'S[1-9][0-9]?')
            and all(valid_text(v) for v in (self.heading, self.question, self.required_limitation, self.verification_action))
            and refs(self.requirement_ids, r'[^\s]{1,128}', 32) and bool(self.requirement_ids)
            and refs(self.required_sources, r'E[1-9][0-9]{0,2}', 8) and bool(self.required_sources),
            'SELECTION_SECTION_INVALID')
        require(all(refs(v, r'E[1-9][0-9]{0,2}\.F[0-9]{2}') for v in
            (self.required_facts, self.optional_facts, self.selected_facts, self.required_direct_facts)),
            'SELECTION_FACT_LIST_INVALID')
        required, optional, selected = map(set, (self.required_facts, self.optional_facts, self.selected_facts))
        require(bool(selected) and not required & optional and required <= selected <= required | optional
            and set(self.required_direct_facts) <= selected, 'SELECTION_SET_INVALID')
        require(type(self.claim_budget) is int and 1 <= self.claim_budget <= CLAIM_HARD_MAX, 'CLAIM_BUDGET')
        require(type(self.block_budget) is int and 1 <= self.block_budget <= BLOCK_HARD_MAX, 'BLOCK_BUDGET')
        require(all(type(v) is int and 0 <= v <= CLAIM_HARD_MAX for v in
            (self.explanation_budget, self.direct_fact_budget, self.cta_budget)), 'SELECTION_BUDGET_INVALID')
        require(len(self.required_direct_facts) <= self.direct_fact_budget
            and self.direct_fact_budget + self.explanation_budget + self.cta_budget <= self.claim_budget,
            'SELECTION_RESERVATION_INFEASIBLE')
        require(len(self.required_direct_facts) + self.explanation_budget + self.cta_budget <=
                self.block_budget * max(MAX_CLAIMS_PER_BLOCK, MAX_BULLET_ITEMS), 'SELECTION_RESERVATION_INFEASIBLE')


@dataclass(frozen=True, slots=True)
class DraftSelectionContract:
    contract_version: str
    evidence_snapshot_sha256: str
    evidence_sha256: str
    plan_sha256: str
    sections: tuple[SectionEvidenceBudget, ...]
    fact_reasons: tuple[FactSelectionReason, ...]

    def __post_init__(self):
        require(self.contract_version == CONTRACT_VERSION and type(self.contract_version) is str,
                'SELECTION_VERSION')
        require(all(valid_hash(v) for v in (self.evidence_snapshot_sha256, self.evidence_sha256, self.plan_sha256)),
                'SELECTION_HASH_INVALID')
        require(type(self.sections) is tuple and 1 <= len(self.sections) <= 24
            and all(type(s) is SectionEvidenceBudget for s in self.sections)
            and len({s.section_id for s in self.sections}) == len(self.sections), 'SELECTION_SECTIONS_INVALID')
        require(type(self.fact_reasons) is tuple and 1 <= len(self.fact_reasons) <= 64
            and all(type(r) is FactSelectionReason for r in self.fact_reasons)
            and len({r.fact_ref for r in self.fact_reasons}) == len(self.fact_reasons), 'SELECTION_AUDIT_INVALID')
        require(sum(s.claim_budget for s in self.sections) <= CLAIM_HARD_MAX, 'CLAIM_BUDGET')
        require(sum(s.block_budget for s in self.sections) <= BLOCK_HARD_MAX, 'BLOCK_BUDGET')


def selection_digest(contract: DraftSelectionContract) -> str:
    require(type(contract) is DraftSelectionContract, 'SELECTION_CONTRACT_INVALID')
    return text_digest(canonical_json(asdict(contract)))


def budget_diagnostics(direct_facts: int, explanations: int, cta: int) -> tuple[str, ...]:
    require(all(type(n) is int and n >= 0 for n in (direct_facts, explanations, cta)), 'BUDGET_COUNTS_INVALID')
    return tuple(code for flag, code in (
        (direct_facts > 30, 'SOFT_DIRECT_FACTS_OVER_30'),
        (explanations < 12, 'SOFT_EXPLANATIONS_UNDER_12'),
        (cta != 1, 'SOFT_CTA_NOT_ONE')) if flag)


def validate_selection(contract: DraftSelectionContract, value: ContentDraftInput, *,
                       current_snapshot_sha256: str) -> tuple[str, ...]:
    """Fail closed before projection. Return soft budget diagnostics only."""
    require(type(contract) is DraftSelectionContract and type(value) is ContentDraftInput, 'SELECTION_INPUT')
    require(value.customer_evidence is not None and value.writing_brief is not None, 'SELECTION_INPUT')
    bundle = value.customer_evidence
    require(valid_hash(current_snapshot_sha256) and contract.evidence_snapshot_sha256 ==
        current_snapshot_sha256 == bundle.snapshot_sha256 == value.writing_brief.snapshot_sha256, 'SELECTION_SNAPSHOT')
    require(contract.plan_sha256 == plan_digest(value), 'SELECTION_PLAN_HASH')
    require(contract.evidence_sha256 == evidence_digest(bundle), 'SELECTION_EVIDENCE_HASH')
    require(stable_content_draft_input_error(value) is None, 'SELECTION_NATIVE_INPUT')
    require(len(value.change_plan_report.operations) == 1, 'SELECTION_PLAN_SCOPE')
    resource = value.change_plan_report.operations[0].new_resource_spec
    require(resource is not None and len(resource.section_briefs) == len(contract.sections), 'SELECTION_SECTION_BINDING')
    require(all(source.facts for source in bundle.sources), 'SELECTION_STRUCTURED_FACTS_REQUIRED')
    facts = {f.fact_ref: (source, f) for source in bundle.sources for f in source.facts}
    direct_seen: set[str] = set()
    for i, (section, brief) in enumerate(zip(contract.sections, resource.section_briefs), 1):
        require(section.section_id == f'S{i}' and section.heading == brief.heading
            and section.question == brief.reader_question
            and set(section.requirement_ids) == set(brief.requirement_ids)
            and set(section.required_sources) == set(brief.supporting_evidence)
            and section.required_limitation == brief.limitations
            and section.verification_action == brief.procurement_action, 'SELECTION_SECTION_BINDING')
        requirements = set(section.requirement_ids)
        for ref in section.required_facts + section.optional_facts:
            require(ref in facts and facts[ref][0].evidence_id in section.required_sources
                and bool(set(facts[ref][1].requirement_ids) & requirements), 'SELECTION_FACT_ROUTING')
        selected_sources = {facts[r][0].evidence_id for r in section.selected_facts}
        covered = {q for r in section.selected_facts for q in facts[r][1].requirement_ids}
        require(selected_sources == set(section.required_sources) and requirements <= covered, 'SELECTION_COVERAGE')
        require(not direct_seen.intersection(section.required_direct_facts), 'SELECTION_DIRECT_DUPLICATE')
        direct_seen.update(section.required_direct_facts)
    require({r.fact_ref for r in contract.fact_reasons} == set(facts), 'SELECTION_AUDIT_COVERAGE')
    for reason in contract.fact_reasons:
        expected = {s.section_id for s in contract.sections if reason.fact_ref in s.selected_facts}
        require(set(reason.selected_sections) == expected, 'SELECTION_AUDIT_ASSIGNMENT')
    return budget_diagnostics(sum(s.direct_fact_budget for s in contract.sections),
        sum(s.explanation_budget for s in contract.sections), sum(s.cta_budget for s in contract.sections))
