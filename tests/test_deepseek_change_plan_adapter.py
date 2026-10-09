import json
import os
import unittest
from unittest.mock import patch

import httpx

from foreign_trade_geo_agent.core import change_plan as change_plan_contract

from foreign_trade_geo_agent.adapters.deepseek_change_plan import DeepSeekChangePlanWriter
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


def completion(
    content: str,
    *,
    finish_reason: object = "stop",
) -> dict[str, object]:
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": finish_reason,
            }
        ],
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
    def test_english_request_contains_no_chinese_only_instruction(self) -> None:
        system = DeepSeekChangePlanWriter.build_system_prompt()

        self.assertIn("English", system)
        self.assertNotIn("Chinese", system)
        self.assertNotIn("中文", system)

    def test_system_prompt_has_bounded_schema_compatibility_and_review_contract(self) -> None:
        rendered = DeepSeekChangePlanWriter.build_system_prompt()
        self.assertIn("Allowed operation_type values by source_action_code:", rendered)
        self.assertIn("EXACT_OBSERVED_HEADING", rendered)
        self.assertIn("comparison_table_brief", rendered)
        self.assertIn("opportunity_operations", rendered)
        self.assertIn("primary_operation", rendered)
        self.assertIn("secondary_operation", rendered)
        self.assertIn("There is no third operation slot", rendered)
        self.assertIn("page_bindings", rendered)
        self.assertIn("suggested_source", rendered)
        self.assertIn("never output either page_refs or suggested_source_page_refs", rendered)
        self.assertIn("resource_purpose", rendered)
        self.assertIn("subject_ref", rendered)
        self.assertIn("content_point_candidates", rendered)
        self.assertIn("Never output subject", rendered)
        self.assertNotIn("page_purpose", rendered)
        self.assertIn("require human review", rendered)
        self.assertIn("observed_present_only", rendered)
        for forbidden in ("risk enum", "proposed slug", "DOM selector", "XPath"):
            self.assertNotIn(forbidden, rendered)
        self.assertLessEqual(len(rendered), MAX_SYSTEM_PROMPT_CHARS)
        self.assertLessEqual(len(rendered.encode("utf-8")), MAX_SYSTEM_PROMPT_BYTES)

    def test_system_prompt_uses_add_section_heading_candidate_ref(self) -> None:
        rendered = DeepSeekChangePlanWriter.build_system_prompt()

        self.assertIn(
            "ADD_SECTION adds only locator_ref, section_purpose, proposed_heading_ref, content_points",
            rendered,
        )
        self.assertIn("selected proposed_heading_ref", rendered)
        self.assertNotIn("section_purpose, proposed_heading, content_points", rendered)

    def test_new_resource_schema_omits_provider_generated_outline(self) -> None:
        rendered = DeepSeekChangePlanWriter.build_system_prompt()

        self.assertIn(
            "CREATE_NEW_RESOURCE adds only page_bindings, resource_purpose, proposed_title, content_points, comparison_table_brief",
            rendered,
        )
        self.assertIn(
            "Python deterministically materializes exactly two outline_headings",
            rendered,
        )
        self.assertNotIn("proposed_title, outline_headings, content_points", rendered)

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
            f"content point subject candidate: at most {MAX_CONTENT_POINT_SUBJECT_CHARS} characters",
            f"proposed heading or title: at most {MAX_PROPOSED_HEADING_CHARS} characters",
            f"ordered_headings: {MIN_REORDER_HEADINGS} to {MAX_REORDER_HEADINGS}",
            f"ordered heading: at most {MAX_PROPOSED_HEADING_CHARS} characters",
            f"outline_headings: {MIN_OUTLINE_HEADINGS} to {MAX_OUTLINE_HEADINGS}",
            f"outline heading: at most {MAX_OUTLINE_HEADING_CHARS} characters",
            f"table columns: {MIN_TABLE_COLUMNS} to {MAX_TABLE_COLUMNS}",
            f"table dimensions: {MIN_TABLE_DIMENSIONS} to {MAX_TABLE_DIMENSIONS}",
            f"table label: at most {MAX_TABLE_LABEL_CHARS} characters",
            f"anchor_intent: at most {MAX_ANCHOR_INTENT_CHARS} characters",
            f"CREATE_NEW_RESOURCE page_bindings: {minimum_page_refs} to {MAX_PAGE_REFS_PER_OPERATION}",
            f"PROPOSE_SECTION_REORDER requires exactly {reorder_page_refs} page_ref",
        )
        for fragment in expected_fragments:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, bounds)
        self.assertIn(bounds, DeepSeekChangePlanWriter.build_system_prompt())

    async def test_valid_escape_heavy_material_uses_chat_envelope_budget(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(200, json=completion('{"opportunity_operations":{}}'))

        site, report = escape_heavy_input()
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": DUMMY_API_KEY}, clear=True):
            writer = DeepSeekChangePlanWriter(transport=httpx.MockTransport(handler))
            result = await ChangePlanWorkflow(writer).run(site, report)

        self.assertEqual(result.status, ChangePlanStatus.SUCCESS)
        self.assertIsNone(result.error)
        self.assertEqual(result.operations, ())
        self.assertEqual(calls, 1)

    async def test_chat_envelope_budget_does_not_mask_missing_key(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(200, json=completion('{"opportunity_operations":{}}'))

        site, report = escape_heavy_input()
        with patch.dict(os.environ, {}, clear=True):
            writer = DeepSeekChangePlanWriter(transport=httpx.MockTransport(handler))
            result = await ChangePlanWorkflow(writer).run(site, report)

        self.assertEqual(result.status, ChangePlanStatus.GENERATION_FAILED)
        self.assertIsNone(result.error)
        self.assertEqual(result.operations, ())
        self.assertEqual(calls, 0)

    async def test_missing_key_fails_before_http(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(200, json=completion('{"opportunity_operations":{}}'))

        with patch.dict(os.environ, {}, clear=True):
            result = await DeepSeekChangePlanWriter(
                transport=httpx.MockTransport(handler)
            ).write_change_plan(prompt())
        self.assertEqual(result.status, ChangePlanGenerationStatus.FAILED)
        self.assertEqual(calls, 0)

    async def test_one_request_uses_chat_completions_json_object_contract(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, json=completion('{"opportunity_operations":{}}'))

        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": DUMMY_API_KEY}, clear=True):
            result = await DeepSeekChangePlanWriter(
                transport=httpx.MockTransport(handler)
            ).write_change_plan(prompt())
        self.assertEqual(result.status, ChangePlanGenerationStatus.SUCCESS)
        self.assertEqual(len(requests), 1)
        self.assertEqual(
            str(requests[0].url), "https://api.deepseek.com/chat/completions"
        )
        self.assertNotIn("/responses", str(requests[0].url))
        payload = json.loads(requests[0].content)
        self.assertEqual(payload["model"], "deepseek-flash")
        self.assertEqual(payload["temperature"], 0)
        self.assertEqual(payload["thinking"], {"type": "disabled"})
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertEqual(payload["max_tokens"], MAX_PROVIDER_TOKENS)
        self.assertEqual(len(payload["messages"]), 2)
        self.assertEqual(payload["messages"][0]["role"], "system")
        self.assertEqual(payload["messages"][1]["role"], "user")
        instructions = payload["messages"][0]["content"]
        self.assertIn("Return JSON only", instructions)
        self.assertIn("verbatim contiguous substring", instructions)
        self.assertIn("Do not paraphrase", instructions)
        self.assertNotIn("reasoning", payload)
        self.assertNotIn("text", payload)
        self.assertNotIn("instructions", payload)
        self.assertNotIn("input", payload)
        self.assertNotIn("max_output_tokens", payload)
        self.assertEqual(requests[0].headers["Authorization"], f"Bearer {DUMMY_API_KEY}")
        material_json = payload["messages"][1]["content"]
        material = json.loads(material_json)
        content_point_contract = material["contract"]["grounded_fields"][
            "content_points[].subject_ref"
        ]
        self.assertEqual(
            content_point_contract["allowed_values"],
            "enclosing_R_content_point_candidates",
        )
        self.assertTrue(content_point_contract["origin_must_be_cited_by_operation"])
        self.assertFalse(content_point_contract["free_text_subject_allowed"])
        self.assertTrue(material["opportunities"][0]["content_point_candidates"])
        self.assertIsNone(material["contract"]["retry_feedback"])
        self.assertNotIn("final_url", material_json)

    async def test_schema_valid_locator_page_mismatch_still_fails_python_validation(self) -> None:
        calls = 0
        raw = json.dumps(
            {
                "opportunity_operations": {
                    "R1": {
                        "primary_operation": {
                            "source_action_code": "EXPAND_PAGE_SECTION",
                            "operation_type": "EXPAND_SECTION",
                            "source_refs": ["S1"],
                            "page_refs": ["P2"],
                            "locator_ref": "P1.LOC_00",
                            "content_points": [
                                {"intent": "EXPLAIN", "subject_ref": "S1.CP_01"}
                            ],
                        }
                    }
                }
            },
            separators=(",", ":"),
        )

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(200, json=completion(raw))

        report = opportunity_report(opportunity(page_refs=("P1", "P2")))
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": DUMMY_API_KEY}, clear=True):
            result = await ChangePlanWorkflow(
                DeepSeekChangePlanWriter(transport=httpx.MockTransport(handler))
            ).run(packet(), report)

        self.assertEqual(result.status, ChangePlanStatus.INVALID_OUTPUT)
        self.assertEqual(result.error, "EVIDENCE_USE_NOT_ALLOWED")
        self.assertEqual(result.final_validation_category, "EVIDENCE_USE_NOT_ALLOWED")
        self.assertEqual(result.writer_attempt_count, 1)
        self.assertEqual(calls, 1)

    async def test_final_chat_request_envelope_fits_hard_limits(self) -> None:
        captured: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured.update(json.loads(request.content))
            return httpx.Response(200, json=completion('{"opportunity_operations":{}}'))

        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": DUMMY_API_KEY}, clear=True):
            result = await DeepSeekChangePlanWriter(
                transport=httpx.MockTransport(handler)
            ).write_change_plan(prompt())
        envelope = json.dumps(captured, ensure_ascii=False, separators=(",", ":"))
        self.assertEqual(result.status, ChangePlanGenerationStatus.SUCCESS)
        self.assertLessEqual(len(envelope), MAX_INPUT_ENVELOPE_CHARS)
        self.assertLessEqual(len(envelope.encode("utf-8")), MAX_INPUT_ENVELOPE_BYTES)

    async def test_total_chat_request_over_budget_fails_closed_before_http(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(200, json=completion('{"opportunity_operations":{}}'))

        with (
            patch.dict(os.environ, {"DEEPSEEK_API_KEY": DUMMY_API_KEY}, clear=True),
            patch(
                "foreign_trade_geo_agent.adapters.deepseek_change_plan.MAX_INPUT_ENVELOPE_CHARS",
                1,
            ),
        ):
            result = await DeepSeekChangePlanWriter(
                transport=httpx.MockTransport(handler)
            ).write_change_plan(prompt())

        self.assertEqual(result.status, ChangePlanGenerationStatus.FAILED)
        self.assertEqual(result.failure_kind.value, "input_too_large")
        self.assertEqual(result.error, "Change plan request exceeds the input budget.")
        self.assertEqual(calls, 0)

    async def test_oversized_user_material_fails_before_http(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(200, json=completion('{"opportunity_operations":{}}'))

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
            return httpx.Response(200, json=completion('{"opportunity_operations":{}}'))

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
                        json=completion(
                            '{"opportunity_operations":{',
                            finish_reason="length",
                        ),
                    )
                )
            ).write_change_plan(prompt())
        self.assertEqual(result.status, ChangePlanGenerationStatus.FAILED)
        self.assertIn("truncated", (result.error or "").casefold())

    async def test_only_stop_finish_reason_is_accepted(self) -> None:
        for finish_reason in (None, "unknown", "tool_calls"):
            with self.subTest(finish_reason=finish_reason):
                with patch.dict(os.environ, {"DEEPSEEK_API_KEY": DUMMY_API_KEY}, clear=True):
                    result = await DeepSeekChangePlanWriter(
                        transport=httpx.MockTransport(
                            lambda request, value=finish_reason: httpx.Response(
                                200,
                                json=completion(
                                    '{"opportunity_operations":{}}',
                                    finish_reason=value,
                                ),
                            )
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
            httpx.Response(200, json={"choices": [{"message": {"content": 42}, "finish_reason": "stop"}]}),
            httpx.Response(200, json={"choices": [{"message": {"content": "{}"}, "finish_reason": 42}]}),
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
        raw_secret = '{"opportunity_operations":{},"secret":"never log this"}'
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
