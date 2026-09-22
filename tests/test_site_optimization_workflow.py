import asyncio
from contextlib import redirect_stdout
from dataclasses import replace
import importlib
import io
import json
import os
import time
import unittest
from unittest.mock import patch

from foreign_trade_geo_agent.core.audit import (
    AuditEvidence,
    AuditEvidenceCategory,
    AuditEvidenceOutcome,
    AuditStatus,
    SiteAuditResult,
)
from foreign_trade_geo_agent.core.optimization import (
    NumberedAuditEvidence,
    OptimizationGeneration,
    OptimizationGenerationStatus,
    OptimizationPrompt,
    OptimizationRecommendation,
    OptimizationSource,
    OptimizationStatus,
    RecommendationKind,
    RecommendationPriority,
    SiteOptimizationReport,
    SiteOptimizationRequest,
)
from foreign_trade_geo_agent.core.search import SearchResponse, SearchResult, SearchStatus
from foreign_trade_geo_agent.workflows.site_optimization import SiteOptimizationWorkflow


def evidence(
    category: AuditEvidenceCategory,
    key: str,
    outcome: AuditEvidenceOutcome,
    value: object = False,
) -> AuditEvidence:
    return AuditEvidence(
        category=category,
        check_key=key,
        observed_value=value,  # type: ignore[arg-type]
        outcome=outcome,
        provider_field=f"provider.{key}",
    )


def successful_audit(*items: AuditEvidence) -> SiteAuditResult:
    return SiteAuditResult(
        url="https://factory.example/",
        status=AuditStatus.SUCCESS,
        score=55,
        band="needs_work",
        score_breakdown={"technical": 55},
        recommendations=("This upstream recommendation is not evidence.",),
        error=None,
        source="geo-optimizer-skill",
        source_version="4.18.1",
        evidence=tuple(items),
        http_status=200,
    )


def sufficient_audit() -> SiteAuditResult:
    return successful_audit(
        evidence(
            AuditEvidenceCategory.META,
            "meta.description.present",
            AuditEvidenceOutcome.ABSENT,
        ),
        evidence(
            AuditEvidenceCategory.SCHEMA,
            "schema.json_parse_errors",
            AuditEvidenceOutcome.WARNING,
            1,
        ),
        evidence(
            AuditEvidenceCategory.ROBOTS,
            "robots.file_detected",
            AuditEvidenceOutcome.NOT_DETECTED,
        ),
    )


def search_result(number: int, *, url: str | None = None, content: str = "evidence") -> SearchResult:
    return SearchResult(
        title=f"Source {number}",
        url=url or f"https://source.example/{number}",
        content=content,
        score=1.0 - number / 100,
    )


def successful_search(query: str, *results: SearchResult) -> SearchResponse:
    return SearchResponse(
        query=query,
        status=SearchStatus.SUCCESS,
        results=tuple(results),
        error=None,
    )


def generated(recommendations: list[dict[str, object]]) -> OptimizationGeneration:
    return OptimizationGeneration(
        provider="deepseek",
        model="deepseek-flash",
        status=OptimizationGenerationStatus.SUCCESS,
        text=json.dumps({"recommendations": recommendations}),
        error=None,
    )


def recommendation(
    kind: str,
    *,
    audit_refs: list[str] | None = None,
    source_refs: list[str] | None = None,
) -> dict[str, object]:
    target_categories = {
        "TECHNICAL_FIX": "schema",
        "POLICY_REVIEW": "robots",
        "CONTENT_OPPORTUNITY": None,
    }
    return {
        "kind": kind,
        "priority": "HIGH",
        "target_category": target_categories.get(kind),
        "site_gap_claimed": kind == "TECHNICAL_FIX",
        "title": "Concrete improvement",
        "rationale": "A bounded rationale supported by the referenced material.",
        "actions": ["Review the current implementation", "Confirm with the site owner"],
        "audit_refs": audit_refs or [],
        "source_refs": source_refs or [],
    }


class FakeAuditor:
    def __init__(self, result: SiteAuditResult, *, delay: float = 0.0) -> None:
        self.result = result
        self.delay = delay
        self.urls: list[str] = []

    def audit_site(self, url: str) -> SiteAuditResult:
        self.urls.append(url)
        if self.delay:
            time.sleep(self.delay)
        return self.result


class FakeSearchProvider:
    def __init__(self, responses: list[SearchResponse], *, delay: float = 0.0) -> None:
        self.responses = responses
        self.delay = delay
        self.queries: list[str] = []
        self.active_calls = 0
        self.max_active_calls = 0

    async def search(self, query: str) -> SearchResponse:
        self.queries.append(query)
        self.active_calls += 1
        self.max_active_calls = max(self.max_active_calls, self.active_calls)
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            return self.responses[len(self.queries) - 1]
        finally:
            self.active_calls -= 1


class FakeOptimizationWriter:
    def __init__(
        self,
        result: OptimizationGeneration,
        *,
        delay: float = 0.0,
    ) -> None:
        self.result = result
        self.delay = delay
        self.prompts: list[object] = []

    async def write_optimization(self, prompt: object) -> OptimizationGeneration:
        self.prompts.append(prompt)
        if self.delay:
            await asyncio.sleep(self.delay)
        return self.result


def request() -> SiteOptimizationRequest:
    return SiteOptimizationRequest(
        url="https://factory.example/",
        research_topic="industrial valve manufacturing",
        product_terms=("ball valve", "gate valve"),
        target_markets=("United States",),
    )


