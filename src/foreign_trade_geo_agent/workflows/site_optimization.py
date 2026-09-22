"""Fixed site-audit, web-search, and optimization-draft workflow."""

import asyncio
import json
import re
from urllib.parse import urlsplit, urlunsplit

from foreign_trade_geo_agent.core.audit import (
    AuditEvidence,
    AuditEvidenceCategory,
    AuditEvidenceOutcome,
    AuditStatus,
)
from foreign_trade_geo_agent.core.optimization import (
    MAX_ACTION_CHARS,
    MAX_ACTIONS,
    MAX_AUDIT_EVIDENCE,
    MAX_AUDIT_MATERIAL_CHARS,
    MAX_DYNAMIC_MATERIAL_CHARS,
    MAX_RATIONALE_CHARS,
    MAX_RECOMMENDATIONS,
    MAX_SOURCE_CONTENT_CHARS,
    MAX_SOURCE_TITLE_CHARS,
    MAX_SOURCES,
    MAX_TITLE_CHARS,
    MAX_TOTAL_SOURCE_CONTENT_CHARS,
    EvidenceUse,
    NumberedAuditEvidence,
    OptimizationGenerationStatus,
    OptimizationPrompt,
    OptimizationRecommendation,
    OptimizationSource,
    OptimizationSourceMaterial,
    OptimizationStatus,
    RecommendationKind,
    RecommendationPriority,
    SiteOptimizationReport,
    SiteOptimizationRequest,
    TechnicalConstraint,
    classify_audit_evidence_use,
)
from foreign_trade_geo_agent.core.ports import (
    OptimizationWriter,
    SearchProvider,
    SiteAuditor,
)
from foreign_trade_geo_agent.core.search import SearchResponse, SearchResult, SearchStatus


class _StageTimeout(Exception):
    pass


INVALID_OUTPUT_ERROR_PREFIX = "INVALID_OUTPUT: "
_BASE_INVALID_OUTPUT_CATEGORIES = frozenset(
    {
        "JSON_FORMAT",
        "FIELD_CONTRACT",
        "UNKNOWN_OR_DUPLICATE_REFERENCE",
        "SCHEMA_APPLICABILITY",
    }
)
_TECHNICAL_INVALID_OUTPUT_CATEGORIES = frozenset(
    {
        "TECHNICAL_FIX_NO_AUDIT_REFERENCE",
        "TECHNICAL_FIX_CATEGORY_MISMATCH",
        "TECHNICAL_FIX_EVIDENCE_USE_NOT_ALLOWED",
        "TECHNICAL_FIX_NO_ELIGIBLE_EVIDENCE_IN_PROMPT",
    }
)
INVALID_OUTPUT_CATEGORIES = (
    _BASE_INVALID_OUTPUT_CATEGORIES | _TECHNICAL_INVALID_OUTPUT_CATEGORIES
)
INVALID_OUTPUT_ERRORS = frozenset(
    f"{INVALID_OUTPUT_ERROR_PREFIX}{category}"
    for category in _BASE_INVALID_OUTPUT_CATEGORIES
) | frozenset(
    f"{INVALID_OUTPUT_ERROR_PREFIX}{category}:R{number}"
    for category in _TECHNICAL_INVALID_OUTPUT_CATEGORIES
    for number in range(1, MAX_RECOMMENDATIONS + 1)
)


