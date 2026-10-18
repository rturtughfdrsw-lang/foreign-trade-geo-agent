"""One bounded Preview path; no production Admission, research, or delivery."""
import asyncio
from dataclasses import asdict
import json
from uuid import uuid4

from foreign_trade_geo_agent.core.commercial_preview import (
    EvidenceSource, EvidenceSpan, ExecutionConfirmation, PreviewAnalyzer, PreviewGeneration, PreviewStore, PreviewTask,
    PreviewWriter, SupportReview, admit, check_evidence, digest, evidence_digest, material,
    parse_article, readiness, request_digest, require, sha, task_from,
)


class CommercialPreviewWorkflow:
    def __init__(self, store: PreviewStore, writer: PreviewWriter, analyzer: PreviewAnalyzer):
        self.store, self.writer, self.analyzer = store, writer, analyzer
        self._initial_policy = writer.policy()

    def writer_policy(self):
        policy = self.writer.policy() if hasattr(self.writer, 'policy') else None
        # Preserve the V1 string-writer port for injected offline test writers.
        return policy if type(policy) is dict else self._initial_policy

    async def analyze(self, website, **options):
        run_id = str(uuid4())
        analysis = await self.analyzer.analyze(website, run_id, **options)
        state = dict(run_id=run_id, revision=1, analysis=analysis, task=None,
                     sources=[], spans=[], reviews=[], confirmation=None, production_authorized=False,
                     execution_policy=self.writer_policy())
        self.store.create(state)
        return state

    def current(self, run_id, revision, state_digest):
        state = self.store.read(run_id)
        require(state['revision'] == revision and digest(state) == state_digest, 'PREVIEW_STALE_FORM')
        return state

    def confirm_task(self, run_id, revision, state_digest, *, title, reader_question, required_facts, scope, limitations):
        state = self.current(run_id, revision, state_digest)
        require(state['analysis']['topic'] is not None, 'PREVIEW_NO_SUITABLE_TOPIC')
        old = state['task']
        # Updates retain the mandatory question/fact slots; no automatic topic narrowing.
        if old:
            require(len(required_facts) == len(old['required_facts']), 'PREVIEW_REQUIRED_FACTS_CANNOT_BE_REMOVED')
        task = PreviewTask(run_id, old['task_id'] if old else str(uuid4()), old['version'] + 1 if old else 1,
                           state['analysis']['website'], title, reader_question, tuple(required_facts), scope, limitations)
        state.update(task=asdict(task), sources=[], spans=[], reviews=[], confirmation=None)
        state['execution_policy'] = self.writer_policy()
        if state['analysis']['data_kind'] == 'REAL':
            for page in state['analysis']['content']['pages']:
                if not page.get('body_text'):
                    continue
                source = EvidenceSource(run_id, task.task_id, task.version, str(uuid4()),
                    page.get('title') or 'Website sample', page['final_url'], page['body_text'],
                    sha(page['body_text']), task.scope, 'REAL', source_type='WEBSITE_SAMPLE', page_digest=digest(page))
                state['sources'].append(asdict(source))
        return self.store.save(state, revision)

    def bind_page(self, run_id, revision, state_digest, *, source_id, obligation_id, quote):
        state = self.current(run_id, revision, state_digest)
        task = task_from(state['task'])
        require(len(state['spans']) < 64 and type(quote) is str and 0 < len(quote) <= 16000,
                'PREVIEW_SPAN_INVALID')
        source = next((EvidenceSource(**s) for s in state['sources'] if s['source_id'] == source_id), None)
        require(source is not None and source.source_type == 'WEBSITE_SAMPLE', 'PREVIEW_PAGE_SOURCE_REQUIRED')
        start = source.content.find(quote)
        span = EvidenceSpan(str(uuid4()), source_id, obligation_id, start, start+len(quote), quote, source.content_sha256)
        span.validate(source, task)
        state['spans'].append(asdict(span))
        state.update(reviews=[], confirmation=None)
        return self.store.save(state, revision)

    def supplement(self, run_id, revision, state_digest, *, obligation_id, content, label, locator,
                   start=0, end=None, content_sha256=None):
        state = self.current(run_id, revision, state_digest)
        task = task_from(state['task'])
        require(obligation_id in task.obligations and len(state['sources']) < 32, 'PREVIEW_EVIDENCE_BUDGET')
        source = EvidenceSource(run_id, task.task_id, task.version, str(uuid4()), label, locator,
                                content, content_sha256 or sha(content), task.scope, state['analysis']['data_kind'])
        end = len(content) if end is None else end
        span = EvidenceSpan(str(uuid4()), source.source_id, obligation_id, start, end, content[start:end],
                            source.content_sha256)
        span.validate(source, task)
        state['sources'].append(asdict(source))
        state['spans'].append(asdict(span))
        state.update(reviews=[], confirmation=None)
        return self.store.save(state, revision)

    def remove_source(self, run_id, revision, state_digest, source_id):
        state = self.current(run_id, revision, state_digest)
        require(any(s['source_id'] == source_id for s in state['sources']), 'PREVIEW_SOURCE_MISSING')
        state['sources'] = [s for s in state['sources'] if s['source_id'] != source_id]
        state['spans'] = [s for s in state['spans'] if s['source_id'] != source_id]
        state.update(reviews=[], confirmation=None)
        return self.store.save(state, revision)

    def review(self, run_id, revision, state_digest, *, obligation_id, span_ids, verdict, note):
        state = self.current(run_id, revision, state_digest)
        task, spans, _ = check_evidence(state)
        require(obligation_id in task.obligations)
        allowed = {s.span_id for s in spans if s.obligation_id == obligation_id}
        # Every currently bound candidate span must be considered. A reviewer
        # cannot silently omit a conflicting source from this obligation.
        require(set(span_ids) == allowed, 'PREVIEW_REVIEW_SPAN_BINDING')
        review = SupportReview(run_id, task.task_id, task.version, evidence_digest(state),
                               obligation_id, tuple(span_ids), verdict, note)
        state['reviews'] = [r for r in state['reviews'] if r['obligation_id'] != obligation_id] + [asdict(review)]
        state.update(confirmation=None)
        return self.store.save(state, revision)

    def confirm_execution(self, run_id, revision, state_digest):
        state = self.current(run_id, revision, state_digest)
        require(not readiness(state), 'PREVIEW_EVIDENCE_OR_REVIEW_REQUIRED')
        require(state.get('execution_policy', self.writer_policy()) == self.writer_policy(), 'PREVIEW_MODEL_POLICY_BINDING')
        if hasattr(self.writer, 'check_ready'):
            self.writer.check_ready()
        require(self.store.attempt(run_id) is None, 'PREVIEW_EXECUTION_CONSUMED')
        if state['confirmation']:
            return state
        task = task_from(state['task'])
        confirmation = ExecutionConfirmation(str(uuid4()), run_id, task.task_id, task.version,
                                             evidence_digest(state), request_digest(state))
        state['confirmation'] = asdict(confirmation)
        return self.store.save(state, revision)

    async def execute(self, run_id, confirmation):
        state = self.store.read(run_id)
        admit(state, confirmation)
        attempt = self.store.reserve(state, confirmation)
        if attempt['duplicate']:
            return self.result(run_id)
        raw = None
        metadata = {}
        try:
            require(state.get('execution_policy', self.writer_policy()) == self.writer_policy(), 'PREVIEW_MODEL_POLICY_BINDING')
            timeout = getattr(self.writer, 'timeout_seconds', 30)
            async with asyncio.timeout((timeout if type(timeout) in {int, float} else 30) + 1):
                # An adapter cannot mutate the admitted snapshot through shared dictionaries.
                request = json.loads(json.dumps(material(state)))
                request['confirmation'] = asdict(confirmation)
                generated = await self.writer.generate(request)
            if isinstance(generated, PreviewGeneration):
                raw, metadata = generated.raw, generated.metadata
                if generated.failure:
                    result = dict(TECHNICAL=generated.technical, EVIDENCE='NOT_CHECKED',
                                  EDITORIAL_REVIEW='NEEDS_REVIEW', PRODUCTION_AUTHORIZATION='NOT_AUTHORIZED',
                                  production_authorized=False, failure=generated.failure)
                    if raw is not None:
                        result['raw'] = raw
            else:
                raw = generated
            if not isinstance(generated, PreviewGeneration) or not generated.failure:
                result = parse_article(raw, state)
                result['raw'] = raw
        except (Exception, asyncio.CancelledError) as error:
            # Never persist provider exceptions or secret-bearing response envelopes.
            result = dict(TECHNICAL='FAILED' if raw is not None else 'UNKNOWN',
                          EVIDENCE='REJECTED' if raw is not None else 'NOT_CHECKED',
                          EDITORIAL_REVIEW='NEEDS_REVIEW', PRODUCTION_AUTHORIZATION='NOT_AUTHORIZED',
                          production_authorized=False, failure='PREVIEW_WRITER_OR_OUTPUT_FAILED')
            if type(raw) is str and len(raw.encode('utf-8')) <= 65536:
                result['raw'] = raw
            if type(error) is ValueError and str(error) in {
                'PREVIEW_MODEL_POLICY_BINDING', 'PREVIEW_MODEL_INPUT_BUDGET',
                'PREVIEW_MODEL_NOT_ENABLED', 'PREVIEW_MODEL_NOT_CONFIGURED',
            }:
                result.update(TECHNICAL='FAILED', failure=str(error))
        if metadata:
            result['provider'] = metadata
        # Persistence failure propagates. Reservation remains consumed, never a false success.
        self.store.finish(attempt['attempt_id'], result)
        return self.result(run_id)

    def result(self, run_id):
        attempt = self.store.attempt(run_id)
        if attempt is not None:
            state = self.store.read(run_id)
            attempt['freshness'] = 'CURRENT' if state['task'] and request_digest(state) == attempt['request_digest'] else 'STALE'
        return attempt
