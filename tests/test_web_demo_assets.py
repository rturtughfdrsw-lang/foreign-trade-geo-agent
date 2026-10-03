from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = ROOT / "src" / "foreign_trade_geo_agent" / "web"


def _requirement_name(value: str) -> str:
    return re.split(r"[<>=!~\s]", value, maxsplit=1)[0].casefold()


class DemoPackagingTests(unittest.TestCase):
    def test_demo_extra_is_bounded_and_does_not_pollute_base_dependencies(self) -> None:
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        base = project["project"]["dependencies"]
        demo = project["project"]["optional-dependencies"]["demo"]
        base_names = {_requirement_name(item) for item in base}
        demo_by_name = {_requirement_name(item): item for item in demo}

        self.assertEqual(
            set(demo_by_name),
            {"fastapi", "uvicorn", "python-multipart"},
        )
        self.assertTrue(all("<" in item for item in demo))
        self.assertTrue(set(demo_by_name).isdisjoint(base_names))
        self.assertNotIn("jinja2", demo_by_name)

    def test_novacnc_manifest_and_required_fixture_files_are_packaged(self) -> None:
        fixture_root = WEB_ROOT / "fixtures" / "novacnc"
        manifest = json.loads(
            (fixture_root / "manifest.json").read_text(encoding="utf-8")
        )

        self.assertEqual(manifest["fixture_identity"], "novacnc-demo-v1")
        self.assertEqual(manifest["display_url"], "https://novacnc.example/")
        self.assertEqual(manifest["source_project"], "geo-test-site")
        self.assertTrue(manifest["source_revision"])
        self.assertTrue(manifest["capture_update_note"])
        for name in ("robots.txt", "index.html", "machines.html"):
            self.assertTrue((fixture_root / name).is_file(), name)

        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        package_data = project["tool"]["setuptools"]["package-data"]
        web_data = package_data["foreign_trade_geo_agent.web"]
        self.assertIn("fixtures/novacnc/*", web_data)
        self.assertIn("static/*", web_data)
        self.assertIn("templates/**/*.html", web_data)

    def test_htmx_is_pinned_local_and_license_is_present(self) -> None:
        script = (WEB_ROOT / "static" / "htmx-2.0.11.min.js").read_text(
            encoding="utf-8"
        )
        license_text = (WEB_ROOT / "static" / "HTMX-LICENSE.txt").read_text(
            encoding="utf-8"
        )

        self.assertIn('version:"2.0.11"', script)
        self.assertIn("Zero-Clause BSD", license_text)
        self.assertNotIn("cdn.jsdelivr.net", script)

    def test_base_package_import_does_not_import_fastapi(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import json, sys; "
                    "import foreign_trade_geo_agent; "
                    "print(json.dumps('fastapi' in sys.modules))"
                ),
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertEqual(json.loads(completed.stdout), False)


if __name__ == "__main__":
    unittest.main()
