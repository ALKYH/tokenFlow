import asyncio

from backend.app.services.scheduler_service import SchedulerService


def test_scheduler_runs_delayed_job_once():
    observed: list[str] = []

    async def callback(payload: dict) -> None:
        observed.append(str(payload["value"]))

    async def scenario():
        service = SchedulerService()
        service.register_callback("once", callback)
        await service.startup()
        try:
            service.schedule_once(callback_name="once", payload={"value": "hello"}, delay_seconds=0.01)
            await asyncio.sleep(0.08)
            health = service.get_health()
            assert observed == ["hello"]
            assert health["executed_job_count"] == 1
            assert health["scheduled_jobs"] == 0
        finally:
            await service.shutdown()

    asyncio.run(scenario())


def test_scheduler_runs_cron_like_job_multiple_times():
    observed = {"count": 0}

    async def callback(payload: dict) -> None:
        _ = payload
        observed["count"] += 1

    async def scenario():
        service = SchedulerService()
        service.register_callback("cron", callback)
        await service.startup()
        try:
            job_id = service.schedule_cron_like(
                callback_name="cron",
                payload={"name": "tick"},
                interval_seconds=0.02,
            )
            await asyncio.sleep(0.09)
            cancelled = service.cancel_job(job_id)
            assert cancelled is True
            assert observed["count"] >= 2
            assert service.get_health()["cancelled_job_count"] == 1
        finally:
            await service.shutdown()

    asyncio.run(scenario())
