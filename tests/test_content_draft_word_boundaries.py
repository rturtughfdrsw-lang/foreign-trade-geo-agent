"""First-party markers must reject words, without rejecting their substrings."""
import json
import unittest

from foreign_trade_geo_agent.core import content_draft as cd
from foreign_trade_geo_agent.workflows.content_draft import _parse_specification
from tests.test_content_draft_workflow import _expand_input, _section_text


class FirstPartyWordBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.value = await _expand_input()

    def finalize(self, text, claim_type):
        payload = json.loads(_section_text())
        payload["draft"]["blocks"][0]["claims"][0].update(
            text=text, claim_type=claim_type, page_refs=[], source_refs=[])
        operation = self.value.change_plan_report.operations[0]
        spec = _parse_specification(json.dumps(payload), expected_change_ref="C1", operation=operation)
        return cd.finalize_draft_item(1, spec, operation,
            self.value.opportunity_report.opportunities[0], self.value.site_content,
            self.value.opportunity_report)

    async def test_normal_words_and_second_person_survive_finalizer(self):
        for text in (
            "your planned application", "yourself", "hour", "flour",
            "Check your planned application.", "Check this yourself.",
            "Allow an hour for review.", "Review the flour sample.",
            "Consider the remodel planning.", "Contact the supplier to confirm how a stated test applies to your planned cutting cycle.",
        ):
            for claim_type in ("CALL_TO_ACTION", "EDITORIAL_TRANSITION"):
                with self.subTest(text=text, claim_type=claim_type):
                    draft, error = self.finalize(text, claim_type)
                    self.assertIsNone(error)
                    self.assertIsNotNone(draft)
                    self.assertEqual(draft.blocks[0].claims[0].text, text)

    async def test_actual_restricted_markers_still_rejected(self):
        for text in (
            "our product", "our team", "our company", "our factory", "our pump",
            "Contact our team.", "Ask whether we can help.",
            "Review certification scope.", "Review certified scope.",
            "Review warranty terms.", "Review maximum duty.",
            "Review material code.", "Review port size.",
            "Review patented designs.", "Review model scope.",
        ):
            for claim_type in ("CALL_TO_ACTION", "EDITORIAL_TRANSITION"):
                with self.subTest(text=text, claim_type=claim_type):
                    draft, error = self.finalize(text, claim_type)
                    self.assertIsNone(draft)
                    self.assertEqual(error, "CLAIM_TYPE_CONTRACT")

    async def test_restricted_words_at_punctuation_and_normalized_boundaries(self):
        for text in ("We can help.", "OUR team", "Ask (our) team.",
                     "Ask (we) about scope.", "our", "model", "ＯＵＲ team",
                     "Review material\ncode.", "Review port\tsize."):
            with self.subTest(text=text):
                draft, error = self.finalize(text, "CALL_TO_ACTION")
                self.assertIsNone(draft)
                self.assertEqual(error, "CLAIM_TYPE_CONTRACT")

    async def test_second_person_does_not_bypass_other_contracts(self):
        for text in ("Review your 7300 rpm application.", "Review your best option."):
            with self.subTest(text=text):
                draft, error = self.finalize(text, "CALL_TO_ACTION")
                self.assertIsNone(draft)
                self.assertEqual(error, "CLAIM_TYPE_CONTRACT")
