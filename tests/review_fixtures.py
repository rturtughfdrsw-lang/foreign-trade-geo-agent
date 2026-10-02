"""Shared persisted-fixture builders for the BLOCKER-2 review tests."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import sqlite3

from foreign_trade_geo_agent.core.audit import (
    AuditEvidence,
    AuditEvidenceCategory,
    AuditEvidenceOutcome,
    AuditStatus,
    SiteAuditResult,
)
from foreign_trade_geo_agent.core.change_plan import ChangePlanReport
from foreign_trade_geo_agent.core.content_draft import (
    ContentDraftGeneration,
    ContentDraftGenerationStatus,
    ContentDraftInput,
    ContentDraftReport,
    ContentDraftStatus,
)
from foreign_trade_geo_agent.core.content_opportunity import (
    ContentOpportunityActionCode,
    ContentOpportunityReport,
)
from foreign_trade_geo_agent.core.history import (
    ArtifactRecord,
    ArtifactType,
    RunStatus,
    WorkflowRun,
)
from foreign_trade_geo_agent.core.optimization import NumberedAuditEvidence
from foreign_trade_geo_agent.core.research import (
    ResearchReport,
    ResearchSource,
    ResearchStatus,
)
from foreign_trade_geo_agent.core.site_content import SiteContentPacket
from foreign_trade_geo_agent.storage.sqlite import SQLiteHistoryStore
from foreign_trade_geo_agent.workflows.change_plan import ChangePlanWorkflow
from foreign_trade_geo_agent.workflows.content_draft import ContentDraftWorkflow
from tests.test_change_plan_workflow import (
    FakeWriter as ChangePlanFakeWriter,
    common,
    expand,
    generated,
    opportunity,
    opportunity_report,
    packet,
    page,
)


RUN_ID = "11111111-1111-4111-8111-111111111111"
SITE_CONTENT_ARTIFACT_ID = "22222222-2222-4222-8222-222222222221"
SITE_AUDIT_ARTIFACT_ID = "22222222-2222-4222-8222-222222222222"
INDUSTRY_RESEARCH_ARTIFACT_ID = "22222222-2222-4222-8222-222222222223"
CONTENT_OPPORTUNITY_ARTIFACT_ID = "22222222-2222-4222-8222-222222222224"
CHANGE_PLAN_ARTIFACT_ID = "22222222-2222-4222-8222-222222222225"
CONTENT_DRAFT_ARTIFACT_ID = "22222222-2222-4222-8222-222222222226"
UNKNOWN_ARTIFACT_ID = "99999999-9999-4999-8999-999999999999"
NOW = datetime(2026, 10, 2, 8, 30, tzinfo=UTC)
WORKFLOW_NAME = "end_to_end_planning_v1"
PAGE_EXCERPT_SENTINEL = "Observed product information"
UNUSED_PAGE_EXCERPT_SENTINEL = "Uncited secondary page observation"
RESEARCH_SENTINEL = "RESEARCH_SENTINEL_SHOULD_NOT_APPEAR"
UNUSED_AUDIT_CHECK_KEY = "content.word_count"


@dataclass(frozen=True, slots=True)
class ReviewDomain:
    site_content: SiteContentPacket
    opportunity_report: ContentOpportunityReport
    change_plan: ChangePlanReport
    content_draft: ContentDraftReport


@dataclass(frozen=True, slots=True)
class PersistedReviewFixture:
    db_path: Path
    domain: ReviewDomain


def _generation(text: str) -> ContentDraftGeneration:
    return ContentDraftGeneration(
        provider="fake",
        model="fake",
        status=ContentDraftGenerationStatus.SUCCESS,
        text=text,
        error=None,
    )


class _DraftWriter:
    def __init__(self, responses: list[ContentDraftGeneration]) -> None:
        self._responses = list(responses)
        self.calls = 0

    async def write_content_draft(self, prompt: object) -> ContentDraftGeneration:
        self.calls += 1
        if not self._responses:
            raise AssertionError("no more draft responses")
        return self._responses.pop(0)


def _section_text(change_ref: str = "C1") -> str:
    return json.dumps(
        {
            "draft": {
                "change_ref": change_ref,
                "draft_type": "SECTION_DRAFT",
                "blocks": [
                    {
                        "kind": "PARAGRAPH",
                        "claims": [
                            {
                                "text": "Material selection and port size are observed.",
                                "claim_type": "OBSERVED_PRODUCT_FACT",
                                "page_refs": ["P1"],
                                "source_refs": [],
                            },
                            {
                                "text": (
                                    "Chemical compatibility guidance appears in the "
                                    "external pump guide."
                                ),
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
                                "text": (
                                    "Maintenance considerations are described in the "
                                    "external pump guide."
                                ),
                                "claim_type": "GENERAL_TECHNICAL_CONTEXT",
                                "page_refs": [],
                                "source_refs": ["S1"],
                            }
                        ],
                    },
                ],
            }
        },
        ensure_ascii=False,
    )


def _reorder_operation() -> dict[str, object]:
    return {
        **common("PROPOSE_SECTION_REORDER", action="REORGANIZE_PAGE_SECTIONS"),
        "opportunity_ref": "R2",
        "ordered_headings": ["Chemical Compatibility", "Maintenance"],
    }


def audit_evidence_items() -> tuple[NumberedAuditEvidence, ...]:
    return (
        NumberedAuditEvidence(
            "A1",
            AuditEvidence(
                AuditEvidenceCategory.META,
                "meta.title.present",
                False,
                AuditEvidenceOutcome.ABSENT,
                "meta.title.present",
            ),
        ),
        NumberedAuditEvidence(
            "A2",
            AuditEvidence(
                AuditEvidenceCategory.CONTENT,
                UNUSED_AUDIT_CHECK_KEY,
                500,
                AuditEvidenceOutcome.OBSERVED,
                UNUSED_AUDIT_CHECK_KEY,
            ),
        ),
    )


def _audit_report() -> SiteAuditResult:
    return SiteAuditResult(
        url="https://example.com/",
        status=AuditStatus.SUCCESS,
        score=90,
        band="good",
        score_breakdown={},
        recommendations=(),
        error=None,
        source="fake",
        source_version="1",
        evidence=tuple(item.evidence for item in audit_evidence_items()),
    )


def _research_report() -> ResearchReport:
    return ResearchReport(
        question="buyer question",
        status=ResearchStatus.SUCCESS,
        draft_text=RESEARCH_SENTINEL,
        sources=(ResearchSource("S1", "Source", "https://source.example/s1"),),
        error=None,
    )


async def build_review_domain() -> ReviewDomain:
    """Build one valid D1/D2 planning chain using the real workflows."""

    site_content = packet(
        page("P1", body=PAGE_EXCERPT_SENTINEL),
        page("P2", body=UNUSED_PAGE_EXCERPT_SENTINEL),
    )
    opportunity_report_value = opportunity_report(
        opportunity(
            "R1",
            action_codes=(ContentOpportunityActionCode.EXPAND_PAGE_SECTION,),
            audit_refs=("A1",),
        ),
        opportunity(
            "R2",
            action_codes=(ContentOpportunityActionCode.REORGANIZE_PAGE_SECTIONS,),
        ),
        audit_evidence=audit_evidence_items(),
    )
    change_plan = await ChangePlanWorkflow(
        ChangePlanFakeWriter(generated([expand(), _reorder_operation()]))
    ).run(site_content, opportunity_report_value)
    content_draft = await ContentDraftWorkflow(
        _DraftWriter([_generation(_section_text("C1"))])
    ).run(
        ContentDraftInput(
            site_content=site_content,
            opportunity_report=opportunity_report_value,
            change_plan_report=change_plan,
            target_language="en",
        )
    )
    if (
        change_plan.status.value != "success"
        or content_draft.status is not ContentDraftStatus.SUCCESS
        or tuple(item.draft_id for item in content_draft.drafts) != ("D1", "D2")
    ):
        raise AssertionError("review fixture could not build a valid planning chain")
    return ReviewDomain(
        site_content=site_content,
        opportunity_report=opportunity_report_value,
        change_plan=change_plan,
        content_draft=content_draft,
    )


def persist_review_fixture(db_path: str | Path) -> PersistedReviewFixture:
    """Persist the review fixture into a real SQLite history database."""

    path = Path(db_path)
    domain = asyncio.run(build_review_domain())
    store = SQLiteHistoryStore(path)
    store.create_run(
        WorkflowRun(
            run_id=RUN_ID,
            site_key="https://example.com:443",
            workflow_name=WORKFLOW_NAME,
            started_at=NOW,
            completed_at=None,
            status=RunStatus.RUNNING,
            failure_kind=None,
            sanitized_error=None,
        )
    )
    for artifact_type, artifact_id, payload in (
        (ArtifactType.SITE_CONTENT, SITE_CONTENT_ARTIFACT_ID, domain.site_content),
        (ArtifactType.SITE_AUDIT, SITE_AUDIT_ARTIFACT_ID, _audit_report()),
        (
            ArtifactType.INDUSTRY_RESEARCH,
            INDUSTRY_RESEARCH_ARTIFACT_ID,
            _research_report(),
        ),
        (
            ArtifactType.CONTENT_OPPORTUNITY,
            CONTENT_OPPORTUNITY_ARTIFACT_ID,
            domain.opportunity_report,
        ),
        (ArtifactType.CHANGE_PLAN, CHANGE_PLAN_ARTIFACT_ID, domain.change_plan),
        (ArtifactType.CONTENT_DRAFT, CONTENT_DRAFT_ARTIFACT_ID, domain.content_draft),
    ):
        store.append_artifact(
            ArtifactRecord(
                artifact_id=artifact_id,
                run_id=RUN_ID,
                artifact_type=artifact_type,
                payload_version=1,
                created_at=NOW,
                payload=payload,
            )
        )
    store.finish_run(RUN_ID, status=RunStatus.SUCCEEDED, completed_at=NOW)
    return PersistedReviewFixture(db_path=path, domain=domain)


def raw_sqlite_update(db_path: str | Path, statement: str, parameters: tuple[object, ...]) -> None:
    """Test-only direct database mutation used to simulate corrupted history."""

    connection = sqlite3.connect(Path(db_path))
    try:
        connection.execute(statement, parameters)
        connection.commit()
    finally:
        connection.close()


def corrupt_artifact_payload(
    db_path: str | Path,
    artifact_id: str,
    payload_json: str = "{not-json",
) -> None:
    raw_sqlite_update(
        db_path,
        "UPDATE artifacts SET payload_json=? WHERE artifact_id=?",
        (payload_json, artifact_id),
    )


def rewrite_opportunity_audit_refs(
    db_path: str | Path,
    *,
    recommendation_id: str,
    audit_refs: list[str],
) -> None:
    connection = sqlite3.connect(Path(db_path))
    try:
        row = connection.execute(
            "SELECT payload_json FROM artifacts WHERE artifact_id=?",
            (CONTENT_OPPORTUNITY_ARTIFACT_ID,),
        ).fetchone()
        if row is None:
            raise AssertionError("content opportunity artifact is missing")
        payload = json.loads(row[0])
        for item in payload["opportunities"]:
            if item["recommendation_id"] == recommendation_id:
                item["audit_refs"] = list(audit_refs)
                break
        else:
            raise AssertionError("recommendation is missing")
        connection.execute(
            "UPDATE artifacts SET payload_json=? WHERE artifact_id=?",
            (
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                CONTENT_OPPORTUNITY_ARTIFACT_ID,
            ),
        )
        connection.commit()
    finally:
        connection.close()


def database_business_snapshot(db_path: str | Path) -> tuple[object, ...]:
    """Return row counts and payload bytes for the business tables."""

    connection = sqlite3.connect(Path(db_path))
    try:
        counts = tuple(
            connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("runs", "artifacts", "wordpress_draft_attempts")
        )
        payloads = tuple(
            row[0]
            for row in connection.execute(
                "SELECT payload_json FROM artifacts ORDER BY artifact_id"
            ).fetchall()
        )
        runs = tuple(
            row
            for row in connection.execute(
                "SELECT * FROM runs ORDER BY run_id"
            ).fetchall()
        )
    finally:
        connection.close()
    return (counts, payloads, runs)
