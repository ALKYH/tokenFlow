from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys

import pytest

# Allow running this file directly (for example from IDE Code Runner) while
# preserving normal pytest package imports.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

pytest.importorskip("langgraph")

from agent.runtime_langgraph.compiler import build_workflow_ir, compile_workflow_dsl, normalize_workflow_dsl
from agent.runtime_langgraph.checkpoint import InMemoryCheckpointStore
from agent.runtime_langgraph.dsl import (
    BranchConditionDSL,
    RetryPolicyDSL,
    RoutePolicyDSL,
    SubgraphRefDSL,
    TimeoutPolicyDSL,
    WorkflowDSL,
    WorkflowEdgeDSL,
    WorkflowNodeDSL,
    normalize_frontend_workflow_payload,
    workflow_dsl_template,
)
from agent.runtime_langgraph.engine import LangGraphRuntime, build_minimal_chain_plan
from agent.runtime_langgraph.executors import HarnessNodeExecutor, create_default_harness_registry
from agent.runtime_langgraph.harness import ExecutionResult, RuntimeBackendExecutor, TraceSpan
from agent.runtime_langgraph.registry import create_default_registry
from agent.runtime_langgraph.types import GraphNode, GraphPlan


def test_state_lifecycle_success() -> None:
    runtime = LangGraphRuntime()
    plan = build_minimal_chain_plan()

    state = runtime.run(plan, initial_state={"input": {}, "context": {}, "resources": {}, "trace": []})

    assert state["error"] is None
    assert state["result"] == "TOKENFLOW WEEK1"
    assert state["context"]["logs"] == ["[print] TOKENFLOW WEEK1"]
    assert state["workflow_id"] == "graph-plan"
    assert state["workflow_version"] == "1.0"
    assert state["execution"]["status"] == "success"
    assert state["execution"]["node_statuses"] == {
        "const_1": "success",
        "python_snippet_1": "success",
        "print_1": "success",
    }

    phases = [(item["node_id"], item["phase"], item["status"]) for item in state["trace"]]
    assert phases == [
        ("const_1", "prepare", "ok"),
        ("const_1", "run", "ok"),
        ("const_1", "postprocess", "ok"),
        ("python_snippet_1", "prepare", "ok"),
        ("python_snippet_1", "run", "ok"),
        ("python_snippet_1", "postprocess", "ok"),
        ("print_1", "prepare", "ok"),
        ("print_1", "run", "ok"),
        ("print_1", "postprocess", "ok"),
    ]


def test_error_branch_sets_structured_error() -> None:
    runtime = LangGraphRuntime()
    source = (
        "def __tokenflow_node_entry(value, context, resources):\n"
        "    raise RuntimeError('boom from snippet')\n"
    )
    plan = GraphPlan(
        nodes=[
            GraphNode(node_id="const_1", node_type="const", config={"value": "boom"}),
            GraphNode(
                node_id="python_snippet_1",
                node_type="python_snippet",
                config={"source": source, "function_name": "__tokenflow_node_entry"},
            ),
            GraphNode(node_id="print_1", node_type="print", config={"prefix": "[print] "}),
        ],
        edges=[("const_1", "python_snippet_1"), ("python_snippet_1", "print_1")],
        entrypoint="const_1",
    )

    state = runtime.run(plan, initial_state={"input": {}, "context": {}, "resources": {}, "trace": []})

    assert state["error"] is not None
    assert state["error"]["node_id"] == "python_snippet_1"
    assert state["error"]["error_type"] == "RuntimeError"
    assert "boom from snippet" in state["error"]["message"]
    assert state["execution"]["status"] == "failed"
    assert state["execution"]["node_statuses"]["const_1"] == "success"
    assert state["execution"]["node_statuses"]["python_snippet_1"] == "failed"
    assert state["execution"]["node_statuses"]["print_1"] == "skipped"
    assert any(
        item["node_id"] == "python_snippet_1" and item["phase"] == "on_error" and item["status"] == "error"
        for item in state["trace"]
    )
    assert any(
        item["node_id"] == "print_1" and item["phase"] == "prepare" and item["status"] == "skipped"
        for item in state["trace"]
    )


