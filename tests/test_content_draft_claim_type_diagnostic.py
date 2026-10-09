"""Claim-type failures expose bounded metadata without generated copy."""

from dataclasses import asdict, replace
import json
from types import SimpleNamespace
import unittest

from foreign_trade_geo_agent.cli import _plan_validation_diagnostic
from foreign_trade_geo_agent.core.history import RunStatus
from foreign_trade_geo_agent.core.orchestration import EndToEndStage
from foreign_trade_geo_agent.workflows.content_draft import ContentDraftWorkflow
from foreign_trade_geo_agent.workflows.run_diagnostics import RunDiagnosticContext
from tests.test_content_draft_workflow import (
    _DraftFakeWriter, _expand_input, _generation, _section_text,
)


def _response(*, text, claim_type, page_refs):
    payload = json.loads(_section_text())
    claim = payload["draft"]["blocks"][0]["claims"][0]
    claim.update(text=text, claim_type=claim_type, page_refs=page_refs)
    return _generation(json.dumps(payload))


class ClaimTypeDiagnosticTests(unittest.IsolatedAsyncioTestCase):
    async def test_retry_terminal_claim_type_has_exact_safe_rule_and_prior_category(self):
        writer = _DraftFakeWriter([
            _response(text="Our pump delivers 987654 GPM.",
                      claim_type="OBSERVED_PRODUCT_FACT", page_refs=["P1"]),
            _response(text="Review material selection.",
                      claim_type="CALL_TO_ACTION", page_refs=["P1"]),
        ])
        workflow = ContentDraftWorkflow(writer)
        report = await workflow.run(await _expand_input())
        self.assertEqual(report.error, "CLAIM_TYPE_CONTRACT")
        self.assertEqual(writer.calls, 2)
        violation = workflow.last_claim_type_violation
        self.assertEqual(violation.change_ref, "C1")
        self.assertEqual(violation.operation_type.value, "EXPAND_SECTION")
        self.assertEqual(violation.field_path, "draft.blocks[0].claims[0].claim_type")
        self.assertEqual(violation.rule_id, "EDITORIAL_CTA_WITH_REFS")
        self.assertEqual(violation.actual_claim_type.value, "CALL_TO_ACTION")
        self.assertEqual(violation.expected_claim_types, ())
        self.assertEqual(violation.prior_category.value, "NUMERIC_NOT_GROUNDED")
        self.assertNotIn("Review material", json.dumps(asdict(violation), default=str))
        self.assertNotIn("987654", json.dumps(asdict(violation), default=str))

        context = RunDiagnosticContext()
        context.claim_type_violation = violation
        result = SimpleNamespace(run=SimpleNamespace(status=RunStatus.FAILED),
                                 stopped_stage=EndToEndStage.CONTENT_DRAFT,
                                 terminal_report=report)
        payload = _plan_validation_diagnostic(result, SimpleNamespace(run_diagnostics=context))
        self.assertEqual(payload["field_path"], violation.field_path)
        self.assertEqual(payload["rule_id"], violation.rule_id)
        self.assertEqual(payload["prior_category"], "NUMERIC_NOT_GROUNDED")
        self.assertNotIn("Review material", json.dumps(payload))
        context.clear()
        self.assertIsNone(context.claim_type_violation)

    async def test_content_rule_and_cleared_on_next_run(self):
        writer = _DraftFakeWriter([
            _response(text="Our pump supports material selection.",
                      claim_type="EDITORIAL_TRANSITION", page_refs=[]),
            _generation(_section_text()),
        ])
        workflow = ContentDraftWorkflow(writer)
        self.assertEqual((await workflow.run(await _expand_input())).error,
                         "CLAIM_TYPE_CONTRACT")
        violation = workflow.last_claim_type_violation
        self.assertEqual(violation.rule_id, "EDITORIAL_CTA_FACTUAL_CONTENT")
        self.assertEqual(violation.actual_claim_type.value, "EDITORIAL_TRANSITION")
        self.assertTrue(violation.has_first_party_expression)
        self.assertIsNone(violation.prior_category)
        self.assertIsNone((await workflow.run(await _expand_input())).error)
        self.assertIsNone(workflow.last_claim_type_violation)

        for field, unsafe in (
            ("change_ref", "secret"),
            ("field_path", "draft.blocks[0].claims[0].secret text"),
            ("rule_id", "untrusted output"),
            ("actual_claim_type", "untrusted output"),
            ("prior_category", "untrusted output"),
            ("has_page_refs", "untrusted output"),
        ):
            with self.subTest(field=field), self.assertRaises(ValueError):
                replace(violation, **{field: unsafe})
