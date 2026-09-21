"""Deterministic Tavily-to-writer industry research workflow."""

import re
from urllib.parse import urlsplit

from foreign_trade_geo_agent.core.ports import ResearchWriter, SearchProvider
from foreign_trade_geo_agent.core.research import (
    ResearchGenerationStatus,
    ResearchMaterial,
    ResearchReport,
    ResearchSource,
    ResearchStatus,
)
from foreign_trade_geo_agent.core.search import SearchResult, SearchStatus


class IndustryResearchWorkflow:
    """Create one sourced Chinese research draft with fixed call limits."""

    max_sources = 5
    max_title_chars = 200
    max_url_chars = 2_048
    max_content_chars_per_source = 1_200
    max_total_content_chars = 6_000

    def __init__(
        self,
        search_provider: SearchProvider,
        research_writer: ResearchWriter,
    ) -> None:
        self._search_provider = search_provider
        self._research_writer = research_writer

    async def run(self, question: str) -> ResearchReport:
        """Run exactly one search followed by at most one generation."""

        canonical_question = question.strip()
        if not canonical_question:
            raise ValueError("Research question must not be empty.")

        search_response = await self._search_provider.search(canonical_question)
        if search_response.status is SearchStatus.FAILED:
            return self._failed(
                canonical_question,
                ResearchStatus.SEARCH_FAILED,
                search_response.error or "Search provider failed.",
            )

        materials = self._prepare_materials(search_response.results)
        if not materials:
            return self._failed(
                canonical_question,
                ResearchStatus.NO_RESULTS,
                "Search returned no usable results.",
            )

        generation = await self._research_writer.write_report(
            canonical_question,
            materials,
        )
        if generation.status is ResearchGenerationStatus.FAILED:
            return self._failed(
                canonical_question,
                ResearchStatus.GENERATION_FAILED,
                generation.error or "Research writer failed.",
            )

        draft_text = generation.text
        if draft_text is None:
            return self._invalid_output(canonical_question)

        sources = self._validated_sources(draft_text, materials)
        if sources is None:
            return self._invalid_output(canonical_question)

        return ResearchReport(
            question=canonical_question,
            status=ResearchStatus.SUCCESS,
            draft_text=draft_text.strip(),
            sources=sources,
            error=None,
        )

    def _prepare_materials(
        self,
        results: tuple[SearchResult, ...],
    ) -> tuple[ResearchMaterial, ...]:
        materials: list[ResearchMaterial] = []
        remaining_content_chars = self.max_total_content_chars

        for result in results:
            if len(materials) >= self.max_sources or remaining_content_chars <= 0:
                break
            if not self._is_usable_url(result.url):
                continue

            content = self._normalize_whitespace(result.content)
            if not content:
                continue
            content_limit = min(
                self.max_content_chars_per_source,
                remaining_content_chars,
            )
            content = content[:content_limit]
            remaining_content_chars -= len(content)

            title = self._normalize_whitespace(result.title)
            title = title[: self.max_title_chars] or "（无标题）"
            materials.append(
                ResearchMaterial(
                    source_id=f"S{len(materials) + 1}",
                    title=title,
                    url=result.url,
                    content=content,
                )
            )

        return tuple(materials)

    def _is_usable_url(self, url: str) -> bool:
        if len(url) > self.max_url_chars or any(character.isspace() for character in url):
            return False
        try:
            parsed = urlsplit(url)
        except ValueError:
            return False
        return parsed.scheme.casefold() in {"http", "https"} and bool(parsed.netloc)

    @staticmethod
    def _normalize_whitespace(value: str) -> str:
        return " ".join(value.split())

    @staticmethod
    def _validated_sources(
        draft_text: str,
        materials: tuple[ResearchMaterial, ...],
    ) -> tuple[ResearchSource, ...] | None:
        text = draft_text.strip()
        if not text or re.search(r"https?://|www\.", text, flags=re.IGNORECASE):
            return None

        marker_candidates = re.findall(r"\[S[^\]]*\]", text)
        if any(re.fullmatch(r"\[S[1-9][0-9]*\]", marker) is None for marker in marker_candidates):
            return None

        referenced_ids = [
            f"S{match.group(1)}"
            for match in re.finditer(r"\[S([1-9][0-9]*)\]", text)
        ]
        if not referenced_ids:
            return None

        material_by_id = {material.source_id: material for material in materials}
        sources: list[ResearchSource] = []
        seen: set[str] = set()
        for source_id in referenced_ids:
            material = material_by_id.get(source_id)
            if material is None:
                return None
            if source_id in seen:
                continue
            seen.add(source_id)
            sources.append(
                ResearchSource(
                    source_id=source_id,
                    title=material.title,
                    url=material.url,
                )
            )
        return tuple(sources)

    @staticmethod
    def _failed(
        question: str,
        status: ResearchStatus,
        error: str,
    ) -> ResearchReport:
        return ResearchReport(
            question=question,
            status=status,
            draft_text=None,
            sources=(),
            error=error,
        )

    def _invalid_output(self, question: str) -> ResearchReport:
        return self._failed(
            question,
            ResearchStatus.INVALID_OUTPUT,
            "Research writer returned an invalid sourced draft.",
        )
