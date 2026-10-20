"""Read-only workflow inspection with separate, non-authorizing local feedback."""
from contextlib import closing
from dataclasses import asdict
from datetime import date, datetime
from enum import Enum
import hashlib
import hmac
import html
import json
import os
from pathlib import Path
import re
import sqlite3
import secrets
import time
from urllib.parse import parse_qs
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from foreign_trade_geo_agent.evidence_review_composition import ProductionDraftAdmission
from foreign_trade_geo_agent.storage.sqlite import SQLiteHistoryReader
from foreign_trade_geo_agent.storage.serialization import encode_artifact
from foreign_trade_geo_agent.storage.evidence_intake import SQLiteEvidenceIntakeStore
from foreign_trade_geo_agent.core.developer_feedback import FeedbackBinding, validate_feedback
from foreign_trade_geo_agent.core.history import ArtifactType, validate_uuid
from foreign_trade_geo_agent.core.content_draft_review import render_draft_body_text
from foreign_trade_geo_agent.storage.developer_feedback import SQLiteDeveloperFeedbackStore
from foreign_trade_geo_agent.web.request_integrity import validate_local_mutation, RequestIntegrityError

MAX_VIEW = 256 * 1024


def report_catalog(project, worktrees):
    phase6 = worktrees/'phase6-e2e/foreign-trade-geo-agent'
    capture = phase6/'docs/e2e-mvp-phase6/phase6-20261014T072047Z'
    return {
        'intake-baseline': project/'.data/seo-mvp/candidate/02-unreviewed-intake.json',
        'evidence-source': project/'.data/seo-mvp/candidate/customer-E1.txt',
        'evidence-binding': project/'.data/seo-mvp/candidate/07-evidence-binding.json',
        'draft-review': project/'.data/seo-mvp/candidate/06-review.json',
        'sufficiency': project/'docs/evidence-sufficiency-positive-candidate-report-2026-10-08.md',
        'phase7-admission': phase6/'docs/evidence-bound-draft-admission-phase7a1/preflight-report.json',
        'phase7-admission-report': phase6/'docs/evidence-bound-draft-admission-phase7a1/report.md',
        'phase7a6-live': project/'docs/real-llm-draft-phase7a6/live-report.md',
        'claim-audit': project/'docs/draft-claim-audit-phase7b/report.md',
        'claim-audit-replay': project/'docs/draft-claim-audit-phase7b/historical-replay.json',
        'editorial-review': phase6/'docs/editorial-review-v1/report.md',
        'human-review': phase6/'docs/editorial-human-review-v1/report.md',
        'phase6-review': capture/'editorial-review-v2.json',
        'phase6-human': capture/'human-review-v2.json',
        'phase6-manifest': capture/'run-manifest-v2.json',
        **{f'evidence-{i:03d}': capture/f'Evidence-{i:03d}.json' for i in range(1,5)},
        'explain-latest': worktrees/'explain-offline-diagnosis/foreign-trade-geo-agent/docs/explain-final-offline-quality-2026-10-10/report.md',
    }


def _safe_text(value):
    value = re.sub(r'\bsk-[A-Za-z0-9_-]{24,}|\bgh[pousr]_[A-Za-z0-9]{24,}|(?i:Bearer\s+)[A-Za-z0-9._-]{16,}',
                   '[REDACTED]', value)
    return value


def _json(value):
    def default(item):
        if isinstance(item, Enum):
            return item.value
        if isinstance(item, (date, datetime)):
            return item.isoformat()
        raise TypeError('Unsupported view value')
    return json.dumps(value,ensure_ascii=False,indent=2,default=default)