def test_parallel_execution_has_isolated_state() -> None:
    runtime = LangGraphRuntime()
    source = (
        "def __tokenflow_node_entry(value, context, resources):\n"
        "    return f'{value}-done'\n"
    )
    plan = GraphPlan(
        nodes=[
            GraphNode(node_id="const_1", node_type="const", config={"input_key": "seed", "default": "na"}),
            GraphNode(
                node_id="python_snippet_1",
                node_type="python_snippet",
                config={"source": source, "function_name": "__tokenflow_node_entry"},
            ),
            GraphNode(node_id="print_1", node_type="print", config={"prefix": "[print] "}),
        ],
        edges=[("const_1", "python_snippet_1"), ("python_snippet_1", "print_1")],
        entrypoint="const_1",
    )

    def execute(seed: int) -> tuple[str, list[str], int]:
        state = runtime.run(
            plan,
            initial_state={"input": {"seed": seed}, "context": {}, "resources": {}, "trace": []},
        )
        assert state["error"] is None
        return state["result"], list(state["context"]["logs"]), len(state["trace"])

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(execute, range(20)))

    assert [result for result, _, _ in results] == [f"{i}-done" for i in range(20)]
    assert [logs for _, logs, _ in results] == [[f"[print] {i}-done"] for i in range(20)]
    assert all(trace_count == 9 for _, _, trace_count in results)


def test_compile_workflow_dsl_to_executable_plan() -> None:
    workflow = WorkflowDSL(
        version="1.0",
        workflow_id="wf_basic",
        retry=RetryPolicyDSL(max_attempts=2, backoff_seconds=0.1),
        timeout=TimeoutPolicyDSL(timeout_seconds=15),
        router=RoutePolicyDSL(mode="direct", top_k=1),
        nodes=[
            WorkflowNodeDSL(
                node_id="const_1",
                node_type="const",
                config={"value": "hello"},
                metadata={"role": "source"},
            ),
            WorkflowNodeDSL(
                node_id="print_1",
                node_type="print",
                config={"prefix": "[dbg] "},
                timeout=TimeoutPolicyDSL(timeout_seconds=5),
            ),
        ],
        edges=[
            WorkflowEdgeDSL(
                source="const_1",
                target="print_1",
                conditions=(BranchConditionDSL(expression="result is not None", label="has_result"),),
            )
        ],
        entrypoint="const_1",
        metadata={"name": "basic"},
    )

    ir = build_workflow_ir(workflow)
    assert ir.workflow_id == "wf_basic"
    assert len(ir.nodes) == 2
    assert ir.edges[0].source == "const_1"
    assert ir.edges[0].target == "print_1"
    assert ir.nodes[0].retry is not None
    assert ir.nodes[1].timeout is not None
    assert ir.branches[0].conditions[0].label == "has_result"

    executable_plan = compile_workflow_dsl(workflow)
    assert executable_plan.workflow_id == "wf_basic"
    assert executable_plan.version == "1.0"
    assert executable_plan.entrypoint == "const_1"
    assert executable_plan.retry is not None
    assert executable_plan.timeout is not None
    assert executable_plan.router is not None
    assert executable_plan.metadata["name"] == "basic"
    assert executable_plan.metadata["fingerprint"] == executable_plan.fingerprint
    assert [node.node_id for node in executable_plan.nodes] == ["const_1", "print_1"]
    assert executable_plan.nodes[0].incoming_count == 0
    assert executable_plan.nodes[1].incoming_count == 1
    assert executable_plan.nodes[0].outgoing[0].target == "print_1"
    assert executable_plan.nodes[0].retry is not None
    assert executable_plan.nodes[1].timeout is not None
    assert executable_plan.nodes[0].outgoing[0].conditions[0].expression == "result is not None"


