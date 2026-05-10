from __future__ import annotations

from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class RoutingRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    category: str
    channel: str
    matcher_type: str
    matcher_config: dict[str, Any] = Field(default_factory=dict)
    action_config: dict[str, Any] = Field(default_factory=dict)
    classifier_mode: str
    priority: int
    enabled: bool
    is_public: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


class RoutingRuleCreate(BaseModel):
    name: str
    category: str = 'general'
    channel: str = 'dashboard'
    matcher_type: str = 'keyword'
    matcher_config: dict[str, Any] = Field(default_factory=dict)
    action_config: dict[str, Any] = Field(default_factory=dict)
    classifier_mode: str = 'rule'
    priority: int = 100
    enabled: bool = True
    is_public: bool = False


class RoutingRuleUpdate(BaseModel):
    name: str | None = None
    category: str | None = None
    channel: str | None = None
    matcher_type: str | None = None
    matcher_config: dict[str, Any] | None = None
    action_config: dict[str, Any] | None = None
    classifier_mode: str | None = None
    priority: int | None = None
    enabled: bool | None = None
    is_public: bool | None = None


class RoutingClassifyRequest(BaseModel):
    category: str | None = None
    channel: str | None = None
    text: str
    use_ai: bool = False
    ai_endpoint: str | None = None
    api_key: str | None = None
    model: str | None = None
    api_name: str | None = None
    file_name: str | None = None
    file_type: str | None = None


class RoutingResolveRequest(BaseModel):
    category: str | None = None
    channel: str | None = None
    api_name: str | None = None
    file_name: str | None = None
    file_type: str | None = None


class RoutingCandidateRead(BaseModel):
    rule_name: str
    score: float
    route_kind: str
    target: dict[str, Any] = Field(default_factory=dict)
    matched_keywords: list[str] = Field(default_factory=list)
    lexical_score: float = 0
    vector_score: float = 0
    source: str = 'rule'
    reason: str = ''


class RoutingExplainability(BaseModel):
    matched_rules: list[str] = Field(default_factory=list)
    recall_scores: dict[str, float] = Field(default_factory=dict)
    selected_reason: str = ''
    rag_context_preview: str = ''


class RoutingClassifyResponse(BaseModel):
    mode: str
    matched: bool
    rule_name: str | None = None
    score: float = 0
    reason: str = ''
    target: dict[str, Any] = Field(default_factory=dict)
    resolved_category: str | None = None
    resolved_channel: str | None = None
    selected_api: dict[str, Any] = Field(default_factory=dict)
    route_kind: str = 'manual'
    top_candidates: list[RoutingCandidateRead] = Field(default_factory=list)
    explainability: RoutingExplainability | None = None


class QueuedRoutingRequest(BaseModel):
    request_id: str
    instance_id: str
    submitted_at: datetime
    user_id: int | None = None
    payload: RoutingClassifyRequest


class RoutingQueueHealth(BaseModel):
    enabled: bool = False
    backend: str = 'inline'
    instance_id: str = ''
    status: str = 'disabled'
    execute_through_queue: bool = False
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
    dead_letter_count: int = 0
    rejected_count: int = 0
    retry_count: int = 0
    reclaim_count: int = 0
    max_attempts: int | None = None
    retry_delay_seconds: float | None = None
    last_error: str | None = None


class QueueMetricRecordRead(BaseModel):
    request_id: str
    queue_backend: str
    status: str
    duration_ms: float
    wait_time_ms: float
    attempts: int
    created_at: datetime | None = None


class QueueDeadLetterRead(BaseModel):
    request_id: str
    queue_backend: str
    error_code: str
    error_message: str
    attempts: int
    created_at: datetime | None = None
    last_attempt_at: datetime | None = None
    wait_time_ms: float = 0


class QueueMetricAggregateRead(BaseModel):
    queue_backend: str
    total_count: int = 0
    success_count: int = 0
    failed_count: int = 0
    avg_duration_ms: float = 0
    avg_wait_time_ms: float = 0
    avg_attempts: float = 0


class RoutingSummary(BaseModel):
    categories: list[str] = Field(default_factory=list)
    channels: list[str] = Field(default_factory=list)
    rule_count: int = 0
    enabled_count: int = 0
