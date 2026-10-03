from __future__ import annotations

import asyncio
import unittest

from foreign_trade_geo_agent.core.orchestration import (
    EndToEndProgressEvent,
    EndToEndProgressEventKind,
    EndToEndStage,
)
from foreign_trade_geo_agent.web.jobs import LocalJobRegistry


RUN_ID = "11111111-1111-4111-8111-111111111111"


class LocalJobRegistryTests(unittest.IsolatedAsyncioTestCase):
    async def test_observer_associates_persisted_run_and_real_stage_state(self) -> None:
        registry = LocalJobRegistry()
        job_id = registry.create_job()
        observer = registry.observer_for(job_id)

        observer(EndToEndProgressEvent(EndToEndProgressEventKind.RUN_STARTED, RUN_ID, None))
        observer(
            EndToEndProgressEvent(
                EndToEndProgressEventKind.STAGE_STARTED,
                RUN_ID,
                EndToEndStage.CRAWL,
            )
        )

        snapshot = registry.get_job(job_id)
        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual(snapshot.run_id, RUN_ID)
        self.assertEqual(registry.get_job_for_run(RUN_ID), snapshot)
        self.assertEqual(snapshot.events[-1].stage, EndToEndStage.CRAWL)

    async def test_registry_shutdown_cancels_and_awaits_owned_tasks(self) -> None:
        registry = LocalJobRegistry()
        job_id = registry.create_job()
        cancelled = asyncio.Event()

        async def wait_forever() -> None:
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        task = asyncio.create_task(wait_forever())
        registry.attach_task(job_id, task)
        await asyncio.sleep(0)

        await registry.shutdown()

        self.assertTrue(task.done())
        self.assertTrue(task.cancelled())
        self.assertTrue(cancelled.is_set())


if __name__ == "__main__":
    unittest.main()
