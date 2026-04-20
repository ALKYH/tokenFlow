from __future__ import annotations

from typing import Type

from .executors import BaseNodeExecutor, ConstNodeExecutor, PrintNodeExecutor, PythonSnippetNodeExecutor


class NodeRegistry:
    def __init__(self) -> None:
        self._executors: dict[str, Type[BaseNodeExecutor]] = {}

    def register(self, node_type: str, executor_cls: Type[BaseNodeExecutor]) -> None:
        normalized = str(node_type).strip()
        if not normalized:
            raise ValueError("node_type 不能为空")
        self._executors[normalized] = executor_cls

    def create(self, node_type: str) -> BaseNodeExecutor:
        normalized = str(node_type).strip()
        executor_cls = self._executors.get(normalized)
        if executor_cls is None:
            raise KeyError(f"未注册的 node_type: {node_type}")
        return executor_cls()

    def has(self, node_type: str) -> bool:
        return str(node_type).strip() in self._executors

    @property
    def node_types(self) -> tuple[str, ...]:
        return tuple(sorted(self._executors.keys()))


def create_default_registry() -> NodeRegistry:
    registry = NodeRegistry()
    registry.register("const", ConstNodeExecutor)
    registry.register("python_snippet", PythonSnippetNodeExecutor)
    registry.register("print", PrintNodeExecutor)
    return registry

