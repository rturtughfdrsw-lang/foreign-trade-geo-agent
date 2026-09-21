from types import SimpleNamespace
import unittest

from foreign_trade_geo_agent.adapters.geo_optimizer import GeoOptimizerAdapter
from foreign_trade_geo_agent.core.audit import (
    AuditEvidence,
    AuditEvidenceCategory,
    AuditEvidenceOutcome,
    AuditStatus,
    CitabilitySummary,
    SiteAuditResult,
)


def complete_third_party_result(**overrides: object) -> SimpleNamespace:
    result = SimpleNamespace(
        url="https://example.com",
        timestamp="2026-09-21T10:00:00+00:00",
        score=42,
        band="needs-work",
        score_breakdown={"robots": 8, "llms": 4, "meta": 9},
        recommendations=["Review the observed audit gaps."],
        error=None,
        http_status=200,
        audit_duration_ms=1234,
        robots=SimpleNamespace(
            found=True,
            bots_allowed=["GPTBot"],
            bots_missing=["ClaudeBot"],
            bots_blocked=["CCBot"],
            bots_partial=["Google-Extended"],
            citation_bots_ok=False,
            crawl_delay=2.5,
            citation_bots_explicit=False,
        ),
        llms=SimpleNamespace(
            found=True,
            has_h1=True,
            has_description=False,
            has_sections=True,
            has_links=True,
            word_count=120,
            has_full=False,
            sections_count=3,
            links_count=4,
            has_blockquote=False,
            has_optional_section=False,
            companion_files_hint=False,
            validation_warnings=["Missing optional section"],
        ),
        meta=SimpleNamespace(
            has_title=True,
            has_description=False,
            has_canonical=True,
            has_og_title=False,
            has_og_description=False,
            has_og_image=False,
            title_text="Sensitive title text that must not be retained",
            description_text="Sensitive description that must not be retained",
            description_length=0,
            title_length=52,
            canonical_url="https://example.com/",
            x_robots_noindex=False,
            x_robots_tag="",
            has_noai=False,
            noai_value="",
        ),
        schema=SimpleNamespace(
            found_types=["Organization", "Product"],
            has_website=False,
            has_webapp=False,
            has_faq=False,
            has_article=False,
            has_organization=True,
            has_howto=False,
            has_person=False,
            has_product=True,
            raw_schemas=[{"@type": "Product", "description": "do not retain"}],
            any_schema_found=True,
            has_sameas=True,
            sameas_urls=["https://www.linkedin.com/company/example"],
            has_date_modified=False,
            schema_richness_score=7,
            avg_attributes_per_schema=4.5,
            ecommerce_signals={"price": True},
            json_parse_errors=1,
            schema_missing_fields={"Product": ["offers", "sku"]},
            incomplete_schema_types=["Product"],
        ),
        content=SimpleNamespace(
            has_h1=True,
            heading_count=4,
            has_numbers=True,
            has_links=True,
            word_count=850,
            h1_text="Sensitive heading text that must not be retained",
            numbers_count=6,
            external_links_count=3,
            has_heading_hierarchy=True,
            has_lists_or_tables=True,
            has_front_loading=False,
        ),
        ai_discovery=SimpleNamespace(
            has_well_known_ai=False,
            has_summary=True,
            has_faq=False,
            has_service=False,
            summary_valid=False,
            faq_count=0,
            endpoints_found=1,
            has_webmcp_declaration=True,
            webmcp_declared_tool_count=2,
        ),
        citability=SimpleNamespace(
            methods=[SimpleNamespace(name="do-not-copy")],
            total_score=31,
            grade="low",
            top_improvements=["Add sourced statistics", "Add attributed quotes"],
            raw_score=65,
            max_possible=210,
        ),
    )
    for key, value in overrides.items():
        setattr(result, key, value)
    return result


def evidence_by_key(result: SiteAuditResult) -> dict[str, AuditEvidence]:
    return {item.check_key: item for item in result.evidence}


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

    def test_legacy_constructor_gets_empty_optional_audit_details(self) -> None:
        result = SiteAuditResult(
            url="https://example.com",
            status=AuditStatus.SUCCESS,
            score=80,
            band="good",
            score_breakdown={},
            recommendations=(),
            error=None,
            source="test",
            source_version="1.0",
        )

        self.assertEqual(result.evidence, ())
        self.assertIsNone(result.citability)
        self.assertIsNone(result.http_status)
        self.assertIsNone(result.audited_at)
        self.assertIsNone(result.audit_duration_ms)


