"""Isolated TEST-only slot domain. No generation, I/O or semantic authority."""
from dataclasses import asdict, dataclass, fields
import json
import re

from .content_draft import ContentDraftInput, MAX_CLAIMS_PER_BLOCK, MAX_PARAGRAPHS_PER_DRAFT
from .draft_selection_contract import (
    DraftSelectionContract, canonical_json, require, selection_digest, text_digest,
    valid_hash, valid_text, refs, validate_selection,
)

MANIFEST_VERSION = 'minimal-slot-manifest-1'
BINDING_VERSION = 'minimal-explanation-binding-1'
TEST_ORIGIN = 'TEST_ONLY_MANUALLY_AUTHORED'
MAX_WIRE_BYTES = 128 * 1024


@dataclass(frozen=True, slots=True)
class Slot:
    slot_id: str
    section_id: str
    kind: str
    reader_subquestion: str
    decision_goal: str
    allowed_fact_refs: tuple[str, ...]
    budget: int
    output_position: int
    # Only CTA may copy already available Plan text. Direct text comes from evidence.
    plan_text: str = ''
    # Explicit authored examples, never a universal semantic classifier.
    forbidden_statements: tuple[str, ...] = ()

    def __post_init__(self):
        require(type(self.slot_id) is str and re.fullmatch(r'S[1-9][0-9]?-[DEC][1-9][0-9]?', self.slot_id)
                and refs((self.section_id,), r'S[1-9][0-9]?')
                and self.slot_id.startswith(self.section_id + '-')
                and type(self.kind) is str and self.kind in {'direct_fact', 'explanation', 'cta'}, 'MW_SLOT_TYPE')
        require(self.slot_id.startswith(self.section_id + '-' +
                {'direct_fact': 'D', 'explanation': 'E', 'cta': 'C'}[self.kind]), 'MW_SLOT_KIND')
        require(all(valid_text(v, 300) for v in (self.reader_subquestion, self.decision_goal))
                and refs(self.allowed_fact_refs, r'E[1-9][0-9]{0,2}\.F[0-9]{2}', 20)
                and type(self.budget) is int and 1 <= self.budget <= (1200 if self.kind == 'explanation' else 300)
                and type(self.output_position) is int and 0 <= self.output_position < 48, 'MW_SLOT_FIELDS')
        require(type(self.plan_text) is str and
                (valid_text(self.plan_text, 300) if self.kind == 'cta' else self.plan_text == ''), 'MW_PLAN_TEXT')
        require((len(self.allowed_fact_refs) == 1 if self.kind == 'direct_fact' else
                 bool(self.allowed_fact_refs) if self.kind == 'explanation' else not self.allowed_fact_refs), 'MW_SLOT_REFS')
        require(type(self.forbidden_statements) is tuple and len(self.forbidden_statements) <= 16
                and all(valid_text(v, 300) for v in self.forbidden_statements), 'MW_CONFLICT_POLICY')


@dataclass(frozen=True, slots=True)
class SlotManifest:
    version: str
    origin: str
    author: str
    selection_sha256: str
    plan_sha256: str
    evidence_sha256: str
    snapshot_sha256: str
    slots: tuple[Slot, ...]

    def __post_init__(self):
        require(self.version == MANIFEST_VERSION and self.origin == TEST_ORIGIN
                and valid_text(self.author, 128) and self.author.startswith('SYNTHETIC-'), 'MW_TEST_PLAN_REQUIRED')
        require(all(valid_hash(v) for v in (self.selection_sha256, self.plan_sha256,
                self.evidence_sha256, self.snapshot_sha256)), 'MW_CONTEXT_HASH')
        require(type(self.slots) is tuple and 1 <= len(self.slots) <= 48
                and all(type(s) is Slot for s in self.slots)
                and len({s.slot_id for s in self.slots}) == len(self.slots), 'MW_SLOT_SET')


def manifest_digest(manifest: SlotManifest) -> str:
    require(type(manifest) is SlotManifest, 'MW_MANIFEST_TYPE')
    return text_digest(canonical_json(asdict(manifest)))


def request_id(manifest: SlotManifest) -> str:
    return 'MW-' + manifest_digest(manifest)


