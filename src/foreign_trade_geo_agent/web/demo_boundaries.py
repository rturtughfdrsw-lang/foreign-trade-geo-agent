"""Deterministic external boundaries for the self-contained NovaCNC Demo."""

from __future__ import annotations

import json
from pathlib import Path

from foreign_trade_geo_agent.core.audit import (
    AuditEvidence,
    AuditEvidenceCategory,
    AuditEvidenceOutcome,
    AuditStatus,
    SiteAuditResult,
)
from foreign_trade_geo_agent.core.change_plan import (
    ChangePlanGeneration,
    ChangePlanGenerationStatus,
    ChangePlanPrompt,
)
from foreign_trade_geo_agent.core.content_draft import (
    ContentDraftGeneration,
    ContentDraftGenerationStatus,
    ContentDraftPrompt,
)
from foreign_trade_geo_agent.core.content_opportunity import (
    ContentOpportunityGeneration,
    ContentOpportunityGenerationStatus,
    ContentOpportunityPrompt,
)
from foreign_trade_geo_agent.core.fetching import FetchStatus, HtmlFetchResult
from foreign_trade_geo_agent.core.research import (
    ResearchGeneration,
    ResearchGenerationStatus,
    ResearchMaterial,
)
from foreign_trade_geo_agent.core.search import SearchResponse, SearchResult, SearchStatus


DEMO_COMPANY_NAME = "NovaCNC Machinery"
DEMO_SITE_URL = "https://novacnc.example/"
DEMO_RESEARCH_QUESTION = "Improve product-page SEO and content coverage"
DEMO_TARGET_LANGUAGE = "en"

_FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "novacnc"
_CONNECTED_IP = "192.0.2.10"


class DemoBoundaryError(RuntimeError):
    """An unexpected target attempted to cross a deterministic Demo boundary."""


def _success(url: str, content: bytes, content_type: str) -> HtmlFetchResult:
    return HtmlFetchResult(
        requested_url=url,
        final_url=url,
        status=FetchStatus.SUCCESS,
        http_status=200,
        content_type=content_type,
        content=content,
        connected_ip=_CONNECTED_IP,
        wire_bytes=len(content),
        decoded_bytes=len(content),
        request_attempts=1,
        redirect_chain=(url,),
        failure_kind=None,
        error=None,
    )


class DemoCrawlFetcher:
    """Serve an exact allowlist of local fixture bytes without resolving a host."""

    _PAGES = {
        DEMO_SITE_URL: ("index.html", "text/html; charset=utf-8"),
        f"{DEMO_SITE_URL}machines.html": (
            "machines.html",
            "text/html; charset=utf-8",
        ),
    }
    _ROBOTS_URL = f"{DEMO_SITE_URL}robots.txt"

    async def fetch_text(self, url: str, **_kwargs: object) -> HtmlFetchResult:
        if url != self._ROBOTS_URL:
            raise DemoBoundaryError("Demo robots request is outside the fixture allowlist.")
        content = (_FIXTURE_ROOT / "robots.txt").read_bytes()
        return _success(url, content, "text/plain; charset=utf-8")

    async def fetch(self, url: str, **_kwargs: object) -> HtmlFetchResult:
        fixture = self._PAGES.get(url)
        if fixture is None:
            raise DemoBoundaryError("Demo page request is outside the fixture allowlist.")
        filename, content_type = fixture
        return _success(url, (_FIXTURE_ROOT / filename).read_bytes(), content_type)


class DemoSiteAuditor:
    def audit_site(self, url: str) -> SiteAuditResult:
        if url != DEMO_SITE_URL:
            raise DemoBoundaryError("Demo audit target is outside the fixed snapshot.")
        return SiteAuditResult(
            url=url,
            status=AuditStatus.SUCCESS,
            score=78,
            band="needs improvement",
            score_breakdown={"meta": 18, "content": 36, "schema": 24},
            recommendations=(
                "Expand product-page selection guidance for industrial buyers.",
                "Clarify application fit and controller compatibility.",
            ),
            error=None,
            source="deterministic-demo-auditor",
            source_version="novacnc-v1",
            evidence=(
                AuditEvidence(
                    category=AuditEvidenceCategory.CONTENT,
                    check_key="content.selection_guidance.present",
                    observed_value=False,
                    outcome=AuditEvidenceOutcome.ABSENT,
                    provider_field="demo.selection_guidance",
                ),
                AuditEvidence(
                    category=AuditEvidenceCategory.SCHEMA,
                    check_key="schema.product.detected",
                    observed_value=None,
                    outcome=AuditEvidenceOutcome.NOT_DETECTED,
                    provider_field="demo.product_schema",
                    note="The deterministic audit did not detect product schema.",
                ),
            ),
        )


