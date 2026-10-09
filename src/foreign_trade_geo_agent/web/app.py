"""FastAPI application factory for local Demo and Live analysis profiles."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path
import secrets

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
from starlette.templating import Jinja2Templates

from foreign_trade_geo_agent.web.application import (
    DemoApplicationError,
    DemoApplicationService,
)
from foreign_trade_geo_agent.web.composition import (
    build_demo_composition,
    build_live_composition,
)
from foreign_trade_geo_agent.web.jobs import LocalJobRegistry
from foreign_trade_geo_agent.web.live_application import (
    LiveApplicationError,
    LiveApplicationNotFoundError,
    LiveApplicationService,
)
from foreign_trade_geo_agent.web.request_integrity import RequestIntegrityError
from foreign_trade_geo_agent.web.routes import build_router


DEFAULT_DEMO_DB_PATH = Path(".data/demo-ui/history.sqlite3")
DEFAULT_LIVE_DB_PATH = Path(".data/live-ui/history.sqlite3")
DemoServiceFactory = Callable[[Path, LocalJobRegistry], DemoApplicationService]
LiveServiceFactory = Callable[[Path, LocalJobRegistry], LiveApplicationService]
_WEB_ROOT = Path(__file__).resolve().parent


def _default_service_factory(
    db_path: Path,
    jobs: LocalJobRegistry,
) -> DemoApplicationService:
    return DemoApplicationService(build_demo_composition(db_path), jobs)


def _default_live_service_factory(
    db_path: Path,
    jobs: LocalJobRegistry,
) -> LiveApplicationService:
    return LiveApplicationService(build_live_composition(db_path), jobs)


def create_app(
    *,
    db_path: str | Path = DEFAULT_DEMO_DB_PATH,
    live_db_path: str | Path = DEFAULT_LIVE_DB_PATH,
    service_factory: DemoServiceFactory | None = None,
    live_service_factory: LiveServiceFactory | None = None,
) -> FastAPI:
    resolved_db_path = Path(db_path).resolve()
    resolved_live_db_path = Path(live_db_path).resolve()
    if resolved_db_path == resolved_live_db_path:
        raise ValueError("Demo and Live databases must be separate.")
    factory = service_factory or _default_service_factory
    live_factory = live_service_factory or _default_live_service_factory
    csrf_token = secrets.token_urlsafe(32)
    environment = Environment(
        loader=FileSystemLoader(_WEB_ROOT / "templates"),
        autoescape=select_autoescape(("html", "xml")),
    )
    templates = Jinja2Templates(env=environment)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        resolved_db_path.parent.mkdir(parents=True, exist_ok=True)
        resolved_live_db_path.parent.mkdir(parents=True, exist_ok=True)
        jobs = LocalJobRegistry()
        live_jobs = LocalJobRegistry()
        app.state.demo_db_path = resolved_db_path
        app.state.live_db_path = resolved_live_db_path
        app.state.demo_jobs = jobs
        app.state.live_jobs = live_jobs
        app.state.demo_service = factory(resolved_db_path, jobs)
        app.state.live_service = live_factory(resolved_live_db_path, live_jobs)
        try:
            yield
        finally:
            await jobs.shutdown()
            await live_jobs.shutdown()

    app = FastAPI(title="SEO Agent MVP Demo", lifespan=lifespan)
    app.state.csrf_token = csrf_token
    app.mount(
        "/static",
        StaticFiles(directory=_WEB_ROOT / "static"),
        name="static",
    )
    app.include_router(build_router(templates))

    @app.exception_handler(DemoApplicationError)
    async def demo_error(
        request: Request,
        error: DemoApplicationError,
    ) -> HTMLResponse:
        service = request.app.state.demo_service
        return templates.TemplateResponse(
            request=request,
            name="error.html",
            context={
                "message": str(error),
                "navigation": service.navigation(current_step="start"),
            },
            status_code=404,
        )

    @app.exception_handler(LiveApplicationError)
    async def live_error(
        request: Request,
        error: LiveApplicationError,
    ) -> HTMLResponse:
        return templates.TemplateResponse(
            request=request,
            name="error.html",
            context={
                "message": str(error),
                "profile": "live",
                "navigation": request.app.state.live_service.navigation(
                    current_step="start"
                ),
            },
            status_code=(
                404 if isinstance(error, LiveApplicationNotFoundError) else 503
            ),
        )

    @app.exception_handler(RequestIntegrityError)
    async def integrity_error(
        request: Request,
        _error: RequestIntegrityError,
    ) -> HTMLResponse:
        return templates.TemplateResponse(
            request=request,
            name="error.html",
            context={
                "message": "Invalid local request.",
                "profile": "live",
                "navigation": request.app.state.demo_service.navigation(
                    current_step="start"
                ),
            },
            status_code=403,
        )

    return app
