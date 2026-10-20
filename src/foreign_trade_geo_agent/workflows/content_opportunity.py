"""Deterministic evidence validation and rendering for content opportunities."""

import asyncio
import json
from foreign_trade_geo_agent.core.first_party_planning import FirstPartyPlanningScope
from dataclasses import replace

from foreign_trade_geo_agent.core.content_opportunity import (
    CONTENT_OPPORTUNITY_LIMITATIONS,
    CONTENT_OPPORTUNITY_REPAIR_CATEGORIES,
    MAX_OPPORTUNITIES,
    MAX_ACTION_CODES,
    OPPORTUNITY_BASE_ACTION,
    OPPORTUNITY_ACTION_COMPATIBILITY,
    MAX_RAW_OUTPUT_BYTES,
    MAX_RAW_OUTPUT_CHARS,
    MAX_SITE_PACKET_BYTES,
    MAX_SITE_PACKET_CHARS,
    MAX_SITE_PAGES,
    MAX_SOURCE_PACKET_BYTES,
    MAX_SOURCE_PACKET_CHARS,
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
    ContentOpportunitySpecification,
    ContentOpportunityStatus,
    ContentOpportunityType,
    build_content_opportunity_evidence_catalog,
    finalize_content_opportunity,
    prepare_content_opportunity_sources,
    validate_content_opportunity_specification,
)
from foreign_trade_geo_agent.core.ports import ContentOpportunityWriter
from foreign_trade_geo_agent.core.history import PlanningValidationCategory
from foreign_trade_geo_agent.core.audit import AuditStatus, SiteAuditResult
from foreign_trade_geo_agent.core.research import ResearchReport
from foreign_trade_geo_agent.core.site_content import SiteContentPacket
from foreign_trade_geo_agent.workflows.audit_evidence import select_numbered_audit_evidence


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