class AuditEvidenceContractTests(unittest.TestCase):
    def test_accepts_only_approved_bounded_value_types(self) -> None:
        valid_values = (
            None,
            True,
            3,
            1.5,
            "observed",
            ("one", "two"),
        )
        for value in valid_values:
            with self.subTest(value=value):
                evidence = AuditEvidence(
                    category=AuditEvidenceCategory.META,
                    check_key="description.present",
                    observed_value=value,
                    outcome=AuditEvidenceOutcome.OBSERVED,
                    provider_field="meta.has_description",
                )
                self.assertEqual(evidence.observed_value, value)

        invalid_values = (
            ["not", "a", "tuple"],
            {"unbounded": "payload"},
            object(),
            ("valid", 1),
        )
        for value in invalid_values:
            with self.subTest(value=type(value).__name__):
                with self.assertRaises((TypeError, ValueError)):
                    AuditEvidence(
                        category=AuditEvidenceCategory.META,
                        check_key="description.present",
                        observed_value=value,  # type: ignore[arg-type]
                        outcome=AuditEvidenceOutcome.OBSERVED,
                        provider_field="meta.has_description",
                    )

    def test_rejects_oversized_string_and_tuple_values(self) -> None:
        base = {
            "category": AuditEvidenceCategory.META,
            "check_key": "description.present",
            "outcome": AuditEvidenceOutcome.OBSERVED,
            "provider_field": "meta.has_description",
        }
        with self.assertRaises(ValueError):
            AuditEvidence(observed_value="x" * 257, **base)
        with self.assertRaises(ValueError):
            AuditEvidence(observed_value=tuple("x" for _ in range(21)), **base)
        with self.assertRaises(ValueError):
            AuditEvidence(observed_value=("x" * 129,), **base)

    def test_citability_summary_rejects_unbounded_improvements(self) -> None:
        with self.assertRaises(ValueError):
            CitabilitySummary(
                score=20,
                grade="low",
                improvements=tuple(f"item-{number}" for number in range(6)),
            )
        with self.assertRaises(ValueError):
            CitabilitySummary(
                score=20,
                grade="low",
                improvements=("x" * 257,),
            )


