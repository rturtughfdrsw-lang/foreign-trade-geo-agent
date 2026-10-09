from __future__ import annotations

from pathlib import Path

from foreign_trade_geo_agent.core.fetching import FetchStatus, HtmlFetchResult
from foreign_trade_geo_agent.web.composition import build_live_composition
from tests.test_mvp_composed_flow import (
    _FixtureChangePlanWriter,
    _FixtureContentDraftWriter,
    _FixtureOpportunityWriter,
    _FixtureResearchWriter,
    _FixtureSearchProvider,
)


ALPHA_URL = "https://alpha.example/"
BETA_URL = "https://beta.example/"


def _success(url: str, content: bytes, content_type: str) -> HtmlFetchResult:
    return HtmlFetchResult(
        requested_url=url,
        final_url=url,
        status=FetchStatus.SUCCESS,
        http_status=200,
        content_type=content_type,
        content=content,
        connected_ip="93.184.216.34",
        wire_bytes=len(content),
        decoded_bytes=len(content),
        request_attempts=1,
        redirect_chain=(url,),
        failure_kind=None,
        error=None,
    )


class GenericDomainFetcher:
    def __init__(self, site_url: str, identity: str) -> None:
        self.site_url = site_url
        self.identity = identity

    async def fetch_text(self, url: str, **_kwargs: object) -> HtmlFetchResult:
        return _success(
            url,
            b"User-agent: ForeignTradeGeoAgent\nAllow: /\n",
            "text/plain",
        )

    async def fetch(self, url: str, **_kwargs: object) -> HtmlFetchResult:
        if url != self.site_url:
            raise AssertionError(f"Unexpected URL: {url}")
        html = f"""<!doctype html>
<html lang="en"><head><title>{self.identity} Industrial Pumps</title>
<meta name="description" content="{self.identity} industrial pump selection and material compatibility guidance for buyers.">
<link rel="canonical" href="{self.site_url}"></head>
<body><main><h1>{self.identity} Industrial Pumps</h1><h2>Material selection</h2>
<p>{self.identity} supplies industrial pumps. Buyers compare chemical compatibility,
materials, pressure, flow, maintenance, and operating conditions for each application.</p>
<a href="/">Product overview</a></main></body></html>""".encode()
        return _success(url, html, "text/html; charset=utf-8")


def live_composition(db_path: Path, site_url: str, identity: str):
    return build_live_composition(
        db_path,
        provider_configuration_ready=True,
        fetcher=GenericDomainFetcher(site_url, identity),
        search_provider=_FixtureSearchProvider(),
        research_writer=_FixtureResearchWriter(),
        content_opportunity_writer=_FixtureOpportunityWriter(),
        change_plan_writer=_FixtureChangePlanWriter(),
        content_draft_writer=_FixtureContentDraftWriter(),
    )
