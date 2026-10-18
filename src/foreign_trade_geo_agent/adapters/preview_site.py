"""An explicit URL allowlist around the existing safe crawl boundary."""
from dataclasses import dataclass
import ipaddress
from urllib.parse import urlsplit

import httpx

from foreign_trade_geo_agent.adapters.safe_http import ip_address_is_permitted
from foreign_trade_geo_agent.core.commercial_preview import require
from foreign_trade_geo_agent.core.fetching import FetchFailureKind, FetchStatus, HtmlFetchResult


def preview_url(value):
    require(type(value) is str and 1 <= len(value) <= 2048, 'PREVIEW_SITE_URL_INVALID')
    require(not any(c.isspace() for c in value) and '\\' not in value, 'PREVIEW_SITE_URL_INVALID')
    try:
        split = urlsplit(value)
        url = httpx.URL(value)
        require(url.scheme == 'https' and bool(url.host) and url.port in {None, 443}
                and split.username is None and split.password is None and not split.query
                and not split.fragment, 'PREVIEW_SITE_HTTPS_REQUIRED')
        try:
            address = ipaddress.ip_address(url.host)
        except ValueError:
            address = None
        require(address is None or ip_address_is_permitted(address), 'PREVIEW_SITE_ADDRESS_FORBIDDEN')
        require(url.host not in {'localhost', 'localhost.localdomain'} and not url.host.endswith('.localhost'),
                'PREVIEW_SITE_ADDRESS_FORBIDDEN')
        # Avoid path alias ambiguity in the operator's exact URL grant.
        require('%' not in split.path and not any(p in {'.', '..'} for p in split.path.split('/')),
                'PREVIEW_SITE_URL_INVALID')
        return str(url)
    except (httpx.InvalidURL, UnicodeError):
        raise ValueError('PREVIEW_SITE_URL_INVALID') from None


@dataclass(frozen=True)
class PreviewSiteConfig:
    enabled: bool = False
    allowed_urls: tuple[str, ...] = ()

    def __post_init__(self):
        require(type(self.enabled) is bool and type(self.allowed_urls) is tuple
                and len(self.allowed_urls) <= 10, 'PREVIEW_SITE_CONFIG_INVALID')
        normalized = tuple(preview_url(url) for url in self.allowed_urls)
        require(len(set(normalized)) == len(normalized), 'PREVIEW_SITE_CONFIG_INVALID')
        object.__setattr__(self, 'allowed_urls', normalized)

    @property
    def status(self):
        return 'NOT_ENABLED' if not self.enabled else ('READY' if self.allowed_urls else 'NOT_AUTHORIZED')

    def authorize(self, website, requested_urls, acknowledged):
        require(self.enabled, 'PREVIEW_REAL_SITE_NOT_ENABLED')
        require(acknowledged is True and self.allowed_urls, 'PREVIEW_REAL_SITE_NOT_AUTHORIZED')
        seed = preview_url(website)
        require(type(requested_urls) in {list, tuple} and 1 <= len(requested_urls) <= 10,
                'PREVIEW_SITE_SCOPE_REQUIRED')
        urls = tuple(preview_url(url) for url in requested_urls)
        require(seed in urls and len(set(urls)) == len(urls)
                and set(urls) <= set(self.allowed_urls), 'PREVIEW_SITE_SCOPE_NOT_AUTHORIZED')
        origin = httpx.URL(seed).copy_with(path='/', query=None, fragment=None)
        require(all(httpx.URL(url).copy_with(path='/', query=None, fragment=None) == origin for url in urls),
                'PREVIEW_SITE_SAME_ORIGIN_REQUIRED')
        return seed, urls, str(origin.copy_with(path='/robots.txt'))


class ScopedPreviewFetcher:
    """Filter seeds, discovered URLs AND redirects, including robots redirects."""
    def __init__(self, fetcher, urls, robots_url):
        self.fetcher, self.urls, self.robots_url = fetcher, frozenset(urls), robots_url

    async def _fetch(self, method, url, allowed, options):
        if url not in allowed:
            return HtmlFetchResult(url, url, FetchStatus.FAILED, None, None, None, None,
                                   0, 0, 0, (), FetchFailureKind.ORIGIN_REJECTED,
                                   'Preview URL is outside the explicitly authorized scope.')
        previous = options.pop('redirect_policy', None)
        options['redirect_policy'] = lambda target: target in allowed and (previous is None or previous(target))
        return await method(url, **options)

    async def fetch(self, url, **options):
        return await self._fetch(self.fetcher.fetch, url, self.urls, options)

    async def fetch_text(self, url, **options):
        return await self._fetch(self.fetcher.fetch_text, url, {self.robots_url}, options)