def validate_manifest(manifest: SlotManifest, value: ContentDraftInput,
                      selection: DraftSelectionContract, *, current_snapshot_sha256: str) -> None:
    validate_selection(selection, value, current_snapshot_sha256=current_snapshot_sha256)
    require(type(manifest) is SlotManifest, 'MW_MANIFEST_TYPE')
    require((manifest.selection_sha256, manifest.plan_sha256, manifest.evidence_sha256, manifest.snapshot_sha256)
            == (selection_digest(selection), selection.plan_sha256, selection.evidence_sha256,
                selection.evidence_snapshot_sha256), 'MW_CONTEXT_HASH')
    require({s.section_id for s in manifest.slots} == {s.section_id for s in selection.sections}, 'MW_SECTION_SET')
    expected_order, direct_seen, goals, questions = [], set(), set(), set()
    quotes = value.customer_evidence.quote_map()
    for section in selection.sections:
        slots = tuple(s for s in manifest.slots if s.section_id == section.section_id)
        require(tuple(s.output_position for s in slots) == tuple(range(len(slots))), 'MW_SLOT_POSITION')
        expected_order.extend(slots)
        direct = tuple(s.allowed_fact_refs[0] for s in slots if s.kind == 'direct_fact')
        explanations = tuple(s for s in slots if s.kind == 'explanation')
        ctas = tuple(s for s in slots if s.kind == 'cta')
        require(direct == section.required_direct_facts and not direct_seen.intersection(direct), 'MW_DIRECT_SET')
        direct_seen.update(direct)
        require(len(explanations) >= section.explanation_budget and len(direct) <= section.direct_fact_budget
                and len(ctas) <= section.cta_budget and len(slots) <= section.claim_budget, 'MW_SECTION_BUDGET')
        blocks = (len(slots) + MAX_CLAIMS_PER_BLOCK - 1) // MAX_CLAIMS_PER_BLOCK
        require(blocks <= section.block_budget and blocks <= MAX_PARAGRAPHS_PER_DRAFT, 'MW_BLOCK_BUDGET')
        require(set(r for s in slots for r in s.allowed_fact_refs) == set(section.selected_facts), 'MW_SELECTED_COVERAGE')
        for slot in slots:
            require(set(slot.allowed_fact_refs) <= set(section.selected_facts), 'MW_SECTION_REFS')
            if slot.kind == 'direct_fact':
                require(len(quotes[slot.allowed_fact_refs[0]]) <= slot.budget, 'MW_TEXT_BUDGET')
            elif slot.kind == 'cta':
                require(slot.plan_text == section.verification_action and len(slot.plan_text) <= slot.budget, 'MW_CTA_PLAN_BINDING')
            else:
                # Textual independence only. Meaning is explicitly a human-review risk.
                goal = ' '.join(slot.decision_goal.casefold().split())
                question = ' '.join(slot.reader_subquestion.casefold().split())
                require(goal not in goals and question not in questions, 'MW_DISTINCT_GOALS_REQUIRED')
                goals.add(goal); questions.add(question)
    require(tuple(expected_order) == manifest.slots and manifest.slots[-1].kind == 'cta'
            and sum(s.kind == 'cta' for s in manifest.slots) == 1, 'MW_OUTPUT_ORDER')
    # Section ceilings are already globally bounded by Selection v2.


def freeze_test_manifest(value: ContentDraftInput, selection: DraftSelectionContract,
                         slots: tuple[Slot, ...], *, author: str,
                         current_snapshot_sha256: str) -> SlotManifest:
    """Accept authored slots; never invent subquestions, goals or approval."""
    result = SlotManifest(MANIFEST_VERSION, TEST_ORIGIN, author, selection_digest(selection),
                          selection.plan_sha256, selection.evidence_sha256,
                          selection.evidence_snapshot_sha256, slots)
    validate_manifest(result, value, selection, current_snapshot_sha256=current_snapshot_sha256)
    return result


@dataclass(frozen=True, slots=True)
class SlotAnswer:
    slot_id: str
    status: str
    premise_refs: tuple[str, ...] = ()
    buyer_implication: str = ''
    assumptions: str = ''
    boundary_condition: str = ''
    verification_action: str = ''
    missing_information: str = ''

    def __post_init__(self):
        require(valid_text(self.slot_id, 32) and type(self.status) is str
                and self.status in {'answered', 'insufficient_evidence'}, 'MW_ANSWER_TYPE')
        require(refs(self.premise_refs, r'E[1-9][0-9]{0,2}\.F[0-9]{2}', 20), 'MW_PREMISE_REFS')
        semantics = (self.buyer_implication, self.assumptions, self.boundary_condition, self.verification_action)
        if self.status == 'answered':
            require(bool(self.premise_refs) and all(valid_text(v, 300) for v in semantics)
                    and len(self.boundary_condition) <= 150 and len(self.verification_action) <= 150
                    and self.missing_information == '', 'MW_ANSWER_FIELDS')
        else:
            require(not self.premise_refs and all(v == '' for v in semantics)
                    and valid_text(self.missing_information, 300), 'MW_REFUSAL_FIELDS')


