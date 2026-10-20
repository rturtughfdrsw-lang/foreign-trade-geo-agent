"""Small local HTML workflow for offline Commercial Preview V1."""
import asyncio
from contextlib import asynccontextmanager
import html
import hmac
import json
import secrets
import sqlite3
from urllib.parse import parse_qs, urlencode
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from foreign_trade_geo_agent.core.commercial_preview import (
    ExecutionConfirmation, digest, readiness, require, task_from,
)
from foreign_trade_geo_agent.storage.commercial_preview import feedback_binding
from foreign_trade_geo_agent.web.jobs import LocalJobRegistry
from foreign_trade_geo_agent.web.request_integrity import validate_local_mutation, RequestIntegrityError

from foreign_trade_geo_agent.web.commercial_preview_ui import (
    STYLE, STATUSES, details, overview, review_cards, obligation_label, source_display,
)

esc = lambda value: html.escape(str(value), quote=True)


def create_preview_app(workflow):
    jobs = LocalJobRegistry()
    csrf = secrets.token_hex(32)

    @asynccontextmanager
    async def lifespan(app):
        yield
        await jobs.shutdown()

    app = FastAPI(title='COMMERCIAL_PREVIEW', docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost'])
    app.state.workflow = workflow

    def root(request):
        return request.scope.get('root_path', '').rstrip('/')

    def page(request, body, status=200):
        return HTMLResponse('<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1"><title>SEO 内容审核</title>'
            '<style>'+STYLE+'</style><main><header><a href="'+esc(root(request)+'/')+'">开始新分析 / 历史</a>'
            '<h1>SEO 内容审核</h1><p class="muted">核对文章资料，准备英文草稿。</p>'
            '<small>本地预览 · 尚未获得生产发布授权。</small></header>'
            + body + '</main></html>', status_code=status,
            headers={'Cache-Control': 'no-store', 'Referrer-Policy': 'same-origin',
                     'X-Content-Type-Options': 'nosniff', 'Content-Security-Policy':
                     "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"})

    def hidden(name, value):
        return '<input type="hidden" name="'+esc(name)+'" value="'+esc(value)+'">'

    def form(request, action, body, button, state=None):
        fields = hidden('csrf_token', csrf)
        if state:
            fields += hidden('revision', state['revision']) + hidden('state_digest', digest(state))
        return '<form method="post" action="'+esc(root(request)+action)+'">'+fields+body+'<button>'+esc(button)+'</button></form>'

    def field(name, label, value='', area=False):
        if area:
            control = '<textarea required name="'+esc(name)+'" maxlength="16000">'+esc(value)+'</textarea>'
        else:
            control = '<input required type="text" name="'+esc(name)+'" maxlength="1000" value="'+esc(value)+'">'
        return '<label>'+esc(label)+control+'</label>'

    async def body(request):
        require(request.headers.get('content-type', '').split(';')[0] == 'application/x-www-form-urlencoded', 'PREVIEW_FORM_REQUIRED')
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > 100000:
                raise HTTPException(413, 'PREVIEW_REQUEST_BUDGET')
        values = parse_qs(raw.decode('utf-8', errors='strict'), keep_blank_values=True, max_num_fields=100)
        require(all(len(v) == 1 for k, v in values.items() if k != 'span_id'), 'PREVIEW_DUPLICATE_FIELD')
        data = {k: v[0] for k, v in values.items()}
        try:
            validate_local_mutation(request.headers.get('host'), data.get('csrf_token'), csrf)
        except (RequestIntegrityError, TypeError, ValueError):
            raise HTTPException(403, 'PREVIEW_REQUEST_INTEGRITY') from None
        origin = request.headers.get('origin')
        if origin is not None and origin != str(request.base_url).rstrip('/'):
            # Mounted apps have a base_url containing /preview; Origin has only authority.
            expected = f"{request.url.scheme}://{request.headers.get('host')}"
            if origin != expected:
                raise HTTPException(403, 'PREVIEW_REQUEST_ORIGIN')
        data['_span_ids'] = values.get('span_id', [])
        return data

    def review_receipt(state, key):
        # Presentation receipt only: never used for admission or persisted authorization.
        message = digest(dict(run_id=state['run_id'], revision=state['revision'],
                              state_digest=digest(state), obligation_id=key))
        return hmac.digest(csrf.encode(), message.encode(), 'sha256').hex()

    def saved_review(request, state):
        key = request.query_params.get('saved', '')
        receipt = request.query_params.get('receipt', '')
        if (request.query_params.get('saved_revision') == str(state['revision'])
                and any(r['obligation_id'] == key for r in state['reviews'])
                and len(receipt) == 64 and receipt.isascii()
                and hmac.compare_digest(receipt, review_receipt(state, key))):
            return key
        return None

    def binding(data):
        return int(data['revision']), data['state_digest']

    @app.exception_handler(HTTPException)
    async def request_failure(request, error):
        messages = {
            403: '页面身份或来源校验未通过。请重新打开本地任务页面后再操作。',
            413: '提交的内容过大。请缩短资料或意见后再提交。',
            404: '未找到此操作，请返回任务页面。',
        }
        code = error.detail if isinstance(error.detail, str) and error.detail.startswith('PREVIEW_') and len(error.detail) <= 100 else 'PREVIEW_REQUEST_FAILED'
        return page(request, '<h2>请求未保存</h2><p>'+messages.get(error.status_code, '请求未通过校验，请返回任务页面检查内容。')+'</p>'+details('查看错误详情', code), error.status_code)

    @app.exception_handler(ValueError)
    async def invalid(request, error):
        # Display only our fixed validation categories, never arbitrary exception text.
        code = str(error)
        if not code.startswith('PREVIEW_') or len(code) > 100:
            code = 'PREVIEW_INVALID'
        messages = {
            'PREVIEW_STALE_FORM': '页面已过期。请重新打开当前任务，核对最新资料后再保存。',
            'PREVIEW_REVIEW_SPAN_BINDING': '请阅读并勾选本项全部证据片段，不能遗漏候选来源。',
            'PREVIEW_REVIEW_ACK_REQUIRED': '请勾选“我已核对”确认框，再保存本项核对。',
            'PREVIEW_INVALID': '请选择核对结论并填写意见。意见须为有效文本，最多 1000 字符。',
        }
        return page(request, '<h2>请求未保存</h2><p>'+messages.get(code, '请求未通过校验。请返回任务检查必填内容和当前资料要求。')+'</p>'+details('查看错误详情', code), 409)

    @app.exception_handler(sqlite3.Error)
    @app.exception_handler(OSError)
    async def persistence_failure(request, error):
        return page(request, '<h2>保存结果未确认</h2><p>本地保存遇到问题，暂时无法确认是否保存成功。请重新打开任务，检查已保存的记录后再决定下一步。</p><p>若本次操作是生成草稿，请先检查生成状态；系统不会自动重试。</p>'+details('技术详情：保存错误', 'PREVIEW_PERSISTENCE_FAILED'), 503)

    @app.get('/')
    async def index(request: Request):
        content = '<h2>1. 网站样本分析</h2><p>真实模式必须由启动配置授权具体 URL，并在此确认范围；采样不构成整站审计。</p>'
        content += details('技术详情：网站读取配置', workflow.analyzer.preparation())
        modes = '<label>网站模式<select name="mode"><option value="SYNTHETIC">演示资料</option><option value="REAL_SITE">真实网站</option></select></label>'
        modes += field('website', '网站 URL', 'https://preview-b2b.example/')
        modes += '<label>真实模式允许抓取的精确 HTTPS URL（每行一个；必须在启动授权清单内）<textarea name="allowed_urls" maxlength="16000"></textarea></label>'
        modes += '<label><input type="checkbox" name="site_ack" value="yes">我授权本次读取所列网站 URL 及同源 /robots.txt，已确认有权访问和保留资料</label>'
        content += form(request, '/analyze', modes, '分析所选网站样本')
        content += '<details><summary>演示测试页面</summary><p>无选题示例：https://preview-b2b.example/empty.html</p></details><h2>已保存的文章任务</h2>'
        for run in workflow.store.list_runs():
            state = workflow.store.read(run)
            title = (state.get('task') or state['analysis'].get('topic') or {}).get('title', '尚未选择文章主题')
            content += '<p><a href="'+esc(root(request)+'/runs/'+run)+'">'+esc(title)+'</a></p>'
        return page(request, content)

    @app.get('/status')
    async def status():
        return dict(profile='COMMERCIAL_PREVIEW', data_kind='SELECTABLE',
                    site=workflow.analyzer.preparation(), writer=workflow.writer.preparation(),
                    live_model_enabled=workflow.writer.policy()['writer'] == 'DeepSeekPreviewWriter' and workflow.writer.policy()['enabled'],
                    production_authorized=False, writer_calls=workflow.writer.calls)

    @app.post('/analyze')
    async def analyze(request: Request):
        data = await body(request)
        job = jobs.create_job()
        task = asyncio.create_task(workflow.analyze(data['website'], mode=data.get('mode', 'SYNTHETIC'),
            allowed_urls=data.get('allowed_urls', '').splitlines(), site_authorized=data.get('site_ack') == 'yes'))
        jobs.attach_task(job, task)
        state = await task
        return RedirectResponse(root(request)+'/runs/'+state['run_id'], status_code=303)

    @app.get('/runs/{run_id}')
    async def view(request: Request, run_id: str):
        state = workflow.store.read(run_id)
        analysis = state['analysis']
        content = '<details class="secondary"><summary>资料与来源管理</summary><details><summary>网站分析与选题依据</summary>'
        content += details('查看分析技术信息', dict(profile='COMMERCIAL_PREVIEW', research=analysis['research'], serp=analysis['serp'], production_authorized=False))
        content += '<p>数据标记：'+esc(analysis['data_kind'])+' · 仅样本审计。网站营销宣称未经独立核实，仍须逐项人工支持核对。</p>'
        content += '<details><summary>采样 SEO 审计（非整站结论）</summary><pre>'+esc(analysis['audit'])+'</pre></details>'
        content += '<details><summary>抓取原文及页面来源</summary><pre>'+esc(json.dumps(analysis['content'], ensure_ascii=False, indent=2))+'</pre></details>'
        if analysis['topic'] is None:
            return page(request, content+'</details></details><p>'+esc(analysis['no_topic_reason'])+'</p>')
        content += details('选题来源绑定', analysis['topic'])+'</details></details>'
        current = state['task'] or dict(title=analysis['topic']['title'], reader_question='What does Aster supply and what must a buyer confirm?',
            required_facts=['Describe the enclosure product.', 'Describe the fabrication capability.'],
            scope='Aster stainless steel enclosure fabrication for reviewed industrial equipment drawings.',
            limitations='Project-specific suitability, ratings and delivery must be separately confirmed.')
        if state['task'] is None and analysis['data_kind'] == 'REAL':
            current.update(reader_question='What should buyers confirm about '+analysis['topic']['subject']+'?',
                required_facts=['Describe the documented product.', 'Describe the documented capability.'],
                scope='Reviewed website samples for '+analysis['topic']['subject']+'.',
                limitations='Website statements require human verification; suitability and commercial terms require separate confirmation.')
        task_fields = ''.join(field(k, label, current[k], True) for k, label in (
            ('title', '文章标题'), ('reader_question', '目标读者问题'), ('scope', '适用范围'), ('limitations', '必要限制')))
        task_fields += ''.join(field('fact_'+str(i), '必需事实 '+str(i+1), fact, True)
                               for i, fact in enumerate(current['required_facts']))
        task_fields += '<label><input type="checkbox" required name="task_ack" value="yes">我确认网站、标题、全部问题、事实、范围与限制</label>'
        content += '<details class="secondary"'+(' open' if state['task'] is None else '')+'><summary>任务设置</summary><p>修订文章任务会使现有证据绑定和核对失效，请仅在需要调整写作要求时修改。</p>'
        content += form(request, '/runs/'+run_id+'/task', task_fields, '确认当前文章任务', state)+'</details>'
        if state['task'] is None:
            return page(request, content)
        task = task_from(state['task'])
        gaps = readiness(state)
        saved = saved_review(request, state)
        attempt = workflow.result(run_id)
        content = overview(state, task, gaps, saved, attempt) + review_cards(request, state, task, saved, form, hidden) + content
        content += '<details class="secondary"><summary>补充资料与调整来源</summary><p>新增、绑定或移除资料会清空现有核对，需要重新逐项核对。</p>'
        content += details('技术详情：待满足的资料要求', gaps) if gaps else '<p>资料齐备且各项均已核对为证据支持，具体含义仍须由人判断。</p>'
        choices = '<label>用于哪一项核对<select name="obligation_id">'+''.join('<option value="'+esc(k)+'">'+esc(obligation_label(k, task))+'</option>' for k in task.obligations)+'</select></label>'
        upload = choices + field('label', '来源名称', '补充资料') + field('locator', '来源定位（仅标签，不抓取）', 'local://document')
        upload += field('content', '精确资料文本（粘贴 UTF-8 内容；默认整个文本为引用片段）', '', True)
        content += form(request, '/runs/'+run_id+'/evidence', upload, '保存资料，清空旧核对与确认', state)
        for source in state['sources']:
            if source.get('source_type') == 'WEBSITE_SAMPLE':
                content += '<details><summary>'+esc(source_display(state, source)['label'])+'</summary>'+details('技术详情：网站来源', source)
                fields = hidden('source_id', source['source_id']) + choices + field('quote', '从此页面复制精确片段（绑定不代表支持已核实）', '', True)
                content += form(request, '/runs/'+run_id+'/bind-page', fields, '绑定页面片段，随后人工核对', state)+'</details>'
        for source in state['sources']:
            content += '<details class="danger"><summary>移除来源：'+esc(source_display(state, source)['label'])+'</summary><p>移除后，全部核对及生成确认会失效。请确认确实不再使用此来源。</p>'
            content += details('技术详情：待移除来源', source)
            content += form(request, '/runs/'+run_id+'/remove-source', hidden('source_id', source['source_id']), '确认移除此来源', state)+'</details>'
        content += '</details>'
        content += '<details class="secondary"><summary>下一步：生成英文预览草稿</summary>'
        preparation = workflow.writer.preparation()
        content += '<p>'+('请先完成上方全部资料审核，再单独确认一次生成。' if gaps else '资料审核已完成。请核对模型和预算，单独确认一次生成。')+'</p>'
        content += details('查看生成模型与预算', preparation)
        content += details('查看任务绑定的模型配置', state.get('execution_policy'))
        if not attempt:
            if not gaps and preparation['status'] == 'READY':
                content += form(request, '/runs/'+run_id+'/confirm', '<label><input required type="checkbox" name="execution_ack" value="yes">我已核对本次模型、预算和当前文章资料，只确认生成一次预览草稿。使用在线模型时会发送外部请求；失败、超时或结果未知均不自动重试。</label>', '确认单次预览执行', state)
            if state['confirmation']:
                confirmation_fields = ''.join(hidden(k, v) for k, v in state['confirmation'].items())
                content += details('查看单次执行确认', state['confirmation'])
                content += form(request, '/runs/'+run_id+'/generate', confirmation_fields, '执行已确认的单次预览', state)
        else:
            content += '<h2>英文草稿与复核</h2><p>本任务已执行一次生成。'+('当前资料已变化，请核对下方保留结果。' if attempt['freshness']=='STALE' else '请阅读草稿并进行编辑复核。')+'</p>'+details('查看生成执行信息', dict(attempt_id=attempt['attempt_id'], freshness=attempt['freshness']))
            content += '<p>'+STATUSES['NEEDS_REVIEW']+' · '+STATUSES['NOT_AUTHORIZED']+'</p>'
            result = attempt['result']
            if result is None:
                content += '<p>生成结果尚未确认，可能仍在执行或已中断；不会自动重试。</p>'+details('查看执行状态', dict(TECHNICAL='UNKNOWN', EVIDENCE='NOT_CHECKED', EDITORIAL_REVIEW='NEEDS_REVIEW', PRODUCTION_AUTHORIZATION='NOT_AUTHORIZED'))
            else:
                summary = {k: v for k, v in result.items() if k not in {'article', 'raw'}}
                if 'provider' in summary:
                    summary['provider'] = {k: v for k, v in summary['provider'].items() if k != 'raw_response'}
                content += '<p>生成结果仍需证据与编辑复核，尚未获得生产授权。</p>'+details('查看生成结果与审核状态', summary)
                if 'article' in result:
                    content += '<article><h2>'+esc(result['article']['title'])+'</h2>'
                    for p in result['article']['paragraphs']:
                        content += '<h3>'+esc(p['heading'])+'</h3><p>'+esc(p['text'])+'</p>'+details('查看段落来源绑定', dict(source_ids=p['source_ids'], obligation_ids=p['obligation_ids']))
                    content += '</article>'
                if 'raw' in result:
                    content += '<details><summary>保留原稿（无自动删句、修复或重试）</summary><pre>'+esc(result['raw'])+'</pre></details>'
                if result.get('provider', {}).get('raw_response') is not None:
                    content += '<details><summary>模型原始响应（已脱敏）</summary><pre>'+esc(result['provider']['raw_response'])+'</pre></details>'
            content += '<details><summary>本次生成时冻结的精确来源、引用和核对记录（STALE 时仍保留）</summary><pre>'+esc(json.dumps(attempt['material'], indent=2, ensure_ascii=False))+'</pre></details>'
        content += '</details><details class="secondary"><summary>普通反馈</summary><p>记录使用意见；反馈不会改变资料核对、生成确认或生产授权。</p>'
        feedback_attempt = workflow.store.attempt(run_id)
        object_id, version, object_digest = feedback_binding(state, feedback_attempt)
        feedback_fields = hidden('object_id', object_id)+hidden('version', version)+hidden('object_digest', object_digest)+hidden('submission_id', str(uuid4()))
        feedback_fields += field('note', '反馈意见', '', True)
        content += form(request, '/runs/'+run_id+'/feedback', feedback_fields, '保存反馈', state)
        content += details('查看反馈记录', workflow.store.list_feedback(run_id))+'</details>'
        return page(request, content)

    @app.post('/runs/{run_id}/{action}')
    async def mutate(request: Request, run_id: str, action: str):
        data = await body(request)
        revision, state_digest = binding(data)
        state = workflow.current(run_id, revision, state_digest)
        args = (run_id, revision, state_digest)
        if action == 'task':
            require(data.get('task_ack') == 'yes', 'PREVIEW_TASK_CONFIRMATION_REQUIRED')
            count = len(state['task']['required_facts']) if state['task'] else 2
            workflow.confirm_task(*args, title=data['title'], reader_question=data['reader_question'],
                scope=data['scope'], limitations=data['limitations'], required_facts=tuple(data['fact_'+str(i)] for i in range(count)))
        elif action == 'evidence':
            workflow.supplement(*args, obligation_id=data['obligation_id'], content=data['content'], label=data['label'], locator=data['locator'])
        elif action == 'bind-page':
            workflow.bind_page(*args, source_id=data['source_id'], obligation_id=data['obligation_id'], quote=data['quote'])
        elif action == 'remove-source':
            workflow.remove_source(*args, source_id=data['source_id'])
        elif action == 'review':
            require(data.get('review_ack') == 'LOCAL_PREVIEW_REVIEW', 'PREVIEW_REVIEW_ACK_REQUIRED')
            saved_state = workflow.review(*args, obligation_id=data['obligation_id'], span_ids=data['_span_ids'], verdict=data['verdict'], note=data['note'])
            query = dict(saved=data['obligation_id'], saved_revision=str(saved_state['revision']), receipt=review_receipt(saved_state, data['obligation_id']))
            return RedirectResponse(root(request)+'/runs/'+run_id+'?'+urlencode(query)+'#review-'+data['obligation_id'], status_code=303)
        elif action == 'confirm':
            require(data.get('execution_ack') == 'yes', 'PREVIEW_CONFIRMATION_REQUIRED')
            workflow.confirm_execution(*args)
        elif action == 'generate':
            confirmation = ExecutionConfirmation(**{k: int(data[k]) if k in {'task_version', 'schema_version'} else data[k]
                for k in ExecutionConfirmation.__dataclass_fields__})
            require(confirmation.run_id == run_id, 'PREVIEW_CONFIRMATION_BINDING')
            await workflow.execute(run_id, confirmation)
        elif action == 'feedback':
            workflow.store.feedback(run_id, data['object_id'], int(data['version']), data['object_digest'], data['submission_id'], data['note'])
        else:
            raise HTTPException(404, 'PREVIEW_ACTION_NOT_FOUND')
        return RedirectResponse(root(request)+'/runs/'+run_id, status_code=303)

    @app.exception_handler(KeyError)
    async def missing_field(request, error):
        return page(request, '<h2>请求未保存</h2><p>缺少必填内容，请返回任务补全后再保存。</p>'+details('查看错误详情', 'PREVIEW_REQUIRED_FIELD_MISSING'), 409)

    return app
