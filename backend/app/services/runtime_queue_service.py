from __future__ import annotations

import asyncio
import os
from time import perf_counter
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from .queue_shared import (
    AsyncMemoryWorker,
    BaseAsyncQueueService,
    BaseQueueError,
    DistributedLockAdapter,
    InMemoryLockAdapter,
    QueueHealthSnapshot,
    RedisLockAdapter,
    build_redis_queue_names,
    decode_queue_message,
    encode_queue_message,
)
from .runtime_queue_store import compute_wait_time_ms, record_runtime_metric
from ..schemas.model_runtime import NodeExecutionRequest, NodeExecutionResponse


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    raw = os.environ.get(name)
    try:
        value = int(raw) if raw is not None else default
    except (TypeError, ValueError):
        value = default
    return max(minimum, value)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class RuntimeQueueConfig:
    backend: str
    instance_id: str
    max_length: int
    wait_timeout_seconds: float
    queue_name: str
    lock_prefix: str
    worker_concurrency: int
    max_attempts: int
    retry_delay_seconds: float
    processing_timeout_seconds: float
    reclaim_interval_seconds: float
    inline_fallback: bool
    redis_url: str
    lock_ttl_seconds: int

    @classmethod
    def from_env(cls) -> "RuntimeQueueConfig":
        backend = (os.environ.get("TOKENFLOW_RUNTIME_QUEUE_BACKEND", "memory").strip().lower() or "memory")
        if backend not in {"inline", "memory", "redis"}:
            backend = "memory"
        instance_id = os.environ.get("TOKENFLOW_RUNTIME_QUEUE_INSTANCE_ID", "").strip() or uuid.uuid4().hex[:12]
        wait_timeout_ms = _env_int("TOKENFLOW_RUNTIME_QUEUE_WAIT_TIMEOUT_MS", 30000, minimum=100)
        return cls(
            backend=backend,
            instance_id=instance_id,
            max_length=_env_int("TOKENFLOW_RUNTIME_QUEUE_MAX_LENGTH", 128, minimum=1),
            wait_timeout_seconds=wait_timeout_ms / 1000.0,
            queue_name=os.environ.get("TOKENFLOW_RUNTIME_QUEUE_NAME", "tokenflow:runtime:jobs").strip() or "tokenflow:runtime:jobs",
            lock_prefix=os.environ.get("TOKENFLOW_RUNTIME_LOCK_PREFIX", "tokenflow:runtime:lock").strip() or "tokenflow:runtime:lock",
            worker_concurrency=_env_int("TOKENFLOW_RUNTIME_WORKER_CONCURRENCY", 2, minimum=1),
            max_attempts=_env_int("TOKENFLOW_RUNTIME_QUEUE_MAX_ATTEMPTS", 3, minimum=1),
            retry_delay_seconds=_env_int("TOKENFLOW_RUNTIME_QUEUE_RETRY_DELAY_MS", 250, minimum=0) / 1000.0,
            processing_timeout_seconds=_env_int("TOKENFLOW_RUNTIME_PROCESSING_TIMEOUT_MS", 30000, minimum=1000) / 1000.0,
            reclaim_interval_seconds=_env_int("TOKENFLOW_RUNTIME_RECLAIM_INTERVAL_MS", 5000, minimum=500) / 1000.0,
            inline_fallback=_env_bool("TOKENFLOW_RUNTIME_QUEUE_INLINE_FALLBACK", default=True),
            redis_url=os.environ.get("TOKENFLOW_REDIS_URL", "redis://localhost:6379/0").strip() or "redis://localhost:6379/0",
            lock_ttl_seconds=_env_int("TOKENFLOW_RUNTIME_LOCK_TTL_SECONDS", 60, minimum=1),
        )

    @property
    def execute_through_queue(self) -> bool:
        return self.backend in {"memory", "redis"}


@dataclass(frozen=True)
class QueuedRuntimeRequest:
    request_id: str
    instance_id: str
    submitted_at: str
    payload: NodeExecutionRequest
    attempts: int = 0


class RuntimeQueueError(BaseQueueError):
    pass


