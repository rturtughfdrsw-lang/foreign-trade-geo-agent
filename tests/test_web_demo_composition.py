from __future__ import annotations

import asyncio
from contextlib import ExitStack
from pathlib import Path
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from foreign_trade_geo_agent.core.approved_wordpress_delivery import (
    ApprovedWordPressDraftDeliveryRequest,
)
from foreign_trade_geo_agent.core.fetching import FetchStatus, HtmlFetchResult
from foreign_trade_geo_agent.core.history import (
    ArtifactType,
    RunStatus,
    WordPressAttemptState,
    WordPressVerificationOutcome,
)
from foreign_trade_geo_agent.core.orchestration import EndToEndRunRequest
from foreign_trade_geo_agent.core.site_content import SiteContentPacket
from foreign_trade_geo_agent.core.wordpress_verification import WordPressVerificationRequest
from foreign_trade_geo_agent.web.composition import build_demo_composition
from foreign_trade_geo_agent.web.demo_boundaries import (
    DEMO_RESEARCH_QUESTION,
    DEMO_SITE_URL,
    DEMO_TARGET_LANGUAGE,
    DemoBoundaryError,
    DemoCrawlFetcher,
)
from foreign_trade_geo_agent.web.demo_wordpress import demo_wordpress_origin


ROOT = Path(__file__).resolve().parents[1]


def _unexpected_network(*_args: object, **_kwargs: object) -> None:
    raise AssertionError("Demo composition attempted real network access")


class DemoBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_fixture_fetcher_serves_only_exact_novacnc_allowlist(self) -> None:
        fetcher = DemoCrawlFetcher()

        robots = await fetcher.fetch_text("https://novacnc.example/robots.txt")
        home = await fetcher.fetch(DEMO_SITE_URL)
        machines = await fetcher.fetch("https://novacnc.example/machines.html")

        for result in (robots, home, machines):
            self.assertIsInstance(result, HtmlFetchResult)
            self.assertIs(result.status, FetchStatus.SUCCESS)
            self.assertEqual(result.connected_ip, "192.0.2.10")
        with self.assertRaises(DemoBoundaryError):
            await fetcher.fetch("https://customer.example/")
        with self.assertRaises(DemoBoundaryError):
            await fetcher.fetch("https://novacnc.example/unknown.html")


