from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
import socket
import unittest
from unittest.mock import patch

import httpx

from foreign_trade_geo_agent.core.change_plan import (
    MAX_SYSTEM_PROMPT_BYTES,
    MAX_SYSTEM_PROMPT_CHARS,
    MAX_USER_MATERIAL_BYTES,
    MAX_USER_MATERIAL_CHARS,
    ChangePlanGeneration,
    ChangePlanGenerationStatus,
    ChangePlanInput,
    build_change_plan_prompt,
    validate_change_plan_input,
)
from scripts import verify_change_plan as cli


class VerifyChangePlanCLITests(unittest.TestCase):
    def setUp(self) -> None:
        self.network_patches = (
            patch.object(
                socket,
                "getaddrinfo",
                side_effect=AssertionError("DNS/site network forbidden"),
            ),
        )
        for active_patch in self.network_patches:
            active_patch.start()

    def tearDown(self) -> None:
        for active_patch in reversed(self.network_patches):
            active_patch.stop()

    @staticmethod
    def _capture_main(arguments, **kwargs):
        stdout = io.StringIO()
        stderr = io.StringIO()
        main = getattr(cli, "main", lambda *_args, **_kwargs: 99)
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = main(arguments, **kwargs)
        return result, stdout.getvalue(), stderr.getvalue()

    def test_default_dry_run_validates_fixture_without_keys_or_writer(self) -> None:
        secret = "DRY_RUN_SECRET_MUST_NOT_APPEAR"
        with (
            patch.object(
                cli,
                "load_api_keys",
                side_effect=AssertionError("dry-run must not load keys"),
                create=True,
            ),
            patch.object(
                cli,
                "DeepSeekChangePlanWriter",
                side_effect=AssertionError("dry-run must not construct writer"),
                create=True,
            ),
            patch.dict(os.environ, {"DEEPSEEK_API_KEY": secret}, clear=True),
        ):
            result, output, error = self._capture_main([])

        self.assertEqual(result, 0)
        self.assertEqual(error, "")
        self.assertIn("Mode: DRY RUN", output)
        self.assertIn("Synthetic fixture: true", output)
        self.assertIn("Expected maximum provider requests: 1", output)
        self.assertIn("Opportunities: R1, R2", output)
        self.assertIn("Pages: P1", output)
        self.assertIn("Sources: S1, S2", output)
        self.assertIn("Request count: 0", output)
        self.assertIn("Tavily accessed: false", output)
        self.assertIn("Crawler accessed: false", output)
        self.assertIn("WordPress accessed: false", output)
        self.assertIn("Envelope chars: unavailable", output)
        self.assertNotIn(secret, output)

    def test_missing_key_stops_before_live_writer_and_reports_zero_calls(self) -> None:
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(200, json={})

        transport = httpx.MockTransport(handler)
        with (
            patch.object(cli, "load_api_keys", return_value=None, create=True),
            patch.object(
                cli,
                "DeepSeekChangePlanWriter",
                side_effect=AssertionError(
                    "writer must not be constructed without a key"
                ),
                create=True,
            ),
            patch.dict(os.environ, {}, clear=True),
        ):
            result, output, error = self._capture_main(
                ["--execute-live"], transport=transport
            )

        self.assertEqual(result, 2)
        self.assertEqual(error, "")
        self.assertEqual(calls, [])
        self.assertIn("DEEPSEEK_API_KEY: unavailable", output)
        self.assertIn("Request count: 0", output)

    def test_only_execute_live_enters_live_writer_path(self) -> None:
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {"message": {"content": "{}"}, "finish_reason": "stop"}
                    ]
                },
            )

        transport = httpx.MockTransport(handler)
        with (
            patch.object(cli, "load_api_keys", return_value=None, create=True),
            patch.dict(
                os.environ, {"DEEPSEEK_API_KEY": "LIVE_GATE_SECRET"}, clear=True
            ),
        ):
            dry_result, dry_output, _ = self._capture_main([], transport=transport)
            live_result, live_output, live_error = self._capture_main(
                ["--execute-live"], transport=transport
            )

        self.assertEqual(dry_result, 0)
        self.assertIn("Request count: 0", dry_output)
        self.assertEqual(live_result, 1)
        self.assertEqual(live_error, "")
        self.assertEqual(len(requests), 1)
        self.assertIn("DEEPSEEK_API_KEY: available", live_output)
        self.assertIn("Request count: 1", live_output)
        self.assertIn("ChangePlanStatus: invalid_output", live_output)
        self.assertNotIn("LIVE_GATE_SECRET", dry_output + live_output)

    def test_synthetic_fixture_passes_stable_input_and_prompt_contracts(self) -> None:
        fixture = cli.build_synthetic_fixture()
        self.assertIsNotNone(fixture)
        change_input = ChangePlanInput(fixture.site_content, fixture.opportunities)
        self.assertIsNone(validate_change_plan_input(change_input))

        prompt = build_change_plan_prompt(change_input)
        payload = json.loads(prompt.material_json())
        self.assertEqual(
            [item["opportunity_ref"] for item in payload["opportunities"]],
            ["R1", "R2"],
        )
        self.assertEqual([item["page_ref"] for item in payload["pages"]], ["P1"])
        self.assertEqual(
            [item["source_ref"] for item in payload["sources"]], ["S1", "S2"]
        )
        self.assertIn("Technical Specifications", prompt.material_json())
        self.assertIn("AODD pump maintenance", prompt.material_json())

    def test_prompt_metrics_are_positive_and_within_production_bounds(self) -> None:
        context = cli.prepare_smoke_context(cli.build_synthetic_fixture())
        self.assertIsNotNone(context)
        metrics = context.metrics
        self.assertGreater(metrics.system_chars, 0)
        self.assertGreater(metrics.system_bytes, 0)
        self.assertGreater(metrics.user_chars, 0)
        self.assertGreater(metrics.user_bytes, 0)
        self.assertLessEqual(metrics.system_chars, MAX_SYSTEM_PROMPT_CHARS)
        self.assertLessEqual(metrics.system_bytes, MAX_SYSTEM_PROMPT_BYTES)
        self.assertLessEqual(metrics.user_chars, MAX_USER_MATERIAL_CHARS)
        self.assertLessEqual(metrics.user_bytes, MAX_USER_MATERIAL_BYTES)
        # Envelope metrics would require duplicating the production adapter's
        # private request schema, so the smoke script must report unavailable.
        self.assertIsNone(metrics.envelope_chars)
        self.assertIsNone(metrics.envelope_bytes)


class SingleRequestTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_transport_allows_one_request_and_blocks_a_second(self) -> None:
        seen = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request.url)
            return httpx.Response(200, json={"ok": True})

        transport = cli.SingleRequestTransport(httpx.MockTransport(handler))
        async with httpx.AsyncClient(transport=transport) as client:
            response = await client.post("https://api.deepseek.com/chat/completions")
            self.assertEqual(response.status_code, 200)
            with self.assertRaises(httpx.RequestError):
                await client.post("https://api.deepseek.com/chat/completions")

        self.assertEqual(transport.request_count, 1)
        self.assertEqual(len(seen), 1)

    async def test_observing_writer_returns_generation_unchanged_and_counts_calls(
        self,
    ) -> None:
        generation = ChangePlanGeneration(
            provider="deepseek",
            model="deepseek-flash",
            status=ChangePlanGenerationStatus.SUCCESS,
            text="raw-text",
            error=None,
        )

        class StubWriter:
            def __init__(self) -> None:
                self.calls = 0

            async def write_change_plan(self, prompt):
                self.calls += 1
                return generation

        stub = StubWriter()
        observer = cli.ObservingChangePlanWriter(stub)
        result = await observer.write_change_plan(None)

        self.assertIs(result, generation)
        self.assertEqual(observer.call_count, 1)
        self.assertEqual(observer.raw_text_chars, len("raw-text"))
        self.assertEqual(observer.raw_text_bytes, len("raw-text".encode("utf-8")))

    async def test_observer_does_not_parse_provider_json(self) -> None:
        # "not-json" is intentionally not valid JSON. The observer must return it
        # unchanged and never parse or repair it.
        generation = ChangePlanGeneration(
            provider="deepseek",
            model="deepseek-flash",
            status=ChangePlanGenerationStatus.SUCCESS,
            text="not-json",
            error=None,
        )

        class StubWriter:
            async def write_change_plan(self, prompt):
                return generation

        observer = cli.ObservingChangePlanWriter(StubWriter())
        result = await observer.write_change_plan(None)

        self.assertIs(result, generation)
        self.assertEqual(result.text, "not-json")
        self.assertEqual(observer.raw_text_chars, 8)

    async def test_offline_live_path_uses_real_adapter_once_and_reports_strict_failure(
        self,
    ) -> None:
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {"message": {"content": "not-json"}, "finish_reason": "stop"}
                    ]
                },
            )

        output = io.StringIO()
        with (
            patch.dict(
                os.environ, {"DEEPSEEK_API_KEY": "OFFLINE_TEST_SECRET"}, clear=True
            ),
            redirect_stdout(output),
        ):
            result = await cli._run_live(
                cli.build_synthetic_fixture(),
                transport=httpx.MockTransport(handler),
            )

        rendered = output.getvalue()
        self.assertEqual(result, 1)
        self.assertEqual(len(requests), 1)
        self.assertEqual(
            str(requests[0].url), "https://api.deepseek.com/chat/completions"
        )
        body = json.loads(requests[0].content)
        self.assertIn("model", body)
        self.assertIn("messages", body)
        self.assertIn("max_tokens", body)
        self.assertIn("thinking", body)
        self.assertEqual(len(body["messages"]), 2)
        self.assertEqual(body["messages"][0]["role"], "system")
        self.assertEqual(body["messages"][1]["role"], "user")
        self.assertIn("Request count: 1", rendered)
        self.assertIn("Generation status: success", rendered)
        self.assertIn("Raw response chars: 8", rendered)
        self.assertIn("Raw response bytes: 8", rendered)
        self.assertIn("Finish result: accepted_stop", rendered)
        self.assertIn("ChangePlanStatus: invalid_output", rendered)
        self.assertIn("Validation category: JSON_FORMAT", rendered)
        self.assertIn("Retry occurred: false", rendered)
        self.assertNotIn("not-json", rendered)
        self.assertNotIn("OFFLINE_TEST_SECRET", rendered)


if __name__ == "__main__":
    unittest.main()
