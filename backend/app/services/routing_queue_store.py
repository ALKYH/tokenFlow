from __future__ import annotations

from datetime import datetime, timezone

from ..db.session import AsyncSessionLocal
from ..models.runtime_execution import RoutingQueueDeadLetterRecord, RoutingQueueMetricRecord
from ..schemas.routing import RoutingClassifyRequest


async def record_routing_dead_letter(
    *,
    request_id: str,
    queue_backend: str,
    error_code: str,
    error_message: str,
    attempts: int,
    payload: RoutingClassifyRequest,
    submitted_at: datetime,
) -> None:
    wait_time_ms = max(0.0, (datetime.now(timezone.utc) - submitted_at).total_seconds() * 1000.0)
    try:
        async with AsyncSessionLocal() as session:
            session.add(
                RoutingQueueDeadLetterRecord(
                    request_id=request_id,
                    queue_backend=queue_backend,
                    error_code=error_code,
                    error_message=error_message,
                    attempts=attempts,
                    payload_json=payload.model_dump(mode='json'),
                    last_attempt_at=datetime.now(timezone.utc),
                    wait_time_ms=wait_time_ms,
                )
            )
            await session.commit()
    except Exception:
        return


async def record_routing_metric(
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
                RoutingQueueMetricRecord(
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
