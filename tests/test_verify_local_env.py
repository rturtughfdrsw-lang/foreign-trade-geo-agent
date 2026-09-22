from contextlib import redirect_stdout
from io import StringIO
import os
from pathlib import Path
import runpy
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from scripts import local_env
from scripts import verify_deepseek_visibility
from scripts import verify_industry_research
from scripts import verify_perplexity_visibility
from scripts import verify_site_optimization
from scripts import verify_tavily_search
from scripts import verify_visibility_monitor
from foreign_trade_geo_agent.core.optimization import (
    OptimizationStatus,
    SiteOptimizationReport,
)
from foreign_trade_geo_agent.core.research import ResearchReport, ResearchStatus
from foreign_trade_geo_agent.core.search import SearchStatus


FAKE_TAVILY_KEY = "temporary-tavily-secret"
FAKE_DEEPSEEK_KEY = "temporary-deepseek-secret"
FAKE_PERPLEXITY_KEY = "temporary-perplexity-secret"


class VerifyScriptLocalEnvTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.project_root = Path(self.temporary_directory.name)
        (self.project_root / ".env").write_text(
            (
                f"TAVILY_API_KEY={FAKE_TAVILY_KEY}\n"
                f"DEEPSEEK_API_KEY={FAKE_DEEPSEEK_KEY}\n"
                f"PERPLEXITY_API_KEY={FAKE_PERPLEXITY_KEY}\n"
                "UNRELATED_API_KEY=temporary-unrelated-secret\n"
            ),
            encoding="utf-8",
        )
        self.project_root_patch = patch.object(
            local_env,
            "PROJECT_ROOT",
            self.project_root,
        )
        self.project_root_patch.start()
        self.addCleanup(self.project_root_patch.stop)
        self.addCleanup(self.temporary_directory.cleanup)

    def test_single_provider_scripts_load_only_their_provider_key(self) -> None:
        cases = (
            (
                verify_tavily_search,
                "TAVILY_API_KEY",
                FAKE_TAVILY_KEY,
                SearchStatus.SUCCESS,
            ),
            (
                verify_deepseek_visibility,
                "DEEPSEEK_API_KEY",
                FAKE_DEEPSEEK_KEY,
                None,
            ),
            (
                verify_visibility_monitor,
                "DEEPSEEK_API_KEY",
                FAKE_DEEPSEEK_KEY,
                None,
            ),
            (
                verify_perplexity_visibility,
                "PERPLEXITY_API_KEY",
                FAKE_PERPLEXITY_KEY,
                None,
            ),
        )

        for module, expected_name, expected_value, verify_result in cases:
            with self.subTest(script=Path(module.__file__).name):
                with patch.dict(os.environ, {}, clear=True):
                    with patch.object(
                        module,
                        "_verify",
                        AsyncMock(return_value=verify_result),
                    ):
                        output = StringIO()
                        with redirect_stdout(output):
                            exit_code = module.main()

                    self.assertEqual(exit_code, 0)
                    self.assertEqual(os.environ[expected_name], expected_value)
                    loaded_api_keys = {
                        name
                        for name in os.environ
                        if name.endswith("_API_KEY")
                    }
                    self.assertEqual(loaded_api_keys, {expected_name})
                    self.assertNotIn(expected_value, output.getvalue())

    def test_industry_research_loads_only_tavily_and_deepseek_keys(self) -> None:
        report = ResearchReport(
            question="temporary question",
            status=ResearchStatus.NO_RESULTS,
            draft_text=None,
            sources=(),
            error="temporary safe failure",
        )

        with patch.dict(os.environ, {}, clear=True):
            with patch.object(
                verify_industry_research,
                "_run_once",
                AsyncMock(return_value=(report, 0.0)),
            ):
                with redirect_stdout(StringIO()):
                    exit_code = verify_industry_research.main()

            self.assertEqual(exit_code, 1)
            self.assertEqual(os.environ["TAVILY_API_KEY"], FAKE_TAVILY_KEY)
            self.assertEqual(os.environ["DEEPSEEK_API_KEY"], FAKE_DEEPSEEK_KEY)
            self.assertNotIn("PERPLEXITY_API_KEY", os.environ)
            self.assertNotIn("UNRELATED_API_KEY", os.environ)

    def test_site_optimization_loads_only_tavily_and_deepseek_keys(self) -> None:
        report = SiteOptimizationReport(
            url="https://example.com",
            status=OptimizationStatus.AUDIT_FAILED,
            recommendations=(),
            audit_evidence=(),
            sources=(),
            error="temporary safe failure",
        )
        business_environment = {
            "SITE_OPTIMIZATION_URL": "https://example.com",
            "SITE_RESEARCH_TOPIC": "temporary topic",
            "SITE_PRODUCT_TERMS": "temporary product",
            "SITE_TARGET_MARKETS": "temporary market",
        }

        with patch.dict(os.environ, business_environment, clear=True):
            with patch.object(
                verify_site_optimization,
                "_run_once",
                AsyncMock(return_value=(report, 0.0)),
            ):
                with redirect_stdout(StringIO()):
                    exit_code = verify_site_optimization.main()

            self.assertEqual(exit_code, 1)
            self.assertEqual(os.environ["TAVILY_API_KEY"], FAKE_TAVILY_KEY)
            self.assertEqual(os.environ["DEEPSEEK_API_KEY"], FAKE_DEEPSEEK_KEY)
            self.assertNotIn("PERPLEXITY_API_KEY", os.environ)
            self.assertNotIn("UNRELATED_API_KEY", os.environ)
            self.assertEqual(
                os.environ["SITE_TARGET_MARKETS"],
                "temporary market",
            )

    def test_importing_scripts_does_not_load_config_or_create_http_client(self) -> None:
        scripts = (
            verify_tavily_search,
            verify_deepseek_visibility,
            verify_visibility_monitor,
            verify_perplexity_visibility,
            verify_industry_research,
            verify_site_optimization,
        )

        for module in scripts:
            with self.subTest(script=Path(module.__file__).name):
                output = StringIO()
                with patch.object(local_env, "load_api_keys") as load:
                    with patch.object(
                        httpx,
                        "AsyncClient",
                        side_effect=AssertionError(
                            "Import must not create an HTTP client."
                        ),
                    ):
                        with redirect_stdout(output):
                            runpy.run_path(
                                Path(module.__file__),
                                run_name=f"{module.__name__}_import_test",
                            )

                self.assertEqual(output.getvalue(), "")
                load.assert_not_called()

    def test_missing_provider_keys_exit_before_any_request(self) -> None:
        (self.project_root / ".env").unlink()
        scripts = (
            verify_tavily_search,
            verify_deepseek_visibility,
            verify_visibility_monitor,
            verify_perplexity_visibility,
        )

        for module in scripts:
            with self.subTest(script=Path(module.__file__).name):
                verify = AsyncMock()
                with patch.dict(os.environ, {}, clear=True):
                    with patch.object(module, "_verify", verify):
                        with redirect_stdout(StringIO()):
                            exit_code = module.main()

                self.assertEqual(exit_code, 2)
                verify.assert_not_awaited()

        with patch.dict(os.environ, {}, clear=True):
            with patch.object(
                verify_industry_research,
                "_run_once",
                AsyncMock(),
            ) as run_once:
                with redirect_stdout(StringIO()):
                    exit_code = verify_industry_research.main()

        self.assertEqual(exit_code, 2)
        run_once.assert_not_awaited()

        business_environment = {
            "SITE_OPTIMIZATION_URL": "https://example.com",
            "SITE_RESEARCH_TOPIC": "temporary topic",
            "SITE_PRODUCT_TERMS": "temporary product",
        }
        with patch.dict(os.environ, business_environment, clear=True):
            with patch.object(
                verify_site_optimization,
                "_run_once",
                AsyncMock(),
            ) as run_once:
                with redirect_stdout(StringIO()):
                    exit_code = verify_site_optimization.main()

        self.assertEqual(exit_code, 2)
        run_once.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
