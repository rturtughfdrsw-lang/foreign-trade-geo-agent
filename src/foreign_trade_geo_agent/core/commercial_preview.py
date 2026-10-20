"""Versioned local Preview contracts. These never confer production authority."""
from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Protocol

from .evidence_intake import Supplement, SupplementMethod, text, version
from .history import validate_uuid

PROFILE = 'COMMERCIAL_PREVIEW'
REVIEW = 'LOCAL_PREVIEW_REVIEW'


def require(ok, message='PREVIEW_INVALID'):
    if not ok:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def sha(text_value):
    return hashlib.sha256(text_value.encode('utf-8')).hexdigest()


def hash_ok(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


@dataclass(frozen=True)
class PreviewTask:
    run_id: str
    task_id: str
    version: int
    website: str
    title: str
    reader_question: str
    required_facts: tuple[str, ...]
    scope: str
    limitations: str
    schema_version: int = 1

    def __post_init__(self):
        validate_uuid(self.run_id, 'run_id')
        validate_uuid(self.task_id, 'task_id')
        require(type(self.schema_version) is int and self.schema_version == 1 and version(self.version))
        require(all(text(v, 1000) for v in (self.website, self.title, self.reader_question,
                                           self.scope, self.limitations)))
        require(type(self.required_facts) is tuple and 1 <= len(self.required_facts) <= 16
                and all(text(v, 1000) for v in self.required_facts)
                and len(set(self.required_facts)) == len(self.required_facts))

    @property
    def obligations(self):
        return dict([('reader-question', self.reader_question),
                     *[(f'fact-{i}', fact) for i, fact in enumerate(self.required_facts, 1)],
                     ('scope', self.scope), ('limitations', self.limitations)])


@dataclass(frozen=True)
class EvidenceSource:
    run_id: str
    task_id: str
    task_version: int
    source_id: str
    label: str
    locator: str
    content: str
    content_sha256: str
    scope: str
    data_kind: str
    schema_version: int = 1
    source_type: str = 'LOCAL_DOCUMENT'
    page_digest: str | None = None

    def __post_init__(self):
        for name in ('run_id', 'task_id', 'source_id'):
            validate_uuid(getattr(self, name), name)
        require(type(self.schema_version) is int and self.schema_version == 1 and version(self.task_version)
                and self.data_kind in {'SYNTHETIC', 'REAL'} and text(self.scope, 1000))
        # Reuse lossless text intake and its file digest validation; upload != support.
        Supplement(self.source_id, ('preview',), SupplementMethod.TEXT_DOCUMENT,
                   self.content, self.label, self.locator, 'LOCAL_PREVIEW', self.content_sha256)
        require(self.source_type in {'LOCAL_DOCUMENT', 'WEBSITE_SAMPLE'})
        require(self.page_digest is None or hash_ok(self.page_digest))
        require(self.source_type != 'WEBSITE_SAMPLE' or hash_ok(self.page_digest))


@dataclass(frozen=True)
class EvidenceSpan:
    span_id: str
    source_id: str
    obligation_id: str
    start: int
    end: int
    quote: str
    source_sha256: str
    schema_version: int = 1

    def validate(self, source, task):
        validate_uuid(self.span_id, 'span_id')
        require(type(self.schema_version) is int and self.schema_version == 1 and self.source_id == source.source_id
                and self.obligation_id in task.obligations
                and self.source_sha256 == source.content_sha256
                and type(self.start) is int and type(self.end) is int
                and 0 <= self.start < self.end <= len(source.content)
                and text(self.quote, 16000) and source.content[self.start:self.end] == self.quote,
                'PREVIEW_SPAN_INVALID')


@dataclass(frozen=True)
class SupportReview:
    run_id: str
    task_id: str
    task_version: int
    evidence_digest: str
    obligation_id: str
    span_ids: tuple[str, ...]
    verdict: str
    note: str
    review_kind: str = REVIEW
    schema_version: int = 1

    def __post_init__(self):
        validate_uuid(self.run_id, 'run_id')
        validate_uuid(self.task_id, 'task_id')
        require(type(self.schema_version) is int and self.schema_version == 1 and version(self.task_version)
                and self.review_kind == REVIEW and hash_ok(self.evidence_digest)
                and self.verdict in {'SUPPORTED', 'CONFLICT', 'UNRESOLVED'} and text(self.note, 1000)
                and type(self.span_ids) is tuple and 1 <= len(self.span_ids) <= 32
                and len(set(self.span_ids)) == len(self.span_ids))
        for value in self.span_ids:
            validate_uuid(value, 'span_id')


@dataclass(frozen=True)
class ExecutionConfirmation:
    confirmation_id: str
    run_id: str
    task_id: str
    task_version: int
    evidence_digest: str
    request_digest: str
    schema_version: int = 1

    def __post_init__(self):
        for name in ('confirmation_id', 'run_id', 'task_id'):
            validate_uuid(getattr(self, name), name)
        require(type(self.schema_version) is int and self.schema_version == 1 and version(self.task_version)
                and hash_ok(self.evidence_digest) and hash_ok(self.request_digest))


def task_from(value):
    require(type(value) is dict, 'PREVIEW_TASK_CONFIRMATION_REQUIRED')
    return PreviewTask(**dict(value, required_facts=tuple(value['required_facts'])))


def evidence_digest(state):
    return digest({'task': state['task'], 'sources': state['sources'], 'spans': state['spans']})


def material(state):
    value = {key: state[key] for key in ('task', 'sources', 'spans', 'reviews')}
    # Preserve V1 request digests for already saved runs.
    if 'execution_policy' in state:
        value.update(profile=PROFILE, execution_policy=state['execution_policy'],
                     task_digest=digest(state['task']), evidence_digest=evidence_digest(state))
    return value


def request_digest(state):
    return digest({'profile': PROFILE, 'schema_version': 1, 'material': material(state)})


def check_evidence(state):
    require(state.get('production_authorized') is False, 'PREVIEW_PRODUCTION_AUTHORITY_FORBIDDEN')
    task = task_from(state['task'])
    require(len(state['sources']) <= 32 and len(state['spans']) <= 64)
    sources = [EvidenceSource(**s) for s in state['sources']]
    require(len({s.source_id for s in sources}) == len(sources))
    by_id = {s.source_id: s for s in sources}
    for source in sources:
        require((source.run_id, source.task_id, source.task_version, source.scope) ==
                (task.run_id, task.task_id, task.version, task.scope), 'PREVIEW_SOURCE_BINDING')
    spans = [EvidenceSpan(**s) for s in state['spans']]
    require(len({s.span_id for s in spans}) == len(spans))
    for span in spans:
        require(span.source_id in by_id, 'PREVIEW_SOURCE_MISSING')
        span.validate(by_id[span.source_id], task)
    missing = [f'{key}: 请补充精确资料以回答/证明：{value}' for key, value in task.obligations.items()
               if not any(s.obligation_id == key for s in spans)]
    return task, spans, missing


def readiness(state):
    task, spans, missing = check_evidence(state)
    current = evidence_digest(state)
    reviews = {}
    for value in state['reviews']:
        review = SupportReview(**dict(value, span_ids=tuple(value['span_ids'])))
        require((review.run_id, review.task_id, review.task_version, review.evidence_digest) ==
                (task.run_id, task.task_id, task.version, current), 'PREVIEW_REVIEW_BINDING')
        require(review.obligation_id in task.obligations and review.obligation_id not in reviews)
        allowed = {s.span_id for s in spans if s.obligation_id == review.obligation_id}
        require(set(review.span_ids) == allowed, 'PREVIEW_REVIEW_SPAN_BINDING')
        reviews[review.obligation_id] = review
    missing += [f'{key}: LOCAL_PREVIEW_REVIEW 人工核对未完成或有冲突：{value}'
                for key, value in task.obligations.items()
                if key not in reviews or reviews[key].verdict != 'SUPPORTED']
    return missing


def admit(state, confirmation):
    require(not readiness(state), 'PREVIEW_EVIDENCE_OR_REVIEW_REQUIRED')
    task = task_from(state['task'])
    require(type(confirmation) is ExecutionConfirmation, 'PREVIEW_CONFIRMATION_REQUIRED')
    require((confirmation.run_id, confirmation.task_id, confirmation.task_version,
             confirmation.evidence_digest, confirmation.request_digest) ==
            (task.run_id, task.task_id, task.version, evidence_digest(state), request_digest(state)),
            'PREVIEW_CONFIRMATION_BINDING')
    require(state['confirmation'] == asdict(confirmation), 'PREVIEW_CONFIRMATION_REQUIRED')


@dataclass(frozen=True)
class PreviewGeneration:
    raw: str | None
    metadata: dict
    failure: str | None = None
    technical: str = 'FAILED'


class PreviewWriter(Protocol):
    timeout_seconds: float
    def policy(self) -> dict: ...
    def preparation(self) -> dict: ...
    async def generate(self, request: dict) -> str | PreviewGeneration: ...


class PreviewStore(Protocol):
    def create(self, state: dict) -> None: ...
    def read(self, run_id: str) -> dict: ...
    def save(self, state: dict, expected_revision: int) -> dict: ...
    def reserve(self, state: dict, confirmation: ExecutionConfirmation) -> dict: ...
    def finish(self, attempt_id: str, result: dict) -> dict: ...
    def attempt(self, run_id: str) -> dict | None: ...


class PreviewAnalyzer(Protocol):
    async def analyze(self, website: str, run_id: str, **options) -> dict: ...


def parse_article(raw, state):
    """Strict bounded wire format; approval and source namespaces are program owned."""
    from .preview_claim_audit import Claim, Scope, audit
    from .content_draft import extract_numeric_expressions

    require(type(raw) is str and len(raw.encode('utf-8')) <= 65536, 'PREVIEW_OUTPUT_BUDGET')

    def pairs(items):
        value = {}
        for key, item in items:
            require(key not in value, 'PREVIEW_OUTPUT_DUPLICATE_KEY')
            value[key] = item
        return value

    try:
        article = json.loads(raw, object_pairs_hook=pairs,
                             parse_constant=lambda _: require(False, 'PREVIEW_OUTPUT_JSON'))
    except (json.JSONDecodeError, RecursionError):
        raise ValueError('PREVIEW_OUTPUT_JSON') from None
    task = task_from(state['task'])
    require(type(article) is dict and set(article) == {'schema_version', 'title', 'paragraphs'}
            and type(article['schema_version']) is int and article['schema_version'] == 1
            and article['title'] == task.title, 'PREVIEW_OUTPUT_CONTRACT')
    paragraphs = article['paragraphs']
    require(type(paragraphs) is list and 1 <= len(paragraphs) <= 32, 'PREVIEW_OUTPUT_CONTRACT')
    sources = {s['source_id']: s for s in state['sources']}
    spans = {s['span_id']: s for s in state['spans']}
    reviewed = {r['obligation_id']: [spans[i] for i in r['span_ids']] for r in state['reviews']}
    findings, covered = [], set()
    all_numbers = {n for s in state['spans'] for n in extract_numeric_expressions(s['quote'])}
    if set(extract_numeric_expressions(article['title'])) - all_numbers:
        findings.append(dict(code='TITLE_NUMERIC_NOT_GROUNDED', status='REJECTED'))
    for index, paragraph in enumerate(paragraphs):
        require(type(paragraph) is dict and set(paragraph) == {'heading', 'text', 'source_ids', 'obligation_ids'}
                and text(paragraph['heading'], 160) and text(paragraph['text'], 6000), 'PREVIEW_OUTPUT_CONTRACT')
        require(not re.search('[\u3400-\u9fff]', paragraph['text'] + paragraph['heading']), 'PREVIEW_ENGLISH_REQUIRED')
        for field in ('source_ids', 'obligation_ids'):
            values = paragraph[field]
            require(type(values) is list and 1 <= len(values) <= 32 and all(type(v) is str for v in values)
                    and len(set(values)) == len(values), 'PREVIEW_OUTPUT_CONTRACT')
        ids, obligations = set(paragraph['source_ids']), set(paragraph['obligation_ids'])
        if not ids <= sources.keys() or not obligations <= task.obligations.keys():
            findings.append(dict(code='INVALID_SOURCE_OR_OBLIGATION_ID', paragraph=index, status='REJECTED'))
            continue
        selected = [s for key in obligations for s in reviewed.get(key, []) if s['source_id'] in ids]
        if (any(not any(s['source_id'] in ids for s in reviewed.get(key, [])) for key in obligations)
                or not ids <= {s['source_id'] for s in selected}):
            findings.append(dict(code='UNREVIEWED_CITATION', paragraph=index, status='REJECTED'))
        covered |= obligations
        # Phase7-B quantity/collection detector, scoped to this paragraph's reviewed quotes.
        scopes = tuple(Scope('PREVIEW', task.scope) for _ in range(1))
        claims = tuple(Claim(f'C{i}', sentence.strip(), scopes[0], (s['source_id'],))
                       for i, (s, sentence) in enumerate(
                           (s, sentence) for s in selected
                           for sentence in re.split(r'(?<=[.!?;])\s+|\n', s['quote']) if sentence.strip()))
        if claims:
            checked = audit(claims[:32], scopes, paragraph['text'])
            findings.extend(dict(code=f.code, paragraph=index, status=checked.status.value,
                                 excerpt=f.excerpt, signal=f.signal) for f in checked.findings)
        # Also preserve the production parser's whole numeric-expression tokenizer.
        allowed_numbers = {n for s in selected for n in extract_numeric_expressions(s['quote'])}
        if set(extract_numeric_expressions(paragraph['text'] + ' ' + paragraph['heading'])) - allowed_numbers:
            findings.append(dict(code='NUMERIC_NOT_GROUNDED', paragraph=index, status='REJECTED'))
        if not any(paragraph['text'] == s['quote'] for s in selected):
            findings.append(dict(code='SEMANTIC_SUPPORT_REQUIRES_HUMAN_REVIEW', paragraph=index,
                                 status='NEEDS_REVIEW'))
    for obligation in task.obligations.keys() - covered:
        findings.append(dict(code='REQUIRED_QUESTION_NOT_COVERED', obligation=obligation, status='REJECTED'))
    words = len(re.findall(r"\b[A-Za-z]+(?:[-'][A-Za-z]+)*\b", ' '.join(p['text'] for p in paragraphs)))
    if not 300 <= words <= 500:
        findings.append(dict(code='SUGGESTED_LENGTH_300_500', word_count=words, status='NEEDS_REVIEW'))
    require(len(findings) <= 512, 'PREVIEW_FINDING_BUDGET')
    return dict(article=article, findings=findings, word_count=words,
                TECHNICAL='SUCCEEDED', EVIDENCE='REJECTED' if any(f['status'] == 'REJECTED' for f in findings)
                else 'NEEDS_REVIEW', EDITORIAL_REVIEW='NEEDS_REVIEW',
                PRODUCTION_AUTHORIZATION='NOT_AUTHORIZED', production_authorized=False)
