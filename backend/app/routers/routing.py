from typing import Any
import httpx
from sqlalchemy import asc, select
from fastapi import APIRouter, Depends
from ..deps import get_optional_user, get_session
from ..models.routing_rule import RoutingRule
from ..schemas.routing import RoutingClassifyRequest, RoutingClassifyResponse, RoutingRuleRead

router = APIRouter(prefix='/api/routing', tags=['routing'])


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


async def _classify_with_ai(payload: RoutingClassifyRequest, rules: list[RoutingRule]) -> RoutingClassifyResponse | None:
    if not payload.ai_endpoint:
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
                    'category': payload.category,
                    'channel': payload.channel,
                    'text': payload.text,
                    'rules': prompt_rules
                }
            }
        ]
    }
    headers = {'Content-Type': 'application/json'}
    if payload.api_key:
        headers['Authorization'] = f'Bearer {payload.api_key}'
    async with httpx.AsyncClient(timeout=18.0) as client:
        response = await client.post(payload.ai_endpoint, json=body, headers=headers)
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
                target=rule.action_config or {}
            )
    return None


@router.get('/rules', response_model=list[RoutingRuleRead])
async def list_rules(session=Depends(get_session), user=Depends(get_optional_user)):
    stmt = select(RoutingRule).where(RoutingRule.is_public.is_(True))
    if user:
        stmt = select(RoutingRule).where((RoutingRule.is_public.is_(True)) | (RoutingRule.owner_id == user.id))
    result = await session.execute(stmt.order_by(asc(RoutingRule.priority), asc(RoutingRule.id)))
    return list(result.scalars().all())


@router.post('/classify', response_model=RoutingClassifyResponse)
async def classify_message(payload: RoutingClassifyRequest, session=Depends(get_session), user=Depends(get_optional_user)):
    stmt = select(RoutingRule).where(RoutingRule.enabled.is_(True), RoutingRule.category == payload.category, RoutingRule.channel == payload.channel)
    if user:
        stmt = stmt.where((RoutingRule.is_public.is_(True)) | (RoutingRule.owner_id == user.id))
    else:
        stmt = stmt.where(RoutingRule.is_public.is_(True))
    result = await session.execute(stmt.order_by(asc(RoutingRule.priority), asc(RoutingRule.id)))
    rules = list(result.scalars().all())

    if payload.use_ai:
        ai_result = await _classify_with_ai(payload, rules)
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
                target=rule.action_config or {}
            )

    return RoutingClassifyResponse(mode='rule', matched=False, reason='No routing rule matched', target={})
