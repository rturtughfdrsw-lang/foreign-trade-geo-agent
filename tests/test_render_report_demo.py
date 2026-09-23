import socket
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from scripts import render_report_demo


class RenderReportDemoTests(unittest.TestCase):
    def test_demo_requires_explicit_output_directory(self) -> None:
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
            render_report_demo.main([])

    def test_demo_generates_both_reports_without_network_access(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "reports"
            with (
                patch.object(
                    socket.socket,
                    "connect",
                    side_effect=AssertionError("demo attempted network access"),
                ),
                redirect_stdout(StringIO()),
            ):
                exit_code = render_report_demo.main([str(output_dir)])

            self.assertEqual(exit_code, 0)
            self.assertIn("# Site Optimization Report", (output_dir / "report.md").read_text(encoding="utf-8"))
            self.assertIn("<h1>Site Optimization Report</h1>", (output_dir / "report.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
