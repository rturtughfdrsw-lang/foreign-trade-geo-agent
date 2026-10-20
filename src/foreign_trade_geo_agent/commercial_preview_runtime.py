"""Commercial Preview composition; live boundaries require explicit configuration."""
import argparse
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
import re
from uuid import uuid4

import httpx

from foreign_trade_geo_agent.adapters.commercial_preview import FakePreviewWriter
from foreign_trade_geo_agent.adapters.page_extractor import TrafilaturaPageExtractor
from foreign_trade_geo_agent.adapters.safe_http import SafeHtmlFetcher
from foreign_trade_geo_agent.adapters.preview_site import PreviewSiteConfig, ScopedPreviewFetcher
from foreign_trade_geo_agent.core.commercial_preview import digest, require
from foreign_trade_geo_agent.core.extraction import PageExtractionStatus
from foreign_trade_geo_agent.core.history import ArtifactRecord, ArtifactType, RunStatus, WorkflowRun, site_key_from_url
from foreign_trade_geo_agent.storage.commercial_preview import SQLitePreviewStore
from foreign_trade_geo_agent.storage.serialization import encode_artifact
from foreign_trade_geo_agent.storage.sqlite import SQLiteHistoryStore
from foreign_trade_geo_agent.workflows.commercial_preview import CommercialPreviewWorkflow
from foreign_trade_geo_agent.workflows.crawl_seo_audit import CrawlSeoAuditor
from foreign_trade_geo_agent.workflows.site_content_packet import SiteContentPacketBuilder
from foreign_trade_geo_agent.workflows.site_crawl import SiteCrawlWorkflow

ORIGIN = 'https://preview-b2b.example'
FIXTURES = Path(__file__).parent / 'web/fixtures/commercial_preview'


class _OfflineResolver:
    async def resolve(self, host, port):
        require(host == 'preview-b2b.example' and port == 443, 'PREVIEW_FIXTURE_ONLY')
        return ('93.184.216.34',)


class OfflinePreviewAnalyzer:
    def __init__(self, history):
        self.history = history

    async def analyze(self, website, run_id):
        require(website in {ORIGIN + '/', ORIGIN + '/empty.html'}, 'PREVIEW_FIXTURE_ONLY')

        def response(request):
            require(str(request.url).startswith(ORIGIN + '/'), 'PREVIEW_FIXTURE_ONLY')
            names = {'/': 'index.html', '/empty.html': 'empty.html', '/robots.txt': 'robots.txt'}
            name = names.get(request.url.path)
            if not name:
                return httpx.Response(404)
            return httpx.Response(200, content=(FIXTURES / name).read_bytes(),
                                  headers={'Content-Type': 'text/plain' if name == 'robots.txt' else 'text/html; charset=utf-8'})

        fetcher = SafeHtmlFetcher(resolver=_OfflineResolver(),
                                  _transport_factory=lambda *_: httpx.MockTransport(response))
        return await self.analyze_with(fetcher, website, run_id, 'SYNTHETIC')

    async def analyze_with(self, fetcher, website, run_id, data_kind, authorized_urls=()):
        crawl = await SiteCrawlWorkflow(fetcher, TrafilaturaPageExtractor(), max_pages=5,
                                        max_depth=1, max_concurrency=1, max_request_attempts=12,
                                        max_total_wire_bytes=5*1024*1024, max_total_decoded_bytes=10*1024*1024,
                                        max_runtime=45).run(website)
        packet = SiteContentPacketBuilder().build(crawl)
        audit = CrawlSeoAuditor().audit_crawl(crawl)
        now = datetime.now(UTC)
        self.history.create_run(WorkflowRun(run_id, site_key_from_url(website), 'COMMERCIAL_PREVIEW_ANALYSIS',
                                            now, None, RunStatus.RUNNING, None, None))
        for kind, payload in ((ArtifactType.SITE_CONTENT, packet), (ArtifactType.SITE_AUDIT, audit)):
            self.history.append_artifact(ArtifactRecord(str(uuid4()), run_id, kind, 1, now, payload))
        self.history.finish_run(run_id, status=RunStatus.SUCCEEDED, completed_at=datetime.now(UTC))
        # Adapt VDemo's deterministic observed-heading/body rule without its Admission.
        topic = None
        for page in packet.pages:
            if page.extraction_status is not PageExtractionStatus.SUCCESS or not page.body_text or len(page.body_text) < 80:
                continue
            for heading in page.h1:
                if heading.casefold() in {'home', 'products', 'about us', 'welcome', 'index'}:
                    continue
                if not re.fullmatch(r"[A-Za-z][A-Za-z0-9 &'()-]{7,100}", heading):
                    continue
                tokens = set(re.findall('[a-z]+', heading.casefold())) - {'the', 'of', 'and', 'for'}
                if len(tokens & set(re.findall('[a-z]+', page.body_text.casefold()))) >= 2:
                    topic = dict(title=heading + ': A Factual Overview', subject=heading,
                                 page_id=page.evidence_id, page_url=page.final_url,
                                 source_digest=digest(asdict(page)))
                    break
            if topic:
                break
        return dict(website=website, data_kind=data_kind, research='NOT_RUN', serp='NOT_RUN',
                    authorized_urls=list(authorized_urls), crawl=asdict(crawl),
                    topic=topic, no_topic_reason='' if topic else '无合适的系统选题：缺少明确产品/能力主题和足够正文。',
                    content=asdict(packet), audit=encode_artifact(ArtifactType.SITE_AUDIT, audit, payload_version=1))


