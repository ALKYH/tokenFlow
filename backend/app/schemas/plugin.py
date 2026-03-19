from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class PluginRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    summary: str
    category: str
    plugin_type: str
    author_name: str
    icon: str = ''
    tags: list[str] = Field(default_factory=list)
    source: dict[str, Any] = Field(default_factory=dict)
    workspace_snapshot: dict[str, Any] | None = None
    node_template_snapshot: dict[str, Any] | None = None
    is_public: bool
    downloads: int
    installs: int
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PluginCreate(BaseModel):
    name: str
    slug: str
    summary: str = ''
    category: str = 'workflow'
    plugin_type: str = 'module'
    author_name: str = 'TokenFlow User'
    icon: str = ''
    tags: list[str] = Field(default_factory=list)
    source: dict[str, Any] = Field(default_factory=dict)
    workspace_snapshot: dict[str, Any] | None = None
    node_template_snapshot: dict[str, Any] | None = None
    is_public: bool = True


class PluginInstallResponse(BaseModel):
    installed: bool
    plugin: PluginRead
