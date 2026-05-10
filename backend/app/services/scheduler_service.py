from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable
import uuid


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ScheduledJob:
    job_id: str
    job_type: str
    run_at: datetime
    callback_name: str
    payload: dict
    interval_seconds: float | None = None


class SchedulerService:
    def __init__(self) -> None:
        self._callbacks: dict[str, Callable[[dict], Awaitable[None]]] = {}
        self._jobs: dict[str, ScheduledJob] = {}
        self._task: asyncio.Task[None] | None = None
        self._started = False
        self._tick_seconds = 0.01
        self._last_error: str | None = None
        self._executed_job_count = 0
        self._cancelled_job_count = 0

    def register_callback(self, name: str, callback: Callable[[dict], Awaitable[None]]) -> None:
        normalized = str(name).strip()
        if not normalized:
            raise ValueError("callback name cannot be empty")
        self._callbacks[normalized] = callback

    async def startup(self) -> None:
        if self._started:
            return
        self._started = True
        self._task = asyncio.create_task(self._loop(), name="tokenflow-scheduler")

    async def shutdown(self) -> None:
        self._started = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def schedule_once(
        self,
        *,
        callback_name: str,
        payload: dict,
        delay_seconds: float = 0.0,
        job_type: str = "delayed",
    ) -> str:
        job_id = uuid.uuid4().hex
        self._jobs[job_id] = ScheduledJob(
            job_id=job_id,
            job_type=job_type,
            run_at=_utc_now() + timedelta(seconds=max(0.0, delay_seconds)),
            callback_name=callback_name,
            payload=dict(payload),
        )
        return job_id

    def schedule_cron_like(
        self,
        *,
        callback_name: str,
        payload: dict,
        interval_seconds: float,
    ) -> str:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be greater than 0")
        job_id = uuid.uuid4().hex
        self._jobs[job_id] = ScheduledJob(
            job_id=job_id,
            job_type="cron",
            run_at=_utc_now() + timedelta(seconds=interval_seconds),
            callback_name=callback_name,
            payload=dict(payload),
            interval_seconds=interval_seconds,
        )
        return job_id

    def cancel_job(self, job_id: str) -> bool:
        if job_id in self._jobs:
            self._jobs.pop(job_id, None)
            self._cancelled_job_count += 1
            return True
        return False

    def list_jobs(self) -> list[ScheduledJob]:
        return sorted(self._jobs.values(), key=lambda item: (item.run_at, item.job_id))

    def get_health(self) -> dict:
        return {
            "started": self._started,
            "scheduled_jobs": len(self._jobs),
            "executed_job_count": self._executed_job_count,
            "cancelled_job_count": self._cancelled_job_count,
            "last_error": self._last_error,
        }

    async def _loop(self) -> None:
        while self._started:
            try:
                await self._run_due_jobs()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                self._last_error = str(exc)
            await asyncio.sleep(self._tick_seconds)

    async def _run_due_jobs(self) -> None:
        now = _utc_now()
        due_jobs = [job for job in self._jobs.values() if job.run_at <= now]
        for job in due_jobs:
            callback = self._callbacks.get(job.callback_name)
            if callback is None:
                self._last_error = f"callback not registered: {job.callback_name}"
                self._jobs.pop(job.job_id, None)
                continue
            await callback(dict(job.payload))
            self._executed_job_count += 1
            if job.job_type == "cron" and job.interval_seconds is not None:
                self._jobs[job.job_id] = ScheduledJob(
                    job_id=job.job_id,
                    job_type=job.job_type,
                    run_at=_utc_now() + timedelta(seconds=job.interval_seconds),
                    callback_name=job.callback_name,
                    payload=dict(job.payload),
                    interval_seconds=job.interval_seconds,
                )
            else:
                self._jobs.pop(job.job_id, None)


scheduler_service = SchedulerService()
