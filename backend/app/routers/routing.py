from sqlalchemy import asc, select
from fastapi import APIRouter, Depends, HTTPException

from ..deps import get_optional_user, get_session
from ..models.routing_rule import RoutingRule
from ..schemas.routing import (
    QueueDeadLetterRead,
    QueueMetricAggregateRead,
    QueueMetricRecordRead,
    RoutingClassifyRequest,
    RoutingClassifyResponse,
    RoutingQueueHealth,
    RoutingResolveRequest,
    RoutingRuleCreate,
    RoutingRuleRead,
    RoutingRuleUpdate,
    RoutingSummary,
)
from ..services.queue_metrics_service import (
    aggregate_routing_metrics,
    list_routing_dead_letters,
    list_routing_metrics,
)
from ..services.routing_queue_service import RoutingQueueError, routing_queue_service
from ..services.routing_service import classify_routing_request, resolve_routing_context

router = APIRouter(prefix='/api/routing', tags=['routing'])


@router.get('/rules', response_model=list[RoutingRuleRead])
async def list_rules(session=Depends(get_session), user=Depends(get_optional_user)):
    stmt = select(RoutingRule).where(RoutingRule.is_public.is_(True))
    if user:
        stmt = select(RoutingRule).where((RoutingRule.is_public.is_(True)) | (RoutingRule.owner_id == user.id))
    result = await session.execute(stmt.order_by(asc(RoutingRule.priority), asc(RoutingRule.id)))
    return list(result.scalars().all())


@router.get('/summary', response_model=RoutingSummary)
async def get_routing_summary(session=Depends(get_session), user=Depends(get_optional_user)):
    rules = await list_rules(session=session, user=user)
    categories = sorted({rule.category for rule in rules if rule.category}) or ['general']
    channels = sorted({rule.channel for rule in rules if rule.channel}) or ['dashboard']
    return RoutingSummary(
        categories=categories,
        channels=channels,
        rule_count=len(rules),
        enabled_count=sum(1 for rule in rules if rule.enabled),
    )


@router.get('/queue/health', response_model=RoutingQueueHealth)
async def get_queue_health(_user=Depends(get_optional_user)):
    return await routing_queue_service.get_health()


@router.get('/queue/dead-letters', response_model=list[QueueDeadLetterRead])
async def get_routing_dead_letters(limit: int = 20, _user=Depends(get_optional_user)):
    rows = await list_routing_dead_letters(limit=limit)
    return [
        QueueDeadLetterRead(
            request_id=row.request_id,
            queue_backend=row.queue_backend,
            error_code=row.error_code,
            error_message=row.error_message,
            attempts=row.attempts,
            created_at=row.created_at,
            last_attempt_at=row.last_attempt_at,
            wait_time_ms=row.wait_time_ms,
        )
        for row in rows
    ]


@router.get('/queue/metrics', response_model=list[QueueMetricRecordRead])
async def get_routing_metrics(limit: int = 50, _user=Depends(get_optional_user)):
    rows = await list_routing_metrics(limit=limit)
    return [
        QueueMetricRecordRead(
            request_id=row.request_id,
            queue_backend=row.queue_backend,
            status=row.status,
            duration_ms=row.duration_ms,
            wait_time_ms=row.wait_time_ms,
            attempts=row.attempts,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.get('/queue/metrics/aggregate', response_model=list[QueueMetricAggregateRead])
async def get_routing_metrics_aggregate(limit: int = 200, _user=Depends(get_optional_user)):
    rows = await aggregate_routing_metrics(limit=limit)
    return [QueueMetricAggregateRead(**row) for row in rows]


@router.post('/rules', response_model=RoutingRuleRead)
async def create_rule(payload: RoutingRuleCreate, session=Depends(get_session), user=Depends(get_optional_user)):
    if not user:
        raise HTTPException(status_code=401, detail='Not authenticated')
    rule = RoutingRule(owner_id=user.id, **payload.model_dump())
    session.add(rule)
    await session.commit()
    await session.refresh(rule)
    return rule


@router.patch('/rules/{rule_id}', response_model=RoutingRuleRead)
async def update_rule(rule_id: int, payload: RoutingRuleUpdate, session=Depends(get_session), user=Depends(get_optional_user)):
    if not user:
        raise HTTPException(status_code=401, detail='Not authenticated')
    rule = await session.get(RoutingRule, rule_id)
    if not rule or (rule.owner_id not in {None, user.id} and not rule.is_public):
        raise HTTPException(status_code=404, detail='Rule not found')
    if rule.owner_id not in {None, user.id}:
        raise HTTPException(status_code=403, detail='Rule is not editable')
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(rule, key, value)
    session.add(rule)
    await session.commit()
    await session.refresh(rule)
    return rule


@router.post('/resolve', response_model=RoutingClassifyResponse)
async def resolve_routing_context_endpoint(
    payload: RoutingResolveRequest,
    session=Depends(get_session),
    user=Depends(get_optional_user),
):
    user_id = user.id if user else None
    return await resolve_routing_context(payload, session=session, user_id=user_id)


@router.post('/classify', response_model=RoutingClassifyResponse)
async def classify_message(payload: RoutingClassifyRequest, session=Depends(get_session), user=Depends(get_optional_user)):
    user_id = user.id if user else None
    if not routing_queue_service.config.execute_through_queue:
        return await classify_routing_request(payload, session=session, user_id=user_id)
    try:
        return await routing_queue_service.classify(payload, user_id=user_id)
    except RoutingQueueError as exc:
        status_code = 504 if exc.code == 'ROUTING_QUEUE_TIMEOUT' else 503
        raise HTTPException(status_code=status_code, detail=exc.message) from exc
