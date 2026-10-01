from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from foreign_trade_geo_agent.core.content_draft import ContentDraftType
from foreign_trade_geo_agent.core.history import (
    ArtifactType,
    RunStatus,
    WordPressAttemptState,
)
from foreign_trade_geo_agent.core.orchestration import (
    ArtifactRef,
    EndToEndRunRequest,
    EndToEndStage,
)
from foreign_trade_geo_agent.core.approved_wordpress_delivery import (
    ApprovedWordPressDraftDeliveryRequest,
)
from foreign_trade_geo_agent.workflows.wordpress_delivery import (
    WordPressDeliveryStatus,
)


RUN_ID = "11111111-1111-4111-8111-111111111111"
ARTIFACT_ID = "22222222-2222-4222-8222-222222222222"
SITE_CONTENT_ID = "33333333-3333-4333-8333-333333333333"
ATTEMPT_ID = "44444444-4444-4444-8444-444444444444"


class FakePlanningWorkflow:
    def __init__(self, result=None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.requests: list[EndToEndRunRequest] = []

    async def run(self, request: EndToEndRunRequest):
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return self.result


class FakeDeliveryWorkflow:
    def __init__(self, result=None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.requests: list[ApprovedWordPressDraftDeliveryRequest] = []

    async def deliver(self, request: ApprovedWordPressDraftDeliveryRequest):
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return self.result


def planning_result(*, status: RunStatus = RunStatus.SUCCEEDED):
    artifacts = (
        ArtifactRef(SITE_CONTENT_ID, ArtifactType.SITE_CONTENT, 1),
        ArtifactRef(ARTIFACT_ID, ArtifactType.CONTENT_DRAFT, 1),
    )
    drafts = (
        SimpleNamespace(
            draft_id="D1",
            draft_type=ContentDraftType.SECTION_DRAFT,
            heading="Chemical compatibility guide",
        ),
        SimpleNamespace(
            draft_id="D2",
            draft_type=ContentDraftType.NEW_RESOURCE_DRAFT,
            heading=None,
        ),
    )
    succeeded = status is RunStatus.SUCCEEDED
    return SimpleNamespace(
        run=SimpleNamespace(
            run_id=RUN_ID,
            status=status,
            site_key="https://manufacturer.example:443",
            failure_kind=None if succeeded else "content_draft.invalid_output",
        ),
        artifacts=artifacts,
        stopped_stage=None if succeeded else EndToEndStage.CONTENT_DRAFT,
        terminal_report=SimpleNamespace(drafts=drafts) if succeeded else None,
        requires_human_review=succeeded,
    )


def delivery_result(
    status: WordPressDeliveryStatus,
    attempt_outcome: WordPressAttemptState,
):
    success = attempt_outcome is WordPressAttemptState.SUCCESS
    attempt = SimpleNamespace(
        attempt_id=ATTEMPT_ID,
        outcome=attempt_outcome,
        remote_post_id=41 if success else None,
        remote_link="https://customer.example/?p=41" if success else None,
    )
    return SimpleNamespace(
        selected_draft_id="D2",
        delivery_result=SimpleNamespace(status=status, attempt=attempt),
        attempt=attempt,
        reconciliation_required=attempt_outcome
        in {WordPressAttemptState.PENDING, WordPressAttemptState.UNKNOWN},
    )


def invoke_main(arguments, **kwargs):
    from foreign_trade_geo_agent.cli import main

    stdout = StringIO()
    stderr = StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = main(arguments, **kwargs)
    return code, stdout.getvalue(), stderr.getvalue()


class CliHelpTests(unittest.TestCase):
    def test_help_paths_do_not_construct_runtime_or_create_database(self) -> None:
        from foreign_trade_geo_agent.cli import main

        for arguments in (["--help"], ["plan", "--help"], ["deliver", "--help"]):
            with self.subTest(arguments=arguments), TemporaryDirectory() as temporary:
                root = Path(temporary)
                calls: list[str] = []

                def planning_factory(_path):
                    calls.append("planning")
                    raise AssertionError("planning factory called by help")

                def delivery_factory(_path, **_kwargs):
                    calls.append("delivery")
                    raise AssertionError("delivery factory called by help")

                with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                    with self.assertRaises(SystemExit) as raised:
                        main(
                            arguments,
                            planning_factory=planning_factory,
                            delivery_factory=delivery_factory,
                            cwd=root,
                        )

                self.assertEqual(raised.exception.code, 0)
                self.assertEqual(calls, [])
                self.assertFalse((root / ".data").exists())

    def test_module_help_commands_exit_zero_without_database_side_effects(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(repository_root / "src")
        commands = (
            [sys.executable, "-m", "foreign_trade_geo_agent", "--help"],
            [sys.executable, "-m", "foreign_trade_geo_agent", "plan", "--help"],
            [sys.executable, "-m", "foreign_trade_geo_agent", "deliver", "--help"],
        )
        for command in commands:
            with self.subTest(command=command), TemporaryDirectory() as temporary:
                root = Path(temporary)
                completed = subprocess.run(
                    command,
                    cwd=root,
                    env=environment,
                    capture_output=True,
                    text=True,
                    check=False,
                )

                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertIn("usage:", completed.stdout)
                self.assertFalse((root / ".data").exists())


class PlanCliTests(unittest.TestCase):
    def test_success_maps_arguments_and_prints_delivery_handoff(self) -> None:
        workflow = FakePlanningWorkflow(planning_result())
        factory_paths: list[Path] = []

        def factory(path: Path):
            factory_paths.append(path)
            return workflow

        with TemporaryDirectory() as temporary, patch.dict(
            os.environ,
            {
                "DEEPSEEK_API_KEY": "deepseek-dummy",
                "TAVILY_API_KEY": "tavily-dummy",
            },
            clear=True,
        ):
            root = Path(temporary)
            db_path = root / "runtime" / "custom.sqlite3"
            code, stdout, stderr = invoke_main(
                [
                    "plan",
                    "--site",
                    "https://manufacturer.example",
                    "--question",
                    "What content should we create?",
                    "--language",
                    "zh-CN",
                    "--db",
                    str(db_path),
                ],
                planning_factory=factory,
                cwd=root,
            )

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(factory_paths, [db_path])
        self.assertEqual(
            workflow.requests,
            [
                EndToEndRunRequest(
                    site_url="https://manufacturer.example",
                    research_question="What content should we create?",
                    target_language="zh-CN",
                )
            ],
        )
        payload = json.loads(stdout)
        self.assertEqual(payload["run_id"], RUN_ID)
        self.assertEqual(payload["status"], "succeeded")
        self.assertEqual(payload["site_key"], "https://manufacturer.example:443")
        self.assertEqual(payload["content_draft_artifact_id"], ARTIFACT_ID)
        self.assertTrue(payload["requires_human_review"])
        self.assertEqual([item["draft_id"] for item in payload["drafts"]], ["D1", "D2"])
        self.assertEqual(payload["drafts"][0]["title"], "Chemical compatibility guide")
        self.assertEqual(payload["drafts"][1]["type"], "NEW_RESOURCE_DRAFT")

    def test_default_database_path_is_passed_to_factory(self) -> None:
        paths: list[Path] = []
        workflow = FakePlanningWorkflow(planning_result())

        def factory(path: Path):
            paths.append(path)
            return workflow

        with TemporaryDirectory() as temporary, patch.dict(
            os.environ,
            {
                "DEEPSEEK_API_KEY": "deepseek-dummy",
                "TAVILY_API_KEY": "tavily-dummy",
            },
            clear=True,
        ):
            code, _, _ = invoke_main(
                [
                    "plan",
                    "--site",
                    "https://manufacturer.example",
                    "--question",
                    "Question",
                ],
                planning_factory=factory,
                cwd=Path(temporary),
            )

        self.assertEqual(code, 0)
        self.assertEqual(paths, [Path(".data/history.sqlite3")])

    def test_perplexity_key_is_not_required(self) -> None:
        workflow = FakePlanningWorkflow(planning_result())
        with TemporaryDirectory() as temporary, patch.dict(
            os.environ,
            {
                "DEEPSEEK_API_KEY": "deepseek-dummy",
                "TAVILY_API_KEY": "tavily-dummy",
            },
            clear=True,
        ):
            code, _, _ = invoke_main(
                [
                    "plan",
                    "--site",
                    "https://manufacturer.example",
                    "--question",
                    "Question",
                ],
                planning_factory=lambda _path: workflow,
                cwd=Path(temporary),
            )

        self.assertEqual(code, 0)
        self.assertEqual(len(workflow.requests), 1)

    def test_missing_plan_credentials_are_safe_and_skip_construction(self) -> None:
        cases = (
            ({"TAVILY_API_KEY": "tavily-dummy"}, "DEEPSEEK_API_KEY"),
            ({"DEEPSEEK_API_KEY": "deepseek-dummy"}, "TAVILY_API_KEY"),
        )
        for environment, missing_name in cases:
            with self.subTest(missing_name=missing_name), TemporaryDirectory() as temporary:
                calls: list[Path] = []
                with patch.dict(os.environ, environment, clear=True):
                    code, stdout, stderr = invoke_main(
                        [
                            "plan",
                            "--site",
                            "https://manufacturer.example",
                            "--question",
                            "Question",
                        ],
                        planning_factory=lambda path: calls.append(path),
                        cwd=Path(temporary),
                    )

                self.assertEqual(code, 2)
                self.assertEqual(stdout, "")
                self.assertIn(
                    f"Missing required environment variable: {missing_name}",
                    stderr,
                )
                self.assertEqual(calls, [])

    def test_failed_run_prints_safe_persisted_state_and_returns_one(self) -> None:
        workflow = FakePlanningWorkflow(planning_result(status=RunStatus.FAILED))
        with TemporaryDirectory() as temporary, patch.dict(
            os.environ,
            {
                "DEEPSEEK_API_KEY": "deepseek-dummy",
                "TAVILY_API_KEY": "tavily-dummy",
            },
            clear=True,
        ):
            code, stdout, stderr = invoke_main(
                [
                    "plan",
                    "--site",
                    "https://manufacturer.example",
                    "--question",
                    "Question",
                ],
                planning_factory=lambda _path: workflow,
                cwd=Path(temporary),
            )

        self.assertEqual(code, 1)
        self.assertEqual(stderr, "")
        payload = json.loads(stdout)
        self.assertEqual(payload["run_id"], RUN_ID)
        self.assertEqual(payload["status"], "failed")
        self.assertEqual(payload["stopped_stage"], "content_draft")
        self.assertEqual(payload["failure_kind"], "content_draft.invalid_output")
        self.assertEqual(len(payload["artifacts"]), 2)

    def test_unexpected_exception_does_not_print_secret_sentinel(self) -> None:
        sentinel = "SECRET_SENTINEL_7f338e"
        workflow = FakePlanningWorkflow(error=RuntimeError(sentinel))
        with TemporaryDirectory() as temporary, patch.dict(
            os.environ,
            {
                "DEEPSEEK_API_KEY": "deepseek-dummy",
                "TAVILY_API_KEY": "tavily-dummy",
            },
            clear=True,
        ):
            code, stdout, stderr = invoke_main(
                [
                    "plan",
                    "--site",
                    "https://manufacturer.example",
                    "--question",
                    "Question",
                ],
                planning_factory=lambda _path: workflow,
                cwd=Path(temporary),
            )

        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        self.assertIn("Planning failed unexpectedly.", stderr)
        self.assertNotIn(sentinel, stdout + stderr)


class DeliverCliTests(unittest.TestCase):
    def test_success_passes_exact_approval_and_prints_remote_result(self) -> None:
        workflow = FakeDeliveryWorkflow(
            delivery_result(
                WordPressDeliveryStatus.SUCCESS,
                WordPressAttemptState.SUCCESS,
            )
        )
        factory_calls: list[dict[str, object]] = []

        def factory(path: Path, **kwargs):
            factory_calls.append({"path": path, **kwargs})
            return workflow

        username = "wp-user-sentinel"
        password = "wp-password-sentinel"
        with TemporaryDirectory() as temporary, patch.dict(
            os.environ,
            {
                "WORDPRESS_USERNAME": username,
                "WORDPRESS_APPLICATION_PASSWORD": password,
            },
            clear=True,
        ):
            root = Path(temporary)
            db_path = root / "runtime" / "history.sqlite3"
            code, stdout, stderr = invoke_main(
                [
                    "deliver",
                    "--run-id",
                    RUN_ID,
                    "--artifact-id",
                    ARTIFACT_ID,
                    "--draft-id",
                    "D2",
                    "--site",
                    "https://customer.example",
                    "--title",
                    "Approved title",
                    "--db",
                    str(db_path),
                ],
                delivery_factory=factory,
                cwd=root,
            )

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(
            factory_calls,
            [
                {
                    "path": db_path,
                    "target_site_url": "https://customer.example",
                    "username": username,
                    "application_password": password,
                }
            ],
        )
        self.assertEqual(
            workflow.requests,
            [
                ApprovedWordPressDraftDeliveryRequest(
                    planning_run_id=RUN_ID,
                    content_draft_artifact_id=ARTIFACT_ID,
                    draft_id="D2",
                    target_site_url="https://customer.example",
                    title_override="Approved title",
                )
            ],
        )
        payload = json.loads(stdout)
        self.assertEqual(payload["selected_draft_id"], "D2")
        self.assertEqual(payload["delivery_status"], "success")
        self.assertEqual(payload["attempt_id"], ATTEMPT_ID)
        self.assertEqual(payload["attempt_outcome"], "success")
        self.assertEqual(payload["remote_post_id"], 41)
        self.assertEqual(payload["remote_link"], "https://customer.example/?p=41")
        self.assertFalse(payload["reconciliation_required"])
        self.assertNotIn(username, stdout + stderr)
        self.assertNotIn(password, stdout + stderr)

    def test_delivery_outcomes_map_to_documented_exit_codes(self) -> None:
        cases = (
            (
                WordPressDeliveryStatus.FAILED_DEFINITELY,
                WordPressAttemptState.FAILED_DEFINITELY,
                1,
                False,
            ),
            (
                WordPressDeliveryStatus.UNKNOWN,
                WordPressAttemptState.UNKNOWN,
                3,
                True,
            ),
            (
                WordPressDeliveryStatus.BLOCKED,
                WordPressAttemptState.SUCCESS,
                0,
                False,
            ),
            (
                WordPressDeliveryStatus.BLOCKED,
                WordPressAttemptState.PENDING,
                3,
                True,
            ),
            (
                WordPressDeliveryStatus.BLOCKED,
                WordPressAttemptState.UNKNOWN,
                3,
                True,
            ),
        )
        for status, attempt_outcome, expected_code, reconcile in cases:
            with self.subTest(status=status, attempt_outcome=attempt_outcome), TemporaryDirectory() as temporary, patch.dict(
                os.environ,
                {
                    "WORDPRESS_USERNAME": "wp-user",
                    "WORDPRESS_APPLICATION_PASSWORD": "wp-password",
                },
                clear=True,
            ):
                workflow = FakeDeliveryWorkflow(delivery_result(status, attempt_outcome))
                code, stdout, stderr = invoke_main(
                    [
                        "deliver",
                        "--run-id",
                        RUN_ID,
                        "--artifact-id",
                        ARTIFACT_ID,
                        "--draft-id",
                        "D2",
                        "--site",
                        "https://customer.example",
                    ],
                    delivery_factory=lambda _path, **_kwargs: workflow,
                    cwd=Path(temporary),
                )

                self.assertEqual(code, expected_code)
                self.assertEqual(stderr, "")
                payload = json.loads(stdout)
                self.assertEqual(payload["reconciliation_required"], reconcile)
                if reconcile:
                    self.assertEqual(
                        payload["operator_action"],
                        "manual reconciliation required",
                    )
                else:
                    self.assertNotIn("operator_action", payload)
                self.assertEqual(len(workflow.requests), 1)

    def test_missing_wordpress_credentials_skip_delivery_construction(self) -> None:
        cases = (
            (
                {"WORDPRESS_APPLICATION_PASSWORD": "wp-password"},
                "WORDPRESS_USERNAME",
            ),
            ({"WORDPRESS_USERNAME": "wp-user"}, "WORDPRESS_APPLICATION_PASSWORD"),
        )
        for environment, missing_name in cases:
            with self.subTest(missing_name=missing_name), TemporaryDirectory() as temporary:
                calls: list[object] = []
                with patch.dict(os.environ, environment, clear=True):
                    code, stdout, stderr = invoke_main(
                        [
                            "deliver",
                            "--run-id",
                            RUN_ID,
                            "--artifact-id",
                            ARTIFACT_ID,
                            "--draft-id",
                            "D2",
                            "--site",
                            "https://customer.example",
                        ],
                        delivery_factory=lambda *args, **kwargs: calls.append(
                            (args, kwargs)
                        ),
                        cwd=Path(temporary),
                    )

                self.assertEqual(code, 2)
                self.assertEqual(stdout, "")
                self.assertIn(
                    f"Missing required environment variable: {missing_name}",
                    stderr,
                )
                self.assertEqual(calls, [])

    def test_delivery_exception_does_not_print_credentials_or_exception(self) -> None:
        username = "WP_USER_SECRET_91d2"
        password = "WP_PASSWORD_SECRET_e82a"
        error_secret = "REMOTE_SECRET_7b12"
        workflow = FakeDeliveryWorkflow(error=RuntimeError(error_secret))
        with TemporaryDirectory() as temporary, patch.dict(
            os.environ,
            {
                "WORDPRESS_USERNAME": username,
                "WORDPRESS_APPLICATION_PASSWORD": password,
            },
            clear=True,
        ):
            code, stdout, stderr = invoke_main(
                [
                    "deliver",
                    "--run-id",
                    RUN_ID,
                    "--artifact-id",
                    ARTIFACT_ID,
                    "--draft-id",
                    "D2",
                    "--site",
                    "https://customer.example",
                ],
                delivery_factory=lambda _path, **_kwargs: workflow,
                cwd=Path(temporary),
            )

        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        self.assertIn("Delivery failed unexpectedly.", stderr)
        for secret in (username, password, error_secret):
            self.assertNotIn(secret, stdout + stderr)

    def test_batch_delivery_option_is_rejected_before_runtime_construction(self) -> None:
        from foreign_trade_geo_agent.cli import main

        calls: list[object] = []
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit) as raised:
                main(
                    [
                        "deliver",
                        "--run-id",
                        RUN_ID,
                        "--artifact-id",
                        ARTIFACT_ID,
                        "--draft-id",
                        "D2",
                        "--site",
                        "https://customer.example",
                        "--deliver-all",
                    ],
                    delivery_factory=lambda *args, **kwargs: calls.append(
                        (args, kwargs)
                    ),
                )

        self.assertEqual(raised.exception.code, 2)
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
