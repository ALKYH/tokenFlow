from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any

from .dsl import (
    SUPPORTED_DSL_VERSION,
    BranchConditionDSL,
    RetryPolicyDSL,
    RoutePolicyDSL,
    SubgraphRefDSL,
    TimeoutPolicyDSL,
    WorkflowDSL,
    WorkflowEdgeDSL,
    WorkflowNodeDSL,
)
from .graph_types import (
    BranchCondition,
    ExecutablePlan,
    ExecutionEdge,
    ExecutionNode,
    GraphPlan,
    RetryPolicy,
    RoutePolicy,
    TimeoutPolicy,
)


@dataclass(frozen=True)
class WorkflowIRNode:
    node_id: str
    node_type: str
    config: dict[str, Any] = field(default_factory=dict)
    retry: RetryPolicy | None = None
    timeout: TimeoutPolicy | None = None
    router: RoutePolicy | None = None
    subgraph: SubgraphRefDSL | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WorkflowIREdge:
    source: str
    target: str
    condition: str | None = None
    conditions: tuple[BranchCondition, ...] = ()
    router: RoutePolicy | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WorkflowIRBranch:
    source: str
    target: str
    conditions: tuple[BranchCondition, ...] = ()


@dataclass(frozen=True)
class WorkflowIR:
    version: str
    workflow_id: str
    nodes: list[WorkflowIRNode]
    edges: list[WorkflowIREdge]
    branches: list[WorkflowIRBranch]
    entrypoint: str | None = None
    retry: RetryPolicy | None = None
    timeout: TimeoutPolicy | None = None
    router: RoutePolicy | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def graph_plan_to_dsl(plan: GraphPlan, workflow_id: str = "graph-plan") -> WorkflowDSL:
    nodes = [
        WorkflowNodeDSL(node_id=node.node_id, node_type=node.node_type, config=dict(node.config))
        for node in plan.nodes
    ]
    edges = [WorkflowEdgeDSL(source=source, target=target) for source, target in plan.edges]
    return WorkflowDSL(
        version=SUPPORTED_DSL_VERSION,
        workflow_id=workflow_id,
        nodes=nodes,
        edges=edges,
        entrypoint=plan.entrypoint,
        metadata={},
    )


def compile_workflow_dsl(workflow: WorkflowDSL) -> ExecutablePlan:
    ir = build_workflow_ir(workflow)
    return compile_workflow_ir(ir)


def build_workflow_ir(workflow: WorkflowDSL) -> WorkflowIR:
    normalized = normalize_workflow_dsl(workflow)
    _validate_dsl(normalized)
    edges = [
        WorkflowIREdge(
            source=edge.source,
            target=edge.target,
            condition=edge.condition,
            conditions=tuple(_to_branch_condition(item) for item in edge.conditions),
            router=_to_route_policy(edge.router),
            metadata=dict(edge.metadata),
        )
        for edge in normalized.edges
    ]
    return WorkflowIR(
        version=normalized.version,
        workflow_id=normalized.workflow_id,
        nodes=[
            WorkflowIRNode(
                node_id=node.node_id,
                node_type=node.node_type,
                config=dict(node.config),
                retry=_merge_retry_policy(normalized.retry, _to_retry_policy(node.retry)),
                timeout=_merge_timeout_policy(normalized.timeout, _to_timeout_policy(node.timeout)),
                router=_merge_route_policy(normalized.router, _to_route_policy(node.router)),
                subgraph=node.subgraph,
                metadata=dict(node.metadata),
            )
            for node in normalized.nodes
        ],
        edges=edges,
        branches=[
            WorkflowIRBranch(source=edge.source, target=edge.target, conditions=edge.conditions)
            for edge in edges
            if edge.conditions
        ],
        entrypoint=normalized.entrypoint,
        retry=_to_retry_policy(normalized.retry),
        timeout=_to_timeout_policy(normalized.timeout),
        router=_to_route_policy(normalized.router),
        metadata=dict(normalized.metadata),
    )


