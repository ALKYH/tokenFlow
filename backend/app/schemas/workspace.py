from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class WorkspaceFileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    file_type: str
    content: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class WorkspaceFileCreate(BaseModel):
    id: int | None = None
    name: str
    description: str = ''
    file_type: str = 'workspace'
    content: dict[str, Any] = Field(default_factory=dict)
