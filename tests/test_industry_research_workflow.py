import unittest

from foreign_trade_geo_agent.core.research import (
    ResearchEvidenceClassification,
    ResearchEvidencePacket,
    ResearchGeneration,
    ResearchGenerationStatus,
    ResearchMaterial,
    ResearchStatus,
)
from foreign_trade_geo_agent.core.search import (
    SearchResponse,
    SearchResult,
    SearchStatus,
)
from foreign_trade_geo_agent.workflows.industry_research import (
    IndustryResearchWorkflow,
)


def search_result(
    number: int,
    *,
    title: str | None = None,
    url: str | None = None,
    content: str = "Evidence about the industry.",
) -> SearchResult:
    return SearchResult(
        title=title if title is not None else f"Source {number}",
        url=url if url is not None else f"https://example.com/source-{number}",
        content=content,
        score=1.0 - number / 100,
    )


def successful_search(*results: SearchResult) -> SearchResponse:
    return SearchResponse(
        query="industrial valve market",
        status=SearchStatus.SUCCESS,
        results=tuple(results),
        error=None,
    )


def successful_generation(text: str) -> ResearchGeneration:
    return ResearchGeneration(
        provider="deepseek",
        model="deepseek-flash",
        status=ResearchGenerationStatus.SUCCESS,
        text=text,
        error=None,
    )


class FakeSearchProvider:
    def __init__(self, response: SearchResponse) -> None:
        self.response = response
        self.queries: list[str] = []

    async def search(self, query: str) -> SearchResponse:
        self.queries.append(query)
        return self.response


class FakeResearchWriter:
    def __init__(self, response: ResearchGeneration) -> None:
        self.response = response
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    async def write_report(
        self,
        question: str,
        materials: tuple[object, ...],
    ) -> ResearchGeneration:
        self.calls.append((question, materials))
        return self.response


