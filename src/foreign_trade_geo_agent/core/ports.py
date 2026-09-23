"""Ports implemented by external service providers."""

from typing import Protocol

from .audit import SiteAuditResult
from .fetching import HtmlFetchResult, UrlOrigin
from .optimization import OptimizationGeneration, OptimizationPrompt
from .research import ResearchGeneration, ResearchMaterial
from .search import SearchResponse
from .visibility import ProviderResponse


class SiteAuditor(Protocol):
    """Provider-independent site-audit boundary used by workflows."""

    def audit_site(self, url: str) -> SiteAuditResult:
        """Audit one public website URL."""
        ...


class HostResolver(Protocol):
    """Resolve one logical host without granting network access."""

    async def resolve(self, host: str, port: int) -> tuple[str, ...]:
        """Return every address currently reported for the host."""
        ...


class HtmlFetcher(Protocol):
    """Fetch one HTML URL through the security-enforcing network boundary."""

    async def fetch(
        self,
        url: str,
        *,
        expected_origin: UrlOrigin | None = None,
    ) -> HtmlFetchResult:
        """Return HTML or a bounded, classified failure."""
        ...


class VisibilityProvider(Protocol):
    """Provider-independent boundary for one AI answer."""

    async def generate(self, prompt: str) -> ProviderResponse:
        """Generate one answer or return an explicit failed response."""
        ...


class SearchProvider(Protocol):
    """Provider-independent boundary for one web search."""

    async def search(self, query: str) -> SearchResponse:
        """Search the web or return an explicit failed response."""
        ...


class ResearchWriter(Protocol):
    """Provider-independent boundary for one sourced research draft."""

    async def write_report(
        self,
        question: str,
        materials: tuple[ResearchMaterial, ...],
    ) -> ResearchGeneration:
        """Generate a draft from bounded, untrusted research materials."""
        ...


class OptimizationWriter(Protocol):
    """Provider-independent boundary for one site-optimization draft."""

    async def write_optimization(
        self,
        prompt: OptimizationPrompt,
    ) -> OptimizationGeneration:
        """Generate one structured draft from bounded audit and search materials."""
        ...
