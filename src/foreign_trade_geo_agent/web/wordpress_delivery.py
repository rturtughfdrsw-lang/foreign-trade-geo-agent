"""Offline delivery facade. The production candidate has no publisher capability.

Only fixed, independent synthetic samples enter the MockTransport composition.
TEST decisions are code fixtures, never trusted human signoff or production permits.
"""
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from html import escape
import hashlib
import json
from types import MappingProxyType
from uuid import uuid4

import httpx

from foreign_trade_geo_agent.adapters.wordpress_rest import WordPressRestDraftPublisher
from foreign_trade_geo_agent.core.change_plan import ChangeTargetKind, SectionLocator, SectionLocatorKind
from foreign_trade_geo_agent.core.content_draft import (
    CONTENT_DRAFT_LIMITATIONS, ContentDraftReport, ContentDraftStatus, ContentDraftType,
    DraftBlockKind, DraftClaim, DraftClaimSupportKind, DraftClaimType, DraftItem, ParagraphBlock,
)
from foreign_trade_geo_agent.core.content_draft_review import local_text_digest
from foreign_trade_geo_agent.core.history import ArtifactRecord, ArtifactType, RunStatus, WorkflowRun, site_key_from_url
from foreign_trade_geo_agent.core.wordpress_draft import build_wordpress_draft_request
from foreign_trade_geo_agent.storage.sqlite import SQLiteHistoryStore
from foreign_trade_geo_agent.storage.wordpress_mock import SQLiteWordPressMockJournal
from foreign_trade_geo_agent.web.mvp_application import MVPError
from foreign_trade_geo_agent.workflows.wordpress_delivery import WordPressDeliveryWorkflow

PROFILE = 'WORDPRESS_MOCK_TEST_ONLY_V1'
TARGET = 'https://wordpress-offline.example'
PATH = '/wp-json/wp/v2/posts'


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class MockSample:
    key: str
    label: str
    version: int
    body: str
    evidence: str
    response: str

    def draft(self):
        claim = DraftClaim('CL1', self.body, DraftClaimType.EDITORIAL_TRANSITION,
                           DraftClaimSupportKind.EXTERNAL_CONTEXT, (), ('S1',))
        return DraftItem('D1', 'C1', 'R1', ContentDraftType.NEW_RESOURCE_DRAFT,
                         ChangeTargetKind.CREATE_NEW_PAGE, None,
                         SectionLocator(SectionLocatorKind.NEW_PAGE, None, None, None, None),
                         'TEST ONLY — ' + self.label, (),
                         (ParagraphBlock(DraftBlockKind.PARAGRAPH, (claim,)),), (), ('S1',))

    def binding(self):
        request = build_wordpress_draft_request(self.draft())
        return dict(profile=PROFILE, sample=self.key, article_version=self.version,
                    body_sha256=local_text_digest(self.body), evidence_snapshot=self.evidence,
                    evidence_sha256=local_text_digest(self.evidence), target_site=TARGET,
                    method='POST', path=PATH,
                    request=dict(title=request.title, content=request.content, status='draft'),
                    mock_response=self.response, production_authorized=False)


_EVIDENCE = 'SYNTHETIC S1 v1: Independent API delivery fixture. No customer or product facts.'
_BODY = 'TEST ONLY: This independent synthetic article checks offline draft creation and persistence.'
_APPROVED = tuple(MockSample(key, label, 1, _BODY + ' Scenario: ' + key + '.', _EVIDENCE, response)
                  for key, label, response in (('success', '创建成功样本', 'success'),
                                               ('failure', 'API 拒绝样本', 'failure'),
                                               ('timeout', '响应不明样本', 'timeout')))
# Deliberately frozen independently from the selectable sample catalog. Changing
# article, evidence, target or response cannot inherit an earlier TEST decision.
_TEST_APPROVED_BINDINGS = frozenset(digest(sample.binding()) for sample in _APPROVED)
SAMPLES = MappingProxyType({s.key: s for s in (*_APPROVED,
    replace(_APPROVED[0], key='revised', label='正文已修改 v2（旧测试批准失效）', version=2,
            body=_BODY + ' Revised body without a new TEST review.'),
    replace(_APPROVED[0], key='evidence-changed', label='证据已更新（旧测试批准失效）',
            evidence=_EVIDENCE.replace('v1', 'v2') + ' New snapshot.'))})


