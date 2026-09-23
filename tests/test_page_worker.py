import os
from pathlib import Path
import unittest
from unittest.mock import patch

from foreign_trade_geo_agent.adapters.page_extractor import TrafilaturaPageExtractor
from foreign_trade_geo_agent.core.extraction import (
    PageExtractionFailureKind,
    PageExtractionStatus,
)


FIXTURE = Path(__file__).parent / "fixtures" / "page_extraction" / "article.html"
FINAL_URL = "https://customer.example/catalog/pump-guide"
HELPER_MODULE = "tests.page_worker_helper"


class PageExtractionWorkerTests(unittest.TestCase):
    def test_normal_worker_is_a_distinct_reaped_process(self) -> None:
        extractor = TrafilaturaPageExtractor()
        result = extractor.extract(FIXTURE.read_bytes(), FINAL_URL)

        self.assertEqual(result.status, PageExtractionStatus.SUCCESS)
        self.assertIsNotNone(extractor._last_process)
        self.assertNotEqual(extractor._last_process.pid, os.getpid())
        self.assertIsNotNone(extractor._last_process.poll())

    def test_timeout_terminates_and_reaps_worker(self) -> None:
        extractor = TrafilaturaPageExtractor(
            timeout=0.2,
            termination_grace=0.5,
            _worker_module=HELPER_MODULE,
        )
        result = extractor.extract(b"MODE:SLEEP", FINAL_URL)

        self.assertEqual(
            result.failure_kind,
            PageExtractionFailureKind.EXTRACTION_TIMEOUT,
        )
        self.assertIsNotNone(extractor._last_process.poll())

    def test_repeated_timeouts_leave_no_live_workers(self) -> None:
        extractor = TrafilaturaPageExtractor(
            timeout=0.2,
            termination_grace=0.5,
            _worker_module=HELPER_MODULE,
        )
        workers = []
        for _ in range(3):
            result = extractor.extract(b"MODE:SLEEP", FINAL_URL)
            self.assertEqual(
                result.failure_kind,
                PageExtractionFailureKind.EXTRACTION_TIMEOUT,
            )
            workers.append(extractor._last_process)

        self.assertTrue(all(process.poll() is not None for process in workers))

    def test_crashed_worker_is_a_controlled_failure(self) -> None:
        extractor = TrafilaturaPageExtractor(_worker_module=HELPER_MODULE)
        result = extractor.extract(b"MODE:CRASH", FINAL_URL)

        self.assertEqual(result.failure_kind, PageExtractionFailureKind.WORKER_FAILED)
        self.assertEqual(extractor._last_process.returncode, 23)

    def test_worker_output_is_bounded(self) -> None:
        extractor = TrafilaturaPageExtractor(
            max_worker_output_bytes=512,
            _worker_module=HELPER_MODULE,
        )
        result = extractor.extract(b"MODE:OVERSIZE", FINAL_URL)

        self.assertEqual(
            result.failure_kind,
            PageExtractionFailureKind.OUTPUT_TOO_LARGE,
        )

    def test_worker_receives_a_sanitized_environment(self) -> None:
        extractor = TrafilaturaPageExtractor(_worker_module=HELPER_MODULE)
        with patch.dict(os.environ, {"STAGE_B_TEST_API_KEY": "not-a-real-key"}):
            result = extractor.extract(b"MODE:ENV", FINAL_URL)

        self.assertEqual(result.status, PageExtractionStatus.SUCCESS)
        self.assertEqual(result.body_text, "worker environment is clean")


if __name__ == "__main__":
    unittest.main()
