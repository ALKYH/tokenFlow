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


class RoutingSummary(BaseModel):
    categories: list[str] = Field(default_factory=list)
    channels: list[str] = Field(default_factory=list)
    rule_count: int = 0
    enabled_count: int = 0