class OfflineWordPressDelivery:
    def __init__(self, service):
        self.service = service
        self.root = service.directory / 'wordpress-mock'
        self.journal = SQLiteWordPressMockJournal(self.root / 'exchanges.sqlite3')

    def preview(self, version=None):
        article = self.service.article(version)
        review = article['review']
        binding = dict(profile='BLOCKED_ARTICLE_PREVIEW_V1',
                       run_id=review.planning_run_id, artifact_id=review.content_draft_artifact_id,
                       draft_id=review.draft.draft_id, article_version=article['selected_version'],
                       latest_version=article['latest_version'], origin_sha256=article['origin_sha256'],
                       body_sha256=local_text_digest(article['local_body']),
                       frozen_evidence_sha256=review.customer_evidence.snapshot_sha256,
                       current_evidence_sha256=article['expected_evidence_sha256'],
                       local_status=article['local_status'], validation_state=article['validation_state'],
                       target_site=None, production_authorized=False)
        blockers = ['QUALITY_NOT_APPROVED：文章质量尚未获得可信人工批准；当前本地状态为 ' + article['local_status'],
                    'TRUSTED_SIGNOFF_REQUIRED：本地审核和重新核验记录不是可信人工签核。',
                    'TEST_ONLY_EVIDENCE：当前客户证据仅供 TEST-only，原生 WordPress 构造器拒绝交付。',
                    'TARGET_NOT_AUTHORIZED：尚未配置并批准真实目标站点。',
                    'P1_GLOBAL_CONSUMPTION_BLOCKED：跨 journal 一次性消费未成立，生产交付入口保持硬阻断。']
        if article['candidate_mode'] == 'LIVE':
            blockers[0] = 'QUALITY_NEEDS_REVISION：真实 DeepSeek 候选尚需商业质量修订，未获人工签核。'
        if not article['version_matches'] or not article['matches']:
            blockers.insert(0, 'STALE_EVIDENCE：当前证据快照与文章冻结证据不一致，旧资格失效。')
        if article['selected_version'] != article['latest_version']:
            blockers.insert(0, 'HISTORICAL_VERSION：这是历史文章版本，不能继承当前版本资格。')
        if article['validation_state'] == 'PENDING_REVALIDATION':
            blockers.insert(0, 'REVALIDATION_REQUIRED：此正文版本尚未完成相应核验。')
        html = '\n'.join('<p>' + escape(part, quote=True).replace('\n', '<br>') + '</p>'
                         for part in article['local_body'].split('\n\n'))
        return dict(article=article, binding=binding, binding_sha256=digest(binding),
                    blockers=blockers, target='未配置 / 未授权（禁止从页面指定站点）',
                    preview_title=review.draft.heading, preview_html=html, delivery_allowed=False)

    def block_real(self, version, expected_binding):
        preview = self.preview(version)
        if preview['binding_sha256'] != expected_binding:
            raise MVPError('文章、摘要、证据或审核状态已改变；交付预览失效，请刷新。', 409)
        # No production publisher, signer, journal consumer or credentials here.
        raise MVPError('交付被阻断：' + '；'.join(preview['blockers']), 409)

    def test_preview(self, key='success'):
        if key not in SAMPLES:
            raise MVPError('未知 TEST-only 样本。', 422)
        sample = SAMPLES[key]
        binding = sample.binding()
        sha = digest(binding)
        try:
            records = self.journal.records()
        except Exception:
            raise MVPError('Mock 记录不可读取；禁止执行。', 503) from None
        record = next((r for r in records if r['claim']['binding_sha256'] == sha), None)
        approved = sha in _TEST_APPROVED_BINDINGS
        return dict(sample=sample, samples=SAMPLES.values(), binding=binding, binding_sha256=sha,
                    test_approved=approved, mock_allowed=approved and record is None,
                    record=record, records=records,
                    record_json=json.dumps(record, ensure_ascii=False, indent=2) if record else None,
                    mock_reason=('已有消费记录；成功、失败或中断均不自动重试。' if record else
                                 '正文、证据或版本已改变，旧 TEST-only 批准失效。' if not approved else
                                 '独立合成样本的固定 TEST-only 决定，仅在内置 MockTransport 生效。'))

    async def deliver_mock(self, key, expected_binding):
        preview = self.test_preview(key)
        if preview['binding_sha256'] != expected_binding:
            raise MVPError('Mock 版本、正文、证据或目标摘要已改变；旧预览失效。', 409)
        if not preview['test_approved']:
            raise MVPError(preview['mock_reason'], 409)
        binding, sha, sample = preview['binding'], preview['binding_sha256'], preview['sample']
        try:
            # Committed unique claim prevents reposts and cross-process duplicates
            # in this fixed isolated local journal. It does NOT repair production P1.
            if not self.journal.claim(sha, dict(binding, binding_sha256=sha)):
                return False
            history_path = self.root / sha / 'history.sqlite3'
            history_path.parent.mkdir(parents=True, exist_ok=True)
            history = SQLiteHistoryStore(history_path)
            run_id, artifact_id, now = str(uuid4()), str(uuid4()), datetime.now(UTC)
            history.create_run(WorkflowRun(run_id, site_key_from_url(TARGET), PROFILE,
                                          now, None, RunStatus.RUNNING, None, None))
            draft = sample.draft()
            report = ContentDraftReport(ContentDraftStatus.SUCCESS, (draft,), CONTENT_DRAFT_LIMITATIONS, None)
            history.append_artifact(ArtifactRecord(artifact_id, run_id, ArtifactType.CONTENT_DRAFT, 1, now, report))
            history.finish_run(run_id, status=RunStatus.SUCCEEDED, completed_at=datetime.now(UTC))

            def mock(request):
                # Observe only the bounded synthetic body, never headers/auth.
                payload = json.loads(request.content)
                if (request.method != 'POST' or str(request.url) != TARGET + PATH
                        or payload != binding['request'] or set(payload) != {'title', 'content', 'status'}
                        or payload['status'] != 'draft'):
                    raise ValueError('Mock request differs from frozen create-draft preview.')
                response = ({'id': 701, 'status': 'draft', 'link': TARGET + '/?p=701'}
                            if sample.response == 'success' else
                            {'code': 'test_rejection', 'message': 'Controlled TEST-only denial.'})
                status = 201 if sample.response == 'success' else 401
                self.journal.append(sha, 'exchange', dict(method=request.method, url=str(request.url),
                    body=payload, response_status=None if sample.response == 'timeout' else status,
                    response=None if sample.response == 'timeout' else response,
                    transport='httpx.MockTransport', real_network_requests=0))
                if sample.response == 'timeout':
                    raise httpx.ReadTimeout('Controlled TEST-only timeout.', request=request)
                return httpx.Response(status, json=response)

            transport = httpx.MockTransport(mock)
            # Always explicit placeholders; never read WORDPRESS_* or .env.
            publisher = WordPressRestDraftPublisher(base_url=TARGET, username='OFFLINE-PLACEHOLDER',
                application_password='OFFLINE-PLACEHOLDER', transport=transport)
            result = await WordPressDeliveryWorkflow(publisher=publisher, history_store=history).deliver(
                run_id, artifact_id, draft, TARGET)
            self.journal.append(sha, 'result', dict(status=result.status.value,
                attempt=asdict(result.attempt) | {'attempted_at': result.attempt.attempted_at.isoformat(),
                    'completed_at': result.attempt.completed_at.isoformat() if result.attempt.completed_at else None},
                real_network_requests=0, production_authorized=False))
            return True
        except Exception:
            # The committed claim remains consumed on crash/storage failure.
            raise MVPError('Mock 交付未能完整记录；消费记录保留，结果需核对，不允许重试。', 503) from None
