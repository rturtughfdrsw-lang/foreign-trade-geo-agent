"""Server-rendered MVP routes on the existing local HTTP application."""
from urllib.parse import parse_qsl

from fastapi import APIRouter, Request
from fastapi.responses import Response

from foreign_trade_geo_agent.core.evidence_intake import MAX_TEXT
from foreign_trade_geo_agent.core.content_draft_review import MAX_LOCAL_BODY, MAX_LOCAL_NOTE
from foreign_trade_geo_agent.web.mvp_application import MVPError
from foreign_trade_geo_agent.web.request_integrity import RequestIntegrityError, validate_local_mutation

MAX_FORM_BYTES = MAX_TEXT * 12 + 8192  # Percent-encoded four-byte UTF-8 + bounded metadata.
MAX_ARTICLE_FORM_BYTES = (MAX_LOCAL_BODY + MAX_LOCAL_NOTE) * 12 + 8192


def build_mvp_router(templates):
    router = APIRouter()

    def page(request, section, *, message=None, status=200, submitted=None, validation_submitted=None):
        service = request.app.state.mvp_service
        context = {"section": section, "ready": service.ready, "message": message,
                   "csrf_token": request.app.state.csrf_token, "submitted": submitted,
                   "validation_submitted": validation_submitted, "article_max_chars": MAX_LOCAL_BODY}
        try:
            if service.ready:
                context.update(service.evidence())
                if section == "analysis":
                    url = request.query_params.get("website_url", "").strip()
                    context["website_url"] = url or "https://novacnc.example/"
                    if len(url) > 2048 or url.rstrip("/") not in {"", "https://novacnc.example"}:
                        context["lookup_empty"] = True
                    else:
                        context.update(service.analysis())
                elif section == "evidence":
                    try:
                        context["sample_text"] = service.sample_text()
                    except MVPError:
                        context["sample_text"] = None
                elif section == "article":
                    context.update(service.article(request.query_params.get("version"),
                                                   revalidate=request.query_params.get('revalidate') == '1'))
                elif section == 'delivery':
                    context.update(service.delivery.preview(request.query_params.get('version')))
                elif section == 'delivery_test':
                    context.update(service.delivery.test_preview(request.query_params.get('sample', 'success')))
                elif section == 'generate':
                    from datetime import UTC, datetime, timedelta
                    context.update(service.generation.view())
                    if context['generation_allowed']:
                        service.generation_ticket = (context['binding_sha256'], datetime.now(UTC) + timedelta(minutes=5))
                        context['generation_expires_at'] = service.generation_ticket[1].isoformat()
        except MVPError as error:
            context.update(ready=False, message=str(error))
            status = error.status
        return templates.TemplateResponse(request=request, name="mvp.html", context=context, status_code=status,
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})

    async def local_form(request, *, max_bytes=MAX_FORM_BYTES, max_fields=8):
        # Bound even chunked bodies before parsing. UTF-8 only, no JSON claims of
        # actor identity, file paths, reviewer authority or authorization accepted.
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > max_bytes:
                raise MVPError("提交内容过大，正文最多 16,000 字符。", 413)
        try:
            if request.headers.get("content-type", "").split(";")[0] != "application/x-www-form-urlencoded":
                raise ValueError()
            pairs = parse_qsl(body.decode("utf-8", errors="strict"), keep_blank_values=True,
                              encoding="utf-8", errors="strict", max_num_fields=max_fields)
            form = dict(pairs)
            if len(form) != len(pairs):
                raise ValueError()
        except (ValueError, UnicodeError):
            raise MVPError("请提交有效的 UTF-8 文本表单。", 422) from None
        token = form.get("csrf_token", "")
        if not token.isascii():
            raise RequestIntegrityError("Invalid local request.")
        validate_local_mutation(request.headers.get("host"), token, request.app.state.csrf_token)
        if len(form.get("content", "")) > MAX_TEXT:
            raise MVPError("正文过长，最多 16,000 字符。", 413)
        return form

    @router.get("/mvp")
    async def analysis(request: Request):
        return page(request, "analysis")

    @router.get("/mvp/evidence")
    async def evidence(request: Request):
        return page(request, "evidence")

    @router.post("/mvp/evidence")
    async def submit(request: Request):
        form = None
        try:
            form = await local_form(request)
            request.app.state.mvp_service.submit(expected_sha256=form.get("expected_sha256"),
                content=form.get("content", ""), source_label=form.get("source_label", "UTF-8 客户资料"),
                requirement_id=form.get('requirement_id'))
            # POST/Redirect/GET prevents accidental repost on browser refresh.
            from fastapi.responses import RedirectResponse
            return RedirectResponse("/mvp/evidence?saved=1", status_code=303)
        except MVPError as error:
            return page(request, "evidence", message=str(error), status=error.status, submitted=form)

    @router.post("/mvp/recheck")
    async def recheck(request: Request):
        try:
            form = await local_form(request)
            await request.app.state.mvp_service.recheck(expected_sha256=form.get("expected_sha256"))
            from fastapi.responses import RedirectResponse
            return RedirectResponse("/mvp/evidence?rechecked=1", status_code=303)
        except MVPError as error:
            return page(request, "evidence", message=str(error), status=error.status)

    @router.post('/mvp/scope')
    async def request_scope(request: Request):
        try:
            form = await local_form(request, max_bytes=28000, max_fields=4)
            if set(form) != {'csrf_token', 'expected_sha256', 'goal', 'reason'}:
                raise MVPError('范围请求字段无效；不接受客户同意、审核或授权字段。', 422)
            request.app.state.mvp_service.scope.request(form['expected_sha256'], form['goal'], form['reason'])
            from fastapi.responses import RedirectResponse
            return RedirectResponse('/mvp/evidence#article-scope', status_code=303)
        except MVPError as error:
            return page(request, 'evidence', message=str(error), status=error.status)

    @router.post('/mvp/scope/test-confirm')
    async def confirm_test_scope(request: Request):
        try:
            form = await local_form(request, max_bytes=2048, max_fields=3)
            if set(form) != {'csrf_token', 'expected_sha256', 'confirmed'}:
                raise MVPError('模拟确认字段无效。', 422)
            await request.app.state.mvp_service.scope.confirm_test(form['expected_sha256'], form['confirmed'])
            from fastapi.responses import RedirectResponse
            return RedirectResponse('/mvp/evidence#article-scope', status_code=303)
        except MVPError as error:
            return page(request, 'evidence', message=str(error), status=error.status)

    @router.get("/mvp/article")
    async def article(request: Request):
        return page(request, "article")

    @router.get('/mvp/delivery')
    async def delivery_preview(request: Request):
        return page(request, 'delivery')

    @router.post('/mvp/delivery')
    async def delivery_blocked(request: Request):
        try:
            form = await local_form(request, max_bytes=2048, max_fields=8)
            if set(form) != {'csrf_token', 'version', 'binding_sha256'}:
                raise MVPError('交付表单字段无效；不接受 approval、signature、permission、目标或正文。', 422)
            request.app.state.mvp_service.delivery.block_real(form['version'], form['binding_sha256'])
        except MVPError as error:
            return page(request, 'delivery', message=str(error), status=error.status)

    @router.get('/mvp/delivery/test')
    async def mock_preview(request: Request):
        return page(request, 'delivery_test')

    @router.post('/mvp/delivery/test')
    async def mock_delivery(request: Request):
        try:
            form = await local_form(request, max_bytes=2048, max_fields=8)
            if set(form) != {'csrf_token', 'sample', 'binding_sha256'}:
                raise MVPError('Mock 表单字段无效；不接受 approval、signature、permission、目标或正文。', 422)
            created = await request.app.state.mvp_service.delivery.deliver_mock(form['sample'], form['binding_sha256'])
            from fastapi.responses import RedirectResponse
            return RedirectResponse('/mvp/delivery/test?sample=' + form['sample'] +
                                    ('&recorded=1' if created else '&duplicate=1'), status_code=303)
        except MVPError as error:
            return page(request, 'delivery_test', message=str(error), status=error.status)

    @router.get('/mvp/generate')
    async def generation(request: Request):
        return page(request, 'generate')

    @router.post('/mvp/generate')
    async def generate(request: Request):
        try:
            form = await local_form(request, max_bytes=2048, max_fields=3)
            if set(form) != {'csrf_token', 'binding_sha256'}:
                raise MVPError('生成表单字段无效；不接受模型、身份、路径、授权或 live 字段。', 422)
            service = request.app.state.mvp_service
            service.generation.start(form['binding_sha256'], service.generation_ticket)
            from fastapi.responses import RedirectResponse
            return RedirectResponse('/mvp/generate', status_code=303)
        except MVPError as error:
            return page(request, 'generate', message=str(error), status=error.status)

    @router.post("/mvp/article")
    async def save_article(request: Request):
        form = None
        try:
            form = await local_form(request, max_bytes=MAX_ARTICLE_FORM_BYTES)
            fields = {"csrf_token", "expected_version", "origin_sha256", "expected_evidence_sha256",
                      "body_text", "note", "status"}
            if set(form) != fields:
                raise MVPError("文章表单字段无效；不接受签核或执行权限字段。", 422)
            request.app.state.mvp_service.save_article(**{k: v for k, v in form.items() if k != "csrf_token"})
            from fastapi.responses import RedirectResponse
            return RedirectResponse("/mvp/article?saved=1", status_code=303)
        except MVPError as error:
            return page(request, "article", message=str(error), status=error.status, submitted=form)

    @router.get("/mvp/article.md")
    async def export(request: Request):
        try:
            service = request.app.state.mvp_service
            article = service.article(request.query_params.get("version"))
            return Response(service.markdown(str(article["selected_version"])), media_type="text/markdown; charset=utf-8",
                headers={"Content-Disposition": f'attachment; filename="novacnc-synthetic-version-{article["selected_version"]}.md"',
                         "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})
        except MVPError as error:
            return page(request, "article", message=str(error), status=error.status)

    @router.post('/mvp/article/validation')
    async def save_revalidation(request: Request):
        form = None
        try:
            form = await local_form(request, max_bytes=MAX_ARTICLE_FORM_BYTES, max_fields=9)
            if set(form) != {'csrf_token', 'version', 'origin_sha256', 'body_sha256',
                             'expected_evidence_sha256', 'report_sha256', 'note', 'confirmed', 'decision'}:
                raise MVPError('核验表单字段无效；不接受引用改绑、签核或执行权限字段。', 422)
            request.app.state.mvp_service.save_revalidation(**{k: v for k, v in form.items() if k != 'csrf_token'})
            from fastapi.responses import RedirectResponse
            return RedirectResponse('/mvp/article?version=' + form['version'] + '&revalidate=1&validated=1', status_code=303)
        except MVPError as error:
            return page(request, 'article', message=str(error), status=error.status, validation_submitted=form)

    @router.get('/mvp/candidate')
    async def candidate_review(request: Request):
        from foreign_trade_geo_agent.web.candidate_review import LocalCandidateReview
        try:
            context = LocalCandidateReview(request.app.state.mvp_service).load(request.query_params.get('key'))
            return templates.TemplateResponse(request=request, name='mvp_candidate.html',
                context={**context, 'csrf_token': request.app.state.csrf_token},
                headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})
        except Exception:
            return Response('候选记录、版本或绑定不可用。', status_code=409)

    @router.post('/mvp/candidate')
    async def save_candidate_review(request: Request):
        from foreign_trade_geo_agent.web.candidate_review import LocalCandidateReview
        try:
            form = await local_form(request, max_bytes=MAX_ARTICLE_FORM_BYTES, max_fields=9)
            if set(form) != {'csrf_token', 'key', 'version', 'binding', 'claim_id', 'decision', 'note', 'body_text'}:
                raise MVPError('字段无效；本地意见不能授予签核或生产权限。', 422)
            LocalCandidateReview(request.app.state.mvp_service).save(**{k: v for k, v in form.items() if k != 'csrf_token'})
            from fastapi.responses import RedirectResponse
            return RedirectResponse('/mvp/candidate?key=' + form['key'], status_code=303)
        except MVPError as error:
            return Response(str(error), status_code=error.status)
        except Exception:
            return Response('候选版本已改变或不可审核；未保存。', status_code=409)

    @router.get('/mvp/candidate.md')
    async def export_candidate(request: Request):
        from foreign_trade_geo_agent.web.candidate_review import LocalCandidateReview
        from foreign_trade_geo_agent.reporting.content_draft_review import render_candidate_review_markdown
        try:
            view = LocalCandidateReview(request.app.state.mvp_service).load(request.query_params.get('key'))
            return Response(render_candidate_review_markdown(view['candidate_check'], view['candidate_latest']),
                media_type='text/markdown; charset=utf-8', headers={'Cache-Control': 'no-store'})
        except Exception:
            return Response('候选不可读取。', status_code=409)

    return router