class PreviewAnalyzerRouter:
    def __init__(self, history, site_config, fetcher_factory):
        self.offline = OfflinePreviewAnalyzer(history)
        self.config = site_config
        self.fetcher_factory = fetcher_factory

    def preparation(self):
        return dict(status=self.config.status, allowed_urls=list(self.config.allowed_urls),
                    scope='EXACT_URL_ALLOWLIST', max_pages=5, max_depth=1, max_request_attempts=12,
                    max_runtime_seconds=45, robots='REQUIRED', audit='SAMPLE_ONLY')

    async def analyze(self, website, run_id, *, mode='SYNTHETIC', allowed_urls=(), site_authorized=False):
        require(mode in {'SYNTHETIC', 'REAL_SITE'}, 'PREVIEW_SITE_MODE_INVALID')
        if mode == 'SYNTHETIC':
            return await self.offline.analyze(website, run_id)
        seed, urls, robots = self.config.authorize(website, allowed_urls, site_authorized)
        fetcher = ScopedPreviewFetcher(self.fetcher_factory(), urls, robots)
        return await self.offline.analyze_with(fetcher, seed, run_id, 'REAL', urls)


def build_preview_runtime(data_dir: Path, *, site_config=None, writer=None, fetcher_factory=SafeHtmlFetcher):
    data_dir = Path(data_dir)
    return CommercialPreviewWorkflow(SQLitePreviewStore(data_dir / 'preview.sqlite3'),
        writer if writer is not None else FakePreviewWriter(),
        PreviewAnalyzerRouter(SQLiteHistoryStore(data_dir / 'history.sqlite3'),
                              site_config or PreviewSiteConfig(), fetcher_factory))


def main():
    parser = argparse.ArgumentParser(description='Commercial Preview V1.1 (live disabled by default)')
    parser.add_argument('--port', type=int, default=8017)
    parser.add_argument('--data-dir', type=Path, default=Path('.data/commercial-preview-v1.1-local'))
    parser.add_argument('--enable-real-site', action='store_true')
    parser.add_argument('--allow-url', action='append', default=[])
    parser.add_argument('--writer', choices=['fake', 'deepseek'], default='fake')
    parser.add_argument('--enable-deepseek-preview', action='store_true')
    parser.add_argument('--model')
    parser.add_argument('--model-timeout', type=float)
    parser.add_argument('--max-output-tokens', type=int)
    parser.add_argument('--max-input-tokens', type=int)
    parser.add_argument('--budget-usd', type=float)
    parser.add_argument('--input-price-cap', type=float)
    parser.add_argument('--output-price-cap', type=float)
    args = parser.parse_args()
    require(1024 <= args.port <= 65535 and args.port not in {8002, 8003}, 'PREVIEW_PORT_FORBIDDEN')
    writer = None
    if args.writer == 'deepseek':
        from dotenv import load_dotenv
        from foreign_trade_geo_agent.adapters.deepseek_preview import DeepSeekPreviewConfig, DeepSeekPreviewWriter
        load_dotenv()
        writer = DeepSeekPreviewWriter(DeepSeekPreviewConfig(args.enable_deepseek_preview, args.model,
            args.model_timeout, args.max_output_tokens, args.max_input_tokens, args.budget_usd,
            args.input_price_cap, args.output_price_cap))
    import uvicorn
    from foreign_trade_geo_agent.web.commercial_preview import create_preview_app
    workflow = build_preview_runtime(args.data_dir, site_config=PreviewSiteConfig(args.enable_real_site, tuple(args.allow_url)),
                                     writer=writer)
    uvicorn.run(create_preview_app(workflow), host='127.0.0.1', port=args.port)


if __name__ == '__main__':
    main()