def create_commercial_app(project_root: Path, *, worktrees_root: Path | None = None, instance='manual'):
    project = Path(project_root).resolve()
    worktrees = Path(worktrees_root).resolve() if worktrees_root else Path.home()/'.codex/worktrees'
    databases = {'candidate': project/'.data/seo-mvp/candidate/history.sqlite3',
                 'live': project/'.data/live-ui/history.sqlite3'}
    reports = report_catalog(project,worktrees)
    feedback = SQLiteDeveloperFeedbackStore(project/'.data/commercial-feedback/feedback.sqlite3')
    csrf_token = secrets.token_hex(32)
    signing_key = secrets.token_bytes(32)
    app = FastAPI(title='SEO Agent - Commercial Dev',docs_url=None,redoc_url=None,openapi_url=None)
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=['127.0.0.1','localhost'])
    # Isolated offline Preview; never opens or writes the inspector's business history.
    from foreign_trade_geo_agent.commercial_preview_runtime import build_preview_runtime
    from foreign_trade_geo_agent.web.commercial_preview import create_preview_app
    app.mount('/preview', create_preview_app(build_preview_runtime(project/'.data/commercial-preview')))

    def page(title, content, status=200):
        body = '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
        body += '<title>SEO Agent - Commercial Dev</title><style>body{font:16px/1.65 system-ui;margin:30px auto;max-width:1100px;padding:0 22px;color:#183747;background:#f3f6f7}section,pre{background:white;padding:18px;border-radius:10px;overflow-wrap:anywhere}pre{white-space:pre-wrap}a{color:#006d77}li{margin:8px 0}table{border-collapse:collapse}td,th{padding:9px;border:1px solid #ccc}</style>'
        body += '<nav><a href="/">开发状态</a> · <a href="/history">历史 Run / Source</a> · <a href="/intake">Evidence Intake</a> · <a href="/reports">Phase7 / 审核报告</a> · <a href="/preview/">离线 Commercial Preview</a></nav>'
        body += '<p><strong>Commercial Dev · LOCAL_DEVELOPER_FEEDBACK · TEST ONLY</strong> — 历史只读，反馈独立追加保存；不生成、不签核、不发布。Trust Layer 尚未通过生产级验收。</p>'
        body += '<h1>'+html.escape(title)+'</h1>'+content+'</html>'
        return HTMLResponse(body,status_code=status,headers={'Cache-Control':'no-store','Content-Security-Policy':
            "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'",
            # Chromium form POSTs use Origin: null under no-referrer, even locally.
            # Preserve same-origin metadata while withholding cross-origin referrers.
            'X-Content-Type-Options':'nosniff','Referrer-Policy':'same-origin'})

    def pre(value):
        return '<pre>'+html.escape(_safe_text(value[:MAX_VIEW]))+('</pre><p>显示已截断</p>' if len(value)>MAX_VIEW else '</pre>')

    def db_path(key):
        if key not in databases:
            raise HTTPException(404,'Unknown database')
        return databases[key]

    def review_object(database, run_id, object_id):
        """Re-read validated history on GET and POST, enforcing Run ownership."""
        try:
            validate_uuid(run_id, 'run_id')
            reader = SQLiteHistoryReader(db_path(database))
            run = reader.get_run(run_id)
            if run is None:
                raise ValueError
            if object_id == 'run':
                version, title, value = 1, '运行记录', asdict(run)
            else:
                validate_uuid(object_id, 'object_id')
                artifact = reader.get_artifact(object_id)
                if artifact is None or artifact.run_id != run_id:
                    raise ValueError
                version, title = artifact.payload_version, artifact.artifact_type.value
                value = json.loads(encode_artifact(artifact.artifact_type, artifact.payload, payload_version=version))
            canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'),
                                   default=lambda x: x.value if isinstance(x, Enum) else x.isoformat())
            binding = FeedbackBinding(database, run_id, object_id, version,
                                      hashlib.sha256(canonical.encode('utf8')).hexdigest())
            return binding, title, _json(value)
        except (ValueError, TypeError, OSError, RuntimeError):
            raise HTTPException(404, 'NOT_AVAILABLE: Run/object missing or unsupported') from None

    def ticket(binding, submission_id, expires):
        message = json.dumps([asdict(binding), submission_id, expires], sort_keys=True).encode('utf8')
        return hmac.new(signing_key, message, hashlib.sha256).hexdigest()

    def review_url(binding):
        return '/runs/'+binding.database+'/'+binding.run_id+'/review/'+binding.object_id

    def review_link(database, run_id, object_id, label='查看并记录开发反馈'):
        return '<a href="/runs/'+database+'/'+run_id+'/review/'+object_id+'">'+html.escape(label)+'</a>'

    @app.get('/_desktop/status')
    async def status():
        return JSONResponse({'instance':instance,'pid':os.getpid(),'profile':'commercial',
            'project':str(project),'database':str(databases['candidate']),
            'source':str(Path(__file__).resolve()),'live_model_enabled':False,'paid_confirmation_required':False},
            headers={'Cache-Control':'no-store'})

    @app.get('/')
    async def home():
        denial = ProductionDraftAdmission().rejection_reason(None)
        content = '<section><p>工作目录：'+html.escape(str(project))+'</p>'
        content += '<p>Production Draft Admission：<strong>'+html.escape(denial)+'</strong></p>'
        content += '<p>Evidence Sufficiency：离线实现及历史记录可检查；可信生产授权未开放。</p>'
        content += '<p>Claim Audit / Editorial Review：历史报告只读；已支持 Run / artifact 开发反馈。正式签核 NOT_IMPLEMENTED，缺失记录标记 NOT_AVAILABLE。</p>'
        content += '<p>VDemo 未审核文章不会导入此开发线，也不会被视为可信文章。</p></section>'
        content += '<h2>开发模块位置</h2><ul>'
        modules = {'Evidence Intake':'core/evidence_intake.py','Evidence Sufficiency':'core/evidence_sufficiency.py',
                   'Production Admission':'evidence_review_composition.py','Claim Audit':'../../../docs/draft-claim-audit-phase7b/claim_audit.py'}
        for label, relative in modules.items():
            path = project/'src/foreign_trade_geo_agent'/relative
            if label=='Claim Audit':
                path=project/'docs/draft-claim-audit-phase7b/claim_audit.py'
            content += '<li>'+html.escape(label+': '+('SOURCE_PRESENT' if path.is_file() else 'NOT_AVAILABLE')+' · '+str(path))+'</li>'
        return page('SEO Agent - Commercial Dev',content+'</ul>')

    @app.get('/history')
    async def history(db: str = 'candidate'):
        path = db_path(db)
        content='<p>只读数据库：'+html.escape(str(path))+'</p><p><a href="/history?db=candidate">合成 MVP</a> · <a href="/history?db=live">原 Live 历史</a></p>'
        try:
            if not path.is_file():
                raise ValueError
            with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as connection:
                connection.execute('PRAGMA query_only=ON')
                ids=connection.execute('SELECT run_id FROM runs ORDER BY started_at DESC LIMIT 40').fetchall()
            reader=SQLiteHistoryReader(path)
            content+='<ul>'
            for (run_id,) in ids:
                run=reader.get_run(run_id)
                content+='<li><a href="/runs/'+db+'/'+run_id+'">'+html.escape(run_id)+'</a> · '+html.escape(run.status.value+' · '+run.workflow_name)+'</li>'
            content+='</ul>' if ids else '</ul><p>NOT_AVAILABLE：没有已保存 Run。</p>'
        except Exception:
            content+='<p>NOT_AVAILABLE：没有可读取的受支持历史记录。</p>'
        return page('已保存运行记录',content)

    @app.get('/runs/{database}/{run_id}')
    async def run_view(database: str,run_id: str):
        try:
            reader=SQLiteHistoryReader(db_path(database))
            run=reader.get_run(run_id)
            if run is None:
                raise ValueError
            artifacts=reader.list_artifacts(run_id,limit=40)
            content=pre(_json(asdict(run)))+review_link(database,run_id,'run','记录本 Run 的开发意见')
            content+='<h2>Evidence / Source / Draft artifacts</h2><p>以下对象均属于当前 Run。适用范围、来源版本、证据缺口只显示原记录字段；未记录的字段为 NOT_AVAILABLE。</p><ul>'
            for artifact in artifacts:
                content+='<li><a href="/artifacts/'+database+'/'+artifact.artifact_id+'">'+html.escape(
                    artifact.artifact_type.value+' · '+artifact.artifact_id)+'</a> · version '+str(artifact.payload_version)+' · '+review_link(database,run_id,artifact.artifact_id)+'</li>'
            content+='</ul><h2>文章状态</h2>'
            drafts=[a for a in artifacts if a.artifact_type==ArtifactType.CONTENT_DRAFT]
            if not drafts:
                content+='<p>Draft NOT_AVAILABLE：当前展示范围没有已保存文章；Run 错误见上方原始记录。Production Gate：'+html.escape(ProductionDraftAdmission().rejection_reason(None))+'</p>'
            for artifact in drafts:
                content+='<p>已保存 Draft 报告状态：'+html.escape(artifact.payload.status.value)+'</p>'
                if not artifact.payload.drafts:
                    content+='<p>Draft NOT_AVAILABLE：报告没有文章；以上为原始保存状态，未推断额外失败原因。</p>'
                    content+=pre(_json({'error':artifact.payload.error,'limitations':artifact.payload.limitations}))
                    content+=review_link(database,run_id,artifact.artifact_id)
                    continue
                content+='<p>已保存 Draft（不构成可信批准）：'+review_link(database,run_id,artifact.artifact_id)+'</p>'
                for draft in artifact.payload.drafts:
                    content+='<h3>'+html.escape(draft.heading or draft.draft_id)+'</h3>'+pre(render_draft_body_text(draft))
            return page('Run '+run_id,content)
        except Exception:
            return page('Run NOT_AVAILABLE','<p>记录不存在或未通过当前 codec 校验；未改写历史数据。</p>',404)

    @app.get('/artifacts/{database}/{artifact_id}')
    async def artifact_view(database: str,artifact_id: str):
        try:
            artifact=SQLiteHistoryReader(db_path(database)).get_artifact(artifact_id)
            if artifact is None:
                raise ValueError
            raw=encode_artifact(artifact.artifact_type,artifact.payload,payload_version=artifact.payload_version)
            return page('已验证 artifact '+artifact_id,review_link(database,artifact.run_id,artifact_id)+pre(_json(json.loads(raw))))
        except Exception:
            return page('Artifact NOT_AVAILABLE','<p>记录不存在或当前契约不支持读取；没有绕过验证。</p>',404)

    @app.get('/runs/{database}/{run_id}/review/{object_id}')
    async def feedback_view(database: str, run_id: str, object_id: str):
        binding, title, raw = review_object(database, run_id, object_id)
        content='<p><a href="/runs/'+database+'/'+run_id+'">返回当前 Run / 关联来源与文章</a></p>'
        content+='<p>LOCAL_DEVELOPER_FEEDBACK：本地开发意见，不构成可信签名、正式批准、Production Authorization、Gate GREEN 或可发布状态。请勿填写密钥或个人敏感资料。</p>'
        content+=pre(_json(asdict(binding)))+pre(raw)
        try:
            rows=feedback.list(binding)
        except (sqlite3.Error,OSError):
            return page('反馈存储不可用',content+'<p>未能读取历史意见；未报告保存成功。</p>',503)
        content+='<h2>已保存开发意见（最多显示最近 100 条）</h2>'
        for row in rows:
            state='当前版本' if row['version']==binding.version and row['digest']==binding.digest else '历史版本，不能应用到当前对象'
            content+='<section><p>'+html.escape(row['created_at']+' · '+row['disposition']+' · '+state)+'</p>'
            content+=pre(_json(row))+'</section>'
        if not rows:
            content+='<p>尚无开发反馈。</p>'
        submission_id, expires = str(uuid4()), str(int(time.time())+3600)
        fields={'csrf_token':csrf_token,'version':str(binding.version),'digest':binding.digest,
                'submission_id':submission_id,'expires':expires,'ticket':ticket(binding,submission_id,expires)}
        content+='<h2>追加开发反馈</h2><form method="post" action="'+review_url(binding)+'">'
        for key,value in fields.items():
            content+='<input type="hidden" name="'+key+'" value="'+html.escape(value,quote=True)+'">'
        content+='<p><label>意见类型 <select name="disposition"><option value="needs_revision">需要修改</option><option value="observation">观察意见</option></select></label></p>'
        content+='<p><label>需修改的内容或位置（可选，最多 2000 字）<br><textarea name="marked_text" maxlength="2000" rows="3" cols="70"></textarea></label></p>'
        content+='<p><label>审核意见（必填，最多 2000 字）<br><textarea name="note" required maxlength="2000" rows="5" cols="70"></textarea></label></p>'
        content+='<button type="submit">保存本地开发意见（不批准）</button></form>'
        return page(title+' · 开发反馈',content)

    @app.post('/runs/{database}/{run_id}/review/{object_id}')
    async def feedback_submit(request: Request, database: str, run_id: str, object_id: str):
        binding, _, _ = review_object(database,run_id,object_id)
        if request.client is None or request.client.host not in {'127.0.0.1','::1'}:
            raise HTTPException(403,'Loopback required')
        origin=request.headers.get('origin')
        if origin is not None and origin != str(request.base_url).rstrip('/'):
            raise HTTPException(403,'Invalid local origin')
        if request.headers.get('content-type','').split(';')[0] != 'application/x-www-form-urlencoded':
            raise HTTPException(415,'URL-encoded form required')
        body=bytearray()
        async for chunk in request.stream():
            if len(body)+len(chunk)>64*1024:
                raise HTTPException(413,'Feedback request too large')
            body.extend(chunk)
        try:
            parsed=parse_qs(body.decode('utf8'),keep_blank_values=True,max_num_fields=12,errors='strict')
            expected={'csrf_token','version','digest','submission_id','expires','ticket','note','marked_text','disposition'}
            if set(parsed)!=expected or any(len(v)!=1 for v in parsed.values()):
                raise ValueError
            form={key:value[0] for key,value in parsed.items()}
        except (ValueError,UnicodeError):
            raise HTTPException(422,'Invalid bounded feedback form') from None
        try:
            validate_local_mutation(request.headers.get('host'),form['csrf_token'],csrf_token)
        except (RequestIntegrityError,ValueError,TypeError):
            raise HTTPException(403,'Invalid local request') from None
        try:
            validate_uuid(form['submission_id'],'submission_id')
            expires=int(form['expires'])
            if (form['version']!=str(binding.version) or form['digest']!=binding.digest
                    or not int(time.time())<=expires<=int(time.time())+3600
                    or not hmac.compare_digest(form['ticket'],ticket(binding,form['submission_id'],form['expires']))):
                raise ValueError
        except (ValueError,TypeError):
            raise HTTPException(409,'Object changed or form invalid/expired; reload and review again') from None
        try:
            validate_feedback(form['note'],form['marked_text'],form['disposition'])
        except ValueError:
            raise HTTPException(422,'Opinion required, bounded to 2000 characters; approval is not supported') from None
        try:
            feedback.append(binding,form['submission_id'],note=form['note'],marked_text=form['marked_text'],disposition=form['disposition'])
        except ValueError:
            raise HTTPException(409,'Feedback conflict or object budget exhausted') from None
        except (sqlite3.Error,OSError):
            raise HTTPException(503,'Feedback not saved: independent local storage unavailable') from None
        return RedirectResponse(review_url(binding),status_code=303)

    @app.get('/intake')
    async def intake():
        try:
            raw=(project/'.data/seo-mvp/session.json').read_bytes()
            if len(raw)>8192:
                raise ValueError
            session=json.loads(raw)
            if session['profile']!='SYNTHETIC_LOCAL_MVP_V1':
                raise ValueError
            store=SQLiteEvidenceIntakeStore(project/'.data/seo-mvp/interactive-intake.sqlite3')
            snapshot=store.latest(session['project_id'],session['task_id'])
            checks=store.checks(session['project_id'],session['task_id'],limit=10)
            content='<p>已保存的合成开发记录；不代表真实客户证据或人工批准。</p>'
            content+=pre(_json({'snapshot':asdict(snapshot),'checks':[asdict(check) for check in checks]}))
        except Exception:
            content='<p>NOT_AVAILABLE：缺少当前可读取的 Intake 状态；未创建或迁移数据库。</p>'
        return page('Evidence Intake 当前保存状态',content)

    @app.get('/reports')
    async def report_index():
        content='<p>以下是原样保留的历史结果，不是本轮重新验收，也不是生产批准。</p><ul>'
        for key,path in reports.items():
            content+='<li><a href="/reports/'+key+'">'+html.escape(key)+'</a> · '+('AVAILABLE' if path.is_file() else 'NOT_AVAILABLE')+' · '+html.escape(str(path))+'</li>'
        return page('Phase7 / EXPLAIN / 审核历史',content+'</ul>')

    @app.get('/reports/{report_id}')
    async def report_view(report_id: str):
        if report_id not in reports:
            raise HTTPException(404,'Unknown report')
        path=reports[report_id]
        try:
            with path.open('rb') as stream:
                raw=stream.read(MAX_VIEW+1)
            if len(raw)>MAX_VIEW:
                raise ValueError
            text=raw.decode('utf-8-sig')
            content='<p>历史文件：'+html.escape(str(path))+'</p><p>SHA256：'+hashlib.sha256(raw).hexdigest()+'</p>'+pre(text)
        except Exception:
            content='<p>NOT_AVAILABLE：文件缺失、超出显示预算或无法读取。</p>'
        return page('历史结果 '+report_id,content)

    return app