def compile_workflow_ir(ir: WorkflowIR) -> ExecutablePlan:
    node_ids = [node.node_id for node in ir.nodes]
    node_id_set = set(node_ids)
    incoming_count = {node_id: 0 for node_id in node_ids}
    outgoing_map: dict[str, list[ExecutionEdge]] = {node_id: [] for node_id in node_ids}

    for edge in ir.edges:
        if edge.source not in node_id_set or edge.target not in node_id_set:
            raise ValueError(f"edge 引用了不存在的节点: {edge.source} -> {edge.target}")
        incoming_count[edge.target] += 1
        outgoing_map[edge.source].append(
            ExecutionEdge(
                source=edge.source,
                target=edge.target,
                condition=edge.condition,
                conditions=edge.conditions,
                router=edge.router,
                metadata=dict(edge.metadata),
            )
        )

    entrypoint = ir.entrypoint or _resolve_entrypoint(node_ids=node_ids, incoming_count=incoming_count)
    nodes = [
        ExecutionNode(
            node_id=node.node_id,
            node_type=node.node_type,
            config=dict(node.config),
            incoming_count=incoming_count[node.node_id],
            outgoing=tuple(outgoing_map[node.node_id]),
            retry=node.retry,
            timeout=node.timeout,
            router=node.router,
            subgraph=node.subgraph,
            metadata=dict(node.metadata),
        )
        for node in ir.nodes
    ]
    fingerprint = _build_plan_fingerprint(ir, entrypoint=entrypoint)
    return ExecutablePlan(
        workflow_id=ir.workflow_id,
        version=ir.version,
        entrypoint=entrypoint,
        nodes=nodes,
        retry=ir.retry,
        timeout=ir.timeout,
        router=ir.router,
        metadata={**dict(ir.metadata), "fingerprint": fingerprint},
        fingerprint=fingerprint,
    )


def normalize_workflow_dsl(workflow: WorkflowDSL) -> WorkflowDSL:
    return WorkflowDSL(
        version=(workflow.version or SUPPORTED_DSL_VERSION).strip() or SUPPORTED_DSL_VERSION,
        workflow_id=str(workflow.workflow_id).strip(),
        nodes=[
            WorkflowNodeDSL(
                node_id=str(node.node_id).strip(),
                node_type=str(node.node_type).strip(),
                config=dict(node.config),
                retry=node.retry or workflow.retry,
                timeout=node.timeout or workflow.timeout,
                router=node.router or workflow.router,
                subgraph=node.subgraph,
                metadata=dict(node.metadata),
            )
            for node in workflow.nodes
        ],
        edges=[
            WorkflowEdgeDSL(
                source=str(edge.source).strip(),
                target=str(edge.target).strip(),
                condition=edge.condition,
                conditions=tuple(edge.conditions),
                router=edge.router or workflow.router,
                metadata=dict(edge.metadata),
            )
            for edge in workflow.edges
        ],
        entrypoint=str(workflow.entrypoint).strip() if workflow.entrypoint else None,
        retry=workflow.retry or RetryPolicyDSL(),
        timeout=workflow.timeout,
        router=workflow.router,
        metadata=dict(workflow.metadata),
    )


def _validate_dsl(workflow: WorkflowDSL) -> None:
    if workflow.version != SUPPORTED_DSL_VERSION:
        raise ValueError(f"unsupported workflow DSL version: {workflow.version}")
    if not workflow.workflow_id:
        raise ValueError("workflow_id 不能为空")
    if not workflow.nodes:
        raise ValueError("workflow.nodes 不能为空")

    node_ids = [node.node_id for node in workflow.nodes]
    if len(node_ids) != len(set(node_ids)):
        raise ValueError("workflow.nodes 存在重复 node_id")

    for node in workflow.nodes:
        if not node.node_id:
            raise ValueError("node_id 不能为空")
        if not node.node_type:
            raise ValueError(f"node_type 不能为空: {node.node_id}")
        if node.retry and node.retry.max_attempts < 1:
            raise ValueError(f"retry.max_attempts 必须大于 0: {node.node_id}")
        if node.timeout and node.timeout.timeout_seconds is not None and node.timeout.timeout_seconds <= 0:
            raise ValueError(f"timeout.timeout_seconds 必须大于 0: {node.node_id}")
        if node.subgraph and not node.subgraph.workflow_id.strip():
            raise ValueError(f"subgraph.workflow_id 不能为空: {node.node_id}")

    node_id_set = set(node_ids)
    seen_edges: set[tuple[str, str, str | None]] = set()
    for edge in workflow.edges:
        if edge.source not in node_id_set or edge.target not in node_id_set:
            raise ValueError(f"edge 引用了不存在的节点: {edge.source} -> {edge.target}")
        edge_key = (edge.source, edge.target, edge.condition)
        if edge_key in seen_edges:
            raise ValueError(f"workflow.edges 存在重复边: {edge.source} -> {edge.target}")
        seen_edges.add(edge_key)
        if edge.condition and edge.conditions:
            raise ValueError(f"edge.condition 与 edge.conditions 不能同时存在: {edge.source} -> {edge.target}")
        for branch in edge.conditions:
            if not branch.expression.strip():
                raise ValueError(f"branch.expression 不能为空: {edge.source} -> {edge.target}")

    if workflow.entrypoint and workflow.entrypoint not in node_id_set:
        raise ValueError(f"entrypoint 不存在: {workflow.entrypoint}")

    _validate_acyclic_graph(workflow)