def test_normalize_frontend_workflow_payload_and_template() -> None:
    template = workflow_dsl_template("wf_template_case")
    assert template.workflow_id == "wf_template_case"
    assert template.entrypoint == "const_1"
    assert len(template.nodes) == 2

    normalized = normalize_frontend_workflow_payload(
        {
            "id": "wf_ui",
            "nodes": [
                {"id": "const_1", "type": "const", "data": {"value": "hello"}},
                {"id": "print_1", "type": "print", "data": {"prefix": "[ui] "}},
            ],
            "edges": [{"source": "const_1", "target": "print_1"}],
            "entrypoint": "const_1",
            "metadata": {"source": "frontend"},
        }
    )
    assert normalized.workflow_id == "wf_ui"
    assert normalized.nodes[0].node_id == "const_1"
    assert normalized.nodes[0].config == {"value": "hello"}
    assert normalized.metadata == {"source": "frontend"}


def test_normalize_workflow_dsl_applies_workflow_level_defaults() -> None:
    workflow = WorkflowDSL(
        version="1.0",
        workflow_id="wf_defaults",
        retry=RetryPolicyDSL(max_attempts=3, backoff_seconds=0.5),
        timeout=TimeoutPolicyDSL(timeout_seconds=20),
        router=RoutePolicyDSL(mode="route", target_kind="workflow", top_k=3),
        nodes=[
            WorkflowNodeDSL(node_id="a", node_type="const", config={"value": "x"}),
            WorkflowNodeDSL(node_id="b", node_type="print", config={"prefix": "[x] "}),
        ],
        edges=[WorkflowEdgeDSL(source="a", target="b")],
    )

    normalized = normalize_workflow_dsl(workflow)
    assert normalized.nodes[0].retry == workflow.retry
    assert normalized.nodes[0].timeout == workflow.timeout
    assert normalized.nodes[0].router == workflow.router


def test_compile_workflow_dsl_rejects_cycle() -> None:
    workflow = WorkflowDSL(
        version="1.0",
        workflow_id="wf_cycle",
        nodes=[
            WorkflowNodeDSL(node_id="a", node_type="const", config={"value": "x"}),
            WorkflowNodeDSL(node_id="b", node_type="print", config={"prefix": "[x] "}),
        ],
        edges=[
            WorkflowEdgeDSL(source="a", target="b"),
            WorkflowEdgeDSL(source="b", target="a"),
        ],
    )

    with pytest.raises(ValueError, match="循环依赖"):
        compile_workflow_dsl(workflow)


def test_run_workflow_dsl_success() -> None:
    runtime = LangGraphRuntime()
    workflow = WorkflowDSL(
        version="1.0",
        workflow_id="wf_from_dsl",
        nodes=[
            WorkflowNodeDSL(node_id="const_1", node_type="const", config={"value": "tokenflow"}),
            WorkflowNodeDSL(
                node_id="python_snippet_1",
                node_type="python_snippet",
                config={
                    "source": (
                        "def __tokenflow_node_entry(value, context, resources):\n"
                        "    return str(value).upper()\n"
                    ),
                    "function_name": "__tokenflow_node_entry",
                },
            ),
            WorkflowNodeDSL(node_id="print_1", node_type="print", config={"prefix": "[dsl] "}),
        ],
        edges=[
            WorkflowEdgeDSL(source="const_1", target="python_snippet_1"),
            WorkflowEdgeDSL(source="python_snippet_1", target="print_1"),
        ],
        entrypoint="const_1",
    )

    state = runtime.run_workflow(
        workflow,
        initial_state={"input": {}, "context": {}, "resources": {}, "trace": []},
    )

    assert state["error"] is None
    assert state["result"] == "TOKENFLOW"
    assert state["context"]["logs"] == ["[dsl] TOKENFLOW"]
    assert state["workflow_id"] == "wf_from_dsl"
    assert state["workflow_version"] == "1.0"
    assert state["execution"]["status"] == "success"


