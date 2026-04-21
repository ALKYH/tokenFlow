from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RagDocumentIngestRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    workspace_id: str = Field(default='default', min_length=1, max_length=120)
    source_uri: str = Field(default='', max_length=500)
    title: str = Field(default='', max_length=255)
    content: str = Field(min_length=1, max_length=2_000_000)
    metadata: dict[str, Any] = Field(default_factory=dict)
    chunk_size: int | None = Field(default=None, ge=128, le=4000)
    chunk_overlap: int | None = Field(default=None, ge=0, le=2000)
    embedding_model: str = Field(default='hash-v1', min_length=1, max_length=120)


class RagDocumentIngestResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    document_id: int
    workspace_id: str
    chunk_count: int
    vector_dim: int
    duration_ms: float


class RagChunkHit(BaseModel):
    model_config = ConfigDict(extra='forbid')

    chunk_id: int
    document_id: int
    chunk_index: int
    score: float
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class RagRetrieveRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    workspace_id: str = Field(default='default', min_length=1, max_length=120)
    query: str = Field(min_length=1, max_length=2000)
    top_k: int | None = Field(default=None, ge=1, le=20)
    rerank: bool = True
    max_context_chars: int = Field(default=2400, ge=256, le=20_000)


class RagRetrieveResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    workspace_id: str
    query: str
    top_k: int
    cache_hit: bool
    duration_ms: float
    estimated_cost_usd: float
    hits: list[RagChunkHit] = Field(default_factory=list)
    context: str = ''


class RagMetricsResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    workspace_id: str
    window_hours: int
    query_count: int
    avg_retrieval_ms: float
    hit_rate: float
    cache_hit_rate: float
    failure_rate: float
    last_query_at: datetime | None = None

