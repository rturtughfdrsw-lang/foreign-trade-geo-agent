import asyncio
from contextlib import redirect_stdout
from io import StringIO
import os
from pathlib import Path
import runpy
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from scripts import verify_industry_research
from foreign_trade_geo_agent.core.research import (
    ResearchReport,
    ResearchSource,
    ResearchStatus,
)


SENSITIVE_KEY = "unit-test-sensitive-api-key"


def successful_report() -> ResearchReport:
    return ResearchReport(
        question="test question",
        status=ResearchStatus.SUCCESS,
        draft_text="工业阀门市场存在稳定需求。[S1]",
        sources=(
            ResearchSource(
                source_id="S1",
                title="Valve market report",
                url="https://example.com/report",
            ),
        ),
        error=None,
    )


def failed_report(
    status: ResearchStatus,
    *,
    error: str = "safe failure",
) -> ResearchReport:
    return ResearchReport(
        question="test question",
        status=status,
        draft_text=None,
        sources=(),
        error=error,
    )


class FakeWorkflow:
    def __init__(self, report: ResearchReport) -> None:
        self.report = report
        self.questions: list[str] = []

    async def run(self, question: str) -> ResearchReport:
        self.questions.append(question)
        return self.report


class VerifyIndustryResearchTests(unittest.TestCase):
    def test_import_does_not_create_an_http_client_or_print_output(self) -> None:
        output = StringIO()

        with patch.object(
            httpx,
            "AsyncClient",
            side_effect=AssertionError("Import must not create an HTTP client."),
        ):
            with redirect_stdout(output):
                runpy.run_path(
                    Path(verify_industry_research.__file__),
                    run_name="verify_industry_research_import_test",
                )

        self.assertEqual(output.getvalue(), "")

    def test_missing_either_api_key_exits_without_running_workflow(self) -> None:
        environments = (
            {"TAVILY_API_KEY": "tavily-only"},
            {"DEEPSEEK_API_KEY": "deepseek-only"},
            {},
        )

        for environment in environments:
            with self.subTest(environment=environment):
                output = StringIO()
                with patch.dict(os.environ, environment, clear=True):
                    with (
                        patch.object(
                            verify_industry_research,
                            "load_api_keys",
                        ),
                        patch.object(
                            verify_industry_research.asyncio,
                            "run",
                        ) as run,
                    ):
                        with redirect_stdout(output):
                            exit_code = verify_industry_research.main()

                self.assertEqual(exit_code, 2)
                run.assert_not_called()
                self.assertIn("no request was sent", output.getvalue())

    def test_run_once_calls_workflow_once_with_fixed_public_question(self) -> None:
        workflow = FakeWorkflow(successful_report())
        times = iter((10.0, 12.5))

        report, elapsed = asyncio.run(
            verify_industry_research._run_once(
                workflow=workflow,
                clock=lambda: next(times),
            )
        )

        self.assertEqual(report.status, ResearchStatus.SUCCESS)
        self.assertEqual(
            workflow.questions,
            [verify_industry_research.RESEARCH_QUESTION],
        )
        self.assertEqual(elapsed, 2.5)
        self.assertIn("工业阀门", verify_industry_research.RESEARCH_QUESTION)

    def test_success_output_contains_draft_sources_and_review_warning(self) -> None:
        output = StringIO()

        with redirect_stdout(output):
            exit_code = verify_industry_research._print_result(
                successful_report(),
                2.5,
            )

        text = output.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("Status: SUCCESS", text)
        self.assertIn("工业阀门市场存在稳定需求。[S1]", text)
        self.assertIn("[S1] https://example.com/report", text)
        self.assertIn("requires_human_review=True", text)
        self.assertIn("引用编号正确不等于事实已核实", text)
        self.assertIn("Elapsed seconds: 2.500", text)

    def test_failure_output_does_not_display_a_success_report(self) -> None:
        for status in (
            ResearchStatus.SEARCH_FAILED,
            ResearchStatus.NO_RESULTS,
            ResearchStatus.GENERATION_FAILED,
            ResearchStatus.INVALID_OUTPUT,
        ):
            with self.subTest(status=status):
                output = StringIO()
                with redirect_stdout(output):
                    exit_code = verify_industry_research._print_result(
                        failed_report(status),
                        1.0,
                    )

                text = output.getvalue()
                self.assertEqual(exit_code, 1)
                self.assertIn(f"Status: {status.name}", text)
                self.assertIn("Failure:", text)
                self.assertNotIn("Report draft:", text)
                self.assertNotIn("Trusted sources:", text)

    def test_failure_output_does_not_echo_sensitive_provider_error(self) -> None:
        output = StringIO()
        report = failed_report(
            ResearchStatus.GENERATION_FAILED,
            error=f"provider failed with {SENSITIVE_KEY}",
        )

        with redirect_stdout(output):
            verify_industry_research._print_result(report, 1.0)

        self.assertNotIn(SENSITIVE_KEY, output.getvalue())
        self.assertIn("Report generation failed.", output.getvalue())

    def test_main_runs_exactly_one_coroutine_when_both_keys_exist(self) -> None:
        async_run = AsyncMock(return_value=(successful_report(), 0.5))
        environment = {
            "TAVILY_API_KEY": "unit-test-tavily-key",
            "DEEPSEEK_API_KEY": "unit-test-deepseek-key",
        }

        with patch.dict(os.environ, environment, clear=True):
            with (
                patch.object(verify_industry_research, "load_api_keys"),
                patch.object(
                    verify_industry_research,
                    "_run_once",
                    async_run,
                ),
            ):
                with redirect_stdout(StringIO()):
                    exit_code = verify_industry_research.main()

        self.assertEqual(exit_code, 0)
        async_run.assert_awaited_once_with()


if __name__ == "__main__":
    unittest.main()
