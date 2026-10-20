import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from foreign_trade_geo_agent.adapters.deepseek_change_plan import DeepSeekChangePlanWriter
from foreign_trade_geo_agent.adapters.deepseek_content_draft import DeepSeekContentDraftWriter
from foreign_trade_geo_agent.adapters.deepseek_content_opportunity import DeepSeekContentOpportunityWriter
from foreign_trade_geo_agent.adapters.deepseek_research import DeepSeekResearchWriter
from foreign_trade_geo_agent.adapters.safe_http import SafeHtmlFetcher
from foreign_trade_geo_agent.adapters.tavily_search import TavilySearchAdapter
from foreign_trade_geo_agent.runtime import planning_provider_configuration_ready
from foreign_trade_geo_agent.web.composition import (
    build_demo_composition,
    build_live_composition,
)
from foreign_trade_geo_agent.workflows.crawl_seo_audit import CrawlSeoAuditor


class LiveCompositionTests(unittest.TestCase):
    def test_missing_tavily_or_deepseek_configuration_is_not_ready(self) -> None:
        self.assertFalse(planning_provider_configuration_ready({}))
        self.assertFalse(
            planning_provider_configuration_ready({"TAVILY_API_KEY": "t"})
        )
        self.assertFalse(
            planning_provider_configuration_ready({"DEEPSEEK_API_KEY": "d"})
        )

    def test_placeholder_configuration_marks_ready_without_network(self) -> None:
        self.assertTrue(
            planning_provider_configuration_ready(
                {"TAVILY_API_KEY": "test-t", "DEEPSEEK_API_KEY": "test-d"}
            )
        )

    def test_default_wiring_uses_safe_fetcher_crawl_auditor_tavily_and_deepseek(self) -> None:
        with TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {"TAVILY_API_KEY": "test-t", "DEEPSEEK_API_KEY": "test-d"},
            clear=True,
        ):
            composition = build_live_composition(Path(directory) / "live.sqlite3")
            workflow = composition.planning_workflow()

        self.assertTrue(composition.providers_ready)
        self.assertIsInstance(workflow._site_crawl._fetcher, SafeHtmlFetcher)
        self.assertIsInstance(workflow._planning_site_auditor, CrawlSeoAuditor)
        self.assertIsInstance(
            workflow._industry_research._search_provider,
            TavilySearchAdapter,
        )
        self.assertIsInstance(
            workflow._industry_research._research_writer,
            DeepSeekResearchWriter,
        )
        self.assertIsInstance(
            workflow._content_opportunity._writer,
            DeepSeekContentOpportunityWriter,
        )
        self.assertIsInstance(workflow._change_plan._writer, DeepSeekChangePlanWriter)
        self.assertIsInstance(workflow._content_draft._writer, DeepSeekContentDraftWriter)

    def test_live_composition_has_no_wordpress_delivery_or_verification_boundary(self) -> None:
        with TemporaryDirectory() as directory:
            composition = build_live_composition(
                Path(directory) / "live.sqlite3",
                provider_configuration_ready=False,
            )

        self.assertFalse(hasattr(composition, "delivery_workflow"))
        self.assertFalse(hasattr(composition, "verification_workflow"))

    def test_demo_composition_builds_with_zero_provider_keys(self) -> None:
        with TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            composition = build_demo_composition(Path(directory) / "demo.sqlite3")
            workflow = composition.planning_workflow()

        self.assertIsNotNone(workflow)


if __name__ == "__main__":
    unittest.main()
