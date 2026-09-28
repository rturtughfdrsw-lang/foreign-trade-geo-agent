"""Deterministic evidence validation and rendering for content opportunities."""

import asyncio
import json
import re
import unicodedata
from urllib.parse import urlsplit, urlunsplit

from foreign_trade_geo_agent.core.content_opportunity import (
    MAX_ACTION_CODES,
    MAX_OPPORTUNITIES,
    MAX_RAW_OUTPUT_BYTES,
    MAX_RAW_OUTPUT_CHARS,
    MAX_RESEARCH_SOURCES,
    MAX_SITE_PACKET_BYTES,
    MAX_SITE_PACKET_CHARS,
    MAX_SITE_PAGES,
    MAX_SOURCE_CONTENT_CHARS,
    MAX_SOURCE_PACKET_BYTES,
    MAX_SOURCE_PACKET_CHARS,
    MAX_SOURCE_TITLE_CHARS,
    MAX_TOPIC_CHARS,
    MAX_TOTAL_SOURCE_CONTENT_CHARS,
    MAX_USER_MATERIAL_BYTES,
    MAX_USER_MATERIAL_CHARS,
    ContentOpportunity,
    ContentOpportunityActionCode,
    ContentOpportunityGeneration,
    ContentOpportunityGenerationStatus,
    ContentOpportunityPage,
    ContentOpportunityPriority,
    ContentOpportunityPrompt,
    ContentOpportunityReport,
    ContentOpportunitySource,
    ContentOpportunitySourceMaterial,
    ContentOpportunitySpecification,
    ContentOpportunityStatus,
    ContentOpportunityType,
    OpportunityEvidenceCatalog,
    OpportunityPageEvidence,
    OpportunitySourceEvidence,
)
from foreign_trade_geo_agent.core.extraction import (
    PageExtractionStatus,
    StructuredContentKind,
)
from foreign_trade_geo_agent.core.ports import ContentOpportunityWriter
from foreign_trade_geo_agent.core.research import (
    ResearchEvidenceClassification,
    ResearchReport,
    ResearchStatus,
)
from foreign_trade_geo_agent.core.site_content import SiteContentPacket


INVALID_OUTPUT_ERROR_PREFIX = "INVALID_OUTPUT: "
INVALID_OUTPUT_CATEGORIES = frozenset(
    {
        "JSON_FORMAT",
        "FIELD_CONTRACT",
        "OUTPUT_TOO_LARGE",
        "REFERENCE_NAMESPACE_NOT_ALLOWED",
        "UNKNOWN_OR_DUPLICATE_REFERENCE",
        "PAGE_REFERENCE_REQUIRED",
        "SOURCE_REFERENCE_REQUIRED",
        "EVIDENCE_USE_NOT_ALLOWED",
        "OPPORTUNITY_TYPE_MISMATCH",
        "UNSUPPORTED_ABSENCE_CLAIM",
        "TOPIC_NOT_GROUNDED",
        "ACTION_NOT_ALLOWED",
    }
)

_ABSENCE_TERMS = (
    "missing",
    "lacks",
    "lack of",
    "not present",
    "absent",
    "缺少",
    "缺失",
    "未覆盖",
    "遗漏",
    "没有",
)
_PAGE_DIRECTED_ACTIONS = frozenset(
    {
        ContentOpportunityActionCode.EXPAND_PAGE_SECTION,
        ContentOpportunityActionCode.REORGANIZE_PAGE_SECTIONS,
        ContentOpportunityActionCode.ADD_INTERNAL_LINK,
    }
)
_ALLOWED_ACTIONS = {
    ContentOpportunityType.EXPAND_OBSERVED_CONTENT: frozenset(
        {
            ContentOpportunityActionCode.EXPAND_PAGE_SECTION,
            ContentOpportunityActionCode.ADD_COMPARISON_TABLE,
            ContentOpportunityActionCode.ADD_INTERNAL_LINK,
        }
    ),
    ContentOpportunityType.REORGANIZE_OBSERVED_CONTENT: frozenset(
        {
            ContentOpportunityActionCode.REORGANIZE_PAGE_SECTIONS,
            ContentOpportunityActionCode.ADD_COMPARISON_TABLE,
            ContentOpportunityActionCode.ADD_INTERNAL_LINK,
        }
    ),
    ContentOpportunityType.NEW_SUPPORTING_CONTENT: frozenset(
        {
            ContentOpportunityActionCode.CREATE_SUPPORTING_RESOURCE,
            ContentOpportunityActionCode.ADD_BUYER_GUIDANCE,
            ContentOpportunityActionCode.ADD_TECHNICAL_DOCUMENTATION,
            ContentOpportunityActionCode.ADD_COMPARISON_TABLE,
            ContentOpportunityActionCode.ADD_INTERNAL_LINK,
        }
    ),
}


