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


class RoutingClassifyRequest(BaseModel):
    category: str
    channel: str
    text: str
    use_ai: bool = False
    ai_endpoint: str | None = None
    api_key: str | None = None
    model: str | None = None


class RoutingClassifyResponse(BaseModel):
    mode: str
    matched: bool
    rule_name: str | None = None
    score: float = 0
    reason: str = ''
    target: dict[str, Any] = Field(default_factory=dict)
