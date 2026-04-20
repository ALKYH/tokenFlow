from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

try:
    from langgraph.graph import END, StateGraph
except ModuleNotFoundError as exc:  # pragma: no cover
    raise ModuleNotFoundError(
        "langgraph 未安装，请先执行: pip install -r agent/requirements.txt"
    ) from exc

from .registry import NodeRegistry, create_default_registry
from .state import append_trace, ensure_graph_state
from .graph_types import GraphNode, GraphPlan, GraphState


@dataclass
class CompiledRuntimeGraph:
    _graph: Any

    def invoke(self, initial_state: GraphState | None = None) -> GraphState:
        state = ensure_graph_state(initial_state)
        result = self._graph.invoke(state)
        return ensure_graph_state(result)

    async def ainvoke(self, initial_state: GraphState | None = None) -> GraphState:
        state = ensure_graph_state(initial_state)
        result = await self._graph.ainvoke(state)
        return ensure_graph_state(result)


class LangGraphRuntime:
    def __init__(self, registry: NodeRegistry | None = None) -> None:
        self.registry = registry or create_default_registry()

    def build_runner(self, plan: GraphPlan) -> CompiledRuntimeGraph:
        self._validate_plan(plan)
        graph = StateGraph(GraphState)

        node_map = {node.node_id: node for node in plan.nodes}
        for node in plan.nodes:
            executor = self.registry.create(node.node_type)
            graph.add_node(node.node_id, self._build_node_runner(node, executor.execute))

        entrypoint = self._resolve_entrypoint(plan)
        graph.set_entry_point(entrypoint)

        outgoing_map: dict[str, set[str]] = {node.node_id: set() for node in plan.nodes}
        for source, target in plan.edges:
            outgoing_map[source].add(target)
            graph.add_edge(source, target)

        for node_id in node_map:
            if not outgoing_map[node_id]:
                graph.add_edge(node_id, END)

        compiled = graph.compile()
        return CompiledRuntimeGraph(compiled)

    def run(self, plan: GraphPlan, initial_state: GraphState | None = None) -> GraphState:
        runner = self.build_runner(plan)
        return runner.invoke(initial_state=initial_state)

    def _build_node_runner(
        self,
        node: GraphNode,
        executor_fn: Callable[[GraphState, GraphNode], GraphState],
    ) -> Callable[[GraphState], GraphState]:
        def run_node(state: GraphState) -> GraphState:
            safe_state = ensure_graph_state(state)
            if safe_state.get("error"):
                append_trace(
                    safe_state,
                    node,
                    phase="prepare",
                    status="skipped",
                    detail="previous node failed",
                )
                return safe_state
            return executor_fn(safe_state, node)

        return run_node

    def _validate_plan(self, plan: GraphPlan) -> None:
        if not plan.nodes:
            raise ValueError("GraphPlan 不能为空")
        node_ids = [node.node_id for node in plan.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("GraphPlan 存在重复 node_id")

        node_id_set = set(node_ids)
        for node in plan.nodes:
            if not self.registry.has(node.node_type):
                raise ValueError(f"node_type 未注册: {node.node_type}")

        for source, target in plan.edges:
            if source not in node_id_set or target not in node_id_set:
                raise ValueError(f"边引用了不存在节点: {source} -> {target}")

        if plan.entrypoint and plan.entrypoint not in node_id_set:
            raise ValueError(f"entrypoint 不存在: {plan.entrypoint}")

    def _resolve_entrypoint(self, plan: GraphPlan) -> str:
        if plan.entrypoint:
            return plan.entrypoint

        incoming = {target for _, target in plan.edges}
        for node in plan.nodes:
            if node.node_id not in incoming:
                return node.node_id
        return plan.nodes[0].node_id


def build_minimal_chain_plan() -> GraphPlan:
    source = (
        "def __tokenflow_node_entry(value, context, resources):\n"
        "    text = '' if value is None else str(value)\n"
        "    return text.upper()\n"
    )
    nodes = [
        GraphNode(node_id="const_1", node_type="const", config={"value": "tokenflow week1"}),
        GraphNode(
            node_id="python_snippet_1",
            node_type="python_snippet",
            config={
                "source": source,
                "function_name": "__tokenflow_node_entry",
            },
        ),
        GraphNode(node_id="print_1", node_type="print", config={"prefix": "[print] "}),
    ]
    edges = [("const_1", "python_snippet_1"), ("python_snippet_1", "print_1")]
    return GraphPlan(nodes=nodes, edges=edges, entrypoint="const_1")
