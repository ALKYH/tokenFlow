from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from time import sleep

from .checkpoint import CheckpointStore, InMemoryCheckpointStore, RuntimeCheckpoint
from .compiler import compile_workflow_dsl, graph_plan_to_dsl
from .dsl import WorkflowDSL
from .graph_types import ExecutablePlan, ExecutionEdge, ExecutionNode, GraphNode, GraphPlan, GraphState
from .registry import NodeRegistry, create_default_registry
from .state import append_trace, ensure_graph_state


TERMINAL_NODE_STATES = {"success", "failed", "timeout", "skipped", "cancelled"}


@dataclass
class CompiledRuntimeGraph:
    _plan: ExecutablePlan
    _registry: NodeRegistry
    _checkpoint_store: CheckpointStore
    _workflow_catalog: dict[str, WorkflowDSL | ExecutablePlan]

    def invoke(self, initial_state: GraphState | None = None) -> GraphState:
        runtime = LangGraphRuntime(
            registry=self._registry,
            checkpoint_store=self._checkpoint_store,
            workflow_catalog=self._workflow_catalog,
        )
        return runtime.run_executable_plan(self._plan, initial_state=initial_state)

    async def ainvoke(self, initial_state: GraphState | None = None) -> GraphState:
        return self.invoke(initial_state=initial_state)


