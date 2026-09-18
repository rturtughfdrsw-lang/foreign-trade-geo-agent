from types import SimpleNamespace
import unittest

from foreign_trade_geo_agent.adapters.geo_optimizer import GeoOptimizerAdapter
from foreign_trade_geo_agent.core.audit import AuditStatus, SiteAuditResult


class GeoOptimizerAdapterTests(unittest.TestCase):
    def test_maps_successful_audit_to_core_result(self) -> None:
        third_party_result = SimpleNamespace(
            url="https://example.com",
            score=82,
            band="good",
            score_breakdown={"technical": 40, "content": 42},
            recommendations=["Add an llms.txt file", "Improve citations"],
            error=None,
        )
        adapter = GeoOptimizerAdapter(
            audit_func=lambda url: third_party_result,
            source_version="4.18.1",
        )

        result = adapter.audit_site("https://example.com")

        self.assertEqual(result.status, AuditStatus.SUCCESS)
        self.assertEqual(result.score, 82)
        self.assertEqual(result.band, "good")
        self.assertEqual(
            result.score_breakdown,
            {"technical": 40, "content": 42},
        )
        self.assertEqual(
            result.recommendations,
            ("Add an llms.txt file", "Improve citations"),
        )
        self.assertIsNone(result.error)
        self.assertEqual(result.source, "geo-optimizer-skill")
        self.assertEqual(result.source_version, "4.18.1")

    def test_maps_third_party_error_to_failure_without_zero_score(self) -> None:
        third_party_result = SimpleNamespace(
            url="https://example.com",
            score=0,
            band="critical",
            score_breakdown={},
            recommendations=[],
            error="Unsafe URL: URL points to a non-public address.",
        )
        adapter = GeoOptimizerAdapter(
            audit_func=lambda url: third_party_result,
            source_version="4.18.1",
        )

        result = adapter.audit_site("https://example.com")

        self.assertEqual(result.status, AuditStatus.FAILED)
        self.assertIsNone(result.score)
        self.assertIsNone(result.band)
        self.assertEqual(result.score_breakdown, {})
        self.assertEqual(result.recommendations, ())
        self.assertEqual(
            result.error,
            "Unsafe URL: URL points to a non-public address.",
        )

    def test_maps_unexpected_audit_exception_to_failure(self) -> None:
        def failing_audit(url: str) -> object:
            raise RuntimeError("upstream request failed")

        adapter = GeoOptimizerAdapter(
            audit_func=failing_audit,
            source_version="4.18.1",
        )

        result = adapter.audit_site("https://example.com")

        self.assertEqual(result.status, AuditStatus.FAILED)
        self.assertIsNone(result.score)
        self.assertIsNone(result.band)
        self.assertIn("RuntimeError", result.error or "")
        self.assertIn("upstream request failed", result.error or "")

    def test_rejects_contract_change_in_score_type(self) -> None:
        third_party_result = SimpleNamespace(
            url="https://example.com",
            score="82",
            band="good",
            score_breakdown={"technical": 40},
            recommendations=["Add an llms.txt file"],
            error=None,
        )
        adapter = GeoOptimizerAdapter(audit_func=lambda url: third_party_result)

        with self.assertRaises(TypeError):
            adapter.audit_site("https://example.com")

    def test_rejects_contract_change_in_score_breakdown_type(self) -> None:
        third_party_result = SimpleNamespace(
            url="https://example.com",
            score=82,
            band="good",
            score_breakdown={"technical": "40"},
            recommendations=["Add an llms.txt file"],
            error=None,
        )
        adapter = GeoOptimizerAdapter(audit_func=lambda url: third_party_result)

        with self.assertRaises(TypeError):
            adapter.audit_site("https://example.com")

    def test_rejects_contract_change_in_recommendations_type(self) -> None:
        third_party_result = SimpleNamespace(
            url="https://example.com",
            score=82,
            band="good",
            score_breakdown={"technical": 40},
            recommendations=["Add an llms.txt file", 1],
            error=None,
        )
        adapter = GeoOptimizerAdapter(audit_func=lambda url: third_party_result)

        with self.assertRaises(TypeError):
            adapter.audit_site("https://example.com")


class SiteAuditResultTests(unittest.TestCase):
    def test_success_requires_a_score_and_no_error(self) -> None:
        with self.assertRaises(ValueError):
            SiteAuditResult(
                url="https://example.com",
                status=AuditStatus.SUCCESS,
                score=None,
                band=None,
                score_breakdown={},
                recommendations=(),
                error=None,
                source="test",
                source_version="1.0",
            )

    def test_failure_requires_no_score_and_an_error(self) -> None:
        with self.assertRaises(ValueError):
            SiteAuditResult(
                url="https://example.com",
                status=AuditStatus.FAILED,
                score=0,
                band=None,
                score_breakdown={},
                recommendations=(),
                error="network failure",
                source="test",
                source_version="1.0",
            )


if __name__ == "__main__":
    unittest.main()