class EvidenceUseClassifierTests(unittest.TestCase):
    def test_classifier_assigns_fixed_uses_without_expanding_technical_allowlist(self) -> None:
        optimization = importlib.import_module(
            "foreign_trade_geo_agent.core.optimization"
        )
        classifier = getattr(optimization, "classify_audit_evidence_use", None)
        self.assertIsNotNone(classifier)
        cases = (
            (
                evidence(
                    AuditEvidenceCategory.META,
                    "meta.description.present",
                    AuditEvidenceOutcome.ABSENT,
                ),
                ("TECHNICAL_FIX",),
                None,
            ),
            (
                evidence(
                    AuditEvidenceCategory.SCHEMA,
                    "schema.json_parse_errors",
                    AuditEvidenceOutcome.WARNING,
                    1,
                ),
                ("TECHNICAL_FIX",),
                None,
            ),
            (
                evidence(
                    AuditEvidenceCategory.SCHEMA,
                    "schema.any_present",
                    AuditEvidenceOutcome.ABSENT,
                ),
                ("TECHNICAL_FIX",),
                "PAGE_APPROPRIATE_SCHEMA_REVIEW_ONLY",
            ),
            (
                evidence(
                    AuditEvidenceCategory.ROBOTS,
                    "robots.crawl_delay",
                    AuditEvidenceOutcome.ABSENT,
                ),
                ("POLICY_REVIEW",),
                None,
            ),
            (
                evidence(
                    AuditEvidenceCategory.LLMS,
                    "llms.validation_warnings",
                    AuditEvidenceOutcome.WARNING,
                ),
                ("POLICY_REVIEW",),
                None,
            ),
            (
                evidence(
                    AuditEvidenceCategory.AI_DISCOVERY,
                    "ai_discovery.summary.present",
                    AuditEvidenceOutcome.NOT_DETECTED,
                ),
                ("POLICY_REVIEW",),
                None,
            ),
            (
                evidence(
                    AuditEvidenceCategory.META,
                    "meta.noai.present",
                    AuditEvidenceOutcome.ABSENT,
                ),
                ("CONTEXT_ONLY",),
                None,
            ),
            (
                evidence(
                    AuditEvidenceCategory.META,
                    "meta.x_robots_noindex",
                    AuditEvidenceOutcome.ABSENT,
                ),
                ("CONTEXT_ONLY",),
                None,
            ),
            (
                evidence(
                    AuditEvidenceCategory.SCHEMA,
                    "schema.product.present",
                    AuditEvidenceOutcome.ABSENT,
                ),
                ("CONTEXT_ONLY",),
                None,
            ),
            (
                evidence(
                    AuditEvidenceCategory.CONTENT,
                    "content.heading_hierarchy.present",
                    AuditEvidenceOutcome.ABSENT,
                ),
                ("CONTEXT_ONLY",),
                None,
            ),
        )
        for audit_evidence, expected_uses, expected_constraint in cases:
            with self.subTest(check_key=audit_evidence.check_key):
                classification = classifier(audit_evidence)
                self.assertEqual(
                    tuple(item.value for item in classification.allowed_uses),
                    expected_uses,
                )
                actual_constraint = classification.technical_constraint
                self.assertEqual(
                    None if actual_constraint is None else actual_constraint.value,
                    expected_constraint,
                )

    def test_prompt_serializes_classifier_uses_and_schema_constraint(self) -> None:
        prompt = OptimizationPrompt(
            research_topic="industrial pumps",
            product_terms=("centrifugal pump",),
            target_markets=(),
            audit_evidence=(
                NumberedAuditEvidence(
                    "A1",
                    evidence(
                        AuditEvidenceCategory.META,
                        "meta.description.present",
                        AuditEvidenceOutcome.ABSENT,
                    ),
                ),
                NumberedAuditEvidence(
                    "A2",
                    evidence(
                        AuditEvidenceCategory.SCHEMA,
                        "schema.any_present",
                        AuditEvidenceOutcome.ABSENT,
                    ),
                ),
                NumberedAuditEvidence(
                    "A3",
                    evidence(
                        AuditEvidenceCategory.CONTENT,
                        "content.heading_hierarchy.present",
                        AuditEvidenceOutcome.ABSENT,
                    ),
                ),
            ),
            sources=(),
        )

        payload = json.loads(prompt.material_json())
        serialized = payload["audit_evidence"]

        for item in serialized:
            self.assertIn("allowed_uses", item)
            self.assertIn("technical_constraint", item)
        self.assertEqual(serialized[0]["allowed_uses"], ["TECHNICAL_FIX"])
        self.assertIsNone(serialized[0]["technical_constraint"])
        self.assertEqual(serialized[1]["allowed_uses"], ["TECHNICAL_FIX"])
        self.assertEqual(
            serialized[1]["technical_constraint"],
            "PAGE_APPROPRIATE_SCHEMA_REVIEW_ONLY",
        )
        self.assertEqual(serialized[2]["allowed_uses"], ["CONTEXT_ONLY"])
        self.assertIsNone(serialized[2]["technical_constraint"])


def successful_dependencies():
    queries = SiteOptimizationWorkflow.build_queries(request())
    search = FakeSearchProvider(
        [
            successful_search(queries[0], search_result(1), search_result(2)),
            successful_search(queries[1], search_result(3), search_result(4)),
        ]
    )
    writer = FakeOptimizationWriter(
        generated(
            [
                recommendation("TECHNICAL_FIX", audit_refs=["A1"]),
                recommendation("CONTENT_OPPORTUNITY", source_refs=["S1"]),
            ]
        )
    )
    return FakeAuditor(sufficient_audit()), search, writer