@dataclass(frozen=True, slots=True)
class MinimalWire:
    request_id: str
    slots: tuple[SlotAnswer, ...]

    def __post_init__(self):
        require(type(self.request_id) is str and re.fullmatch(r'MW-[0-9a-f]{64}', self.request_id)
                and type(self.slots) is tuple and 1 <= len(self.slots) <= 48
                and all(type(s) is SlotAnswer for s in self.slots), 'MW_WIRE_FIELDS')


def answer_text(answer: SlotAnswer) -> str:
    """Join only supplied semantic text. Assumptions stay visible, without hidden copies."""
    return ' '.join((answer.buyer_implication, answer.assumptions,
                     answer.boundary_condition, answer.verification_action))


def validate_wire(wire: MinimalWire, manifest: SlotManifest,
                  selection: DraftSelectionContract) -> tuple[str, ...]:
    require(type(wire) is MinimalWire and wire.request_id == request_id(manifest), 'MW_REQUEST_BINDING')
    wanted = {s.slot_id: s for s in manifest.slots if s.kind == 'explanation'}
    ids = tuple(a.slot_id for a in wire.slots)
    require(len(set(ids)) == len(ids), 'MW_DUPLICATE_SLOT')
    require(set(ids) == set(wanted), 'MW_REQUIRED_SLOT_SET')
    sections = {s.section_id: s for s in selection.sections}
    refused = []
    for answer in wire.slots:
        slot = wanted[answer.slot_id]
        if answer.status == 'insufficient_evidence':
            refused.append(answer.slot_id)
            continue
        require(set(answer.premise_refs) <= set(slot.allowed_fact_refs), 'MW_PREMISE_OUTSIDE_SLOT')
        section = sections[slot.section_id]
        # No fallback appending of required sentences. Mismatches fail closed.
        require(answer.boundary_condition == section.required_limitation
                and answer.verification_action == section.verification_action, 'MW_PLAN_BOUNDARY_CONFLICT')
        text = answer_text(answer)
        require(len(text) <= slot.budget, 'MW_TEXT_BUDGET')
        normalized = ' '.join(text.casefold().split())
        require(not any(' '.join(v.casefold().split()) in normalized
                        for v in slot.forbidden_statements), 'MW_KNOWN_PLAN_CONFLICT')
    return tuple(refused)


@dataclass(frozen=True, slots=True)
class SourceQuote:
    fact_ref: str
    source_quote: str
    source_version: int
    content_sha256: str
    source_locator: str
    start: int
    end: int

    def __post_init__(self):
        require(refs((self.fact_ref,), r'E[1-9][0-9]{0,2}\.F[0-9]{2}')
                and valid_text(self.source_quote, 300) and valid_text(self.source_locator, 1000)
                and type(self.source_version) is int and 1 <= self.source_version <= 1000
                and valid_hash(self.content_sha256) and type(self.start) is int and type(self.end) is int
                and 0 <= self.start < self.end <= 16000, 'MW_SOURCE_BINDING')


@dataclass(frozen=True, slots=True)
class SlotBinding:
    slot_id: str
    section_id: str
    kind: str
    claim_id: str
    text: str
    text_sha256: str
    evidence: tuple[SourceQuote, ...]

    def __post_init__(self):
        require(valid_text(self.slot_id, 32) and refs((self.section_id,), r'S[1-9][0-9]?')
                and type(self.kind) is str and self.kind in {'direct_fact', 'explanation', 'cta'}
                and refs((self.claim_id,), r'CL[1-9][0-9]?') and valid_text(self.text, 1200)
                and valid_hash(self.text_sha256) and text_digest(self.text) == self.text_sha256
                and type(self.evidence) is tuple and len(self.evidence) <= 20
                and all(type(e) is SourceQuote for e in self.evidence), 'MW_BINDING_FIELDS')


@dataclass(frozen=True, slots=True)
class ExplanationBindings:
    version: str
    request_id: str
    manifest_sha256: str
    selection_sha256: str
    plan_sha256: str
    evidence_sha256: str
    snapshot_sha256: str
    wire_sha256: str
    candidate_hash: str
    bindings: tuple[SlotBinding, ...]

    def __post_init__(self):
        require(self.version == BINDING_VERSION and type(self.request_id) is str
                and re.fullmatch(r'MW-[0-9a-f]{64}', self.request_id)
                and all(valid_hash(v) for v in (self.manifest_sha256, self.selection_sha256,
                    self.plan_sha256, self.evidence_sha256, self.snapshot_sha256,
                    self.wire_sha256, self.candidate_hash)), 'MW_BINDING_CONTEXT')
        require(type(self.bindings) is tuple and 1 <= len(self.bindings) <= 48
                and all(type(b) is SlotBinding for b in self.bindings)
                and len({b.slot_id for b in self.bindings}) == len(self.bindings)
                and tuple(b.claim_id for b in self.bindings) == tuple(f'CL{i}' for i in range(1, len(self.bindings)+1)),
                'MW_SLOT_CLAIM_MAPPING')