def test_checkpoint_resume_and_retry() -> None:
    checkpoint_store = InMemoryCheckpointStore()
    runtime = LangGraphRuntime(checkpoint_store=checkpoint_store)
    source = (
        "def __tokenflow_node_entry(value, context, resources):\n"
        "    if context.get('should_fail_once'):\n"
        "        context['should_fail_once'] = False\n"
        "        raise RuntimeError('boom once')\n"
        "    return f'{value}-done'\n"
    )
    workflow = WorkflowDSL(
        version="1.0",
        workflow_id="wf_retry_resume",
        nodes=[
            WorkflowNodeDSL(node_id="const_1", node_type="const", config={"value": "resume"}),
            WorkflowNodeDSL(
                node_id="python_snippet_1",
                node_type="python_snippet",
                config={"source": source, "function_name": "__tokenflow_node_entry"},
            ),
            WorkflowNodeDSL(node_id="print_1", node_type="print", config={"prefix": "[resume] "}),
        ],
        edges=[
            WorkflowEdgeDSL(source="const_1", target="python_snippet_1"),
            WorkflowEdgeDSL(source="python_snippet_1", target="print_1"),
        ],
        entrypoint="const_1",
    )

    executable_plan = compile_workflow_dsl(workflow)
    failed_state = runtime.run_workflow(
        workflow,
        initial_state={
            "input": {},
            "context": {"should_fail_once": True},
            "resources": {},
            "trace": [],
        },
    )
    assert failed_state["error"] is not None
    assert failed_state["execution"]["status"] == "failed"
    assert failed_state["execution"]["node_statuses"]["const_1"] == "success"
    assert failed_state["execution"]["node_statuses"]["python_snippet_1"] == "failed"
    assert checkpoint_store.load_latest("wf_retry_resume:run") is not None

    retried_state = runtime.retry_execution_node(
        executable_plan,
        node_id="python_snippet_1",
        initial_state=failed_state,
        execution_id="wf_retry_resume:run",
    )
    assert retried_state["error"] is None
    assert retried_state["result"] == "resume-done"
    assert retried_state["context"]["logs"] == ["[resume] resume-done"]
    assert retried_state["execution"]["retry_counts"]["python_snippet_1"] == 1
    assert retried_state["execution"]["status"] == "success"

    resumed_state = runtime.resume_execution(executable_plan, execution_id="wf_retry_resume:run")
    assert resumed_state["execution"]["status"] == "success"
    assert resumed_state["context"]["logs"] == ["[resume] resume-done"]


def test_conditional_branch_skips_unmatched_path_and_allows_join() -> None:
    runtime = LangGraphRuntime()
    workflow = WorkflowDSL(
        version="1.0",
        workflow_id="wf_conditional_join",
        nodes=[
            WorkflowNodeDSL(node_id="const_1", node_type="const", config={"value": "go"}),
            WorkflowNodeDSL(node_id="print_yes", node_type="print", config={"prefix": "[yes] "}),
            WorkflowNodeDSL(node_id="print_no", node_type="print", config={"prefix": "[no] "}),
            WorkflowNodeDSL(
                node_id="join_1",
                node_type="python_snippet",
                config={
                    "source": (
                        "def __tokenflow_node_entry(value, context, resources):\n"
                        "    logs = context.get('logs', [])\n"
                        "    return logs[-1] if logs else value\n"
                    ),
                    "function_name": "__tokenflow_node_entry",
                },
            ),
        ],
        edges=[
            WorkflowEdgeDSL(
                source="const_1",
                target="print_yes",
                conditions=(BranchConditionDSL(expression="result == 'go'"),),
            ),
            WorkflowEdgeDSL(
                source="const_1",
                target="print_no",
                conditions=(BranchConditionDSL(expression="result == 'stop'"),),
            ),
            WorkflowEdgeDSL(source="print_yes", target="join_1"),
            WorkflowEdgeDSL(source="print_no", target="join_1"),
        ],
        entrypoint="const_1",
    )

    state = runtime.run_workflow(workflow, initial_state={"input": {}, "context": {}, "resources": {}, "trace": []})

    assert state["error"] is None
    assert state["execution"]["status"] == "success"
    assert state["execution"]["node_statuses"]["print_yes"] == "success"
    assert state["execution"]["node_statuses"]["print_no"] == "skipped"
    assert state["execution"]["node_statuses"]["join_1"] == "success"
    assert state["context"]["logs"] == ["[yes] go"]
    assert state["result"] == "go"
    assert state["execution"]["activated_edges"]["const_1->print_yes"] is True
    assert state["execution"]["activated_edges"]["const_1->print_no"] is False


