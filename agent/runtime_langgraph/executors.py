from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .state import append_trace, build_error_info, ensure_graph_state
from .types import GraphNode, GraphState

SAFE_BUILTINS = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "Exception": Exception,
    "enumerate": enumerate,
    "float": float,
    "int": int,
    "len": len,
    "list": list,
    "max": max,
    "min": min,
    "range": range,
    "round": round,
    "RuntimeError": RuntimeError,
    "set": set,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "ValueError": ValueError,
    "zip": zip,
}

BLACKLISTED_SNIPPET_TOKENS = (
    "__import__",
    "import os",
    "import subprocess",
    "open(",
    "exec(",
    "eval(",
)


class BaseNodeExecutor(ABC):
    def execute(self, state: GraphState, node: GraphNode) -> GraphState:
        working_state = ensure_graph_state(state)
        current_phase = "prepare"
        try:
            prepared = self.prepare(working_state, node)
            append_trace(working_state, node, phase="prepare", status="ok")

            current_phase = "run"
            output = self.run(working_state, node, prepared)
            append_trace(working_state, node, phase="run", status="ok")

            current_phase = "postprocess"
            next_state = self.postprocess(working_state, node, output)
            next_state = ensure_graph_state(next_state)
            next_state["error"] = None
            append_trace(next_state, node, phase="postprocess", status="ok")
            return next_state
        except Exception as exc:  # noqa: BLE001
            failed_state = self.on_error(working_state, node, exc, current_phase)
            append_trace(
                failed_state,
                node,
                phase="on_error",
                status="error",
                detail=f"{type(exc).__name__}: {exc}",
            )
            return failed_state

    def prepare(self, state: GraphState, node: GraphNode) -> Any:
        return None

    @abstractmethod
    def run(self, state: GraphState, node: GraphNode, prepared: Any) -> Any:
        raise NotImplementedError

    def postprocess(self, state: GraphState, node: GraphNode, output: Any) -> GraphState:
        next_state = ensure_graph_state(state)
        context = next_state["context"]
        outputs = context.get("node_outputs")
        if not isinstance(outputs, dict):
            outputs = {}
            context["node_outputs"] = outputs
        outputs[node.node_id] = output
        next_state["result"] = output
        return next_state

    def on_error(self, state: GraphState, node: GraphNode, exc: Exception, phase: str) -> GraphState:
        next_state = ensure_graph_state(state)
        next_state["error"] = build_error_info(node=node, phase=phase, exc=exc)
        return next_state


class ConstNodeExecutor(BaseNodeExecutor):
    def prepare(self, state: GraphState, node: GraphNode) -> Any:
        config = node.config
        if "input_key" in config:
            key = str(config.get("input_key"))
            return state["input"].get(key, config.get("default"))
        return config.get("value")

    def run(self, state: GraphState, node: GraphNode, prepared: Any) -> Any:
        return prepared


class PythonSnippetNodeExecutor(BaseNodeExecutor):
    def prepare(self, state: GraphState, node: GraphNode) -> dict[str, Any]:
        config = node.config
        source = str(config.get("source", "")).strip()
        if not source:
            raise ValueError("python_snippet 节点缺少 module.source")

        function_name = str(config.get("function_name", "__tokenflow_node_entry")).strip()
        if not function_name:
            raise ValueError("python_snippet 节点缺少 module.function_name")

        explicit_args = "args" in config or "kwargs" in config
        args = config.get("args")
        kwargs = config.get("kwargs")
        if not explicit_args:
            args = [state.get("result"), state.get("context"), state.get("resources")]
            kwargs = {}

        return {
            "source": source,
            "function_name": function_name,
            "args": list(args or []),
            "kwargs": dict(kwargs or {}),
        }

    def run(self, state: GraphState, node: GraphNode, prepared: dict[str, Any]) -> Any:
        source = prepared["source"]
        for token in BLACKLISTED_SNIPPET_TOKENS:
            if token in source:
                raise ValueError(f"python_snippet 含有不允许的调用: {token}")

        function_name = prepared["function_name"]
        globals_scope = {"__builtins__": SAFE_BUILTINS}
        locals_scope: dict[str, Any] = {}
        exec(source, globals_scope, locals_scope)  # noqa: S102

        callable_target = locals_scope.get(function_name) or globals_scope.get(function_name)
        if not callable(callable_target):
            raise ValueError(f"module.function_name 未在 source 中定义: {function_name}")

        return callable_target(*prepared["args"], **prepared["kwargs"])


class PrintNodeExecutor(BaseNodeExecutor):
    def prepare(self, state: GraphState, node: GraphNode) -> dict[str, Any]:
        return {
            "prefix": str(node.config.get("prefix", "")),
            "value": state.get("result"),
        }

    def run(self, state: GraphState, node: GraphNode, prepared: dict[str, Any]) -> str:
        return f"{prepared['prefix']}{prepared['value']}"

    def postprocess(self, state: GraphState, node: GraphNode, output: str) -> GraphState:
        next_state = super().postprocess(state, node, output)
        context = next_state["context"]
        logs = context.get("logs")
        if not isinstance(logs, list):
            logs = []
            context["logs"] = logs
        logs.append(output)
        next_state["result"] = state.get("result")
        return next_state
