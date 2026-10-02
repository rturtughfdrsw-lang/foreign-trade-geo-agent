"""Ports implemented by external service providers."""

from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from .history import (
    ArtifactRecord,
    ArtifactType,
    RunStatus,
    WorkflowRun,
    WordPressAttemptState,
    WordPressDraftAttempt,
)

from .audit import SiteAuditResult
from .content_opportunity import ContentOpportunityGeneration, ContentOpportunityPrompt
from .change_plan import ChangePlanGeneration, ChangePlanPrompt
from .content_draft import ContentDraftGeneration, ContentDraftPrompt
from .extraction import PageExtractionResult
from .fetching import HtmlFetchResult, TextFetchResult, UrlOrigin
from .optimization import OptimizationGeneration, OptimizationPrompt
from .research import ResearchGeneration, ResearchMaterial
from .search import SearchResponse
from .visibility import ProviderResponse
from .wordpress_draft import WordPressDraftRequest, WordPressDraftResult


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
        max_request_attempts: int | None = None,
        max_total_wire_bytes: int | None = None,
        max_total_decoded_bytes: int | None = None,
        redirect_policy: Callable[[str], bool] | None = None,
    ) -> HtmlFetchResult:
        """Return HTML or a bounded, classified failure."""
        ...


class TextFetcher(Protocol):
    """Fetch bounded plain text through the security-enforcing boundary."""

    async def fetch_text(
        self,
        url: str,
        *,
        expected_origin: UrlOrigin | None = None,
        max_request_attempts: int | None = None,
        max_total_wire_bytes: int | None = None,
        max_total_decoded_bytes: int | None = None,
        redirect_policy: Callable[[str], bool] | None = None,
    ) -> TextFetchResult:
        """Return plain text bytes or a bounded, classified failure."""
        ...


class CrawlFetcher(HtmlFetcher, TextFetcher, Protocol):
    """Network boundary required by the site crawl workflow."""


class PageExtractor(Protocol):
    """Extract structured page content from already downloaded HTML."""

    def extract(self, html: bytes, final_url: str) -> PageExtractionResult:
        """Return bounded page data without performing network access."""
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


class ContentOpportunityWriter(Protocol):
    """Provider-independent boundary for one content-opportunity draft."""

    async def write_content_opportunities(
        self,
        prompt: ContentOpportunityPrompt,
    ) -> ContentOpportunityGeneration:
        """Generate structured specifications from bounded P and S evidence."""
        ...


class ChangePlanWriter(Protocol):
    """Provider-independent boundary for one bounded change-plan draft."""

    async def write_change_plan(
        self,
        prompt: ChangePlanPrompt,
    ) -> ChangePlanGeneration:
        """Generate strict operation specifications from bounded R/P/S evidence."""
        ...


class ContentDraftWriter(Protocol):
    """Provider-independent boundary for one bounded content-draft call."""

    async def write_content_draft(
        self,
        prompt: ContentDraftPrompt,
    ) -> ContentDraftGeneration:
        """Generate bounded draft material from one C# and its evidence."""
        ...


class ContentDraftPublisher(Protocol):
    """Publish a provider-independent content draft as a remote draft only."""

    async def publish_draft(
        self,
        request: WordPressDraftRequest,
    ) -> WordPressDraftResult:
        """Create one remote WordPress draft."""
        ...


class HistoryStore(Protocol):
    """Provider-independent synchronous historical persistence boundary."""

    def create_run(self, run: WorkflowRun) -> None: ...

    def finish_run(
        self,
        run_id: str,
        *,
        status: RunStatus,
        completed_at: datetime,
        failure_kind: str | None = None,
        sanitized_error: str | None = None,
    ) -> WorkflowRun: ...

    def append_artifact(self, artifact: ArtifactRecord) -> None: ...

    def get_run(self, run_id: str) -> WorkflowRun | None: ...

    def list_runs_for_site(self, site_key: str, *, limit: int = 100) -> tuple[WorkflowRun, ...]: ...

    def get_artifact(self, artifact_id: str) -> ArtifactRecord | None: ...

    def list_artifacts(
        self,
        run_id: str,
        *,
        artifact_type: ArtifactType | None = None,
        limit: int = 100,
    ) -> tuple[ArtifactRecord, ...]: ...

    def begin_wordpress_attempt(self, attempt: WordPressDraftAttempt) -> None: ...

    def finish_wordpress_attempt(
        self,
        attempt_id: str,
        *,
        outcome: WordPressAttemptState,
        completed_at: datetime,
        remote_post_id: int | None = None,
        remote_link: str | None = None,
        failure_kind: str | None = None,
        sanitized_error: str | None = None,
    ) -> WordPressDraftAttempt: ...

    def list_wordpress_attempts(self, run_id: str, *, limit: int = 100) -> tuple[WordPressDraftAttempt, ...]: ...

    def list_wordpress_attempts_for_draft(
        self,
        content_draft_artifact_id: str,
        draft_item_id: str,
        *,
        limit: int = 100,
    ) -> tuple[WordPressDraftAttempt, ...]: ...

    def find_wordpress_attempts_by_fingerprint(
        self,
        target_site_key: str,
        request_fingerprint: str,
        *,
        limit: int = 100,
    ) -> tuple[WordPressDraftAttempt, ...]: ...


class HistoryReader(Protocol):
    """Read-only retrieval subset used by inspection workflows."""

    def get_run(self, run_id: str) -> WorkflowRun | None: ...

    def get_artifact(self, artifact_id: str) -> ArtifactRecord | None: ...

    def list_artifacts(
        self,
        run_id: str,
        *,
        artifact_type: ArtifactType | None = None,
        limit: int = 100,
    ) -> tuple[ArtifactRecord, ...]: ...
