"""Ports implemented by external service providers."""

from typing import Protocol

from .audit import SiteAuditResult
from .research import ResearchGeneration, ResearchMaterial
from .search import SearchResponse
from .visibility import ProviderResponse


class SiteAuditor(Protocol):
    """Provider-independent site-audit boundary used by workflows."""

    def audit_site(self, url: str) -> SiteAuditResult:
        """Audit one public website URL."""
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
