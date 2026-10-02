import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from foreign_trade_geo_agent.adapters.deepseek_change_plan import (
    DeepSeekChangePlanWriter,
)
from foreign_trade_geo_agent.adapters.deepseek_content_draft import (
    DeepSeekContentDraftWriter,
)
from foreign_trade_geo_agent.adapters.deepseek_content_opportunity import (
    DeepSeekContentOpportunityWriter,
)
from foreign_trade_geo_agent.adapters.deepseek_research import DeepSeekResearchWriter
from foreign_trade_geo_agent.adapters.page_extractor import TrafilaturaPageExtractor
from foreign_trade_geo_agent.adapters.geo_optimizer import GeoOptimizerAdapter
from foreign_trade_geo_agent.adapters.safe_http import SafeHtmlFetcher
from foreign_trade_geo_agent.adapters.tavily_search import TavilySearchAdapter
from foreign_trade_geo_agent.adapters.wordpress_rest import WordPressRestDraftPublisher
from foreign_trade_geo_agent.storage.sqlite import SQLiteHistoryStore
from foreign_trade_geo_agent.workflows.approved_wordpress_delivery import (
    ApprovedWordPressDraftDeliveryWorkflow,
)
from foreign_trade_geo_agent.workflows.end_to_end import EndToEndWorkflow
from foreign_trade_geo_agent.workflows.wordpress_delivery import (
    WordPressDeliveryWorkflow,
)


class RuntimeEnvironmentTests(unittest.TestCase):
    def test_process_environment_wins_over_cwd_dotenv(self) -> None:
        from foreign_trade_geo_agent.runtime import load_runtime_environment

        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / ".env").write_text(
                "DEEPSEEK_API_KEY=dotenv-deepseek\n"
                "TAVILY_API_KEY=dotenv-tavily\n",
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {"DEEPSEEK_API_KEY": "process-deepseek"},
                clear=True,
            ):
                load_runtime_environment(root)

                self.assertEqual(
                    os.environ["DEEPSEEK_API_KEY"],
                    "process-deepseek",
                )
                self.assertEqual(os.environ["TAVILY_API_KEY"], "dotenv-tavily")


class RuntimeCompositionTests(unittest.TestCase):
    def test_real_planning_composition_constructs_without_network(self) -> None:
        from foreign_trade_geo_agent.runtime import build_planning_workflow

        with TemporaryDirectory() as temporary_directory, patch.dict(
            os.environ,
            {
                "DEEPSEEK_API_KEY": "dummy-deepseek",
                "TAVILY_API_KEY": "dummy-tavily",
            },
            clear=True,
        ):
            db_path = Path(temporary_directory) / "nested" / "history.sqlite3"
            workflow = build_planning_workflow(db_path)

            self.assertIsInstance(workflow, EndToEndWorkflow)
            self.assertIsInstance(workflow._site_crawl._fetcher, SafeHtmlFetcher)
            self.assertIsInstance(
                workflow._site_crawl._extractor,
                TrafilaturaPageExtractor,
            )
            self.assertIsInstance(
                workflow._industry_research._search_provider,
                TavilySearchAdapter,
            )
            self.assertIsInstance(workflow._site_auditor, GeoOptimizerAdapter)
            self.assertIsInstance(
                workflow._industry_research._research_writer,
                DeepSeekResearchWriter,
            )
            self.assertIsInstance(
                workflow._content_opportunity._writer,
                DeepSeekContentOpportunityWriter,
            )
            self.assertIsInstance(
                workflow._change_plan._writer,
                DeepSeekChangePlanWriter,
            )
            self.assertIsInstance(
                workflow._content_draft._writer,
                DeepSeekContentDraftWriter,
            )
            self.assertIsInstance(workflow._history_store, SQLiteHistoryStore)
            self.assertTrue(db_path.is_file())

    def test_real_delivery_composition_constructs_without_post(self) -> None:
        from foreign_trade_geo_agent.runtime import build_delivery_workflow

        with TemporaryDirectory() as temporary_directory:
            db_path = Path(temporary_directory) / "nested" / "history.sqlite3"
            workflow = build_delivery_workflow(
                db_path,
                target_site_url="https://customer.example",
                username="dummy-user",
                application_password="dummy-password",
            )

            self.assertIsInstance(workflow, ApprovedWordPressDraftDeliveryWorkflow)
            self.assertIsInstance(workflow._history_store, SQLiteHistoryStore)
            self.assertIsInstance(
                workflow._wordpress_delivery,
                WordPressDeliveryWorkflow,
            )
            self.assertIsInstance(
                workflow._wordpress_delivery._publisher,
                WordPressRestDraftPublisher,
            )
            self.assertIs(
                workflow._wordpress_delivery._history_store,
                workflow._history_store,
            )
            self.assertTrue(db_path.is_file())


    def test_real_review_composition_is_read_only(self) -> None:
        from foreign_trade_geo_agent.runtime import build_review_workflow
        from foreign_trade_geo_agent.storage.sqlite import SQLiteHistoryReader
        from foreign_trade_geo_agent.workflows.content_draft_review import (
            ContentDraftReviewWorkflow,
        )
        from tests.review_fixtures import persist_review_fixture

        with TemporaryDirectory() as temporary_directory:
            db_path = Path(temporary_directory) / "history.sqlite3"
            fixture = persist_review_fixture(db_path)
            before = db_path.read_bytes()

            workflow = build_review_workflow(fixture.db_path)

            self.assertIsInstance(workflow, ContentDraftReviewWorkflow)
            self.assertIsInstance(workflow._history_reader, SQLiteHistoryReader)
            self.assertEqual(db_path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
