from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, NotRequired, TypedDict

from .dsl import SubgraphRefDSL


class TraceEntry(TypedDict, total=False):
    node_id: str
    node_type: str
    phase: str
    status: str
    detail: NotRequired[str]


class ErrorInfo(TypedDict):
    node_id: str
    node_type: str
    phase: str
    error_type: str
    message: str
    traceback: str


class GraphState(TypedDict, total=False):
    input: dict[str, Any]
    context: dict[str, Any]
    resources: dict[str, Any] | list[dict[str, Any]]
    result: Any
    error: ErrorInfo | None
    trace: list[TraceEntry]
    spans: list[dict[str, Any]]
    workflow_id: str
    workflow_version: str
    execution: dict[str, Any]


@dataclass(frozen=True)
class GraphNode:
    node_id: str
    node_type: str
    config: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GraphPlan:
    nodes: list[GraphNode]
    edges: list[tuple[str, str]]
    entrypoint: str | None = None


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 1
    backoff_seconds: float = 0.0


@dataclass(frozen=True)
class TimeoutPolicy:
    timeout_seconds: float | None = None


@dataclass(frozen=True)
class RoutePolicy:
    mode: str = "direct"
    target_kind: str | None = None
    target_ref: str | None = None
    top_k: int = 1
    config: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BranchCondition:
    expression: str
    label: str | None = None


@dataclass(frozen=True)
class ExecutionEdge:
    source: str
    target: str
    condition: str | None = None
    conditions: tuple[BranchCondition, ...] = ()
    router: RoutePolicy | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExecutionNode:
    node_id: str
    node_type: str
    config: dict[str, Any] = field(default_factory=dict)
    incoming_count: int = 0
    outgoing: tuple[ExecutionEdge, ...] = ()
    retry: RetryPolicy | None = None
    timeout: TimeoutPolicy | None = None
    router: RoutePolicy | None = None
    subgraph: SubgraphRefDSL | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExecutablePlan:
    workflow_id: str
    version: str
    entrypoint: str
    nodes: list[ExecutionNode]
    retry: RetryPolicy | None = None
    timeout: TimeoutPolicy | None = None
    router: RoutePolicy | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    fingerprint: str = ""
