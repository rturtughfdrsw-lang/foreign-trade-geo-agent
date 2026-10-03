from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = ROOT / "src" / "foreign_trade_geo_agent" / "web"


class DemoVisualPolishTests(unittest.TestCase):
    def test_stylesheet_defines_shared_visual_system(self) -> None:
        css = (WEB_ROOT / "static" / "app.css").read_text(encoding="utf-8")
        for selector in (
            ".workflow-rail",
            ".page-shell",
            ".context-bar",
            ".panel",
            ".eyebrow",
            ".technical-meta",
        ):
            with self.subTest(selector=selector):
                self.assertIn(selector, css)

    def test_rail_is_fixed_and_full_height_on_desktop(self) -> None:
        css = (WEB_ROOT / "static" / "app.css").read_text(encoding="utf-8")
        rail = css.split(".workflow-rail", 1)[1].split("}", 1)[0]
        self.assertIn("position: fixed", rail)
        self.assertIn("inset: 0", rail)

    def test_stylesheet_defines_screen_specific_components(self) -> None:
        css = (WEB_ROOT / "static" / "app.css").read_text(encoding="utf-8")
        for selector in (
            ".findings-panel",
            ".finding-list",
            ".score-primary",
            ".recommendation-list",
            ".source-link",
            ".change-product-header",
            ".priority-badge",
            ".target-summary",
            ".why-block",
            ".evidence-section",
            ".evidence-group",
            ".draft-primary-grid",
            ".draft-evidence-grid",
            ".draft-body",
            ".why-draft",
            ".warning-badge",
            ".heading-with-badge",
            ".review-readonly",
            ".phase-two-action",
            ".review-notes",
        ):
            with self.subTest(selector=selector):
                self.assertIn(selector, css)

    def test_stylesheet_defines_four_progress_states(self) -> None:
        css = (WEB_ROOT / "static" / "app.css").read_text(encoding="utf-8")
        for selector in (
            ".stage-complete",
            ".stage-running",
            ".stage-waiting",
            ".stage-failed",
        ):
            with self.subTest(selector=selector):
                self.assertIn(selector, css)


if __name__ == "__main__":
    unittest.main()
