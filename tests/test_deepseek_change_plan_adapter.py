import json
import os
import unittest
from unittest.mock import patch

import httpx

from foreign_trade_geo_agent.core import change_plan as change_plan_contract

from foreign_trade_geo_agent.adapters.deepseek_change_plan import (
    DeepSeekChangePlanWriter,
)
from foreign_trade_geo_agent.core.change_plan import (
    MAX_CHANGE_PLAN_TIMEOUT_SECONDS,
    MAX_INPUT_ENVELOPE_BYTES,
    MAX_INPUT_ENVELOPE_CHARS,
    MAX_PROVIDER_TOKENS,
    MAX_RAW_OUTPUT_BYTES,
    MAX_RAW_OUTPUT_CHARS,
    MAX_SYSTEM_PROMPT_BYTES,
    MAX_SYSTEM_PROMPT_CHARS,
    MAX_ANCHOR_INTENT_CHARS,
    MAX_CONTENT_POINT_SUBJECT_CHARS,
    MAX_CONTENT_POINTS_PER_OPERATION,
    MAX_OPERATIONS,
    MAX_OPERATIONS_PER_OPPORTUNITY,
    MAX_OUTLINE_HEADING_CHARS,
    MAX_OUTLINE_HEADINGS,
    MAX_PAGE_REFS_PER_OPERATION,
    MAX_PROPOSED_HEADING_CHARS,
    MAX_REORDER_HEADINGS,
    MAX_SOURCE_REFS_PER_OPERATION,
    MAX_TABLE_COLUMNS,
    MAX_TABLE_DIMENSIONS,
    MAX_TABLE_LABEL_CHARS,
    MIN_OUTLINE_HEADINGS,
    MIN_REORDER_HEADINGS,
    MIN_TABLE_COLUMNS,
    MIN_TABLE_DIMENSIONS,
    ChangePlanGenerationStatus,
    ChangePlanInput,
    build_change_plan_prompt,
)
from foreign_trade_geo_agent.core.change_plan import ChangePlanStatus
from foreign_trade_geo_agent.core.extraction import (
    StructuredContentBlock,
    StructuredContentKind,
)
from foreign_trade_geo_agent.workflows.change_plan import ChangePlanWorkflow
from tests.test_change_plan_workflow import opportunity, opportunity_report, packet, page


DUMMY_API_KEY = "test-key-never-send"


def prompt():
    return build_change_plan_prompt(ChangePlanInput(packet(), opportunity_report()))


def completion(content: str, finish_reason: str = "stop") -> dict[str, object]:
    return {
        "choices": [
            {"message": {"content": content}, "finish_reason": finish_reason}
        ]
    }


def escape_heavy_input():
    noise = '\\"' * 170
    pages = tuple(
        page(
            f"P{index}",
            body="chemical compatibility " + noise,
            structured=(
                StructuredContentBlock(
                    StructuredContentKind.SECTION,
                    heading=f"Technical Evidence {index}",
                    text="chemical compatibility " + noise,
                ),
                StructuredContentBlock(
                    StructuredContentKind.SECTION,
                    heading=f"Buyer Evidence {index}",
                    text="material selection " + noise,
                ),
            ),
        )
        for index in range(1, 6)
    )
    opportunities = tuple(
        opportunity(
            f"R{index}",
            page_refs=tuple(f"P{page_index}" for page_index in range(1, 6)),
            source_refs=tuple(f"S{source_index}" for source_index in range(1, 5)),
        )
        for index in range(1, 5)
    )
    report = opportunity_report(
        *opportunities,
        source_text="chemical compatibility material selection " + noise,
    )
    return packet(*pages), report


