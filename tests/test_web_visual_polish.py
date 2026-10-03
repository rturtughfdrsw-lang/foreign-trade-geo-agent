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

    def test_stylesheet_defines_phase2_components(self) -> None:
        css = (WEB_ROOT / "static" / "app.css").read_text(encoding="utf-8")
        for selector in (
            ".delivery-setup",
            ".delivery-facts",
            ".intent-check",
            ".delivery-result",
            ".verification-result",
        ):
            with self.subTest(selector=selector):
                self.assertIn(selector, css)

    def test_evidence_grids_collapse_at_medium_desktop_width(self) -> None:
        css = (WEB_ROOT / "static" / "app.css").read_text(encoding="utf-8")
        breakpoint = "@media (max-width: 1100px)"
        self.assertIn(breakpoint, css)
        medium_rule = css.split(breakpoint, 1)[1].split(
            "@media (max-width: 760px)",
            1,
        )[0]

        self.assertIn(".evidence-groups", medium_rule)
        self.assertIn(".draft-evidence-grid", medium_rule)
        self.assertIn("grid-template-columns: 1fr", medium_rule)

    def test_evidence_technical_text_wraps_safely(self) -> None:
        css = (WEB_ROOT / "static" / "app.css").read_text(encoding="utf-8")

        self.assertIn(".source-link", css)
        self.assertIn(".evidence-row code", css)
        self.assertIn(".technical-meta", css)
        self.assertIn("overflow-wrap: anywhere", css)


if __name__ == "__main__":
    unittest.main()
