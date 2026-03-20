from typing import Any
import httpx
from sqlalchemy import asc, select
from fastapi import APIRouter, Depends
from ..deps import get_optional_user, get_session
from ..models.routing_rule import RoutingRule
from ..schemas.routing import RoutingClassifyRequest, RoutingClassifyResponse, RoutingResolveRequest, RoutingRuleRead
from ..services.secret_service import build_runtime_secret, resolve_user_secret

router = APIRouter(prefix='/api/routing', tags=['routing'])

FILE_TYPE_ROUTE_MAP = {
    'workspace': ('workspace', 'editor'),
    'module': ('marketplace', 'editor'),
    'plugin': ('marketplace', 'community'),
    'workflow': ('routing', 'editor'),
    'knowledge': ('knowledge', 'api'),
    'pdf': ('knowledge', 'api'),
    'image': ('vision', 'api'),
    'audio': ('speech', 'api')
}


def _resolve_category_and_channel(payload: RoutingResolveRequest, runtime_secret: dict) -> tuple[str, str, str]:
    if payload.category and payload.channel:
        return payload.category, payload.channel, 'manual'

    file_type = (payload.file_type or '').strip().lower()
    if file_type in FILE_TYPE_ROUTE_MAP:
        category, channel = FILE_TYPE_ROUTE_MAP[file_type]
        return payload.category or category, payload.channel or channel, 'file-type'

    provider = str(runtime_secret.get('provider') or '').lower()
    prefix = str(runtime_secret.get('request_prefix') or '').lower()
    if 'embedding' in prefix or 'vector' in prefix:
        return payload.category or 'knowledge', payload.channel or 'api', 'api'
    if provider in {'openai', 'azure-openai', 'anthropic', 'custom'}:
        return payload.category or 'routing', payload.channel or 'api', 'api'
    return payload.category or 'general', payload.channel or 'dashboard', 'fallback'


def _match_rule(rule: RoutingRule, text: str) -> tuple[bool, float, str]:
    normalized = (text or '').lower()
    keywords = [str(item).lower() for item in (rule.matcher_config or {}).get('keywords', [])]
    if not keywords:
        return False, 0, 'No keywords configured'
    hits = [keyword for keyword in keywords if keyword and keyword in normalized]
    if not hits:
        return False, 0, 'No keyword hit'
    score = min(1.0, len(hits) / max(1, len(keywords)))
    return True, score, f"Matched keywords: {', '.join(hits[:4])}"


async def _classify_with_ai(
    payload: RoutingClassifyRequest,
    rules: list[RoutingRule],
    runtime_secret: dict,
    resolved_category: str,
    resolved_channel: str,
    route_kind: str
) -> RoutingClassifyResponse | None:
    ai_endpoint = payload.ai_endpoint or runtime_secret.get('request_prefix')
    if not ai_endpoint:
        return None
    prompt_rules = [
        {
            'name': rule.name,
            'category': rule.category,
            'channel': rule.channel,
            'action': rule.action_config
        }
        for rule in rules
    ]
    body: dict[str, Any] = {
        'model': payload.model or 'gpt-4o-mini',
        'messages': [
            {
                'role': 'system',
                'content': 'Classify the message to the best routing rule and return JSON with rule_name, reason, score.'
            },
            {
                'role': 'user',
                'content': {
                    'category': resolved_category,
                    'channel': resolved_channel,
                    'text': payload.text,
                    'rules': prompt_rules
                }
            }
        ]
    }
    headers = {'Content-Type': 'application/json'}
    auth_key = payload.api_key or runtime_secret.get('api_key')
    if auth_key:
        headers['Authorization'] = f'Bearer {auth_key}'
    async with httpx.AsyncClient(timeout=18.0) as client:
        response = await client.post(ai_endpoint, json=body, headers=headers)
        response.raise_for_status()
        data = response.json()
    content = ''
    try:
        content = data['choices'][0]['message']['content']
    except Exception:
        content = str(data)
    for rule in rules:
        if rule.name in content:
            return RoutingClassifyResponse(
                mode='ai',
                matched=True,
                rule_name=rule.name,
                score=0.88,
                reason=content[:240],
                target=rule.action_config or {},
                resolved_category=resolved_category,
                resolved_channel=resolved_channel,
                selected_api={k: v for k, v in runtime_secret.items() if k != 'api_key'},
                route_kind=route_kind
            )
    return None


@router.get('/rules', response_model=list[RoutingRuleRead])
async def list_rules(session=Depends(get_session), user=Depends(get_optional_user)):
    stmt = select(RoutingRule).where(RoutingRule.is_public.is_(True))
    if user:
        stmt = select(RoutingRule).where((RoutingRule.is_public.is_(True)) | (RoutingRule.owner_id == user.id))
    result = await session.execute(stmt.order_by(asc(RoutingRule.priority), asc(RoutingRule.id)))
    return list(result.scalars().all())


@router.post('/resolve', response_model=RoutingClassifyResponse)
async def resolve_routing_context(payload: RoutingResolveRequest, session=Depends(get_session), user=Depends(get_optional_user)):
    runtime_secret = {}
    if user:
        runtime_secret = build_runtime_secret(await resolve_user_secret(session, user.id, payload.api_name))
    resolved_category, resolved_channel, route_kind = _resolve_category_and_channel(payload, runtime_secret)
    return RoutingClassifyResponse(
        mode='resolve',
        matched=False,
        reason='Resolved routing context',
        target={},
        resolved_category=resolved_category,
        resolved_channel=resolved_channel,
        selected_api={k: v for k, v in runtime_secret.items() if k != 'api_key'},
        route_kind=route_kind
    )


@router.post('/classify', response_model=RoutingClassifyResponse)
async def classify_message(payload: RoutingClassifyRequest, session=Depends(get_session), user=Depends(get_optional_user)):
    runtime_secret = {}
    if user:
        runtime_secret = build_runtime_secret(await resolve_user_secret(session, user.id, payload.api_name))
    resolved_category, resolved_channel, route_kind = _resolve_category_and_channel(payload, runtime_secret)

    stmt = select(RoutingRule).where(
        RoutingRule.enabled.is_(True),
        RoutingRule.category == resolved_category,
        RoutingRule.channel == resolved_channel
    )
    if user:
        stmt = stmt.where((RoutingRule.is_public.is_(True)) | (RoutingRule.owner_id == user.id))
    else:
        stmt = stmt.where(RoutingRule.is_public.is_(True))
    result = await session.execute(stmt.order_by(asc(RoutingRule.priority), asc(RoutingRule.id)))
    rules = list(result.scalars().all())

    if payload.use_ai:
        ai_result = await _classify_with_ai(payload, rules, runtime_secret, resolved_category, resolved_channel, route_kind)
        if ai_result:
            return ai_result

    for rule in rules:
        matched, score, reason = _match_rule(rule, payload.text)
        if matched:
            return RoutingClassifyResponse(
                mode='rule',
                matched=True,
                rule_name=rule.name,
                score=score,
                reason=reason,
                target=rule.action_config or {},
                resolved_category=resolved_category,
                resolved_channel=resolved_channel,
                selected_api={k: v for k, v in runtime_secret.items() if k != 'api_key'},
                route_kind=route_kind
            )

    return RoutingClassifyResponse(
        mode='rule',
        matched=False,
        reason='No routing rule matched',
        target={},
        resolved_category=resolved_category,
        resolved_channel=resolved_channel,
        selected_api={k: v for k, v in runtime_secret.items() if k != 'api_key'},
        route_kind=route_kind
    )
