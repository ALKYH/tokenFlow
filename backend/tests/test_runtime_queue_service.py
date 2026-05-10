import asyncio

from backend.app.schemas.model_runtime import NodeExecutionRequest, NodeExecutionResponse, RuntimeModuleSpec
from backend.app.services.runtime_queue_service import RuntimeQueueConfig, RuntimeQueueService


def _build_request(request_id: str = "req_runtime_queue") -> NodeExecutionRequest:
    return NodeExecutionRequest(
        protocol_version="1.0.0",
        request_id=request_id,
        node_id="runtime_node_1",
        node_type="python_snippet",
        execution_mode="python-module",
        module=RuntimeModuleSpec(
            source=(
                "def __tokenflow_node_entry(value, context, resources):\n"
                "    return value\n"
            ),
            function_name="__tokenflow_node_entry",
        ),
        inputs=["hello"],
        resources=[],
        env={},
    )


def _build_config(backend: str) -> RuntimeQueueConfig:
    return RuntimeQueueConfig(
        backend=backend,
        instance_id="test-runtime",
        max_length=8,
        wait_timeout_seconds=1.0,
        queue_name="tokenflow:runtime:test",
        lock_prefix="tokenflow:runtime:lock:test",
        worker_concurrency=1,
        max_attempts=3,
        retry_delay_seconds=0.0,
        processing_timeout_seconds=30.0,
        reclaim_interval_seconds=5.0,
        inline_fallback=True,
        redis_url="redis://localhost:6379/0",
        lock_ttl_seconds=30,
    )


def test_runtime_queue_memory_backend_executes():
    async def executor(payload: NodeExecutionRequest) -> NodeExecutionResponse:
        return NodeExecutionResponse(
            protocol_version=payload.protocol_version,
            request_id=payload.request_id,
            status="ok",
            output=payload.inputs[0] if payload.inputs else None,
            logs=["queue executed"],
        )

    async def scenario():
        service = RuntimeQueueService(config=_build_config("memory"), executor=executor)
        try:
            response = await service.execute(_build_request())
            health = await service.get_health()
            assert response.status == "ok"
            assert response.output == "hello"
            assert response.logs == ["queue executed"]
            assert health["backend"] == "memory"
            assert health["pending_requests"] == 0
        finally:
            await service.shutdown()

    asyncio.run(scenario())


def test_runtime_queue_memory_backend_retries_before_success():
    observed = {"calls": 0}

    async def executor(payload: NodeExecutionRequest) -> NodeExecutionResponse:
        _ = payload
        observed["calls"] += 1
        if observed["calls"] < 3:
            raise RuntimeError("retry me")
        return NodeExecutionResponse(
            protocol_version="1.0.0",
            request_id=payload.request_id,
            status="ok",
            output="retried-ok",
        )

    async def scenario():
        service = RuntimeQueueService(config=_build_config("memory"), executor=executor)
        try:
            response = await service.execute(_build_request("req_retry"))
            health = await service.get_health()
            assert response.status == "ok"
            assert response.output == "retried-ok"
            assert observed["calls"] == 3
            assert health["retry_count"] == 2
            assert health["dead_letter_count"] == 0
        finally:
            await service.shutdown()

    asyncio.run(scenario())


def test_runtime_queue_inline_backend_bypasses_queue():
    observed: dict[str, str] = {}

    async def executor(payload: NodeExecutionRequest) -> NodeExecutionResponse:
        observed["request_id"] = payload.request_id or ""
        return NodeExecutionResponse(
            protocol_version=payload.protocol_version,
            request_id=payload.request_id,
            status="ok",
            output="inline",
        )

    async def scenario():
        service = RuntimeQueueService(config=_build_config("inline"), executor=executor)
        response = await service.execute(_build_request("req_inline"))
        assert response.status == "ok"
        assert response.output == "inline"
        assert observed["request_id"] == "req_inline"

    asyncio.run(scenario())


def test_runtime_queue_duplicate_request_is_rejected():
    gate = asyncio.Event()
    release = asyncio.Event()

    async def executor(payload: NodeExecutionRequest) -> NodeExecutionResponse:
        gate.set()
        await release.wait()
        return NodeExecutionResponse(
            protocol_version=payload.protocol_version,
            request_id=payload.request_id,
            status="ok",
            output="ok",
        )

    async def scenario():
        service = RuntimeQueueService(config=_build_config("memory"), executor=executor)
        try:
            request = _build_request("dup-1")
            first = asyncio.create_task(service.execute(request))
            await gate.wait()
            second = await asyncio.gather(service.execute(request), return_exceptions=True)
            release.set()
            await first
            assert isinstance(second[0], Exception)
            assert getattr(second[0], "code", "") == "RUNTIME_QUEUE_DUPLICATE"
        finally:
            await service.shutdown()

    asyncio.run(scenario())


def test_runtime_queue_cleanup_zombies_noop_for_memory_backend():
    async def executor(payload: NodeExecutionRequest) -> NodeExecutionResponse:
        return NodeExecutionResponse(
            protocol_version=payload.protocol_version,
            request_id=payload.request_id,
            status="ok",
            output=payload.inputs[0] if payload.inputs else None,
        )

    async def scenario():
        service = RuntimeQueueService(config=_build_config("memory"), executor=executor)
        try:
            cleaned = await service.cleanup_zombie_jobs()
            assert cleaned == 0
        finally:
            await service.shutdown()

    asyncio.run(scenario())
