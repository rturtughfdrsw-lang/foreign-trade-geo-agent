"""FastAPI application factory for the local deterministic Demo."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
from starlette.templating import Jinja2Templates

from foreign_trade_geo_agent.web.application import (
    DemoApplicationError,
    DemoApplicationService,
)
from foreign_trade_geo_agent.web.composition import build_demo_composition
from foreign_trade_geo_agent.web.jobs import LocalJobRegistry
from foreign_trade_geo_agent.web.routes import build_router


DEFAULT_DEMO_DB_PATH = Path(".data/demo-ui/history.sqlite3")
DemoServiceFactory = Callable[[Path, LocalJobRegistry], DemoApplicationService]
_WEB_ROOT = Path(__file__).resolve().parent


def _default_service_factory(
    db_path: Path,
    jobs: LocalJobRegistry,
) -> DemoApplicationService:
    return DemoApplicationService(build_demo_composition(db_path), jobs)


def create_app(
    *,
    db_path: str | Path = DEFAULT_DEMO_DB_PATH,
    service_factory: DemoServiceFactory | None = None,
) -> FastAPI:
    resolved_db_path = Path(db_path).resolve()
    factory = service_factory or _default_service_factory
    environment = Environment(
        loader=FileSystemLoader(_WEB_ROOT / "templates"),
        autoescape=select_autoescape(("html", "xml")),
    )
    templates = Jinja2Templates(env=environment)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        resolved_db_path.parent.mkdir(parents=True, exist_ok=True)
        jobs = LocalJobRegistry()
        app.state.demo_db_path = resolved_db_path
        app.state.demo_jobs = jobs
        app.state.demo_service = factory(resolved_db_path, jobs)
        try:
            yield
        finally:
            await jobs.shutdown()

    app = FastAPI(title="SEO Agent MVP Demo", lifespan=lifespan)
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

    return app