def _object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'MW_DUPLICATE_JSON_KEY')
        result[key] = value
    return result


def strict_json(raw: str, maximum: int = MAX_WIRE_BYTES):
    require(type(raw) is str and len(raw) <= maximum
            and len(raw.encode('utf-8')) <= maximum, 'MW_RAW_BUDGET')
    try:
        return json.loads(raw, object_pairs_hook=_object,
                          parse_constant=lambda _: require(False, 'MW_JSON_CONSTANT'))
    except (json.JSONDecodeError, RecursionError):
        raise ValueError('MW_JSON_FORMAT') from None


def _keys(obj, keys):
    require(type(obj) is dict and set(obj) == set(keys), 'MW_EXACT_FIELDS')


def _list(value, maximum):
    require(type(value) is list and len(value) <= maximum, 'MW_ARRAY_TYPE')
    return value


ANSWER_FIELDS = {'slot_id', 'status', 'premise_refs', 'buyer_implication',
                 'assumptions', 'boundary_condition', 'verification_action'}
REFUSAL_FIELDS = {'slot_id', 'status', 'missing_information'}


def decode_wire(raw: str) -> MinimalWire:
    obj = strict_json(raw)
    _keys(obj, {'request_id', 'slots'})
    answers = []
    for item in _list(obj['slots'], 48):
        require(type(item) is dict, 'MW_ANSWER_TYPE')
        if item.get('status') == 'insufficient_evidence':
            _keys(item, REFUSAL_FIELDS)
            answers.append(SlotAnswer(**item))
        else:
            _keys(item, ANSWER_FIELDS)
            data = dict(item)
            data['premise_refs'] = tuple(_list(data['premise_refs'], 20))
            answers.append(SlotAnswer(**data))
    return MinimalWire(obj['request_id'], tuple(answers))


def encode_wire(wire: MinimalWire) -> str:
    require(type(wire) is MinimalWire, 'MW_WIRE_FIELDS')
    slots = []
    for answer in wire.slots:
        data = asdict(answer)
        keys = REFUSAL_FIELDS if answer.status == 'insufficient_evidence' else ANSWER_FIELDS
        slots.append({key: data[key] for key in keys})
    return canonical_json(dict(request_id=wire.request_id, slots=slots))


def encode_bindings(sidecar: ExplanationBindings) -> str:
    require(type(sidecar) is ExplanationBindings, 'MW_BINDING_FIELDS')
    return canonical_json(asdict(sidecar))


def decode_bindings(raw: str) -> ExplanationBindings:
    """Independent strict codec; never decodes or impersonates v3 sidecars."""
    obj = strict_json(raw, 256 * 1024)
    _keys(obj, {f.name for f in fields(ExplanationBindings)})
    bindings = []
    for item in _list(obj['bindings'], 48):
        _keys(item, {f.name for f in fields(SlotBinding)})
        data = dict(item)
        quotes = []
        for quote in _list(data['evidence'], 20):
            _keys(quote, {f.name for f in fields(SourceQuote)})
            quotes.append(SourceQuote(**quote))
        data['evidence'] = tuple(quotes)
        bindings.append(SlotBinding(**data))
    return ExplanationBindings(**{**obj, 'bindings': tuple(bindings)})


def encode_manifest(manifest: SlotManifest) -> str:
    require(type(manifest) is SlotManifest, 'MW_MANIFEST_TYPE')
    return canonical_json(asdict(manifest))


def decode_manifest(raw: str) -> SlotManifest:
    obj = strict_json(raw)
    _keys(obj, {f.name for f in fields(SlotManifest)})
    slots = []
    for item in _list(obj['slots'], 48):
        _keys(item, {f.name for f in fields(Slot)})
        data = dict(item)
        data['allowed_fact_refs'] = tuple(_list(data['allowed_fact_refs'], 20))
        data['forbidden_statements'] = tuple(_list(data['forbidden_statements'], 16))
        slots.append(Slot(**data))
    return SlotManifest(**{**obj, 'slots': tuple(slots)})