def test_router_selects_target_node_from_context() -> None:
    runtime = LangGraphRuntime()
    workflow = WorkflowDSL(
        version="1.0",
        workflow_id="wf_router",
        nodes=[
            WorkflowNodeDSL(node_id="const_1", node_type="const", config={"value": "route"}),
            WorkflowNodeDSL(
                node_id="route_1",
                node_type="python_snippet",
                config={
                    "source": (
                        "def __tokenflow_node_entry(value, context, resources):\n"
                        "    context['selected_target'] = 'print_b'\n"
                        "    return value\n"
                    ),
                    "function_name": "__tokenflow_node_entry",
                },
                router=RoutePolicyDSL(mode="context_key", config={"key": "selected_target"}),
            ),
            WorkflowNodeDSL(node_id="print_a", node_type="print", config={"prefix": "[a] "}),
            WorkflowNodeDSL(node_id="print_b", node_type="print", config={"prefix": "[b] "}),
        ],
        edges=[
            WorkflowEdgeDSL(source="const_1", target="route_1"),
            WorkflowEdgeDSL(source="route_1", target="print_a"),
            WorkflowEdgeDSL(source="route_1", target="print_b"),
        ],
        entrypoint="const_1",
    )

    state = runtime.run_workflow(workflow, initial_state={"input": {}, "context": {}, "resources": {}, "trace": []})

    assert state["error"] is None
    assert state["execution"]["status"] == "success"
    assert state["execution"]["node_statuses"]["print_a"] == "skipped"
    assert state["execution"]["node_statuses"]["print_b"] == "success"
    assert state["context"]["logs"] == ["[b] route"]


def test_subgraph_node_runs_nested_workflow() -> None:
    child_workflow = WorkflowDSL(
        version="1.0",
        workflow_id="wf_child",
        nodes=[
            WorkflowNodeDSL(node_id="child_const", node_type="const", config={"value": "child"}),
            WorkflowNodeDSL(node_id="child_print", node_type="print", config={"prefix": "[child] "}),
        ],
        edges=[WorkflowEdgeDSL(source="child_const", target="child_print")],
        entrypoint="child_const",
    )
    runtime = LangGraphRuntime(workflow_catalog={"wf_child": child_workflow})
    workflow = WorkflowDSL(
        version="1.0",
        workflow_id="wf_parent",
        nodes=[
            WorkflowNodeDSL(
                node_id="subgraph_1",
                node_type="python_snippet",
                subgraph=SubgraphRefDSL(workflow_id="wf_child"),
            ),
        ],
        edges=[],
        entrypoint="subgraph_1",
    )

    state = runtime.run_workflow(workflow, initial_state={"input": {}, "context": {}, "resources": {}, "trace": []})

    assert state["error"] is None
    assert state["execution"]["status"] == "success"
    assert state["context"]["logs"] == ["[child] child"]
    assert state["context"]["subgraph_runs"]["subgraph_1"]["workflow_id"] == "wf_child"


