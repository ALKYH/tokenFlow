from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx
from sqlalchemy import asc, select

from ..models.routing_rule import RoutingRule
from ..schemas.rag import RagChunkHit
from ..schemas.routing import (
    RoutingCandidateRead,
    RoutingClassifyRequest,
    RoutingClassifyResponse,
    RoutingExplainability,
    RoutingResolveRequest,
)
from .rag_service import build_context_from_hits, rerank_hits, runtime_search
from .secret_service import build_runtime_secret, resolve_user_secret


FILE_TYPE_ROUTE_MAP = {
    'workspace': ('workspace', 'editor'),
    'module': ('marketplace', 'editor'),
    'plugin': ('marketplace', 'community'),
    'workflow': ('routing', 'editor'),
    'knowledge': ('knowledge', 'api'),
    'pdf': ('knowledge', 'api'),
    'image': ('vision', 'api'),
    'audio': ('speech', 'api'),
}


@dataclass(frozen=True)
class RoutingCandidate:
    rule_name: str
    score: float
    route_kind: str
    target: dict[str, Any] = field(default_factory=dict)
    matched_keywords: tuple[str, ...] = ()
    lexical_score: float = 0.0
    vector_score: float = 0.0
    source: str = "rule"
    reason: str = ""


def _to_candidate_read(candidate: RoutingCandidate) -> RoutingCandidateRead:
    return RoutingCandidateRead(
        rule_name=candidate.rule_name,
        score=candidate.score,
        route_kind=candidate.route_kind,
        target=candidate.target,
        matched_keywords=list(candidate.matched_keywords),
        lexical_score=candidate.lexical_score,
        vector_score=candidate.vector_score,
        source=candidate.source,
        reason=candidate.reason,
    )


async def _build_runtime_secret_for_user(session, user_id: int | None, api_name: str | None) -> dict[str, Any]:
    if user_id is None:
        return {}
    return build_runtime_secret(await resolve_user_secret(session, user_id, api_name))


def resolve_category_and_channel(payload: RoutingResolveRequest, runtime_secret: dict[str, Any]) -> tuple[str, str, str]:
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


def match_rule(rule: RoutingRule, text: str) -> tuple[bool, float, str, list[str]]:
    normalized = (text or '').lower()
    keywords = [str(item).lower() for item in (rule.matcher_config or {}).get('keywords', [])]
    if not keywords:
        return False, 0.0, 'No keywords configured', []
    hits = [keyword for keyword in keywords if keyword and keyword in normalized]
    if not hits:
        return False, 0.0, 'No keyword hit', []
    score = min(1.0, len(hits) / max(1, len(keywords)))
    return True, score, f"Matched keywords: {', '.join(hits[:4])}", hits


def build_rule_documents(rules: list[RoutingRule]) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    for rule in rules:
        keywords = [str(item) for item in (rule.matcher_config or {}).get("keywords", [])]
        content = " ".join(
            [
                rule.name,
                rule.category,
                rule.channel,
                " ".join(keywords),
                str((rule.action_config or {}).get("target", "")),
                str((rule.action_config or {}).get("workflow_id", "")),
            ]
        ).strip()
        documents.append(
            {
                "rule": rule,
                "content": content,
            }
        )
    return documents


def score_rule_candidates(
    *,
    text: str,
    rules: list[RoutingRule],
    rag_hits: list[RagChunkHit],
    route_kind: str,
) -> list[RoutingCandidate]:
    documents = build_rule_documents(rules)
    vector_lookup: dict[str, float] = {}
    for hit in rag_hits:
        rule_name = str(hit.metadata.get("rule_name") or "")
        if rule_name:
            vector_lookup[rule_name] = max(vector_lookup.get(rule_name, 0.0), float(hit.score))

    candidates: list[RoutingCandidate] = []
    for item in documents:
        rule = item["rule"]
        matched, lexical_score, reason, hits = match_rule(rule, text)
        vector_score = vector_lookup.get(rule.name, 0.0)
        source = "hybrid"
        if vector_score > 0 and lexical_score == 0:
            source = "vector"
        elif lexical_score > 0 and vector_score == 0:
            source = "rule"
        final_score = min(1.0, (lexical_score * 0.65) + (vector_score * 0.35))
        if not matched and vector_score <= 0:
            continue
        if not matched and vector_score > 0:
            reason = f"Vector recall matched semantic context for {rule.name}"
        candidates.append(
            RoutingCandidate(
                rule_name=rule.name,
                score=final_score,
                route_kind=route_kind,
                target=rule.action_config or {},
                matched_keywords=tuple(hits),
                lexical_score=lexical_score,
                vector_score=vector_score,
                source=source,
                reason=reason,
            )
        )
    return sorted(candidates, key=lambda item: (-item.score, item.rule_name))


async def retrieve_rag_candidates(
    *,
    payload: RoutingClassifyRequest,
    rules: list[RoutingRule],
    resolved_category: str,
    resolved_channel: str,
    top_k: int = 5,
) -> tuple[list[RagChunkHit], str]:
    if not rules:
        return [], ""

    synthetic_chunks: list[RagChunkHit] = []
    for index, rule in enumerate(rules, start=1):
        keywords = [str(item) for item in (rule.matcher_config or {}).get("keywords", [])]
        text = " ".join(
            [rule.name, resolved_category, resolved_channel, " ".join(keywords), payload.text]
        )
        synthetic_chunks.append(
            RagChunkHit(
                chunk_id=index,
                document_id=index,
                chunk_index=0,
                score=0.25,
                text=text,
                metadata={"rule_name": rule.name, "keywords": keywords},
            )
        )

    reranked = rerank_hits(payload.text, synthetic_chunks)[:top_k]
    context = build_context_from_hits(reranked, max_context_chars=1200)
    return reranked, context


