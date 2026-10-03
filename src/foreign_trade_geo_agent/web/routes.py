"""HTTP routes for the local Demo UI."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.templating import Jinja2Templates

from foreign_trade_geo_agent.web.application import DemoApplicationService
from foreign_trade_geo_agent.web.demo_boundaries import (
    DEMO_COMPANY_NAME,
    DEMO_RESEARCH_QUESTION,
    DEMO_SITE_URL,
)


def _service(request: Request) -> DemoApplicationService:
    return request.app.state.demo_service


def build_router(templates: Jinja2Templates) -> APIRouter:
    router = APIRouter()

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
