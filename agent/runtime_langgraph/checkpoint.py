from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Protocol

from .graph_types import GraphState
from .state import ensure_graph_state


@dataclass(frozen=True)
class RuntimeCheckpoint:
    execution_id: str
    workflow_id: str
    workflow_version: str
    node_id: str
    sequence: int
    state: GraphState


class CheckpointStore(Protocol):
    def save(self, checkpoint: RuntimeCheckpoint) -> None:
        ...

    def load_latest(self, execution_id: str) -> RuntimeCheckpoint | None:
        ...

    def list_for_execution(self, execution_id: str) -> list[RuntimeCheckpoint]:
        ...


@dataclass
class InMemoryCheckpointStore:
    _items: dict[str, list[RuntimeCheckpoint]] = field(default_factory=dict)

    def save(self, checkpoint: RuntimeCheckpoint) -> None:
        bucket = self._items.setdefault(checkpoint.execution_id, [])
        bucket.append(
            RuntimeCheckpoint(
                execution_id=checkpoint.execution_id,
                workflow_id=checkpoint.workflow_id,
                workflow_version=checkpoint.workflow_version,
                node_id=checkpoint.node_id,
                sequence=checkpoint.sequence,
                state=ensure_graph_state(copy.deepcopy(checkpoint.state)),
            )
        )

    def load_latest(self, execution_id: str) -> RuntimeCheckpoint | None:
        bucket = self._items.get(execution_id, [])
        if not bucket:
            return None
        latest = bucket[-1]
        return RuntimeCheckpoint(
            execution_id=latest.execution_id,
            workflow_id=latest.workflow_id,
            workflow_version=latest.workflow_version,
            node_id=latest.node_id,
            sequence=latest.sequence,
            state=ensure_graph_state(copy.deepcopy(latest.state)),
        )

    def list_for_execution(self, execution_id: str) -> list[RuntimeCheckpoint]:
        return [
            RuntimeCheckpoint(
                execution_id=item.execution_id,
                workflow_id=item.workflow_id,
                workflow_version=item.workflow_version,
                node_id=item.node_id,
                sequence=item.sequence,
                state=ensure_graph_state(copy.deepcopy(item.state)),
            )
            for item in self._items.get(execution_id, [])
        ]
