from __future__ import annotations

import asyncio
import json
import threading
from dataclasses import dataclass
from time import monotonic
from typing import Any, Awaitable, Callable, Generic, TypeVar


@dataclass(frozen=True)
class QueueHealthSnapshot:
    enabled: bool
    backend: str
    instance_id: str
    status: str
    queue_name: str | None = None
    processing_queue_name: str | None = None
    retry_queue_name: str | None = None
    dead_letter_queue_name: str | None = None
    processing_meta_name: str | None = None
    processing_payload_name: str | None = None
    topic: str | None = None
    producer_group: str | None = None
    consumer_group: str | None = None
    queue_depth: int | None = 0
    processing_queue_depth: int | None = 0
    retry_queue_depth: int | None = 0
    dead_letter_queue_depth: int | None = 0
    stuck_processing_count: int = 0
    pending_requests: int = 0
    worker_concurrency: int | None = None
    max_attempts: int | None = None
    retry_delay_seconds: float | None = None
    dead_letter_count: int = 0
    rejected_count: int = 0
    retry_count: int = 0
    reclaim_count: int = 0
    last_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "backend": self.backend,
            "instance_id": self.instance_id,
            "status": self.status,
            "queue_name": self.queue_name,
            "processing_queue_name": self.processing_queue_name,
            "retry_queue_name": self.retry_queue_name,
            "dead_letter_queue_name": self.dead_letter_queue_name,
            "processing_meta_name": self.processing_meta_name,
            "processing_payload_name": self.processing_payload_name,
            "topic": self.topic,
            "producer_group": self.producer_group,
            "consumer_group": self.consumer_group,
            "queue_depth": self.queue_depth,
            "processing_queue_depth": self.processing_queue_depth,
            "retry_queue_depth": self.retry_queue_depth,
            "dead_letter_queue_depth": self.dead_letter_queue_depth,
            "stuck_processing_count": self.stuck_processing_count,
            "pending_requests": self.pending_requests,
            "worker_concurrency": self.worker_concurrency,
            "max_attempts": self.max_attempts,
            "retry_delay_seconds": self.retry_delay_seconds,
            "dead_letter_count": self.dead_letter_count,
            "rejected_count": self.rejected_count,
            "retry_count": self.retry_count,
            "reclaim_count": self.reclaim_count,
            "last_error": self.last_error,
        }


@dataclass(frozen=True)
class RedisQueueNames:
    main: str
    processing: str
    retry: str
    dead_letter: str
    processing_meta: str
    processing_payload: str


def build_redis_queue_names(base_name: str) -> RedisQueueNames:
    normalized = base_name.strip() or "tokenflow:queue"
    return RedisQueueNames(
        main=normalized,
        processing=f"{normalized}:processing",
        retry=f"{normalized}:retry",
        dead_letter=f"{normalized}:dead-letter",
        processing_meta=f"{normalized}:processing:meta",
        processing_payload=f"{normalized}:processing:payload",
    )


