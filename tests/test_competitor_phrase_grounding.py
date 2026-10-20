"""Capitalization alone must not reject recombined first-party terminology."""
import unittest
from dataclasses import replace

from foreign_trade_geo_agent.core.content_draft import _has_competitor_mention
from foreign_trade_geo_agent.workflows.content_draft import ContentDraftWorkflow
from tests.test_content_draft_competitor_diagnostic import response
from tests.test_content_draft_workflow import _DraftFakeWriter, _expand_input


class CompetitorPhraseGroundingTests(unittest.TestCase):
    def test_recombined_observed_terms_are_not_new_brands(self):
        for phrase, evidence in (
            ('Stainless Steel', 'Stainless components with steel construction.'),
            ('Quality Control', 'Quality checks support process control.'),
            ('CNC Turning Centers', 'CNC machines include turning and machining centers.'),
            ('The DN Solutions', 'DN Solutions supplies the equipment.'),
        ):
            with self.subTest(phrase=phrase):
                self.assertIsNone(_has_competitor_mention(phrase, first_party_text=evidence))

    def test_unknown_brand_is_still_rejected_even_beside_grounded_terms(self):
        evidence = 'Quality checks support control. Stainless components use steel. Pumps are available.'
        for phrase, expected in (
            ('Rival Pumps', 'Rival Pumps'),
            ('Quality Control by Acme Pumps', 'Acme Pumps'),
            ('Stainless Steel Rival Pumps', 'Stainless Steel Rival Pumps'),
            ('Steel Works', 'Steel Works'),
        ):
            with self.subTest(phrase=phrase):
                self.assertEqual(_has_competitor_mention(phrase, first_party_text=evidence), expected)

    def test_substrings_do_not_ground_new_words(self):
        self.assertEqual(_has_competitor_mention('Rival Pumps',
            first_party_text='Unrivalled pumps'), 'Rival Pumps')

    def test_arbitrary_observed_words_do_not_allow_a_new_company_name(self):
        self.assertEqual(_has_competitor_mention('General Electric',
            first_party_text='General guidance for electric machines.'), 'General Electric')


class CompetitorPhraseWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_grounded_recombination_passes_without_provider_retry(self):
        value = await _expand_input()
        pages = value.site_content.pages
        first = replace(pages[0], body_text=pages[0].body_text +
                        ' Quality checks support process control.')
        value = replace(value, site_content=replace(value.site_content, pages=(first, *pages[1:])))
        writer = _DraftFakeWriter([response('Quality Control supports material selection.')])
        workflow = ContentDraftWorkflow(writer, max_repair_attempts=0)
        report = await workflow.run(value)
        self.assertIsNone(report.error)
        self.assertTrue(report.drafts)
        self.assertEqual(writer.calls, 1)
        self.assertIsNone(workflow.last_competitor_mention_violation)
