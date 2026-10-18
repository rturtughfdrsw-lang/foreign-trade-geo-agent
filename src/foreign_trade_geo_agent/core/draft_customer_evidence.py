"""Bounded customer facts and reviewed interpretations; never execution authority.

The only admitted review profile in this release is explicitly TEST-only.
Exact fact and inference preservation is a structural constraint, not semantic proof.
Current intake state and reviewer availability must be checked by composition
both before and after generation. Persisted bindings are historical snapshots.
"""
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
import hashlib
import json
import re


# Prose capacity is independent of the exact source fact quote budget (300).
MAX_INTERPRETATION_CHARS = 1200
MAX_INTERPRETATIONS = 48


def _require(condition):
    if not condition:
        raise ValueError("CUSTOMER_EVIDENCE_INVALID")


def _text(value, maximum=1000):
    return (type(value) is str and bool(value.strip()) and len(value) <= maximum
            and not any(ord(c) < 32 and c not in "\n\r\t" for c in value))


def _digest(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def native_scope_digest(site_content, opportunity_report, operation):
    """Bind the complete native P/S/operation graph, without importing Draft."""
    op = asdict(operation)
    if op.get('new_resource_spec') is not None and not op['new_resource_spec'].get('section_briefs'):
        op['new_resource_spec'].pop('section_briefs', None)
    raw = json.dumps([asdict(site_content), asdict(opportunity_report), op],
        default=lambda v: v.value if isinstance(v, Enum) else v.astimezone(UTC).isoformat(),
        ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class DraftCustomerFact:
    fact_ref: str
    start: int
    end: int
    quote: str
    requirement_ids: tuple[str, ...] = ()

    def __post_init__(self):
        _require(type(self.fact_ref) is str and re.fullmatch(r'E[1-9][0-9]{0,2}\.F[0-9]{2}', self.fact_ref) is not None
                 and type(self.start) is int and type(self.end) is int and 0 <= self.start < self.end <= 16000
                 and _text(self.quote, 300))
        _require(type(self.requirement_ids) is tuple and len(self.requirement_ids) <= 32
                 and len(set(self.requirement_ids)) == len(self.requirement_ids)
                 and all(_text(r, 128) for r in self.requirement_ids))


@dataclass(frozen=True, slots=True)
class InterpretationProposal:
    """Untrusted reasoning metadata. No review or authority fields accepted."""
    procurement_question: str
    reasoning: str
    assumptions: str
    limitation: str
    procurement_action: str

    def __post_init__(self):
        _require(all(_text(v, 300) for v in (self.procurement_question, self.reasoning, self.assumptions))
            and _text(self.limitation, 150) and _text(self.procurement_action, 150))


@dataclass(frozen=True, slots=True)
class DraftInterpretation:
    """Reviewer-approved inference, not a provider self-certification.

    The writer may select/combine these with direct facts. Arbitrary inference
    needs a new review. Exact text and premise binding make this fail closed.
    """
    text: str
    fact_refs: tuple[str, ...]
    limitation: str
    procurement_action: str
    proposal: InterpretationProposal | None = None

    def __post_init__(self):
        _require(self.proposal is None or (type(self.proposal) is InterpretationProposal
            and self.limitation == self.proposal.limitation
            and self.procurement_action == self.proposal.procurement_action))
        _require(_text(self.text, MAX_INTERPRETATION_CHARS) and type(self.fact_refs) is tuple
                 and 1 <= len(self.fact_refs) <= 20 and len(set(self.fact_refs)) == len(self.fact_refs)
                 and all(_text(r, 32) for r in self.fact_refs)
                 and _text(self.limitation, 150) and self.limitation in self.text
                 and _text(self.procurement_action, 150) and self.procurement_action in self.text)


@dataclass(frozen=True, slots=True)
class DraftCustomerSource:
    evidence_id: str
    evidence_version: int
    requirement_ids: tuple[str, ...]
    source_label: str
    source_locator: str
    content: str
    content_sha256: str
    span_start: int
    span_end: int
    quote: str
    facts: tuple[DraftCustomerFact, ...] = ()

    def __post_init__(self):
        _require(type(self.facts) is tuple and len(self.facts) <= 64
                 and len({f.fact_ref for f in self.facts}) == len(self.facts)
                 and all(type(f) is DraftCustomerFact and f.fact_ref.startswith(self.evidence_id + '.')
                         and set(f.requirement_ids) <= set(self.requirement_ids)
                         and f.end <= len(self.content) and self.content[f.start:f.end] == f.quote for f in self.facts))
        _require(type(self.evidence_id) is str and re.fullmatch(r"E[1-9][0-9]{0,2}", self.evidence_id) is not None
            and type(self.evidence_version) is int and 1 <= self.evidence_version <= 1000
            and type(self.requirement_ids) is tuple and 1 <= len(self.requirement_ids) <= 32
            and len(set(self.requirement_ids)) == len(self.requirement_ids)
            and all(_text(r, 128) for r in self.requirement_ids)
            and _text(self.source_label) and _text(self.source_locator)
            and _text(self.content, 16000) and _digest(self.content_sha256)
            and hashlib.sha256(self.content.encode("utf-8")).hexdigest() == self.content_sha256
            and type(self.span_start) is int and type(self.span_end) is int
            and 0 <= self.span_start < self.span_end <= len(self.content)
            and _text(self.quote, 300) and self.content[self.span_start:self.span_end] == self.quote)


@dataclass(frozen=True, slots=True)
class DraftCustomerEvidence:
    project_id: str
    customer_id: str
    task_id: str
    task_version: int
    plan_version: int
    evidence_version: int
    snapshot_revision: int
    snapshot_sha256: str
    native_scope_sha256: str
    change_ref: str
    reviewer_id: str
    reviewed_at: datetime
    review_status: str
    sources: tuple[DraftCustomerSource, ...]
    interpretations: tuple[DraftInterpretation, ...] = ()

    def __post_init__(self):
        _require(all(_text(v, 128) for v in (self.project_id, self.customer_id, self.task_id, self.reviewer_id))
            and all(type(v) is int and 1 <= v <= 1000 for v in
                (self.task_version, self.plan_version, self.evidence_version, self.snapshot_revision))
            and _digest(self.snapshot_sha256) and _digest(self.native_scope_sha256)
            and self.change_ref == "C1"
            and isinstance(self.reviewed_at, datetime) and self.reviewed_at.utcoffset() is not None
            and self.review_status == "TEST_ONLY_SUPPORTED_NOT_HUMAN_SIGNOFF"
            and self.reviewer_id.startswith("SYNTHETIC-")
            and type(self.sources) is tuple and 1 <= len(self.sources) <= 8
            and all(type(s) is DraftCustomerSource and s.evidence_version <= self.evidence_version for s in self.sources)
            and len({s.evidence_id for s in self.sources}) == len(self.sources)
            and sum(len(s.content) for s in self.sources) <= 16000)
        _require(sum(len(s.facts) for s in self.sources) <= 64
                 and type(self.interpretations) is tuple and len(self.interpretations) <= MAX_INTERPRETATIONS
                 and len({i.text for i in self.interpretations}) == len(self.interpretations)
                 and all(type(i) is DraftInterpretation and set(i.fact_refs) <= set(self.quote_map())
                         for i in self.interpretations))

    def quote_map(self):
        return {ref: quote for s in self.sources for ref, quote in
                ([(f.fact_ref, f.quote) for f in s.facts] if s.facts else [(s.evidence_id, s.quote)])}

    def reference_selection_valid(self, refs):
        """A structured fact bank is optional; Plan still owns question coverage.

        Legacy or mixed quote-only input keeps its existing complete coverage.
        This does not validate claim meaning, quotes, or section assignments.
        """
        used, available = set(refs), set(self.quote_map())
        return bool(used) and used <= available and (
            all(s.facts for s in self.sources) or used == available)

    def claim_error(self, text, kind, refs, page_refs=(), source_refs=(), proposal=None):
        """Shared by Validator and persisted DraftItem reconstruction."""
        if page_refs or source_refs:
            return 'CUSTOMER_QUOTE_MISMATCH'
        if kind == 'EVIDENCE_BASED_INTERPRETATION':
            return None if any(text == i.text and refs == i.fact_refs and proposal == i.proposal for i in self.interpretations) else 'CUSTOMER_QUOTE_MISMATCH'
        return None if (kind == 'OBSERVED_PRODUCT_FACT' and len(refs) == 1
                        and text == self.quote_map().get(refs[0])) else 'CUSTOMER_QUOTE_MISMATCH'

    def fresh_at(self, now):
        return (isinstance(now, datetime) and now.utcoffset() is not None
                and self.reviewed_at <= now <= self.reviewed_at + timedelta(minutes=5))

    def matches_native(self, site_content, opportunity_report, operation):
        return (operation.change_id == self.change_ref
                and operation.operation_type.value == "CREATE_NEW_RESOURCE"
                and self.native_scope_sha256 == native_scope_digest(site_content, opportunity_report, operation))
