from __future__ import annotations

from datetime import UTC, datetime
import json
import unittest

from foreign_trade_geo_agent.core.audit import (
    AuditEvidence,
    AuditEvidenceCategory,
    AuditEvidenceOutcome,
    AuditStatus,
    SiteAuditResult,
)
from foreign_trade_geo_agent.core.change_plan import ChangePlanReport, ChangePlanStatus
from foreign_trade_geo_agent.core.content_draft import ContentDraftReport, ContentDraftStatus
from foreign_trade_geo_agent.core.content_opportunity import (
    ContentOpportunityReport,
    ContentOpportunityStatus,
)
from foreign_trade_geo_agent.core.crawling import CrawlStopReason
from foreign_trade_geo_agent.core.history import (
    ArtifactType,
    MalformedHistoryDataError,
    UnsupportedHistoryVersionError,
)
from foreign_trade_geo_agent.core.optimization import OptimizationStatus, SiteOptimizationReport
from foreign_trade_geo_agent.core.research import ResearchReport, ResearchStatus
from foreign_trade_geo_agent.core.site_content import SiteContentPacket
from foreign_trade_geo_agent.core.visibility import (
    ProviderResponse,
    ResponseStatus,
    VisibilityObservation,
    VisibilityReport,
)
from foreign_trade_geo_agent.storage.serialization import decode_artifact, encode_artifact


def artifacts() -> dict[ArtifactType, object]:
    failed_response = ProviderResponse(
        provider="provider",
        model="model",
        status=ResponseStatus.FAILED,
        text=None,
        citations=(),
        error="failed",
    )
    return {
        ArtifactType.SITE_CONTENT: SiteContentPacket(
            pages=(),
            source_page_count=0,
            crawl_stop_reason=CrawlStopReason.COMPLETED,
            crawl_budget_exhausted=False,
            truncated=False,
        ),
        ArtifactType.SITE_AUDIT: SiteAuditResult(
            url="https://example.com",
            status=AuditStatus.FAILED,
            score=None,
            band=None,
            score_breakdown={},
            recommendations=(),
            error="audit_failed",
            source="test",
            source_version="1",
        ),
        ArtifactType.VISIBILITY: VisibilityReport(
            target_brand="Example",
            total_attempts=1,
            successful_observations=0,
            failed_observations=1,
            mentioned_count=0,
            mention_rate=None,
            competitor_mention_counts={"Competitor": 0},
            competitor_mention_rates={"Competitor": None},
            citation_count=0,
            observations=(
                VisibilityObservation(
                    prompt="prompt",
                    provider="provider",
                    model="model",
                    response=failed_response,
                    target_mentioned=None,
                    mentioned_competitors=(),
                    timestamp=datetime(2026, 10, 2, 8, 30, tzinfo=UTC),
                ),
            ),
        ),
        ArtifactType.SITE_OPTIMIZATION: SiteOptimizationReport(
            url="https://example.com",
            status=OptimizationStatus.GENERATION_FAILED,
            recommendations=(),
            audit_evidence=(),
            sources=(),
            error="generation failed",
        ),
        ArtifactType.INDUSTRY_RESEARCH: ResearchReport(
            question="question",
            status=ResearchStatus.GENERATION_FAILED,
            draft_text=None,
            sources=(),
            error="generation failed",
        ),
        ArtifactType.CONTENT_OPPORTUNITY: ContentOpportunityReport(
            status=ContentOpportunityStatus.GENERATION_FAILED,
            opportunities=(),
            pages=(),
            sources=(),
            limitations=(),
            error="generation failed",
        ),
        ArtifactType.CHANGE_PLAN: ChangePlanReport(
            status=ChangePlanStatus.GENERATION_FAILED,
            operations=(),
            limitations=(),
            error=None,
        ),
        ArtifactType.CONTENT_DRAFT: ContentDraftReport(
            status=ContentDraftStatus.GENERATION_FAILED,
            drafts=(),
            limitations=(),
            error=None,
        ),
    }


class ArtifactSerializationTests(unittest.TestCase):
    def test_round_trips_every_v1_root_as_exact_domain_type(self) -> None:
        for artifact_type, value in artifacts().items():
            with self.subTest(artifact_type=artifact_type):
                payload = encode_artifact(artifact_type, value, payload_version=1)
                restored = decode_artifact(artifact_type, 1, payload)
                self.assertEqual(restored, value)
                self.assertIs(type(restored), type(value))
                self.assertNotIn("__class__", payload)

    def test_json_is_canonical_unicode_and_utc_z(self) -> None:
        payload = encode_artifact(
            ArtifactType.VISIBILITY,
            artifacts()[ArtifactType.VISIBILITY],
            payload_version=1,
        )
        self.assertEqual(payload, json.dumps(json.loads(payload), ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")))
        self.assertIn('"timestamp":"2026-10-02T08:30:00Z"', payload)

    def test_wrong_root_type_unsupported_version_and_malformed_payload_fail_closed(self) -> None:
        with self.assertRaises(TypeError):
            encode_artifact(
                ArtifactType.SITE_AUDIT,
                artifacts()[ArtifactType.SITE_CONTENT],
                payload_version=1,
            )
        with self.assertRaises(UnsupportedHistoryVersionError):
            decode_artifact(ArtifactType.SITE_AUDIT, 99, "{}")
        for payload in ("not json", "[]", '{"unexpected":true}'):
            with self.subTest(payload=payload), self.assertRaises(MalformedHistoryDataError):
                decode_artifact(ArtifactType.SITE_AUDIT, 1, payload)

    def test_invalid_reconstructed_domain_model_is_malformed_history(self) -> None:
        value = artifacts()[ArtifactType.SITE_AUDIT]
        payload = json.loads(encode_artifact(ArtifactType.SITE_AUDIT, value, payload_version=1))
        payload["status"] = "success"
        with self.assertRaises(MalformedHistoryDataError):
            decode_artifact(
                ArtifactType.SITE_AUDIT,
                1,
                json.dumps(payload, separators=(",", ":"), sort_keys=True),
            )

    def test_integer_union_value_round_trips_without_matching_float(self) -> None:
        value = SiteAuditResult(
            url="https://example.com",
            status=AuditStatus.SUCCESS,
            score=80,
            band="good",
            score_breakdown={"technical": 80},
            recommendations=(),
            error=None,
            source="test",
            source_version="1",
            evidence=(
                AuditEvidence(
                    category=AuditEvidenceCategory.CONTENT,
                    check_key="content.word_count",
                    observed_value=42,
                    outcome=AuditEvidenceOutcome.OBSERVED,
                    provider_field="content.word_count",
                ),
            ),
        )
        payload = encode_artifact(ArtifactType.SITE_AUDIT, value)
        self.assertEqual(decode_artifact(ArtifactType.SITE_AUDIT, 1, payload), value)

    def test_nonfinite_numbers_and_duplicate_json_keys_fail_closed(self) -> None:
        payload = encode_artifact(
            ArtifactType.VISIBILITY,
            artifacts()[ArtifactType.VISIBILITY],
        )
        with self.assertRaises(MalformedHistoryDataError):
            decode_artifact(
                ArtifactType.VISIBILITY,
                1,
                payload.replace('"mention_rate":null', '"mention_rate":NaN'),
            )
        duplicate = payload.replace(
            '"target_brand":"Example"',
            '"target_brand":"First","target_brand":"Second"',
        )
        with self.assertRaises(MalformedHistoryDataError):
            decode_artifact(ArtifactType.VISIBILITY, 1, duplicate)


if __name__ == "__main__":
    unittest.main()
