from dataclasses import replace
import unittest

from foreign_trade_geo_agent.core.extraction import PageExtractionStatus
from foreign_trade_geo_agent.core.research_query import build_research_query
from tests.test_end_to_end_workflow import crawl_report, failed_crawled_page


class ResearchQueryTests(unittest.TestCase):
    def test_query_uses_hostname_first_successful_title_h1_and_goal(self) -> None:
        first_success = replace(
            crawl_report().pages[0],
            title="Industrial Pumps",
            h1=("Chemical Pumps", "Ignored second heading"),
        )
        report = replace(
            crawl_report(),
            pages=(failed_crawled_page(), first_success),
        )

        query = build_research_query(
            report,
            "Improve organic search visibility",
        )

        self.assertEqual(
            query,
            "example.com | title: Industrial Pumps | h1: Chemical Pumps | "
            "goal: Improve organic search visibility",
        )

    def test_query_omits_missing_fields_and_is_bounded_to_300_chars(self) -> None:
        page = replace(
            crawl_report().pages[0],
            title=None,
            h1=(),
            extraction_status=PageExtractionStatus.SUCCESS,
        )

        query = build_research_query(
            replace(crawl_report(), pages=(page,)),
            "g" * 500,
        )

        self.assertNotIn("title:", query)
        self.assertNotIn("h1:", query)
        self.assertTrue(query.startswith("example.com | goal: "))
        self.assertEqual(len(query), 300)


if __name__ == "__main__":
    unittest.main()