def test_timeout_marks_node_and_workflow_timeout() -> None:
    runtime = LangGraphRuntime()
    workflow = WorkflowDSL(
        version="1.0",
        workflow_id="wf_timeout",
        nodes=[
            WorkflowNodeDSL(
                node_id="slow_1",
                node_type="python_snippet",
                config={
                    "source": (
                        "def __tokenflow_node_entry(value, context, resources):\n"
                        "    sleep(0.05)\n"
                        "    return 'done'\n"
                    ),
                    "function_name": "__tokenflow_node_entry",
                },
                timeout=TimeoutPolicyDSL(timeout_seconds=0.01),
            ),
        ],
        edges=[],
        entrypoint="slow_1",
    )

    state = runtime.run_workflow(workflow, initial_state={"input": {}, "context": {}, "resources": {}, "trace": []})

    assert state["error"] is not None
    assert state["error"]["error_type"] == "TimeoutError"
    assert state["execution"]["status"] == "timeout"
    assert state["execution"]["node_statuses"]["slow_1"] == "timeout"


def test_cancel_request_marks_workflow_cancelled() -> None:
    runtime = LangGraphRuntime()
    workflow = WorkflowDSL(
        version="1.0",
        workflow_id="wf_cancel",
        nodes=[
            WorkflowNodeDSL(node_id="const_1", node_type="const", config={"value": "x"}),
            WorkflowNodeDSL(node_id="print_1", node_type="print", config={"prefix": "[x] "}),
        ],
        edges=[WorkflowEdgeDSL(source="const_1", target="print_1")],
        entrypoint="const_1",
    )

    initial_state = runtime.cancel_execution({"input": {}, "context": {}, "resources": {}, "trace": []})
    state = runtime.run_workflow(workflow, initial_state=initial_state)

    assert state["execution"]["status"] == "cancelled"
    assert state["execution"]["node_statuses"]["const_1"] == "pending"
    assert state["execution"]["node_statuses"]["print_1"] == "pending"


def test_tool_skill_agent_function_harness_execution() -> None:
    runtime = LangGraphRuntime()
    workflow = WorkflowDSL(
        version="1.0",
        workflow_id="wf_harness_stack",
        nodes=[
            WorkflowNodeDSL(node_id="const_1", node_type="const", config={"value": "seed"}),
            WorkflowNodeDSL(
                node_id="tool_1",
                node_type="tool",
                config={"backend": "tool", "payload": {"tool_name": "search", "value": "tool-input"}},
            ),
            WorkflowNodeDSL(
                node_id="skill_1",
                node_type="skill",
                config={"backend": "skill", "payload": {"skill_name": "summarize", "value": "skill-input"}},
            ),
            WorkflowNodeDSL(
                node_id="agent_1",
                node_type="agent",
                config={"backend": "agent", "payload": {"agent_name": "planner", "steps": ["a", "b"]}},
            ),
            WorkflowNodeDSL(
                node_id="fn_1",
                node_type="function",
                config={
                    "backend": "function",
                    "payload": {"function_name": "emit", "arguments": {"channel": "console"}},
                },
            ),
        ],
        edges=[
            WorkflowEdgeDSL(source="const_1", target="tool_1"),
            WorkflowEdgeDSL(source="tool_1", target="skill_1"),
            WorkflowEdgeDSL(source="skill_1", target="agent_1"),
            WorkflowEdgeDSL(source="agent_1", target="fn_1"),
        ],
        entrypoint="const_1",
    )

    state = runtime.run_workflow(workflow, initial_state={"input": {}, "context": {}, "resources": {}, "trace": []})

    assert state["error"] is None
    assert state["execution"]["status"] == "success"
    assert state["context"]["node_outputs"]["tool_1"]["tool_name"] == "search"
    assert state["context"]["node_outputs"]["skill_1"]["skill_name"] == "summarize"
    assert state["context"]["node_outputs"]["agent_1"]["agent_name"] == "planner"
    assert state["context"]["node_outputs"]["fn_1"]["function_name"] == "emit"
    assert len(state["spans"]) == 4
    assert {item["executor_type"] for item in state["spans"]} == {"tool", "skill", "agent", "function_call"}


