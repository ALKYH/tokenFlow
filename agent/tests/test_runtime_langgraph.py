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

from agent.runtime_langgraph.engine import LangGraphRuntime, build_minimal_chain_plan
from agent.runtime_langgraph.types import GraphNode, GraphPlan


def test_state_lifecycle_success() -> None:
    runtime = LangGraphRuntime()
    plan = build_minimal_chain_plan()

    state = runtime.run(plan, initial_state={"input": {}, "context": {}, "resources": {}, "trace": []})

    assert state["error"] is None
    assert state["result"] == "TOKENFLOW WEEK1"
    assert state["context"]["logs"] == ["[print] TOKENFLOW WEEK1"]

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
