"""Frozen synthetic Web experiment, separately composed; production stays closed."""
import asyncio
from dataclasses import replace
from datetime import UTC, datetime
import json
from pathlib import Path

import httpx

from foreign_trade_geo_agent.adapters.retained_deepseek import OneShotTransport, receive_candidate
from foreign_trade_geo_agent.core import content_draft as cd
from foreign_trade_geo_agent.core.evidence_intake import snapshot_digest
from foreign_trade_geo_agent.storage.serialization import _decode
from foreign_trade_geo_agent.web.generation import (
    LocalGeneration, MockArticleExecutor, canonical, check, digest, read_json,
    restrict_directory, save_bytes, TIMEOUT_SECONDS, OFFLINE_KEY, retain_review_candidate,
)
from foreign_trade_geo_agent.workflows.content_draft import ContentDraftWorkflow

ROOT = Path(__file__).resolve().parents[3]


def code_hashes():
    paths = sorted([* (ROOT / 'src').rglob('*.py'), * (ROOT / 'scripts').glob('*.py'),
                    * (ROOT / 'src/foreign_trade_geo_agent/web/templates').glob('*.html'),
                    * (ROOT / 'src/foreign_trade_geo_agent/web/static').glob('*')])
    return {p.relative_to(ROOT).as_posix(): digest(p.read_bytes()) for p in paths if p.is_file()}


def freeze(service):
    """Offline operator action after Web evidence/recheck. Does not issue a permit."""
    executor = service.generation_executor
    check(type(executor) is MockArticleExecutor, 'SYNTHETIC_PROFILE_REQUIRED')
    _, _, store, _, _ = service._load()
    current = service._current(store, service._load()[0])
    scope_review = service.require_generation_scope(current)
    value = executor.input_for(current, datetime.now(UTC))
    check(current.task.customer_id == executor.template.customer_evidence.customer_id
          and current.task == executor.task, 'SYNTHETIC_PROFILE_REQUIRED')
    raw = executor.request_for(value)
    output = service.directory / 'web-experiment'
    output.mkdir()
    restrict_directory(output)
    from foreign_trade_geo_agent.storage.serialization import _encode
    save_bytes(output / 'native-input.json', canonical(_encode(value)))
    save_bytes(output / 'snapshot.json', canonical(_encode(current)))
    save_bytes(output / 'scope-review.json', canonical({'mode': 'TEST_ONLY_NOT_HUMAN_SIGNOFF',
        'production_authorized': False, 'assessment': _encode(scope_review)}))
    save_bytes(output / 'request.json', raw)
    manifest = {'scope': 'SYNTHETIC_TEST_ONLY_WEB', 'request_sha256': digest(raw),
        'snapshot_sha256': snapshot_digest(current), 'request_bytes': len(raw),
        'files': {p.name: digest(p.read_bytes()) for p in sorted(output.iterdir())},
        'code': code_hashes(), 'model': 'deepseek-flash', 'max_tokens': json.loads(raw)['max_tokens'],
        'timeout_seconds': TIMEOUT_SECONDS, 'max_requests': 1, 'automatic_retries': 0,
        'production_authorized': False, 'wordpress_authorized': False}
    save_bytes(output / 'bundle.json', canonical(manifest))
    bundle = digest(canonical(manifest))
    save_bytes(output / 'bundle.sha256', (bundle + '\n').encode())
    return bundle


