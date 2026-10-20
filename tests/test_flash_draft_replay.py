"""Regression for digit-leading identifiers and the unchanged second Flash response."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import unittest

from foreign_trade_geo_agent.core import content_draft as cd
from foreign_trade_geo_agent.storage.serialization import _decode
from foreign_trade_geo_agent.workflows.content_draft import inspect_candidate_output


class CompoundIdentifierTests(unittest.TestCase):
    def test_digit_leading_material_is_one_grounded_expression(self):
        for token in ('6061-T6', '7075-T6', '17-4PH', 'S45C', 'BT40', 'ISO-230-2'):
            with self.subTest(token=token):
                self.assertEqual(cd.extract_numeric_expressions(token), (token.casefold(),))
                self.assertIsNone(cd._validate_numeric_grounding(token, cd._normalized_text(token)))

    def test_identifier_match_cannot_borrow_parts_or_other_values(self):
        for text, evidence in (('7075-T6', '6061-T6'), ('6061-T7', '6061-T6'),
                ('6061-T6', '16061-T6'), ('6061-T6', '6061-T60'),
                ('6061-T6', '6061-T6-A'), ('BT50', 'BT40'), ('NCX10', 'NCX7'),
                ('ISO-230-3', 'ISO-230-2'), ('9000 rpm', '8000 rpm'),
                ('121 mm', '120 mm'), ('521 kg', '520 kg'), ('0.03 mm', '0.02 mm')):
            with self.subTest(text=text, evidence=evidence):
                self.assertEqual(cd._validate_numeric_grounding(text, cd._normalized_text(evidence)),
                                 'NUMERIC_NOT_GROUNDED')


class HistoricalFlashReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        history = root / 'docs/seo-flash-contract-quality-live-2026-10-12'
        cls.raw = (history / 'model-output.txt').read_bytes()
        cls.value = _decode(json.loads((history / 'native-input.json').read_bytes()), cd.ContentDraftInput)

    def check(self, response=None, value=None, snapshot=None):
        value = value or self.value
        raw = self.raw.decode() if response is None else json.dumps(response)
        return inspect_candidate_output(value, raw,
            current_snapshot_sha256=snapshot or value.customer_evidence.snapshot_sha256)

    def test_original_stays_rejected_after_identifier_fix_and_fact_selection_change(self):
        self.assertEqual(hashlib.sha256(self.raw).hexdigest(),
                         '04c311ca5fc7a85833f3662dd11d21a97aae00cc95a40afe2604dd5e4ba202e0')
        check = self.check()
        self.assertIsNone(check.claims[18].deterministic_error)
        self.assertEqual(check.claims[6].deterministic_error, 'NUMERIC_CONTEXT_NOT_PRESERVED')
        self.assertEqual(check.state, 'DETERMINISTICALLY_REJECTED')
        self.assertEqual(check.errors, (
            'CL7: NUMERIC_CONTEXT_NOT_PRESERVED',
            'SECTION_EVIDENCE_OUTSIDE_QUESTION: Read spindle and cutting trial evidence',
            'SECTION_FACT_OUTSIDE_QUESTION: Read spindle and cutting trial evidence',
            'SECTION_QUESTION_EVIDENCE_INCOMPLETE: Read spindle and cutting trial evidence',
            'SECTION_FACT_OUTSIDE_QUESTION: Specify representative acceptance tests',
            'SECTION_QUESTION_EVIDENCE_INCOMPLETE: Agree delivery training and support'))
        self.assertFalse(check.production_authorized)

    def test_material_and_dimension_changes_in_original_claim19_still_fail(self):
        for old, new in (('6061-T6', '7075-T6'), ('6061-T6', '6061-T7'), ('120 mm', '121 mm')):
            response = json.loads(self.raw)
            claim = response['draft']['sections'][2]['blocks'][0]['claims'][0]
            claim['text'] = claim['text'].replace(old, new)
            self.assertEqual(self.check(response).claims[18].deterministic_error, 'NUMERIC_NOT_GROUNDED')

    def test_exact_text_does_not_bypass_reference_or_snapshot_binding(self):
        for refs, expected in ((['E4.F99'], 'UNKNOWN_CUSTOMER_REFERENCE'),
                               (['E4.F02'], 'NUMERIC_NOT_GROUNDED')):
            response = deepcopy(json.loads(self.raw))
            response['draft']['sections'][2]['blocks'][0]['claims'][0]['customer_refs'] = refs
            self.assertEqual(self.check(response).claims[18].deterministic_error, expected)
        self.assertIn('STALE_EVIDENCE_SNAPSHOT', self.check(snapshot='a' * 64).errors)
        value = replace(self.value, customer_evidence=replace(self.value.customer_evidence,
                        native_scope_sha256='a' * 64))
        with self.assertRaisesRegex(ValueError, 'CUSTOMER_EVIDENCE_INVALID'):
            self.check(value=value)


if __name__ == '__main__':
    unittest.main()
