"""Bounded, read-only inspection of existing commercial development artifacts."""
from contextlib import closing
from dataclasses import asdict
from datetime import date, datetime
from enum import Enum
import hashlib
import html
import json
import os
from pathlib import Path
import re
import sqlite3

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from foreign_trade_geo_agent.evidence_review_composition import ProductionDraftAdmission
from foreign_trade_geo_agent.storage.sqlite import SQLiteHistoryReader
from foreign_trade_geo_agent.storage.serialization import encode_artifact
from foreign_trade_geo_agent.storage.evidence_intake import SQLiteEvidenceIntakeStore

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
    app = FastAPI(title='SEO Agent - Commercial Dev',docs_url=None,redoc_url=None,openapi_url=None)
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=['127.0.0.1','localhost'])

    def page(title, content, status=200):
        body = '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
        body += '<title>SEO Agent - Commercial Dev</title><style>body{font:16px/1.65 system-ui;margin:30px auto;max-width:1100px;padding:0 22px;color:#183747;background:#f3f6f7}section,pre{background:white;padding:18px;border-radius:10px;overflow-wrap:anywhere}pre{white-space:pre-wrap}a{color:#006d77}li{margin:8px 0}table{border-collapse:collapse}td,th{padding:9px;border:1px solid #ccc}</style>'
        body += '<nav><a href="/">开发状态</a> · <a href="/history">历史 Run / Source</a> · <a href="/intake">Evidence Intake</a> · <a href="/reports">Phase7 / 审核报告</a></nav>'
        body += '<p><strong>Commercial Dev · READ ONLY · TEST ONLY</strong> — 不生成、不签核、不发布。Trust Layer 尚未通过生产级验收。</p>'
        body += '<h1>'+html.escape(title)+'</h1>'+content+'</html>'
        return HTMLResponse(body,status_code=status,headers={'Cache-Control':'no-store','Content-Security-Policy':
            "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"})

    def pre(value):
        return '<pre>'+html.escape(_safe_text(value[:MAX_VIEW]))+('</pre><p>显示已截断</p>' if len(value)>MAX_VIEW else '</pre>')

    def db_path(key):
        if key not in databases:
            raise HTTPException(404,'Unknown database')
        return databases[key]

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
        content += '<p>Claim Audit / Editorial Review：只读历史报告；人工审核提交界面 NOT_IMPLEMENTED。缺失记录标记 NOT_AVAILABLE。</p>'
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
            content=pre(_json(asdict(run)))+'<h2>Evidence / Source / Draft artifacts</h2><ul>'
            for artifact in artifacts:
                content+='<li><a href="/artifacts/'+database+'/'+artifact.artifact_id+'">'+html.escape(
                    artifact.artifact_type.value+' · '+artifact.artifact_id)+'</a> · version '+str(artifact.payload_version)+'</li>'
            return page('Run '+run_id,content+'</ul>')
        except Exception:
            return page('Run NOT_AVAILABLE','<p>记录不存在或未通过当前 codec 校验；未改写历史数据。</p>',404)

    @app.get('/artifacts/{database}/{artifact_id}')
    async def artifact_view(database: str,artifact_id: str):
        try:
            artifact=SQLiteHistoryReader(db_path(database)).get_artifact(artifact_id)
            if artifact is None:
                raise ValueError
            raw=encode_artifact(artifact.artifact_type,artifact.payload,payload_version=artifact.payload_version)
            return page('已验证 artifact '+artifact_id,pre(_json(json.loads(raw))))
        except Exception:
            return page('Artifact NOT_AVAILABLE','<p>记录不存在或当前契约不支持读取；没有绕过验证。</p>',404)

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