class FrozenWebExecutor:
    def __init__(self, directory, bundle, ledger, permit, *, transport=None):
        self.directory, self.bundle, self.ledger, self.permit = Path(directory).resolve(), bundle, ledger, permit
        check(transport is None or type(transport) is httpx.MockTransport, 'MOCK_TRANSPORT_REQUIRED')
        self.mode = 'LIVE' if transport is None else 'MOCK'
        self.transport, self.calls = transport, 0

    def load(self, current):
        root = self.directory / 'web-experiment'
        raw_manifest = (root / 'bundle.json').read_bytes()
        check(digest(raw_manifest) == self.bundle, 'BUNDLE_CHANGED')
        manifest = json.loads(raw_manifest)
        check(manifest['code'] == code_hashes(), 'EXPERIMENT_CODE_CHANGED')
        check(all(Path(n).name == n and digest((root / n).read_bytes()) == h
                  for n, h in manifest['files'].items()), 'FROZEN_INPUT_CHANGED')
        value = _decode(read_json(root / 'native-input.json', 100_000), cd.ContentDraftInput)
        from foreign_trade_geo_agent.core.evidence_intake import SemanticAssessment, article_scope_error
        review = read_json(root / 'scope-review.json', 100_000)
        assessment = _decode(review['assessment'], SemanticAssessment)
        check(review['mode'] == 'TEST_ONLY_NOT_HUMAN_SIGNOFF' and review['production_authorized'] is False
              and assessment.snapshot_sha256 == snapshot_digest(current)
              and article_scope_error(assessment) is None, 'ARTICLE_SCOPE_REVIEW_REQUIRED')
        raw = (root / 'request.json').read_bytes()
        check(snapshot_digest(current) == value.customer_evidence.snapshot_sha256 == manifest['snapshot_sha256']
              and current.task.task_id == value.customer_evidence.task_id
              and current.task.customer_id == value.customer_evidence.customer_id
              and current.plan_bound, 'STALE_BINDING')
        check(raw == MockArticleExecutor.request_for(value) and digest(raw) == manifest['request_sha256'],
              'FROZEN_REQUEST_CHANGED')
        # Repeat TEST-only structural review of the exact current snapshot.
        # Its freshness timestamp is not request material or human authority.
        # This never changes the frozen evidence/Plan or renews the permit.
        value = replace(value, customer_evidence=replace(value.customer_evidence, reviewed_at=datetime.now(UTC)))
        check(cd.stable_content_draft_input_error(value) is None
              and MockArticleExecutor.request_for(value) == raw, 'NATIVE_INPUT_INVALID')
        self.ledger.validate(self.permit, self.bundle, self.directory, digest(raw), self.mode)
        return value, raw

    async def execute(self, value, raw, output, metadata):
        row = self.ledger.validate(self.permit, self.bundle, self.directory, digest(raw), self.mode)
        check(row[7] is not None, 'PERMIT_NOT_CLAIMED')
        expiry = datetime.fromisoformat(row[5])
        check(datetime.now(UTC) < expiry, 'PERMIT_EXPIRED')
        key, transport = OFFLINE_KEY, self.transport
        if self.mode == 'LIVE':
            # Only the explicitly invoked isolated launcher composes this class.
            # No browser/environment setting can switch a Mock executor to LIVE.
            import os
            from scripts.local_env import load_api_keys
            try:
                load_api_keys('DEEPSEEK_API_KEY', project_root=ROOT)
                key = os.environ.get('DEEPSEEK_API_KEY', '').strip()
                check(bool(key), 'CREDENTIALS_UNAVAILABLE')
            except Exception:
                raise ValueError('CREDENTIALS_UNAVAILABLE') from None
            transport = httpx.AsyncHTTPTransport(retries=0, trust_env=False)
        guard = OneShotTransport(transport, raw, expires_at=expiry,
            request_limit=(cd.MAX_INPUT_ENVELOPE_BYTES if any(s.facts for s in value.customer_evidence.sources) else 16000))

        async def validator(native, text):
            if native.propose_interpretations:
                retain_review_candidate(native, text, output, metadata)
                raise ValueError('INTERPRETATION_PENDING_REVIEW')
            class CapturedWriter:
                async def write_content_draft(self, prompt):
                    return cd.ContentDraftGeneration('deepseek', 'deepseek-flash',
                        cd.ContentDraftGenerationStatus.SUCCESS, text, None)
            report = await ContentDraftWorkflow(CapturedWriter(), max_repair_attempts=0).run(native)
            check(report.status is cd.ContentDraftStatus.SUCCESS, report.error or 'NATIVE_VALIDATION_FAILED')
            return report

        try:
            self.calls += 1
            return await asyncio.wait_for(receive_candidate(value, raw, guard, key, output=output,
                metadata=metadata, validator=validator, detail=lambda v, t, c: {'category': c},
                timeout=TIMEOUT_SECONDS), TIMEOUT_SECONDS)
        finally:
            metadata.update(request_count=guard.calls, real_requests=guard.calls if self.mode == 'LIVE' else 0)


