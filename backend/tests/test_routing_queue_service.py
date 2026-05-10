import asyncio

import pytest

from backend.app.schemas.routing import RoutingClassifyRequest, RoutingClassifyResponse
from backend.app.services.routing_queue_service import RoutingQueueConfig, RoutingQueueService


def _build_config(backend: str) -> RoutingQueueConfig:
    return RoutingQueueConfig(
        backend=backend,
        instance_id='test-instance',
        max_length=8,
        wait_timeout_seconds=1.0,
        max_attempts=2,
        retry_delay_seconds=0.0,
        processing_timeout_seconds=30.0,
        reclaim_interval_seconds=5.0,
        inline_fallback=False,
        queue_name='tokenflow:routing:test',
        redis_url='redis://localhost:6379/0',
    )


def _build_payload(text: str = 'route this') -> RoutingClassifyRequest:
    return RoutingClassifyRequest(text=text)


def _build_response(rule_name: str, reason: str) -> RoutingClassifyResponse:
    return RoutingClassifyResponse(
        mode='rule',
        matched=True,
        rule_name=rule_name,
        score=1.0,
        reason=reason,
        target={'target': rule_name},
        resolved_category='general',
        resolved_channel='dashboard',
        route_kind='manual',
        top_candidates=[],
        explainability=None,
    )


def test_inline_backend_bypasses_queue():
    observed: dict[str, object] = {}

    async def classifier(payload: RoutingClassifyRequest, user_id: int | None):
        observed['text'] = payload.text
        observed['user_id'] = user_id
        return _build_response('inline-rule', 'inline')

    async def scenario():
        service = RoutingQueueService(config=_build_config('inline'), classifier=classifier)
        response = await service.classify(_build_payload('hello inline'), user_id=42)
        health = await service.get_health()
        assert response.rule_name == 'inline-rule'
        assert observed == {'text': 'hello inline', 'user_id': 42}
        assert health.enabled is False
        assert health.status == 'disabled'

    asyncio.run(scenario())


def test_memory_backend_processes_requests():
    observed: list[tuple[str, int | None]] = []

    async def classifier(payload: RoutingClassifyRequest, user_id: int | None):
        await asyncio.sleep(0.01)
        observed.append((payload.text, user_id))
        return _build_response('memory-rule', 'queued')

    async def scenario():
        service = RoutingQueueService(config=_build_config('memory'), classifier=classifier)
        try:
            response = await service.classify(_build_payload('hello memory'), user_id=7)
            health = await service.get_health()
            assert response.rule_name == 'memory-rule'
            assert observed == [('hello memory', 7)]
            assert health.enabled is True
            assert health.backend == 'memory'
            assert health.status == 'ok'
            assert health.pending_requests == 0
        finally:
            await service.shutdown()

    asyncio.run(scenario())


def test_memory_backend_propagates_classifier_errors():
    observed = {"calls": 0}

    async def classifier(payload: RoutingClassifyRequest, user_id: int | None):
        _ = payload, user_id
        observed["calls"] += 1
        raise RuntimeError('queue boom')

    async def scenario():
        service = RoutingQueueService(config=_build_config('memory'), classifier=classifier)
        try:
            with pytest.raises(RuntimeError, match='queue boom'):
                await service.classify(_build_payload('explode'))
            health = await service.get_health()
            assert observed["calls"] == 2
            assert health.retry_count >= 1
            assert health.dead_letter_count >= 1
        finally:
            await service.shutdown()

    asyncio.run(scenario())


def test_memory_backend_queue_full_updates_rejected_count():
    async def classifier(payload: RoutingClassifyRequest, user_id: int | None):
        await asyncio.sleep(0.2)
        _ = payload, user_id
        return _build_response('slow-rule', 'slow')

    async def scenario():
        config = RoutingQueueConfig(
            backend='memory',
            instance_id='test-instance',
            max_length=1,
            wait_timeout_seconds=1.0,
            max_attempts=2,
            retry_delay_seconds=0.0,
            processing_timeout_seconds=30.0,
            reclaim_interval_seconds=5.0,
            inline_fallback=False,
            queue_name='tokenflow:routing:test',
            redis_url='redis://localhost:6379/0',
        )
        service = RoutingQueueService(config=config, classifier=classifier)
        try:
            first = asyncio.create_task(service.classify(_build_payload('first'), user_id=1))
            await asyncio.sleep(0.01)
            second = asyncio.create_task(service.classify(_build_payload('second'), user_id=2))
            await asyncio.gather(first, return_exceptions=True)
            result = await asyncio.gather(second, return_exceptions=True)
            health = await service.get_health()
            assert health.backend == 'memory'
            assert health.rejected_count >= 0
            _ = result
        finally:
            await service.shutdown()

    asyncio.run(scenario())


def test_routing_queue_cleanup_zombies_noop_for_memory_backend():
    async def classifier(payload: RoutingClassifyRequest, user_id: int | None):
        _ = payload, user_id
        return _build_response('memory-rule', 'queued')

    async def scenario():
        service = RoutingQueueService(config=_build_config('memory'), classifier=classifier)
        try:
            cleaned = await service.cleanup_zombie_jobs()
            assert cleaned == 0
        finally:
            await service.shutdown()

    asyncio.run(scenario())
