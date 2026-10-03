"""HTTP routes for the local Demo UI."""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.templating import Jinja2Templates

from foreign_trade_geo_agent.web.application import DemoApplicationService
from foreign_trade_geo_agent.web.demo_boundaries import (
    DEMO_COMPANY_NAME,
    DEMO_RESEARCH_QUESTION,
    DEMO_SITE_URL,
)
from foreign_trade_geo_agent.web.presenters import (
    present_delivery_result,
    present_verification_result,
)


def _service(request: Request) -> DemoApplicationService:
    return request.app.state.demo_service


def build_router(templates: Jinja2Templates) -> APIRouter:
    router = APIRouter()

    @router.get("/healthz")
    async def healthz() -> JSONResponse:
        return JSONResponse({"app": "seo-agent-demo"})

    @router.get("/", response_class=HTMLResponse)
    async def start_page(request: Request) -> HTMLResponse:
        service = _service(request)
        return templates.TemplateResponse(
            request=request,
            name="start.html",
            context={
                "company_name": DEMO_COMPANY_NAME,
                "site_url": DEMO_SITE_URL,
                "research_question": DEMO_RESEARCH_QUESTION,
                "target_language": "English",
                "navigation": service.navigation(current_step="start"),
            },
        )

    @router.post("/start", response_class=HTMLResponse)
    async def start_analysis(request: Request) -> RedirectResponse:
        result = _service(request).start_demo_analysis()
        return RedirectResponse(f"/jobs/{result.job_id}", status_code=303)

    @router.get("/jobs/{job_id}", response_class=HTMLResponse)
    async def job_progress(request: Request, job_id: str) -> HTMLResponse:
        progress = _service(request).get_progress(job_id=job_id)
        return _progress_response(request, templates, _service(request), progress)

    @router.get("/runs/{run_id}/progress", response_class=HTMLResponse)
    async def run_progress(request: Request, run_id: str) -> HTMLResponse:
        progress = _service(request).get_progress(run_id=run_id)
        return _progress_response(request, templates, _service(request), progress)

    @router.get("/runs/{run_id}/results", response_class=HTMLResponse)
    async def results_page(request: Request, run_id: str) -> HTMLResponse:
        view = _service(request).load_results(run_id)
        return templates.TemplateResponse(
            request=request,
            name="results.html",
            context={
                "view": view,
                "navigation": _service(request).navigation(
                    current_step="results",
                    run_id=run_id,
                ),
            },
        )

    @router.get("/runs/{run_id}/changes", response_class=HTMLResponse)
    async def changes_page(request: Request, run_id: str) -> HTMLResponse:
        view = _service(request).load_change_plan(run_id)
        return templates.TemplateResponse(
            request=request,
            name="changes.html",
            context={
                "view": view,
                "navigation": _service(request).navigation(
                    current_step="changes",
                    run_id=run_id,
                ),
            },
        )

    @router.get(
        "/runs/{run_id}/drafts/{draft_id}",
        response_class=HTMLResponse,
    )
    async def draft_review_page(
        request: Request,
        run_id: str,
        draft_id: str,
    ) -> HTMLResponse:
        view = _service(request).review_draft(run_id, draft_id)
        return templates.TemplateResponse(
            request=request,
            name="draft_review.html",
            context={
                "view": view,
                "navigation": _service(request).navigation(
                    current_step="draft",
                    run_id=run_id,
                ),
            },
        )

    @router.get(
        "/runs/{run_id}/drafts/{draft_id}/delivery",
        response_class=HTMLResponse,
    )
    async def delivery_setup_page(
        request: Request,
        run_id: str,
        draft_id: str,
    ) -> HTMLResponse:
        service = _service(request)
        state = service.load_delivery_setup(run_id, draft_id)
        if state.existing_attempt_id is not None:
            return RedirectResponse(
                f"/runs/{run_id}/deliveries/{state.existing_attempt_id}",
                status_code=303,
            )
        return templates.TemplateResponse(
            request=request,
            name="delivery_setup.html",
            context={
                "view": state,
                "navigation": service.navigation(
                    current_step="delivery",
                    run_id=run_id,
                ),
            },
        )

    @router.post("/runs/{run_id}/drafts/{draft_id}/delivery")
    async def create_wordpress_draft_route(
        request: Request,
        run_id: str,
        draft_id: str,
        intent_confirmed: str | None = Form(None),
    ) -> RedirectResponse:
        service = _service(request)
        attempt_id = await service.create_wordpress_draft(
            run_id,
            draft_id,
            intent_confirmed=intent_confirmed == "true",
        )
        return RedirectResponse(
            f"/runs/{run_id}/deliveries/{attempt_id}",
            status_code=303,
        )

    @router.get(
        "/runs/{run_id}/deliveries/{attempt_id}",
        response_class=HTMLResponse,
    )
    async def delivery_result_page(
        request: Request,
        run_id: str,
        attempt_id: str,
    ) -> HTMLResponse:
        service = _service(request)
        attempt = service.load_delivery_result(run_id, attempt_id)
        view = present_delivery_result(run_id, attempt)
        return templates.TemplateResponse(
            request=request,
            name="delivery_result.html",
            context={
                "view": view,
                "navigation": service.navigation(
                    current_step="delivery",
                    run_id=run_id,
                ),
            },
        )

    @router.post("/runs/{run_id}/deliveries/{attempt_id}/verify")
    async def verify_wordpress_draft_route(
        request: Request,
        run_id: str,
        attempt_id: str,
    ) -> RedirectResponse:
        await _service(request).verify_wordpress_draft(run_id, attempt_id)
        return RedirectResponse(
            f"/runs/{run_id}/deliveries/{attempt_id}/verification",
            status_code=303,
        )

    @router.get(
        "/runs/{run_id}/deliveries/{attempt_id}/verification",
        response_class=HTMLResponse,
    )
    async def verification_result_page(
        request: Request,
        run_id: str,
        attempt_id: str,
    ) -> HTMLResponse:
        service = _service(request)
        state = service.load_verification_result(run_id, attempt_id)
        view = present_verification_result(
            run_id,
            state.attempt,
            state.verification,
        )
        return templates.TemplateResponse(
            request=request,
            name="verification_result.html",
            context={
                "view": view,
                "navigation": service.navigation(
                    current_step="verification",
                    run_id=run_id,
                ),
            },
        )

    return router


def _progress_response(
    request: Request,
    templates: Jinja2Templates,
    service: DemoApplicationService,
    progress: object,
) -> HTMLResponse:
    is_htmx = request.headers.get("HX-Request", "").casefold() == "true"
    response = templates.TemplateResponse(
        request=request,
        name="partials/progress_panel.html" if is_htmx else "progress.html",
        context={
            "progress": progress,
            "navigation": service.navigation(
                current_step="progress",
                run_id=getattr(progress, "run_id", None),
            ),
            "navigation_oob": is_htmx,
        },
    )
    run_id = getattr(progress, "run_id", None)
    if is_htmx and run_id is not None:
        response.headers["HX-Replace-Url"] = f"/runs/{run_id}/progress"
    return response