class DemoCompositionTests(unittest.IsolatedAsyncioTestCase):
    async def test_demo_composition_runs_real_planning_chain_into_sqlite(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            db_path = Path(temporary_directory) / "history.sqlite3"
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
                composition = build_demo_composition(db_path)
                result = await composition.planning_workflow().run(
                    EndToEndRunRequest(
                        site_url=DEMO_SITE_URL,
                        research_question=DEMO_RESEARCH_QUESTION,
                        target_language=DEMO_TARGET_LANGUAGE,
                    )
                )

            self.assertIs(result.run.status, RunStatus.SUCCEEDED)
            artifacts = composition.history_reader.list_artifacts(result.run.run_id)
            self.assertEqual(
                tuple(item.artifact_type for item in artifacts),
                (
                    ArtifactType.SITE_CONTENT,
                    ArtifactType.SITE_AUDIT,
                    ArtifactType.INDUSTRY_RESEARCH,
                    ArtifactType.CONTENT_OPPORTUNITY,
                    ArtifactType.CHANGE_PLAN,
                    ArtifactType.CONTENT_DRAFT,
                ),
            )
            packet = artifacts[0].payload
            self.assertIsInstance(packet, SiteContentPacket)
            self.assertEqual(tuple(page.evidence_id for page in packet.pages), ("P1", "P2"))
            self.assertIn("850 mm X-axis travel", " ".join(page.body_text or "" for page in packet.pages))
            self.assertTrue(db_path.is_file())

    async def test_demo_composition_does_not_construct_production_providers(self) -> None:
        guarded_constructors = (
            "foreign_trade_geo_agent.adapters.safe_http.SafeHtmlFetcher",
            "foreign_trade_geo_agent.adapters.tavily_search.TavilySearchAdapter",
            "foreign_trade_geo_agent.adapters.geo_optimizer.GeoOptimizerAdapter",
            "foreign_trade_geo_agent.adapters.deepseek_research.DeepSeekResearchWriter",
            "foreign_trade_geo_agent.adapters.deepseek_content_opportunity.DeepSeekContentOpportunityWriter",
            "foreign_trade_geo_agent.adapters.deepseek_change_plan.DeepSeekChangePlanWriter",
            "foreign_trade_geo_agent.adapters.deepseek_content_draft.DeepSeekContentDraftWriter",
            "foreign_trade_geo_agent.adapters.wordpress_rest.WordPressRestDraftPublisher",
        )
        with TemporaryDirectory() as temporary_directory, ExitStack() as guards:
            for target in guarded_constructors:
                guards.enter_context(patch(target, side_effect=AssertionError(target)))
            composition = build_demo_composition(
                Path(temporary_directory) / "history.sqlite3"
            )
            result = await composition.planning_workflow().run(
                EndToEndRunRequest(
                    DEMO_SITE_URL,
                    DEMO_RESEARCH_QUESTION,
                    DEMO_TARGET_LANGUAGE,
                )
            )

        self.assertIs(result.run.status, RunStatus.SUCCEEDED)

    async def test_demo_d1_has_multiple_grounded_semantic_blocks(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            db_path = Path(temporary_directory) / "history.sqlite3"
            composition = build_demo_composition(db_path)
            result = await composition.planning_workflow().run(
                EndToEndRunRequest(
                    DEMO_SITE_URL,
                    DEMO_RESEARCH_QUESTION,
                    DEMO_TARGET_LANGUAGE,
                )
            )
            artifacts = composition.history_reader.list_artifacts(result.run.run_id)
            draft_artifact = next(
                item
                for item in artifacts
                if item.artifact_type is ArtifactType.CONTENT_DRAFT
            )
            report = draft_artifact.payload

        self.assertEqual(len(report.drafts), 1)
        draft = report.drafts[0]
        self.assertGreaterEqual(len(draft.blocks), 2)
        self.assertTrue(
            any(block.kind.value == "PARAGRAPH" for block in draft.blocks)
        )
        self.assertTrue(
            any(block.kind.value == "BULLET_LIST" for block in draft.blocks)
        )

    async def test_composition_exposes_delivery_and_verification_workflows(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            composition = build_demo_composition(
                Path(temporary_directory) / "history.sqlite3"
            )

        self.assertIsNotNone(composition.history_store)
        self.assertIsNotNone(composition.wordpress_transport)
        self.assertIsNotNone(
            composition.delivery_workflow("https://demo-wordpress-x.example")
        )
        self.assertIsNotNone(composition.verification_workflow())

    async def test_delivery_and_verification_use_only_mock_transport(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            db_path = Path(temporary_directory) / "history.sqlite3"
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
                composition = build_demo_composition(db_path)
                planning = await composition.planning_workflow().run(
                    EndToEndRunRequest(
                        DEMO_SITE_URL,
                        DEMO_RESEARCH_QUESTION,
                        DEMO_TARGET_LANGUAGE,
                    )
                )
                run_id = planning.run.run_id
                artifacts = composition.history_reader.list_artifacts(run_id)
                draft_artifact = next(
                    item
                    for item in artifacts
                    if item.artifact_type is ArtifactType.CONTENT_DRAFT
                )
                target = demo_wordpress_origin(run_id)
                delivery = await composition.delivery_workflow(target).deliver(
                    ApprovedWordPressDraftDeliveryRequest(
                        planning_run_id=run_id,
                        content_draft_artifact_id=draft_artifact.artifact_id,
                        draft_id="D1",
                        target_site_url=target,
                        title_override="NovaCNC Machining Center Buyer Guide",
                    )
                )
                self.assertIs(
                    delivery.attempt.outcome,
                    WordPressAttemptState.SUCCESS,
                )
                verification = await composition.verification_workflow().verify(
                    WordPressVerificationRequest(delivery.attempt.attempt_id)
                )
                self.assertIs(
                    verification.verification_outcome,
                    WordPressVerificationOutcome.VERIFIED,
                )
                observations = composition.wordpress_transport.observations

        self.assertEqual(
            tuple(observation.method for observation in observations),
            ("POST", "GET"),
        )
        self.assertEqual(len(observations), 2)

    def test_demo_composition_import_does_not_load_production_runtime(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import json, sys; "
                    "import foreign_trade_geo_agent.web.composition; "
                    "print(json.dumps('foreign_trade_geo_agent.runtime' in sys.modules))"
                ),
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.stdout.strip(), "false")


if __name__ == "__main__":
    unittest.main()
