from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import os
from pathlib import Path
import runpy
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


class DemoEntrypointTests(unittest.TestCase):
    def test_entrypoint_defaults_to_loopback_and_isolated_absolute_database(self) -> None:
        from foreign_trade_geo_agent.web import __main__ as entrypoint

        output = StringIO()
        with TemporaryDirectory() as directory:
            previous = Path.cwd()
            os.chdir(directory)
            try:
                expected_db = (
                    Path(directory) / ".data" / "demo-ui" / "history.sqlite3"
                ).resolve()
                with (
                    patch.object(entrypoint.uvicorn, "run") as run,
                    redirect_stdout(output),
                ):
                    entrypoint.main()
            finally:
                os.chdir(previous)

        run.assert_called_once_with(
            "foreign_trade_geo_agent.web.app:create_app",
            factory=True,
            host="127.0.0.1",
            port=8000,
        )
        self.assertIn(str(expected_db), output.getvalue())
        self.assertIn("http://127.0.0.1:8000", output.getvalue())
        self.assertNotIn("0.0.0.0", output.getvalue())

    def test_package_module_execution_reaches_uvicorn_factory(self) -> None:
        output = StringIO()
        module_name = "foreign_trade_geo_agent.web.__main__"
        imported_module = sys.modules.pop(module_name, None)
        with TemporaryDirectory() as directory:
            previous = Path.cwd()
            os.chdir(directory)
            try:
                expected_db = (
                    Path(directory) / ".data" / "demo-ui" / "history.sqlite3"
                ).resolve()
                with patch("uvicorn.run") as run, redirect_stdout(output):
                    runpy.run_module(
                        "foreign_trade_geo_agent.web",
                        run_name="__main__",
                    )
            finally:
                os.chdir(previous)
                if imported_module is not None:
                    sys.modules[module_name] = imported_module

        run.assert_called_once_with(
            "foreign_trade_geo_agent.web.app:create_app",
            factory=True,
            host="127.0.0.1",
            port=8000,
        )
        self.assertIn(str(expected_db), output.getvalue())
        self.assertIn("http://127.0.0.1:8000", output.getvalue())

    def test_readme_documents_demo_extra_command_and_no_external_contact(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        for text in (
            'python -m pip install -e ".[demo]"',
            "python -m foreign_trade_geo_agent.web",
            "http://127.0.0.1:8000",
            "Demo Mode",
            "customer websites",
            "model or search providers",
            "WordPress",
        ):
            self.assertIn(text, readme)
        self.assertNotIn("--host 0.0.0.0", readme)


if __name__ == "__main__":
    unittest.main()