class RuntimeQueueService(BaseAsyncQueueService[NodeExecutionResponse]):
    def __init__(
        self,
        config: RuntimeQueueConfig | None = None,
        executor: Callable[[NodeExecutionRequest], Awaitable[NodeExecutionResponse]] | None = None,
    ) -> None:
        super().__init__()
        self.config = config or RuntimeQueueConfig.from_env()
        self._executor = executor
        self._memory_queue: asyncio.Queue[QueuedRuntimeRequest | None] | None = None
        self._memory_worker: AsyncMemoryWorker[QueuedRuntimeRequest] | None = None
        self._dead_letter_count = 0
        self._retry_count = 0
        self._reclaim_count = 0
        self._persistence_tasks: set[asyncio.Task[None]] = set()
        self._lock_adapter: DistributedLockAdapter = (
            RedisLockAdapter(self.config.redis_url) if self.config.backend == "redis" else InMemoryLockAdapter()
        )
        self._redis_queue_names = build_redis_queue_names(self.config.queue_name)
        self._redis_client = None
        self._redis_consumer_tasks: list[asyncio.Task[None]] = []
        self._redis_reclaim_task: asyncio.Task[None] | None = None

    async def startup(self) -> None:
        await self._startup_lifecycle()

    async def shutdown(self) -> None:
        await self._shutdown_lifecycle(
            RuntimeQueueError("RUNTIME_QUEUE_STOPPED", "Runtime queue service stopped")
        )

    async def _startup_backend(self) -> None:
        if self._executor is None:
            from .runtime_service import execute_node

            self._executor = execute_node
        if self.config.backend == "memory":
            self._memory_worker = AsyncMemoryWorker(
                self._process_memory_envelope,
                concurrency=self.config.worker_concurrency,
                maxsize=self.config.max_length,
                name_prefix="tokenflow-runtime-worker",
            )
            await self._memory_worker.start()
        elif self.config.backend == "redis":
            await self._startup_redis()
            self._redis_consumer_tasks = [
                asyncio.create_task(self._redis_consumer_loop(), name=f"tokenflow-runtime-redis-{index}")
                for index in range(self.config.worker_concurrency)
            ]
            self._redis_reclaim_task = asyncio.create_task(
                self._redis_reclaim_loop(),
                name="tokenflow-runtime-redis-reclaim",
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

    async def execute(self, payload: NodeExecutionRequest) -> NodeExecutionResponse:
        if not self.config.execute_through_queue:
            assert self._executor is not None or True
            if self._executor is None:
                from .runtime_service import execute_node

                self._executor = execute_node
            return await self._executor(payload)

        await self.startup()
        request_id = payload.request_id or uuid.uuid4().hex
        envelope = QueuedRuntimeRequest(
            request_id=request_id,
            instance_id=self.config.instance_id,
            submitted_at=datetime.now(timezone.utc).isoformat(),
            payload=payload.model_copy(update={"request_id": request_id}),
        )
        lock_key = f"{self.config.lock_prefix}:{payload.node_id}:{request_id}"
        acquired = await self._lock_adapter.acquire(lock_key, ttl_seconds=self.config.lock_ttl_seconds)
        if not acquired:
            raise RuntimeQueueError("RUNTIME_QUEUE_DUPLICATE", "Runtime task is already executing")

        try:
            return await self._submit_and_wait(
                request_id=request_id,
                max_length=self.config.max_length,
                wait_timeout_seconds=self.config.wait_timeout_seconds,
                queue_full_exc_factory=lambda: RuntimeQueueError("RUNTIME_QUEUE_FULL", "Runtime queue is full"),
                timeout_exc_factory=lambda: RuntimeQueueError(
                    "RUNTIME_QUEUE_TIMEOUT",
                    f"Runtime queue timed out after {self.config.wait_timeout_seconds:.3f}s",
                ),
                enqueue_coro_factory=lambda: self._enqueue(envelope),
                on_enqueue_error=lambda exc: self._handle_enqueue_error(exc, envelope),
            )
        finally:
            await self._lock_adapter.release(lock_key)

    async def _handle_enqueue_error(self, exc: Exception, envelope: QueuedRuntimeRequest) -> None:
        if isinstance(exc, RuntimeQueueError) and exc.code == "RUNTIME_QUEUE_FULL":
            self._rejected_count += 1
        if self.config.inline_fallback:
            if self._executor is None:
                from .runtime_service import execute_node

                self._executor = execute_node
            response = await self._executor(envelope.payload)
            self._complete_future(envelope.request_id, response)
            return
        raise RuntimeQueueError("RUNTIME_QUEUE_UNAVAILABLE", f"Failed to enqueue runtime request: {exc}") from exc

    async def get_health(self) -> dict[str, Any]:
        processing_depth = retry_depth = dead_letter_depth = stuck_processing_count = None
        if self.config.backend == "redis" and self._redis_client is not None:
            try:
                processing_depth = await self._redis_client.llen(self._redis_queue_names.processing)
                retry_depth = await self._redis_client.llen(self._redis_queue_names.retry)
                dead_letter_depth = await self._redis_client.llen(self._redis_queue_names.dead_letter)
                stuck_processing_count = await self._redis_client.zcard(self._redis_queue_names.processing_meta)
            except Exception:
                processing_depth = retry_depth = dead_letter_depth = stuck_processing_count = None
        snapshot = self._build_health_snapshot(
            enabled=self.config.execute_through_queue,
            backend=self.config.backend,
            instance_id=self.config.instance_id,
            queue_name=self.config.queue_name if self.config.backend == "redis" else "memory",
            processing_queue_name=self._redis_queue_names.processing if self.config.backend == "redis" else None,
            retry_queue_name=self._redis_queue_names.retry if self.config.backend == "redis" else None,
            dead_letter_queue_name=self._redis_queue_names.dead_letter if self.config.backend == "redis" else None,
            processing_meta_name=self._redis_queue_names.processing_meta if self.config.backend == "redis" else None,
            processing_payload_name=self._redis_queue_names.processing_payload if self.config.backend == "redis" else None,
            queue_depth=self._memory_worker.qsize() if self.config.backend == "memory" and self._memory_worker else None,
            processing_queue_depth=processing_depth,
            retry_queue_depth=retry_depth,
            dead_letter_queue_depth=dead_letter_depth,
            stuck_processing_count=stuck_processing_count or 0,
            worker_concurrency=self.config.worker_concurrency,
            max_attempts=self.config.max_attempts,
            retry_delay_seconds=self.config.retry_delay_seconds,
            dead_letter_count=self._dead_letter_count,
            retry_count=self._retry_count,
            reclaim_count=self._reclaim_count,
        )
        return snapshot.to_dict()

    async def cleanup_zombie_jobs(self) -> int:
        before = self._reclaim_count
        await self._reclaim_stuck_processing_messages()
        return self._reclaim_count - before

    async def _startup_redis(self) -> None:
        try:
            from redis.asyncio import Redis
        except Exception as exc:  # pragma: no cover - dependency/environment specific
            raise RuntimeQueueError("RUNTIME_QUEUE_DRIVER_ERROR", "redis dependency is not available") from exc
        self._redis_client = Redis.from_url(self.config.redis_url, encoding="utf-8", decode_responses=True)

    async def _enqueue(self, envelope: QueuedRuntimeRequest) -> None:
        if self.config.backend == "memory":
            if self._memory_worker is None:
                raise RuntimeQueueError("RUNTIME_QUEUE_UNAVAILABLE", "Runtime memory worker is not started")
            await self._memory_worker.submit(envelope)
            return
        if self.config.backend == "redis":
            if self._redis_client is None:
                raise RuntimeQueueError("RUNTIME_QUEUE_UNAVAILABLE", "Runtime redis client is not started")
            payload = encode_queue_message(
                {
                    "request_id": envelope.request_id,
                    "instance_id": envelope.instance_id,
                    "submitted_at": envelope.submitted_at,
                    "attempts": envelope.attempts,
                    "payload": envelope.payload.model_dump(mode="json"),
                }
            )
            await self._redis_client.lpush(self._redis_queue_names.main, payload)
            return
        raise RuntimeQueueError("RUNTIME_QUEUE_CONFIG_ERROR", f"Unsupported backend: {self.config.backend}")

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
                self._last_error = f"Redis consumer failed: {exc}"
                await asyncio.sleep(0.2)
                continue
            if not item:
                continue
            raw = str(item)
            data = decode_queue_message(raw)
            envelope = QueuedRuntimeRequest(
                request_id=str(data["request_id"]),
                instance_id=str(data["instance_id"]),
                submitted_at=str(data["submitted_at"]),
                payload=NodeExecutionRequest.model_validate(data["payload"]),
                attempts=int(data.get("attempts", 0)),
            )
            await self._mark_processing_message(envelope.request_id, raw)
            await self._process_redis_envelope(envelope, raw_message=raw)

    async def _process_redis_envelope(self, envelope: QueuedRuntimeRequest, *, raw_message: str) -> None:
        assert self._executor is not None
        started = perf_counter()
        try:
            response = await self._executor(envelope.payload)
        except Exception as exc:  # noqa: BLE001
            await self._handle_retry_or_dead_letter(envelope, exc, started=started, raw_message=raw_message)
        else:
            await self._ack_processed_message(raw_message)
            await self._clear_processing_message(envelope.request_id)
            self._spawn_persistence_task(
                record_runtime_metric(
                    request_id=envelope.request_id,
                    queue_backend=self.config.backend,
                    status='ok',
                    duration_ms=max(0.0, (perf_counter() - started) * 1000.0),
                    wait_time_ms=compute_wait_time_ms(envelope.submitted_at),
                    attempts=max(1, envelope.attempts + 1),
                )
            )
            self._resolve_result(envelope.request_id, response)

    def _resolve_result(self, request_id: str, result: NodeExecutionResponse | Exception) -> None:
        if not isinstance(result, Exception):
            self._complete_future(request_id, result)
            return
        future = self._drop_future(request_id)
        if future is None:
            return
        loop = future.get_loop()

        def _complete() -> None:
            if future.done():
                return
            if isinstance(result, Exception):
                future.set_exception(result)
            else:
                future.set_result(result)

        loop.call_soon_threadsafe(_complete)

    async def _process_memory_envelope(self, envelope: QueuedRuntimeRequest) -> None:
        assert self._executor is not None
        started = perf_counter()
        try:
            response = await self._executor(envelope.payload)
        except Exception as exc:  # noqa: BLE001
            await self._handle_retry_or_dead_letter(envelope, exc, started=started)
            return
        self._spawn_persistence_task(
            record_runtime_metric(
                request_id=envelope.request_id,
                queue_backend=self.config.backend,
                status='ok',
                duration_ms=max(0.0, (perf_counter() - started) * 1000.0),
                wait_time_ms=compute_wait_time_ms(envelope.submitted_at),
                attempts=max(1, envelope.attempts + 1),
            )
        )
        self._resolve_result(envelope.request_id, response)

    async def _handle_retry_or_dead_letter(
        self,
        envelope: QueuedRuntimeRequest,
        exc: Exception,
        *,
        started: float,
        raw_message: str | None = None,
    ) -> None:
        attempts = envelope.attempts + 1
        if attempts < self.config.max_attempts:
            self._retry_count += 1
            retried = QueuedRuntimeRequest(
                request_id=envelope.request_id,
                instance_id=envelope.instance_id,
                submitted_at=envelope.submitted_at,
                payload=envelope.payload,
                attempts=attempts,
            )
            if self.config.retry_delay_seconds > 0:
                await asyncio.sleep(self.config.retry_delay_seconds)
            try:
                if self.config.backend == "redis" and self._redis_client is not None:
                    await self._redis_client.lpush(
                        self._redis_queue_names.retry,
                        encode_queue_message(
                            {
                                "request_id": retried.request_id,
                                "instance_id": retried.instance_id,
                                "submitted_at": retried.submitted_at,
                                "attempts": retried.attempts,
                                "payload": retried.payload.model_dump(mode="json"),
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
                    return
                await self._enqueue(retried)
                return
            except Exception as enqueue_exc:  # noqa: BLE001
                exc = enqueue_exc
        if self.config.backend == "redis" and self._redis_client is not None and raw_message is not None:
            await self._redis_client.lpush(self._redis_queue_names.dead_letter, raw_message)
            await self._ack_processed_message(raw_message)
            await self._clear_processing_message(envelope.request_id)
        await self._store_dead_letter(
            request_id=envelope.request_id,
            payload=envelope.payload,
            attempts=attempts,
            error_code=type(exc).__name__,
            error_message=str(exc),
            submitted_at=envelope.submitted_at,
        )
        self._spawn_persistence_task(
            record_runtime_metric(
                request_id=envelope.request_id,
                queue_backend=self.config.backend,
                status='failed',
                duration_ms=max(0.0, (perf_counter() - started) * 1000.0),
                wait_time_ms=compute_wait_time_ms(envelope.submitted_at),
                attempts=attempts,
            )
        )
        self._resolve_result(envelope.request_id, exc)

    async def _store_dead_letter(
        self,
        *,
        request_id: str,
        payload: NodeExecutionRequest,
        attempts: int,
        error_code: str,
        error_message: str,
        submitted_at: str,
    ) -> None:
        from ..db.session import AsyncSessionLocal
        from ..models.runtime_execution import RuntimeQueueDeadLetterRecord

        self._dead_letter_count += 1
        wait_time_ms = 0.0
        if submitted_at:
            try:
                submitted_dt = datetime.fromisoformat(submitted_at)
                wait_time_ms = max(0.0, (datetime.now(timezone.utc) - submitted_dt).total_seconds() * 1000.0)
            except Exception:
                wait_time_ms = 0.0
        async with AsyncSessionLocal() as session:
            session.add(
                RuntimeQueueDeadLetterRecord(
                    request_id=request_id,
                    node_id=payload.node_id,
                    queue_backend=self.config.backend,
                    error_code=error_code,
                    error_message=error_message,
                    attempts=attempts,
                    payload_json=payload.model_dump(mode="json"),
                    last_attempt_at=datetime.now(timezone.utc),
                    wait_time_ms=wait_time_ms,
                )
            )
            await session.commit()

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
                self._last_error = f"Redis reclaim failed: {exc}"

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


runtime_queue_service = RuntimeQueueService()
