from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class InboxMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    body: str
    category: str
    channel: str
    source: str
    is_read: bool
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class InboxMessageCreate(BaseModel):
    title: str
    body: str = ''
    category: str = 'system'
    channel: str = 'dashboard'
    source: str = 'manual'
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)


class InboxMessageReadUpdate(BaseModel):
    ids: list[int] = Field(default_factory=list)
    is_read: bool = True


class InboxChannelSummary(BaseModel):
    channel: str
    count: int = 0
    unread: int = 0