class DemoSearchProvider:
    async def search(self, query: str) -> SearchResponse:
        return SearchResponse(
            query=query,
            status=SearchStatus.SUCCESS,
            results=(
                SearchResult(
                    title="CNC machining center selection guide",
                    url="https://research.example/cnc-selection-guide",
                    content=(
                        "Industrial buyers compare travel, spindle capability, "
                        "controller compatibility, tooling, tolerances, and service "
                        "support when selecting a CNC machining center."
                    ),
                    score=0.98,
                ),
            ),
            error=None,
        )


class DemoResearchWriter:
    async def write_report(
        self,
        question: str,
        materials: tuple[ResearchMaterial, ...],
    ) -> ResearchGeneration:
        if question != DEMO_RESEARCH_QUESTION or len(materials) != 1:
            raise DemoBoundaryError("Demo research input is outside the fixed preset.")
        return ResearchGeneration(
            provider="deterministic-demo-writer",
            model="fixed-v1",
            status=ResearchGenerationStatus.SUCCESS,
            text=(
                "CNC machining center buyers compare travel, spindle capability, "
                "controller compatibility, tooling, tolerances, and service support "
                "before shortlisting equipment [S1]."
            ),
            error=None,
        )


class DemoContentOpportunityWriter:
    async def write_content_opportunities(
        self,
        _prompt: ContentOpportunityPrompt,
    ) -> ContentOpportunityGeneration:
        return ContentOpportunityGeneration(
            provider="deterministic-demo-writer",
            model="fixed-v1",
            status=ContentOpportunityGenerationStatus.SUCCESS,
            text=json.dumps(
                {
                    "opportunities": [
                        {
                            "opportunity_type": "EXPAND_OBSERVED_CONTENT",
                            "priority": "HIGH",
                            "topic": "CNC machining center",
                            "action_codes": ["EXPAND_PAGE_SECTION"],
                            "page_refs": ["P1"],
                            "source_refs": ["S1"],
                            "audit_refs": ["A1"],
                        }
                    ]
                }
            ),
            error=None,
        )


class DemoChangePlanWriter:
    async def write_change_plan(
        self,
        _prompt: ChangePlanPrompt,
    ) -> ChangePlanGeneration:
        return ChangePlanGeneration(
            provider="deterministic-demo-writer",
            model="fixed-v1",
            status=ChangePlanGenerationStatus.SUCCESS,
            text=json.dumps(
                {
                    "operations": [
                        {
                            "opportunity_ref": "R1",
                            "source_action_code": "EXPAND_PAGE_SECTION",
                            "operation_type": "EXPAND_SECTION",
                            "page_refs": ["P1"],
                            "source_refs": ["S1"],
                            "target_page_ref": "P1",
                            "locator_kind": "PAGE_LEVEL",
                            "target_heading": None,
                            "content_points": [
                                {
                                    "intent": "EXPLAIN",
                                    "subject": "CNC machining center",
                                }
                            ],
                        }
                    ]
                }
            ),
            error=None,
        )


class DemoContentDraftWriter:
    async def write_content_draft(
        self,
        _prompt: ContentDraftPrompt,
    ) -> ContentDraftGeneration:
        return ContentDraftGeneration(
            provider="deterministic-demo-writer",
            model="fixed-v1",
            status=ContentDraftGenerationStatus.SUCCESS,
            text=json.dumps(
                {
                    "draft": {
                        "change_ref": "C1",
                        "draft_type": "SECTION_DRAFT",
                        "blocks": [
                            {
                                "kind": "PARAGRAPH",
                                "claims": [
                                    {
                                        "text": "NovaCNC supplies CNC machining centers for industrial production teams.",
                                        "claim_type": "OBSERVED_PRODUCT_FACT",
                                        "page_refs": ["P1"],
                                        "source_refs": [],
                                    },
                                    {
                                        "text": "Buyers commonly compare travel, spindle capability, controller compatibility, tooling, tolerances, and service support.",
                                        "claim_type": "GENERAL_TECHNICAL_CONTEXT",
                                        "page_refs": [],
                                        "source_refs": ["S1"],
                                    },
                                ],
                            },
                            {
                                "kind": "BULLET_LIST",
                                "items": [
                                    {
                                        "text": "Compare travel and spindle capability.",
                                        "claim_type": "GENERAL_TECHNICAL_CONTEXT",
                                        "page_refs": [],
                                        "source_refs": ["S1"],
                                    },
                                    {
                                        "text": "Check controller compatibility and tooling.",
                                        "claim_type": "GENERAL_TECHNICAL_CONTEXT",
                                        "page_refs": [],
                                        "source_refs": ["S1"],
                                    },
                                    {
                                        "text": "Confirm tolerances and service support.",
                                        "claim_type": "GENERAL_TECHNICAL_CONTEXT",
                                        "page_refs": [],
                                        "source_refs": ["S1"],
                                    },
                                ],
                            },
                        ],
                    }
                }
            ),
            error=None,
        )