def _validate_acyclic_graph(workflow: WorkflowDSL) -> None:
    adjacency: dict[str, list[str]] = {node.node_id: [] for node in workflow.nodes}
    indegree: dict[str, int] = {node.node_id: 0 for node in workflow.nodes}
    for edge in workflow.edges:
        adjacency[edge.source].append(edge.target)
        indegree[edge.target] += 1

    queue = [node_id for node_id, count in indegree.items() if count == 0]
    visited_count = 0
    while queue:
        current = queue.pop(0)
        visited_count += 1
        for target in adjacency[current]:
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
    if visited_count != len(workflow.nodes):
        raise ValueError("workflow DAG 存在循环依赖")


def _resolve_entrypoint(node_ids: list[str], incoming_count: dict[str, int]) -> str:
    zero_incoming = [node_id for node_id in node_ids if incoming_count[node_id] == 0]
    if zero_incoming:
        return zero_incoming[0]
    return node_ids[0]


def _to_retry_policy(policy: RetryPolicyDSL | None) -> RetryPolicy | None:
    if policy is None:
        return None
    return RetryPolicy(max_attempts=policy.max_attempts, backoff_seconds=policy.backoff_seconds)


def _to_timeout_policy(policy: TimeoutPolicyDSL | None) -> TimeoutPolicy | None:
    if policy is None:
        return None
    return TimeoutPolicy(timeout_seconds=policy.timeout_seconds)


def _to_route_policy(policy: RoutePolicyDSL | None) -> RoutePolicy | None:
    if policy is None:
        return None
    return RoutePolicy(
        mode=policy.mode,
        target_kind=policy.target_kind,
        target_ref=policy.target_ref,
        top_k=policy.top_k,
        config=dict(policy.config),
    )


def _to_branch_condition(condition: BranchConditionDSL) -> BranchCondition:
    return BranchCondition(expression=condition.expression, label=condition.label)


def _merge_retry_policy(base: RetryPolicy | None, override: RetryPolicy | None) -> RetryPolicy | None:
    return override or base


def _merge_timeout_policy(base: TimeoutPolicy | None, override: TimeoutPolicy | None) -> TimeoutPolicy | None:
    return override or base


def _merge_route_policy(base: RoutePolicy | None, override: RoutePolicy | None) -> RoutePolicy | None:
    return override or base


def _build_plan_fingerprint(ir: WorkflowIR, *, entrypoint: str) -> str:
    payload = {
        "version": ir.version,
        "workflow_id": ir.workflow_id,
        "entrypoint": entrypoint,
        "retry": asdict(ir.retry) if ir.retry else None,
        "timeout": asdict(ir.timeout) if ir.timeout else None,
        "router": asdict(ir.router) if ir.router else None,
        "metadata": ir.metadata,
        "nodes": [
            {
                "node_id": node.node_id,
                "node_type": node.node_type,
                "config": node.config,
                "retry": asdict(node.retry) if node.retry else None,
                "timeout": asdict(node.timeout) if node.timeout else None,
                "router": asdict(node.router) if node.router else None,
                "subgraph": asdict(node.subgraph) if node.subgraph else None,
                "metadata": node.metadata,
            }
            for node in ir.nodes
        ],
        "edges": [
            {
                "source": edge.source,
                "target": edge.target,
                "condition": edge.condition,
                "conditions": [asdict(item) for item in edge.conditions],
                "router": asdict(edge.router) if edge.router else None,
                "metadata": edge.metadata,
            }
            for edge in ir.edges
        ],
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    return digest
