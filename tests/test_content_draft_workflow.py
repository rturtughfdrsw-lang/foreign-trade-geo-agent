import json
import unittest

from foreign_trade_geo_agent.core.content_draft import (
    ContentDraftGeneration,
    ContentDraftGenerationStatus,
    ContentDraftInput,
    ContentDraftStatus,
    ContentDraftType,
)
from foreign_trade_geo_agent.core.content_opportunity import ContentOpportunityActionCode
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
    point,
)


def _generation(text):
    return ContentDraftGeneration(
        provider="deepseek",
        model="deepseek-flash",
        status=ContentDraftGenerationStatus.SUCCESS,
        text=text,
        error=None,
    )


class _DraftFakeWriter:
    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []
        self.calls = 0

    async def write_content_draft(self, prompt):
        self.prompts.append(prompt)
        self.calls += 1
        if not self.responses:
            raise AssertionError("no more draft responses")
        return self.responses.pop(0)


def _section_text(change_ref="C1"):
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
                            }
                        ],
                    }
                ],
            }
        }
    )


async def _plan(raw, *, site=None, report=None):
    site = site or packet()
    report = report or opportunity_report()
    return await ChangePlanWorkflow(ChangePlanFakeWriter(generated([raw]))).run(
        site, report
    )


async def _expand_input():
    site = packet(
        page(
            "P1",
            body=(
                "Chemical compatibility, material selection, port size, application, "
                "maintenance considerations, and AODD pump maintenance are observed topics."
            ),
        )
    )
    report = opportunity_report(
        opportunity(action_codes=(ContentOpportunityActionCode.EXPAND_PAGE_SECTION,))
    )
    plan = await _plan(expand(), site=site, report=report)
    return ContentDraftInput(site, report, plan)


class ContentDraftWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_zero_change_plan_is_success_without_calls(self) -> None:
        site = packet(page("P1"))
        report = opportunity_report(opportunity())
        empty_plan = await ChangePlanWorkflow(
            ChangePlanFakeWriter(generated([]))
        ).run(site, report)
        writer = _DraftFakeWriter([])
        result = await ContentDraftWorkflow(writer).run(
            ContentDraftInput(site, report, empty_plan)
        )
        self.assertEqual(result.status, ContentDraftStatus.SUCCESS)
        self.assertEqual(result.drafts, ())
        self.assertEqual(writer.calls, 0)

    async def test_one_prose_change_makes_one_call_and_one_draft(self) -> None:
        writer = _DraftFakeWriter([_generation(_section_text())])
        result = await ContentDraftWorkflow(writer).run(await _expand_input())
        self.assertEqual(result.status, ContentDraftStatus.SUCCESS)
        self.assertEqual(len(result.drafts), 1)
        self.assertEqual(result.drafts[0].draft_id, "D1")
        self.assertEqual(writer.calls, 1)
        self.assertEqual(writer.prompts[0].change_ref, "C1")

    async def test_structure_only_mixed_case_skips_provider(self) -> None:
        site = packet(page("P1", h2=("Chemical Compatibility", "Maintenance")))
        report = opportunity_report(
            opportunity(
                "R1",
                action_codes=(ContentOpportunityActionCode.REORGANIZE_PAGE_SECTIONS,),
            )
        )
        reorder_raw = {
            **common("PROPOSE_SECTION_REORDER", action="REORGANIZE_PAGE_SECTIONS"),
            "ordered_headings": ["Chemical Compatibility", "Maintenance"],
        }
        plan = await _plan(reorder_raw, site=site, report=report)
        writer = _DraftFakeWriter([])
        result = await ContentDraftWorkflow(writer).run(
            ContentDraftInput(site, report, plan)
        )
        self.assertEqual(result.status, ContentDraftStatus.SUCCESS)
        self.assertEqual(writer.calls, 0)
        self.assertEqual(result.drafts[0].draft_type, ContentDraftType.STRUCTURE_ONLY)
        self.assertEqual(
            result.drafts[0].ordered_headings,
            ("Chemical Compatibility", "Maintenance"),
        )

    async def test_all_or_nothing_discards_partial_drafts_and_aborts(self) -> None:
        site = packet(page("P1"))
        report = opportunity_report(
            opportunity("R1", action_codes=(ContentOpportunityActionCode.EXPAND_PAGE_SECTION,)),
            opportunity("R2", action_codes=(ContentOpportunityActionCode.ADD_TECHNICAL_DOCUMENTATION,)),
        )
        raw1 = expand()
        raw2 = {
            **common("ADD_SECTION", action="ADD_TECHNICAL_DOCUMENTATION"),
            "opportunity_ref": "R2",
            "section_purpose": "TECHNICAL_DOCUMENTATION",
            "proposed_heading": "Chemical Compatibility Guide",
            "content_points": [point("chemical compatibility")],
        }
        raw3 = expand(content_points=[point("maintenance considerations")])
        plan = await ChangePlanWorkflow(
            ChangePlanFakeWriter(generated([raw1, raw2, raw3]))
        ).run(site, report)
        writer = _DraftFakeWriter(
            [_generation(_section_text("C1")), _generation("not-json")]
        )
        result = await ContentDraftWorkflow(writer).run(
            ContentDraftInput(site, report, plan)
        )
        self.assertEqual(result.status, ContentDraftStatus.INVALID_OUTPUT)
        self.assertEqual(result.drafts, ())
        self.assertEqual(writer.calls, 2)

    async def test_malformed_json_is_invalid_output(self) -> None:
        writer = _DraftFakeWriter([_generation("not-json")])
        result = await ContentDraftWorkflow(writer).run(await _expand_input())
        self.assertEqual(result.status, ContentDraftStatus.INVALID_OUTPUT)
        self.assertEqual(result.error, "JSON_FORMAT")

    async def test_provider_draft_id_is_rejected(self) -> None:
        text = json.dumps(
            {
                "draft": {
                    "draft_id": "D1",
                    "change_ref": "C1",
                    "draft_type": "SECTION_DRAFT",
                    "blocks": [],
                }
            }
        )
        writer = _DraftFakeWriter([_generation(text)])
        result = await ContentDraftWorkflow(writer).run(await _expand_input())
        self.assertEqual(result.status, ContentDraftStatus.INVALID_OUTPUT)
        self.assertEqual(result.error, "FIELD_CONTRACT")

    async def test_provider_url_is_rejected(self) -> None:
        text = json.dumps(
            {
                "draft": {
                    "change_ref": "C1",
                    "draft_type": "SECTION_DRAFT",
                    "url": "https://example.com/evil",
                    "blocks": [],
                }
            }
        )
        writer = _DraftFakeWriter([_generation(text)])
        result = await ContentDraftWorkflow(writer).run(await _expand_input())
        self.assertEqual(result.status, ContentDraftStatus.INVALID_OUTPUT)
        self.assertEqual(result.error, "FIELD_CONTRACT")

    async def test_target_language_default_en_and_explicit_bounded(self) -> None:
        writer = _DraftFakeWriter([_generation(_section_text())])
        result = await ContentDraftWorkflow(writer).run(await _expand_input())
        self.assertEqual(result.status, ContentDraftStatus.SUCCESS)
        self.assertEqual(writer.prompts[0].input.target_language, "en")

        site = packet(page("P1"))
        report = opportunity_report(
            opportunity(action_codes=(ContentOpportunityActionCode.EXPAND_PAGE_SECTION,))
        )
        plan = await _plan(expand(), site=site, report=report)
        writer2 = _DraftFakeWriter([_generation(_section_text())])
        result2 = await ContentDraftWorkflow(writer2).run(
            ContentDraftInput(site, report, plan, target_language="en-GB")
        )
        self.assertEqual(result2.status, ContentDraftStatus.SUCCESS)
        self.assertEqual(writer2.prompts[0].input.target_language, "en-GB")

    async def test_deterministic_report_for_same_input(self) -> None:
        writer1 = _DraftFakeWriter([_generation(_section_text())])
        writer2 = _DraftFakeWriter([_generation(_section_text())])
        result1 = await ContentDraftWorkflow(writer1).run(await _expand_input())
        result2 = await ContentDraftWorkflow(writer2).run(await _expand_input())
        self.assertEqual(result1, result2)

    async def test_multiple_structure_only_makes_zero_calls(self) -> None:
        site = packet(
            page("P1", h2=("Chemical Compatibility", "Maintenance")),
            page("P2", h2=("Installation", "Warranty")),
        )
        report = opportunity_report(
            opportunity(
                "R1",
                action_codes=(ContentOpportunityActionCode.REORGANIZE_PAGE_SECTIONS,),
                page_refs=("P1",),
            ),
            opportunity(
                "R2",
                action_codes=(ContentOpportunityActionCode.REORGANIZE_PAGE_SECTIONS,),
                page_refs=("P2",),
            ),
        )
        raw1 = {
            **common("PROPOSE_SECTION_REORDER", action="REORGANIZE_PAGE_SECTIONS"),
            "opportunity_ref": "R1",
            "page_refs": ["P1"],
            "target_page_ref": "P1",
            "ordered_headings": ["Chemical Compatibility", "Maintenance"],
        }
        raw2 = {
            **common("PROPOSE_SECTION_REORDER", action="REORGANIZE_PAGE_SECTIONS"),
            "opportunity_ref": "R2",
            "page_refs": ["P2"],
            "target_page_ref": "P2",
            "ordered_headings": ["Installation", "Warranty"],
        }
        plan = await ChangePlanWorkflow(
            ChangePlanFakeWriter(generated([raw1, raw2]))
        ).run(site, report)
        writer = _DraftFakeWriter([])
        result = await ContentDraftWorkflow(writer).run(
            ContentDraftInput(site, report, plan)
        )
        self.assertEqual(result.status, ContentDraftStatus.SUCCESS)
        self.assertEqual(writer.calls, 0)
        self.assertEqual(
            tuple(item.draft_id for item in result.drafts), ("D1", "D2")
        )
        self.assertTrue(all(item.draft_type is ContentDraftType.STRUCTURE_ONLY for item in result.drafts))


if __name__ == "__main__":
    unittest.main()
