from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
import asyncio
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from foreign_trade_geo_agent.core.fetching import HtmlFetchResult
from foreign_trade_geo_agent.core.orchestration import EndToEndRunRequest
from foreign_trade_geo_agent.core.search import SearchResponse
from foreign_trade_geo_agent.web.application import DemoApplicationService
from foreign_trade_geo_agent.web.app import create_app
from foreign_trade_geo_agent.web.composition import build_demo_composition
from foreign_trade_geo_agent.web.demo_boundaries import (
    DEMO_RESEARCH_QUESTION,
    DEMO_SITE_URL,
    DEMO_TARGET_LANGUAGE,
    DemoContentDraftWriter,
    DemoCrawlFetcher,
    DemoSearchProvider,
)
from foreign_trade_geo_agent.web.jobs import LocalJobRegistry
from foreign_trade_geo_agent.web.presenters import present_navigation


HOSTILE = "<script>alert(1)</script>"
ESCAPED = "&lt;script&gt;alert(1)&lt;/script&gt;"


def _finish_run(client: TestClient) -> str:
    response = client.post("/start", follow_redirects=False)
    location = response.headers["location"]
    for _ in range(300):
        progress = client.get(location, headers={"HX-Request": "true"})
        location = progress.headers.get("HX-Replace-Url", location)
        if "hx-trigger" not in progress.text:
            match = re.search(r"/runs/([^/]+)/progress", location)
            if match is None:
                raise AssertionError("Demo run finished without a persisted run URL")
            return match.group(1)
        time.sleep(0.01)
    raise AssertionError("Demo run did not finish")


@contextmanager
def _website_hostile_text():
    original = DemoCrawlFetcher.fetch

    async def fetch(self: DemoCrawlFetcher, url: str, **kwargs: object) -> HtmlFetchResult:
        result = await original(self, url, **kwargs)
        if url != DEMO_SITE_URL:
            return result
        content = result.content.replace(
            b"</main>",
            b"<p>&lt;script&gt;alert(1)&lt;/script&gt;</p></main>",
        )
        return replace(
            result,
            content=content,
            wire_bytes=len(content),
            decoded_bytes=len(content),
        )

    with patch.object(DemoCrawlFetcher, "fetch", fetch):
        yield


@contextmanager
def _research_hostile_text():
    original = DemoSearchProvider.search

    async def search(self: DemoSearchProvider, query: str) -> SearchResponse:
        response = await original(self, query)
        item = response.results[0]
        return replace(
            response,
            results=(replace(item, content=f"{item.content} {HOSTILE}"),),
        )

    with patch.object(DemoSearchProvider, "search", search):
        yield


@contextmanager
def _draft_hostile_text():
    original = DemoContentDraftWriter.write_content_draft

    async def write(self: DemoContentDraftWriter, prompt: object):
        generation = await original(self, prompt)
        payload = json.loads(generation.text or "{}")
        payload["draft"]["blocks"][0]["claims"][0]["text"] += f" {HOSTILE}"
        return replace(generation, text=json.dumps(payload))

    with _website_hostile_text(), patch.object(
        DemoContentDraftWriter,
        "write_content_draft",
        write,
    ):
        yield


class DemoXssTests(unittest.TestCase):
    def _render_hostile_path(self, injection: object, suffix: str) -> str:
        with TemporaryDirectory() as directory, injection:
            app = create_app(db_path=Path(directory) / "history.sqlite3")
            with TestClient(app) as client:
                run_id = _finish_run(client)
                response = client.get(f"/runs/{run_id}/{suffix}")
        self.assertEqual(response.status_code, 200)
        return response.text

    def test_website_evidence_script_text_is_escaped(self) -> None:
        html = self._render_hostile_path(_website_hostile_text(), "results")
        self.assertNotIn(HOSTILE, html)
        self.assertIn(ESCAPED, html)

    def test_external_research_script_text_is_escaped(self) -> None:
        html = self._render_hostile_path(_research_hostile_text(), "changes")
        self.assertNotIn(HOSTILE, html)
        self.assertIn(ESCAPED, html)

    def test_draft_script_text_is_escaped(self) -> None:
        async def build_view(db_path: Path):
            composition = build_demo_composition(db_path)
            result = await composition.planning_workflow().run(
                EndToEndRunRequest(
                    DEMO_SITE_URL,
                    DEMO_RESEARCH_QUESTION,
                    DEMO_TARGET_LANGUAGE,
                )
            )
            service = DemoApplicationService(composition, LocalJobRegistry())
            view = service.review_draft(result.run.run_id, "D1")
            return result.run.run_id, replace(
                view,
                review=replace(
                    view.review,
                    draft=replace(
                        view.review.draft,
                        body_text=f"{view.review.draft.body_text} {HOSTILE}",
                    ),
                ),
            )

        class DraftTextService:
            def __init__(self, view: object) -> None:
                self.view = view

            def review_draft(self, _run_id: str, _draft_id: str):
                return self.view

            def navigation(self, *, current_step: str, run_id: str | None = None):
                return present_navigation(
                    current_step=current_step,
                    destinations={
                        "start": "/",
                        "progress": None,
                        "results": None,
                        "changes": None,
                        "draft": None,
                    },
                )

        with TemporaryDirectory() as directory:
            db_path = Path(directory) / "history.sqlite3"
            run_id, view = asyncio.run(build_view(db_path))
            app = create_app(
                db_path=db_path,
                service_factory=lambda _path, _jobs: DraftTextService(view),
            )
            with TestClient(app) as client:
                response = client.get(f"/runs/{run_id}/drafts/D1")

        self.assertEqual(response.status_code, 200)
        html = response.text
        self.assertNotIn(HOSTILE, html)
        self.assertIn(ESCAPED, html)

    def test_web_templates_and_python_use_no_safe_markup_escape_bypass(self) -> None:
        web_root = Path(__file__).resolve().parents[1] / "src" / "foreign_trade_geo_agent" / "web"
        for path in tuple((web_root / "templates").rglob("*.html")) + tuple(web_root.glob("*.py")):
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertNotIn("|safe", text)
                self.assertNotIn("Markup(", text)
                self.assertNotIn("markupsafe", text.casefold())


if __name__ == "__main__":
    unittest.main()