class ContentOpportunityWorkflow:
    """Create a bounded opportunity draft without crawling or searching."""

    limitations = CONTENT_OPPORTUNITY_LIMITATIONS

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
        research_report: ResearchReport | None,
        audit_result: SiteAuditResult | None = None,
        *,
        first_party_scope: FirstPartyPlanningScope | None = None,
        task_id: str | None = None,
    ) -> ContentOpportunityReport:
        if not isinstance(site_content, SiteContentPacket):
            raise TypeError("Content opportunity workflow requires SiteContentPacket.")
        if first_party_scope is not None and (
            not isinstance(first_party_scope, FirstPartyPlanningScope)
            or not first_party_scope.matches_packet(site_content)
            or not first_party_scope.matches_task(task_id)
            or research_report is not None or audit_result is not None
        ):
            return self._failed(ContentOpportunityStatus.INSUFFICIENT_RESEARCH_EVIDENCE,
                                "First-party planning scope does not match the input.")
        if first_party_scope is None and not isinstance(research_report, ResearchReport):
            raise TypeError("Content opportunity workflow requires ResearchReport.")
        if audit_result is not None and (
            not isinstance(audit_result, SiteAuditResult)
            or audit_result.status is not AuditStatus.SUCCESS
        ):
            raise TypeError("Content opportunity workflow requires a successful SiteAuditResult.")
        try:
            return await asyncio.wait_for(
                self._run(site_content, research_report, audit_result, first_party_scope, task_id),
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
        research_report: ResearchReport | None,
        audit_result: SiteAuditResult | None,
        first_party_scope: FirstPartyPlanningScope | None,
        task_id: str | None,
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

        prepared = None if first_party_scope is not None else prepare_content_opportunity_sources(research_report)
        if prepared is None and first_party_scope is None:
            return self._failed(
                ContentOpportunityStatus.INSUFFICIENT_RESEARCH_EVIDENCE,
                "Insufficient cross-validated research evidence.",
            )
        sources = () if prepared is None else prepared.materials
        report_sources = () if prepared is None else prepared.sources
        selection_truncated = False if prepared is None else prepared.selection_truncated
        audits = () if audit_result is None else select_numbered_audit_evidence(audit_result.evidence)
        catalog = build_content_opportunity_evidence_catalog(site_content, sources, audits)
        prompt = ContentOpportunityPrompt(
            site_content=site_content,
            catalog=catalog,
            sources=sources,
            research_sources_truncated=selection_truncated,
            first_party_scope=first_party_scope,
            task_id=task_id,
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

        writer_attempt_count = 1
        try:
            generation = await asyncio.wait_for(
                self._writer.write_content_opportunities(prompt),
                timeout=self._generation_timeout,
            )
        except (TimeoutError, asyncio.TimeoutError):
            return self._failed(
                ContentOpportunityStatus.WORKFLOW_TIMEOUT,
                "Content opportunity workflow timed out.",
                writer_attempt_count=writer_attempt_count,
            )
        except Exception:
            return self._failed(
                ContentOpportunityStatus.GENERATION_FAILED,
                "Content opportunity writer raised an exception.",
                writer_attempt_count=writer_attempt_count,
            )
        if not isinstance(generation, ContentOpportunityGeneration):
            return self._failed(
                ContentOpportunityStatus.GENERATION_FAILED,
                "Content opportunity writer returned an invalid result.",
                writer_attempt_count=writer_attempt_count,
            )
        if generation.status is ContentOpportunityGenerationStatus.FAILED:
            return self._failed(
                ContentOpportunityStatus.GENERATION_FAILED,
                "Content opportunity generation failed.",
                writer_attempt_count=writer_attempt_count,
            )

        opportunities, error = self._validate_and_render(generation.text, prompt)
        repair_category = (
            None
            if error is None
            else PlanningValidationCategory(
                error.removeprefix(INVALID_OUTPUT_ERROR_PREFIX)
            )
        )
        if repair_category in CONTENT_OPPORTUNITY_REPAIR_CATEGORIES:
            retry_prompt = replace(prompt, repair_category=repair_category)
            retry_material = retry_prompt.material_json()
            if (
                len(retry_material) > MAX_USER_MATERIAL_CHARS
                or len(retry_material.encode("utf-8")) > MAX_USER_MATERIAL_BYTES
            ):
                return self._failed(
                    ContentOpportunityStatus.INPUT_TOO_LARGE,
                    "Content opportunity input exceeds the fixed budget.",
                    writer_attempt_count=writer_attempt_count,
                )
            writer_attempt_count = 2
            try:
                generation = await asyncio.wait_for(
                    self._writer.write_content_opportunities(retry_prompt),
                    timeout=self._generation_timeout,
                )
            except (TimeoutError, asyncio.TimeoutError):
                return self._failed(
                    ContentOpportunityStatus.WORKFLOW_TIMEOUT,
                    "Content opportunity workflow timed out.",
                    writer_attempt_count=writer_attempt_count,
                )
            except Exception:
                return self._failed(
                    ContentOpportunityStatus.GENERATION_FAILED,
                    "Content opportunity writer raised an exception.",
                    writer_attempt_count=writer_attempt_count,
                )
            if not isinstance(generation, ContentOpportunityGeneration):
                return self._failed(
                    ContentOpportunityStatus.GENERATION_FAILED,
                    "Content opportunity writer returned an invalid result.",
                    writer_attempt_count=writer_attempt_count,
                )
            if generation.status is ContentOpportunityGenerationStatus.FAILED:
                return self._failed(
                    ContentOpportunityStatus.GENERATION_FAILED,
                    "Content opportunity generation failed.",
                    writer_attempt_count=writer_attempt_count,
                )
            opportunities, error = self._validate_and_render(
                generation.text,
                retry_prompt,
            )
        if opportunities is None:
            assert error is not None
            return self._failed(
                ContentOpportunityStatus.INVALID_OUTPUT,
                error,
                final_validation_category=PlanningValidationCategory(
                    error.removeprefix(INVALID_OUTPUT_ERROR_PREFIX)
                ),
                writer_attempt_count=writer_attempt_count,
            )

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
            source_materials=sources,
            research_sources_truncated=selection_truncated,
            audit_evidence=audits,
        )

    @classmethod
    def count_eligible_sources(cls, report: ResearchReport) -> int:
        """Return the bounded source count produced by the real selection rules."""

        prepared = prepare_content_opportunity_sources(report)
        return 0 if prepared is None else len(prepared.materials)

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
        if prompt.first_party_scope is not None and len(raw_items) != 1:
            return self._invalid("FIELD_CONTRACT")

        rendered: list[ContentOpportunity] = []
        for number, raw in enumerate(raw_items, start=1):
            specification, error = self._validate_specification(raw, prompt)
            if specification is None:
                return None, error
            rendered.append(finalize_content_opportunity(number, specification))
        return tuple(rendered), None

    def _validate_specification(
        self,
        raw: object,
        prompt: ContentOpportunityPrompt,
    ) -> tuple[ContentOpportunitySpecification | None, str | None]:
        expected = {
            "opportunity_type",
            "priority",
            "topic_ref",
            "enhancement_action_codes",
            "page_refs",
            "source_refs",
            "audit_refs",
        }
        if type(raw) is not dict or set(raw) != expected:
            return self._invalid("FIELD_CONTRACT")
        try:
            opportunity_type = ContentOpportunityType(raw["opportunity_type"])
            priority = ContentOpportunityPriority(raw["priority"])
        except (TypeError, ValueError):
            return self._invalid("FIELD_CONTRACT")

        topic_ref = raw["topic_ref"]
        if type(topic_ref) is not str:
            return self._invalid("FIELD_CONTRACT")
        topic_candidate = prompt.topic_candidate(topic_ref)
        if topic_candidate is None:
            return self._invalid("FIELD_CONTRACT")
        if type(raw["enhancement_action_codes"]) is not list:
            return self._invalid("ACTION_NOT_ALLOWED")
        try:
            action_codes = tuple(
                ContentOpportunityActionCode(item)
                for item in raw["enhancement_action_codes"]
            )
        except (TypeError, ValueError):
            return self._invalid("ACTION_NOT_ALLOWED")
        if (
            len(action_codes) > MAX_ACTION_CODES - 1
            or len(action_codes) != len(set(action_codes))
            or any(code in OPPORTUNITY_BASE_ACTION.values() for code in action_codes)
        ):
            return self._invalid("ACTION_NOT_ALLOWED")
        if any(
            code not in OPPORTUNITY_ACTION_COMPATIBILITY[opportunity_type]
            for code in action_codes
        ):
            return self._invalid("OPPORTUNITY_TYPE_MISMATCH")
        action_codes = (OPPORTUNITY_BASE_ACTION[opportunity_type], *action_codes)
        if (
            type(raw["page_refs"]) is not list
            or type(raw["source_refs"]) is not list
            or type(raw["audit_refs"]) is not list
            or any(type(item) is not str for item in raw["page_refs"])
            or any(type(item) is not str for item in raw["source_refs"])
            or any(type(item) is not str for item in raw["audit_refs"])
        ):
            return self._invalid("FIELD_CONTRACT")
        cited_refs = raw["page_refs"] if topic_candidate.origin_ref.startswith("P") else raw["source_refs"]
        if topic_candidate.origin_ref not in cited_refs:
            return self._invalid("EVIDENCE_USE_NOT_ALLOWED")
        specification = ContentOpportunitySpecification(
            opportunity_type=opportunity_type,
            priority=priority,
            topic=topic_candidate.text,
            action_codes=action_codes,
            page_refs=tuple(raw["page_refs"]),
            source_refs=tuple(raw["source_refs"]),
            audit_refs=tuple(raw["audit_refs"]),
        )
        validation_error = validate_content_opportunity_specification(
            specification,
            prompt.catalog,
            prompt.sources,
            first_party_scope=prompt.first_party_scope,
            task_id=prompt.task_id,
        )
        if validation_error is not None:
            return self._invalid(validation_error)
        return specification, None

    @staticmethod
    def _invalid(category: str) -> tuple[None, str]:
        assert category in INVALID_OUTPUT_CATEGORIES
        return None, f"{INVALID_OUTPUT_ERROR_PREFIX}{category}"

    @staticmethod
    def _failed(
        status: ContentOpportunityStatus,
        error: str,
        *,
        final_validation_category: PlanningValidationCategory | None = None,
        writer_attempt_count: int | None = None,
    ) -> ContentOpportunityReport:
        return ContentOpportunityReport(
            status=status,
            opportunities=(),
            pages=(),
            sources=(),
            limitations=(),
            error=error,
            final_validation_category=final_validation_category,
            writer_attempt_count=writer_attempt_count,
        )