class LangGraphRuntime:
    def __init__(
        self,
        registry: NodeRegistry | None = None,
        checkpoint_store: CheckpointStore | None = None,
        workflow_catalog: dict[str, WorkflowDSL | ExecutablePlan] | None = None,
    ) -> None:
        self.registry = registry or create_default_registry()
        self.checkpoint_store = checkpoint_store or InMemoryCheckpointStore()
        self.workflow_catalog = dict(workflow_catalog or {})

    def build_runner(self, plan: GraphPlan) -> CompiledRuntimeGraph:
        workflow = graph_plan_to_dsl(plan)
        return self.build_runner_from_dsl(workflow)

    def build_runner_from_dsl(self, workflow: WorkflowDSL) -> CompiledRuntimeGraph:
        executable_plan = compile_workflow_dsl(workflow)
        self._validate_executable_plan(executable_plan)
        return CompiledRuntimeGraph(
            executable_plan,
            self.registry,
            self.checkpoint_store,
            self.workflow_catalog,
        )

    def run(self, plan: GraphPlan, initial_state: GraphState | None = None) -> GraphState:
        return self.build_runner(plan).invoke(initial_state=initial_state)

    def run_workflow(self, workflow: WorkflowDSL, initial_state: GraphState | None = None) -> GraphState:
        return self.build_runner_from_dsl(workflow).invoke(initial_state=initial_state)

    def run_executable_plan(
        self,
        plan: ExecutablePlan,
        initial_state: GraphState | None = None,
        execution_id: str | None = None,
        start_node_id: str | None = None,
    ) -> GraphState:
        self._validate_executable_plan(plan)
        state = ensure_graph_state(initial_state)
        state["workflow_id"] = plan.workflow_id
        state["workflow_version"] = plan.version
        effective_execution_id = execution_id or str(
            state.get("execution", {}).get("execution_id") or f"{plan.workflow_id}:run"
        )
        execution = state["execution"]
        execution["execution_id"] = effective_execution_id
        execution["status"] = "running"
        execution.setdefault("retry_counts", {})
        execution.setdefault("checkpoints", [])
        execution.setdefault("activated_edges", {})
        execution.setdefault("cancel_requested", False)
        execution["node_statuses"] = {
            node.node_id: execution.get("node_statuses", {}).get(node.node_id, "pending")
            for node in plan.nodes
        }

        node_map = {node.node_id: node for node in plan.nodes}
        predecessors = self._build_predecessor_map(plan)
        processed_predecessors: dict[str, set[str]] = {node.node_id: set() for node in plan.nodes}
        active_predecessors: dict[str, set[str]] = {node.node_id: set() for node in plan.nodes}
        ready_queue = [start_node_id or plan.entrypoint]
        queued = {start_node_id or plan.entrypoint}

        if start_node_id:
            self._prepare_resume_state(
                plan=plan,
                state=state,
                processed_predecessors=processed_predecessors,
                active_predecessors=active_predecessors,
                predecessors=predecessors,
                start_node_id=start_node_id,
            )

        while ready_queue:
            execution = state["execution"]
            if execution.get("cancel_requested"):
                execution["status"] = "cancelled"
                break

            node_id = ready_queue.pop(0)
            node = node_map[node_id]
            queued.discard(node_id)
            if execution["node_statuses"][node_id] != "pending":
                continue

            if state.get("error"):
                execution["node_statuses"][node_id] = "skipped"
                append_trace(
                    state,
                    GraphNode(node_id=node.node_id, node_type=node.node_type, config=node.config),
                    phase="prepare",
                    status="skipped",
                    detail="previous node failed",
                )
                continue

            execution["node_statuses"][node_id] = "running"
            state = self._execute_node_with_policy(plan=plan, state=state, node=node)
            execution = state["execution"]
            self._save_checkpoint(
                state=state,
                node=node,
                execution_id=effective_execution_id,
            )

            activated_edges = self._resolve_activated_edges(state=state, node=node)
            for edge in node.outgoing:
                processed_predecessors[edge.target].add(node.node_id)
                is_active = edge in activated_edges
                execution["activated_edges"][f"{edge.source}->{edge.target}"] = is_active
                if is_active:
                    active_predecessors[edge.target].add(node.node_id)
                self._maybe_queue_target(
                    state=state,
                    target_id=edge.target,
                    predecessors=predecessors,
                    processed_predecessors=processed_predecessors,
                    active_predecessors=active_predecessors,
                    node_map=node_map,
                    ready_queue=ready_queue,
                    queued=queued,
                )

            node_status = execution["node_statuses"][node_id]
            if node_status in {"failed", "timeout", "cancelled"} and execution["status"] == "running":
                execution["status"] = node_status if node_status != "failed" else "failed"

        execution = state["execution"]
        if execution["status"] == "running":
            execution["status"] = "success" if not state.get("error") else "failed"

        self._mark_unreachable_nodes(plan=plan, state=state)
        return ensure_graph_state(state)

    def cancel_execution(self, state: GraphState) -> GraphState:
        next_state = ensure_graph_state(state)
        next_state["execution"]["cancel_requested"] = True
        return next_state

    def _run_execution_node(self, state: GraphState, node: ExecutionNode) -> GraphState:
        if node.subgraph is not None:
            return self._run_subgraph_node(state=state, node=node)
        graph_node = GraphNode(node_id=node.node_id, node_type=node.node_type, config=node.config)
        executor = self.registry.create(node.node_type)
        return executor.execute(state, graph_node)

    def _execute_node_with_policy(
        self,
        plan: ExecutablePlan,
        state: GraphState,
        node: ExecutionNode,
    ) -> GraphState:
        retry_policy = node.retry or plan.retry
        timeout_policy = node.timeout or plan.timeout
        max_attempts = retry_policy.max_attempts if retry_policy is not None else 1
        backoff_seconds = retry_policy.backoff_seconds if retry_policy is not None else 0.0

        last_state = ensure_graph_state(state)
        for attempt in range(1, max_attempts + 1):
            execution = last_state["execution"]
            if execution.get("cancel_requested"):
                execution["node_statuses"][node.node_id] = "cancelled"
                execution["status"] = "cancelled"
                append_trace(
                    last_state,
                    GraphNode(node_id=node.node_id, node_type=node.node_type, config=node.config),
                    phase="prepare",
                    status="cancelled",
                    detail="workflow cancellation requested",
                )
                return last_state

            run_state = self._run_execution_node_with_timeout(
                state=last_state,
                node=node,
                timeout_seconds=timeout_policy.timeout_seconds if timeout_policy else None,
            )
            run_execution = run_state["execution"]
            if run_state.get("error") is None:
                run_execution["node_statuses"][node.node_id] = "success"
                return run_state

            if run_execution["node_statuses"].get(node.node_id) == "timeout":
                run_execution["status"] = "timeout"
                return run_state

            if attempt < max_attempts:
                run_execution["node_statuses"][node.node_id] = "retrying"
                run_execution.setdefault("retry_counts", {})
                run_execution["retry_counts"][node.node_id] = attempt
                append_trace(
                    run_state,
                    GraphNode(node_id=node.node_id, node_type=node.node_type, config=node.config),
                    phase="retry",
                    status="retrying",
                    detail=f"attempt {attempt + 1}/{max_attempts}",
                )
                if backoff_seconds > 0:
                    sleep(backoff_seconds)
                run_state["error"] = None
                run_execution["status"] = "running"
                run_execution["node_statuses"][node.node_id] = "pending"
                last_state = run_state
                continue

            run_execution["node_statuses"][node.node_id] = "failed"
            run_execution["status"] = "failed"
            return run_state

        return last_state

    def _run_execution_node_with_timeout(
        self,
        state: GraphState,
        node: ExecutionNode,
        timeout_seconds: float | None,
    ) -> GraphState:
        if timeout_seconds is None:
            return self._run_execution_node(state, node)

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(self._run_execution_node, state, node)
            try:
                return future.result(timeout=timeout_seconds)
            except FutureTimeoutError:
                timed_out_state = ensure_graph_state(state)
                graph_node = GraphNode(node_id=node.node_id, node_type=node.node_type, config=node.config)
                timed_out_state["error"] = {
                    "node_id": node.node_id,
                    "node_type": node.node_type,
                    "phase": "run",
                    "error_type": "TimeoutError",
                    "message": f"node execution timed out after {timeout_seconds}s",
                    "traceback": "",
                }
                timed_out_state["execution"]["node_statuses"][node.node_id] = "timeout"
                timed_out_state["execution"]["status"] = "timeout"
                append_trace(
                    timed_out_state,
                    graph_node,
                    phase="run",
                    status="timeout",
                    detail=f"timeout={timeout_seconds}s",
                )
                return timed_out_state

    def _run_subgraph_node(self, state: GraphState, node: ExecutionNode) -> GraphState:
        assert node.subgraph is not None
        workflow_ref = node.subgraph.workflow_id
        target = self.workflow_catalog.get(workflow_ref)
        if target is None:
            raise ValueError(f"subgraph workflow not found: {workflow_ref}")
        if isinstance(target, WorkflowDSL):
            subplan = compile_workflow_dsl(target)
        else:
            subplan = target
        sub_execution_id = f"{state.get('execution', {}).get('execution_id', state.get('workflow_id', 'wf'))}:{node.node_id}"
        sub_state = self.run_executable_plan(
            subplan,
            initial_state=state,
            execution_id=sub_execution_id,
        )
        next_state = ensure_graph_state(sub_state)
        next_state["context"].setdefault("subgraph_runs", {})[node.node_id] = {
            "workflow_id": subplan.workflow_id,
            "execution_id": sub_execution_id,
            "status": next_state["execution"].get("status"),
        }
        return next_state

    def _resolve_activated_edges(self, state: GraphState, node: ExecutionNode) -> list[ExecutionEdge]:
        if not node.outgoing:
            return []

        selected = [edge for edge in node.outgoing if self._edge_matches(state, edge)]
        route_target = self._resolve_route_targets(state=state, node=node)
        if route_target is not None:
            selected = [edge for edge in selected if edge.target in route_target]
        return selected

    def _resolve_route_targets(self, state: GraphState, node: ExecutionNode) -> set[str] | None:
        policy = node.router
        if policy is None:
            return None
        if policy.mode == "direct":
            return None
        if policy.mode == "target_node" and policy.target_ref:
            return {policy.target_ref}
        if policy.mode == "context_key":
            key = str(policy.config.get("key", "")).strip()
            if not key:
                return None
            value = state["context"].get(key, state["input"].get(key))
            if isinstance(value, str):
                return {value}
            if isinstance(value, list):
                return {str(item) for item in value}
        if policy.mode == "result":
            value = state.get("result")
            if isinstance(value, str):
                return {value}
            if isinstance(value, list):
                return {str(item) for item in value}
        return None

    def _edge_matches(self, state: GraphState, edge: ExecutionEdge) -> bool:
        if edge.condition:
            return self._evaluate_expression(state, edge.condition)
        if edge.conditions:
            return all(self._evaluate_expression(state, item.expression) for item in edge.conditions)
        return True

    def _evaluate_expression(self, state: GraphState, expression: str) -> bool:
        scope = {
            "input": state.get("input", {}),
            "context": state.get("context", {}),
            "resources": state.get("resources", {}),
            "result": state.get("result"),
            "execution": state.get("execution", {}),
        }
        return bool(eval(expression, {"__builtins__": {}}, scope))  # noqa: S307

    def _build_predecessor_map(self, plan: ExecutablePlan) -> dict[str, set[str]]:
        predecessors: dict[str, set[str]] = {node.node_id: set() for node in plan.nodes}
        for node in plan.nodes:
            for edge in node.outgoing:
                predecessors[edge.target].add(node.node_id)
        return predecessors

    def _maybe_queue_target(
        self,
        state: GraphState,
        target_id: str,
        predecessors: dict[str, set[str]],
        processed_predecessors: dict[str, set[str]],
        active_predecessors: dict[str, set[str]],
        node_map: dict[str, ExecutionNode],
        ready_queue: list[str],
        queued: set[str],
    ) -> None:
        execution = state["execution"]
        if execution["node_statuses"].get(target_id) != "pending":
            return
        required_predecessors = predecessors.get(target_id, set())
        if not required_predecessors:
            if target_id not in queued:
                ready_queue.append(target_id)
                queued.add(target_id)
            return
        if processed_predecessors[target_id] != required_predecessors:
            return
        if active_predecessors[target_id]:
            if target_id not in queued:
                ready_queue.append(target_id)
                queued.add(target_id)
            return
        execution["node_statuses"][target_id] = "skipped"
        append_trace(
            state,
            GraphNode(
                node_id=target_id,
                node_type=node_map[target_id].node_type,
                config=node_map[target_id].config,
            ),
            phase="prepare",
            status="skipped",
            detail="no active inbound edges matched",
        )

    def _mark_unreachable_nodes(self, plan: ExecutablePlan, state: GraphState) -> None:
        execution = state["execution"]
        node_statuses = execution.get("node_statuses", {})
        for node in plan.nodes:
            status = node_statuses.get(node.node_id, "pending")
            if status in TERMINAL_NODE_STATES:
                continue
            if execution.get("status") == "cancelled":
                continue
            if state.get("error") or execution.get("status") in {"failed", "timeout"}:
                node_statuses[node.node_id] = "skipped"
                append_trace(
                    state,
                    GraphNode(node_id=node.node_id, node_type=node.node_type, config=node.config),
                    phase="prepare",
                    status="skipped",
                    detail="workflow terminated before node execution",
                )
            else:
                node_statuses[node.node_id] = "success"

    def retry_execution_node(
        self,
        plan: ExecutablePlan,
        node_id: str,
        initial_state: GraphState | None = None,
        execution_id: str | None = None,
    ) -> GraphState:
        state = ensure_graph_state(initial_state)
        execution = state["execution"]
        retry_counts = execution.setdefault("retry_counts", {})
        retry_counts[node_id] = int(retry_counts.get(node_id, 0)) + 1
        self._reset_restart_subgraph(plan=plan, state=state, start_node_id=node_id)
        state["error"] = None
        execution["status"] = "running"
        execution["cancel_requested"] = False
        return self.run_executable_plan(
            plan=plan,
            initial_state=state,
            execution_id=execution_id,
            start_node_id=node_id,
        )

    def resume_execution(
        self,
        plan: ExecutablePlan,
        execution_id: str,
    ) -> GraphState:
        checkpoint = self.checkpoint_store.load_latest(execution_id)
        if checkpoint is None:
            raise ValueError(f"execution checkpoint not found: {execution_id}")

        state = ensure_graph_state(checkpoint.state)
        next_node_id = self._resolve_resume_target_node(plan=plan, state=state, last_node_id=checkpoint.node_id)
        if next_node_id is None:
            state["execution"]["status"] = "success" if not state.get("error") else "failed"
            return state
        return self.run_executable_plan(
            plan=plan,
            initial_state=state,
            execution_id=execution_id,
            start_node_id=next_node_id,
        )

    def _prepare_resume_state(
        self,
        plan: ExecutablePlan,
        state: GraphState,
        processed_predecessors: dict[str, set[str]],
        active_predecessors: dict[str, set[str]],
        predecessors: dict[str, set[str]],
        start_node_id: str,
    ) -> None:
        node_statuses = state["execution"].get("node_statuses", {})
        for node in plan.nodes:
            status = node_statuses.get(node.node_id)
            if status == "success":
                processed_predecessors[node.node_id] = set(predecessors.get(node.node_id, set()))
                for edge in node.outgoing:
                    processed_predecessors[edge.target].add(node.node_id)
                    active_predecessors[edge.target].add(node.node_id)
            elif node.node_id == start_node_id:
                processed_predecessors[node.node_id] = set(predecessors.get(node.node_id, set()))

    def _reset_restart_subgraph(self, plan: ExecutablePlan, state: GraphState, start_node_id: str) -> None:
        node_statuses = state["execution"].setdefault("node_statuses", {})
        queue = [start_node_id]
        visited: set[str] = set()
        node_map = {node.node_id: node for node in plan.nodes}
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            node_statuses[current] = "pending"
            node = node_map.get(current)
            if node is None:
                continue
            for edge in node.outgoing:
                if node_statuses.get(edge.target) != "success":
                    queue.append(edge.target)

    def _resolve_resume_target_node(
        self,
        plan: ExecutablePlan,
        state: GraphState,
        last_node_id: str,
    ) -> str | None:
        node_statuses = state.get("execution", {}).get("node_statuses", {})
        if state.get("error"):
            return state["error"]["node_id"]

        last_node = next((node for node in plan.nodes if node.node_id == last_node_id), None)
        if last_node is None:
            return plan.entrypoint

        for edge in last_node.outgoing:
            if node_statuses.get(edge.target, "pending") == "pending":
                return edge.target

        for node in plan.nodes:
            if node_statuses.get(node.node_id, "pending") == "pending":
                return node.node_id
        return None

    def _save_checkpoint(self, state: GraphState, node: ExecutionNode, execution_id: str) -> None:
        execution = state["execution"]
        sequence = len(execution.get("checkpoints", [])) + 1
        checkpoint = RuntimeCheckpoint(
            execution_id=execution_id,
            workflow_id=state.get("workflow_id", ""),
            workflow_version=state.get("workflow_version", ""),
            node_id=node.node_id,
            sequence=sequence,
            state=ensure_graph_state(state),
        )
        self.checkpoint_store.save(checkpoint)
        execution.setdefault("checkpoints", []).append({"node_id": node.node_id, "sequence": sequence})

    def _validate_executable_plan(self, plan: ExecutablePlan) -> None:
        if not plan.nodes:
            raise ValueError("ExecutablePlan 不能为空")

        node_ids = [node.node_id for node in plan.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("ExecutablePlan 存在重复 node_id")

        node_id_set = set(node_ids)
        if plan.entrypoint not in node_id_set:
            raise ValueError(f"entrypoint 不存在: {plan.entrypoint}")

        for node in plan.nodes:
            if node.subgraph is None and not self.registry.has(node.node_type):
                raise ValueError(f"node_type 未注册: {node.node_type}")
            for edge in node.outgoing:
                if edge.source != node.node_id:
                    raise ValueError(f"edge.source 与节点不匹配: {edge.source} != {node.node_id}")
                if edge.target not in node_id_set:
                    raise ValueError(f"edge.target 不存在: {edge.target}")


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
