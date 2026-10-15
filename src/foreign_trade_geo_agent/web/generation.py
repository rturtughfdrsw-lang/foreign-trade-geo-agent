"""Local one-shot generation composition over native Workflow/History/Review.

The only executor admitted by this release is explicitly injected MockTransport.
No form, environment variable, TEST review or saved state can enable paid HTTP.
"""
import asyncio
from dataclasses import replace
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from uuid import uuid4

import httpx

from foreign_trade_geo_agent.adapters.deepseek_content_draft import DeepSeekContentDraftWriter, content_draft_request_payload
from foreign_trade_geo_agent.adapters.retained_deepseek import (
    OneShotTransport, receive_candidate, restrict_directory, save_bytes, MAX_REQUEST_BYTES, MAX_RESPONSE_BYTES,
)
from foreign_trade_geo_agent.core import content_draft as cd
from foreign_trade_geo_agent.core.content_draft_review import ContentDraftReviewRequest
from foreign_trade_geo_agent.core.draft_customer_evidence import DraftCustomerEvidence, DraftCustomerSource, native_scope_digest
from foreign_trade_geo_agent.core.evidence_intake import snapshot_digest, SupplementMethod
from foreign_trade_geo_agent.core.history import ArtifactRecord, ArtifactType, RunStatus, WorkflowRun
from foreign_trade_geo_agent.storage.sqlite import SQLiteHistoryStore, SQLiteHistoryReader
from foreign_trade_geo_agent.workflows.content_draft import ContentDraftWorkflow
from foreign_trade_geo_agent.workflows.content_draft_review import ContentDraftReviewWorkflow

TIMEOUT_SECONDS = 60.0
WORKFLOW = 'isolated_web_mock_content_draft'
OFFLINE_KEY = 'OFFLINE-WEB-PLACEHOLDER'


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read_json(path, maximum=8192):
    with path.open('rb') as stream:
        raw = stream.read(maximum + 1)
    if len(raw) > maximum:
        raise ValueError('LOCAL_RECORD_INVALID')
    return json.loads(raw)


def check(condition, reason):
    if not condition:
        raise ValueError(reason)


def retain_review_candidate(native, text, output, metadata):
    """Shared retention for a NEW native proposal; no review is synthesized."""
    from foreign_trade_geo_agent.workflows.content_draft import inspect_candidate_output
    from foreign_trade_geo_agent.storage.content_draft_review import SQLiteLocalDraftReviewStore
    from foreign_trade_geo_agent.core.draft_candidate_review import digest
    check_result = inspect_candidate_output(native, text,
        current_snapshot_sha256=native.customer_evidence.snapshot_sha256)
    journal = SQLiteLocalDraftReviewStore(output / 'local-review.sqlite3')
    journal.append(origin_sha256=digest(text), expected_version=0, original_body=text,
        body_text=text, note='Original model candidate; no semantic approval.', status='PENDING_REVIEW',
        frozen_evidence_sha256=native.customer_evidence.snapshot_sha256,
        observed_evidence_sha256=native.customer_evidence.snapshot_sha256, saved_at=datetime.now(UTC))
    metadata['candidate_available'] = True
    metadata['candidate_state'] = check_result.state
    metadata['candidate_errors'] = list(check_result.errors)


