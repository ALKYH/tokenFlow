from __future__ import annotations

import asyncio
import os
from time import perf_counter
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Awaitable, Callable

from .queue_shared import (
    AsyncMemoryWorker,
    BaseAsyncQueueService,
    BaseQueueError,
    QueueHealthSnapshot,
    build_redis_queue_names,
    decode_queue_message,
    encode_queue_message,
)
from .routing_queue_store import record_routing_dead_letter, record_routing_metric
from ..schemas.routing import QueuedRoutingRequest, RoutingClassifyRequest, RoutingClassifyResponse, RoutingQueueHealth


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {'1', 'true', 'yes', 'on'}


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    raw = os.environ.get(name)
    try:
        value = int(raw) if raw is not None else default
    except (TypeError, ValueError):
        value = default
    return max(minimum, value)


@dataclass(frozen=True)
class RoutingQueueConfig:
    backend: str
    instance_id: str
    max_length: int
    wait_timeout_seconds: float
    max_attempts: int
    retry_delay_seconds: float
    processing_timeout_seconds: float
    reclaim_interval_seconds: float
    inline_fallback: bool
    queue_name: str
    redis_url: str

    @classmethod
    def from_env(cls) -> 'RoutingQueueConfig':
        backend = (os.environ.get('TOKENFLOW_ROUTING_QUEUE_BACKEND', 'inline').strip().lower() or 'inline')
        if backend not in {'inline', 'memory', 'redis'}:
            backend = 'inline'
        instance_id = os.environ.get('TOKENFLOW_ROUTING_QUEUE_INSTANCE_ID', '').strip() or uuid.uuid4().hex[:12]
        max_length = _env_int('TOKENFLOW_ROUTING_QUEUE_MAX_LENGTH', 128, minimum=1)
        wait_timeout_ms = _env_int('TOKENFLOW_ROUTING_QUEUE_WAIT_TIMEOUT_MS', 15000, minimum=100)
        return cls(
            backend=backend,
            instance_id=instance_id,
            max_length=max_length,
            wait_timeout_seconds=wait_timeout_ms / 1000.0,
            max_attempts=_env_int('TOKENFLOW_ROUTING_QUEUE_MAX_ATTEMPTS', 2, minimum=1),
            retry_delay_seconds=_env_int('TOKENFLOW_ROUTING_QUEUE_RETRY_DELAY_MS', 100, minimum=0) / 1000.0,
            processing_timeout_seconds=_env_int('TOKENFLOW_ROUTING_PROCESSING_TIMEOUT_MS', 30000, minimum=1000) / 1000.0,
            reclaim_interval_seconds=_env_int('TOKENFLOW_ROUTING_RECLAIM_INTERVAL_MS', 5000, minimum=500) / 1000.0,
            inline_fallback=_env_bool('TOKENFLOW_ROUTING_QUEUE_INLINE_FALLBACK', default=False),
            queue_name=os.environ.get('TOKENFLOW_ROUTING_QUEUE_NAME', 'tokenflow:routing:jobs').strip() or 'tokenflow:routing:jobs',
            redis_url=os.environ.get('TOKENFLOW_REDIS_URL', 'redis://localhost:6379/0').strip() or 'redis://localhost:6379/0',
        )

    @property
    def execute_through_queue(self) -> bool:
        return self.backend in {'memory', 'redis'}


class RoutingQueueError(BaseQueueError):
    pass


async def _classify_via_db(payload: RoutingClassifyRequest, user_id: int | None) -> RoutingClassifyResponse:
    from ..db.session import AsyncSessionLocal
    from .routing_service import classify_routing_request

    async with AsyncSessionLocal() as session:
        return await classify_routing_request(payload, session=session, user_id=user_id)


