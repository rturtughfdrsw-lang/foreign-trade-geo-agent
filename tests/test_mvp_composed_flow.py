"""Contract tests for the composed SEO MVP planning-to-verification loop."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import httpx

from foreign_trade_geo_agent.adapters.page_extractor import TrafilaturaPageExtractor
from foreign_trade_geo_agent.adapters.wordpress_rest import (
    WordPressRestDraftPublisher,
    WordPressRestDraftReader,
)
from foreign_trade_geo_agent.core.approved_wordpress_delivery import (
    ApprovedWordPressDraftDeliveryRequest,
)
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
)
from foreign_trade_geo_agent.core.content_draft import (
    ContentDraftGeneration,
    ContentDraftGenerationStatus,
    ContentDraftReport,
)
from foreign_trade_geo_agent.core.content_draft_review import (
    ContentDraftReviewRequest,
)
from foreign_trade_geo_agent.core.content_opportunity import (
    ContentOpportunityGeneration,
    ContentOpportunityGenerationStatus,
)
from foreign_trade_geo_agent.core.fetching import FetchStatus, HtmlFetchResult
from foreign_trade_geo_agent.core.history import (
    ArtifactType,
    RunStatus,
    WordPressAttemptState,
    WordPressVerificationLookupKind,
    WordPressVerificationOutcome,
)
from foreign_trade_geo_agent.core.orchestration import EndToEndRunRequest
from foreign_trade_geo_agent.core.research import (
    ResearchGeneration,
    ResearchGenerationStatus,
)
from foreign_trade_geo_agent.core.search import SearchResponse, SearchResult, SearchStatus
from foreign_trade_geo_agent.core.site_content import SiteContentPacket
from foreign_trade_geo_agent.core.wordpress_verification import (
    WordPressVerificationRequest,
)
from foreign_trade_geo_agent.reporting.content_draft_review import (
    content_draft_review_payload,
)
from foreign_trade_geo_agent.runtime import (
    build_delivery_workflow,
    build_planning_workflow,
    build_review_workflow,
    build_verification_workflow,
)
from foreign_trade_geo_agent.storage.sqlite import SQLiteHistoryStore
from foreign_trade_geo_agent.workflows.wordpress_delivery import (
    WordPressDeliveryStatus,
)


SITE_URL = "https://example.com/"
WORDPRESS_URL = "https://cms.example.com"
WORDPRESS_SITE_KEY = "https://cms.example.com:443"
REMOTE_POST_ID = 41
HTML = b"""<!doctype html>
<html lang="en">
  <head>
    <title>Industrial Pump Materials</title>
    <meta name="description" content="Industrial pump selection guidance">
  </head>
  <body>
    <main>
      <h1>Industrial Pump Materials</h1>
      <h2>Chemical Compatibility</h2>
      <p>Chemical compatibility, material selection, port size, application,
      maintenance considerations, and pump performance are observed topics.</p>
      <p>Buyers compare wetted materials and operating conditions before
      selecting an industrial pump for a corrosive process.</p>
    </main>
  </body>
