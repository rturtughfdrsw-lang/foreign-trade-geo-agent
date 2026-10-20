from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DocumentationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.readme = (ROOT / "README.md").read_text(encoding="utf-8")
        cls.architecture = (ROOT / "docs" / "architecture.md").read_text(
            encoding="utf-8"
        )

    def test_readme_describes_demo_and_live_profiles(self) -> None:
        self.assertIn("Demo profile", self.readme)
        self.assertIn("Live profile", self.readme)
        self.assertIn(".data/demo-ui/history.sqlite3", self.readme)
        self.assertIn(".data/live-ui/history.sqlite3", self.readme)

    def test_readme_documents_public_https_and_bounded_limits(self) -> None:
        self.assertIn("public HTTPS", self.readme)
        self.assertIn("5 pages", self.readme)
        self.assertIn("depth 1", self.readme)
        self.assertIn("120 seconds", self.readme)
        self.assertIn("2048", self.readme)

    def test_readme_states_live_stops_before_draft_execution(self) -> None:
        self.assertIn("Live stops before Draft execution", self.readme)
        self.assertIn("INTAKE_EXECUTION_BLOCKED", self.readme)
        self.assertIn("does not call WordPress", self.readme)

    def test_architecture_documents_crawl_based_planning_audit(self) -> None:
        self.assertIn("CrawlSeoAuditor", self.architecture)
        self.assertIn("crawl-derived SEO audit", self.architecture)
        self.assertIn("does not perform network access", self.architecture)

    def test_manual_web_smoke_is_marked_operator_only(self) -> None:
        self.assertIn("Operator-only manual Live smoke", self.readme)
        self.assertIn("must not run in automated tests", self.readme)

    def test_failure_kind_is_documented_as_internal_not_persisted(self) -> None:
        self.assertIn("PlanningFailure.failure_kind", self.architecture)
        self.assertIn("process-local and is not persisted", self.architecture)
        self.assertIn("sanitized run error", self.architecture)


if __name__ == "__main__":
    unittest.main()