class ContentOpportunityWorkflow:
    """Create a bounded opportunity draft without crawling or searching."""

    limitations = (
        "P evidence records observed page content only and never supports absence claims.",
        "S evidence is unverified external search context, not an authoritative or native AI-platform citation.",
        "Truncated inputs are incomplete and cannot establish that omitted content is absent.",
        "Opportunities do not guarantee rankings, AI mentions, or inquiries and require human review.",
    )

    def __init__(
        self,
        writer: ContentOpportunityWriter,
        *,
        generation_timeout: float = 40.0,
        total_timeout: float = 45.0,
    ) -> None:
        for name, value in (
            ("generation_timeout", generation_timeout),
            ("total_timeout", total_timeout),
        ):
            if type(value) not in {int, float} or value <= 0:
                raise ValueError(f"{name} must be positive.")
        self._writer = writer
        self._generation_timeout = float(generation_timeout)
        self._total_timeout = float(total_timeout)

    async def run(
        self,
        site_content: SiteContentPacket,
        research_report: ResearchReport,
    ) -> ContentOpportunityReport:
        if not isinstance(site_content, SiteContentPacket):
            raise TypeError("Content opportunity workflow requires SiteContentPacket.")
        if not isinstance(research_report, ResearchReport):
            raise TypeError("Content opportunity workflow requires ResearchReport.")
        try:
            return await asyncio.wait_for(
                self._run(site_content, research_report),
                timeout=self._total_timeout,
            )
        except (TimeoutError, asyncio.TimeoutError):
            return self._failed(
                ContentOpportunityStatus.WORKFLOW_TIMEOUT,
                "Content opportunity workflow timed out.",
            )

    async def _run(
        self,
        site_content: SiteContentPacket,
        research_report: ResearchReport,
    ) -> ContentOpportunityReport:
        packet_json = site_content.to_json()
        if (
            len(site_content.pages) > MAX_SITE_PAGES
            or len(packet_json) > MAX_SITE_PACKET_CHARS
            or len(packet_json.encode("utf-8")) > MAX_SITE_PACKET_BYTES
        ):
            return self._failed(
                ContentOpportunityStatus.INPUT_TOO_LARGE,
                "Content opportunity input exceeds the fixed budget.",
            )

        prepared = self._prepare_sources(research_report)
        if prepared is None:
            return self._failed(
                ContentOpportunityStatus.INSUFFICIENT_RESEARCH_EVIDENCE,
                "Insufficient cross-validated research evidence.",
            )
        sources, report_sources, selection_truncated = prepared
        catalog = self._build_catalog(site_content, sources)
        prompt = ContentOpportunityPrompt(
            site_content=site_content,
            catalog=catalog,
            sources=sources,
            research_sources_truncated=selection_truncated,
        )
        source_json = prompt.source_material_json()
        material_json = prompt.material_json()
        if (
            len(source_json) > MAX_SOURCE_PACKET_CHARS
            or len(source_json.encode("utf-8")) > MAX_SOURCE_PACKET_BYTES
            or len(material_json) > MAX_USER_MATERIAL_CHARS
            or len(material_json.encode("utf-8")) > MAX_USER_MATERIAL_BYTES
        ):
            return self._failed(
                ContentOpportunityStatus.INPUT_TOO_LARGE,
                "Content opportunity input exceeds the fixed budget.",
            )

        try:
            generation = await asyncio.wait_for(
                self._writer.write_content_opportunities(prompt),
                timeout=self._generation_timeout,
            )
        except (TimeoutError, asyncio.TimeoutError):
            raise
        except Exception:
            return self._failed(
                ContentOpportunityStatus.GENERATION_FAILED,
                "Content opportunity writer raised an exception.",
            )
        if not isinstance(generation, ContentOpportunityGeneration):
            return self._failed(
                ContentOpportunityStatus.GENERATION_FAILED,
                "Content opportunity writer returned an invalid result.",
            )
        if generation.status is ContentOpportunityGenerationStatus.FAILED:
            return self._failed(
                ContentOpportunityStatus.GENERATION_FAILED,
                "Content opportunity generation failed.",
            )

        opportunities, error = self._validate_and_render(generation.text, prompt)
        if opportunities is None:
            assert error is not None
            return self._failed(ContentOpportunityStatus.INVALID_OUTPUT, error)

        pages = tuple(
            ContentOpportunityPage(item.evidence_id, item.final_url, item.title)
            for item in site_content.pages
        )
        return ContentOpportunityReport(
            status=ContentOpportunityStatus.SUCCESS,
            opportunities=opportunities,
            pages=pages,
            sources=report_sources,
            limitations=self.limitations,
            error=None,
        )

    def _prepare_sources(
        self,
        report: ResearchReport,
    ) -> tuple[
        tuple[ContentOpportunitySourceMaterial, ...],
        tuple[ContentOpportunitySource, ...],
        bool,
    ] | None:
        if report.status is not ResearchStatus.SUCCESS or report.research_evidence is None:
            return None
        material_by_id = {
            material.source_id: material
            for material in report.research_evidence.materials
        }
        selected: list[ContentOpportunitySourceMaterial] = []
        display: list[ContentOpportunitySource] = []
        seen_urls: set[str] = set()
        total_content = 0
        usable_seen = 0
        classifications = report.research_evidence.classifications

        for source in report.sources:
            material = material_by_id.get(source.source_id)
            if material is None:
                return None
            if (
                type(material.title) is not str
                or type(material.content) is not str
                or type(material.url) is not str
                or type(source.title) is not str
                or type(source.url) is not str
            ):
                continue
            if material.title != source.title or material.url != source.url:
                return None
            normalized_url = self._normalized_url(material.url)
            title = self._normalize(material.title)
            content = self._normalize(material.content)
            if normalized_url is None or not title or not content:
                continue
            if normalized_url in seen_urls:
                continue
            seen_urls.add(normalized_url)
            usable_seen += 1
            if len(selected) >= MAX_RESEARCH_SOURCES:
                continue
            remaining = MAX_TOTAL_SOURCE_CONTENT_CHARS - total_content
            if remaining <= 0:
                continue
            bounded_title = title[:MAX_SOURCE_TITLE_CHARS]
            bounded_content = content[: min(MAX_SOURCE_CONTENT_CHARS, remaining)]
            total_content += len(bounded_content)
            selected.append(
                ContentOpportunitySourceMaterial(
                    source_id=source.source_id,
                    title=bounded_title,
                    content=bounded_content,
                    content_truncated=len(bounded_content) < len(content),
                )
            )
            display.append(
                ContentOpportunitySource(
                    source_id=source.source_id,
                    title=source.title,
                    url=source.url,
                    classifications=classifications,
                )
            )
        if not selected:
            return None
        return tuple(selected), tuple(display), usable_seen > len(selected)

    @staticmethod
    def _build_catalog(
        packet: SiteContentPacket,
        sources: tuple[ContentOpportunitySourceMaterial, ...],
    ) -> OpportunityEvidenceCatalog:
        pages: list[OpportunityPageEvidence] = []
        for page in packet.pages:
            has_observed = page.extraction_status is PageExtractionStatus.SUCCESS and (
                bool(page.body_text and page.body_text.strip())
                or any(
                    block.kind is not StructuredContentKind.IMAGE_ALT
                    for block in page.structured_content
                )
            )
            has_context = any(
                block.kind is StructuredContentKind.IMAGE_ALT
                for block in page.structured_content
            )
            pages.append(
                OpportunityPageEvidence(
                    evidence_id=page.evidence_id,
                    extraction_status=page.extraction_status,
                    content_truncated=page.content_truncated,
                    structured_content_truncated=page.structured_content_truncated,
                    evidence_scope=packet.evidence_scope,
                    supports_absence_claims=packet.supports_absence_claims,
                    has_observed_present=has_observed,
                    context_only_only=has_context and not has_observed,
                )
            )
        classifications = (
            ResearchEvidenceClassification.EXTERNAL_RESEARCH_CONTEXT,
            ResearchEvidenceClassification.UNVERIFIED_SEARCH_RESULT,
        )
        return OpportunityEvidenceCatalog(
            pages=tuple(pages),
            sources=tuple(
                OpportunitySourceEvidence(
                    evidence_id=source.source_id,
                    content_truncated=source.content_truncated,
                    classifications=classifications,
                )
                for source in sources
            ),
        )

    def _validate_and_render(
        self,
        text: str | None,
        prompt: ContentOpportunityPrompt,
    ) -> tuple[tuple[ContentOpportunity, ...] | None, str | None]:
        if text is None:
            return self._invalid("JSON_FORMAT")
        if (
            len(text) > MAX_RAW_OUTPUT_CHARS
            or len(text.encode("utf-8")) > MAX_RAW_OUTPUT_BYTES
        ):
            return self._invalid("OUTPUT_TOO_LARGE")
        try:
            payload = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return self._invalid("JSON_FORMAT")
        if type(payload) is not dict or set(payload) != {"opportunities"}:
            return self._invalid("FIELD_CONTRACT")
        raw_items = payload["opportunities"]
        if type(raw_items) is not list or len(raw_items) > MAX_OPPORTUNITIES:
            return self._invalid("FIELD_CONTRACT")

        rendered: list[ContentOpportunity] = []
        for number, raw in enumerate(raw_items, start=1):
            specification, error = self._validate_specification(raw, prompt)
            if specification is None:
                return None, error
            rendered.append(self._render(number, specification))
        return tuple(rendered), None

    def _validate_specification(
        self,
        raw: object,
        prompt: ContentOpportunityPrompt,
    ) -> tuple[ContentOpportunitySpecification | None, str | None]:
        expected = {
            "opportunity_type",
            "priority",
            "topic",
            "action_codes",
            "page_refs",
            "source_refs",
        }
        if type(raw) is not dict or set(raw) != expected:
            return self._invalid("FIELD_CONTRACT")
        try:
            opportunity_type = ContentOpportunityType(raw["opportunity_type"])
            priority = ContentOpportunityPriority(raw["priority"])
        except (TypeError, ValueError):
            return self._invalid("FIELD_CONTRACT")

        topic, topic_error = self._validated_topic(raw["topic"])
        if topic is None:
            return self._invalid(topic_error or "FIELD_CONTRACT")
        action_codes = self._validated_actions(raw["action_codes"])
        if action_codes is None:
            return self._invalid("ACTION_NOT_ALLOWED")
        page_refs, page_error = self._validated_refs(
            raw["page_refs"], "P", set(prompt.catalog.page_by_id())
        )
        if page_refs is None:
            return self._invalid(page_error or "FIELD_CONTRACT")
        source_refs, source_error = self._validated_refs(
            raw["source_refs"], "S", set(prompt.catalog.source_by_id())
        )
        if source_refs is None:
            return self._invalid(source_error or "FIELD_CONTRACT")

        if opportunity_type in {
            ContentOpportunityType.EXPAND_OBSERVED_CONTENT,
            ContentOpportunityType.REORGANIZE_OBSERVED_CONTENT,
        } and not page_refs:
            return self._invalid("PAGE_REFERENCE_REQUIRED")
        if not source_refs:
            return self._invalid("SOURCE_REFERENCE_REQUIRED")
        if any(action in _PAGE_DIRECTED_ACTIONS for action in action_codes) and not page_refs:
            return self._invalid("PAGE_REFERENCE_REQUIRED")
        if any(action not in _ALLOWED_ACTIONS[opportunity_type] for action in action_codes):
            return self._invalid("OPPORTUNITY_TYPE_MISMATCH")

        page_by_id = prompt.catalog.page_by_id()
        if any(
            page_by_id[reference].extraction_status is not PageExtractionStatus.SUCCESS
            for reference in page_refs
        ):
            return self._invalid("EVIDENCE_USE_NOT_ALLOWED")
        if opportunity_type in {
            ContentOpportunityType.EXPAND_OBSERVED_CONTENT,
            ContentOpportunityType.REORGANIZE_OBSERVED_CONTENT,
        }:
            if any(not page_by_id[reference].has_observed_present for reference in page_refs):
                return self._invalid("EVIDENCE_USE_NOT_ALLOWED")

        source_by_id = {source.source_id: source for source in prompt.sources}
        grounded_texts = tuple(
            value
            for reference in source_refs
            for value in (
                source_by_id[reference].title,
                source_by_id[reference].content,
            )
        )
        normalized_topic = self._grounding_normalize(topic)
        if not any(
            normalized_topic in self._grounding_normalize(value)
            for value in grounded_texts
        ):
            return self._invalid("TOPIC_NOT_GROUNDED")

        return (
            ContentOpportunitySpecification(
                opportunity_type=opportunity_type,
                priority=priority,
                topic=topic,
                action_codes=action_codes,
                page_refs=page_refs,
                source_refs=source_refs,
            ),
            None,
        )

    @staticmethod
    def _validated_topic(value: object) -> tuple[str | None, str | None]:
        if type(value) is not str or "\n" in value or "\r" in value:
            return None, "FIELD_CONTRACT"
        topic = " ".join(value.split())
        if not topic or len(topic) > MAX_TOPIC_CHARS:
            return None, "FIELD_CONTRACT"
        if re.search(
            r"(?:[a-z][a-z0-9+.-]*://|www\.|"
            r"\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,63}\b|"
            r"\b(?:[a-z0-9-]+\.)+[a-z]{2,63}(?:/[^\s]*)?|"
            r"\b[PSA][1-9][0-9]*\b|\[[PSA][^\]]*\])",
            topic,
            flags=re.IGNORECASE,
        ):
            return None, "FIELD_CONTRACT"
        folded = unicodedata.normalize("NFKC", topic).casefold()
        if any(term in folded for term in _ABSENCE_TERMS):
            return None, "UNSUPPORTED_ABSENCE_CLAIM"
        return topic, None

    @staticmethod
    def _validated_actions(value: object) -> tuple[ContentOpportunityActionCode, ...] | None:
        if type(value) is not list or not 1 <= len(value) <= MAX_ACTION_CODES:
            return None
        try:
            actions = tuple(ContentOpportunityActionCode(item) for item in value)
        except (TypeError, ValueError):
            return None
        if len(actions) != len(set(actions)):
            return None
        return actions

    @staticmethod
    def _validated_refs(
        value: object,
        prefix: str,
        known: set[str],
    ) -> tuple[tuple[str, ...] | None, str | None]:
        if type(value) is not list or any(type(item) is not str for item in value):
            return None, "FIELD_CONTRACT"
        refs = tuple(value)
        if len(refs) != len(set(refs)):
            return None, "UNKNOWN_OR_DUPLICATE_REFERENCE"
        for reference in refs:
            namespace = re.fullmatch(r"([PSA])[1-9][0-9]*", reference)
            if namespace is not None and namespace.group(1) != prefix:
                return None, "REFERENCE_NAMESPACE_NOT_ALLOWED"
            if re.fullmatch(fr"{prefix}[1-9][0-9]*", reference) is None or reference not in known:
                return None, "UNKNOWN_OR_DUPLICATE_REFERENCE"
        return refs, None

    @classmethod
    def _render(
        cls,
        number: int,
        specification: ContentOpportunitySpecification,
    ) -> ContentOpportunity:
        topic = specification.topic
        page_refs = ", ".join(specification.page_refs)
        source_refs = ", ".join(specification.source_refs)
        if specification.opportunity_type is ContentOpportunityType.EXPAND_OBSERVED_CONTENT:
            title = f"Expand observed {topic} content"
            rationale = (
                f"Observed page evidence {page_refs} contains content related to {topic}; "
                f"external research context {source_refs} is unverified and may be considered "
                "only after human review."
            )
        elif specification.opportunity_type is ContentOpportunityType.REORGANIZE_OBSERVED_CONTENT:
            title = f"Reorganize observed {topic} content"
            rationale = (
                f"Observed page evidence {page_refs} contains content related to {topic}; "
                f"external research context {source_refs} is unverified and may inform a "
                "human-reviewed reorganization."
            )
        else:
            title = f"Consider a supporting resource about {topic}"
            rationale = (
                f"External research context {source_refs} discusses {topic}; it is unverified "
                "and may inform consideration of a supporting resource after human review."
            )
            if page_refs:
                rationale += f" Observed page context {page_refs} may be reviewed for placement."
        actions = tuple(
            cls._render_action(code, topic, page_refs, source_refs)
            for code in specification.action_codes
        )
        return ContentOpportunity(
            recommendation_id=f"R{number}",
            opportunity_type=specification.opportunity_type,
            priority=specification.priority,
            topic=topic,
            title=title,
            rationale=rationale,
            actions=actions,
            page_refs=specification.page_refs,
            source_refs=specification.source_refs,
        )

    @staticmethod
    def _render_action(
        code: ContentOpportunityActionCode,
        topic: str,
        page_refs: str,
        source_refs: str,
    ) -> str:
        return {
            ContentOpportunityActionCode.EXPAND_PAGE_SECTION: f"Review {page_refs} and {source_refs}, then consider expanding the observed section about {topic}.",
            ContentOpportunityActionCode.REORGANIZE_PAGE_SECTIONS: f"Review {page_refs} and {source_refs}, then consider reorganizing the observed material about {topic}.",
            ContentOpportunityActionCode.CREATE_SUPPORTING_RESOURCE: f"Review {source_refs}, then consider a supporting resource about {topic}.",
            ContentOpportunityActionCode.ADD_BUYER_GUIDANCE: f"Review {source_refs}, then consider buyer guidance about {topic}.",
            ContentOpportunityActionCode.ADD_TECHNICAL_DOCUMENTATION: f"Review {source_refs}, then consider technical documentation about {topic}.",
            ContentOpportunityActionCode.ADD_COMPARISON_TABLE: f"Review {source_refs}, then consider a comparison table about {topic}.",
            ContentOpportunityActionCode.ADD_INTERNAL_LINK: f"After human review, consider linking {page_refs} to an approved resource about {topic}.",
        }[code]

    @staticmethod
    def _grounding_normalize(value: str) -> str:
        return " ".join(unicodedata.normalize("NFKC", value).casefold().split())

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(value.split())

    @staticmethod
    def _normalized_url(url: str) -> str | None:
        if type(url) is not str or not url or any(char.isspace() for char in url):
            return None
        try:
            parsed = urlsplit(url)
            port = parsed.port
        except ValueError:
            return None
        if (
            parsed.scheme.casefold() not in {"http", "https"}
            or parsed.hostname is None
            or parsed.username is not None
            or parsed.password is not None
        ):
            return None
        scheme = parsed.scheme.casefold()
        host = parsed.hostname.casefold()
        if port is not None and not (
            (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
        ):
            host = f"{host}:{port}"
        return urlunsplit((scheme, host, parsed.path or "/", parsed.query, ""))

    @staticmethod
    def _invalid(category: str) -> tuple[None, str]:
        assert category in INVALID_OUTPUT_CATEGORIES
        return None, f"{INVALID_OUTPUT_ERROR_PREFIX}{category}"

    @staticmethod
    def _failed(
        status: ContentOpportunityStatus,
        error: str,
    ) -> ContentOpportunityReport:
        return ContentOpportunityReport(
            status=status,
            opportunities=(),
            pages=(),
            sources=(),
            limitations=(),
            error=error,
        )
