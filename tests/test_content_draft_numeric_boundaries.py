"""Offline numeric boundaries and replay of the immutable synthetic model article."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest

from foreign_trade_geo_agent.core import content_draft as cd
from foreign_trade_geo_agent.core.history import ArtifactType
from foreign_trade_geo_agent.storage.serialization import decode_artifact
from foreign_trade_geo_agent.workflows.content_draft import _parse_specification


FIXTURE = Path(__file__).parent / "fixtures/content_draft_numeric_article"


class NumericBoundaryTests(unittest.TestCase):
    def test_certificate_and_date_do_not_consume_following_prose(self):
        text = "Certificate ACME-CNC-1 was issued under STD-2026 for X7; expires 2027-01-01, and is synthetic."
        self.assertEqual(cd.extract_numeric_expressions(text),
                         ("acme-cnc-1", "std-2026", "x7", "2027-01-01"))
        self.assertIsNone(cd._validate_numeric_grounding(text, cd._normalized_text(
            "Certificate ACME-CNC-1; STD-2026; X7; expires 2027-01-01; synthetic.")))

    def test_sentence_punctuation_is_not_part_of_numeric_token(self):
        self.assertEqual(cd.extract_numeric_expressions("Date 2027-01-01. Pressure 10, then stop."),
                         ("2027-01-01", "10"))

    def test_identifier_and_date_normalization_preserves_facts(self):
        self.assertEqual(cd.extract_numeric_expressions("Model ＡＸ７ was tested; date ２０２７/０１/０１, and valid."),
                         ("ax7", "2027/01/01"))
        self.assertIsNone(cd._validate_numeric_grounding("AX7 was tested; date 2027/01/01.",
                         cd._normalized_text("Model ax7; date 2027/01/01;")))

    def test_units_fractions_and_tolerances_keep_exact_values_and_spacing(self):
        for expression in ("10bar", "20°C", "100 L/min", "0.02 mm", "+/-0.02 mm", "50%", '1/2"', "1-1/2"):
            with self.subTest(expression=expression):
                self.assertIsNone(cd._validate_numeric_grounding(
                    expression, cd._normalized_text(expression)))
        for text, evidence in (("10 bar", "10bar"), ("20°C", "20° C"),
                               ("10 m", "10 mm"), ("0.02 mm", "0.02 cm"),
                               ("+/-0.02 mm", "+/-0.03 mm")):
            with self.subTest(text=text, evidence=evidence):
                self.assertEqual(cd._validate_numeric_grounding(text, cd._normalized_text(evidence)),
                                 "NUMERIC_NOT_GROUNDED")

    def test_changed_identifiers_dates_and_embedded_suffixes_fail(self):
        for text, evidence in (("ACME-CNC-2", "ACME-CNC-1; TEST-2"),
                               ("STD-2028", "STD-2026"), ("X8", "X7"),
                               ("2027-01-02", "2027-01-01"),
                               ("2027-01-01", "2027-01-01-2"),
                               ("2027-01-01", "2027-01-01/2"),
                               ("CNC-1", "ACME-CNC-1"),
                               ("X7", "X70"), ("X7", "AX7"),
                               ("10 bar", "110 bar"), ("5 bar", "0.5 bar")):
            with self.subTest(text=text, evidence=evidence):
                self.assertEqual(cd._validate_numeric_grounding(text, cd._normalized_text(evidence)),
                                 "NUMERIC_NOT_GROUNDED")

    def test_unsupported_bare_numbers_are_never_skipped(self):
        for text in ("42", "42.", "42,", "3.14"):
            for evidence in ("", cd._normalized_text(text)):
                with self.subTest(text=text, evidence=evidence):
                    self.assertEqual(cd._validate_numeric_grounding(text, evidence),
                                     "NUMERIC_NOT_GROUNDED")


class FrozenArticleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = (FIXTURE / "model-output.txt").read_text(encoding="utf-8")
        cls.value = cd.ContentDraftInput(*(decode_artifact(kind, 1, (FIXTURE / name).read_text(encoding="utf-8"))
            for kind, name in ((ArtifactType.SITE_CONTENT, "site-content.json"),
                               (ArtifactType.CONTENT_OPPORTUNITY, "opportunities.json"),
                               (ArtifactType.CHANGE_PLAN, "change-plan.json"))))

    def finalize(self, raw=None):
        op = self.value.change_plan_report.operations[0]
        spec = _parse_specification(self.text if raw is None else json.dumps(raw),
                                    expected_change_ref=op.change_id, operation=op)
        return cd.finalize_draft_item(1, spec, op, self.value.opportunity_report.opportunities[0],
                                     self.value.site_content, self.value.opportunity_report)

    def test_exact_frozen_response_passes_parser_and_finalizer_but_requires_review(self):
        self.assertEqual(hashlib.sha256((FIXTURE / "model-output.txt").read_bytes()).hexdigest(),
                         "9776fb2b6e9788f0d6198f4bce4ebb59d19bb5b348619b3098d6bc33ad08d179")
        self.assertIsNone(cd.stable_content_draft_input_error(self.value))
        draft, error = self.finalize()
        self.assertIsNone(error)
        self.assertTrue(draft.requires_human_review)
        self.assertEqual(draft.section_block_counts, (2, 3))
        self.assertEqual(sum(len(b.claims) for b in draft.blocks), 13)

    def test_actual_failing_claim_extracts_complete_certificate_standard_and_date(self):
        claim = json.loads(self.text)["draft"]["sections"][1]["blocks"][1]["claims"][1]
        self.assertEqual(cd.extract_numeric_expressions(claim["text"]),
                         ("demo-cnc-1", "demo-2026", "2027-01-01"))

    def test_article_mutations_cannot_borrow_other_numeric_facts(self):
        for old, new in (("8000 rpm", "9000 rpm"), ("+/-0.02 mm", "+/-0.03 mm"),
                         ("20 C", "21 C"), ("DEMO-CNC-1", "DEMO-CNC-2"),
                         ("DEMO-2026", "DEMO-2028"), ("2027-01-01", "2027-01-02"),
                         ("DEMO-TEST-2", "DEMO-TEST-1")):
            with self.subTest(old=old, new=new):
                raw = json.loads(self.text.replace(old, new))
                self.assertEqual(self.finalize(raw)[1], "NUMERIC_NOT_GROUNDED")

    def test_ps_reference_integrity_is_unchanged(self):
        original = json.loads(self.text)
        for field, refs, expected in (("page_refs", ["P999"], "UNKNOWN_PAGE_REFERENCE"),
                                      ("source_refs", ["S999"], "UNKNOWN_SOURCE_REFERENCE"),
                                      ("page_refs", [], "FIRST_PARTY_FACT_WITHOUT_PAGE")):
            with self.subTest(field=field, refs=refs):
                raw = deepcopy(original)
                raw["draft"]["sections"][0]["blocks"][0]["claims"][1][field] = refs
                self.assertEqual(self.finalize(raw)[1], expected)


if __name__ == "__main__":
    unittest.main()
