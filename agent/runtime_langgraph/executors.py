from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict
from time import sleep
from typing import Any
import uuid

from .graph_types import GraphNode, GraphState
from .harness import (
    AgentExecutor,
    ExecutionContext,
    ExecutionRequest,
    ExecutionResult,
    FunctionCallExecutor,
    HarnessRegistry,
    RuntimeBackendExecutor,
    SkillExecutor,
    ToolExecutor,
    TraceSpan,
)
from .state import append_span, append_trace, build_error_info, ensure_graph_state

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
    "sleep": sleep,
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
                raise ValueError(f"python_snippet 包含不允许的调用: {token}")

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


class PythonSnippetRuntimeBackend(RuntimeBackendExecutor):
    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        payload = request.payload
        source = str(payload.get("source", "")).strip()
        function_name = str(payload.get("function_name", "__tokenflow_node_entry")).strip()
        if not source:
            raise ValueError("runtime backend requires source")
        for token in BLACKLISTED_SNIPPET_TOKENS:
            if token in source:
                raise ValueError(f"runtime backend contains blocked token: {token}")

        globals_scope = {"__builtins__": SAFE_BUILTINS}
        locals_scope: dict[str, Any] = {}
        exec(source, globals_scope, locals_scope)  # noqa: S102
        callable_target = locals_scope.get(function_name) or globals_scope.get(function_name)
        if not callable(callable_target):
            raise ValueError(f"runtime backend function not found: {function_name}")

        args = list(payload.get("args") or [])
        kwargs = dict(payload.get("kwargs") or {})
        output = callable_target(*args, **kwargs)
        return ExecutionResult(output=output)


class EchoToolExecutor(ToolExecutor):
    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        payload = request.payload
        tool_name = str(payload.get("tool_name") or "tool")
        value = payload.get("value", request.context.shared_memory.get("last_result"))
        return ExecutionResult(
            output={"tool_name": tool_name, "value": value},
            metadata={"tool_name": tool_name},
        )


class EchoSkillExecutor(SkillExecutor):
    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        payload = request.payload
        skill_name = str(payload.get("skill_name") or "skill")
        value = payload.get("value", request.context.shared_memory.get("last_result"))
        return ExecutionResult(
            output={"skill_name": skill_name, "value": value},
            metadata={"skill_name": skill_name},
        )


class EchoAgentExecutor(AgentExecutor):
    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        payload = request.payload
        agent_name = str(payload.get("agent_name") or "agent")
        steps = list(payload.get("steps") or [])
        output = {
            "agent_name": agent_name,
            "steps": steps,
            "input": payload.get("value", request.context.shared_memory.get("last_result")),
        }
        return ExecutionResult(output=output, metadata={"agent_name": agent_name})


class EchoFunctionCallExecutor(FunctionCallExecutor):
    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        payload = request.payload
        function_name = str(payload.get("function_name") or "function")
        arguments = dict(payload.get("arguments") or {})
        return ExecutionResult(
            output={"function_name": function_name, "arguments": arguments},
            metadata={"function_name": function_name},
        )


def create_default_harness_registry() -> HarnessRegistry:
    registry = HarnessRegistry()
    registry.register("runtime", PythonSnippetRuntimeBackend())
    registry.register("tool", EchoToolExecutor())
    registry.register("skill", EchoSkillExecutor())
    registry.register("agent", EchoAgentExecutor())
    registry.register("function", EchoFunctionCallExecutor())
    return registry


class HarnessNodeExecutor(BaseNodeExecutor):
    def __init__(self, harness_registry: HarnessRegistry | None = None) -> None:
        self.harness_registry = harness_registry or create_default_harness_registry()

    def prepare(self, state: GraphState, node: GraphNode) -> dict[str, Any]:
        config = dict(node.config)
        backend = str(config.get("backend", "runtime")).strip() or "runtime"
        payload = dict(config.get("payload") or {})
        if backend == "runtime":
            payload.setdefault("source", config.get("source", ""))
            payload.setdefault("function_name", config.get("function_name", "__tokenflow_node_entry"))
            if "args" not in payload and "kwargs" not in payload:
                payload["args"] = [state.get("result"), state.get("context"), state.get("resources")]
                payload["kwargs"] = {}
        return {"backend": backend, "payload": payload, "config": config}

    def run(self, state: GraphState, node: GraphNode, prepared: dict[str, Any]) -> Any:
        backend = prepared["backend"]
        executor = self.harness_registry.get(backend)
        execution = state.get("execution", {})
        context = ExecutionContext(
            workflow_id=str(state.get("workflow_id", "")),
            workflow_version=str(state.get("workflow_version", "")),
            execution_id=str(execution.get("execution_id", "")),
            node_id=node.node_id,
            node_type=node.node_type,
            backend=backend,
            run_context={"workflow_id": state.get("workflow_id", ""), "execution": dict(execution)},
            node_context={"config": dict(node.config)},
            agent_context={},
            shared_memory={"last_result": state.get("result"), "resources": state.get("resources")},
            scratchpad={},
            trace_spans=[],
        )
        span_id = uuid.uuid4().hex
        span = TraceSpan(
            span_id=span_id,
            parent_span_id=None,
            layer=executor.layer,
            executor_type=executor.executor_type,
            node_id=node.node_id,
            status="ok",
            detail=f"backend={backend}",
        )
        request = ExecutionRequest(payload=prepared["payload"], config=prepared["config"], context=context)
        result = executor.execute(request)
        context.trace_spans.append(span)
        result_spans = tuple(list(result.trace_spans) + [span])
        return {"output": result.output, "spans": result_spans, "metadata": dict(result.metadata), "backend": backend}

    def postprocess(self, state: GraphState, node: GraphNode, output: Any) -> GraphState:
        if not isinstance(output, dict) or "output" not in output:
            return super().postprocess(state, node, output)

        next_state = ensure_graph_state(state)
        context = next_state["context"]
        outputs = context.get("node_outputs")
        if not isinstance(outputs, dict):
            outputs = {}
            context["node_outputs"] = outputs
        outputs[node.node_id] = output["output"]
        context.setdefault("backend_results", {})[node.node_id] = {
            "backend": output.get("backend"),
            "metadata": dict(output.get("metadata") or {}),
        }
        next_state["result"] = output["output"]
        for item in output.get("spans", ()):
            append_span(next_state, **asdict(item))
        return next_state