def test_runtime_backend_harness_executes_python_snippet() -> None:
    runtime = LangGraphRuntime()
    workflow = WorkflowDSL(
        version="1.0",
        workflow_id="wf_runtime_backend",
        nodes=[
            WorkflowNodeDSL(node_id="const_1", node_type="const", config={"value": "hello"}),
            WorkflowNodeDSL(
                node_id="runtime_1",
                node_type="tool",
                config={
                    "backend": "runtime",
                    "source": (
                        "def __tokenflow_node_entry(value, context, resources):\n"
                        "    return str(value).upper()\n"
                    ),
                    "function_name": "__tokenflow_node_entry",
                },
            ),
        ],
        edges=[WorkflowEdgeDSL(source="const_1", target="runtime_1")],
        entrypoint="const_1",
    )

    state = runtime.run_workflow(workflow, initial_state={"input": {}, "context": {}, "resources": {}, "trace": []})

    assert state["error"] is None
    assert state["execution"]["status"] == "success"
    assert state["result"] == "HELLO"
    assert state["context"]["backend_results"]["runtime_1"]["backend"] == "runtime"
    assert state["spans"][0]["executor_type"] == "runtime"


def test_harness_backend_can_be_overridden() -> None:
    class ReverseRuntimeExecutor(RuntimeBackendExecutor):
        executor_type = "runtime"
        layer = "runtime"

        def execute(self, request):
            value = str((request.payload.get("args") or [""])[0])
            return ExecutionResult(
                output=value[::-1],
                trace_spans=(
                    TraceSpan(
                        span_id="custom-span",
                        parent_span_id=None,
                        layer="runtime",
                        executor_type="runtime",
                        node_id=request.context.node_id,
                        status="ok",
                        detail="custom override",
                    ),
                ),
            )

    class CustomHarnessNodeExecutor(HarnessNodeExecutor):
        def __init__(self) -> None:
            harness_registry = create_default_harness_registry()
            harness_registry.register("runtime", ReverseRuntimeExecutor())
            super().__init__(harness_registry=harness_registry)

    registry = create_default_registry()
    registry.register("tool", CustomHarnessNodeExecutor)
    runtime = LangGraphRuntime(registry=registry)

    workflow = WorkflowDSL(
        version="1.0",
        workflow_id="wf_override",
        nodes=[
            WorkflowNodeDSL(node_id="const_1", node_type="const", config={"value": "hello"}),
            WorkflowNodeDSL(
                node_id="runtime_1",
                node_type="tool",
                config={
                    "backend": "runtime",
                    "source": (
                        "def __tokenflow_node_entry(value, context, resources):\n"
                        "    return value\n"
                    ),
                    "function_name": "__tokenflow_node_entry",
                },
            ),
        ],
        edges=[WorkflowEdgeDSL(source="const_1", target="runtime_1")],
        entrypoint="const_1",
    )

    state = runtime.run_workflow(workflow, initial_state={"input": {}, "context": {}, "resources": {}, "trace": []})

    assert state["error"] is None
    assert state["result"] == "olleh"


def test_harness_shared_memory_does_not_pollute_context_structures() -> None:
    runtime = LangGraphRuntime()
    workflow = WorkflowDSL(
        version="1.0",
        workflow_id="wf_context_isolation",
        nodes=[
            WorkflowNodeDSL(node_id="const_1", node_type="const", config={"value": "safe"}),
            WorkflowNodeDSL(
                node_id="agent_1",
                node_type="agent",
                config={"backend": "agent", "payload": {"agent_name": "isolated", "steps": ["one"]}},
            ),
        ],
        edges=[WorkflowEdgeDSL(source="const_1", target="agent_1")],
        entrypoint="const_1",
    )

    state = runtime.run_workflow(
        workflow,
        initial_state={
            "input": {"topic": "x"},
            "context": {"existing": True},
            "resources": {"shared": 1},
            "trace": [],
        },
    )

    assert state["error"] is None
    assert state["context"]["existing"] is True
    assert "run_context" not in state["context"]
    assert "agent_context" not in state["context"]
    assert state["context"]["backend_results"]["agent_1"]["backend"] == "agent"