class SiteOptimizationRequestTests(unittest.TestCase):
    def test_accepts_bounded_public_http_input(self) -> None:
        value = request()

        self.assertEqual(value.product_terms, ("ball valve", "gate valve"))

    def test_rejects_invalid_or_credentialed_url(self) -> None:
        for url in ("ftp://factory.example", "https:///missing", "https://u:p@factory.example"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                SiteOptimizationRequest(url, "valves", ("ball valve",))

    def test_rejects_unbounded_or_empty_research_context(self) -> None:
        invalid_arguments = (
            {"research_topic": " ", "product_terms": ("valve",)},
            {"research_topic": "x" * 201, "product_terms": ("valve",)},
            {"research_topic": "valves", "product_terms": ()},
            {"research_topic": "valves", "product_terms": tuple(str(i) for i in range(6))},
            {"research_topic": "valves", "product_terms": ("x" * 81,)},
            {"research_topic": "valves", "product_terms": ("valve",), "target_markets": ("a", "b", "c", "d")},
        )
        for arguments in invalid_arguments:
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                SiteOptimizationRequest(url="https://factory.example", **arguments)


class SiteOptimizationWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_success_runs_fixed_pipeline_and_returns_dual_evidence(self) -> None:
        auditor, search, writer = successful_dependencies()

        report = await SiteOptimizationWorkflow(auditor, search, writer).run(request())

        self.assertEqual(report.status, OptimizationStatus.SUCCESS)
        self.assertTrue(report.requires_human_review)
        self.assertEqual(auditor.urls, ["https://factory.example/"])
        self.assertEqual(search.queries, list(SiteOptimizationWorkflow.build_queries(request())))
        self.assertEqual(search.max_active_calls, 1)
        self.assertEqual(len(writer.prompts), 1)
        prompt_payload = writer.prompts[0].material_json()
        self.assertNotIn("This upstream recommendation is not evidence", prompt_payload)
        self.assertNotIn("needs_work", prompt_payload)
        self.assertNotIn("score_breakdown", prompt_payload)
        self.assertEqual([item.evidence_id for item in report.audit_evidence], ["A1", "A2", "A3"])
        self.assertEqual([item.source_id for item in report.sources], ["S1", "S2", "S3", "S4"])
        self.assertEqual([item.recommendation_id for item in report.recommendations], ["R1", "R2"])
        self.assertEqual(report.recommendations[0].kind, RecommendationKind.TECHNICAL_FIX)
        self.assertEqual(report.recommendations[0].priority, RecommendationPriority.HIGH)
        self.assertIn("entry URL", " ".join(report.limitations))

    async def test_audit_failure_short_circuits_search_and_generation(self) -> None:
        failed = SiteAuditResult(
            url="https://factory.example/",
            status=AuditStatus.FAILED,
            score=None,
            band=None,
            score_breakdown={},
            recommendations=(),
            error="unsafe URL",
            source="geo-optimizer-skill",
            source_version="4.18.1",
        )
        search = FakeSearchProvider([])
        writer = FakeOptimizationWriter(generated([]))

        report = await SiteOptimizationWorkflow(FakeAuditor(failed), search, writer).run(request())

        self.assertEqual(report.status, OptimizationStatus.AUDIT_FAILED)
        self.assertEqual(search.queries, [])
        self.assertEqual(writer.prompts, [])
        self.assertEqual(report.recommendations, ())

    async def test_insufficient_evidence_short_circuits_later_stages(self) -> None:
        audit = successful_audit(
            evidence(AuditEvidenceCategory.META, "one", AuditEvidenceOutcome.ABSENT),
            evidence(AuditEvidenceCategory.META, "two", AuditEvidenceOutcome.NOT_CHECKED),
        )
        search = FakeSearchProvider([])
        writer = FakeOptimizationWriter(generated([]))

        report = await SiteOptimizationWorkflow(FakeAuditor(audit), search, writer).run(request())

        self.assertEqual(report.status, OptimizationStatus.INSUFFICIENT_AUDIT_EVIDENCE)
        self.assertEqual(search.queries, [])
        self.assertEqual(writer.prompts, [])

    async def test_search_failure_does_not_degrade_to_audit_only_report(self) -> None:
        queries = SiteOptimizationWorkflow.build_queries(request())
        search = FakeSearchProvider(
            [
                SearchResponse(queries[0], SearchStatus.FAILED, (), "timeout"),
                successful_search(queries[1], search_result(1)),
            ]
        )
        writer = FakeOptimizationWriter(generated([]))

        report = await SiteOptimizationWorkflow(FakeAuditor(sufficient_audit()), search, writer).run(request())

        self.assertEqual(report.status, OptimizationStatus.SEARCH_FAILED)
        self.assertEqual(len(search.queries), 1)
        self.assertEqual(writer.prompts, [])
        self.assertEqual(report.recommendations, ())

    async def test_second_search_failure_happens_after_exactly_two_serial_calls(self) -> None:
        queries = SiteOptimizationWorkflow.build_queries(request())
        search = FakeSearchProvider(
            [
                successful_search(queries[0], search_result(1)),
                SearchResponse(queries[1], SearchStatus.FAILED, (), "timeout"),
            ],
            delay=0.001,
        )
        writer = FakeOptimizationWriter(generated([]))

        report = await SiteOptimizationWorkflow(FakeAuditor(sufficient_audit()), search, writer).run(request())

        self.assertEqual(report.status, OptimizationStatus.SEARCH_FAILED)
        self.assertEqual(len(search.queries), 2)
        self.assertEqual(search.max_active_calls, 1)
        self.assertEqual(writer.prompts, [])

    async def test_no_usable_result_in_either_query_stops_generation(self) -> None:
        queries = SiteOptimizationWorkflow.build_queries(request())
        search = FakeSearchProvider(
            [
                successful_search(queries[0], search_result(1, url="file:///tmp/a")),
                successful_search(queries[1], search_result(2)),
            ]
        )
        writer = FakeOptimizationWriter(generated([]))

        report = await SiteOptimizationWorkflow(FakeAuditor(sufficient_audit()), search, writer).run(request())

        self.assertEqual(report.status, OptimizationStatus.NO_SEARCH_RESULTS)
        self.assertEqual(writer.prompts, [])

    async def test_sources_are_deduplicated_before_ids_are_assigned(self) -> None:
        queries = SiteOptimizationWorkflow.build_queries(request())
        duplicate = "https://source.example/shared#fragment"
        search = FakeSearchProvider(
            [
                successful_search(queries[0], search_result(1, url=duplicate), search_result(2)),
                successful_search(queries[1], search_result(3, url="https://source.example/shared"), search_result(4)),
            ]
        )
        writer = FakeOptimizationWriter(
            generated([recommendation("CONTENT_OPPORTUNITY", source_refs=["S1"])])
        )

        report = await SiteOptimizationWorkflow(FakeAuditor(sufficient_audit()), search, writer).run(request())

        self.assertEqual(report.status, OptimizationStatus.SUCCESS)
        self.assertEqual([source.source_id for source in report.sources], ["S1", "S2", "S3"])
        self.assertEqual(len({source.url for source in report.sources}), 3)

    async def test_each_query_must_contribute_a_unique_source_after_deduplication(self) -> None:
        queries = SiteOptimizationWorkflow.build_queries(request())
        shared = "https://source.example/shared"
        search = FakeSearchProvider(
            [
                successful_search(queries[0], search_result(1, url=shared)),
                successful_search(queries[1], search_result(2, url=f"{shared}#same")),
            ]
        )
        writer = FakeOptimizationWriter(
            generated([recommendation("CONTENT_OPPORTUNITY", source_refs=["S1"])])
        )

        report = await SiteOptimizationWorkflow(FakeAuditor(sufficient_audit()), search, writer).run(request())

        self.assertEqual(report.status, OptimizationStatus.NO_SEARCH_RESULTS)
        self.assertEqual(writer.prompts, [])

    async def test_evidence_ids_are_assigned_after_filtering_and_deduplication(self) -> None:
        duplicate = evidence(AuditEvidenceCategory.META, "meta.description.present", AuditEvidenceOutcome.ABSENT)
        audit = successful_audit(
            duplicate,
            duplicate,
            evidence(AuditEvidenceCategory.CONTENT, "ignored", AuditEvidenceOutcome.NOT_APPLICABLE),
            evidence(AuditEvidenceCategory.SCHEMA, "schema.product.present", AuditEvidenceOutcome.WARNING),
            evidence(AuditEvidenceCategory.ROBOTS, "robots.file_detected", AuditEvidenceOutcome.NOT_DETECTED),
        )
        _, search, _ = successful_dependencies()
        item = recommendation("TECHNICAL_FIX", audit_refs=["A1"])
        item["target_category"] = "meta"
        writer = FakeOptimizationWriter(generated([item]))

        report = await SiteOptimizationWorkflow(FakeAuditor(audit), search, writer).run(request())

        self.assertEqual(report.status, OptimizationStatus.SUCCESS)
        self.assertEqual([item.evidence_id for item in report.audit_evidence], ["A1", "A2", "A3"])
        self.assertNotIn("ignored", [item.evidence.check_key for item in report.audit_evidence])
        self.assertEqual(
            [item.evidence.check_key for item in report.audit_evidence],
            [
                "meta.description.present",
                "robots.file_detected",
                "schema.product.present",
            ],
        )
        self.assertEqual(report.audit_evidence[1].evidence.outcome, AuditEvidenceOutcome.NOT_DETECTED)

    def test_business_relevance_keeps_core_observations_ahead_of_optional_absences(self) -> None:
        preferred = (
            evidence(AuditEvidenceCategory.META, "meta.title.present", AuditEvidenceOutcome.PRESENT, True),
            evidence(AuditEvidenceCategory.META, "meta.description.present", AuditEvidenceOutcome.PRESENT, True),
            evidence(AuditEvidenceCategory.META, "meta.canonical.present", AuditEvidenceOutcome.PRESENT, True),
            evidence(AuditEvidenceCategory.SCHEMA, "schema.any_present", AuditEvidenceOutcome.PRESENT, True),
            evidence(AuditEvidenceCategory.SCHEMA, "schema.types", AuditEvidenceOutcome.OBSERVED, ("Organization",)),
            evidence(AuditEvidenceCategory.SCHEMA, "schema.json_parse_errors", AuditEvidenceOutcome.WARNING, 1),
            evidence(AuditEvidenceCategory.SCHEMA, "schema.missing_fields", AuditEvidenceOutcome.WARNING, ("Product:offers",)),
            evidence(AuditEvidenceCategory.SCHEMA, "schema.incomplete_types", AuditEvidenceOutcome.WARNING, ("Product",)),
            evidence(AuditEvidenceCategory.CONTENT, "content.h1.present", AuditEvidenceOutcome.PRESENT, True),
            evidence(AuditEvidenceCategory.CONTENT, "content.word_count", AuditEvidenceOutcome.OBSERVED, 900),
            evidence(
                AuditEvidenceCategory.CONTENT,
                "content.heading_hierarchy.present",
                AuditEvidenceOutcome.PRESENT,
                True,
            ),
            evidence(AuditEvidenceCategory.ROBOTS, "robots.file_detected", AuditEvidenceOutcome.PRESENT, True),
            evidence(
                AuditEvidenceCategory.ROBOTS,
                "robots.ai_crawlers.allowed",
                AuditEvidenceOutcome.OBSERVED,
                ("GPTBot",),
            ),
            evidence(
                AuditEvidenceCategory.ROBOTS,
                "robots.ai_crawlers.blocked",
                AuditEvidenceOutcome.OBSERVED,
                (),
            ),
        )
        optional_absences = tuple(
            evidence(category, key, AuditEvidenceOutcome.ABSENT)
            for category, key in (
                (AuditEvidenceCategory.ROBOTS, "robots.crawl_delay"),
                (AuditEvidenceCategory.META, "meta.noai.present"),
                (AuditEvidenceCategory.META, "meta.x_robots_noindex"),
                (AuditEvidenceCategory.SCHEMA, "schema.article.present"),
                (AuditEvidenceCategory.SCHEMA, "schema.faq.present"),
                (AuditEvidenceCategory.SCHEMA, "schema.howto.present"),
                (AuditEvidenceCategory.SCHEMA, "schema.person.present"),
                (AuditEvidenceCategory.SCHEMA, "schema.product.present"),
                (AuditEvidenceCategory.AI_DISCOVERY, "ai_discovery.summary.present"),
                (AuditEvidenceCategory.AI_DISCOVERY, "ai_discovery.faq.present"),
                (AuditEvidenceCategory.AI_DISCOVERY, "ai_discovery.service.present"),
            )
        )
        workflow = SiteOptimizationWorkflow(object(), object(), object())

        selected = workflow._prepare_audit_evidence(preferred + optional_absences)

        positions = {item.evidence.check_key: index for index, item in enumerate(selected)}
        self.assertTrue(all(item.check_key in positions for item in preferred))
        selected_optional_positions = [
            positions[item.check_key]
            for item in optional_absences
            if item.check_key in positions
        ]
        self.assertTrue(selected_optional_positions)
        self.assertLess(
            max(positions[item.check_key] for item in preferred),
            min(selected_optional_positions),
        )
        self.assertLessEqual(len(selected), 24)

    def test_oversized_observation_does_not_block_smaller_core_categories(self) -> None:
        large_collection = tuple("\\" * 128 for _ in range(20))
        audit_items = (
            evidence(
                AuditEvidenceCategory.SCHEMA,
                "schema.json_parse_errors",
                AuditEvidenceOutcome.WARNING,
                1,
            ),
            evidence(
                AuditEvidenceCategory.SCHEMA,
                "schema.incomplete_types",
                AuditEvidenceOutcome.WARNING,
                large_collection,
            ),
            evidence(
                AuditEvidenceCategory.SCHEMA,
                "schema.missing_fields",
                AuditEvidenceOutcome.WARNING,
                large_collection,
            ),
            evidence(
                AuditEvidenceCategory.META,
                "meta.title.present",
                AuditEvidenceOutcome.ABSENT,
            ),
            evidence(
                AuditEvidenceCategory.CONTENT,
                "content.h1.present",
                AuditEvidenceOutcome.PRESENT,
                True,
            ),
        )
        workflow = SiteOptimizationWorkflow(object(), object(), object())

        selected = workflow._prepare_audit_evidence(audit_items)

        selected_keys = {item.evidence.check_key for item in selected}
        self.assertIn("schema.json_parse_errors", selected_keys)
        self.assertIn("meta.title.present", selected_keys)
        self.assertIn("content.h1.present", selected_keys)
        self.assertEqual(
            {item.evidence.category for item in selected},
            {
                AuditEvidenceCategory.META,
                AuditEvidenceCategory.SCHEMA,
                AuditEvidenceCategory.CONTENT,
            },
        )

    async def test_material_budgets_are_enforced_before_writer_call(self) -> None:
        audit_items = tuple(
            evidence(
                AuditEvidenceCategory.META if number % 2 else AuditEvidenceCategory.SCHEMA,
                f"check.{number}." + "x" * 200,
                AuditEvidenceOutcome.WARNING,
                "v" * 256,
            )
            for number in range(40)
        )
        queries = SiteOptimizationWorkflow.build_queries(request())
        long_content = "word   " * 500
        search = FakeSearchProvider(
            [
                successful_search(queries[0], *[search_result(i, content=long_content) for i in range(1, 6)]),
                successful_search(queries[1], *[search_result(i + 10, content=long_content) for i in range(1, 6)]),
            ]
        )
        writer = FakeOptimizationWriter(
            generated([recommendation("CONTENT_OPPORTUNITY", source_refs=["S1"])])
        )

        report = await SiteOptimizationWorkflow(
            FakeAuditor(successful_audit(*audit_items)),
            search,
            writer,
        ).run(request())

        prompt = writer.prompts[0]
        prompt_evidence_ids = tuple(
            item.evidence_id for item in prompt.audit_evidence
        )
        serialized_evidence_ids = tuple(
            item["evidence_id"]
            for item in json.loads(prompt.material_json())["audit_evidence"]
        )
        validator_evidence_ids = tuple(
            item.evidence_id for item in report.audit_evidence
        )
        self.assertEqual(prompt_evidence_ids, serialized_evidence_ids)
        self.assertEqual(prompt_evidence_ids, validator_evidence_ids)
        self.assertLessEqual(len(prompt.audit_evidence), 24)
        self.assertLessEqual(prompt.audit_material_chars(), 8_000)
        self.assertLessEqual(len(prompt.sources), 6)
        self.assertTrue(all(len(source.content) <= 1_000 for source in prompt.sources))
        self.assertLessEqual(sum(len(source.content) for source in prompt.sources), 6_000)
        self.assertLessEqual(prompt.dynamic_material_chars(), 16_000)
        self.assertTrue(all("  " not in source.content for source in prompt.sources))

    async def test_generation_failure_returns_no_partial_recommendations(self) -> None:
        auditor, search, _ = successful_dependencies()
        writer = FakeOptimizationWriter(
            OptimizationGeneration(
                provider="deepseek",
                model="deepseek-flash",
                status=OptimizationGenerationStatus.FAILED,
                text=None,
                error="timeout",
            )
        )

        report = await SiteOptimizationWorkflow(auditor, search, writer).run(request())

        self.assertEqual(report.status, OptimizationStatus.GENERATION_FAILED)
        self.assertEqual(report.recommendations, ())

    async def test_invalid_json_or_more_than_five_recommendations_is_invalid_output(self) -> None:
        invalid_generations = (
            (
                OptimizationGeneration(
                    "deepseek",
                    "deepseek-flash",
                    OptimizationGenerationStatus.SUCCESS,
                    "not-json",
                    None,
                ),
                "INVALID_OUTPUT: JSON_FORMAT",
            ),
            (
                generated(
                    [
                        recommendation("CONTENT_OPPORTUNITY", source_refs=["S1"])
                        for _ in range(6)
                    ]
                ),
                "INVALID_OUTPUT: FIELD_CONTRACT",
            ),
        )
        for generation, expected_error in invalid_generations:
            with self.subTest(text=generation.text):
                auditor, search, _ = successful_dependencies()
                report = await SiteOptimizationWorkflow(
                    auditor,
                    search,
                    FakeOptimizationWriter(generation),
                ).run(request())
                self.assertEqual(report.status, OptimizationStatus.INVALID_OUTPUT)
                self.assertEqual(report.error, expected_error)
                self.assertEqual(report.recommendations, ())

    async def test_top_level_and_recommendation_fields_report_field_contract(self) -> None:
        invalid_texts = (
            json.dumps({"unexpected": []}),
            json.dumps(
                {
                    "recommendations": [
                        {
                            key: value
                            for key, value in recommendation(
                                "CONTENT_OPPORTUNITY",
                                source_refs=["S1"],
                            ).items()
                            if key != "rationale"
                        }
                    ]
                }
            ),
        )
        for text in invalid_texts:
            with self.subTest(text=text):
                auditor, search, _ = successful_dependencies()
                generation = OptimizationGeneration(
                    "deepseek",
                    "deepseek-flash",
                    OptimizationGenerationStatus.SUCCESS,
                    text,
                    None,
                )

                report = await SiteOptimizationWorkflow(
                    auditor,
                    search,
                    FakeOptimizationWriter(generation),
                ).run(request())

                self.assertEqual(report.status, OptimizationStatus.INVALID_OUTPUT)
                self.assertEqual(report.error, "INVALID_OUTPUT: FIELD_CONTRACT")

    async def test_unknown_a_or_s_reference_reports_reference_category(self) -> None:
        cases = (
            recommendation("TECHNICAL_FIX", audit_refs=["A99"]),
            recommendation("CONTENT_OPPORTUNITY", source_refs=["S99"]),
        )
        for item in cases:
            with self.subTest(item=item):
                auditor, search, _ = successful_dependencies()

                report = await SiteOptimizationWorkflow(
                    auditor,
                    search,
                    FakeOptimizationWriter(generated([item])),
                ).run(request())

                self.assertEqual(report.status, OptimizationStatus.INVALID_OUTPUT)
                self.assertEqual(
                    report.error,
                    "INVALID_OUTPUT: UNKNOWN_OR_DUPLICATE_REFERENCE",
                )

    async def test_duplicate_a_or_s_reference_reports_reference_category(self) -> None:
        cases = (
            recommendation("TECHNICAL_FIX", audit_refs=["A1", "A1"]),
            recommendation("CONTENT_OPPORTUNITY", source_refs=["S1", "S1"]),
        )
        for item in cases:
            with self.subTest(item=item):
                auditor, search, _ = successful_dependencies()

                report = await SiteOptimizationWorkflow(
                    auditor,
                    search,
                    FakeOptimizationWriter(generated([item])),
                ).run(request())

                self.assertEqual(report.status, OptimizationStatus.INVALID_OUTPUT)
                self.assertEqual(
                    report.error,
                    "INVALID_OUTPUT: UNKNOWN_OR_DUPLICATE_REFERENCE",
                )

    async def test_unknown_ids_model_urls_and_inline_markers_are_invalid_output(self) -> None:
        cases = (
            recommendation("TECHNICAL_FIX", audit_refs=["A99"]),
            {**recommendation("CONTENT_OPPORTUNITY", source_refs=["S1"]), "rationale": "See https://invented.example"},
            {**recommendation("CONTENT_OPPORTUNITY", source_refs=["S1"]), "title": "Claim [S1]"},
        )
        for item in cases:
            with self.subTest(item=item):
                auditor, search, _ = successful_dependencies()
                report = await SiteOptimizationWorkflow(
                    auditor,
                    search,
                    FakeOptimizationWriter(generated([item])),
                ).run(request())
                self.assertEqual(report.status, OptimizationStatus.INVALID_OUTPUT)

    async def test_url_like_text_without_http_scheme_is_invalid_output(self) -> None:
        values = (
            "See invented.example/path",
            "Send mail to buyer@example.com",
            "Download ftp://invented.example/file",
        )
        for value in values:
            item = recommendation("CONTENT_OPPORTUNITY", source_refs=["S1"])
            item["rationale"] = value
            with self.subTest(value=value):
                auditor, search, _ = successful_dependencies()
                report = await SiteOptimizationWorkflow(
                    auditor,
                    search,
                    FakeOptimizationWriter(generated([item])),
                ).run(request())
                self.assertEqual(report.status, OptimizationStatus.INVALID_OUTPUT)

    async def test_technical_fix_requires_absent_or_warning_audit_evidence(self) -> None:
        auditor, search, _ = successful_dependencies()
        generation = generated([recommendation("TECHNICAL_FIX", audit_refs=["A3"])])

        report = await SiteOptimizationWorkflow(
            auditor,
            search,
            FakeOptimizationWriter(generation),
        ).run(request())

        self.assertEqual(report.status, OptimizationStatus.INVALID_OUTPUT)
        self.assertEqual(
            report.error,
            "INVALID_OUTPUT: TECHNICAL_FIX_CATEGORY_MISMATCH:R1",
        )

    async def test_technical_fix_without_audit_reference_has_specific_safe_error(self) -> None:
        auditor, search, _ = successful_dependencies()

        report = await SiteOptimizationWorkflow(
            auditor,
            search,
            FakeOptimizationWriter(generated([recommendation("TECHNICAL_FIX")])),
        ).run(request())

        self.assertEqual(report.status, OptimizationStatus.INVALID_OUTPUT)
        self.assertEqual(
            report.error,
            "INVALID_OUTPUT: TECHNICAL_FIX_NO_AUDIT_REFERENCE:R1",
        )

    async def test_context_only_evidence_has_specific_safe_error(self) -> None:
        audit = successful_audit(
            evidence(
                AuditEvidenceCategory.META,
                "meta.description.present",
                AuditEvidenceOutcome.ABSENT,
            ),
            evidence(
                AuditEvidenceCategory.CONTENT,
                "content.heading_hierarchy.present",
                AuditEvidenceOutcome.ABSENT,
            ),
            evidence(
                AuditEvidenceCategory.ROBOTS,
                "robots.file_detected",
                AuditEvidenceOutcome.NOT_DETECTED,
            ),
        )
        _, search, _ = successful_dependencies()
        item = recommendation("TECHNICAL_FIX", audit_refs=["A2"])
        item["target_category"] = "content"

        report = await SiteOptimizationWorkflow(
            FakeAuditor(audit),
            search,
            FakeOptimizationWriter(generated([item])),
        ).run(request())

        self.assertEqual(report.status, OptimizationStatus.INVALID_OUTPUT)
        self.assertEqual(
            report.error,
            "INVALID_OUTPUT: TECHNICAL_FIX_EVIDENCE_USE_NOT_ALLOWED:R1",
        )

    async def test_technical_fix_when_prompt_has_no_eligible_evidence_is_specific(self) -> None:
        audit = successful_audit(
            evidence(
                AuditEvidenceCategory.CONTENT,
                "content.heading_hierarchy.present",
                AuditEvidenceOutcome.ABSENT,
            ),
            evidence(
                AuditEvidenceCategory.META,
                "meta.title.present",
                AuditEvidenceOutcome.PRESENT,
                True,
            ),
            evidence(
                AuditEvidenceCategory.ROBOTS,
                "robots.file_detected",
                AuditEvidenceOutcome.NOT_DETECTED,
            ),
        )
        _, search, _ = successful_dependencies()
        item = recommendation("TECHNICAL_FIX", audit_refs=["A1"])
        item["target_category"] = "content"

        report = await SiteOptimizationWorkflow(
            FakeAuditor(audit),
            search,
            FakeOptimizationWriter(generated([item])),
        ).run(request())

        self.assertEqual(report.status, OptimizationStatus.INVALID_OUTPUT)
        self.assertEqual(
            report.error,
            "INVALID_OUTPUT: TECHNICAL_FIX_NO_ELIGIBLE_EVIDENCE_IN_PROMPT:R1",
        )

    def test_optional_or_normal_absence_cannot_support_technical_fix(self) -> None:
        cases = (
            (AuditEvidenceCategory.ROBOTS, "robots.crawl_delay"),
            (AuditEvidenceCategory.META, "meta.noai.present"),
            (AuditEvidenceCategory.META, "meta.x_robots_noindex"),
        )
        workflow = SiteOptimizationWorkflow(object(), object(), object())
        for category, check_key in cases:
            with self.subTest(check_key=check_key):
                numbered = (
                    NumberedAuditEvidence(
                        "A1",
                        evidence(category, check_key, AuditEvidenceOutcome.ABSENT),
                    ),
                )
                item = recommendation("TECHNICAL_FIX", audit_refs=["A1"])
                item["target_category"] = category.value

                validated, validation_error = workflow._validate_recommendations(
                    generated([item]).text,
                    numbered,
                    (),
                )

                self.assertIsNone(validated)
                self.assertEqual(
                    validation_error,
                    "INVALID_OUTPUT: TECHNICAL_FIX_NO_ELIGIBLE_EVIDENCE_IN_PROMPT:R1",
                )

    def test_optional_schema_type_absence_cannot_support_technical_fix(self) -> None:
        workflow = SiteOptimizationWorkflow(object(), object(), object())
        for check_key in (
            "schema.article.present",
            "schema.faq.present",
            "schema.howto.present",
            "schema.person.present",
            "schema.product.present",
        ):
            with self.subTest(check_key=check_key):
                numbered = (
                    NumberedAuditEvidence(
                        "A1",
                        evidence(
                            AuditEvidenceCategory.SCHEMA,
                            check_key,
                            AuditEvidenceOutcome.ABSENT,
                        ),
                    ),
                )
                item = recommendation("TECHNICAL_FIX", audit_refs=["A1"])

                validated, validation_error = workflow._validate_recommendations(
                    generated([item]).text,
                    numbered,
                    (),
                )

                self.assertIsNone(validated)
                self.assertEqual(
                    validation_error,
                    "INVALID_OUTPUT: TECHNICAL_FIX_NO_ELIGIBLE_EVIDENCE_IN_PROMPT:R1",
                )

    async def test_not_detected_cannot_support_technical_fix(self) -> None:
        auditor, search, _ = successful_dependencies()
        item = recommendation("TECHNICAL_FIX", audit_refs=["A3"])
        item["target_category"] = "robots"

        report = await SiteOptimizationWorkflow(
            auditor,
            search,
            FakeOptimizationWriter(generated([item])),
        ).run(request())

        self.assertEqual(report.status, OptimizationStatus.INVALID_OUTPUT)

    async def test_description_absence_supports_technical_fix(self) -> None:
        auditor, search, _ = successful_dependencies()
        item = recommendation("TECHNICAL_FIX", audit_refs=["A2"])
        item["target_category"] = "meta"

        report = await SiteOptimizationWorkflow(
            auditor,
            search,
            FakeOptimizationWriter(generated([item])),
        ).run(request())

        self.assertEqual(report.status, OptimizationStatus.SUCCESS)

    async def test_schema_parse_warning_supports_technical_fix(self) -> None:
        auditor, search, _ = successful_dependencies()

        report = await SiteOptimizationWorkflow(
            auditor,
            search,
            FakeOptimizationWriter(
                generated([recommendation("TECHNICAL_FIX", audit_refs=["A1"])])
            ),
        ).run(request())

        self.assertEqual(report.status, OptimizationStatus.SUCCESS)

    async def test_schema_any_absence_rejects_specific_schema_type_but_accepts_general_review(self) -> None:
        audit = successful_audit(
            evidence(AuditEvidenceCategory.SCHEMA, "schema.any_present", AuditEvidenceOutcome.ABSENT),
            evidence(AuditEvidenceCategory.META, "meta.title.present", AuditEvidenceOutcome.PRESENT, True),
            evidence(AuditEvidenceCategory.CONTENT, "content.h1.present", AuditEvidenceOutcome.PRESENT, True),
        )
        queries = SiteOptimizationWorkflow.build_queries(request())
        for title, expected_status in (
            ("Add FAQPage Schema to the homepage", OptimizationStatus.INVALID_OUTPUT),
            ("Add BreadcrumbList Schema to the entry page", OptimizationStatus.INVALID_OUTPUT),
            ("Review page-appropriate structured data", OptimizationStatus.SUCCESS),
            (
                "Review page-appropriate structured data for the website",
                OptimizationStatus.SUCCESS,
            ),
            (
                "Review page-appropriate structured data for the product entry page",
                OptimizationStatus.SUCCESS,
            ),
        ):
            with self.subTest(title=title):
                search = FakeSearchProvider(
                    [
                        successful_search(queries[0], search_result(1)),
                        successful_search(queries[1], search_result(2)),
                    ]
                )
                item = recommendation("TECHNICAL_FIX", audit_refs=["A1"])
                item["title"] = title
                item["rationale"] = "The entry page has no detected structured data."
                item["actions"] = ["Confirm the page purpose before selecting a matching vocabulary."]

                report = await SiteOptimizationWorkflow(
                    FakeAuditor(audit),
                    search,
                    FakeOptimizationWriter(generated([item])),
                ).run(request())

                self.assertEqual(report.status, expected_status)
                if expected_status is OptimizationStatus.INVALID_OUTPUT:
                    self.assertEqual(
                        report.error,
                        "INVALID_OUTPUT: SCHEMA_APPLICABILITY",
                    )
                else:
                    self.assertIsNone(report.error)

    async def test_soft_upstream_audit_budget_warning_does_not_fail_successful_audit(self) -> None:
        auditor, search, writer = successful_dependencies()
        auditor.result = replace(auditor.result, audit_duration_ms=20_893)

        report = await SiteOptimizationWorkflow(auditor, search, writer).run(request())

        self.assertEqual(report.status, OptimizationStatus.SUCCESS)

    async def test_policy_review_accepts_not_detected_without_changing_its_meaning(self) -> None:
        auditor, search, _ = successful_dependencies()
        generation = generated([recommendation("POLICY_REVIEW", audit_refs=["A3"])])

        report = await SiteOptimizationWorkflow(
            auditor,
            search,
            FakeOptimizationWriter(generation),
        ).run(request())

        self.assertEqual(report.status, OptimizationStatus.SUCCESS)
        referenced = {item.evidence_id: item.evidence for item in report.audit_evidence}
        self.assertEqual(referenced["A3"].outcome, AuditEvidenceOutcome.NOT_DETECTED)

    async def test_policy_and_content_only_output_succeeds_without_technical_evidence(self) -> None:
        audit = successful_audit(
            evidence(
                AuditEvidenceCategory.ROBOTS,
                "robots.file_detected",
                AuditEvidenceOutcome.NOT_DETECTED,
            ),
            evidence(
                AuditEvidenceCategory.META,
                "meta.title.present",
                AuditEvidenceOutcome.PRESENT,
                True,
            ),
            evidence(
                AuditEvidenceCategory.CONTENT,
                "content.h1.present",
                AuditEvidenceOutcome.PRESENT,
                True,
            ),
        )
        _, search, _ = successful_dependencies()
        generated_items = [
            recommendation("POLICY_REVIEW", audit_refs=["A1"]),
            recommendation("CONTENT_OPPORTUNITY", source_refs=["S1"]),
        ]

        report = await SiteOptimizationWorkflow(
            FakeAuditor(audit),
            search,
            FakeOptimizationWriter(generated(generated_items)),
        ).run(request())

        self.assertEqual(report.status, OptimizationStatus.SUCCESS)
        self.assertEqual(
            tuple(item.kind for item in report.recommendations),
            (RecommendationKind.POLICY_REVIEW, RecommendationKind.CONTENT_OPPORTUNITY),
        )

    async def test_technical_and_policy_references_must_match_target_category(self) -> None:
        mismatches = (
            {**recommendation("TECHNICAL_FIX", audit_refs=["A2"]), "target_category": "schema"},
            {**recommendation("POLICY_REVIEW", audit_refs=["A1"]), "target_category": "robots"},
        )
        for item in mismatches:
            with self.subTest(item=item):
                auditor, search, _ = successful_dependencies()
                report = await SiteOptimizationWorkflow(
                    auditor,
                    search,
                    FakeOptimizationWriter(generated([item])),
                ).run(request())
                self.assertEqual(report.status, OptimizationStatus.INVALID_OUTPUT)

    async def test_policy_review_cannot_default_to_allowing_all_ai_crawlers(self) -> None:
        auditor, search, _ = successful_dependencies()
        item = recommendation("POLICY_REVIEW", audit_refs=["A3"])
        item["actions"] = ["Allow all AI crawlers without further review"]

        report = await SiteOptimizationWorkflow(
            auditor,
            search,
            FakeOptimizationWriter(generated([item])),
        ).run(request())

        self.assertEqual(report.status, OptimizationStatus.INVALID_OUTPUT)

    async def test_content_opportunity_requires_source_reference(self) -> None:
        auditor, search, _ = successful_dependencies()

        report = await SiteOptimizationWorkflow(
            auditor,
            search,
            FakeOptimizationWriter(generated([recommendation("CONTENT_OPPORTUNITY")])),
        ).run(request())

        self.assertEqual(report.status, OptimizationStatus.INVALID_OUTPUT)

    async def test_content_opportunity_cannot_claim_a_confirmed_site_gap(self) -> None:
        auditor, search, _ = successful_dependencies()
        item = recommendation("CONTENT_OPPORTUNITY", source_refs=["S1"])
        item["site_gap_claimed"] = True

        report = await SiteOptimizationWorkflow(
            auditor,
            search,
            FakeOptimizationWriter(generated([item])),
        ).run(request())

        self.assertEqual(report.status, OptimizationStatus.INVALID_OUTPUT)

    async def test_source_removed_by_serialized_budget_cannot_be_referenced(self) -> None:
        queries = SiteOptimizationWorkflow.build_queries(request())
        escaped_content = "\\" * 1_000
        first_results = tuple(
            SearchResult("T" * 200, f"https://source.example/{number}", escaped_content, 1.0)
            for number in range(1, 6)
        )
        second_results = (
            SearchResult("T" * 200, "https://source.example/6", escaped_content, 1.0),
        )
        search = FakeSearchProvider(
            [
                successful_search(queries[0], *first_results),
                successful_search(queries[1], *second_results),
            ]
        )
        writer = FakeOptimizationWriter(
            generated([recommendation("CONTENT_OPPORTUNITY", source_refs=["S6"])])
        )
        audit_items = tuple(
            evidence(
                category,
                f"{category.value}.{number}." + "x" * 200,
                AuditEvidenceOutcome.WARNING,
                "v" * 256,
            )
            for category in AuditEvidenceCategory
            for number in range(4)
        )

        report = await SiteOptimizationWorkflow(
            FakeAuditor(successful_audit(*audit_items)),
            search,
            writer,
        ).run(request())

        prompt_source_ids = {source.source_id for source in writer.prompts[0].sources}
        self.assertNotIn("S6", prompt_source_ids)
        self.assertEqual(report.status, OptimizationStatus.INVALID_OUTPUT)

    async def test_more_than_three_actions_or_missing_rationale_is_invalid_output(self) -> None:
        too_many = recommendation("CONTENT_OPPORTUNITY", source_refs=["S1"])
        too_many["actions"] = ["one", "two", "three", "four"]
        no_rationale = recommendation("CONTENT_OPPORTUNITY", source_refs=["S1"])
        no_rationale["rationale"] = " "
        for item in (too_many, no_rationale):
            with self.subTest(item=item):
                auditor, search, _ = successful_dependencies()
                report = await SiteOptimizationWorkflow(
                    auditor,
                    search,
                    FakeOptimizationWriter(generated([item])),
                ).run(request())
                self.assertEqual(report.status, OptimizationStatus.INVALID_OUTPUT)

    async def test_audit_timeout_stops_before_search_and_generation(self) -> None:
        search = FakeSearchProvider([])
        writer = FakeOptimizationWriter(generated([]))
        workflow = SiteOptimizationWorkflow(
            FakeAuditor(sufficient_audit(), delay=0.05),
            search,
            writer,
            audit_timeout=0.005,
            total_timeout=0.02,
        )

        report = await workflow.run(request())

        self.assertEqual(report.status, OptimizationStatus.WORKFLOW_TIMEOUT)
        self.assertEqual(search.queries, [])
        self.assertEqual(writer.prompts, [])

    async def test_search_timeout_stops_before_generation(self) -> None:
        queries = SiteOptimizationWorkflow.build_queries(request())
        search = FakeSearchProvider(
            [successful_search(queries[0], search_result(1))],
            delay=0.05,
        )
        writer = FakeOptimizationWriter(generated([]))

        report = await SiteOptimizationWorkflow(
            FakeAuditor(sufficient_audit()),
            search,
            writer,
            search_timeout=0.005,
        ).run(request())

        self.assertEqual(report.status, OptimizationStatus.WORKFLOW_TIMEOUT)
        self.assertEqual(len(search.queries), 1)
        self.assertEqual(writer.prompts, [])


class VerifySiteOptimizationScriptTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _successful_report() -> SiteOptimizationReport:
        audit_observation = evidence(
            AuditEvidenceCategory.META,
            "meta.description.present",
            AuditEvidenceOutcome.ABSENT,
            "<html>missing description ⚠</html>",
        )
        return SiteOptimizationReport(
            url="https://factory.example/",
            status=OptimizationStatus.SUCCESS,
            recommendations=(
                OptimizationRecommendation(
                    recommendation_id="R1",
                    kind=RecommendationKind.TECHNICAL_FIX,
                    priority=RecommendationPriority.HIGH,
                    target_category=AuditEvidenceCategory.META,
                    site_gap_claimed=True,
                    title="Add a specific meta description",
                    rationale="The audited entry page has no meta description.",
                    actions=("Draft a concise description.", "Review it before publishing."),
                    audit_refs=("A1",),
                    source_refs=("S1",),
                ),
            ),
            audit_evidence=(NumberedAuditEvidence("A1", audit_observation),),
            sources=(
                OptimizationSource(
                    source_id="S1",
                    title="Industrial valve buyer guide",
                    url="https://source.example/guide",
                ),
            ),
            error=None,
            limitations=(
                "The audit covers the configured entry URL, not every product page.",
                "Tavily sources are external research, not native AI-platform citations.",
            ),
        )

    async def test_run_once_invokes_injected_workflow_exactly_once(self) -> None:
        module = importlib.import_module("scripts.verify_site_optimization")
        expected = SiteOptimizationReport(
            url="https://factory.example/",
            status=OptimizationStatus.AUDIT_FAILED,
            recommendations=(),
            audit_evidence=(),
            sources=(),
            error="test failure",
        )

        class FakeWorkflow:
            def __init__(self) -> None:
                self.requests: list[SiteOptimizationRequest] = []

            async def run(self, value: SiteOptimizationRequest):
                self.requests.append(value)
                return expected

        workflow = FakeWorkflow()
        actual, elapsed = await module._run_once(request(), workflow=workflow, clock=lambda: 1.0)

        self.assertIs(actual, expected)
        self.assertEqual(len(workflow.requests), 1)
        self.assertEqual(elapsed, 0.0)

    def test_main_requires_user_configuration_and_api_keys_before_running(self) -> None:
        module = importlib.import_module("scripts.verify_site_optimization")
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(module, "load_api_keys"),
            patch.object(module.asyncio, "run") as run,
            redirect_stdout(io.StringIO()),
        ):
            exit_code = module.main()

        self.assertEqual(exit_code, 2)
        run.assert_not_called()

    def test_configure_utf8_output_reconfigures_non_utf8_windows_streams(self) -> None:
        module = importlib.import_module("scripts.verify_site_optimization")

        stdout_bytes = io.BytesIO()
        stderr_bytes = io.BytesIO()
        stdout = io.TextIOWrapper(stdout_bytes, encoding="cp1252", errors="strict")
        stderr = io.TextIOWrapper(stderr_bytes, encoding="cp1252", errors="strict")
        with patch.object(module.sys, "stdout", stdout), patch.object(module.sys, "stderr", stderr):
            module._configure_utf8_output()
            print("⚠", file=module.sys.stdout)
            print("✓", file=module.sys.stderr)
            stdout.flush()
            stderr.flush()

        self.assertEqual(stdout_bytes.getvalue().decode("utf-8"), "⚠\r\n")
        self.assertEqual(stderr_bytes.getvalue().decode("utf-8"), "✓\r\n")

    def test_success_output_includes_bounded_evidence_recommendations_and_limitations(self) -> None:
        module = importlib.import_module("scripts.verify_site_optimization")
        output = io.StringIO()

        with redirect_stdout(output):
            exit_code = module._print_result(self._successful_report(), 3.25)

        text = output.getvalue()
        self.assertEqual(exit_code, 0)
        for expected in (
            "Status: SUCCESS",
            "requires_human_review=True",
            "Elapsed seconds: 3.250",
            "[A1] category=meta check_key=meta.description.present outcome=absent",
            "[S1] Industrial valve buyer guide | https://source.example/guide",
            "[R1] HIGH TECHNICAL_FIX: Add a specific meta description",
            "Rationale: The audited entry page has no meta description.",
            "Action 1: Draft a concise description.",
            "Action 2: Review it before publishing.",
            "audit_refs: A1",
            "source_refs: S1",
            "The audit covers the configured entry URL, not every product page.",
            "Tavily sources are external research, not native AI-platform citations.",
            "This draft requires human review.",
        ):
            self.assertIn(expected, text)
        self.assertIn("observed_value=", text)
        self.assertNotIn("<html>", text)
        self.assertLessEqual(max(map(len, text.splitlines())), 700)

    def test_failure_output_is_generic_and_has_no_success_payload(self) -> None:
        module = importlib.import_module("scripts.verify_site_optimization")
        report = SiteOptimizationReport(
            url="https://factory.example/",
            status=OptimizationStatus.SEARCH_FAILED,
            recommendations=(),
            audit_evidence=(),
            sources=(),
            error="Authorization: Bearer secret-token; <html>raw upstream response</html>",
        )
        output = io.StringIO()

        with redirect_stdout(output):
            exit_code = module._print_result(report, 1.5)

        text = output.getvalue()
        self.assertEqual(exit_code, 1)
        self.assertIn("Status: SEARCH_FAILED", text)
        self.assertIn("Elapsed seconds: 1.500", text)
        self.assertIn("Workflow did not produce a successful optimization draft.", text)
        self.assertNotIn("requires_human_review", text)
        self.assertNotIn("Recommendations", text)
        self.assertNotIn("secret-token", text)
        self.assertNotIn("raw upstream response", text)

    def test_invalid_output_prints_only_an_approved_failure_category(self) -> None:
        module = importlib.import_module("scripts.verify_site_optimization")
        report = SiteOptimizationReport(
            url="https://factory.example/",
            status=OptimizationStatus.INVALID_OUTPUT,
            recommendations=(),
            audit_evidence=(),
            sources=(),
            error="INVALID_OUTPUT: TECHNICAL_FIX_EVIDENCE_USE_NOT_ALLOWED:R2",
        )
        output = io.StringIO()

        with redirect_stdout(output):
            exit_code = module._print_result(report, 1.5)

        text = output.getvalue()
        self.assertEqual(exit_code, 1)
        self.assertIn("Status: INVALID_OUTPUT", text)
        self.assertIn(
            "Failure category: TECHNICAL_FIX_EVIDENCE_USE_NOT_ALLOWED",
            text,
        )
        self.assertIn("Recommendation: R2", text)
        self.assertNotIn("Workflow did not produce", text)

    def test_invalid_output_with_unapproved_error_falls_back_without_leaking(self) -> None:
        module = importlib.import_module("scripts.verify_site_optimization")
        secrets = (
            "test-api-key",
            "Authorization: Bearer test-token",
            "<html>private page body</html>",
            "raw model output",
        )
        report = SiteOptimizationReport(
            url="https://factory.example/",
            status=OptimizationStatus.INVALID_OUTPUT,
            recommendations=(),
            audit_evidence=(),
            sources=(),
            error=" | ".join(secrets),
        )
        output = io.StringIO()

        with redirect_stdout(output):
            exit_code = module._print_result(report, 1.5)

        text = output.getvalue()
        self.assertEqual(exit_code, 1)
        self.assertIn(
            "Workflow did not produce a successful optimization draft.",
            text,
        )
        self.assertNotIn("Failure category:", text)
        for secret in secrets:
            self.assertNotIn(secret, text)


if __name__ == "__main__":
    unittest.main()