class SiteOptimizationWorkflow:
    """Create one evidence-grounded draft with fixed provider call counts."""

    limitations = (
        "Audit observations apply to the supplied entry URL and checks actually completed; they do not establish the state of every product page.",
        "geo-optimizer scores and citability are provider heuristics, not official search-engine rankings.",
        "Tavily sources are external research results, not native citations from ChatGPT, Perplexity, or another AI surface.",
        "Recommendations do not guarantee rankings, AI mentions, or inquiries and require human review.",
    )
    _outcome_priority = {
        AuditEvidenceOutcome.WARNING: 0,
        AuditEvidenceOutcome.ABSENT: 1,
        AuditEvidenceOutcome.CHECK_FAILED: 2,
        AuditEvidenceOutcome.NOT_DETECTED: 3,
        AuditEvidenceOutcome.UNKNOWN: 4,
        AuditEvidenceOutcome.OBSERVED: 5,
        AuditEvidenceOutcome.PRESENT: 6,
    }
    _category_priority = {
        category: number for number, category in enumerate(AuditEvidenceCategory)
    }
    _preferred_evidence_keys = {
        "robots.file_detected",
        "robots.ai_crawlers.allowed",
        "robots.ai_crawlers.blocked",
        "robots.ai_crawlers.missing_rules",
        "robots.ai_crawlers.partial",
        "meta.title.present",
        "meta.description.present",
        "meta.canonical.present",
        "schema.any_present",
        "schema.types",
        "schema.json_parse_errors",
        "schema.missing_fields",
        "schema.incomplete_types",
        "content.h1.present",
        "content.word_count",
        "content.heading_hierarchy.present",
    }
    _optional_absence_keys = {
        "robots.crawl_delay",
        "meta.noai.present",
        "meta.x_robots_noindex",
        "schema.article.present",
        "schema.faq.present",
        "schema.howto.present",
        "schema.person.present",
        "schema.product.present",
    }
    _schema_phrase_pattern = re.compile(
        r"\b([a-z][a-z0-9]*)\s+(?:schema|structured\s+data)\b",
        re.IGNORECASE,
    )
    _page_fit_pattern = re.compile(
        r"(?:page[- ]appropriate|(?:appropriate|matching|relevant|suitable)"
        r".{0,32}\bpage\b)",
        re.IGNORECASE,
    )
    _generic_schema_leading_words = {
        "a",
        "add",
        "any",
        "appropriate",
        "detected",
        "general",
        "generic",
        "implement",
        "matching",
        "no",
        "page",
        "relevant",
        "review",
        "structured",
        "suitable",
        "the",
    }

    def __init__(
        self,
        site_auditor: SiteAuditor,
        search_provider: SearchProvider,
        optimization_writer: OptimizationWriter,
        *,
        audit_timeout: float = 60.0,
        search_timeout: float = 35.0,
        generation_timeout: float = 40.0,
        total_timeout: float = 140.0,
    ) -> None:
        for name, value in (
            ("audit_timeout", audit_timeout),
            ("search_timeout", search_timeout),
            ("generation_timeout", generation_timeout),
            ("total_timeout", total_timeout),
        ):
            if type(value) not in {int, float} or value <= 0:
                raise ValueError(f"{name} must be positive.")
        self._site_auditor = site_auditor
        self._search_provider = search_provider
        self._optimization_writer = optimization_writer
        self._audit_timeout = float(audit_timeout)
        self._search_timeout = float(search_timeout)
        self._generation_timeout = float(generation_timeout)
        self._total_timeout = float(total_timeout)

    async def run(self, request: SiteOptimizationRequest) -> SiteOptimizationReport:
        if not isinstance(request, SiteOptimizationRequest):
            raise TypeError("Site optimization workflow requires SiteOptimizationRequest.")
        try:
            return await asyncio.wait_for(
                self._run_stages(request),
                timeout=self._total_timeout,
            )
        except (_StageTimeout, TimeoutError, asyncio.TimeoutError):
            return self._failed(
                request.url,
                OptimizationStatus.WORKFLOW_TIMEOUT,
                "Site optimization workflow timed out; an audit worker thread may still be finishing.",
            )

    async def _run_stages(self, request: SiteOptimizationRequest) -> SiteOptimizationReport:
        try:
            audit_result = await asyncio.wait_for(
                asyncio.to_thread(self._site_auditor.audit_site, request.url),
                timeout=self._audit_timeout,
            )
        except (TimeoutError, asyncio.TimeoutError) as exc:
            raise _StageTimeout from exc
        except Exception:
            return self._failed(
                request.url,
                OptimizationStatus.AUDIT_FAILED,
                "Site auditor raised an exception.",
            )

        if audit_result.status is AuditStatus.FAILED:
            return self._failed(
                request.url,
                OptimizationStatus.AUDIT_FAILED,
                "Site audit failed.",
            )

        numbered_evidence = self._prepare_audit_evidence(audit_result.evidence)
        if (
            len(numbered_evidence) < 3
            or len({item.evidence.category for item in numbered_evidence}) < 2
        ):
            return self._failed(
                request.url,
                OptimizationStatus.INSUFFICIENT_AUDIT_EVIDENCE,
                "Site audit returned insufficient usable evidence.",
            )

        responses: list[SearchResponse] = []
        for query in self.build_queries(request):
            try:
                response = await asyncio.wait_for(
                    self._search_provider.search(query),
                    timeout=self._search_timeout,
                )
            except (TimeoutError, asyncio.TimeoutError) as exc:
                raise _StageTimeout from exc
            except Exception:
                return self._failed(
                    request.url,
                    OptimizationStatus.SEARCH_FAILED,
                    "Search provider raised an exception.",
                )
            if response.status is SearchStatus.FAILED:
                return self._failed(
                    request.url,
                    OptimizationStatus.SEARCH_FAILED,
                    "External research search failed.",
                )
            responses.append(response)

        prepared_sources = self._prepare_sources(responses)
        if prepared_sources is None:
            return self._failed(
                request.url,
                OptimizationStatus.NO_SEARCH_RESULTS,
                "External searches returned insufficient usable results.",
            )
        source_materials, report_sources = prepared_sources
        prompt = self._fit_prompt_budget(request, numbered_evidence, source_materials)
        if prompt is None:
            return self._failed(
                request.url,
                OptimizationStatus.NO_SEARCH_RESULTS,
                "External research materials could not fit the input budget.",
            )
        prompt_source_ids = {source.source_id for source in prompt.sources}
        report_sources = tuple(
            source for source in report_sources if source.source_id in prompt_source_ids
        )

        try:
            generation = await asyncio.wait_for(
                self._optimization_writer.write_optimization(prompt),
                timeout=self._generation_timeout,
            )
        except (TimeoutError, asyncio.TimeoutError) as exc:
            raise _StageTimeout from exc
        except Exception:
            return self._failed(
                request.url,
                OptimizationStatus.GENERATION_FAILED,
                "Optimization writer raised an exception.",
            )
        if generation.status is OptimizationGenerationStatus.FAILED:
            return self._failed(
                request.url,
                OptimizationStatus.GENERATION_FAILED,
                "Optimization generation failed.",
            )

        recommendations, validation_error = self._validate_recommendations(
            generation.text,
            numbered_evidence,
            report_sources,
        )
        if recommendations is None:
            assert validation_error in INVALID_OUTPUT_ERRORS
            return self._failed(
                request.url,
                OptimizationStatus.INVALID_OUTPUT,
                validation_error,
            )

        return SiteOptimizationReport(
            url=request.url,
            status=OptimizationStatus.SUCCESS,
            recommendations=recommendations,
            audit_evidence=numbered_evidence,
            sources=report_sources,
            error=None,
            limitations=self.limitations,
        )

    @staticmethod
    def build_queries(request: SiteOptimizationRequest) -> tuple[str, str]:
        products = " ".join(request.product_terms)
        markets = " ".join(request.target_markets)
        first = (
            f"{request.research_topic} {products} "
            "applications selection technical questions"
        )
        second_parts = [
            request.research_topic,
            markets,
            "B2B buyer procurement requirements specifications testing certification supplier evaluation",
        ]
        second = " ".join(part for part in second_parts if part)
        return first, second

    def _prepare_audit_evidence(
        self,
        evidence: tuple[AuditEvidence, ...],
    ) -> tuple[NumberedAuditEvidence, ...]:
        eligible: list[AuditEvidence] = []
        for item in evidence:
            if item.outcome in {
                AuditEvidenceOutcome.NOT_CHECKED,
                AuditEvidenceOutcome.NOT_APPLICABLE,
            }:
                continue
            if item not in eligible:
                eligible.append(item)
        eligible.sort(key=self._evidence_sort_key)

        selected = [
            item for item in eligible if self._evidence_business_priority(item) == 0
        ][:MAX_AUDIT_EVIDENCE]
        for category in AuditEvidenceCategory:
            already_selected = sum(
                item.category is category for item in selected
            )
            category_allowance = max(0, 4 - already_selected)
            if category_allowance == 0:
                continue
            category_items = [
                item
                for item in eligible
                if item.category is category and item not in selected
            ]
            selected.extend(category_items[:category_allowance])
            if len(selected) >= MAX_AUDIT_EVIDENCE:
                break
        selected = sorted(selected[:MAX_AUDIT_EVIDENCE], key=self._evidence_sort_key)

        numbered: list[NumberedAuditEvidence] = []
        for item in selected:
            candidate = NumberedAuditEvidence(f"A{len(numbered) + 1}", item)
            tentative = OptimizationPrompt("x", ("x",), (), tuple(numbered + [candidate]), ())
            if tentative.audit_material_chars() > MAX_AUDIT_MATERIAL_CHARS:
                continue
            numbered.append(candidate)
        return tuple(numbered)

    def _evidence_sort_key(
        self,
        item: AuditEvidence,
    ) -> tuple[int, int, int, str, str]:
        return (
            self._evidence_business_priority(item),
            self._outcome_priority.get(item.outcome, 99),
            self._category_priority[item.category],
            item.check_key,
            item.provider_field,
        )

    @classmethod
    def _evidence_business_priority(cls, item: AuditEvidence) -> int:
        if item.check_key in cls._preferred_evidence_keys:
            return 0
        if (
            item.check_key in cls._optional_absence_keys
            and item.outcome is AuditEvidenceOutcome.ABSENT
        ) or (
            item.category is AuditEvidenceCategory.AI_DISCOVERY
            and item.outcome
            in {AuditEvidenceOutcome.ABSENT, AuditEvidenceOutcome.NOT_DETECTED}
        ):
            return 2
        return 1

    @classmethod
    def _is_actionable_technical_evidence(cls, item: AuditEvidence) -> bool:
        return EvidenceUse.TECHNICAL_FIX in (
            classify_audit_evidence_use(item).allowed_uses
        )

    @classmethod
    def _is_generic_page_fit_schema_review(cls, text: str) -> bool:
        if cls._page_fit_pattern.search(text) is None:
            return False
        return all(
            match.casefold() in cls._generic_schema_leading_words
            for match in cls._schema_phrase_pattern.findall(text)
        )

    def _prepare_sources(
        self,
        responses: list[SearchResponse],
    ) -> tuple[tuple[OptimizationSourceMaterial, ...], tuple[OptimizationSource, ...]] | None:
        per_query: list[list[SearchResult]] = []
        for response in responses:
            usable = [
                result
                for result in response.results[:5]
                if self._is_usable_result(result)
            ]
            if not usable:
                return None
            per_query.append(usable)

        selected: list[tuple[SearchResult, str]] = []
        seen_urls: set[str] = set()
        for results in per_query:
            anchor: tuple[SearchResult, str] | None = None
            for result in results:
                normalized_url = self._normalized_url(result.url)
                if normalized_url not in seen_urls:
                    anchor = (result, normalized_url)
                    break
            if anchor is None:
                return None
            selected.append(anchor)
            seen_urls.add(anchor[1])

        for results in per_query:
            for result in results:
                normalized_url = self._normalized_url(result.url)
                if normalized_url in seen_urls:
                    continue
                seen_urls.add(normalized_url)
                selected.append((result, normalized_url))
                if len(selected) >= MAX_SOURCES:
                    break
            if len(selected) >= MAX_SOURCES:
                break
        if not selected:
            return None

        materials: list[OptimizationSourceMaterial] = []
        sources: list[OptimizationSource] = []
        remaining_content = MAX_TOTAL_SOURCE_CONTENT_CHARS
        for result, normalized_url in selected:
            if remaining_content <= 0:
                break
            source_id = f"S{len(materials) + 1}"
            title = self._normalize(result.title)[:MAX_SOURCE_TITLE_CHARS] or "(untitled)"
            content = self._normalize(result.content)[: min(MAX_SOURCE_CONTENT_CHARS, remaining_content)]
            if not content:
                continue
            remaining_content -= len(content)
            materials.append(OptimizationSourceMaterial(source_id, title, content))
            sources.append(OptimizationSource(source_id, title, normalized_url))
        return (tuple(materials), tuple(sources)) if materials else None

    def _fit_prompt_budget(
        self,
        request: SiteOptimizationRequest,
        evidence: tuple[NumberedAuditEvidence, ...],
        sources: tuple[OptimizationSourceMaterial, ...],
    ) -> OptimizationPrompt | None:
        mutable_sources = list(sources)
        while mutable_sources:
            prompt = OptimizationPrompt(
                request.research_topic,
                request.product_terms,
                request.target_markets,
                evidence,
                tuple(mutable_sources),
            )
            overflow = prompt.dynamic_material_chars() - MAX_DYNAMIC_MATERIAL_CHARS
            if overflow <= 0:
                return prompt
            last = mutable_sources[-1]
            if len(last.content) > overflow:
                mutable_sources[-1] = OptimizationSourceMaterial(
                    last.source_id,
                    last.title,
                    last.content[: len(last.content) - overflow],
                )
            else:
                mutable_sources.pop()
        return None

    @staticmethod
    def _is_usable_result(result: SearchResult) -> bool:
        if (
            type(result.title) is not str
            or type(result.url) is not str
            or type(result.content) is not str
            or not result.content.strip()
            or len(result.url) > 2_048
            or any(char.isspace() for char in result.url)
        ):
            return False
        try:
            parsed = urlsplit(result.url)
        except ValueError:
            return False
        return (
            parsed.scheme.casefold() in {"http", "https"}
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
        )

    @staticmethod
    def _normalized_url(url: str) -> str:
        parsed = urlsplit(url)
        return urlunsplit(
            (
                parsed.scheme.casefold(),
                parsed.netloc.casefold(),
                parsed.path or "/",
                parsed.query,
                "",
            )
        )

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(value.split())

    def _validate_recommendations(
        self,
        text: str | None,
        evidence: tuple[NumberedAuditEvidence, ...],
        sources: tuple[OptimizationSource, ...],
    ) -> tuple[tuple[OptimizationRecommendation, ...] | None, str | None]:
        if text is None:
            return self._invalid_output("JSON_FORMAT")
        try:
            payload = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return self._invalid_output("JSON_FORMAT")
        if type(payload) is not dict or set(payload) != {"recommendations"}:
            return self._invalid_output("FIELD_CONTRACT")
        raw_items = payload["recommendations"]
        if type(raw_items) is not list or not 1 <= len(raw_items) <= MAX_RECOMMENDATIONS:
            return self._invalid_output("FIELD_CONTRACT")

        evidence_by_id = {item.evidence_id: item.evidence for item in evidence}
        source_ids = {source.source_id for source in sources}
        validated: list[OptimizationRecommendation] = []
        for raw in raw_items:
            recommendation, validation_error = self._validate_recommendation(
                raw,
                len(validated) + 1,
                evidence_by_id,
                source_ids,
            )
            if recommendation is None:
                assert validation_error in INVALID_OUTPUT_ERRORS
                return None, validation_error
            validated.append(recommendation)
        return tuple(validated), None

    def _validate_recommendation(
        self,
        raw: object,
        number: int,
        evidence_by_id: dict[str, AuditEvidence],
        source_ids: set[str],
    ) -> tuple[OptimizationRecommendation | None, str | None]:
        required_keys = {
            "kind",
            "priority",
            "target_category",
            "site_gap_claimed",
            "title",
            "rationale",
            "actions",
            "audit_refs",
            "source_refs",
        }
        if type(raw) is not dict or set(raw) != required_keys:
            return self._invalid_output("FIELD_CONTRACT")
        try:
            kind = RecommendationKind(raw["kind"])
            priority = RecommendationPriority(raw["priority"])
        except (ValueError, TypeError):
            return self._invalid_output("FIELD_CONTRACT")
        raw_target_category = raw["target_category"]
        try:
            target_category = (
                None
                if raw_target_category is None
                else AuditEvidenceCategory(raw_target_category)
            )
        except (ValueError, TypeError):
            return self._invalid_output("FIELD_CONTRACT")
        site_gap_claimed = raw["site_gap_claimed"]
        if type(site_gap_claimed) is not bool:
            return self._invalid_output("FIELD_CONTRACT")
        title = self._validated_text(raw["title"], MAX_TITLE_CHARS)
        rationale = self._validated_text(raw["rationale"], MAX_RATIONALE_CHARS)
        actions = self._validated_text_list(raw["actions"], MAX_ACTIONS, MAX_ACTION_CHARS)
        if None in {title, rationale, actions}:
            return self._invalid_output("FIELD_CONTRACT")
        audit_refs, audit_refs_error = self._validated_refs(
            raw["audit_refs"],
            "A",
            set(evidence_by_id),
        )
        source_refs, source_refs_error = self._validated_refs(
            raw["source_refs"],
            "S",
            source_ids,
        )
        references_error = audit_refs_error or source_refs_error
        if references_error is not None:
            return self._invalid_output(references_error)
        assert isinstance(title, str) and isinstance(rationale, str)
        assert isinstance(actions, tuple) and isinstance(audit_refs, tuple) and isinstance(source_refs, tuple)

        if kind is RecommendationKind.TECHNICAL_FIX:
            if target_category is None or site_gap_claimed is not True:
                return self._invalid_output("FIELD_CONTRACT")
            if not audit_refs:
                return self._invalid_output(
                    "TECHNICAL_FIX_NO_AUDIT_REFERENCE",
                    number,
                )
            same_category_evidence = tuple(
                evidence_by_id[reference]
                for reference in audit_refs
                if evidence_by_id[reference].category is target_category
            )
            if not same_category_evidence:
                return self._invalid_output(
                    "TECHNICAL_FIX_CATEGORY_MISMATCH",
                    number,
                )
            supporting_evidence = tuple(
                item
                for item in same_category_evidence
                if self._is_actionable_technical_evidence(item)
            )
            if not supporting_evidence:
                prompt_has_eligible_evidence = any(
                    self._is_actionable_technical_evidence(item)
                    for item in evidence_by_id.values()
                )
                return self._invalid_output(
                    (
                        "TECHNICAL_FIX_EVIDENCE_USE_NOT_ALLOWED"
                        if prompt_has_eligible_evidence
                        else "TECHNICAL_FIX_NO_ELIGIBLE_EVIDENCE_IN_PROMPT"
                    ),
                    number,
                )
            if (
                target_category is AuditEvidenceCategory.SCHEMA
                and all(
                    classify_audit_evidence_use(item).technical_constraint
                    is TechnicalConstraint.PAGE_APPROPRIATE_SCHEMA_REVIEW_ONLY
                    for item in supporting_evidence
                )
                and not self._is_generic_page_fit_schema_review(
                    " ".join((title, rationale, *actions))
                )
            ):
                return self._invalid_output("SCHEMA_APPLICABILITY")
        elif kind is RecommendationKind.POLICY_REVIEW:
            if (
                target_category
                not in {
                    AuditEvidenceCategory.ROBOTS,
                    AuditEvidenceCategory.LLMS,
                    AuditEvidenceCategory.AI_DISCOVERY,
                }
                or site_gap_claimed is not False
                or not audit_refs
                or not any(
                    evidence_by_id[reference].category is target_category
                    and EvidenceUse.POLICY_REVIEW
                    in classify_audit_evidence_use(
                        evidence_by_id[reference]
                    ).allowed_uses
                    for reference in audit_refs
                )
            ):
                return self._invalid_output("FIELD_CONTRACT")
            policy_text = " ".join((title, rationale, *actions)).casefold()
            if any(
                phrase in policy_text
                for phrase in (
                    "allow all ai crawlers",
                    "allow all crawlers",
                    "开放所有 ai 爬虫",
                    "开放全部 ai 爬虫",
                )
            ):
                return self._invalid_output("FIELD_CONTRACT")
        elif kind is RecommendationKind.CONTENT_OPPORTUNITY:
            if target_category is not None or site_gap_claimed is not False or not source_refs:
                return self._invalid_output("FIELD_CONTRACT")

        return (
            OptimizationRecommendation(
                recommendation_id=f"R{number}",
                kind=kind,
                priority=priority,
                target_category=target_category,
                site_gap_claimed=site_gap_claimed,
                title=title,
                rationale=rationale,
                actions=actions,
                audit_refs=audit_refs,
                source_refs=source_refs,
            ),
            None,
        )

    @staticmethod
    def _validated_text(value: object, limit: int) -> str | None:
        if type(value) is not str:
            return None
        normalized = " ".join(value.split())
        if not normalized or len(normalized) > limit:
            return None
        url_scan_text = re.sub(
            r"\b(?:robots|llms)\.txt\b",
            "",
            normalized,
            flags=re.IGNORECASE,
        )
        if re.search(
            r"(?:[a-z][a-z0-9+.-]*://|mailto:|www\.|"
            r"\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b|"
            r"\b(?:[a-z0-9-]+\.)+(?:com|org|net|io|ai|co|cn|de|uk|us|info|biz|xyz|example)(?:/[^\s]*)?|"
            r"\[[AS][^\]]*\])",
            url_scan_text,
            re.IGNORECASE,
        ):
            return None
        return normalized

    @classmethod
    def _validated_text_list(
        cls,
        value: object,
        max_items: int,
        max_chars: int,
    ) -> tuple[str, ...] | None:
        if type(value) is not list or not 1 <= len(value) <= max_items:
            return None
        items = tuple(cls._validated_text(item, max_chars) for item in value)
        if any(item is None for item in items):
            return None
        return items  # type: ignore[return-value]

    @staticmethod
    def _validated_refs(
        value: object,
        prefix: str,
        known: set[str],
    ) -> tuple[tuple[str, ...] | None, str | None]:
        if type(value) is not list or any(type(item) is not str for item in value):
            return None, "FIELD_CONTRACT"
        references = tuple(value)
        if len(references) != len(set(references)):
            return None, "UNKNOWN_OR_DUPLICATE_REFERENCE"
        if any(
            re.fullmatch(fr"{prefix}[1-9][0-9]*", reference) is None
            or reference not in known
            for reference in references
        ):
            return None, "UNKNOWN_OR_DUPLICATE_REFERENCE"
        return references, None

    @staticmethod
    def _invalid_output(
        category: str,
        recommendation_number: int | None = None,
    ) -> tuple[None, str]:
        assert category in INVALID_OUTPUT_CATEGORIES
        suffix = ""
        if category in _TECHNICAL_INVALID_OUTPUT_CATEGORIES:
            assert recommendation_number is not None
            assert 1 <= recommendation_number <= MAX_RECOMMENDATIONS
            suffix = f":R{recommendation_number}"
        else:
            assert recommendation_number is None
        return None, f"{INVALID_OUTPUT_ERROR_PREFIX}{category}{suffix}"

    @staticmethod
    def _failed(
        url: str,
        status: OptimizationStatus,
        error: str,
    ) -> SiteOptimizationReport:
        return SiteOptimizationReport(
            url=url,
            status=status,
            recommendations=(),
            audit_evidence=(),
            sources=(),
            error=error,
        )
