from contextlib import chdir, redirect_stdout
from io import StringIO
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import local_env


FAKE_ENV_KEY = "temporary-dotenv-secret"
FAKE_PROCESS_KEY = "temporary-process-secret"


class LocalEnvTests(unittest.TestCase):
    def test_loads_requested_key_from_project_dotenv(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text(
                f"TAVILY_API_KEY={FAKE_ENV_KEY}\n",
                encoding="utf-8",
            )

            with patch.dict(os.environ, {}, clear=True):
                local_env.load_api_keys("TAVILY_API_KEY", project_root=root)

                self.assertEqual(os.environ["TAVILY_API_KEY"], FAKE_ENV_KEY)

    def test_missing_dotenv_is_safe(self) -> None:
        with TemporaryDirectory() as directory:
            with patch.dict(os.environ, {}, clear=True):
                local_env.load_api_keys(
                    "TAVILY_API_KEY",
                    project_root=Path(directory),
                )

                self.assertNotIn("TAVILY_API_KEY", os.environ)

    def test_process_environment_takes_precedence(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text(
                f"TAVILY_API_KEY={FAKE_ENV_KEY}\n",
                encoding="utf-8",
            )

            with patch.dict(
                os.environ,
                {"TAVILY_API_KEY": FAKE_PROCESS_KEY},
                clear=True,
            ):
                local_env.load_api_keys("TAVILY_API_KEY", project_root=root)

                self.assertEqual(os.environ["TAVILY_API_KEY"], FAKE_PROCESS_KEY)

    def test_loads_only_requested_key(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text(
                (
                    f"TAVILY_API_KEY={FAKE_ENV_KEY}\n"
                    "DEEPSEEK_API_KEY=unrequested-secret\n"
                ),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {}, clear=True):
                local_env.load_api_keys("TAVILY_API_KEY", project_root=root)

                self.assertEqual(os.environ["TAVILY_API_KEY"], FAKE_ENV_KEY)
                self.assertNotIn("DEEPSEEK_API_KEY", os.environ)

    def test_dotenv_example_is_not_loaded(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env.example").write_text(
                f"TAVILY_API_KEY={FAKE_ENV_KEY}\n",
                encoding="utf-8",
            )

            with patch.dict(os.environ, {}, clear=True):
                local_env.load_api_keys("TAVILY_API_KEY", project_root=root)

                self.assertNotIn("TAVILY_API_KEY", os.environ)

    def test_key_value_is_not_printed(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text(
                f"TAVILY_API_KEY={FAKE_ENV_KEY}\n",
                encoding="utf-8",
            )
            output = StringIO()

            with patch.dict(os.environ, {}, clear=True):
                with redirect_stdout(output):
                    local_env.load_api_keys("TAVILY_API_KEY", project_root=root)

            self.assertNotIn(FAKE_ENV_KEY, output.getvalue())

    def test_explicit_project_root_is_independent_of_working_directory(self) -> None:
        with TemporaryDirectory() as project_directory:
            with TemporaryDirectory() as working_directory:
                root = Path(project_directory)
                (root / ".env").write_text(
                    f"TAVILY_API_KEY={FAKE_ENV_KEY}\n",
                    encoding="utf-8",
                )

                with patch.dict(os.environ, {}, clear=True):
                    with patch.object(local_env, "PROJECT_ROOT", root):
                        with chdir(working_directory):
                            local_env.load_api_keys("TAVILY_API_KEY")

                    self.assertEqual(
                        os.environ["TAVILY_API_KEY"],
                        FAKE_ENV_KEY,
                    )


if __name__ == "__main__":
    unittest.main()
