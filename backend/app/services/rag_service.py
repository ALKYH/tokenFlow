from __future__ import annotations

import hashlib
import json
import math
import os
import re
from datetime import datetime, timedelta, timezone
from time import perf_counter
from typing import Any

from ..schemas.rag import (
    RagChunkHit,
    RagDocumentIngestRequest,
    RagDocumentIngestResponse,
    RagMetricsResponse,
    RagRetrieveRequest,
    RagRetrieveResponse,
)


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name, str(default)).strip()
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


RAG_VECTOR_DIM = _env_int('TOKENFLOW_RAG_VECTOR_DIM', 256, 8, 4096)
RAG_CHUNK_SIZE = _env_int('TOKENFLOW_RAG_CHUNK_SIZE', 700, 128, 4000)
RAG_CHUNK_OVERLAP = _env_int('TOKENFLOW_RAG_CHUNK_OVERLAP', 120, 0, 2000)
RAG_DEFAULT_TOP_K = _env_int('TOKENFLOW_RAG_DEFAULT_TOP_K', 5, 1, 20)
RAG_CACHE_TTL_SECONDS = _env_int('TOKENFLOW_RAG_CACHE_TTL_SECONDS', 900, 30, 86400)

_WORKSPACE_PATTERN = re.compile(r'[^A-Za-z0-9._:-]+')
_TOKEN_PATTERN = re.compile(r'[A-Za-z0-9_\u4e00-\u9fff]+')


class RagServiceError(Exception):
    pass


def _load_db_deps():
    try:
        from sqlalchemy import text as sql_text  # type: ignore
        from ..db.session import AsyncSessionLocal  # type: ignore
    except Exception as exc:  # pragma: no cover - environment specific
        raise RagServiceError(
            'Database dependencies are unavailable. Please install a Python/SQLAlchemy combination '
            'compatible with this environment.'
        ) from exc
    return sql_text, AsyncSessionLocal


def normalize_workspace_id(value: str | None) -> str:
    raw = (value or 'default').strip()
    if not raw:
        raw = 'default'
    normalized = _WORKSPACE_PATTERN.sub('_', raw)
    return normalized[:120] or 'default'


