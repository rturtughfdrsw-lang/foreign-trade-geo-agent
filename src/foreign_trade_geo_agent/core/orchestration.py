"""Provider-independent models for one fixed end-to-end planning run."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .change_plan import ChangePlanReport
from .audit import SiteAuditResult
from .content_draft import (
    ContentDraftReport,
    validate_target_language,
)
from .content_opportunity import ContentOpportunityReport
from .crawling import SiteCrawlReport
from .history import (
    ArtifactType,
    RunStatus,
    WorkflowRun,
    site_key_from_url,
    validate_uuid,
)
from .research import ResearchReport


class EndToEndStage(str, Enum):
    """Stages owned by the fixed planning workflow."""

    CRAWL = "crawl"
    SITE_CONTENT = "site_content"
    SITE_AUDIT = "site_audit"
    INDUSTRY_RESEARCH = "industry_research"
    CONTENT_OPPORTUNITY = "content_opportunity"
    CHANGE_PLAN = "change_plan"
    CONTENT_DRAFT = "content_draft"


@dataclass(frozen=True, slots=True)
class EndToEndRunRequest:
    site_url: str
    research_question: str
    target_language: str = "en"

    def __post_init__(self) -> None:
        site_key_from_url(self.site_url)
        if type(self.research_question) is not str:
            raise ValueError("Research question must be a string.")
        question = " ".join(self.research_question.split())
        if not question:
            raise ValueError("Research question must not be empty.")
        if type(self.target_language) is not str:
            raise ValueError("Target language must be a string.")
        language = self.target_language.strip()
        if validate_target_language(language) is not None:
            raise ValueError("Target language is invalid.")
        object.__setattr__(self, "research_question", question)
        object.__setattr__(self, "target_language", language)


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    artifact_id: str
    artifact_type: ArtifactType
    payload_version: int

    def __post_init__(self) -> None:
        validate_uuid(self.artifact_id, "artifact_id")
        if not isinstance(self.artifact_type, ArtifactType):
            raise ValueError("Artifact type is invalid.")
        if type(self.payload_version) is not int or self.payload_version <= 0:
            raise ValueError("Artifact payload version is invalid.")


TerminalReport = (
    SiteAuditResult
    | ResearchReport
    | ContentOpportunityReport
    | ChangePlanReport
    | ContentDraftReport
)


@dataclass(frozen=True, slots=True)
class EndToEndRunResult:
    run: WorkflowRun
    artifacts: tuple[ArtifactRef, ...]
    stopped_stage: EndToEndStage | None
    crawl_report: SiteCrawlReport | None
    terminal_report: TerminalReport | None
    requires_human_review: bool

    def __post_init__(self) -> None:
        if not isinstance(self.run, WorkflowRun):
            raise TypeError("End-to-end result requires WorkflowRun.")
        if not isinstance(self.artifacts, tuple) or not all(
            isinstance(item, ArtifactRef) for item in self.artifacts
        ):
            raise TypeError("End-to-end artifact references are invalid.")
        if self.stopped_stage is not None and not isinstance(
            self.stopped_stage, EndToEndStage
        ):
            raise TypeError("End-to-end stopped stage is invalid.")
        if self.crawl_report is not None and not isinstance(
            self.crawl_report, SiteCrawlReport
        ):
            raise TypeError("End-to-end crawl report is invalid.")
        if self.terminal_report is not None and not isinstance(
            self.terminal_report,
            (
                ResearchReport,
                SiteAuditResult,
                ContentOpportunityReport,
                ChangePlanReport,
                ContentDraftReport,
            ),
        ):
            raise TypeError("End-to-end terminal report is invalid.")
        if type(self.requires_human_review) is not bool:
            raise TypeError("Human-review state is invalid.")

    @property
    def reconciliation_required(self) -> bool:
        return self.run.status is RunStatus.NEEDS_RECONCILIATION