</html>"""


def _successful_fetch(url: str, content: bytes, content_type: str) -> HtmlFetchResult:
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


class _FixtureFetcher:
    def __init__(self) -> None:
        self.page_requests: list[str] = []
        self.text_requests: list[str] = []

    async def fetch_text(self, url: str, **_kwargs: object) -> HtmlFetchResult:
        self.text_requests.append(url)
        return _successful_fetch(
            url,
            b"User-agent: ForeignTradeGeoAgent\nAllow: /\n",
            "text/plain",
        )

    async def fetch(self, url: str, **_kwargs: object) -> HtmlFetchResult:
        self.page_requests.append(url)
        if url != SITE_URL:
            raise AssertionError(f"Unexpected crawl request: {url}")
        return _successful_fetch(url, HTML, "text/html; charset=utf-8")


class _FixtureAuditor:
    def audit_site(self, url: str) -> SiteAuditResult:
        return SiteAuditResult(
            url=url,
            status=AuditStatus.SUCCESS,
            score=84,
            band="good",
            score_breakdown={"meta": 8},
            recommendations=("Add a descriptive title.",),
            error=None,
            source="deterministic-test-provider",
            source_version="1",
            evidence=(
                AuditEvidence(
                    category=AuditEvidenceCategory.META,
                    check_key="meta.title.present",
                    observed_value=False,
                    outcome=AuditEvidenceOutcome.ABSENT,
                    provider_field="meta.has_title",
                ),
            ),
        )


class _FixtureSearchProvider:
    async def search(self, query: str) -> SearchResponse:
        return SearchResponse(
            query=query,
            status=SearchStatus.SUCCESS,
            results=(
                SearchResult(
                    title="Chemical compatibility selection guide",
                    url="https://research.example.com/chemical-compatibility",
                    content=(
                        "Chemical compatibility and material selection help buyers "
                        "evaluate industrial pump applications."
                    ),
                    score=0.99,
                ),
            ),
            error=None,
        )


class _FixtureResearchWriter:
    async def write_report(self, question: str, materials: tuple[object, ...]) -> ResearchGeneration:
        return ResearchGeneration(
            provider="deterministic-test-provider",
            model="fixed",
            status=ResearchGenerationStatus.SUCCESS,
            text="Chemical compatibility supports pump material selection [S1].",
            error=None,
        )


class _FixtureOpportunityWriter:
    async def write_content_opportunities(self, prompt: object) -> ContentOpportunityGeneration:
        return ContentOpportunityGeneration(
            provider="deterministic-test-provider",
            model="fixed",
            status=ContentOpportunityGenerationStatus.SUCCESS,
            text=json.dumps(
                {
                    "opportunities": [
                        {
                            "opportunity_type": "EXPAND_OBSERVED_CONTENT",
                            "priority": "HIGH",
                            "topic": "chemical compatibility",
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


class _FixtureChangePlanWriter:
    async def write_change_plan(self, prompt: object) -> ChangePlanGeneration:
        return ChangePlanGeneration(
            provider="deterministic-test-provider",
            model="fixed",
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
                                    "subject": "chemical compatibility",
                                }
                            ],
                        }
                    ]
                }
            ),
            error=None,
        )


class _FixtureContentDraftWriter:
    async def write_content_draft(self, prompt: object) -> ContentDraftGeneration:
        return ContentDraftGeneration(
            provider="deterministic-test-provider",
            model="fixed",
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
                                        "text": (
                                            "Material selection and port size are observed."
                                        ),
                                        "claim_type": "OBSERVED_PRODUCT_FACT",
                                        "page_refs": ["P1"],
                                        "source_refs": [],
                                    }
                                ],
                            }
                        ],
                    }
                }
            ),
            error=None,
        )


class _WordPressRecorder:
    def __init__(self, *, timeout_on_post: bool = False) -> None:
        self.timeout_on_post = timeout_on_post
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.method == "POST" and request.url.path == "/wp-json/wp/v2/posts":
            if self.timeout_on_post:
                raise httpx.ReadTimeout("controlled timeout", request=request)
            body = json.loads(request.content)
            if body["status"] != "draft":
                raise AssertionError("WordPress create was not draft-only.")
            return httpx.Response(
                201,
                json={
                    "id": REMOTE_POST_ID,
                    "status": "draft",
                    "link": f"{WORDPRESS_URL}/?p={REMOTE_POST_ID}",
                },
            )
        if (
            request.method == "GET"
            and request.url.path == f"/wp-json/wp/v2/posts/{REMOTE_POST_ID}"
        ):
            return httpx.Response(
                200,
                json={
                    "id": REMOTE_POST_ID,
                    "status": "draft",
                    "link": f"{WORDPRESS_URL}/?p={REMOTE_POST_ID}",
                    "title": {"rendered": "Industrial Pump Buyer Guide"},
                    "content": {"rendered": "<p>Draft body</p>"},
                },
            )
        raise AssertionError(f"Unexpected WordPress request: {request.method} {request.url}")

    def requests_for(self, method: str) -> tuple[httpx.Request, ...]:
        return tuple(request for request in self.requests if request.method == method)


def _content_draft_artifact_id(planning_result: object) -> str:
    return next(
        item.artifact_id
        for item in planning_result.artifacts
        if item.artifact_type is ArtifactType.CONTENT_DRAFT
    )


async def _run_planning(db_path: Path):
    fetcher = _FixtureFetcher()
    workflow = build_planning_workflow(
        db_path,
        fetcher=fetcher,
        site_auditor=_FixtureAuditor(),
        search_provider=_FixtureSearchProvider(),
        research_writer=_FixtureResearchWriter(),
        content_opportunity_writer=_FixtureOpportunityWriter(),
        change_plan_writer=_FixtureChangePlanWriter(),
        content_draft_writer=_FixtureContentDraftWriter(),
    )
    if not isinstance(workflow._site_crawl._extractor, TrafilaturaPageExtractor):
        raise AssertionError("Composed planning must use the production page extractor.")
    result = await workflow.run(
        EndToEndRunRequest(
            site_url=SITE_URL,
            research_question="How should buyers evaluate chemical compatibility?",
        )
    )
    return result, fetcher


def _approved_request(run_id: str, artifact_id: str) -> ApprovedWordPressDraftDeliveryRequest:
    return ApprovedWordPressDraftDeliveryRequest(
        planning_run_id=run_id,
        content_draft_artifact_id=artifact_id,
        draft_id="D1",
        target_site_url=WORDPRESS_URL,
        title_override="Industrial Pump Buyer Guide",
    )


def _publisher(recorder: _WordPressRecorder) -> WordPressRestDraftPublisher:
    return WordPressRestDraftPublisher(
        base_url=WORDPRESS_URL,
        username="test-editor",
        application_password="test-application-password",
        transport=httpx.MockTransport(recorder),
    )


def _reader(recorder: _WordPressRecorder, site_key: str) -> WordPressRestDraftReader:
    return WordPressRestDraftReader(
        base_url=site_key,
        username="test-editor",
        application_password="test-application-password",
        transport=httpx.MockTransport(recorder),
    )


class MvpComposedFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_composed_mvp_happy_path_persists_review_delivery_and_verification(
        self,
    ) -> None:
        with TemporaryDirectory() as temporary_directory:
            db_path = Path(temporary_directory) / "history.sqlite3"
            planning, fetcher = await _run_planning(db_path)
            run_id = planning.run.run_id
            artifact_id = _content_draft_artifact_id(planning)

            self.assertEqual(planning.run.status, RunStatus.SUCCEEDED)
            self.assertTrue(planning.requires_human_review)
            self.assertEqual(fetcher.page_requests, [SITE_URL])
            self.assertEqual(fetcher.text_requests, ["https://example.com/robots.txt"])
            del planning

            review = build_review_workflow(db_path).review(
                ContentDraftReviewRequest(run_id, artifact_id, "D1")
            )
            review_payload = content_draft_review_payload(review)
            self.assertEqual(review.draft.draft_id, "D1")
            self.assertEqual(review.change.change_id, "C1")
            self.assertEqual(review.opportunity.recommendation_id, "R1")
            self.assertEqual(tuple(item.evidence_id for item in review.audit_evidence), ("A1",))
            self.assertEqual(tuple(item.evidence_id for item in review.page_evidence), ("P1",))
            self.assertEqual(tuple(item.source_id for item in review.source_evidence), ("S1",))
            self.assertTrue(review.draft.requires_human_review)
            self.assertEqual(review_payload["approval_record"], "NOT RECORDED")
            self.assertEqual(review_payload["review_action"], "READ ONLY")

            recorder = _WordPressRecorder()
            delivery_workflow = build_delivery_workflow(
                db_path,
                target_site_url=WORDPRESS_URL,
                username="test-editor",
                application_password="test-application-password",
                publisher=_publisher(recorder),
            )
            delivery = await delivery_workflow.deliver(_approved_request(run_id, artifact_id))
            self.assertEqual(delivery.attempt.outcome, WordPressAttemptState.SUCCESS)
            self.assertEqual(delivery.attempt.remote_post_id, REMOTE_POST_ID)

            persisted = SQLiteHistoryStore(db_path)
            self.assertEqual(persisted.list_wordpress_verifications(delivery.attempt.attempt_id), ())
            attempt_before_verify = persisted.get_wordpress_attempt(delivery.attempt.attempt_id)
            del delivery_workflow

            reader_sites: list[str] = []

            def reader_factory(site_key: str) -> WordPressRestDraftReader:
                reader_sites.append(site_key)
                return _reader(recorder, site_key)

            verification = await build_verification_workflow(
                db_path,
                username="test-editor",
                application_password="test-application-password",
                draft_reader_factory=reader_factory,
            ).verify(WordPressVerificationRequest(delivery.attempt.attempt_id))

            final_store = SQLiteHistoryStore(db_path)
            run = final_store.get_run(run_id)
            artifacts = final_store.list_artifacts(run_id)
            attempts = final_store.list_wordpress_attempts(run_id)
            verifications = final_store.list_wordpress_verifications(
                delivery.attempt.attempt_id
            )

            self.assertIsNotNone(run)
            self.assertEqual(run.status, RunStatus.SUCCEEDED)
            self.assertEqual(
                tuple(item.artifact_type for item in artifacts),
                (
                    ArtifactType.SITE_CONTENT,
                    ArtifactType.SITE_AUDIT,
                    ArtifactType.INDUSTRY_RESEARCH,
                    ArtifactType.CONTENT_OPPORTUNITY,
                    ArtifactType.CHANGE_PLAN,
                    ArtifactType.CONTENT_DRAFT,
                ),
            )
            self.assertTrue(all(item.run_id == run_id for item in artifacts))

            packet = artifacts[0].payload
            opportunity_report = artifacts[3].payload
            change_plan = artifacts[4].payload
            draft_report = artifacts[5].payload
            self.assertIsInstance(packet, SiteContentPacket)
            self.assertEqual(tuple(page.evidence_id for page in packet.pages), ("P1",))
            self.assertIn("Chemical compatibility", packet.pages[0].body_text or "")
            self.assertEqual(opportunity_report.audit_evidence[0].evidence_id, "A1")
            opportunity = opportunity_report.opportunities[0]
            self.assertEqual(opportunity.recommendation_id, "R1")
            self.assertEqual(opportunity.page_refs, ("P1",))
            self.assertEqual(opportunity.source_refs, ("S1",))
            self.assertEqual(opportunity.audit_refs, ("A1",))
            change = change_plan.operations[0]
            self.assertEqual(change.change_id, "C1")
            self.assertEqual(change.opportunity_ref, "R1")
            self.assertEqual(change.page_refs, ("P1",))
            self.assertEqual(change.source_refs, ("S1",))
            self.assertEqual(change.audit_refs, ("A1",))
            self.assertIsInstance(draft_report, ContentDraftReport)
            self.assertEqual(tuple(item.draft_id for item in draft_report.drafts), ("D1",))
            draft = draft_report.drafts[0]
            self.assertEqual(draft.change_ref, "C1")
            self.assertEqual(draft.opportunity_ref, "R1")
            self.assertTrue(draft.requires_human_review)

            self.assertEqual(len(attempts), 1)
            self.assertEqual(attempts[0].content_draft_artifact_id, artifact_id)
            self.assertEqual(attempts[0].draft_item_id, "D1")
            self.assertEqual(attempts[0], attempt_before_verify)
            self.assertEqual(attempts[0].outcome, WordPressAttemptState.SUCCESS)
            self.assertEqual(attempts[0].remote_post_id, REMOTE_POST_ID)
            self.assertEqual(len(verifications), 1)
            self.assertEqual(verifications[0].attempt_id, attempts[0].attempt_id)
            self.assertEqual(verifications[0].run_id, run_id)
            self.assertEqual(verifications[0].content_draft_artifact_id, artifact_id)
            self.assertEqual(verifications[0].draft_item_id, "D1")
            self.assertEqual(
                verifications[0].outcome,
                WordPressVerificationOutcome.VERIFIED,
            )
            self.assertEqual(
                verification.verification_outcome,
                WordPressVerificationOutcome.VERIFIED,
            )
            self.assertEqual(reader_sites, [WORDPRESS_SITE_KEY])

            posts = recorder.requests_for("POST")
            gets = recorder.requests_for("GET")
            self.assertEqual(len(posts), 1)
            self.assertEqual(posts[0].url.path, "/wp-json/wp/v2/posts")
            self.assertEqual(json.loads(posts[0].content)["status"], "draft")
            self.assertEqual(len(gets), 1)
            self.assertEqual(gets[0].url.path, "/wp-json/wp/v2/posts/41")
            self.assertEqual(
                tuple(request.method for request in recorder.requests),
                ("POST", "GET"),
            )

    async def test_composed_unknown_create_is_unresolved_and_never_retried(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            db_path = Path(temporary_directory) / "history.sqlite3"
            planning, _fetcher = await _run_planning(db_path)
            run_id = planning.run.run_id
            artifact_id = _content_draft_artifact_id(planning)
            del planning

            recorder = _WordPressRecorder(timeout_on_post=True)
            delivery_workflow = build_delivery_workflow(
                db_path,
                target_site_url=WORDPRESS_URL,
                username="test-editor",
                application_password="test-application-password",
                publisher=_publisher(recorder),
            )
            request = _approved_request(run_id, artifact_id)
            first_delivery = await delivery_workflow.deliver(request)
            attempt_id = first_delivery.attempt.attempt_id

            self.assertEqual(
                first_delivery.delivery_result.status,
                WordPressDeliveryStatus.UNKNOWN,
            )
            self.assertEqual(first_delivery.attempt.outcome, WordPressAttemptState.UNKNOWN)
            self.assertIsNone(first_delivery.attempt.remote_post_id)
            self.assertEqual(len(recorder.requests_for("POST")), 1)

            reader_factory_calls: list[str] = []

            def reader_factory(site_key: str) -> WordPressRestDraftReader:
                reader_factory_calls.append(site_key)
                return _reader(recorder, site_key)

            verification = await build_verification_workflow(
                db_path,
                username="test-editor",
                application_password="test-application-password",
                draft_reader_factory=reader_factory,
            ).verify(WordPressVerificationRequest(attempt_id))
            second_delivery = await delivery_workflow.deliver(request)

            final_store = SQLiteHistoryStore(db_path)
            attempts = final_store.list_wordpress_attempts(run_id)
            verifications = final_store.list_wordpress_verifications(attempt_id)
            self.assertEqual(
                verification.verification_outcome,
                WordPressVerificationOutcome.UNRESOLVED,
            )
            self.assertEqual(
                verification.verification.lookup_kind,
                WordPressVerificationLookupKind.NONE,
            )
            self.assertEqual(reader_factory_calls, [])
            self.assertEqual(len(recorder.requests_for("GET")), 0)
            self.assertEqual(
                second_delivery.delivery_result.status,
                WordPressDeliveryStatus.BLOCKED,
            )
            self.assertEqual(len(recorder.requests_for("POST")), 1)
            self.assertEqual(len(attempts), 1)
            self.assertEqual(attempts[0].outcome, WordPressAttemptState.UNKNOWN)
            self.assertIsNone(attempts[0].remote_post_id)
            self.assertEqual(len(verifications), 1)
            self.assertEqual(
                verifications[0].outcome,
                WordPressVerificationOutcome.UNRESOLVED,
            )


if __name__ == "__main__":
    unittest.main()