class MockArticleExecutor:
    """Trusted-side synthetic fixture profile; never production admission.

    Task/native graph/quotes come from the offline package builder. Web evidence
    is accepted only if its complete bytes and obligations match this profile.
    This is structural fixture matching, not an invented semantic reviewer.
    """
    mode = 'MOCK'

    def __init__(self, *, task, template, transport):
        check(type(transport) is httpx.MockTransport, 'MOCK_TRANSPORT_REQUIRED')
        check(template.customer_evidence is not None and len(template.change_plan_report.operations) == 1,
              'SYNTHETIC_PROFILE_REQUIRED')
        self.task, self.template, self.transport = task, template, transport
        self.calls = 0

    def input_for(self, current, now):
        check(current.task == self.task, 'TASK_CHANGED')
        check(bool(current.active_evidence), 'EVIDENCE_INSUFFICIENT')
        check(current.plan_bound, 'PLAN_RECHECK_REQUIRED')
        value = current.planning_input
        check(len(value.change_plan_report.operations) == 1 and value.customer_evidence is None,
              'PLAN_CHANGED')
        check(native_scope_digest(value.site_content, value.opportunity_report, value.change_plan_report.operations[0])
              == self.template.customer_evidence.native_scope_sha256, 'PLAN_CHANGED')
        frozen = self.template.customer_evidence.sources
        check(len(current.active_evidence) == len(frozen), 'EVIDENCE_NOT_ALLOWLISTED')
        sources = []
        for record, expected in zip(current.active_evidence, frozen):
            material = record.supplement
            check(material.method is SupplementMethod.TEXT_DOCUMENT
                  and material.content == expected.content and material.file_sha256 == expected.content_sha256
                  and material.requirement_ids == expected.requirement_ids, 'EVIDENCE_NOT_ALLOWLISTED')
            sources.append(DraftCustomerSource(material.evidence_id, record.evidence_version,
                material.requirement_ids, material.source_label, material.source_locator, material.content,
                material.file_sha256, expected.span_start, expected.span_end, expected.quote, expected.facts))
        bundle = DraftCustomerEvidence(current.task.project_id, current.task.customer_id, current.task.task_id,
            current.task.task_version, current.plan_version, current.evidence_version, current.revision,
            snapshot_digest(current), native_scope_digest(value.site_content, value.opportunity_report,
                value.change_plan_report.operations[0]), value.change_plan_report.operations[0].change_id,
            'SYNTHETIC-WEB-FIXTURE-NOT-HUMAN', now, 'TEST_ONLY_SUPPORTED_NOT_HUMAN_SIGNOFF', tuple(sources),
            self.template.customer_evidence.interpretations)
        brief = self.template.writing_brief
        if brief is not None:
            check(brief.snapshot_sha256 == snapshot_digest(current) and brief.goal == current.task.goal,
                  'ARTICLE_BRIEF_BINDING_INVALID')
        result = replace(value, customer_evidence=bundle, writing_brief=brief,
            propose_interpretations=self.template.propose_interpretations)
        check(cd.stable_content_draft_input_error(result) is None, 'NATIVE_INPUT_INVALID')
        return result

    @staticmethod
    def request_for(value):
        prompt = cd.build_content_draft_prompt(value, value.change_plan_report.operations[0].change_id)
        system = DeepSeekContentDraftWriter.build_system_prompt(customer_evidence=True, propose_interpretations=value.propose_interpretations)
        material = prompt.material_json()
        request = canonical(content_draft_request_payload(system, material))
        check(len(system) <= cd.MAX_SYSTEM_PROMPT_CHARS and len(system.encode()) <= cd.MAX_SYSTEM_PROMPT_BYTES
              and len(material) <= cd.MAX_USER_MATERIAL_CHARS and len(material.encode()) <= cd.MAX_USER_MATERIAL_BYTES
              and len(request) <= (cd.MAX_INPUT_ENVELOPE_BYTES if any(s.facts for s in value.customer_evidence.sources)
                                  else MAX_REQUEST_BYTES)
              and len(request.decode()) <= cd.MAX_INPUT_ENVELOPE_CHARS, 'INPUT_BUDGET_EXCEEDED')
        return request

    async def execute(self, value, raw, output, metadata):
        check(type(self.transport) is httpx.MockTransport, 'MOCK_TRANSPORT_REQUIRED')
        guard = OneShotTransport(self.transport, raw, request_limit=(cd.MAX_INPUT_ENVELOPE_BYTES
            if any(s.facts for s in value.customer_evidence.sources) else MAX_REQUEST_BYTES))

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

        self.calls += 1
        try:
            return await asyncio.wait_for(receive_candidate(value, raw, guard, OFFLINE_KEY,
                output=output, metadata=metadata, validator=validator,
                detail=lambda v, t, c: {'category': c}, timeout=TIMEOUT_SECONDS), TIMEOUT_SECONDS)
        finally:
            metadata['request_count'] = guard.calls


