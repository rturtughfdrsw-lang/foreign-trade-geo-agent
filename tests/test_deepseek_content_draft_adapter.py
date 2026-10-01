import json
import os
import unittest
from unittest.mock import patch

import httpx

from foreign_trade_geo_agent.adapters.deepseek_content_draft import (
    DeepSeekContentDraftWriter,
    content_draft_request_payload,
)
from foreign_trade_geo_agent.core.content_draft import (
    MAX_INPUT_ENVELOPE_BYTES,
    MAX_INPUT_ENVELOPE_CHARS,
    MAX_PROVIDER_TOKENS,
    MAX_RAW_OUTPUT_CHARS,
    MAX_SYSTEM_PROMPT_BYTES,
    MAX_SYSTEM_PROMPT_CHARS,
    MAX_USER_MATERIAL_BYTES,
    MAX_USER_MATERIAL_CHARS,
    ContentDraftGenerationStatus,
    ContentDraftInput,
    build_content_draft_prompt,
)
from foreign_trade_geo_agent.core.content_opportunity import ContentOpportunityActionCode
from foreign_trade_geo_agent.workflows.change_plan import ChangePlanWorkflow
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


async def _make_prompt():
    site = packet(page("P1"))
    report = opportunity_report(
        opportunity(action_codes=(ContentOpportunityActionCode.EXPAND_PAGE_SECTION,))
    )
    plan = await ChangePlanWorkflow(
        ChangePlanFakeWriter(generated([expand()]))
    ).run(site, report)
    value = ContentDraftInput(site, report, plan)
    return build_content_draft_prompt(value, "C1")


def _response(content, finish_reason="stop"):
    return httpx.Response(
        200,
        json={
            "choices": [
                {"message": {"content": content}, "finish_reason": finish_reason}
            ]
        },
    )


class DeepSeekContentDraftWriterTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_key_fails_before_http(self) -> None:
        calls = []

        def handler(request):
            calls.append(request)
            raise AssertionError("HTTP must not be called without a key")

        prompt = await _make_prompt()
        with patch.dict(os.environ, {}, clear=True):
            writer = DeepSeekContentDraftWriter(transport=httpx.MockTransport(handler))
            result = await writer.write_content_draft(prompt)
        self.assertEqual(result.status, ContentDraftGenerationStatus.FAILED)
        self.assertIn("DEEPSEEK_API_KEY", result.error or "")
        self.assertEqual(calls, [])

    async def test_one_request_uses_injected_transport_and_fixed_schema(self) -> None:
        requests = []
        content = json.dumps(
            {
                "draft": {
                    "change_ref": "C1",
                    "draft_type": "SECTION_DRAFT",
                    "blocks": [],
                }
            }
        )

        def handler(request):
            requests.append(request)
            return _response(content)

        prompt = await _make_prompt()
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "TEST_KEY"}, clear=True):
            writer = DeepSeekContentDraftWriter(transport=httpx.MockTransport(handler))
            result = await writer.write_content_draft(prompt)
        self.assertEqual(result.status, ContentDraftGenerationStatus.SUCCESS)
        self.assertEqual(result.text, content)
        self.assertEqual(len(requests), 1)
        self.assertEqual(
            str(requests[0].url), "https://api.deepseek.com/chat/completions"
        )
        body = json.loads(requests[0].content)
        self.assertEqual(body["model"], "deepseek-flash")
        self.assertEqual(body["max_tokens"], MAX_PROVIDER_TOKENS)
        self.assertEqual(len(body["messages"]), 2)

    async def test_strict_finish_reason(self) -> None:
        content = json.dumps(
            {"draft": {"change_ref": "C1", "draft_type": "SECTION_DRAFT", "blocks": []}}
        )
        prompt = await _make_prompt()
        for finish_reason in ("length", "tool_calls", None):
            def handler(request, finish_reason=finish_reason):
                return _response(content, finish_reason)

            with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "TEST_KEY"}, clear=True):
                writer = DeepSeekContentDraftWriter(
                    transport=httpx.MockTransport(handler)
                )
                result = await writer.write_content_draft(prompt)
            self.assertEqual(result.status, ContentDraftGenerationStatus.FAILED)
            self.assertIsNone(result.text)

    async def test_oversized_raw_output_fails(self) -> None:
        prompt = await _make_prompt()
        big = "x" * (MAX_RAW_OUTPUT_CHARS + 1)

        def handler(request):
            return _response(big)

        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "TEST_KEY"}, clear=True):
            writer = DeepSeekContentDraftWriter(transport=httpx.MockTransport(handler))
            result = await writer.write_content_draft(prompt)
        self.assertEqual(result.status, ContentDraftGenerationStatus.FAILED)
        self.assertIn("budget", result.error or "")

    async def test_http_error_is_sanitized_and_single_call(self) -> None:
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(500, text="secret-internal-body")

        prompt = await _make_prompt()
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "TEST_KEY"}, clear=True):
            writer = DeepSeekContentDraftWriter(transport=httpx.MockTransport(handler))
            result = await writer.write_content_draft(prompt)
        self.assertEqual(result.status, ContentDraftGenerationStatus.FAILED)
        self.assertIn("HTTP 500", result.error or "")
        self.assertNotIn("secret-internal-body", result.error or "")
        self.assertEqual(len(calls), 1)

    async def test_malformed_response_body_fails(self) -> None:
        prompt = await _make_prompt()

        def handler(request):
            return httpx.Response(200, text="not-json")

        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "TEST_KEY"}, clear=True):
            writer = DeepSeekContentDraftWriter(transport=httpx.MockTransport(handler))
            result = await writer.write_content_draft(prompt)
        self.assertEqual(result.status, ContentDraftGenerationStatus.FAILED)

    def test_timeout_is_finite_positive_bounded(self) -> None:
        with self.assertRaises(ValueError):
            DeepSeekContentDraftWriter(timeout=0)
        with self.assertRaises(ValueError):
            DeepSeekContentDraftWriter(timeout=121.0)
        self.assertEqual(DeepSeekContentDraftWriter(timeout=30.0)._timeout, 30.0)

    def test_max_tokens_constant(self) -> None:
        self.assertEqual(DeepSeekContentDraftWriter.max_output_tokens, MAX_PROVIDER_TOKENS)

    async def test_utf8_multibyte_bytes_bound(self) -> None:
        prompt = await _make_prompt()
        # 12000 CJK chars stay under the char bound but exceed the UTF-8 byte bound.
        content = "中" * 12_000

        def handler(request):
            return _response(content)

        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "TEST_KEY"}, clear=True):
            writer = DeepSeekContentDraftWriter(transport=httpx.MockTransport(handler))
            result = await writer.write_content_draft(prompt)
        self.assertEqual(result.status, ContentDraftGenerationStatus.FAILED)
        self.assertIn("budget", result.error or "")

    async def test_worst_case_prompt_and_envelope_fit(self) -> None:
        base_body = "chemical compatibility material selection port size application maintenance considerations "
        body = (base_body * 12)[:590]
        source_text = (
            "aodd pump technical specifications buyer guidance comparison " * 12
        )[:740]
        site = packet(
            page("P1", body=body),
            page("P2", body=body),
            page("P3", body=body),
        )
        report = opportunity_report(
            opportunity(
                "R1",
                action_codes=(ContentOpportunityActionCode.EXPAND_PAGE_SECTION,),
                page_refs=("P1", "P2", "P3"),
                source_refs=("S1", "S2", "S3", "S4"),
            ),
            source_text=source_text,
        )
        raw = expand(
            page_refs=["P1", "P2", "P3"],
            source_refs=["S1", "S2", "S3", "S4"],
        )
        plan = await ChangePlanWorkflow(
            ChangePlanFakeWriter(generated([raw]))
        ).run(site, report)
        value = ContentDraftInput(site, report, plan)
        prompt = build_content_draft_prompt(value, "C1")

        system = DeepSeekContentDraftWriter.build_system_prompt()
        material = prompt.material_json()
        envelope = json.dumps(
            content_draft_request_payload(system, material),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        self.assertLessEqual(len(system), MAX_SYSTEM_PROMPT_CHARS)
        self.assertLessEqual(len(system.encode("utf-8")), MAX_SYSTEM_PROMPT_BYTES)
        self.assertLessEqual(len(material), MAX_USER_MATERIAL_CHARS)
        self.assertLessEqual(len(material.encode("utf-8")), MAX_USER_MATERIAL_BYTES)
        self.assertLessEqual(len(envelope), MAX_INPUT_ENVELOPE_CHARS)
        self.assertLessEqual(len(envelope.encode("utf-8")), MAX_INPUT_ENVELOPE_BYTES)


if __name__ == "__main__":
    unittest.main()