class IndustryResearchWorkflowTests(unittest.IsolatedAsyncioTestCase):
    def test_research_report_keeps_legacy_construction_compatible(self) -> None:
        from foreign_trade_geo_agent.core.research import ResearchReport, ResearchSource

        report = ResearchReport(
            question="market",
            status=ResearchStatus.SUCCESS,
            draft_text="Draft [S1]",
            sources=(ResearchSource("S1", "Source", "https://example.com/source"),),
            error=None,
        )

        self.assertIsNone(report.research_evidence)

    def test_research_evidence_packet_is_immutable_and_unverified(self) -> None:
        packet = ResearchEvidencePacket(
            materials=(
                ResearchMaterial(
                    source_id="S1",
                    title="Source",
                    url="https://example.com/source",
                    content="Bounded evidence.",
                ),
            )
        )

        self.assertEqual(
            packet.classifications,
            (
                ResearchEvidenceClassification.EXTERNAL_RESEARCH_CONTEXT,
                ResearchEvidenceClassification.UNVERIFIED_SEARCH_RESULT,
            ),
        )
        with self.assertRaises((AttributeError, TypeError)):
            packet.materials = ()  # type: ignore[misc]

    def test_research_report_rejects_source_packet_identity_mismatch(self) -> None:
        from foreign_trade_geo_agent.core.research import ResearchReport, ResearchSource

        packet = ResearchEvidencePacket(
            (
                ResearchMaterial(
                    "S1",
                    "Packet source",
                    "https://example.com/source",
                    "Evidence",
                ),
            )
        )
        with self.assertRaisesRegex(ValueError, "match retained evidence"):
            ResearchReport(
                question="market",
                status=ResearchStatus.SUCCESS,
                draft_text="Draft [S1]",
                sources=(
                    ResearchSource(
                        "S1",
                        "Different source",
                        "https://example.com/source",
                    ),
                ),
                error=None,
                research_evidence=packet,
            )

    async def test_returns_human_review_draft_with_trusted_cited_sources(self) -> None:
        search = FakeSearchProvider(
            successful_search(search_result(1), search_result(2), search_result(3))
        )
        writer = FakeResearchWriter(
            successful_generation("## 研究草稿\n\n市场需求正在增长。[S2][S1]")
        )

        report = await IndustryResearchWorkflow(search, writer).run(
            "  industrial valve market  "
        )

        self.assertEqual(search.queries, ["industrial valve market"])
        self.assertEqual(len(writer.calls), 1)
        self.assertEqual(report.status, ResearchStatus.SUCCESS)
        self.assertEqual(report.draft_text, "## 研究草稿\n\n市场需求正在增长。[S2][S1]")
        self.assertTrue(report.requires_human_review)
        self.assertEqual(
            [(source.source_id, source.title, source.url) for source in report.sources],
            [
                ("S2", "Source 2", "https://example.com/source-2"),
                ("S1", "Source 1", "https://example.com/source-1"),
            ],
        )
        self.assertIsNone(report.error)
        self.assertIsNotNone(report.research_evidence)
        assert report.research_evidence is not None
        self.assertEqual(
            [material.source_id for material in report.research_evidence.materials],
            ["S1", "S2", "S3"],
        )
        material_by_id = {
            material.source_id: material
            for material in report.research_evidence.materials
        }
        for source in report.sources:
            material = material_by_id[source.source_id]
            self.assertEqual((source.title, source.url), (material.title, material.url))

    async def test_search_failure_stops_before_generation(self) -> None:
        search = FakeSearchProvider(
            SearchResponse(
                query="industrial valve market",
                status=SearchStatus.FAILED,
                results=(),
                error="search timeout",
            )
        )
        writer = FakeResearchWriter(successful_generation("unused [S1]"))

        report = await IndustryResearchWorkflow(search, writer).run(
            "industrial valve market"
        )

        self.assertEqual(report.status, ResearchStatus.SEARCH_FAILED)
        self.assertEqual(report.draft_text, None)
        self.assertEqual(report.sources, ())
        self.assertEqual(writer.calls, [])
        self.assertIsNone(report.research_evidence)

    async def test_zero_search_results_stop_before_generation(self) -> None:
        writer = FakeResearchWriter(successful_generation("unused [S1]"))

        report = await IndustryResearchWorkflow(
            FakeSearchProvider(successful_search()),
            writer,
        ).run("industrial valve market")

        self.assertEqual(report.status, ResearchStatus.NO_RESULTS)
        self.assertEqual(writer.calls, [])

    async def test_generation_failure_has_no_partial_report(self) -> None:
        failed_generation = ResearchGeneration(
            provider="deepseek",
            model="deepseek-flash",
            status=ResearchGenerationStatus.FAILED,
            text=None,
            error="generation timeout",
        )

        report = await IndustryResearchWorkflow(
            FakeSearchProvider(successful_search(search_result(1))),
            FakeResearchWriter(failed_generation),
        ).run("industrial valve market")

        self.assertEqual(report.status, ResearchStatus.GENERATION_FAILED)
        self.assertIsNone(report.draft_text)
        self.assertEqual(report.sources, ())

    async def test_blank_question_calls_neither_provider(self) -> None:
        search = FakeSearchProvider(successful_search(search_result(1)))
        writer = FakeResearchWriter(successful_generation("unused [S1]"))

        with self.assertRaises(ValueError):
            await IndustryResearchWorkflow(search, writer).run("   ")

        self.assertEqual(search.queries, [])
        self.assertEqual(writer.calls, [])

    async def test_only_valid_http_urls_enter_research_materials(self) -> None:
        overlong_url = "https://example.com/" + "x" * 2_100
        search = FakeSearchProvider(
            successful_search(
                search_result(1, url="ftp://example.com/file"),
                search_result(2, url="https:///missing-host"),
                search_result(3, url="https://example.com/white space"),
                search_result(4, url=overlong_url),
                search_result(5, url="http://example.com/usable"),
            )
        )
        writer = FakeResearchWriter(successful_generation("结论。[S1]"))

        report = await IndustryResearchWorkflow(search, writer).run("market")

        materials = writer.calls[0][1]
        self.assertEqual(len(materials), 1)
        self.assertEqual(materials[0].source_id, "S1")
        self.assertEqual(materials[0].url, "http://example.com/usable")
        self.assertEqual(report.status, ResearchStatus.SUCCESS)

    async def test_all_unusable_results_are_treated_as_no_results(self) -> None:
        writer = FakeResearchWriter(successful_generation("unused [S1]"))
        search = FakeSearchProvider(
            successful_search(
                search_result(1, url="file:///local/file"),
                search_result(2, content="   "),
            )
        )

        report = await IndustryResearchWorkflow(search, writer).run("market")

        self.assertEqual(report.status, ResearchStatus.NO_RESULTS)
        self.assertEqual(writer.calls, [])

    async def test_enforces_source_title_and_content_budgets_before_generation(self) -> None:
        long_title = "  " + "T" * 250 + "  "
        long_content = "word   " * 500
        search = FakeSearchProvider(
            successful_search(
                *[
                    search_result(
                        number,
                        title=long_title,
                        content=long_content,
                    )
                    for number in range(1, 8)
                ]
            )
        )
        writer = FakeResearchWriter(successful_generation("结论。[S1]"))

        await IndustryResearchWorkflow(search, writer).run("market")

        materials = writer.calls[0][1]
        self.assertEqual(len(materials), 5)
        self.assertTrue(all(len(material.title) <= 200 for material in materials))
        self.assertTrue(all(len(material.content) <= 1_200 for material in materials))
        self.assertLessEqual(sum(len(material.content) for material in materials), 6_000)
        self.assertNotIn("  ", materials[0].content)

    async def test_unknown_source_reference_is_invalid_output(self) -> None:
        report = await self._run_with_generated_text("结论。[S9]")

        self.assertEqual(report.status, ResearchStatus.INVALID_OUTPUT)
        self.assertIsNone(report.draft_text)
        self.assertEqual(report.sources, ())

    async def test_report_without_source_reference_is_invalid_output(self) -> None:
        report = await self._run_with_generated_text("没有任何来源编号的结论。")

        self.assertEqual(report.status, ResearchStatus.INVALID_OUTPUT)

    async def test_report_containing_model_generated_url_is_invalid_output(self) -> None:
        report = await self._run_with_generated_text(
            "请查看 https://invented.example/report。[S1]"
        )

        self.assertEqual(report.status, ResearchStatus.INVALID_OUTPUT)

    async def test_malformed_source_marker_is_invalid_output(self) -> None:
        report = await self._run_with_generated_text("结论。[S-one][S1]")

        self.assertEqual(report.status, ResearchStatus.INVALID_OUTPUT)

    async def _run_with_generated_text(self, text: str):
        return await IndustryResearchWorkflow(
            FakeSearchProvider(successful_search(search_result(1))),
            FakeResearchWriter(successful_generation(text)),
        ).run("industrial valve market")


if __name__ == "__main__":
    unittest.main()
