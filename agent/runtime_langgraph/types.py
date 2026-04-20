from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, NotRequired, TypedDict


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