class FrozenWebGeneration(LocalGeneration):
    workflow_name = 'isolated_frozen_web_content_draft_TEST_ONLY'

    def _prepare(self):
        executor = self.service.generation_executor
        check(type(executor) is FrozenWebExecutor and executor.directory == self.service.directory.resolve(),
              'FROZEN_EXECUTOR_REQUIRED')
        session, _, store, _, _ = self.service._load()
        current = self.service._current(store, session)
        self.service.require_generation_scope(current)
        value, raw = executor.load(current)
        return executor, store, value, raw, executor.bundle

    def view(self):
        state = super().view()
        executor = self.service.generation_executor
        state.update(frozen_experiment=True, execution_mode=executor.mode, bundle_sha256=executor.bundle)
        try:
            row = executor.ledger.read(executor.permit)
            state['permit_expires_at'] = row[5]
            if row[7] is not None and state['generation_state'] == 'NOT_GENERATED':
                state.update(generation_state='UNKNOWN', generation_allowed=False,
                    generation_reason='许可已持久化消费，结果未确认。禁止重试。')
            if row[7] is None:
                executor.ledger.validate(executor.permit, executor.bundle, executor.directory,
                    row[3], executor.mode, unclaimed=True)
            elif state['generation_state'] == 'REQUEST_FAILED' and not state.get('attempt', {}).get('error'):
                state['generation_state'] = 'UNKNOWN'
            if state['generation_state'] == 'UNKNOWN' and state.get('attempt') and not state['attempt'].get('error'):
                state['attempt'] = dict(state['attempt'], response_state='RETENTION_UNCONFIRMED', response_saved=False)
                state['generation_reason'] = '许可已消费，但完成诊断未保存；响应、usage 和结果留存状态未知，禁止重试。'
        except Exception:
            state.update(generation_allowed=False, generation_reason='实验许可缺失、已截止或绑定失效；禁止执行。')
        return state

    def start(self, binding_sha256, ticket):
        from foreign_trade_geo_agent.web.mvp_application import MVPError
        try:
            executor, store, value, raw, key = self._prepare()
            check(key == binding_sha256, 'STALE_BINDING')
            row = executor.ledger.validate(executor.permit, key, executor.directory, digest(raw), executor.mode)
            if row[7] is not None:
                return  # Consumed even if output is missing, process died or path changed.
            check(ticket and ticket[0] == key and datetime.now(UTC) < ticket[1], 'STALE_TICKET')
            with store.snapshot_guard():
                check(snapshot_digest(store.latest(value.customer_evidence.project_id, value.customer_evidence.task_id))
                      == value.customer_evidence.snapshot_sha256, 'STALE_BINDING')
                executor.ledger.claim(executor.permit, key, executor.directory, digest(raw), executor.mode)
                output = self.root / key
                self.root.mkdir(exist_ok=True)
                output.mkdir()  # If setup fails, permit remains consumed.
                restrict_directory(output)
                save_bytes(output / 'request.json', raw)
                started = {'binding_sha256': key, 'request_sha256': digest(raw), 'state': 'RUNNING',
                    'mode': executor.mode, 'permit': executor.permit, 'scope': 'SYNTHETIC_TEST_ONLY_WEB',
                    'snapshot_sha256': value.customer_evidence.snapshot_sha256,
                    'task_version': value.customer_evidence.task_version, 'plan_version': value.customer_evidence.plan_version,
                    'evidence_version': value.customer_evidence.evidence_version,
                    'snapshot_revision': value.customer_evidence.snapshot_revision,
                    'started_at': datetime.now(UTC).isoformat(), 'expires_at': row[5], 'max_requests': 1,
                    'automatic_retries': 0, 'real_requests': None if executor.mode == 'LIVE' else 0, 'production_authorized': False,
                    'wordpress_authorized': False, 'usage': None}
                save_bytes(output / 'started.json', canonical(started))
            self.active.add(key)
            task = asyncio.create_task(self._run(executor, value, raw, output, started))
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)
        except Exception:
            raise MVPError('冻结版本或实验许可不可用；许可一经占用即禁止重试。请查看执行状态。', 409) from None

    @staticmethod
    def failure_state(metadata, exc):
        if metadata.get('failure_stage') == 'native_validation':
            return 'VALIDATION_FAILED'
        if isinstance(exc, (TimeoutError, httpx.RequestError, asyncio.CancelledError)):
            return 'UNKNOWN'
        if metadata.get('state') == 'SUCCEEDED' or str(exc) == 'OUTPUT_INCOMPLETE' \
                or metadata.get('failure_stage') in {'candidate_persistence', 'response_persistence',
                'model_text_persistence', 'rejected_candidate_persistence', 'binding_revalidation'}:
            return 'INCOMPLETE'
        return 'REQUEST_FAILED'

    def selected(self):
        if not (self.root / 'selected.json').exists():
            return None
        key = read_json(self.root / 'selected.json')['binding_sha256']
        check(key == self.service.generation_executor.bundle, 'LOCAL_RECORD_INVALID')
        result = read_json(self.root / key / 'result.json')
        check(result['state'] == 'SUCCEEDED' and result['mode'] == self.service.generation_executor.mode
              and result['binding_sha256'] == key and result['production_authorized'] is False
              and not (self.root / key / 'failed.json').exists(), 'LOCAL_RECORD_INVALID')
        return self.root / key / 'history.sqlite3', result
