from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class RetryRecordRead(BaseModel):
    node_id: str
    attempt: int
    reason: str = ""
    created_at: datetime | None = None


class NodeRunRead(BaseModel):
    node_id: str
    node_type: str
    status: str
    input_summary: str = ""
    output_summary: str = ""
    trace_json: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime | None = None
    updated_at: datetime | None = None
    completed_at: datetime | None = None


class AgentRunRead(BaseModel):
    node_id: str
    agent_name: str
    status: str
    input_summary: str = ""
    output_summary: str = ""
    trace_json: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime | None = None
    updated_at: datetime | None = None
    completed_at: datetime | None = None


class WorkflowRunRead(BaseModel):
    execution_id: str
    workflow_id: str
    workflow_version: str
    status: str
    input_summary: str = ""
    output_summary: str = ""
    trace_summary_json: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime | None = None
    updated_at: datetime | None = None
    completed_at: datetime | None = None


class WorkflowTimelineRead(BaseModel):
    execution_id: str
    workflow_id: str
    status: str
    node_runs: list[NodeRunRead] = Field(default_factory=list)
    agent_runs: list[AgentRunRead] = Field(default_factory=list)
    retries: list[RetryRecordRead] = Field(default_factory=list)
    checkpoints: list[dict[str, Any]] = Field(default_factory=list)


class WorkflowReplayRequest(BaseModel):
    workflow_id: str
    workflow_version: str = "1.0"
    execution_id: str
    node_id: str
    plan_json: dict[str, Any]


class WorkflowCancelRequest(BaseModel):
    execution_id: str


class WorkflowResumeRequest(BaseModel):
    workflow_id: str
    workflow_version: str = "1.0"
    execution_id: str
    plan_json: dict[str, Any]