class LocalGeneration:
    """Exclusive durable reservations survive refresh, retries and process restart.

    Directory creation reserves a binding BEFORE any HTTP. Missing completion
    records consume that binding forever; restart never resumes a request.
    """
    def __init__(self, service):
        self.service = service
        self.tasks = set()
        self.active = set()

    @property
    def root(self):
        return self.service.directory / 'generation'

    def _prepare(self):
        executor = self.service.generation_executor
        check(type(executor) is MockArticleExecutor, 'MOCK_DISABLED')
        session, _, store, _, _ = self.service._load()
        current = self.service._current(store, session)
        assessment = self.service.require_generation_scope(current)
        value = executor.input_for(current, datetime.now(UTC))
        if any(s.facts for s in value.customer_evidence.sources):
            from foreign_trade_geo_agent.workflows.evidence_intake import reviewed_draft_input
            fresh = reviewed_draft_input(current, assessment, now=datetime.now(UTC),
                propose_interpretations=value.propose_interpretations)
            check(fresh.customer_evidence.sources == value.customer_evidence.sources
                  and fresh.customer_evidence.interpretations == value.customer_evidence.interpretations,
                  'REVIEWED_EXPLANATION_CHANGED')
            check(value.writing_brief is not None and
                  (value.writing_brief.article_type, value.writing_brief.reader_problem, value.writing_brief.search_intent)
                  == (current.task.article_type, current.task.reader_problem, current.task.search_intent),
                  'ARTICLE_BRIEF_BINDING_INVALID')
        request = executor.request_for(value)
        key = digest(canonical({'snapshot': snapshot_digest(current), 'request': digest(request), 'mode': 'MOCK'}))
        return executor, store, value, request, key

    def view(self):
        state = {'generation_state': 'NOT_GENERATED', 'generation_allowed': False, 'generation_reason': None,
                 'attempt': None, 'binding_sha256': '', 'generation_expires_at': '', 'web_candidate_available': False,
                 'generation_response_limit': MAX_RESPONSE_BYTES}
        try:
            state['web_candidate_available'] = bool(self.selected())
            _, _, value, raw, key = self._prepare()
            state.update(binding_sha256=key, generation_request_sha256=digest(raw),
                         generation_sources=value.customer_evidence.sources, generation_request_bytes=len(raw),
                         generation_request_limit=(cd.MAX_INPUT_ENVELOPE_BYTES if any(s.facts for s in value.customer_evidence.sources) else MAX_REQUEST_BYTES))
            output = self.root / key
            if output.exists():
                started = read_json(output / 'started.json')
                if (output / 'result.json').exists() or (output / 'failed.json').exists():
                    result = read_json(output / ('failed.json' if (output / 'failed.json').exists() else 'result.json'))
                    check(result['binding_sha256'] == key, 'LOCAL_RECORD_INVALID')
                    if result['state'] == 'SUCCEEDED':
                        check(self.selected()[1]['binding_sha256'] == key, 'LOCAL_RECORD_INVALID')
                    state.update(generation_state=result['state'], attempt=result)
                elif key in self.active:
                    state.update(generation_state='RUNNING', attempt=started)
                else:
                    state.update(generation_state='REQUEST_FAILED', attempt=started,
                                 generation_reason='上次执行中断或仍由另一服务处理；已消费绑定，不自动重试。')
            else:
                state['generation_allowed'] = not self.active
        except ValueError as exc:
            reasons = {'MOCK_DISABLED': '未配置隔离 Mock 执行器', 'EVIDENCE_INSUFFICIENT': '证据不足，先补充资料。',
                'EVIDENCE_GAPS_REMAIN': '证据不足，请查看已覆盖与缺失要求并补充资料。',
                'ARTICLE_SCOPE_REVIEW_REQUIRED': '文章目标、Plan 与证据要求需人工审核范围一致性；当前不可生成。',
                'ARTICLE_SCOPE_MISMATCH': '文章目标超出当前 Plan 或证据义务覆盖范围，请补充资料或请求调整文章范围。',
                'ARTICLE_BRIEF_BINDING_INVALID': '写作 brief 与当前任务或证据版本不一致；请重新准备并确认。',
                'REVIEWED_EXPLANATION_CHANGED': '事实或解释的当前审核已变化；请重新准备证据映射和解释边界。',
                'PLAN_RECHECK_REQUIRED': 'Plan 尚未绑定当前证据，请先重新核对。',
                'PLAN_REBIND_REQUIRED': 'Plan 尚未绑定当前证据，请先重新规划和确认。',
                'TASK_CHANGED': '任务已改变，超出本地合成测试许可。', 'PLAN_CHANGED': 'Plan 已改变，超出本地合成测试许可。',
                'EVIDENCE_NOT_ALLOWLISTED': '当前证据不匹配隔离测试许可，禁止生成。'}
            state['generation_reason'] = reasons.get(str(exc), '本地生成资料不可用；禁止执行。')
        except Exception:
            state['generation_reason'] = '本地生成记录不可读取；禁止执行。'
        return state

    def start(self, binding_sha256, ticket):
        from foreign_trade_geo_agent.web.mvp_application import MVPError
        try:
            executor, store, value, raw, key = self._prepare()
            check(key == binding_sha256, 'STALE_BINDING')
            output = self.root / key
            if output.exists():
                # Duplicate POST returns the persisted status, including failures.
                return
            check(ticket and ticket[0] == key and datetime.now(UTC) <= ticket[1], 'STALE_TICKET')
            check(not self.active, 'BUSY')
            self.root.mkdir(exist_ok=True)
            check(len(list(self.root.iterdir())) < 40, 'ATTEMPT_LIMIT')
            with store.snapshot_guard():
                check(snapshot_digest(store.latest(value.customer_evidence.project_id, value.customer_evidence.task_id))
                      == value.customer_evidence.snapshot_sha256, 'STALE_BINDING')
                try:
                    output.mkdir()  # Atomic across pages/processes; never removed.
                except FileExistsError:
                    return
                restrict_directory(output)
                save_bytes(output / 'request.json', raw)
                started = {'binding_sha256': key, 'request_sha256': digest(raw), 'state': 'RUNNING', 'mode': 'MOCK',
                    'snapshot_sha256': value.customer_evidence.snapshot_sha256,
                    'task_version': value.customer_evidence.task_version, 'plan_version': value.customer_evidence.plan_version,
                    'evidence_version': value.customer_evidence.evidence_version, 'snapshot_revision': value.customer_evidence.snapshot_revision,
                    'started_at': datetime.now(UTC).isoformat(), 'automatic_retries': 0, 'real_requests': 0,
                    'production_authorized': False, 'usage': None}
                save_bytes(output / 'started.json', canonical(started))
            self.active.add(key)
            task = asyncio.create_task(self._run(executor, value, raw, output, started))
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)
        except Exception:
            raise MVPError('任务、Plan、证据、许可或提交窗口已过期；未发起新的模型请求。请刷新检查。', 409) from None

    async def _run(self, executor, value, raw, output, started):
        metadata = dict(started)
        metadata.update(response_state='NO_RESPONSE', response_saved=False, request_count=0)
        key = started['binding_sha256']
        try:
            check(self.service.generation_executor is executor, 'PROFILE_CHANGED')
            _, _, _, before_raw, before_key = self._prepare()
            check(value.customer_evidence.fresh_at(datetime.now(UTC)) and before_key == key and before_raw == raw,
                  'STALE_BINDING')
            # Stable frozen material is explicit TEST-only. No production admission
            # is minted. Current fixture/profile is checked again after the await.
            if value.propose_interpretations:
                from foreign_trade_geo_agent.storage.serialization import _encode
                save_bytes(output / 'native-input.json', canonical(_encode(value)))
            report, _, _ = await executor.execute(value, raw, output, metadata)
            metadata['failure_stage'] = 'binding_revalidation'
            check(self.service.generation_executor is executor, 'PROFILE_CHANGED')
            _, store, latest, latest_raw, latest_key = self._prepare()
            check(value.customer_evidence.fresh_at(datetime.now(UTC)), 'STALE_BINDING')
            latest = replace(latest, customer_evidence=replace(latest.customer_evidence,
                reviewed_at=value.customer_evidence.reviewed_at))
            check(latest == value and latest_raw == raw and latest_key == key, 'STALE_BINDING')
            with store.snapshot_guard():
                check(snapshot_digest(store.latest(value.customer_evidence.project_id, value.customer_evidence.task_id))
                      == value.customer_evidence.snapshot_sha256, 'STALE_BINDING')
                metadata['failure_stage'] = 'candidate_persistence'
                history = SQLiteHistoryStore(output / 'history.sqlite3')
                run_id, artifact_id, now = str(uuid4()), str(uuid4()), datetime.now(UTC)
                session, reader, _, _, _ = self.service._load()
                site_key = reader.get_run(session['project_id']).site_key
                history.create_run(WorkflowRun(run_id, site_key, getattr(self, 'workflow_name', WORKFLOW), now, None, RunStatus.RUNNING, None, None))
                for kind, payload in ((ArtifactType.SITE_CONTENT, value.site_content),
                        (ArtifactType.CONTENT_OPPORTUNITY, value.opportunity_report),
                        (ArtifactType.CHANGE_PLAN, value.change_plan_report), (ArtifactType.CONTENT_DRAFT, report)):
                    history.append_artifact(ArtifactRecord(artifact_id if kind is ArtifactType.CONTENT_DRAFT else str(uuid4()),
                        run_id, kind, 1, now, payload))
                history.finish_run(run_id, status=RunStatus.SUCCEEDED, completed_at=datetime.now(UTC))
                persisted = SQLiteHistoryReader(output / 'history.sqlite3')
                check(persisted.get_artifact(artifact_id).payload == report, 'PERSISTENCE_MISMATCH')
                ContentDraftReviewWorkflow(history_reader=persisted).review(ContentDraftReviewRequest(run_id, artifact_id, 'D1'))
                metadata.update(state='SUCCEEDED', run_id=run_id, artifact_id=artifact_id, failure_stage=None)
                save_bytes(output / 'result.json', canonical(metadata))
                # Selection is separate from the immutable original package.
                selected = self.root / 'selected.pending'
                selected.write_bytes(canonical({'binding_sha256': key}))
                selected.replace(self.root / 'selected.json')
        except BaseException as exc:
            category = str(exc) if type(exc) is ValueError and str(exc) in {c.value for c in cd.ContentDraftValidationCategory} else None
            metadata.pop('run_id', None)
            metadata.pop('artifact_id', None)
            failure_state = ('PENDING_REVIEW' if metadata.get('candidate_available') else self.failure_state(metadata, exc) if hasattr(self, 'failure_state') else
                'VALIDATION_FAILED' if metadata.get('failure_stage') == 'native_validation' else 'REQUEST_FAILED')
            metadata.update(state=failure_state,
                error=category or ('REQUEST_TIMEOUT' if isinstance(exc, (TimeoutError, httpx.TimeoutException)) else
                    'EXECUTION_INTERRUPTED' if isinstance(exc, asyncio.CancelledError) else 'REQUEST_OR_PERSISTENCE_FAILED'))
            try:
                name = 'failed.json' if (output / 'result.json').exists() else 'result.json'
                save_bytes(output / name, canonical(metadata))
            except Exception:
                pass  # A consumed reservation without a result can never resume.
        finally:
            self.active.discard(key)

    def selected(self):
        if not (self.root / 'selected.json').exists():
            return None
        key = read_json(self.root / 'selected.json')['binding_sha256']
        check(type(key) is str and len(key) == 64 and all(c in '0123456789abcdef' for c in key), 'LOCAL_RECORD_INVALID')
        result = read_json(self.root / key / 'result.json')
        check(result['state'] == 'SUCCEEDED' and result['mode'] == 'MOCK'
              and result['binding_sha256'] == key and result['production_authorized'] is False
              and not (self.root / key / 'failed.json').exists(), 'LOCAL_RECORD_INVALID')
        return self.root / key / 'history.sqlite3', result

    async def shutdown(self):
        tasks = tuple(self.tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
