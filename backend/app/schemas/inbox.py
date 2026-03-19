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
    is_read: bool
    extra: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