class RoutingQueueService(BaseAsyncQueueService[RoutingClassifyResponse]):
    def __init__(
        self,
        config: RoutingQueueConfig | None = None,
        classifier: Callable[[RoutingClassifyRequest, int | None], Awaitable[RoutingClassifyResponse]] | None = None,
    ) -> None:
        super().__init__()
        self.config = config or RoutingQueueConfig.from_env()
        self._classifier = classifier or _classify_via_db
        self._memory_worker: AsyncMemoryWorker[QueuedRoutingRequest] | None = None
        self._dead_letter_count = 0
        self._retry_count = 0
        self._reclaim_count = 0
        self._persistence_tasks: set[asyncio.Task[None]] = set()
        self._redis_queue_names = build_redis_queue_names(self.config.queue_name)
        self._redis_client = None
        self._redis_consumer_tasks: list[asyncio.Task[None]] = []
        self._redis_reclaim_task: asyncio.Task[None] | None = None

    async def startup(self) -> None:
        await self._startup_lifecycle()

    async def shutdown(self) -> None:
        await self._shutdown_lifecycle(
            RoutingQueueError('ROUTING_QUEUE_STOPPED', 'Routing queue service stopped')
        )

    async def _startup_backend(self) -> None:
        if self.config.backend == 'memory':
            self._memory_worker = AsyncMemoryWorker(
                self._process_envelope,
                concurrency=1,
                maxsize=self.config.max_length,
                name_prefix=f'tokenflow-routing-memory-{self.config.instance_id}',
            )
            await self._memory_worker.start()
        elif self.config.backend == 'redis':
            await self._startup_redis()
            self._redis_consumer_tasks = [
                asyncio.create_task(self._redis_consumer_loop(), name=f'tokenflow-routing-redis-{index}')
                for index in range(1)
            ]
            self._redis_reclaim_task = asyncio.create_task(
                self._redis_reclaim_loop(),
                name='tokenflow-routing-redis-reclaim',
            )

    async def _shutdown_backend(self) -> None:
        await self._shutdown_memory_worker(self._memory_worker)
        self._memory_worker = None
        for task in list(self._persistence_tasks):
            task.cancel()
        self._persistence_tasks.clear()
        if self._redis_client is not None:
            await self._redis_client.aclose()
            self._redis_client = None
        for task in self._redis_consumer_tasks:
            task.cancel()
        self._redis_consumer_tasks = []
        if self._redis_reclaim_task is not None:
            self._redis_reclaim_task.cancel()
            self._redis_reclaim_task = None

    async def classify(
        self,
        payload: RoutingClassifyRequest,
        user_id: int | None = None,
    ) -> RoutingClassifyResponse:
        if not self.config.execute_through_queue:
            return await self._classifier(payload, user_id)

        await self.startup()
        envelope = QueuedRoutingRequest(
            request_id=uuid.uuid4().hex,
            instance_id=self.config.instance_id,
            submitted_at=datetime.now(timezone.utc),
            user_id=user_id,
            payload=payload,
        )
        return await self._submit_and_wait(
            request_id=envelope.request_id,
            max_length=self.config.max_length,
            wait_timeout_seconds=self.config.wait_timeout_seconds,
            queue_full_exc_factory=lambda: RoutingQueueError('ROUTING_QUEUE_FULL', 'Routing queue is full'),
            timeout_exc_factory=lambda: RoutingQueueError(
                'ROUTING_QUEUE_TIMEOUT',
                f'Routing queue timed out after {self.config.wait_timeout_seconds:.3f}s',
            ),
            enqueue_coro_factory=lambda: self._enqueue(envelope),
            on_enqueue_error=lambda exc: self._handle_enqueue_error(exc, envelope),
        )

    async def _handle_enqueue_error(self, exc: Exception, envelope: QueuedRoutingRequest) -> None:
        if isinstance(exc, RoutingQueueError) and exc.code == 'ROUTING_QUEUE_FULL':
            self._rejected_count += 1
        if self.config.inline_fallback:
            response = await self._classifier(envelope.payload, envelope.user_id)
            self._complete_future(envelope.request_id, response)
            return
        raise RoutingQueueError('ROUTING_QUEUE_UNAVAILABLE', f'Failed to enqueue routing request: {exc}') from exc

    async def get_health(self) -> RoutingQueueHealth:
        queue_depth: int | None = 0
        processing_depth = retry_depth = dead_letter_depth = stuck_processing_count = None
        if self.config.backend == 'memory' and self._memory_worker is not None:
            queue_depth = self._memory_worker.qsize()
        elif self.config.backend == 'redis' and self._redis_client is not None:
            try:
                queue_depth = await self._redis_client.llen(self._redis_queue_names.main)
                processing_depth = await self._redis_client.llen(self._redis_queue_names.processing)
                retry_depth = await self._redis_client.llen(self._redis_queue_names.retry)
                dead_letter_depth = await self._redis_client.llen(self._redis_queue_names.dead_letter)
                stuck_processing_count = await self._redis_client.zcard(self._redis_queue_names.processing_meta)
            except Exception:
                queue_depth = processing_depth = retry_depth = dead_letter_depth = stuck_processing_count = None

        snapshot = self._build_health_snapshot(
            enabled=self.config.execute_through_queue,
            backend=self.config.backend,
            instance_id=self.config.instance_id,
            queue_name=self.config.queue_name if self.config.backend == 'redis' else 'memory',
            processing_queue_name=self._redis_queue_names.processing if self.config.backend == 'redis' else None,
            retry_queue_name=self._redis_queue_names.retry if self.config.backend == 'redis' else None,
            dead_letter_queue_name=self._redis_queue_names.dead_letter if self.config.backend == 'redis' else None,
            processing_meta_name=self._redis_queue_names.processing_meta if self.config.backend == 'redis' else None,
            processing_payload_name=self._redis_queue_names.processing_payload if self.config.backend == 'redis' else None,
            queue_depth=queue_depth,
            processing_queue_depth=processing_depth,
            retry_queue_depth=retry_depth,
            dead_letter_queue_depth=dead_letter_depth,
            stuck_processing_count=stuck_processing_count or 0,
            dead_letter_count=self._dead_letter_count,
            retry_count=self._retry_count,
            max_attempts=self.config.max_attempts,
            retry_delay_seconds=self.config.retry_delay_seconds,
            reclaim_count=self._reclaim_count,
        )

        return RoutingQueueHealth(
            enabled=snapshot.enabled,
            backend=snapshot.backend,
            instance_id=snapshot.instance_id,
            status=snapshot.status,
            execute_through_queue=self.config.execute_through_queue,
            topic=None,
            producer_group=None,
            consumer_group=None,
            queue_depth=snapshot.queue_depth,
            pending_requests=snapshot.pending_requests,
            dead_letter_count=snapshot.dead_letter_count,
            rejected_count=snapshot.rejected_count,
            retry_count=snapshot.retry_count,
            max_attempts=snapshot.max_attempts,
            retry_delay_seconds=snapshot.retry_delay_seconds,
            last_error=snapshot.last_error,
        )

    async def cleanup_zombie_jobs(self) -> int:
        before = self._reclaim_count
        await self._reclaim_stuck_processing_messages()
        return self._reclaim_count - before

    async def _enqueue(self, envelope: QueuedRoutingRequest) -> None:
        if self.config.backend == 'memory':
            if self._memory_worker is None:
                raise RoutingQueueError('ROUTING_QUEUE_UNAVAILABLE', 'Memory queue is not started')
            try:
                await self._memory_worker.submit(envelope)
            except asyncio.QueueFull as exc:
                raise RoutingQueueError('ROUTING_QUEUE_FULL', 'Memory routing queue is full') from exc
            return
        if self.config.backend == 'redis':
            if self._redis_client is None:
                raise RoutingQueueError('ROUTING_QUEUE_UNAVAILABLE', 'Redis routing queue client is not started')
            await self._redis_client.lpush(
                self._redis_queue_names.main,
                encode_queue_message(envelope.model_dump(mode="json")),
            )
            return
        raise RoutingQueueError('ROUTING_QUEUE_CONFIG_ERROR', f'Unsupported backend: {self.config.backend}')

    async def _process_serialized_message(self, raw_message: str) -> None:
        envelope = QueuedRoutingRequest.model_validate(decode_queue_message(raw_message))
        if envelope.instance_id != self.config.instance_id:
            return
        await self._mark_processing_message(envelope.request_id, raw_message)
        await self._process_envelope(envelope, raw_message=raw_message)

    async def _process_envelope(self, envelope: QueuedRoutingRequest, raw_message: str | None = None) -> None:
        started = perf_counter()
        try:
            response = await self._classifier(envelope.payload, envelope.user_id)
        except Exception as exc:
            self._last_error = str(exc)
            await self._handle_retry_or_dead_letter(envelope, exc, started=started, raw_message=raw_message)
            return
        if self.config.backend == 'redis' and raw_message is not None:
            await self._ack_processed_message(raw_message)
            await self._clear_processing_message(envelope.request_id)
        self._spawn_persistence_task(
            self._record_metric(envelope=envelope, status='ok', started=started)
        )
        self._complete_future(envelope.request_id, response)

    async def _startup_redis(self) -> None:
        try:
            from redis.asyncio import Redis
        except Exception as exc:
            raise RoutingQueueError(
                'ROUTING_QUEUE_DRIVER_ERROR',
                'redis dependency is not available',
            ) from exc
        self._redis_client = Redis.from_url(self.config.redis_url, encoding='utf-8', decode_responses=True)

    async def _redis_consumer_loop(self) -> None:
        if self._redis_client is None:
            return
        while True:
            try:
                item = await self._redis_client.brpoplpush(
                    self._redis_queue_names.main,
                    self._redis_queue_names.processing,
                    timeout=1,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                self._last_error = f'Redis consumer failed: {exc}'
                await asyncio.sleep(0.2)
                continue
            if not item:
                continue
            await self._process_serialized_message(str(item))

    async def _handle_retry_or_dead_letter(
        self,
        envelope: QueuedRoutingRequest,
        exc: Exception,
        *,
        started: float,
        raw_message: str | None = None,
    ) -> None:
        attempts = 1
        if attempts < self.config.max_attempts:
            self._retry_count += 1
            if self.config.retry_delay_seconds > 0:
                await asyncio.sleep(self.config.retry_delay_seconds)
            try:
                if self.config.backend == 'redis' and self._redis_client is not None:
                    await self._redis_client.lpush(
                        self._redis_queue_names.retry,
                        encode_queue_message(
                            {
                                "request_id": envelope.request_id,
                                "instance_id": envelope.instance_id,
                                "submitted_at": envelope.submitted_at.isoformat(),
                                "user_id": envelope.user_id,
                                "payload": envelope.payload.model_dump(mode="json"),
                            }
                        ),
                    )
                    await self._redis_client.lmove(
                        self._redis_queue_names.retry,
                        self._redis_queue_names.main,
                        "RIGHT",
                        "LEFT",
                    )
                    if raw_message is not None:
                        await self._ack_processed_message(raw_message)
                    raise RuntimeError(str(exc))
                retry_response = await self._classifier(envelope.payload, envelope.user_id)
            except Exception as retry_exc:
                exc = retry_exc
            else:
                await self._record_metric(envelope=envelope, status='ok', started=started, attempts=2)
                self._complete_future(envelope.request_id, retry_response)
                return

        self._dead_letter_count += 1
        if self.config.backend == 'redis' and self._redis_client is not None and raw_message is not None:
            await self._redis_client.lpush(self._redis_queue_names.dead_letter, raw_message)
            await self._ack_processed_message(raw_message)
            await self._clear_processing_message(envelope.request_id)
        self._spawn_persistence_task(
            record_routing_dead_letter(
                request_id=envelope.request_id,
                queue_backend=self.config.backend,
                error_code=type(exc).__name__,
                error_message=str(exc),
                attempts=max(self.config.max_attempts, 1),
                payload=envelope.payload,
                submitted_at=envelope.submitted_at,
            )
        )
        self._spawn_persistence_task(
            self._record_metric(
                envelope=envelope,
                status='failed',
                started=started,
                attempts=max(self.config.max_attempts, 1),
            )
        )
        self._fail_future(envelope.request_id, exc)

    async def _record_metric(
        self,
        *,
        envelope: QueuedRoutingRequest,
        status: str,
        started: float,
        attempts: int = 1,
    ) -> None:
        duration_ms = max(0.0, (perf_counter() - started) * 1000.0)
        wait_time_ms = max(0.0, (datetime.now(timezone.utc) - envelope.submitted_at).total_seconds() * 1000.0)
        await record_routing_metric(
            request_id=envelope.request_id,
            queue_backend=self.config.backend,
            status=status,
            duration_ms=duration_ms,
            wait_time_ms=wait_time_ms,
            attempts=attempts,
        )

    def _spawn_persistence_task(self, awaitable: Awaitable[None]) -> None:
        task = asyncio.create_task(awaitable)
        self._persistence_tasks.add(task)
        task.add_done_callback(lambda done: self._persistence_tasks.discard(done))

    async def _ack_processed_message(self, raw_message: str) -> None:
        if self._redis_client is None:
            return
        await self._redis_client.lrem(self._redis_queue_names.processing, 1, raw_message)

    async def _mark_processing_message(self, request_id: str, raw_message: str) -> None:
        if self._redis_client is None:
            return
        now_ts = datetime.now(timezone.utc).timestamp()
        await self._redis_client.zadd(self._redis_queue_names.processing_meta, {request_id: now_ts})
        await self._redis_client.hset(self._redis_queue_names.processing_payload, request_id, raw_message)

    async def _clear_processing_message(self, request_id: str) -> None:
        if self._redis_client is None:
            return
        await self._redis_client.zrem(self._redis_queue_names.processing_meta, request_id)
        await self._redis_client.hdel(self._redis_queue_names.processing_payload, request_id)

    async def _redis_reclaim_loop(self) -> None:
        if self._redis_client is None:
            return
        while True:
            try:
                await asyncio.sleep(self.config.reclaim_interval_seconds)
                await self._reclaim_stuck_processing_messages()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                self._last_error = f'Redis reclaim failed: {exc}'

    async def _reclaim_stuck_processing_messages(self) -> None:
        if self._redis_client is None:
            return
        threshold = datetime.now(timezone.utc).timestamp() - self.config.processing_timeout_seconds
        stuck_ids = await self._redis_client.zrangebyscore(self._redis_queue_names.processing_meta, 0, threshold)
        for request_id in stuck_ids:
            raw_message = await self._redis_client.hget(self._redis_queue_names.processing_payload, request_id)
            if not raw_message:
                await self._clear_processing_message(request_id)
                continue
            self._reclaim_count += 1
            await self._redis_client.lrem(self._redis_queue_names.processing, 1, raw_message)
            await self._redis_client.lpush(self._redis_queue_names.retry, raw_message)
            await self._redis_client.lmove(
                self._redis_queue_names.retry,
                self._redis_queue_names.main,
                "RIGHT",
                "LEFT",
            )
            await self._clear_processing_message(request_id)

routing_queue_service = RoutingQueueService()
