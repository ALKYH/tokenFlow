from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


SUPPORTED_DSL_VERSION = "1.0"


@dataclass(frozen=True)
class RetryPolicyDSL:
    max_attempts: int = 1
    backoff_seconds: float = 0.0


@dataclass(frozen=True)
class TimeoutPolicyDSL:
    timeout_seconds: float | None = None


@dataclass(frozen=True)
class RoutePolicyDSL:
    mode: str = "direct"
    target_kind: str | None = None
    target_ref: str | None = None
    top_k: int = 1
    config: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BranchConditionDSL:
    expression: str
    label: str | None = None


@dataclass(frozen=True)
class SubgraphRefDSL:
    workflow_id: str
    version: str | None = None
    entrypoint: str | None = None


@dataclass(frozen=True)
class WorkflowNodeDSL:
    node_id: str
    node_type: str
    config: dict[str, Any] = field(default_factory=dict)
    retry: RetryPolicyDSL | None = None
    timeout: TimeoutPolicyDSL | None = None
    router: RoutePolicyDSL | None = None
    subgraph: SubgraphRefDSL | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WorkflowEdgeDSL:
    source: str
    target: str
    condition: str | None = None
    conditions: tuple[BranchConditionDSL, ...] = ()
    router: RoutePolicyDSL | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WorkflowDSL:
    version: str
    workflow_id: str
    nodes: list[WorkflowNodeDSL]
    edges: list[WorkflowEdgeDSL]
    entrypoint: str | None = None
    retry: RetryPolicyDSL | None = None
    timeout: TimeoutPolicyDSL | None = None
    router: RoutePolicyDSL | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def workflow_dsl_template(workflow_id: str = "wf_template") -> WorkflowDSL:
    return WorkflowDSL(
        version=SUPPORTED_DSL_VERSION,
        workflow_id=workflow_id,
        nodes=[
            WorkflowNodeDSL(
                node_id="const_1",
                node_type="const",
                config={"value": "hello"},
            ),
            WorkflowNodeDSL(
                node_id="print_1",
                node_type="print",
                config={"prefix": "[template] "},
            ),
        ],
        edges=[WorkflowEdgeDSL(source="const_1", target="print_1")],
        entrypoint="const_1",
        metadata={"template": True},
    )


def normalize_frontend_workflow_payload(payload: dict[str, Any]) -> WorkflowDSL:
    raw_nodes = payload.get("nodes", [])
    raw_edges = payload.get("edges", [])
    nodes = [
        WorkflowNodeDSL(
            node_id=str(item.get("node_id") or item.get("id") or "").strip(),
            node_type=str(item.get("node_type") or item.get("type") or "").strip(),
            config=dict(item.get("config") or item.get("data") or {}),
            metadata=dict(item.get("metadata") or {}),
        )
        for item in raw_nodes
    ]
    edges = [
        WorkflowEdgeDSL(
            source=str(item.get("source") or "").strip(),
            target=str(item.get("target") or "").strip(),
            condition=item.get("condition"),
            metadata=dict(item.get("metadata") or {}),
        )
        for item in raw_edges
    ]
    return WorkflowDSL(
        version=str(payload.get("version") or SUPPORTED_DSL_VERSION),
        workflow_id=str(payload.get("workflow_id") or payload.get("id") or "workflow").strip(),
        nodes=nodes,
        edges=edges,
        entrypoint=payload.get("entrypoint"),
        metadata=dict(payload.get("metadata") or {}),
    )
