"""Local MVP application facade over native persisted planning and Intake.

Generation is disabled by default; a trusted local composition may inject the
isolated Mock executor. No crawl, production authority or CMS port is exposed.
"""
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from uuid import uuid4

from foreign_trade_geo_agent.core.content_draft_review import (
    ContentDraftReviewRequest, validate_local_review_text, MAX_LOCAL_BODY, local_text_digest,
)
from foreign_trade_geo_agent.core.draft_revalidation import revalidate_revision, LocalRevisionRevalidation
from foreign_trade_geo_agent.core.evidence_intake import (
    CustomerContext, CustomerSubmission, Supplement, SupplementMethod, MAX_TEXT,
    require, snapshot_digest, text,
)
from foreign_trade_geo_agent.core.history import ArtifactType, RunStatus
from foreign_trade_geo_agent.runtime import build_planning_evidence_workflow
from foreign_trade_geo_agent.reporting.content_draft_review import render_content_draft_review_markdown
from foreign_trade_geo_agent.storage.sqlite import SQLiteHistoryReader
from foreign_trade_geo_agent.storage.serialization import encode_artifact
from foreign_trade_geo_agent.storage.content_draft_review import SQLiteLocalDraftReviewStore, SQLiteLocalRevalidationStore
from foreign_trade_geo_agent.core.history import HistoryConflictError
from foreign_trade_geo_agent.web.presenters import AnalysisContextView, present_results, present_change_plan
from foreign_trade_geo_agent.workflows.content_draft_review import ContentDraftReviewWorkflow


class MVPError(ValueError):
    def __init__(self, message="本地演示资料不可用，请检查准备步骤；未授权任何执行。", status=503):
        super().__init__(message)
        self.status = status