class GeoOptimizerEvidenceMappingTests(unittest.TestCase):
    def test_maps_first_release_categories_without_sensitive_raw_content(self) -> None:
        result = GeoOptimizerAdapter(
            audit_func=lambda url: complete_third_party_result(),
            source_version="4.18.1",
        ).audit_site("https://example.com")
        mapped = evidence_by_key(result)

        self.assertEqual(result.http_status, 200)
        self.assertEqual(result.audited_at, "2026-09-21T10:00:00+00:00")
        self.assertEqual(result.audit_duration_ms, 1234)
        self.assertEqual(
            result.citability,
            CitabilitySummary(
                score=31,
                grade="low",
                improvements=("Add sourced statistics", "Add attributed quotes"),
            ),
        )
        self.assertEqual(mapped["robots.file_detected"].outcome, AuditEvidenceOutcome.PRESENT)
        self.assertEqual(mapped["robots.ai_crawlers.allowed"].observed_value, ("GPTBot",))
        self.assertEqual(mapped["robots.ai_crawlers.blocked"].outcome, AuditEvidenceOutcome.OBSERVED)
        self.assertEqual(mapped["llms.description.present"].outcome, AuditEvidenceOutcome.ABSENT)
        self.assertEqual(mapped["meta.description.present"].outcome, AuditEvidenceOutcome.ABSENT)
        self.assertEqual(mapped["schema.types"].observed_value, ("Organization", "Product"))
        self.assertEqual(mapped["schema.json_parse_errors"].outcome, AuditEvidenceOutcome.WARNING)
        self.assertEqual(mapped["content.word_count"].observed_value, 850)
        self.assertEqual(mapped["ai_discovery.summary.present"].outcome, AuditEvidenceOutcome.PRESENT)
        self.assertEqual(mapped["ai_discovery.summary.valid"].outcome, AuditEvidenceOutcome.ABSENT)

        provider_fields = {item.provider_field for item in result.evidence}
        self.assertNotIn("meta.title_text", provider_fields)
        self.assertNotIn("meta.description_text", provider_fields)
        self.assertNotIn("schema.raw_schemas", provider_fields)
        self.assertNotIn("content.h1_text", provider_fields)
        self.assertNotIn("citability.methods", provider_fields)
        self.assertNotIn("ai_discovery.has_webmcp_declaration", provider_fields)
        self.assertTrue(all(not isinstance(item.observed_value, dict) for item in result.evidence))

    def test_auxiliary_endpoint_defaults_are_not_claimed_as_confirmed_absence(self) -> None:
        provider = complete_third_party_result(
            robots=SimpleNamespace(found=False),
            llms=SimpleNamespace(found=False),
            ai_discovery=SimpleNamespace(
                has_well_known_ai=False,
                has_summary=False,
                has_faq=False,
                has_service=False,
                summary_valid=False,
                faq_count=0,
                endpoints_found=0,
            ),
        )

        result = GeoOptimizerAdapter(audit_func=lambda url: provider).audit_site(
            "https://example.com"
        )
        mapped = evidence_by_key(result)

        self.assertEqual(mapped["robots.file_detected"].outcome, AuditEvidenceOutcome.NOT_DETECTED)
        self.assertEqual(mapped["llms.file_detected"].outcome, AuditEvidenceOutcome.NOT_DETECTED)
        self.assertEqual(
            mapped["ai_discovery.summary.present"].outcome,
            AuditEvidenceOutcome.NOT_DETECTED,
        )
        self.assertEqual(
            mapped["ai_discovery.summary.valid"].outcome,
            AuditEvidenceOutcome.NOT_APPLICABLE,
        )
        self.assertNotIn("robots.ai_crawlers.allowed", mapped)
        self.assertNotIn("llms.word_count", mapped)

    def test_missing_nested_objects_are_marked_not_checked_without_crashing(self) -> None:
        provider = SimpleNamespace(
            url="https://example.com",
            score=82,
            band="good",
            score_breakdown={"technical": 82},
            recommendations=[],
            error=None,
        )

        result = GeoOptimizerAdapter(audit_func=lambda url: provider).audit_site(
            "https://example.com"
        )

        self.assertEqual(result.status, AuditStatus.SUCCESS)
        self.assertEqual(len(result.evidence), 6)
        self.assertTrue(
            all(item.outcome is AuditEvidenceOutcome.NOT_CHECKED for item in result.evidence)
        )
        self.assertIsNone(result.citability)
        self.assertIsNone(result.http_status)

    def test_unconfirmed_homepage_does_not_create_absent_page_evidence(self) -> None:
        provider = complete_third_party_result(http_status=0)

        result = GeoOptimizerAdapter(audit_func=lambda url: provider).audit_site(
            "https://example.com"
        )
        mapped = evidence_by_key(result)

        self.assertNotIn("meta.description.present", mapped)
        self.assertNotIn("schema.any_present", mapped)
        self.assertNotIn("content.h1.present", mapped)
        self.assertEqual(
            mapped["meta.check_available"].outcome,
            AuditEvidenceOutcome.NOT_CHECKED,
        )
        self.assertEqual(
            mapped["schema.check_available"].outcome,
            AuditEvidenceOutcome.NOT_CHECKED,
        )
        self.assertEqual(
            mapped["content.check_available"].outcome,
            AuditEvidenceOutcome.NOT_CHECKED,
        )

    def test_non_integer_http_status_does_not_confirm_homepage_checks(self) -> None:
        provider = complete_third_party_result(http_status=200.0)

        result = GeoOptimizerAdapter(audit_func=lambda url: provider).audit_site(
            "https://example.com"
        )
        mapped = evidence_by_key(result)

        self.assertIsNone(result.http_status)
        self.assertNotIn("meta.description.present", mapped)
        self.assertEqual(
            mapped["meta.check_available"].outcome,
            AuditEvidenceOutcome.NOT_CHECKED,
        )
        self.assertEqual(
            mapped["schema.check_available"].outcome,
            AuditEvidenceOutcome.NOT_CHECKED,
        )
        self.assertEqual(
            mapped["content.check_available"].outcome,
            AuditEvidenceOutcome.NOT_CHECKED,
        )

    def test_canonical_url_omits_credentials_and_query_values(self) -> None:
        provider = complete_third_party_result()
        provider.meta.canonical_url = (
            "https://user:secret@example.com/product?token=sensitive#details"
        )

        result = GeoOptimizerAdapter(audit_func=lambda url: provider).audit_site(
            "https://example.com"
        )
        canonical = evidence_by_key(result)["meta.canonical.url"]

        self.assertIsNone(canonical.observed_value)
        self.assertEqual(canonical.outcome, AuditEvidenceOutcome.UNKNOWN)
        self.assertNotIn("secret", canonical.note or "")
        self.assertNotIn("sensitive", canonical.note or "")

    def test_adapter_truncates_untrusted_collections_and_text_to_model_budgets(self) -> None:
        provider = complete_third_party_result()
        provider.robots.bots_allowed = ["bot-" + "x" * 200 for _ in range(30)]
        provider.llms.validation_warnings = ["warning-" + "y" * 400 for _ in range(12)]
        provider.citability.top_improvements = [
            "improvement-" + "z" * 400 for _ in range(12)
        ]

        result = GeoOptimizerAdapter(audit_func=lambda url: provider).audit_site(
            "https://example.com"
        )
        mapped = evidence_by_key(result)

        allowed = mapped["robots.ai_crawlers.allowed"].observed_value
        warnings = mapped["llms.validation_warnings"].observed_value
        self.assertIsInstance(allowed, tuple)
        self.assertEqual(len(allowed), 20)
        self.assertTrue(all(len(item) <= 128 for item in allowed))
        self.assertIsInstance(warnings, tuple)
        self.assertEqual(len(warnings), 5)
        self.assertTrue(all(len(item) <= 128 for item in warnings))
        self.assertIsNotNone(result.citability)
        self.assertEqual(len(result.citability.improvements), 5)  # type: ignore[union-attr]
        self.assertTrue(
            all(len(item) <= 256 for item in result.citability.improvements)  # type: ignore[union-attr]
        )

    def test_failed_provider_result_never_leaks_success_evidence(self) -> None:
        provider = complete_third_party_result(
            score=0,
            band="critical",
            error="HTTP 403",
            http_status=403,
        )

        result = GeoOptimizerAdapter(audit_func=lambda url: provider).audit_site(
            "https://example.com"
        )

        self.assertEqual(result.status, AuditStatus.FAILED)
        self.assertIsNone(result.score)
        self.assertEqual(result.evidence, ())
        self.assertIsNone(result.citability)
        self.assertEqual(result.http_status, 403)

    def test_actual_geo_optimizer_result_defaults_remain_offline_and_conservative(self) -> None:
        from geo_optimizer import AuditResult

        provider = AuditResult(url="https://example.com")
        provider.score = 10
        provider.band = "critical"
        provider.http_status = 200

        result = GeoOptimizerAdapter(audit_func=lambda url: provider).audit_site(
            "https://example.com"
        )
        mapped = evidence_by_key(result)

        self.assertEqual(result.status, AuditStatus.SUCCESS)
        self.assertEqual(mapped["robots.file_detected"].outcome, AuditEvidenceOutcome.NOT_DETECTED)
        self.assertEqual(mapped["llms.file_detected"].outcome, AuditEvidenceOutcome.NOT_DETECTED)

    def test_site_audit_result_rejects_more_than_total_evidence_budget(self) -> None:
        item = AuditEvidence(
            category=AuditEvidenceCategory.META,
            check_key="meta.title.present",
            observed_value=True,
            outcome=AuditEvidenceOutcome.PRESENT,
            provider_field="meta.has_title",
        )

        with self.assertRaises(ValueError):
            SiteAuditResult(
                url="https://example.com",
                status=AuditStatus.SUCCESS,
                score=80,
                band="good",
                score_breakdown={},
                recommendations=(),
                error=None,
                source="test",
                source_version="1.0",
                evidence=(item,) * 97,
            )


if __name__ == "__main__":
    unittest.main()
