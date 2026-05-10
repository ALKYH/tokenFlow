from __future__ import annotations

from datetime import datetime, timezone

from ..db.session import AsyncSessionLocal
from ..models.runtime_execution import RuntimeQueueMetricRecord


async def record_runtime_metric(
    *,
    request_id: str,
    queue_backend: str,
    status: str,
    duration_ms: float,
    wait_time_ms: float,
    attempts: int,
) -> None:
    try:
        async with AsyncSessionLocal() as session:
            session.add(
                RuntimeQueueMetricRecord(
                    request_id=request_id,
                    queue_backend=queue_backend,
                    status=status,
                    duration_ms=duration_ms,
                    wait_time_ms=wait_time_ms,
                    attempts=attempts,
                )
            )
            await session.commit()
    except Exception:
        return


def compute_wait_time_ms(submitted_at: str) -> float:
    try:
        submitted_dt = datetime.fromisoformat(submitted_at)
        return max(0.0, (datetime.now(timezone.utc) - submitted_dt).total_seconds() * 1000.0)
    except Exception:
        return 0.0