async def classify_with_ai(
    payload: RoutingClassifyRequest,
    rules: list[RoutingRule],
    runtime_secret: dict[str, Any],
    resolved_category: str,
    resolved_channel: str,
    route_kind: str,
) -> RoutingClassifyResponse | None:
    ai_endpoint = payload.ai_endpoint or runtime_secret.get('request_prefix')
    if not ai_endpoint:
        return None
    prompt_rules = [
        {
            'name': rule.name,
            'category': rule.category,
            'channel': rule.channel,
            'action': rule.action_config,
        }
        for rule in rules
    ]
    body: dict[str, Any] = {
        'model': payload.model or 'gpt-4o-mini',
        'messages': [
            {
                'role': 'system',
                'content': 'Classify the message to the best routing rule and return JSON with rule_name, reason, score.',
            },
            {
                'role': 'user',
                'content': {
                    'category': resolved_category,
                    'channel': resolved_channel,
                    'text': payload.text,
                    'rules': prompt_rules,
                },
            },
        ],
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
            candidate = RoutingCandidate(
                rule_name=rule.name,
                score=0.88,
                route_kind=route_kind,
                target=rule.action_config or {},
                source="ai",
                reason=content[:240],
            )
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
                route_kind=route_kind,
                top_candidates=[_to_candidate_read(candidate)],
                explainability=RoutingExplainability(
                    matched_rules=[rule.name],
                    selected_reason=content[:240],
                ),
            )
    return None


async def resolve_routing_context(
    payload: RoutingResolveRequest,
    session,
    user_id: int | None = None,
) -> RoutingClassifyResponse:
    runtime_secret = await _build_runtime_secret_for_user(session, user_id, payload.api_name)
    resolved_category, resolved_channel, route_kind = resolve_category_and_channel(payload, runtime_secret)
    return RoutingClassifyResponse(
        mode='resolve',
        matched=False,
        reason='Resolved routing context',
        target={},
        resolved_category=resolved_category,
        resolved_channel=resolved_channel,
        selected_api={k: v for k, v in runtime_secret.items() if k != 'api_key'},
        route_kind=route_kind,
        top_candidates=[],
        explainability=RoutingExplainability(
            selected_reason='Resolved category/channel context only',
        ),
    )


async def classify_routing_request(
    payload: RoutingClassifyRequest,
    session,
    user_id: int | None = None,
) -> RoutingClassifyResponse:
    runtime_secret = await _build_runtime_secret_for_user(session, user_id, payload.api_name)
    resolved_category, resolved_channel, route_kind = resolve_category_and_channel(payload, runtime_secret)

    stmt = select(RoutingRule).where(
        RoutingRule.enabled.is_(True),
        RoutingRule.category == resolved_category,
        RoutingRule.channel == resolved_channel,
    )
    if user_id is not None:
        stmt = stmt.where((RoutingRule.is_public.is_(True)) | (RoutingRule.owner_id == user_id))
    else:
        stmt = stmt.where(RoutingRule.is_public.is_(True))
    result = await session.execute(stmt.order_by(asc(RoutingRule.priority), asc(RoutingRule.id)))
    rules = list(result.scalars().all())

    if payload.use_ai:
        ai_result = await classify_with_ai(
            payload,
            rules,
            runtime_secret,
            resolved_category,
            resolved_channel,
            route_kind,
        )
        if ai_result:
            return ai_result

    rag_hits, rag_context = await retrieve_rag_candidates(
        payload=payload,
        rules=rules,
        resolved_category=resolved_category,
        resolved_channel=resolved_channel,
        top_k=5,
    )
    candidates = score_rule_candidates(
        text=payload.text,
        rules=rules,
        rag_hits=rag_hits,
        route_kind=route_kind,
    )
    top_candidates = [_to_candidate_read(item) for item in candidates[:5]]
    selected = candidates[0] if candidates else None

    if selected is not None:
        return RoutingClassifyResponse(
            mode='hybrid',
            matched=True,
            rule_name=selected.rule_name,
            score=selected.score,
            reason=selected.reason,
            target=selected.target,
            resolved_category=resolved_category,
            resolved_channel=resolved_channel,
            selected_api={k: v for k, v in runtime_secret.items() if k != 'api_key'},
            route_kind=route_kind,
            top_candidates=top_candidates,
            explainability=RoutingExplainability(
                matched_rules=[item.rule_name for item in candidates if item.lexical_score > 0],
                recall_scores={str(hit.metadata.get("rule_name") or f"rule-{hit.document_id}"): hit.score for hit in rag_hits},
                selected_reason=selected.reason,
                rag_context_preview=rag_context[:400],
            ),
        )

    return RoutingClassifyResponse(
        mode='hybrid',
        matched=False,
        reason='No routing rule matched',
        target={},
        resolved_category=resolved_category,
        resolved_channel=resolved_channel,
        selected_api={k: v for k, v in runtime_secret.items() if k != 'api_key'},
        route_kind=route_kind,
        top_candidates=[],
        explainability=RoutingExplainability(
            matched_rules=[],
            recall_scores={str(hit.metadata.get("rule_name") or f"rule-{hit.document_id}"): hit.score for hit in rag_hits},
            selected_reason='No candidate reached routing threshold',
            rag_context_preview=rag_context[:400],
        ),
    )