class DeepSeekChangePlanWriterTests(unittest.IsolatedAsyncioTestCase):
    def test_system_prompt_has_bounded_schema_compatibility_and_review_contract(self) -> None:
        rendered = DeepSeekChangePlanWriter.build_system_prompt()
        self.assertIn("Allowed operation_type values by source_action_code:", rendered)
        self.assertIn("EXACT_OBSERVED_HEADING", rendered)
        self.assertIn("comparison_table_brief", rendered)
        self.assertIn("resource_purpose", rendered)
        self.assertNotIn("page_purpose", rendered)
        self.assertIn(f"at most {MAX_OPERATIONS} items", rendered)
        self.assertIn(
            f"at most {MAX_OPERATIONS_PER_OPPORTUNITY} items",
            rendered,
        )
        self.assertIn("require human review", rendered)
        self.assertIn("observed_present_only", rendered)
        for forbidden in ("risk enum", "proposed slug", "DOM selector", "XPath"):
            self.assertNotIn(forbidden, rendered)
        self.assertLessEqual(len(rendered), MAX_SYSTEM_PROMPT_CHARS)
        self.assertLessEqual(len(rendered.encode("utf-8")), MAX_SYSTEM_PROMPT_BYTES)

    def test_system_prompt_bounds_are_rendered_from_core_contract(self) -> None:
        required_minimums = (
            "MIN_CONTENT_POINTS_PER_OPERATION",
            "MIN_PAGE_REFS_PER_OPERATION",
            "MIN_SOURCE_REFS_PER_OPERATION",
            "MIN_EXISTING_PAGE_REFS_PER_OPERATION",
            "MIN_INTERNAL_LINK_PAGE_REFS",
            "REORDER_PAGE_REFS",
        )
        for name in required_minimums:
            self.assertTrue(hasattr(change_plan_contract, name), name)
        self.assertTrue(hasattr(change_plan_contract, "render_change_plan_bounds"))

        minimum_points = change_plan_contract.MIN_CONTENT_POINTS_PER_OPERATION
        minimum_page_refs = change_plan_contract.MIN_PAGE_REFS_PER_OPERATION
        minimum_source_refs = change_plan_contract.MIN_SOURCE_REFS_PER_OPERATION
        minimum_existing_page_refs = (
            change_plan_contract.MIN_EXISTING_PAGE_REFS_PER_OPERATION
        )
        minimum_internal_link_refs = (
            change_plan_contract.MIN_INTERNAL_LINK_PAGE_REFS
        )
        reorder_page_refs = change_plan_contract.REORDER_PAGE_REFS
        bounds = change_plan_contract.render_change_plan_bounds()
        expected_fragments = (
            f"page_refs: {minimum_page_refs} to {MAX_PAGE_REFS_PER_OPERATION}",
            f"source_refs: {minimum_source_refs} to {MAX_SOURCE_REFS_PER_OPERATION}",
            f"existing-page operations require at least {minimum_existing_page_refs} page_ref",
            f"internal links require at least {minimum_internal_link_refs} page_refs",
            f"content_points: {minimum_points} to {MAX_CONTENT_POINTS_PER_OPERATION}",
            f"content point subject: at most {MAX_CONTENT_POINT_SUBJECT_CHARS} characters",
            f"proposed heading or title: at most {MAX_PROPOSED_HEADING_CHARS} characters",
            f"ordered_headings: {MIN_REORDER_HEADINGS} to {MAX_REORDER_HEADINGS}",
            f"ordered heading: at most {MAX_PROPOSED_HEADING_CHARS} characters",
            f"outline_headings: {MIN_OUTLINE_HEADINGS} to {MAX_OUTLINE_HEADINGS}",
            f"outline heading: at most {MAX_OUTLINE_HEADING_CHARS} characters",
            f"table columns: {MIN_TABLE_COLUMNS} to {MAX_TABLE_COLUMNS}",
            f"table dimensions: {MIN_TABLE_DIMENSIONS} to {MAX_TABLE_DIMENSIONS}",
            f"table label: at most {MAX_TABLE_LABEL_CHARS} characters",
            f"anchor_intent: at most {MAX_ANCHOR_INTENT_CHARS} characters",
            f"suggested_source_page_refs: {minimum_page_refs} to {MAX_PAGE_REFS_PER_OPERATION}",
            f"PROPOSE_SECTION_REORDER requires exactly {reorder_page_refs} page_ref",
        )
        for fragment in expected_fragments:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, bounds)
        self.assertIn(bounds, DeepSeekChangePlanWriter.build_system_prompt())

    async def test_valid_escape_heavy_envelope_overflow_is_input_too_large(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(200, json=completion('{"operations":[]}'))

        site, report = escape_heavy_input()
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": DUMMY_API_KEY}, clear=True):
            writer = DeepSeekChangePlanWriter(transport=httpx.MockTransport(handler))
            result = await ChangePlanWorkflow(writer).run(site, report)

        self.assertEqual(result.status, ChangePlanStatus.INPUT_TOO_LARGE)
        self.assertEqual(result.error, "INPUT_TOO_LARGE")
        self.assertEqual(result.operations, ())
        self.assertEqual(calls, 0)

    async def test_envelope_overflow_precedes_missing_key_failure(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(200, json=completion('{"operations":[]}'))

        site, report = escape_heavy_input()
        with patch.dict(os.environ, {}, clear=True):
            writer = DeepSeekChangePlanWriter(transport=httpx.MockTransport(handler))
            result = await ChangePlanWorkflow(writer).run(site, report)

        self.assertEqual(result.status, ChangePlanStatus.INPUT_TOO_LARGE)
        self.assertEqual(result.error, "INPUT_TOO_LARGE")
        self.assertEqual(result.operations, ())
        self.assertEqual(calls, 0)

    async def test_missing_key_fails_before_http(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(200, json=completion('{"operations":[]}'))

        with patch.dict(os.environ, {}, clear=True):
            result = await DeepSeekChangePlanWriter(
                transport=httpx.MockTransport(handler)
            ).write_change_plan(prompt())
        self.assertEqual(result.status, ChangePlanGenerationStatus.FAILED)
        self.assertEqual(calls, 0)

    async def test_one_request_uses_injected_transport_and_fixed_schema(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, json=completion('{"operations":[]}'))

        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": DUMMY_API_KEY}, clear=True):
            result = await DeepSeekChangePlanWriter(
                transport=httpx.MockTransport(handler)
            ).write_change_plan(prompt())
        self.assertEqual(result.status, ChangePlanGenerationStatus.SUCCESS)
        self.assertEqual(len(requests), 1)
        payload = json.loads(requests[0].content)
        self.assertEqual(payload["model"], "deepseek-flash")
        self.assertEqual(payload["max_tokens"], MAX_PROVIDER_TOKENS)
        self.assertEqual(payload["thinking"], {"type": "disabled"})
        self.assertEqual(len(payload["messages"]), 2)
        self.assertEqual(requests[0].headers["Authorization"], f"Bearer {DUMMY_API_KEY}")
        self.assertNotIn("final_url", payload["messages"][1]["content"])

    async def test_final_request_envelope_fits_hard_limits(self) -> None:
        captured: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured.update(json.loads(request.content))
            return httpx.Response(200, json=completion('{"operations":[]}'))

        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": DUMMY_API_KEY}, clear=True):
            result = await DeepSeekChangePlanWriter(
                transport=httpx.MockTransport(handler)
            ).write_change_plan(prompt())
        envelope = json.dumps(captured, ensure_ascii=False, separators=(",", ":"))
        self.assertEqual(result.status, ChangePlanGenerationStatus.SUCCESS)
        self.assertLessEqual(len(envelope), MAX_INPUT_ENVELOPE_CHARS)
        self.assertLessEqual(len(envelope.encode("utf-8")), MAX_INPUT_ENVELOPE_BYTES)

    async def test_oversized_user_material_fails_before_http(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(200, json=completion('{"operations":[]}'))

        oversized_prompt = prompt()
        oversized_page = oversized_prompt.input.site_content.pages[0]
        oversized_page = __import__("dataclasses").replace(
            oversized_page, body_text="chemical compatibility " * 2_000
        )
        oversized_packet = __import__("dataclasses").replace(
            oversized_prompt.input.site_content,
            pages=(oversized_page,),
            source_page_count=1,
        )
        oversized_prompt = build_change_plan_prompt(
            ChangePlanInput(oversized_packet, oversized_prompt.input.opportunities)
        )
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": DUMMY_API_KEY}, clear=True):
            result = await DeepSeekChangePlanWriter(
                transport=httpx.MockTransport(handler)
            ).write_change_plan(oversized_prompt)
        self.assertEqual(result.status, ChangePlanGenerationStatus.FAILED)
        self.assertEqual(calls, 0)

    async def test_invalid_prompt_type_fails_without_http(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(200, json=completion('{"operations":[]}'))

        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": DUMMY_API_KEY}, clear=True):
            result = await DeepSeekChangePlanWriter(
                transport=httpx.MockTransport(handler)
            ).write_change_plan(object())  # type: ignore[arg-type]
        self.assertEqual(result.status, ChangePlanGenerationStatus.FAILED)
        self.assertEqual(calls, 0)

    async def test_http_and_network_failures_are_sanitized_and_not_retried(self) -> None:
        failures: tuple[object, ...] = (
            401,
            httpx.ReadTimeout("secret timeout"),
            httpx.ConnectError("secret connection"),
        )
        for failure in failures:
            calls = 0

            def handler(request: httpx.Request) -> httpx.Response:
                nonlocal calls
                calls += 1
                if isinstance(failure, int):
                    return httpx.Response(failure, json={"secret": DUMMY_API_KEY})
                failure.request = request
                raise failure

            with self.subTest(failure=type(failure).__name__):
                with patch.dict(os.environ, {"DEEPSEEK_API_KEY": DUMMY_API_KEY}, clear=True):
                    result = await DeepSeekChangePlanWriter(
                        transport=httpx.MockTransport(handler)
                    ).write_change_plan(prompt())
                self.assertEqual(result.status, ChangePlanGenerationStatus.FAILED)
                self.assertEqual(calls, 1)
                self.assertNotIn("secret", (result.error or "").casefold())
                self.assertNotIn(DUMMY_API_KEY, result.error or "")

    async def test_length_finish_reason_fails_without_using_partial_output(self) -> None:
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": DUMMY_API_KEY}, clear=True):
            result = await DeepSeekChangePlanWriter(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(
                        200,
                        json=completion('{"operations":[', finish_reason="length"),
                    )
                )
            ).write_change_plan(prompt())
        self.assertEqual(result.status, ChangePlanGenerationStatus.FAILED)
        self.assertIn("truncated", (result.error or "").casefold())

    async def test_only_stop_finish_reason_is_accepted(self) -> None:
        for finish_reason in (None, "unknown", "tool_calls"):
            payload = completion('{"operations":[]}', finish_reason="stop")
            payload["choices"][0]["finish_reason"] = finish_reason
            with self.subTest(finish_reason=finish_reason):
                with patch.dict(os.environ, {"DEEPSEEK_API_KEY": DUMMY_API_KEY}, clear=True):
                    result = await DeepSeekChangePlanWriter(
                        transport=httpx.MockTransport(
                            lambda request, value=payload: httpx.Response(200, json=value)
                        )
                    ).write_change_plan(prompt())
                self.assertEqual(result.status, ChangePlanGenerationStatus.FAILED)

    async def test_non_string_finish_reason_is_malformed_shape(self) -> None:
        payload = completion('{"operations":[]}')
        payload["choices"][0]["finish_reason"] = 42
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": DUMMY_API_KEY}, clear=True):
            result = await DeepSeekChangePlanWriter(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(200, json=payload)
                )
            ).write_change_plan(prompt())
        self.assertEqual(result.status, ChangePlanGenerationStatus.FAILED)

    async def test_timeout_error_is_sanitized_and_single_call(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            error = httpx.ReadTimeout("secret timeout detail")
            error.request = request
            raise error

        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": DUMMY_API_KEY}, clear=True):
            result = await DeepSeekChangePlanWriter(
                timeout=0.01,
                transport=httpx.MockTransport(handler),
            ).write_change_plan(prompt())
        self.assertEqual(result.status, ChangePlanGenerationStatus.FAILED)
        self.assertEqual(calls, 1)
        self.assertNotIn("secret", result.error or "")
        self.assertNotIn("0.01", result.error or "")

    def test_timeout_configuration_is_positive(self) -> None:
        for value in (
            0,
            -1,
            "30",
            float("nan"),
            float("inf"),
            MAX_CHANGE_PLAN_TIMEOUT_SECONDS + 1,
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    DeepSeekChangePlanWriter(timeout=value)  # type: ignore[arg-type]

    async def test_malformed_response_shapes_fail_safely(self) -> None:
        responses = (
            httpx.Response(200, content=b"not-json", headers={"Content-Type": "application/json"}),
            httpx.Response(200, json={"choices": []}),
            httpx.Response(200, json=completion("   ")),
            httpx.Response(200, json={"choices": [{"message": {"content": 42}}]}),
        )
        for response in responses:
            with self.subTest(content=response.content):
                with patch.dict(os.environ, {"DEEPSEEK_API_KEY": DUMMY_API_KEY}, clear=True):
                    result = await DeepSeekChangePlanWriter(
                        transport=httpx.MockTransport(
                            lambda request, value=response: value
                        )
                    ).write_change_plan(prompt())
                self.assertEqual(result.status, ChangePlanGenerationStatus.FAILED)

    async def test_character_and_utf8_byte_response_bounds_are_independent(self) -> None:
        outputs = (
            "x" * (MAX_RAW_OUTPUT_CHARS + 1),
            "泵" * (MAX_RAW_OUTPUT_BYTES // 3 + 1),
        )
        for output in outputs:
            with self.subTest(chars=len(output), bytes=len(output.encode("utf-8"))):
                with patch.dict(os.environ, {"DEEPSEEK_API_KEY": DUMMY_API_KEY}, clear=True):
                    result = await DeepSeekChangePlanWriter(
                        transport=httpx.MockTransport(
                            lambda request, value=output: httpx.Response(
                                200, json=completion(value)
                            )
                        )
                    ).write_change_plan(prompt())
                self.assertEqual(result.status, ChangePlanGenerationStatus.FAILED)

    async def test_raw_provider_output_is_not_logged(self) -> None:
        raw_secret = '{"operations":[],"secret":"never log this"}'
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": DUMMY_API_KEY}, clear=True):
            with self.assertLogs("httpx", level="INFO") as captured:
                await DeepSeekChangePlanWriter(
                    transport=httpx.MockTransport(
                        lambda request: httpx.Response(200, json=completion(raw_secret))
                    )
                ).write_change_plan(prompt())
        self.assertNotIn(raw_secret, "\n".join(captured.output))
        self.assertNotIn("never log this", "\n".join(captured.output))


if __name__ == "__main__":
    unittest.main()
