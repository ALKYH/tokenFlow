from __future__ import annotations

import copy
import traceback

from .types import ErrorInfo, GraphNode, GraphState, TraceEntry


def ensure_graph_state(raw_state: GraphState | None) -> GraphState:
    source: GraphState = raw_state or {}
    state: GraphState = {
        "input": copy.deepcopy(source.get("input", {})),
        "context": copy.deepcopy(source.get("context", {})),
        "resources": copy.deepcopy(source.get("resources", {})),
        "result": copy.deepcopy(source.get("result")),
        "error": copy.deepcopy(source.get("error")),
        "trace": copy.deepcopy(source.get("trace", [])),
    }
    if not isinstance(state["input"], dict):
        state["input"] = {}
    if not isinstance(state["context"], dict):
        state["context"] = {}
    if not isinstance(state["trace"], list):
        state["trace"] = []
    return state


def append_trace(
    state: GraphState,
    node: GraphNode,
    phase: str,
    status: str,
    detail: str | None = None,
) -> None:
    entry: TraceEntry = {
        "node_id": node.node_id,
        "node_type": node.node_type,
        "phase": phase,
        "status": status,
    }
    if detail:
        entry["detail"] = detail
    state["trace"].append(entry)


def build_error_info(node: GraphNode, phase: str, exc: Exception) -> ErrorInfo:
    return {
        "node_id": node.node_id,
        "node_type": node.node_type,
        "phase": phase,
        "error_type": type(exc).__name__,
        "message": str(exc),
        "traceback": traceback.format_exc(),
    }