def encode_queue_message(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def decode_queue_message(raw: str) -> dict[str, Any]:
    return json.loads(raw)


class BaseQueueError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class DistributedLockAdapter:
    async def acquire(self, key: str, ttl_seconds: int) -> bool:
        raise NotImplementedError

    async def release(self, key: str) -> None:
        raise NotImplementedError


class InMemoryLockAdapter(DistributedLockAdapter):
    def __init__(self) -> None:
        self._items: dict[str, float] = {}
        self._lock = threading.Lock()

    async def acquire(self, key: str, ttl_seconds: int) -> bool:
        now = monotonic()
        with self._lock:
            expired_keys = [item_key for item_key, expires_at in self._items.items() if expires_at <= now]
            for expired_key in expired_keys:
                self._items.pop(expired_key, None)
            if key in self._items:
                return False
            self._items[key] = now + max(1, ttl_seconds)
            return True

    async def release(self, key: str) -> None:
        with self._lock:
            self._items.pop(key, None)


class RedisLockAdapter(DistributedLockAdapter):
    def __init__(self, redis_url: str) -> None:
        self.redis_url = redis_url
        self._client = None

    async def _get_client(self):
        if self._client is None:
            try:
                from redis.asyncio import Redis
            except Exception as exc:  # pragma: no cover - dependency/environment specific
                raise RuntimeError("redis dependency is not available") from exc
            self._client = Redis.from_url(self.redis_url, encoding="utf-8", decode_responses=True)
        return self._client

    async def acquire(self, key: str, ttl_seconds: int) -> bool:
        client = await self._get_client()
        return bool(await client.set(key, "1", ex=ttl_seconds, nx=True))

    async def release(self, key: str) -> None:
        client = await self._get_client()
        await client.delete(key)


ResponseT = TypeVar("ResponseT")


class BaseAsyncQueueService(Generic[ResponseT]):
    def __init__(self) -> None:
        self._startup_lock = asyncio.Lock()
        self._pending_lock = threading.Lock()
        self._pending: dict[str, asyncio.Future[ResponseT]] = {}
        self._started = False
        self._last_error: str | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._rejected_count = 0

    def _status_from_runtime(self, backend: str) -> str:
        if backend == "inline":
            return "disabled"
        if self._started and not self._last_error:
            return "ok"
        if self._last_error:
            return "degraded"
        return "starting"

    def _register_future(self, request_id: str, max_length: int | None = None) -> asyncio.Future[ResponseT]:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[ResponseT] = loop.create_future()
        with self._pending_lock:
            if max_length is not None and len(self._pending) >= max_length:
                raise OverflowError("queue is full")
            self._pending[request_id] = future
        return future

    def _drop_future(self, request_id: str) -> asyncio.Future[ResponseT] | None:
        with self._pending_lock:
            return self._pending.pop(request_id, None)

    def _complete_future(self, request_id: str, response: ResponseT) -> None:
        future = self._drop_future(request_id)
        if future is None:
            return
        loop = future.get_loop()

        def _set_result() -> None:
            if not future.done():
                future.set_result(response)

        loop.call_soon_threadsafe(_set_result)

    def _fail_future(self, request_id: str, exc: Exception) -> None:
        future = self._drop_future(request_id)
        if future is None:
            return
        loop = future.get_loop()

        def _set_exception() -> None:
            if not future.done():
                future.set_exception(exc)

        loop.call_soon_threadsafe(_set_exception)

    def _fail_all_pending(self, exc: Exception) -> None:
        with self._pending_lock:
            pending = list(self._pending.items())
            self._pending.clear()
        for _, future in pending:
            loop = future.get_loop()

            def _set_exception(target_future: asyncio.Future[ResponseT] = future) -> None:
                if not target_future.done():
                    target_future.set_exception(exc)

            loop.call_soon_threadsafe(_set_exception)

    def _pending_count(self) -> int:
        with self._pending_lock:
            return len(self._pending)

    def _build_health_snapshot(
        self,
        *,
        enabled: bool,
        backend: str,
        instance_id: str,
        queue_name: str | None = None,
        processing_queue_name: str | None = None,
        retry_queue_name: str | None = None,
        dead_letter_queue_name: str | None = None,
        processing_meta_name: str | None = None,
        processing_payload_name: str | None = None,
        topic: str | None = None,
        producer_group: str | None = None,
        consumer_group: str | None = None,
        queue_depth: int | None = 0,
        processing_queue_depth: int | None = 0,
        retry_queue_depth: int | None = 0,
        dead_letter_queue_depth: int | None = 0,
        stuck_processing_count: int = 0,
        pending_requests: int | None = None,
        worker_concurrency: int | None = None,
        max_attempts: int | None = None,
        retry_delay_seconds: float | None = None,
        dead_letter_count: int = 0,
        rejected_count: int | None = None,
        retry_count: int = 0,
        reclaim_count: int = 0,
        last_error: str | None = None,
    ) -> QueueHealthSnapshot:
        return QueueHealthSnapshot(
            enabled=enabled,
            backend=backend,
            instance_id=instance_id,
            status=self._status_from_runtime(backend),
            queue_name=queue_name,
            processing_queue_name=processing_queue_name,
            retry_queue_name=retry_queue_name,
            dead_letter_queue_name=dead_letter_queue_name,
            processing_meta_name=processing_meta_name,
            processing_payload_name=processing_payload_name,
            topic=topic,
            producer_group=producer_group,
            consumer_group=consumer_group,
            queue_depth=queue_depth,
            processing_queue_depth=processing_queue_depth,
            retry_queue_depth=retry_queue_depth,
            dead_letter_queue_depth=dead_letter_queue_depth,
            stuck_processing_count=stuck_processing_count,
            pending_requests=self._pending_count() if pending_requests is None else pending_requests,
            worker_concurrency=worker_concurrency,
            max_attempts=max_attempts,
            retry_delay_seconds=retry_delay_seconds,
            dead_letter_count=dead_letter_count,
            rejected_count=self._rejected_count if rejected_count is None else rejected_count,
            retry_count=retry_count,
            reclaim_count=reclaim_count,
            last_error=self._last_error if last_error is None else last_error,
        )

    async def _shutdown_memory_worker(self, worker: "AsyncMemoryWorker[Any] | None") -> None:
        if worker is None:
            return
        await worker.stop()

    async def _startup_lifecycle(self) -> None:
        async with self._startup_lock:
            if self._started:
                return
            self._loop = asyncio.get_running_loop()
            self._last_error = None
            await self._startup_backend()
            self._started = True

    async def _shutdown_lifecycle(self, stop_exc: Exception) -> None:
        async with self._startup_lock:
            await self._shutdown_backend()
            self._started = False
            self._loop = None
            self._fail_all_pending(stop_exc)

    async def _startup_backend(self) -> None:
        raise NotImplementedError

    async def _shutdown_backend(self) -> None:
        raise NotImplementedError

    async def _submit_and_wait(
        self,
        *,
        request_id: str,
        max_length: int,
        wait_timeout_seconds: float,
        queue_full_exc_factory: Callable[[], Exception],
        timeout_exc_factory: Callable[[], Exception],
        enqueue_coro_factory: Callable[[], Awaitable[None]],
        on_enqueue_error: Callable[[Exception], Awaitable[None]] | None = None,
    ) -> ResponseT:
        try:
            future = self._register_future(request_id, max_length=max_length)
        except OverflowError as exc:
            self._rejected_count += 1
            raise queue_full_exc_factory() from exc

        try:
            await enqueue_coro_factory()
        except Exception as exc:  # noqa: BLE001
            self._drop_future(request_id)
            if on_enqueue_error is not None:
                await on_enqueue_error(exc)
            raise

        try:
            return await asyncio.wait_for(future, timeout=wait_timeout_seconds)
        except asyncio.TimeoutError as exc:
            self._drop_future(request_id)
            raise timeout_exc_factory() from exc


ItemT = TypeVar("ItemT")


class AsyncMemoryWorker(Generic[ItemT]):
    def __init__(
        self,
        handler: Callable[[ItemT], Awaitable[None]],
        *,
        concurrency: int = 1,
        maxsize: int = 0,
        name_prefix: str = "queue-worker",
    ) -> None:
        self._handler = handler
        self._concurrency = max(1, concurrency)
        self._maxsize = maxsize
        self._name_prefix = name_prefix
        self._queue: asyncio.Queue[ItemT | None] | None = None
        self._tasks: list[asyncio.Task[None]] = []

    async def start(self) -> None:
        if self._queue is not None:
            return
        self._queue = asyncio.Queue(maxsize=self._maxsize)
        self._tasks = [
            asyncio.create_task(self._loop(), name=f"{self._name_prefix}-{index}")
            for index in range(self._concurrency)
        ]

    async def stop(self) -> None:
        if self._queue is None:
            return
        for _ in self._tasks:
            await self._queue.put(None)
        for task in self._tasks:
            await task
        self._queue = None
        self._tasks = []

    async def submit(self, item: ItemT) -> None:
        if self._queue is None:
            raise RuntimeError("memory worker is not started")
        self._queue.put_nowait(item)

    def qsize(self) -> int:
        if self._queue is None:
            return 0
        return self._queue.qsize()

    async def _loop(self) -> None:
        assert self._queue is not None
        while True:
            item = await self._queue.get()
            try:
                if item is None:
                    return
                await self._handler(item)
            finally:
                self._queue.task_done()
