"""Single-process task ownership and transient progress for the local Demo."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from uuid import uuid4

from foreign_trade_geo_agent.core.orchestration import (
    EndToEndProgressEvent,
    EndToEndProgressEventKind,
    EndToEndProgressObserver,
)


@dataclass(frozen=True, slots=True)
class LocalJobSnapshot:
    job_id: str
    run_id: str | None
    events: tuple[EndToEndProgressEvent, ...]
    active: bool
    failure_message: str | None


@dataclass(slots=True)
class _LocalJob:
    job_id: str
    run_id: str | None = None
    events: list[EndToEndProgressEvent] = field(default_factory=list)
    task: asyncio.Task[object] | None = None
    active: bool = True
    failure_message: str | None = None


class LocalJobRegistry:
    """Own local asyncio tasks without replacing persisted history."""

    def __init__(self) -> None:
        self._jobs: dict[str, _LocalJob] = {}

    def create_job(self) -> str:
        job_id = str(uuid4())
        self._jobs[job_id] = _LocalJob(job_id=job_id)
        return job_id

    def observer_for(self, job_id: str) -> EndToEndProgressObserver:
        self._require(job_id)

        def observe(event: EndToEndProgressEvent) -> None:
            job = self._require(job_id)
            if event.kind is EndToEndProgressEventKind.RUN_STARTED:
                job.run_id = event.run_id
            job.events.append(event)

        return observe

    def attach_task(self, job_id: str, task: asyncio.Task[object]) -> None:
        job = self._require(job_id)
        if job.task is not None:
            raise ValueError("Demo job already owns a task.")
        job.task = task

        def completed(finished: asyncio.Task[object]) -> None:
            job.active = False
            try:
                finished.result()
            except asyncio.CancelledError:
                job.failure_message = "Analysis was cancelled."
            except Exception:
                job.failure_message = "Analysis failed unexpectedly."

        task.add_done_callback(completed)

    def get_job(self, job_id: str) -> LocalJobSnapshot | None:
        job = self._jobs.get(job_id)
        return None if job is None else self._snapshot(job)

    def get_job_for_run(self, run_id: str) -> LocalJobSnapshot | None:
        for job in self._jobs.values():
            if job.run_id == run_id:
                return self._snapshot(job)
        return None

    async def shutdown(self) -> None:
        tasks = tuple(
            job.task
            for job in self._jobs.values()
            if job.task is not None and not job.task.done()
        )
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            await asyncio.sleep(0)

    def _require(self, job_id: str) -> _LocalJob:
        job = self._jobs.get(job_id)
        if job is None:
            raise KeyError("Demo job was not found.")
        return job

    @staticmethod
    def _snapshot(job: _LocalJob) -> LocalJobSnapshot:
        return LocalJobSnapshot(
            job_id=job.job_id,
            run_id=job.run_id,
            events=tuple(job.events),
            active=job.active,
            failure_message=job.failure_message,
        )
