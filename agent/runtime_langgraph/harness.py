from __future__ import annotations

from abc import ABC, abstractmethod
import copy
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TraceSpan:
    span_id: str
    parent_span_id: str | None
    layer: str
    executor_type: str
    node_id: str
    status: str = "pending"
    detail: str | None = None


@dataclass
class ExecutionContext:
    workflow_id: str
    workflow_version: str
    execution_id: str
    node_id: str
    node_type: str
    backend: str
    run_context: dict[str, Any] = field(default_factory=dict)
    node_context: dict[str, Any] = field(default_factory=dict)
    agent_context: dict[str, Any] = field(default_factory=dict)
    shared_memory: dict[str, Any] = field(default_factory=dict)
    scratchpad: dict[str, Any] = field(default_factory=dict)
    trace_spans: list[TraceSpan] = field(default_factory=list)

    def child(self, *, backend: str, layer: str, parent_span_id: str | None) -> "ExecutionContext":
        next_context = ExecutionContext(
            workflow_id=self.workflow_id,
            workflow_version=self.workflow_version,
            execution_id=self.execution_id,
            node_id=self.node_id,
            node_type=self.node_type,
            backend=backend,
            run_context=copy.deepcopy(self.run_context),
            node_context=copy.deepcopy(self.node_context),
            agent_context=copy.deepcopy(self.agent_context),
            shared_memory=copy.deepcopy(self.shared_memory),
            scratchpad=copy.deepcopy(self.scratchpad),
            trace_spans=list(self.trace_spans),
        )
        next_context.scratchpad["layer"] = layer
        next_context.scratchpad["parent_span_id"] = parent_span_id
        return next_context


@dataclass(frozen=True)
class ExecutionRequest:
    payload: dict[str, Any]
    config: dict[str, Any]
    context: ExecutionContext


@dataclass(frozen=True)
class ExecutionResult:
    output: Any
    trace_spans: tuple[TraceSpan, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseHarnessExecutor(ABC):
    executor_type = "base"
    layer = "executor"

    @abstractmethod
    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        raise NotImplementedError


class ToolExecutor(BaseHarnessExecutor):
    executor_type = "tool"
    layer = "tool"


class SkillExecutor(BaseHarnessExecutor):
    executor_type = "skill"
    layer = "skill"


class AgentExecutor(BaseHarnessExecutor):
    executor_type = "agent"
    layer = "agent"


class FunctionCallExecutor(BaseHarnessExecutor):
    executor_type = "function_call"
    layer = "function_call"


class RuntimeBackendExecutor(BaseHarnessExecutor):
    executor_type = "runtime"
    layer = "runtime"


class HarnessRegistry:
    def __init__(self) -> None:
        self._executors: dict[str, BaseHarnessExecutor] = {}

    def register(self, backend: str, executor: BaseHarnessExecutor) -> None:
        normalized = str(backend).strip()
        if not normalized:
            raise ValueError("backend cannot be empty")
        self._executors[normalized] = executor

    def get(self, backend: str) -> BaseHarnessExecutor:
        normalized = str(backend).strip()
        executor = self._executors.get(normalized)
        if executor is None:
            raise KeyError(f"backend not registered: {backend}")
        return executor

    def has(self, backend: str) -> bool:
        return str(backend).strip() in self._executors

    @property
    def backends(self) -> tuple[str, ...]:
        return tuple(sorted(self._executors.keys()))
