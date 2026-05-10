from __future__ import annotations

from collections import defaultdict
from sqlalchemy import desc, select

from ..db.session import AsyncSessionLocal
from ..models.runtime_execution import (
    RoutingQueueDeadLetterRecord,
    RoutingQueueMetricRecord,
    RuntimeQueueDeadLetterRecord,
    RuntimeQueueMetricRecord,
)


async def list_routing_dead_letters(limit: int = 20) -> list[RoutingQueueDeadLetterRecord]:
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(RoutingQueueDeadLetterRecord)
                .order_by(desc(RoutingQueueDeadLetterRecord.created_at), desc(RoutingQueueDeadLetterRecord.id))
                .limit(max(1, min(limit, 200)))
            )
        ).scalars().all()
        return list(rows)


async def list_routing_metrics(limit: int = 50) -> list[RoutingQueueMetricRecord]:
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(RoutingQueueMetricRecord)
                .order_by(desc(RoutingQueueMetricRecord.created_at), desc(RoutingQueueMetricRecord.id))
                .limit(max(1, min(limit, 500)))
            )
        ).scalars().all()
        return list(rows)


async def list_runtime_dead_letters(limit: int = 20) -> list[RuntimeQueueDeadLetterRecord]:
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(RuntimeQueueDeadLetterRecord)
                .order_by(desc(RuntimeQueueDeadLetterRecord.created_at), desc(RuntimeQueueDeadLetterRecord.id))
                .limit(max(1, min(limit, 200)))
            )
        ).scalars().all()
        return list(rows)


async def list_runtime_metrics(limit: int = 50) -> list[RuntimeQueueMetricRecord]:
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(RuntimeQueueMetricRecord)
                .order_by(desc(RuntimeQueueMetricRecord.created_at), desc(RuntimeQueueMetricRecord.id))
                .limit(max(1, min(limit, 500)))
            )
        ).scalars().all()
        return list(rows)


def _aggregate_metric_rows(rows) -> list[dict]:
    grouped: dict[str, dict] = defaultdict(
        lambda: {
            "queue_backend": "",
            "total_count": 0,
            "success_count": 0,
            "failed_count": 0,
            "duration_sum": 0.0,
            "wait_sum": 0.0,
            "attempts_sum": 0.0,
        }
    )
    for row in rows:
        item = grouped[row.queue_backend]
        item["queue_backend"] = row.queue_backend
        item["total_count"] += 1
        if row.status == "ok":
            item["success_count"] += 1
        else:
            item["failed_count"] += 1
        item["duration_sum"] += float(row.duration_ms or 0.0)
        item["wait_sum"] += float(row.wait_time_ms or 0.0)
        item["attempts_sum"] += float(row.attempts or 0.0)

    result: list[dict] = []
    for item in grouped.values():
        total = max(1, item["total_count"])
        result.append(
            {
                "queue_backend": item["queue_backend"],
                "total_count": item["total_count"],
                "success_count": item["success_count"],
                "failed_count": item["failed_count"],
                "avg_duration_ms": item["duration_sum"] / total,
                "avg_wait_time_ms": item["wait_sum"] / total,
                "avg_attempts": item["attempts_sum"] / total,
            }
        )
    return sorted(result, key=lambda item: item["queue_backend"])


async def aggregate_routing_metrics(limit: int = 200) -> list[dict]:
    rows = await list_routing_metrics(limit=limit)
    return _aggregate_metric_rows(rows)


async def aggregate_runtime_metrics(limit: int = 200) -> list[dict]:
    rows = await list_runtime_metrics(limit=limit)
    return _aggregate_metric_rows(rows)