class MVPApplicationService:
    def __init__(self, directory: Path):
        self.directory = Path(directory)
        from foreign_trade_geo_agent.web.generation import LocalGeneration
        self.generation_executor = None
        self.generation = LocalGeneration(self)
        self.generation_ticket = None
        self.scope_reviewer = None  # trusted composition only; never a form field
        from foreign_trade_geo_agent.web.article_scope import LocalArticleScope
        self.scope = LocalArticleScope(self)
        from foreign_trade_geo_agent.web.wordpress_delivery import OfflineWordPressDelivery
        self.delivery = OfflineWordPressDelivery(self)

    @property
    def ready(self):
        return (self.directory / "session.json").is_file()

    def _load(self):
        try:
            with (self.directory / "session.json").open("rb") as stream:
                raw = stream.read(8193)
            require(len(raw) <= 8192)
            session = json.loads(raw.decode("utf-8"))
            require(set(session) == {"profile", "project_id", "task_id", "candidate_run_id", "candidate_artifact_id"}
                    and session["profile"] == "SYNTHETIC_LOCAL_MVP_V1")
            history_path = self.directory / "candidate/history.sqlite3"
            store, planning, planner = build_planning_evidence_workflow(history_path,
                self.directory / "interactive-intake.sqlite3", run_id=session["project_id"], plan_id=session["task_id"])
            planning.bound_origin(session["project_id"], session["task_id"],
                                  store.get_revision(session["project_id"], session["task_id"], 1))
            session = self.scope.selected(store, session)
            return session, SQLiteHistoryReader(history_path), store, planning, planner
        except Exception:
            raise MVPError() from None

    @staticmethod
    def _current(store, session):
        try:
            return store.latest(session["project_id"], session["task_id"])
        except Exception:
            raise MVPError("当前任务版本不可读取；未修改资料。请检查本地保存结果。") from None

    def evidence(self):
        session, _, store, planning, _ = self._load()
        try:
            current = self._current(store, session)
            from foreign_trade_geo_agent.workflows.evidence_intake import EvidenceIntakeWorkflow
            checked_intake = EvidenceIntakeWorkflow(store, reviewer=self.scope_reviewer)
            request = checked_intake.customer_request(session["project_id"], session["task_id"], now=datetime.now(UTC))
            require(request.snapshot_sha256 == snapshot_digest(current))
            needs_customer = any(g.reason_code not in {"HUMAN_SEMANTIC_REVIEW_REQUIRED", "UNREVIEWED"} for g in request.gaps)
            state = ("RECHECK_REQUIRED" if not current.plan_bound else
                     "WAITING_FOR_EVIDENCE" if needs_customer else "WAITING_FOR_HUMAN_REVIEW")
            checks = store.checks(session['project_id'], session['task_id'], limit=1)
            check = checks[0]
            coverage = check.assessment.scope_coverage if check.assessment else None
            return {"state": state, "snapshot": current, "intake_request": request, "expected_sha256": request.snapshot_sha256,
                    "scope_coverage": coverage, "intake_check": check,
                    **self.scope.view(current)}
        except Exception:
            raise MVPError() from None

    def analysis(self):
        session, reader, store, planning, _ = self._load()
        try:
            original_session = json.loads((self.directory / 'session.json').read_text(encoding='utf-8'))
            request, value, refs = planning.origin(original_session["project_id"], original_session["task_id"])
            value = self._current(store, session).planning_input
            audit = reader.get_artifact(refs[ArtifactType.SITE_AUDIT.value]).payload
            context = AnalysisContextView("NovaCNC · 本地合成演示", request.website_url,
                                          request.seo_goal, request.target_language, False)
            return {"results": present_results(context=context, run_id=session["project_id"], audit=audit,
                        packet=value.site_content, opportunities=value.opportunity_report),
                    "changes": present_change_plan(context=context, run_id=session["project_id"],
                        packet=value.site_content, opportunities=value.opportunity_report, change_plan=value.change_plan_report),
                    "packet": value.site_content, "audit": audit}
        except Exception:
            raise MVPError() from None

    def submit(self, *, expected_sha256, content, source_label, requirement_id=None):
        # HTML textarea form serialization converts LF to CRLF. This interface
        # stores canonical LF text (and hashes those exact UTF-8 bytes), not an
        # uploaded file's original bytes. The UI discloses this normalization.
        content = content.replace("\r\n", "\n").replace("\r", "\n")
        if not text(content, MAX_TEXT) or not text(source_label, 200):
            raise MVPError("请输入有效的 UTF-8 文本及资料名称（正文最多 16,000 字符）。", 422)
        session, _, store, planning, _ = self._load()
        current = self._current(store, session)
        if snapshot_digest(current) != expected_sha256:
            raise MVPError("任务已更新，请刷新后重新提交。重复提交未保存。", 409)
        try:
            # Revisions append; replacements name the previous active source.
            active = current.active_evidence
            requirement_id = requirement_id or current.task.requirements[0].requirement_id
            require(requirement_id in {r.requirement_id for r in current.task.requirements})
            previous = next((e for e in reversed(active) if e.supplement.requirement_ids == (requirement_id,)), None)
            evidence_id = f"E{len(current.evidence) + 1}"
            supplement = Supplement(evidence_id, (requirement_id,), SupplementMethod.TEXT_DOCUMENT, content,
                source_label, f"local:customer/{evidence_id}/utf8-text", "LOCAL-OPERATOR-DECLARED-NOT-VERIFIED",
                hashlib.sha256(content.encode("utf-8")).hexdigest(), previous.supplement.evidence_id if previous else None)
            submission = CustomerSubmission(str(uuid4()), expected_sha256, (supplement,))
            planning.intake.submit(session["project_id"], session["task_id"], submission,
                customer=CustomerContext(current.task.customer_id, "LOCAL-WEB-OPERATOR-NOT-SIGNOFF", datetime.now(UTC)))
        except Exception:
            raise MVPError("资料未保存。请刷新任务，检查文本和版本后重试。", 409) from None

    async def recheck(self, *, expected_sha256):
        session, _, store, planning, planner = self._load()
        current = self._current(store, session)
        if snapshot_digest(current) != expected_sha256:
            raise MVPError("任务已更新，请刷新后重新核对。", 409)
        try:
            await planning.recheck(session["project_id"], session["task_id"], expected_sha256=expected_sha256,
                current=current, planner=planner, now=datetime.now(UTC))
        except Exception:
            raise MVPError("重新核对未完成；已保存资料仍保留。请刷新后重试。", 409) from None

    def _original_article(self):
        session, reader, store, _, _ = self._load()
        try:
            selected = self.generation.selected()
            generated_from_web = selected is not None
            if selected:
                history_path, result = selected
                reader = SQLiteHistoryReader(history_path)
                session = dict(session, candidate_run_id=result['run_id'], candidate_artifact_id=result['artifact_id'])
            run = reader.get_run(session["candidate_run_id"])
            experiment = run.workflow_name == "isolated_e_only_article_experiment"
            require(run.workflow_name in {"synthetic_e_only_native_draft_TEST_ONLY",
                    "isolated_e_only_article_experiment", "isolated_web_mock_content_draft",
                    "isolated_frozen_web_content_draft_TEST_ONLY"} and run.status is RunStatus.SUCCEEDED)
            review = ContentDraftReviewWorkflow(history_reader=reader).review(ContentDraftReviewRequest(
                session["candidate_run_id"], session["candidate_artifact_id"], "D1"))
            require(review.customer_evidence is not None
                    and review.customer_evidence.review_status == "TEST_ONLY_SUPPORTED_NOT_HUMAN_SIGNOFF"
                    and review.customer_evidence.project_id == session["project_id"]
                    and review.customer_evidence.task_id == session["task_id"])
            current = self._current(store, session)
            sources = review.customer_evidence.sources
            matches = bool(current.active_evidence) and tuple(e.supplement.content for e in current.active_evidence) == tuple(s.content for s in sources)
            version_matches = snapshot_digest(current) == review.customer_evidence.snapshot_sha256
            candidate_mode = "FIXTURE"
            if generated_from_web:
                candidate_mode = result['mode']
            if experiment:
                with (self.directory / "candidate/diagnostics.json").open("rb") as stream:
                    raw = stream.read(8193)
                require(len(raw) <= 8192)
                diagnostics = json.loads(raw)
                require(diagnostics["status"] == "SUCCESS" and diagnostics["run_id"] == run.run_id
                        and diagnostics["artifact_id"] == session["candidate_artifact_id"]
                        and diagnostics["mode"] in {"MOCK", "LIVE"}
                        and diagnostics["model_generated"] is (diagnostics["mode"] == "LIVE")
                        and diagnostics["production_authorized"] is False)
                candidate_mode = diagnostics["mode"]
            body_parts = review.draft.body_text.split("\n\n")
            if body_parts and body_parts[0] == review.draft.heading:
                body_parts = body_parts[1:]
            artifact = reader.get_artifact(session["candidate_artifact_id"])
            origin = "\n".join((run.run_id, artifact.artifact_id, "D1", str(artifact.payload_version),
                encode_artifact(artifact.artifact_type, artifact.payload, payload_version=artifact.payload_version)))
            return {"review": review, "matches": matches, "has_evidence": bool(current.active_evidence),
                    "body_parts": body_parts, "candidate_mode": candidate_mode,
                    "generated_from_web": generated_from_web, "native_draft": artifact.payload.drafts[0],
                    "version_matches": version_matches,
                    "origin_sha256": hashlib.sha256(origin.encode("utf-8")).hexdigest(),
                    "expected_evidence_sha256": snapshot_digest(current)}
        except Exception:
            raise MVPError("已保存的合成候选不可用；当前任务资料未改变。") from None

    @staticmethod
    def _version(value):
        if value is None:
            return None
        if type(value) is not str or not value.isascii() or not value.isdecimal() or len(value) > 3:
            raise MVPError("文章版本无效。", 422)
        return int(value)

    def article(self, version=None, *, revalidate=False):
        selected = self._version(version)
        result = self._original_article()
        try:
            history = SQLiteLocalDraftReviewStore(self.directory / "local-draft-review.sqlite3").revisions(result["origin_sha256"])
        except Exception:
            raise MVPError("本地审核记录不可读取；原始候选保留，请检查本地数据库。") from None
        if selected is None:
            selected = len(history)
        if selected > len(history):
            raise MVPError("未找到该文章版本。", 404)
        record = history[selected - 1] if selected else None
        body = record.body_text if record else result["review"].draft.body_text
        pending = not result["version_matches"] or bool(record and record.validation_state == "PENDING_REVALIDATION")
        status = record.status if record else "PENDING_REVIEW"
        if record and record.observed_evidence_sha256 != result["expected_evidence_sha256"]:
            status = "PENDING_REVIEW"
        result.update(local_history=history, selected_revision=record, selected_version=selected,
            latest_version=len(history), local_body=body, local_note=record.note if record else "",
            local_status=status, validation_state="PENDING_REVALIDATION" if pending else "HISTORICAL_NATIVE_VALIDATION",
            body_changed=body != result["review"].draft.body_text,
            body_parts=body.split("\n\n"))
        try:
            records = self._revalidation_store().records(result['origin_sha256'])
            selected_records = tuple(r for r in records if r.report.version == selected)
            matching_record = next((r for r in reversed(selected_records)
                if r.report.body_sha256 == local_text_digest(body)
                and r.report.evidence_sha256 == result['expected_evidence_sha256']
                and r.report.origin_sha256 == result['origin_sha256']), None)
            valid = matching_record if matching_record and matching_record.report.eligible and matching_record.decision == 'CONFIRMED' else None
            report = self._revalidation_report(result) if revalidate and record else None
            result.update(revalidation_records=selected_records, revalidation_record=valid,
                          revalidation_report=report or (selected_records[-1].report if selected_records else None),
                          revalidation_form_available=bool(report))
            if valid:
                result['validation_state'] = 'LOCAL_REVALIDATION_COMPLETE'
            elif selected_records:
                result['validation_state'] = 'PENDING_REVALIDATION'
        except Exception:
            raise MVPError('本地重新核验记录不可读取；原文和修订保留。') from None
        return result

    def _revalidation_store(self):
        return SQLiteLocalRevalidationStore(self.directory / 'local-draft-revalidation.sqlite3')

    def _revalidation_report(self, article):
        session, reader, store, _, _ = self._load()
        current = self._current(store, session)
        draft = article['native_draft']
        return revalidate_revision(article['review'], article['selected_revision'], current, draft,
                                   latest_version=article['latest_version'])

    def save_revalidation(self, *, version, origin_sha256, body_sha256, expected_evidence_sha256,
                          report_sha256, note, confirmed, decision):
        note = note.replace('\r\n', '\n').replace('\r', '\n')
        if not text(note, 2000) or confirmed != 'yes' or decision not in {'CONFIRMED', 'ISSUES_FOUND'}:
            raise MVPError('请填写人工复核意见，并确认已逐项核对全文、来源、条件和适用范围。', 422)
        selected = self._version(version)
        if not selected:
            raise MVPError('请先保存一个文章修订版本。', 422)
        try:
            _, _, intake_store, _, _ = self._load()
            with (SQLiteLocalDraftReviewStore(self.directory / 'local-draft-review.sqlite3').version_guard(),
                  intake_store.snapshot_guard()):
                article = self.article(version, revalidate=True)
                report = article['revalidation_report']
                if (origin_sha256 != article['origin_sha256'] or body_sha256 != report.body_sha256
                        or expected_evidence_sha256 != article['expected_evidence_sha256']
                        or report_sha256 != report.sha256):
                    raise MVPError('文章、证据或核验结果已更新；请重新发起此版本核验。本次意见未保存。', 409)
                self._revalidation_store().append(LocalRevisionRevalidation(report, note, True, decision, datetime.now(UTC)))
        except MVPError:
            raise
        except HistoryConflictError:
            raise MVPError('此核验结果已保存或达到记录上限；请查看版本对应记录。', 409) from None
        except Exception:
            raise MVPError('重新核验记录未保存；原文和修订保留。') from None

    def save_article(self, *, expected_version, origin_sha256, expected_evidence_sha256, body_text, note, status):
        body_text = body_text.replace("\r\n", "\n").replace("\r", "\n")
        note = note.replace("\r\n", "\n").replace("\r", "\n")
        if len(body_text) > MAX_LOCAL_BODY:
            raise MVPError("文章过长，最多 16,000 字符。", 413)
        try:
            validate_local_review_text(body_text, note, status)
        except ValueError:
            raise MVPError("请输入有效正文、审核状态和意见（意见最多 2,000 字符）。", 422) from None
        version = self._version(expected_version)
        current = self.article()
        if (version is None or origin_sha256 != current["origin_sha256"]
                or expected_evidence_sha256 != current["expected_evidence_sha256"]):
            raise MVPError("原始文章或任务证据已更新，请刷新后核对；本次输入未保存。", 409)
        try:
            return SQLiteLocalDraftReviewStore(self.directory / "local-draft-review.sqlite3").append(
                origin_sha256=origin_sha256, expected_version=version, original_body=current["review"].draft.body_text,
                body_text=body_text, note=note, status=status,
                frozen_evidence_sha256=current["review"].customer_evidence.snapshot_sha256,
                observed_evidence_sha256=current["expected_evidence_sha256"], saved_at=datetime.now(UTC))
        except HistoryConflictError:
            raise MVPError("文章已在其他页面保存或达到 100 次保存上限；请先核对最新版本。本次输入未保存。", 409) from None
        except Exception:
            raise MVPError("本地修订未保存；原始候选保留，请检查本地数据库。") from None

    def sample_text(self):
        # Read the exact frozen source rather than duplicate the E-only fact.
        session, _, store, _, _ = self._load()
        current = self._current(store, session)
        if current.active_evidence:
            return current.active_evidence[0].supplement.content
        return self.article()["review"].customer_evidence.sources[0].content

    def require_generation_scope(self, current):
        from foreign_trade_geo_agent.workflows.evidence_intake import EvidenceIntakeWorkflow
        from foreign_trade_geo_agent.core.evidence_intake import IntakeStatus
        session, _, store, _, _ = self._load()
        result = EvidenceIntakeWorkflow(store, reviewer=self.scope_reviewer).check(
            session['project_id'], session['task_id'], now=datetime.now(UTC))
        if result.snapshot_sha256 != snapshot_digest(current) or result.status is not IntakeStatus.CANDIDATE_FOR_REVIEW:
            raise ValueError(result.reason or 'ARTICLE_SCOPE_REVIEW_REQUIRED')
        return result.assessment

    def markdown(self, version=None):
        article = self.article(version)
        prefix = {"FIXTURE": "",
            "MOCK": "> MockTransport / hand-written fixture; NOT a real model article. SYNTHETIC / UNREVIEWED.\n\n",
            "LIVE": "> DeepSeek isolated experiment candidate. SYNTHETIC / UNREVIEWED; no production authority.\n\n"}
        if article["selected_version"] == 0:
            return prefix[article["candidate_mode"]] + render_content_draft_review_markdown(article["review"])
        from foreign_trade_geo_agent.reporting.content_draft_review import render_local_draft_review_markdown
        return prefix[article["candidate_mode"]] + render_local_draft_review_markdown(
            article["review"], article["selected_revision"], validation_state=article["validation_state"],
            local_status=article["local_status"], revalidation_records=article['revalidation_records'])
