"""Adapter for the geo-optimizer-skill Python API."""

from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from foreign_trade_geo_agent.core.audit import (
    MAX_CITABILITY_IMPROVEMENT_LENGTH,
    MAX_CITABILITY_IMPROVEMENTS,
    MAX_EVIDENCE_COUNT,
    MAX_EVIDENCE_STRING_LENGTH,
    MAX_EVIDENCE_TUPLE_ITEM_LENGTH,
    MAX_EVIDENCE_TUPLE_ITEMS,
    AuditEvidence,
    AuditEvidenceCategory,
    AuditEvidenceOutcome,
    AuditEvidenceValue,
    AuditStatus,
    CitabilitySummary,
    SiteAuditResult,
)


AuditCallable = Callable[[str], Any]


def _load_default_audit() -> tuple[AuditCallable, str]:
    import geo_optimizer

    return geo_optimizer.audit, geo_optimizer.__version__


class GeoOptimizerAdapter:
    """Translate geo-optimizer results into the application's core model."""

    source = "geo-optimizer-skill"
    max_warning_items = 5

    def __init__(
        self,
        audit_func: AuditCallable | None = None,
        source_version: str | None = None,
    ) -> None:
        if audit_func is None:
            audit_func, installed_version = _load_default_audit()
            source_version = source_version or installed_version

        self._audit_func = audit_func
        self._source_version = source_version or "unknown"

    def audit_site(self, url: str) -> SiteAuditResult:
        try:
            provider_result = self._audit_func(url)
        except Exception as exc:
            message = str(exc) or "no exception message"
            return self._failed_result(
                url=url,
                error=f"{self.source} raised {type(exc).__name__}: {message}",
            )

        result_url = self._require_str(getattr(provider_result, "url"), "url")
        provider_error = getattr(provider_result, "error")
        if provider_error is not None:
            error = self._require_str(provider_error, "error")
            error = error or f"{self.source} returned an unspecified error"
            return self._failed_result(
                url=result_url,
                error=error,
                http_status=self._optional_int(
                    getattr(provider_result, "http_status", None)
                ),
                audited_at=self._optional_str(
                    getattr(provider_result, "timestamp", None)
                ),
                audit_duration_ms=self._optional_int(
                    getattr(provider_result, "audit_duration_ms", None)
                ),
            )

        score = self._require_int(getattr(provider_result, "score"), "score")
        band = self._require_str(getattr(provider_result, "band"), "band")
        score_breakdown = self._copy_score_breakdown(
            getattr(provider_result, "score_breakdown")
        )
        recommendations = self._copy_recommendations(
            getattr(provider_result, "recommendations")
        )
        evidence = self._map_evidence(provider_result)

        return SiteAuditResult(
            url=result_url,
            status=AuditStatus.SUCCESS,
            score=score,
            band=band,
            score_breakdown=score_breakdown,
            recommendations=recommendations,
            error=None,
            source=self.source,
            source_version=self._source_version,
            evidence=evidence,
            citability=self._map_citability(
                getattr(provider_result, "citability", None)
            ),
            http_status=self._optional_int(
                getattr(provider_result, "http_status", None)
            ),
            audited_at=self._optional_str(
                getattr(provider_result, "timestamp", None)
            ),
            audit_duration_ms=self._optional_int(
                getattr(provider_result, "audit_duration_ms", None)
            ),
        )

    def _failed_result(
        self,
        url: str,
        error: str,
        *,
        http_status: int | None = None,
        audited_at: str | None = None,
        audit_duration_ms: int | None = None,
    ) -> SiteAuditResult:
        return SiteAuditResult(
            url=url,
            status=AuditStatus.FAILED,
            score=None,
            band=None,
            score_breakdown={},
            recommendations=(),
            error=error,
            source=self.source,
            source_version=self._source_version,
            http_status=http_status,
            audited_at=audited_at,
            audit_duration_ms=audit_duration_ms,
        )

    def _map_evidence(self, provider_result: object) -> tuple[AuditEvidence, ...]:
        evidence: list[AuditEvidence] = []
        self._map_robots(evidence, getattr(provider_result, "robots", None))
        self._map_llms(evidence, getattr(provider_result, "llms", None))
        http_status = getattr(provider_result, "http_status", None)
        homepage_checked = type(http_status) is int and http_status in (200, 203)
        if homepage_checked:
            self._map_meta(evidence, getattr(provider_result, "meta", None))
            self._map_schema(evidence, getattr(provider_result, "schema", None))
            self._map_content(evidence, getattr(provider_result, "content", None))
        else:
            self._add_not_checked(evidence, AuditEvidenceCategory.META, "meta")
            self._add_not_checked(evidence, AuditEvidenceCategory.SCHEMA, "schema")
            self._add_not_checked(evidence, AuditEvidenceCategory.CONTENT, "content")
        self._map_ai_discovery(
            evidence,
            getattr(provider_result, "ai_discovery", None),
        )
        return tuple(evidence)

    def _map_robots(self, target: list[AuditEvidence], value: object) -> None:
        category = AuditEvidenceCategory.ROBOTS
        if value is None:
            self._add_not_checked(target, category, "robots")
            return

        found = getattr(value, "found", None)
        self._add_detection(
            target,
            category,
            "robots.file_detected",
            found,
            "robots.found",
        )
        if found is not True:
            return

        for field_name, check_key in (
            ("bots_allowed", "robots.ai_crawlers.allowed"),
            ("bots_missing", "robots.ai_crawlers.missing_rules"),
            ("bots_blocked", "robots.ai_crawlers.blocked"),
            ("bots_partial", "robots.ai_crawlers.partial"),
        ):
            self._add_string_collection(
                target,
                category,
                check_key,
                getattr(value, field_name, None),
                f"robots.{field_name}",
            )

        crawl_delay = getattr(value, "crawl_delay", None)
        if crawl_delay is None:
            self._add(
                target,
                category,
                "robots.crawl_delay",
                None,
                AuditEvidenceOutcome.ABSENT,
                "robots.crawl_delay",
            )
        elif type(crawl_delay) in {int, float}:
            self._add(
                target,
                category,
                "robots.crawl_delay",
                crawl_delay,
                AuditEvidenceOutcome.OBSERVED,
                "robots.crawl_delay",
            )
        else:
            self._add_unknown(
                target,
                category,
                "robots.crawl_delay",
                "robots.crawl_delay",
            )

    def _map_llms(self, target: list[AuditEvidence], value: object) -> None:
        category = AuditEvidenceCategory.LLMS
        if value is None:
            self._add_not_checked(target, category, "llms")
            return

        found = getattr(value, "found", None)
        self._add_detection(
            target,
            category,
            "llms.file_detected",
            found,
            "llms.found",
        )
        if found is not True:
            return

        for field_name, check_key in (
            ("has_h1", "llms.h1.present"),
            ("has_description", "llms.description.present"),
            ("has_sections", "llms.sections.present"),
            ("has_links", "llms.links.present"),
            ("has_blockquote", "llms.blockquote.present"),
            ("has_optional_section", "llms.optional_section.present"),
        ):
            self._add_presence(
                target,
                category,
                check_key,
                getattr(value, field_name, None),
                f"llms.{field_name}",
            )
        for field_name, check_key in (
            ("word_count", "llms.word_count"),
            ("sections_count", "llms.sections_count"),
            ("links_count", "llms.links_count"),
        ):
            self._add_scalar(
                target,
                category,
                check_key,
                getattr(value, field_name, None),
                f"llms.{field_name}",
            )

        self._add_detection(
            target,
            category,
            "llms.full_file_detected",
            getattr(value, "has_full", None),
            "llms.has_full",
        )
        warnings = self._bounded_string_tuple(
            getattr(value, "validation_warnings", None),
            max_items=self.max_warning_items,
        )
        if warnings is None:
            self._add_unknown(
                target,
                category,
                "llms.validation_warnings",
                "llms.validation_warnings",
            )
        else:
            self._add(
                target,
                category,
                "llms.validation_warnings",
                warnings,
                (
                    AuditEvidenceOutcome.WARNING
                    if warnings
                    else AuditEvidenceOutcome.OBSERVED
                ),
                "llms.validation_warnings",
            )

    def _map_meta(self, target: list[AuditEvidence], value: object) -> None:
        category = AuditEvidenceCategory.META
        if value is None:
            self._add_not_checked(target, category, "meta")
            return

        for field_name, check_key in (
            ("has_title", "meta.title.present"),
            ("has_description", "meta.description.present"),
            ("has_canonical", "meta.canonical.present"),
            ("has_og_title", "meta.open_graph.title.present"),
            ("has_og_description", "meta.open_graph.description.present"),
            ("has_og_image", "meta.open_graph.image.present"),
            ("x_robots_noindex", "meta.x_robots_noindex"),
            ("has_noai", "meta.noai.present"),
        ):
            self._add_presence(
                target,
                category,
                check_key,
                getattr(value, field_name, None),
                f"meta.{field_name}",
            )
        for field_name, check_key in (
            ("title_length", "meta.title.length"),
            ("description_length", "meta.description.length"),
        ):
            self._add_scalar(
                target,
                category,
                check_key,
                getattr(value, field_name, None),
                f"meta.{field_name}",
            )
        self._add_canonical_url(
            target,
            getattr(value, "canonical_url", None),
        )
        for field_name, check_key in (
            ("x_robots_tag", "meta.x_robots_tag"),
            ("noai_value", "meta.noai.value"),
        ):
            self._add_bounded_string(
                target,
                category,
                check_key,
                getattr(value, field_name, None),
                f"meta.{field_name}",
            )

    def _add_canonical_url(
        self,
        target: list[AuditEvidence],
        value: object,
    ) -> None:
        category = AuditEvidenceCategory.META
        check_key = "meta.canonical.url"
        provider_field = "meta.canonical_url"
        if type(value) is not str:
            self._add_unknown(target, category, check_key, provider_field)
            return
        if not value:
            self._add(
                target,
                category,
                check_key,
                "",
                AuditEvidenceOutcome.OBSERVED,
                provider_field,
            )
            return
        try:
            parsed = urlsplit(value)
        except ValueError:
            self._add_unknown(target, category, check_key, provider_field)
            return
        if (
            parsed.scheme.casefold() not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
        ):
            self._add(
                target,
                category,
                check_key,
                None,
                AuditEvidenceOutcome.UNKNOWN,
                provider_field,
                note="Canonical URL was omitted because it was unsafe to retain.",
            )
            return
        sanitized = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
        self._add(
            target,
            category,
            check_key,
            self._truncate(sanitized, MAX_EVIDENCE_STRING_LENGTH),
            AuditEvidenceOutcome.OBSERVED,
            provider_field,
        )

    def _map_schema(self, target: list[AuditEvidence], value: object) -> None:
        category = AuditEvidenceCategory.SCHEMA
        if value is None:
            self._add_not_checked(target, category, "schema")
            return

        self._add_presence(
            target,
            category,
            "schema.any_present",
            getattr(value, "any_schema_found", None),
            "schema.any_schema_found",
        )
        self._add_string_collection(
            target,
            category,
            "schema.types",
            getattr(value, "found_types", None),
            "schema.found_types",
        )
        for field_name, check_key in (
            ("has_website", "schema.website.present"),
            ("has_webapp", "schema.webapp.present"),
            ("has_faq", "schema.faq.present"),
            ("has_article", "schema.article.present"),
            ("has_organization", "schema.organization.present"),
            ("has_howto", "schema.howto.present"),
            ("has_person", "schema.person.present"),
            ("has_product", "schema.product.present"),
            ("has_sameas", "schema.sameas.present"),
            ("has_date_modified", "schema.date_modified.present"),
        ):
            self._add_presence(
                target,
                category,
                check_key,
                getattr(value, field_name, None),
                f"schema.{field_name}",
            )

        sameas_urls = getattr(value, "sameas_urls", None)
        if isinstance(sameas_urls, (list, tuple)):
            self._add(
                target,
                category,
                "schema.sameas.count",
                len(sameas_urls),
                AuditEvidenceOutcome.OBSERVED,
                "schema.sameas_urls",
            )
        else:
            self._add_unknown(
                target,
                category,
                "schema.sameas.count",
                "schema.sameas_urls",
            )

        parse_errors = getattr(value, "json_parse_errors", None)
        if type(parse_errors) is int:
            self._add(
                target,
                category,
                "schema.json_parse_errors",
                parse_errors,
                (
                    AuditEvidenceOutcome.WARNING
                    if parse_errors > 0
                    else AuditEvidenceOutcome.OBSERVED
                ),
                "schema.json_parse_errors",
            )
        else:
            self._add_unknown(
                target,
                category,
                "schema.json_parse_errors",
                "schema.json_parse_errors",
            )

        missing_fields = self._flatten_schema_missing_fields(
            getattr(value, "schema_missing_fields", None)
        )
        if missing_fields is None:
            self._add_unknown(
                target,
                category,
                "schema.missing_fields",
                "schema.schema_missing_fields",
            )
        else:
            self._add(
                target,
                category,
                "schema.missing_fields",
                missing_fields,
                (
                    AuditEvidenceOutcome.WARNING
                    if missing_fields
                    else AuditEvidenceOutcome.OBSERVED
                ),
                "schema.schema_missing_fields",
            )
        self._add_string_collection(
            target,
            category,
            "schema.incomplete_types",
            getattr(value, "incomplete_schema_types", None),
            "schema.incomplete_schema_types",
            nonempty_outcome=AuditEvidenceOutcome.WARNING,
        )

    def _map_content(self, target: list[AuditEvidence], value: object) -> None:
        category = AuditEvidenceCategory.CONTENT
        if value is None:
            self._add_not_checked(target, category, "content")
            return

        for field_name, check_key in (
            ("has_h1", "content.h1.present"),
            ("has_numbers", "content.numbers.present"),
            ("has_links", "content.links.present"),
            ("has_heading_hierarchy", "content.heading_hierarchy.present"),
            ("has_lists_or_tables", "content.lists_or_tables.present"),
            ("has_front_loading", "content.front_loading.detected"),
        ):
            self._add_presence(
                target,
                category,
                check_key,
                getattr(value, field_name, None),
                f"content.{field_name}",
            )
        for field_name, check_key in (
            ("heading_count", "content.heading_count"),
            ("word_count", "content.word_count"),
            ("numbers_count", "content.numbers_count"),
            ("external_links_count", "content.external_links_count"),
        ):
            self._add_scalar(
                target,
                category,
                check_key,
                getattr(value, field_name, None),
                f"content.{field_name}",
            )

    def _map_ai_discovery(
        self,
        target: list[AuditEvidence],
        value: object,
    ) -> None:
        category = AuditEvidenceCategory.AI_DISCOVERY
        if value is None:
            self._add_not_checked(target, category, "ai_discovery")
            return

        endpoint_fields = (
            ("has_well_known_ai", "ai_discovery.well_known_ai.present"),
            ("has_summary", "ai_discovery.summary.present"),
            ("has_faq", "ai_discovery.faq.present"),
            ("has_service", "ai_discovery.service.present"),
        )
        for field_name, check_key in endpoint_fields:
            self._add_detection(
                target,
                category,
                check_key,
                getattr(value, field_name, None),
                f"ai_discovery.{field_name}",
            )

        has_summary = getattr(value, "has_summary", None)
        if has_summary is True:
            self._add_presence(
                target,
                category,
                "ai_discovery.summary.valid",
                getattr(value, "summary_valid", None),
                "ai_discovery.summary_valid",
            )
        elif has_summary is False:
            self._add(
                target,
                category,
                "ai_discovery.summary.valid",
                None,
                AuditEvidenceOutcome.NOT_APPLICABLE,
                "ai_discovery.summary_valid",
            )
        else:
            self._add_unknown(
                target,
                category,
                "ai_discovery.summary.valid",
                "ai_discovery.summary_valid",
            )

        has_faq = getattr(value, "has_faq", None)
        if has_faq is True:
            self._add_scalar(
                target,
                category,
                "ai_discovery.faq_count",
                getattr(value, "faq_count", None),
                "ai_discovery.faq_count",
            )
        elif has_faq is False:
            self._add(
                target,
                category,
                "ai_discovery.faq_count",
                None,
                AuditEvidenceOutcome.NOT_APPLICABLE,
                "ai_discovery.faq_count",
            )
        else:
            self._add_unknown(
                target,
                category,
                "ai_discovery.faq_count",
                "ai_discovery.faq_count",
            )
        self._add_scalar(
            target,
            category,
            "ai_discovery.endpoints_found",
            getattr(value, "endpoints_found", None),
            "ai_discovery.endpoints_found",
        )

    def _map_citability(self, value: object) -> CitabilitySummary | None:
        if value is None:
            return None
        score = getattr(value, "total_score", None)
        grade = getattr(value, "grade", None)
        improvements = self._bounded_string_tuple(
            getattr(value, "top_improvements", None),
            max_items=MAX_CITABILITY_IMPROVEMENTS,
            item_length=MAX_CITABILITY_IMPROVEMENT_LENGTH,
        )
        if type(score) is not int or type(grade) is not str or not grade.strip():
            return None
        if improvements is None:
            return None
        return CitabilitySummary(
            score=score,
            grade=self._truncate(grade, MAX_EVIDENCE_STRING_LENGTH),
            improvements=improvements,
        )

    def _add_not_checked(
        self,
        target: list[AuditEvidence],
        category: AuditEvidenceCategory,
        provider_field: str,
    ) -> None:
        self._add(
            target,
            category,
            f"{category.value}.check_available",
            None,
            AuditEvidenceOutcome.NOT_CHECKED,
            provider_field,
            note="The provider check object was unavailable.",
        )

    def _add_detection(
        self,
        target: list[AuditEvidence],
        category: AuditEvidenceCategory,
        check_key: str,
        value: object,
        provider_field: str,
    ) -> None:
        if type(value) is bool:
            self._add(
                target,
                category,
                check_key,
                value,
                (
                    AuditEvidenceOutcome.PRESENT
                    if value
                    else AuditEvidenceOutcome.NOT_DETECTED
                ),
                provider_field,
            )
        else:
            self._add_unknown(target, category, check_key, provider_field)

    def _add_presence(
        self,
        target: list[AuditEvidence],
        category: AuditEvidenceCategory,
        check_key: str,
        value: object,
        provider_field: str,
    ) -> None:
        if type(value) is bool:
            self._add(
                target,
                category,
                check_key,
                value,
                (
                    AuditEvidenceOutcome.PRESENT
                    if value
                    else AuditEvidenceOutcome.ABSENT
                ),
                provider_field,
            )
        else:
            self._add_unknown(target, category, check_key, provider_field)

    def _add_scalar(
        self,
        target: list[AuditEvidence],
        category: AuditEvidenceCategory,
        check_key: str,
        value: object,
        provider_field: str,
    ) -> None:
        if type(value) in {int, float}:
            self._add(
                target,
                category,
                check_key,
                value,
                AuditEvidenceOutcome.OBSERVED,
                provider_field,
            )
        else:
            self._add_unknown(target, category, check_key, provider_field)

    def _add_bounded_string(
        self,
        target: list[AuditEvidence],
        category: AuditEvidenceCategory,
        check_key: str,
        value: object,
        provider_field: str,
    ) -> None:
        if type(value) is str:
            self._add(
                target,
                category,
                check_key,
                self._truncate(value, MAX_EVIDENCE_STRING_LENGTH),
                AuditEvidenceOutcome.OBSERVED,
                provider_field,
            )
        else:
            self._add_unknown(target, category, check_key, provider_field)

    def _add_string_collection(
        self,
        target: list[AuditEvidence],
        category: AuditEvidenceCategory,
        check_key: str,
        value: object,
        provider_field: str,
        *,
        nonempty_outcome: AuditEvidenceOutcome = AuditEvidenceOutcome.OBSERVED,
    ) -> None:
        bounded = self._bounded_string_tuple(value)
        if bounded is None:
            self._add_unknown(target, category, check_key, provider_field)
            return
        self._add(
            target,
            category,
            check_key,
            bounded,
            nonempty_outcome if bounded else AuditEvidenceOutcome.OBSERVED,
            provider_field,
        )

    def _add_unknown(
        self,
        target: list[AuditEvidence],
        category: AuditEvidenceCategory,
        check_key: str,
        provider_field: str,
    ) -> None:
        self._add(
            target,
            category,
            check_key,
            None,
            AuditEvidenceOutcome.UNKNOWN,
            provider_field,
        )

    @staticmethod
    def _add(
        target: list[AuditEvidence],
        category: AuditEvidenceCategory,
        check_key: str,
        observed_value: AuditEvidenceValue,
        outcome: AuditEvidenceOutcome,
        provider_field: str,
        *,
        note: str | None = None,
    ) -> None:
        if len(target) >= MAX_EVIDENCE_COUNT:
            return
        target.append(
            AuditEvidence(
                category=category,
                check_key=check_key,
                observed_value=observed_value,
                outcome=outcome,
                provider_field=provider_field,
                note=note,
            )
        )

    @staticmethod
    def _bounded_string_tuple(
        value: object,
        *,
        max_items: int = MAX_EVIDENCE_TUPLE_ITEMS,
        item_length: int = MAX_EVIDENCE_TUPLE_ITEM_LENGTH,
    ) -> tuple[str, ...] | None:
        if not isinstance(value, (list, tuple)) or any(
            type(item) is not str for item in value
        ):
            return None
        return tuple(
            GeoOptimizerAdapter._truncate(item, item_length)
            for item in value[:max_items]
        )

    @staticmethod
    def _flatten_schema_missing_fields(value: object) -> tuple[str, ...] | None:
        if not isinstance(value, Mapping):
            return None
        flattened: list[str] = []
        for schema_type, missing in value.items():
            if type(schema_type) is not str or not isinstance(missing, (list, tuple)):
                return None
            for field_name in missing:
                if type(field_name) is not str:
                    return None
                flattened.append(f"{schema_type}.{field_name}")
                if len(flattened) >= MAX_EVIDENCE_TUPLE_ITEMS:
                    break
            if len(flattened) >= MAX_EVIDENCE_TUPLE_ITEMS:
                break
        return tuple(
            GeoOptimizerAdapter._truncate(item, MAX_EVIDENCE_TUPLE_ITEM_LENGTH)
            for item in flattened
        )

    @staticmethod
    def _truncate(value: str, limit: int) -> str:
        return value[:limit]

    @staticmethod
    def _optional_int(value: object) -> int | None:
        return value if type(value) is int else None

    @staticmethod
    def _optional_str(value: object) -> str | None:
        if type(value) is not str:
            return None
        return GeoOptimizerAdapter._truncate(value, MAX_EVIDENCE_STRING_LENGTH)

    @staticmethod
    def _copy_score_breakdown(value: Mapping[object, object]) -> dict[str, int]:
        if not isinstance(value, Mapping):
            raise TypeError("geo-optimizer score_breakdown must be a mapping.")

        copied: dict[str, int] = {}
        for key, score in value.items():
            if type(key) is not str or type(score) is not int:
                raise TypeError(
                    "geo-optimizer score_breakdown must map strings to integers."
                )
            copied[key] = score
        return copied

    @staticmethod
    def _copy_recommendations(value: object) -> tuple[str, ...]:
        if not isinstance(value, list) or any(type(item) is not str for item in value):
            raise TypeError("geo-optimizer recommendations must be a list of strings.")
        return tuple(value)

    @staticmethod
    def _require_int(value: object, field_name: str) -> int:
        if type(value) is not int:
            raise TypeError(f"geo-optimizer {field_name} must be an integer.")
        return value

    @staticmethod
    def _require_str(value: object, field_name: str) -> str:
        if type(value) is not str:
            raise TypeError(f"geo-optimizer {field_name} must be a string.")
        return value
