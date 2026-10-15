"""Local scope requests; only an injected TEST proposal can create a child task.

No customer identity, semantic verdict or production authority comes from HTML.
The original task is never updated. Native Intake owns child versions/replan.
"""
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from foreign_trade_geo_agent.core.content_draft import ContentDraftInput
from foreign_trade_geo_agent.core.evidence_intake import (
    CustomerContext, CustomerSubmission, EvidenceTask, snapshot_digest, require, text,
)
from foreign_trade_geo_agent.storage.serialization import _encode
from foreign_trade_geo_agent.web.generation import canonical, read_json, digest


@dataclass(frozen=True)
class TestScopeProposal:
    """Analyst-prepared local fixture, never decoded from a customer form."""
    parent_snapshot_sha256: str
    task: EvidenceTask
    planning_input: ContentDraftInput


class LocalArticleScope:
    def __init__(self, service):
        self.service = service
        self.test_proposal = None

    @property
    def root(self):
        return self.service.directory / 'scope-requests'

    def view(self, current):
        key = snapshot_digest(current)
        path = self.root / (key + '.json')
        request = read_json(path, 8192) if path.exists() else None
        proposal = self.test_proposal
        return {'scope_request': request,
                'test_scope_proposal': proposal if proposal and proposal.parent_snapshot_sha256 == key else None,
                'scope_lineage': read_json(self.root / 'selected.json', 100_000)
                    if (self.root / 'selected.json').exists() else None}

    def request(self, expected_sha256, goal, reason):
        from .mvp_application import MVPError
        if not text(goal) or not text(reason):
            raise MVPError('请填写拟调整的文章目标和原因（各最多 1,000 字符）。', 422)
        session, _, store, _, _ = self.service._load()
        current = self.service._current(store, session)
        with store.snapshot_guard():
            if snapshot_digest(store.latest(current.task.project_id, current.task.task_id)) != expected_sha256:
                raise MVPError('任务已更新；请刷新后重新请求范围调整。', 409)
            self.root.mkdir(exist_ok=True)
            path = self.root / (expected_sha256 + '.json')
            record = {'state': 'SCOPE_REQUESTED_REPLAN_AND_CONFIRMATION_REQUIRED',
                'parent_snapshot_sha256': expected_sha256, 'parent_task_id': current.task.task_id,
                'parent_revision': current.revision, 'requested_goal': goal, 'reason': reason,
                'recorded_at': datetime.now(UTC).isoformat(), 'customer_consented': False,
                'production_authorized': False}
            try:
                require(len(list(self.root.iterdir())) < 40)
                with path.open('xb') as stream:
                    stream.write(canonical(record))
            except FileExistsError:
                old = read_json(path)
                if old['requested_goal'] != goal or old['reason'] != reason:
                    raise MVPError('当前版本已有范围请求；请先处理该请求。', 409) from None

    async def confirm_test(self, expected_sha256, confirmed):
        from .mvp_application import MVPError
        if confirmed != 'TEST_ONLY_SIMULATED_CONSENT':
            raise MVPError('必须明确勾选 TEST-only 模拟同意；此操作不记录正式客户同意。', 422)
        proposal = self.test_proposal
        if proposal is None or proposal.parent_snapshot_sha256 != expected_sha256:
            raise MVPError('未配置匹配当前版本的独立 TEST-only 范围提案。', 409)
        session, _, store, planning, planner = self.service._load()
        parent = self.service._current(store, session)
        request_path = self.root / (expected_sha256 + '.json')
        try:
            requested = read_json(request_path)
            require(snapshot_digest(parent) == expected_sha256
                    and requested['requested_goal'] == proposal.task.goal
                    and requested['parent_task_id'] == parent.task.task_id
                    and proposal.task.project_id == parent.task.project_id
                    and proposal.task.customer_id == parent.task.customer_id
                    and proposal.task.task_id != parent.task.task_id)
            child = planning.intake.register(proposal.task, proposal.planning_input)
            # Exact sources only; unretained or unreviewed supplements are never
            # invented or remapped. Child still requires its own semantic review.
            ids = {r.requirement_id for r in proposal.task.requirements}
            # Preserve replacement ancestry too: an active E2 may supersede E1.
            # Copying E2 alone would leave a dangling reference in the child.
            evidence = tuple(e.supplement for e in parent.evidence
                             if set(e.supplement.requirement_ids) <= ids)
            # Intake replacements must reference an already persisted source.
            for supplement in evidence:
                child = planning.intake.submit(child.task.project_id, child.task.task_id,
                    CustomerSubmission(str(uuid4()), snapshot_digest(child), (supplement,)),
                    customer=CustomerContext(child.task.customer_id,
                        'TEST-ONLY-SIMULATED-CONSENT-NOT-CUSTOMER', datetime.now(UTC)))
            if evidence:
                child = (await planning.intake.replan(child.task.project_id, child.task.task_id,
                    expected_sha256=snapshot_digest(child), planner=planner, now=datetime.now(UTC))).snapshot
            require(snapshot_digest(store.latest(parent.task.project_id, parent.task.task_id)) == expected_sha256)
            initial = store.get_revision(child.task.project_id, child.task.task_id, 1)
            operation = child.planning_input.change_plan_report.operations[0]
            lineage = {'mode': 'TEST_ONLY_SIMULATED_CONSENT', 'customer_consented': False,
                'production_authorized': False, 'parent_task_id': parent.task.task_id,
                'parent_revision': parent.revision, 'parent_snapshot_sha256': expected_sha256,
                'task_id': child.task.task_id, 'initial_snapshot_sha256': snapshot_digest(initial),
                'task_goal': child.task.goal, 'plan_title': (operation.new_resource_spec.proposed_title
                    if operation.new_resource_spec else operation.locator.observed_heading),
                'new_snapshot_sha256': snapshot_digest(child), 'old_approval_transferred': False,
                'initial_snapshot': _encode(initial)}
            # Selection is the final step. A failed attempt cannot select a
            # partial child and cannot mutate the parent task or grant authority.
            with store.snapshot_guard():
                require(snapshot_digest(store.latest(parent.task.project_id, parent.task.task_id)) == expected_sha256)
                with (self.root / 'selected.json').open('xb') as stream:
                    stream.write(canonical(lineage))
            self.service.generation_ticket = None
        except Exception:
            raise MVPError('范围模拟确认未完成或版本已过期；旧任务保留，未授权生成。', 409) from None

    def selected(self, store, session):
        path = self.root / 'selected.json'
        if not path.exists():
            return session
        record = read_json(path, 100_000)
        require(record['mode'] == 'TEST_ONLY_SIMULATED_CONSENT' and record['customer_consented'] is False
                and record['production_authorized'] is False and record['old_approval_transferred'] is False
                and record['parent_task_id'] == session['task_id'])
        parent = store.get_revision(session['project_id'], session['task_id'], record['parent_revision'])
        initial = store.get_revision(session['project_id'], record['task_id'], 1)
        require(snapshot_digest(parent) == record['parent_snapshot_sha256']
                and snapshot_digest(initial) == record['initial_snapshot_sha256']
                and _encode(initial) == record['initial_snapshot']
                and initial.task.goal == record['task_goal'])
        return dict(session, task_id=record['task_id'])
