from __future__ import annotations

import asyncio
from contextlib import ExitStack
from pathlib import Path
import re
import socket
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from foreign_trade_geo_agent.core.history import ArtifactType
from foreign_trade_geo_agent.storage.sqlite import SQLiteHistoryReader
from foreign_trade_geo_agent.web.app import create_app


def _unexpected_network(*_args: object, **_kwargs: object) -> None:
    raise AssertionError("Demo HTTP flow attempted real network access")


class DemoNoNetworkTests(unittest.TestCase):
    def test_start_to_draft_review_has_hard_no_network_tripwire(self) -> None:
        guarded_constructors = (
            "foreign_trade_geo_agent.adapters.safe_http.SafeHtmlFetcher",
            "foreign_trade_geo_agent.adapters.tavily_search.TavilySearchAdapter",
            "foreign_trade_geo_agent.adapters.geo_optimizer.GeoOptimizerAdapter",
            "foreign_trade_geo_agent.adapters.deepseek_research.DeepSeekResearchWriter",
            "foreign_trade_geo_agent.adapters.deepseek_content_opportunity.DeepSeekContentOpportunityWriter",
            "foreign_trade_geo_agent.adapters.deepseek_change_plan.DeepSeekChangePlanWriter",
            "foreign_trade_geo_agent.adapters.deepseek_content_draft.DeepSeekContentDraftWriter",
            "foreign_trade_geo_agent.adapters.wordpress_rest.WordPressRestDraftPublisher",
            "foreign_trade_geo_agent.adapters.wordpress_rest.WordPressRestDraftReader",
        )
        with TemporaryDirectory() as directory:
            db_path = Path(directory) / "history.sqlite3"
            with TestClient(create_app(db_path=db_path)) as client:
                with ExitStack() as guards:
                    guards.enter_context(patch.object(socket, "getaddrinfo", _unexpected_network))
                    guards.enter_context(patch.object(socket, "create_connection", _unexpected_network))
                    guards.enter_context(patch.object(socket.socket, "connect", _unexpected_network))
                    guards.enter_context(patch.object(socket.socket, "connect_ex", _unexpected_network))
                    guards.enter_context(
                        patch.object(
                            asyncio.BaseEventLoop,
                            "create_connection",
                            _unexpected_network,
                        )
                    )
                    for target in guarded_constructors:
                        guards.enter_context(patch(target, side_effect=AssertionError(target)))

                    start = client.get("/")
                    launched = client.post("/start", follow_redirects=False)
                    location = launched.headers["location"]
                    progress_pages = []
                    for _ in range(300):
                        progress = client.get(location, headers={"HX-Request": "true"})
                        progress_pages.append(progress.text)
                        location = progress.headers.get("HX-Replace-Url", location)
                        if "hx-trigger" not in progress.text:
                            break
                        time.sleep(0.01)
                    else:
                        self.fail("Demo analysis did not reach a terminal state")
                    match = re.search(r"/runs/([^/]+)/progress", location)
                    self.assertIsNotNone(match)
                    run_id = match.group(1) if match is not None else ""
                    results = client.get(f"/runs/{run_id}/results")
                    changes = client.get(f"/runs/{run_id}/changes")
                    draft = client.get(f"/runs/{run_id}/drafts/D1")

            self.assertEqual(start.status_code, 200)
            self.assertEqual(launched.status_code, 303)
            self.assertEqual(results.status_code, 200)
            self.assertEqual(changes.status_code, 200)
            self.assertEqual(draft.status_code, 200)
            self.assertTrue(any("Running" in page for page in progress_pages))
            artifacts = SQLiteHistoryReader(db_path).list_artifacts(run_id)
            self.assertEqual(len(artifacts), 6)
            self.assertEqual(
                {item.artifact_type for item in artifacts},
                {
                    ArtifactType.SITE_CONTENT,
                    ArtifactType.SITE_AUDIT,
                    ArtifactType.INDUSTRY_RESEARCH,
                    ArtifactType.CONTENT_OPPORTUNITY,
                    ArtifactType.CHANGE_PLAN,
                    ArtifactType.CONTENT_DRAFT,
                },
            )


if __name__ == "__main__":
    unittest.main()