def normalize_chunk_params(chunk_size: int | None, chunk_overlap: int | None) -> tuple[int, int]:
    size = chunk_size if chunk_size is not None else RAG_CHUNK_SIZE
    overlap = chunk_overlap if chunk_overlap is not None else RAG_CHUNK_OVERLAP
    size = max(128, min(4000, size))
    overlap = max(0, min(2000, overlap))
    if overlap >= size:
        overlap = max(0, size // 3)
    return size, overlap


def chunk_text(content: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    normalized = re.sub(r'\s+', ' ', (content or '').strip())
    if not normalized:
        return []
    chunks: list[str] = []
    cursor = 0
    total = len(normalized)
    while cursor < total:
        end = min(total, cursor + chunk_size)
        chunk = normalized[cursor:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= total:
            break
        cursor = max(cursor + 1, end - chunk_overlap)
    return chunks


def hash_embedding(text_value: str, vector_dim: int) -> list[float]:
    seed = hashlib.sha256(text_value.encode('utf-8')).digest()
    values: list[float] = []
    counter = 0
    while len(values) < vector_dim:
        block = hashlib.sha256(seed + counter.to_bytes(4, 'big')).digest()
        for index in range(0, len(block), 4):
            if len(values) >= vector_dim:
                break
            segment = block[index:index + 4]
            ratio = int.from_bytes(segment, 'big') / 4_294_967_295
            values.append((ratio * 2.0) - 1.0)
        counter += 1
    norm = math.sqrt(sum(item * item for item in values)) or 1.0
    return [item / norm for item in values]


def vector_literal(vector: list[float]) -> str:
    return '[' + ','.join(f'{value:.8f}' for value in vector) + ']'


def tokenize_text(text_value: str) -> set[str]:
    return {token.lower() for token in _TOKEN_PATTERN.findall(text_value or '') if token}


def rerank_hits(query: str, hits: list[RagChunkHit]) -> list[RagChunkHit]:
    query_tokens = tokenize_text(query)
    if not query_tokens:
        return hits
    boosted: list[RagChunkHit] = []
    for hit in hits:
        hit_tokens = tokenize_text(hit.text)
        lexical = len(query_tokens & hit_tokens) / max(1, len(query_tokens))
        blended_score = (hit.score * 0.75) + (lexical * 0.25)
        boosted.append(hit.model_copy(update={'score': blended_score}))
    return sorted(boosted, key=lambda item: item.score, reverse=True)


def build_context_from_hits(hits: list[RagChunkHit], max_context_chars: int) -> str:
    limit = max(256, min(20_000, max_context_chars))
    blocks: list[str] = []
    used = 0
    for hit in hits:
        prefix = f'[doc:{hit.document_id} chunk:{hit.chunk_index} score:{hit.score:.4f}] '
        block = f'{prefix}{hit.text.strip()}'
        if used + len(block) > limit:
            remaining = limit - used
            if remaining > 0:
                blocks.append(block[:remaining])
            break
        blocks.append(block)
        used += len(block) + 2
    return '\n\n'.join(blocks)


def estimate_cost_usd(query: str, hits: list[RagChunkHit]) -> float:
    query_tokens = max(1, len(query) // 4)
    retrieved_tokens = sum(max(1, len(hit.text) // 4) for hit in hits)
    # Local hash embedding is near-zero cost; keep a tiny synthetic budget for observability.
    return round((query_tokens * 0.00000002) + (retrieved_tokens * 0.00000001), 8)


async def _log_query(
    *,
    workspace_id: str,
    query_text: str,
    top_k: int,
    hit_count: int,
    duration_ms: float,
    rerank_enabled: bool,
    cache_hit: bool,
    success: bool,
    error_code: str,
    estimated_cost_usd: float,
) -> None:
    sql_text, AsyncSessionLocal = _load_db_deps()
    async with AsyncSessionLocal() as session:
        await session.execute(
            sql_text(
                """
                INSERT INTO rag_query_logs (
                    workspace_id, query_text, top_k, hit_count, duration_ms,
                    rerank_enabled, cache_hit, success, error_code, estimated_cost_usd
                )
                VALUES (
                    :workspace_id, :query_text, :top_k, :hit_count, :duration_ms,
                    :rerank_enabled, :cache_hit, :success, :error_code, :estimated_cost_usd
                )
                """
            ),
            {
                'workspace_id': workspace_id,
                'query_text': query_text,
                'top_k': top_k,
                'hit_count': hit_count,
                'duration_ms': duration_ms,
                'rerank_enabled': rerank_enabled,
                'cache_hit': cache_hit,
                'success': success,
                'error_code': error_code,
                'estimated_cost_usd': estimated_cost_usd,
            },
        )
        await session.commit()


async def ingest_document(payload: RagDocumentIngestRequest) -> RagDocumentIngestResponse:
    started = perf_counter()
    workspace_id = normalize_workspace_id(payload.workspace_id)
    content = payload.content.strip()
    if not content:
        raise RagServiceError('content is empty')
    chunk_size, chunk_overlap = normalize_chunk_params(payload.chunk_size, payload.chunk_overlap)
    chunks = chunk_text(content, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    if not chunks:
        raise RagServiceError('chunking produced no data')

    metadata = dict(payload.metadata or {})
    if payload.source_uri:
        metadata.setdefault('source_uri', payload.source_uri)
    if payload.title:
        metadata.setdefault('title', payload.title)
    metadata.setdefault('chunk_size', chunk_size)
    metadata.setdefault('chunk_overlap', chunk_overlap)

    content_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()
    embedding_model = payload.embedding_model.strip() or 'hash-v1'
    embeddings = [hash_embedding(chunk, vector_dim=RAG_VECTOR_DIM) for chunk in chunks]

    sql_text, AsyncSessionLocal = _load_db_deps()
    async with AsyncSessionLocal() as session:
        document_id = await session.scalar(
            sql_text(
                """
                INSERT INTO rag_documents (
                    workspace_id, source_uri, title, content, content_hash, metadata, ingest_status, updated_at
                )
                VALUES (
                    :workspace_id, :source_uri, :title, :content, :content_hash, CAST(:metadata AS jsonb), 'ready', NOW()
                )
                ON CONFLICT (workspace_id, content_hash)
                DO UPDATE SET
                    source_uri = EXCLUDED.source_uri,
                    title = EXCLUDED.title,
                    content = EXCLUDED.content,
                    metadata = EXCLUDED.metadata,
                    ingest_status = 'ready',
                    updated_at = NOW()
                RETURNING id
                """
            ),
            {
                'workspace_id': workspace_id,
                'source_uri': payload.source_uri or '',
                'title': payload.title or '',
                'content': content,
                'content_hash': content_hash,
                'metadata': json.dumps(metadata, ensure_ascii=False),
            },
        )
        if document_id is None:
            raise RagServiceError('failed to persist rag document')

        await session.execute(
            sql_text("DELETE FROM rag_chunks WHERE document_id = :document_id"),
            {'document_id': int(document_id)},
        )
        for index, chunk in enumerate(chunks):
            await session.execute(
                sql_text(
                    """
                    INSERT INTO rag_chunks (
                        document_id, workspace_id, chunk_index, chunk_text, token_count, metadata, embedding, embedding_model
                    )
                    VALUES (
                        :document_id, :workspace_id, :chunk_index, :chunk_text, :token_count,
                        CAST(:metadata AS jsonb), CAST(:embedding AS vector), :embedding_model
                    )
                    """
                ),
                {
                    'document_id': int(document_id),
                    'workspace_id': workspace_id,
                    'chunk_index': index,
                    'chunk_text': chunk,
                    'token_count': max(1, len(chunk) // 4),
                    'metadata': json.dumps(metadata, ensure_ascii=False),
                    'embedding': vector_literal(embeddings[index]),
                    'embedding_model': embedding_model,
                },
            )
        await session.commit()

    return RagDocumentIngestResponse(
        document_id=int(document_id),
        workspace_id=workspace_id,
        chunk_count=len(chunks),
        vector_dim=RAG_VECTOR_DIM,
        duration_ms=(perf_counter() - started) * 1000,
    )


async def retrieve_chunks(payload: RagRetrieveRequest) -> RagRetrieveResponse:
    started = perf_counter()
    workspace_id = normalize_workspace_id(payload.workspace_id)
    query = payload.query.strip()
    if not query:
        raise RagServiceError('query is empty')
    top_k = payload.top_k or RAG_DEFAULT_TOP_K
    cache_key = hashlib.sha256(
        f'{workspace_id}|{query}|{top_k}|{int(payload.rerank)}'.encode('utf-8')
    ).hexdigest()
    query_hash = hashlib.sha256(query.encode('utf-8')).hexdigest()
    sql_text, AsyncSessionLocal = _load_db_deps()

    try:
        async with AsyncSessionLocal() as session:
            cached_row = (
                await session.execute(
                    sql_text(
                        """
                        SELECT result, expires_at
                        FROM rag_query_cache
                        WHERE cache_key = :cache_key
                          AND workspace_id = :workspace_id
                        """
                    ),
                    {'cache_key': cache_key, 'workspace_id': workspace_id},
                )
            ).mappings().first()
            now = datetime.now(timezone.utc)
            if cached_row is not None and cached_row['expires_at'] > now:
                await session.execute(
                    sql_text("UPDATE rag_query_cache SET hit_count = hit_count + 1 WHERE cache_key = :cache_key"),
                    {'cache_key': cache_key},
                )
                await session.commit()
                cached_hits = [RagChunkHit.model_validate(item) for item in (cached_row['result'] or [])]
                context = build_context_from_hits(cached_hits, payload.max_context_chars)
                duration_ms = (perf_counter() - started) * 1000
                estimated_cost = estimate_cost_usd(query, cached_hits)
                await _log_query(
                    workspace_id=workspace_id,
                    query_text=query,
                    top_k=top_k,
                    hit_count=len(cached_hits),
                    duration_ms=duration_ms,
                    rerank_enabled=payload.rerank,
                    cache_hit=True,
                    success=True,
                    error_code='',
                    estimated_cost_usd=estimated_cost,
                )
                return RagRetrieveResponse(
                    workspace_id=workspace_id,
                    query=query,
                    top_k=top_k,
                    cache_hit=True,
                    duration_ms=duration_ms,
                    estimated_cost_usd=estimated_cost,
                    hits=cached_hits,
                    context=context,
                )

            query_embedding = hash_embedding(query, vector_dim=RAG_VECTOR_DIM)
            rows = (
                await session.execute(
                    sql_text(
                        """
                        SELECT
                            c.id AS chunk_id,
                            c.document_id,
                            c.chunk_index,
                            c.chunk_text,
                            c.metadata,
                            1 - (c.embedding <=> CAST(:query_embedding AS vector)) AS score
                        FROM rag_chunks AS c
                        WHERE c.workspace_id = :workspace_id
                        ORDER BY c.embedding <=> CAST(:query_embedding AS vector)
                        LIMIT :top_k
                        """
                    ),
                    {
                        'query_embedding': vector_literal(query_embedding),
                        'workspace_id': workspace_id,
                        'top_k': top_k,
                    },
                )
            ).mappings().all()

            hits = [
                RagChunkHit(
                    chunk_id=int(row['chunk_id']),
                    document_id=int(row['document_id']),
                    chunk_index=int(row['chunk_index']),
                    score=float(row['score'] or 0.0),
                    text=str(row['chunk_text'] or ''),
                    metadata=dict(row['metadata'] or {}),
                )
                for row in rows
            ]
            if payload.rerank:
                hits = rerank_hits(query, hits)
            hits = hits[:top_k]
            context = build_context_from_hits(hits, payload.max_context_chars)
            estimated_cost = estimate_cost_usd(query, hits)
            duration_ms = (perf_counter() - started) * 1000

            expires_at = datetime.now(timezone.utc) + timedelta(seconds=RAG_CACHE_TTL_SECONDS)
            await session.execute(
                sql_text(
                    """
                    INSERT INTO rag_query_cache (
                        cache_key, workspace_id, query_text, query_hash, top_k, result, hit_count, expires_at
                    )
                    VALUES (
                        :cache_key, :workspace_id, :query_text, :query_hash, :top_k,
                        CAST(:result AS jsonb), 0, :expires_at
                    )
                    ON CONFLICT (cache_key)
                    DO UPDATE SET
                        query_text = EXCLUDED.query_text,
                        query_hash = EXCLUDED.query_hash,
                        top_k = EXCLUDED.top_k,
                        result = EXCLUDED.result,
                        expires_at = EXCLUDED.expires_at
                    """
                ),
                {
                    'cache_key': cache_key,
                    'workspace_id': workspace_id,
                    'query_text': query,
                    'query_hash': query_hash,
                    'top_k': top_k,
                    'result': json.dumps([item.model_dump() for item in hits], ensure_ascii=False),
                    'expires_at': expires_at,
                },
            )
            await session.commit()

            await _log_query(
                workspace_id=workspace_id,
                query_text=query,
                top_k=top_k,
                hit_count=len(hits),
                duration_ms=duration_ms,
                rerank_enabled=payload.rerank,
                cache_hit=False,
                success=True,
                error_code='',
                estimated_cost_usd=estimated_cost,
            )
            return RagRetrieveResponse(
                workspace_id=workspace_id,
                query=query,
                top_k=top_k,
                cache_hit=False,
                duration_ms=duration_ms,
                estimated_cost_usd=estimated_cost,
                hits=hits,
                context=context,
            )
    except Exception as exc:
        duration_ms = (perf_counter() - started) * 1000
        await _log_query(
            workspace_id=workspace_id,
            query_text=query,
            top_k=top_k,
            hit_count=0,
            duration_ms=duration_ms,
            rerank_enabled=payload.rerank,
            cache_hit=False,
            success=False,
            error_code=type(exc).__name__,
            estimated_cost_usd=0.0,
        )
        raise


async def get_retrieval_metrics(workspace_id: str = 'default', window_hours: int = 24) -> RagMetricsResponse:
    window = max(1, min(24 * 30, int(window_hours)))
    normalized_workspace = normalize_workspace_id(workspace_id)
    sql_text, AsyncSessionLocal = _load_db_deps()
    async with AsyncSessionLocal() as session:
        row = (
            await session.execute(
                sql_text(
                    """
                    SELECT
                        COUNT(*)::int AS query_count,
                        COALESCE(AVG(duration_ms), 0) AS avg_retrieval_ms,
                        COALESCE(AVG(CASE WHEN hit_count > 0 THEN 1 ELSE 0 END), 0) AS hit_rate,
                        COALESCE(AVG(CASE WHEN cache_hit THEN 1 ELSE 0 END), 0) AS cache_hit_rate,
                        COALESCE(AVG(CASE WHEN success THEN 0 ELSE 1 END), 0) AS failure_rate,
                        MAX(created_at) AS last_query_at
                    FROM rag_query_logs
                    WHERE workspace_id = :workspace_id
                      AND created_at >= NOW() - make_interval(hours => :window_hours)
                    """
                ),
                {'workspace_id': normalized_workspace, 'window_hours': window},
            )
        ).mappings().one()
    return RagMetricsResponse(
        workspace_id=normalized_workspace,
        window_hours=window,
        query_count=int(row['query_count'] or 0),
        avg_retrieval_ms=float(row['avg_retrieval_ms'] or 0.0),
        hit_rate=float(row['hit_rate'] or 0.0),
        cache_hit_rate=float(row['cache_hit_rate'] or 0.0),
        failure_rate=float(row['failure_rate'] or 0.0),
        last_query_at=row['last_query_at'],
    )


async def runtime_ingest_text(
    *,
    workspace_id: str,
    content: str,
    title: str = '',
    source_uri: str = '',
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = RagDocumentIngestRequest(
        workspace_id=workspace_id,
        title=title,
        source_uri=source_uri,
        content=content,
        metadata=metadata or {},
    )
    result = await ingest_document(payload)
    return result.model_dump()


async def runtime_search(
    *,
    workspace_id: str,
    query: str,
    top_k: int = 5,
    rerank: bool = True,
    max_context_chars: int = 2400,
) -> dict[str, Any]:
    payload = RagRetrieveRequest(
        workspace_id=workspace_id,
        query=query,
        top_k=top_k,
        rerank=rerank,
        max_context_chars=max_context_chars,
    )
    result = await retrieve_chunks(payload)
    return result.model_dump()
