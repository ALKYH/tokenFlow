from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import desc, select

from agent.runtime_langgraph.compiler import compile_workflow_dsl
from agent.runtime_langgraph.dsl import normalize_frontend_workflow_payload
from agent.runtime_langgraph.engine import LangGraphRuntime

from ..db.session import AsyncSessionLocal
from ..models.runtime_execution import (
    AgentRunRecord,
    NodeRunRecord,
    RetryRecord,
    RuntimeCheckpointRecord,
    WorkflowRunRecord,
)
from ..schemas.observability import WorkflowTimelineRead
from .runtime_checkpoint_store import DatabaseRuntimeCheckpointStore


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _summarize_value(value: Any, *, max_chars: int = 240) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False)
    except Exception:
        text = str(value)
    return text[:max_chars]


class RuntimeExecutionRegistry:
    def __init__(self) -> None:
        self._plans: dict[str, tuple[LangGraphRuntime, Any]] = {}
        self._states: dict[str, dict[str, Any]] = {}

    def register(self, execution_id: str, runtime: LangGraphRuntime, plan, state: dict[str, Any]) -> None:
        self._plans[execution_id] = (runtime, plan)
        self._states[execution_id] = state

    def get(self, execution_id: str):
        return self._plans.get(execution_id), self._states.get(execution_id)

    def update_state(self, execution_id: str, state: dict[str, Any]) -> None:
        if execution_id in self._states:
            self._states[execution_id] = state


runtime_execution_registry = RuntimeExecutionRegistry()
_workflow_runs_cache: dict[str, dict[str, Any]] = {}
_timeline_cache: dict[str, WorkflowTimelineRead] = {}


def _build_timeline_from_state(state: dict[str, Any]) -> WorkflowTimelineRead:
    execution = state.get("execution", {})
    execution_id = str(execution.get("execution_id") or "")
    workflow_id = str(state.get("workflow_id") or "")
    now = _utc_now()
    input_summary = _summarize_value(state.get("input", {}))
    output_summary = _summarize_value(state.get("result"))
    trace = list(state.get("trace") or [])
    node_statuses = dict(execution.get("node_statuses") or {})
    return WorkflowTimelineRead(
        execution_id=execution_id,
        workflow_id=workflow_id,
        status=str(execution.get("status") or "running"),
        node_runs=[
            {
                "node_id": node_id,
                "node_type": "",
                "status": str(status),
                "input_summary": input_summary,
                "output_summary": output_summary,
                "trace_json": {
                    "trace": [item for item in trace if item.get("node_id") == node_id],
                    "spans": [item for item in state.get("spans", []) if item.get("node_id") == node_id],
                },
                "started_at": now,
                "updated_at": now,
                "completed_at": now if str(status) in {"success", "failed", "skipped", "cancelled", "timeout"} else None,
            }
            for node_id, status in node_statuses.items()
        ],
        agent_runs=[
            {
                "node_id": str(span.get("node_id") or ""),
                "agent_name": str(span.get("node_id") or ""),
                "status": str(span.get("status") or "running"),
                "input_summary": input_summary,
                "output_summary": output_summary,
                "trace_json": dict(span),
                "started_at": now,
                "updated_at": now,
                "completed_at": now,
            }
            for span in state.get("spans", [])
            if str(span.get("executor_type") or "") == "agent"
        ],
        retries=[
            {
                "node_id": node_id,
                "attempt": int(attempt),
                "reason": "runtime retry",
                "created_at": now,
            }
            for node_id, attempt in dict(execution.get("retry_counts") or {}).items()
        ],
        checkpoints=[
            {
                "node_id": item.get("node_id"),
                "sequence": item.get("sequence"),
                "created_at": now,
            }
            for item in execution.get("checkpoints", [])
        ],
    )


async def persist_runtime_state(state: dict[str, Any]) -> None:
    execution = state.get("execution", {})
    execution_id = str(execution.get("execution_id") or "")
    workflow_id = str(state.get("workflow_id") or "")
    workflow_version = str(state.get("workflow_version") or "")
    if not execution_id or not workflow_id:
        return

    now = _utc_now()
    input_summary = _summarize_value(state.get("input", {}))
    output_summary = _summarize_value(state.get("result"))
    trace = list(state.get("trace") or [])
    node_statuses = dict(execution.get("node_statuses") or {})
    timeline = _build_timeline_from_state(state)

    _workflow_runs_cache[execution_id] = {
        "execution_id": execution_id,
        "workflow_id": workflow_id,
        "workflow_version": workflow_version,
        "status": str(execution.get("status", "running")),
        "input_summary": input_summary,
        "output_summary": output_summary,
        "started_at": now,
        "updated_at": now,
        "completed_at": now if str(execution.get("status", "running")) in {"success", "failed", "cancelled", "timeout"} else None,
    }
    _timeline_cache[execution_id] = timeline

    try:
        async with AsyncSessionLocal() as session:
            workflow_run = await session.scalar(
                select(WorkflowRunRecord).where(WorkflowRunRecord.execution_id == execution_id)
            )
            if workflow_run is None:
                workflow_run = WorkflowRunRecord(
                    execution_id=execution_id,
                    workflow_id=workflow_id,
                    workflow_version=workflow_version,
                )
            workflow_run.status = str(execution.get("status", "running"))
            workflow_run.input_summary = input_summary
            workflow_run.output_summary = output_summary
            workflow_run.trace_summary_json = {"trace": trace, "spans": state.get("spans", [])}
            workflow_run.state_json = state
            if workflow_run.status in {"success", "failed", "cancelled", "timeout"}:
                workflow_run.completed_at = now
            session.add(workflow_run)

            for node_run in timeline.node_runs:
                existing_node = await session.scalar(
                    select(NodeRunRecord).where(
                        NodeRunRecord.execution_id == execution_id,
                        NodeRunRecord.node_id == node_run.node_id,
                    )
                )
                if existing_node is None:
                    existing_node = NodeRunRecord(
                        execution_id=execution_id,
                        workflow_id=workflow_id,
                        node_id=node_run.node_id,
                        node_type=node_run.node_type,
                    )
                existing_node.status = node_run.status
                existing_node.input_summary = node_run.input_summary
                existing_node.output_summary = node_run.output_summary
                existing_node.trace_json = node_run.trace_json
                existing_node.completed_at = node_run.completed_at
                session.add(existing_node)

            for agent_run in timeline.agent_runs:
                existing_agent = await session.scalar(
                    select(AgentRunRecord).where(
                        AgentRunRecord.execution_id == execution_id,
                        AgentRunRecord.node_id == agent_run.node_id,
                    )
                )
                if existing_agent is None:
                    existing_agent = AgentRunRecord(
                        execution_id=execution_id,
                        workflow_id=workflow_id,
                        node_id=agent_run.node_id,
                        agent_name=agent_run.agent_name,
                    )
                existing_agent.status = agent_run.status
                existing_agent.input_summary = agent_run.input_summary
                existing_agent.output_summary = agent_run.output_summary
                existing_agent.trace_json = agent_run.trace_json
                existing_agent.completed_at = agent_run.completed_at
                session.add(existing_agent)

            for retry in timeline.retries:
                existing_retry = await session.scalar(
                    select(RetryRecord).where(
                        RetryRecord.execution_id == execution_id,
                        RetryRecord.node_id == retry.node_id,
                        RetryRecord.attempt == retry.attempt,
                    )
                )
                if existing_retry is None:
                    session.add(
                        RetryRecord(
                            execution_id=execution_id,
                            workflow_id=workflow_id,
                            node_id=retry.node_id,
                            attempt=retry.attempt,
                            reason=retry.reason,
                        )
                    )

            await session.commit()
    except Exception:
        return


async def get_workflow_runs(limit: int = 50) -> list[Any]:
    try:
        async with AsyncSessionLocal() as session:
            rows = (
                await session.execute(
                    select(WorkflowRunRecord)
                    .order_by(desc(WorkflowRunRecord.updated_at), desc(WorkflowRunRecord.id))
                    .limit(max(1, min(limit, 200)))
                )
            ).scalars().all()
            return list(rows)
    except Exception:
        return []


async def get_workflow_timeline(execution_id: str) -> WorkflowTimelineRead | None:
    try:
        async with AsyncSessionLocal() as session:
            workflow_run = await session.scalar(
                select(WorkflowRunRecord).where(WorkflowRunRecord.execution_id == execution_id)
            )
            if workflow_run is None:
                return _timeline_cache.get(execution_id)

            node_runs = (
                await session.execute(
                    select(NodeRunRecord)
                    .where(NodeRunRecord.execution_id == execution_id)
                    .order_by(NodeRunRecord.id.asc())
                )
            ).scalars().all()
            agent_runs = (
                await session.execute(
                    select(AgentRunRecord)
                    .where(AgentRunRecord.execution_id == execution_id)
                    .order_by(AgentRunRecord.id.asc())
                )
            ).scalars().all()
            retries = (
                await session.execute(
                    select(RetryRecord)
                    .where(RetryRecord.execution_id == execution_id)
                    .order_by(RetryRecord.id.asc())
                )
            ).scalars().all()
            checkpoints = (
                await session.execute(
                    select(RuntimeCheckpointRecord)
                    .where(RuntimeCheckpointRecord.execution_id == execution_id)
                    .order_by(RuntimeCheckpointRecord.sequence.asc(), RuntimeCheckpointRecord.id.asc())
                )
            ).scalars().all()

        return WorkflowTimelineRead(
            execution_id=workflow_run.execution_id,
            workflow_id=workflow_run.workflow_id,
            status=workflow_run.status,
            node_runs=[
                {
                    "node_id": row.node_id,
                    "node_type": row.node_type,
                    "status": row.status,
                    "input_summary": row.input_summary,
                    "output_summary": row.output_summary,
                    "trace_json": row.trace_json or {},
                    "started_at": row.started_at,
                    "updated_at": row.updated_at,
                    "completed_at": row.completed_at,
                }
                for row in node_runs
            ],
            agent_runs=[
                {
                    "node_id": row.node_id,
                    "agent_name": row.agent_name,
                    "status": row.status,
                    "input_summary": row.input_summary,
                    "output_summary": row.output_summary,
                    "trace_json": row.trace_json or {},
                    "started_at": row.started_at,
                    "updated_at": row.updated_at,
                    "completed_at": row.completed_at,
                }
                for row in agent_runs
            ],
            retries=[
                {
                    "node_id": row.node_id,
                    "attempt": row.attempt,
                    "reason": row.reason,
                    "created_at": row.created_at,
                }
                for row in retries
            ],
            checkpoints=[
                {
                    "node_id": row.node_id,
                    "sequence": row.sequence,
                    "created_at": row.created_at,
                }
                for row in checkpoints
            ],
        )
    except Exception:
        return _timeline_cache.get(execution_id)


def register_runtime_execution(execution_id: str, runtime: LangGraphRuntime, plan, state: dict[str, Any]) -> None:
    runtime_execution_registry.register(execution_id, runtime, plan, state)


async def retry_workflow_node(execution_id: str, node_id: str) -> dict[str, Any]:
    runtime_bundle, state = runtime_execution_registry.get(execution_id)
    if runtime_bundle is None or state is None:
        raise ValueError(f"execution not registered: {execution_id}")
    runtime, plan = runtime_bundle
    next_state = runtime.retry_execution_node(plan, node_id=node_id, initial_state=state, execution_id=execution_id)
    runtime_execution_registry.update_state(execution_id, next_state)
    await persist_runtime_state(next_state)
    return next_state


async def resume_workflow_execution(execution_id: str) -> dict[str, Any]:
    runtime_bundle, _state = runtime_execution_registry.get(execution_id)
    if runtime_bundle is None:
        raise ValueError(f"execution not registered: {execution_id}")
    runtime, plan = runtime_bundle
    next_state = runtime.resume_execution(plan, execution_id=execution_id)
    runtime_execution_registry.update_state(execution_id, next_state)
    await persist_runtime_state(next_state)
    return next_state


async def cancel_workflow_execution(execution_id: str) -> dict[str, Any]:
    runtime_bundle, state = runtime_execution_registry.get(execution_id)
    if runtime_bundle is None or state is None:
        raise ValueError(f"execution not registered: {execution_id}")
    runtime, _plan = runtime_bundle
    next_state = runtime.cancel_execution(state)
    runtime_execution_registry.update_state(execution_id, next_state)
    await persist_runtime_state(next_state)
    return next_state


def build_runtime_from_plan_json(plan_json: dict[str, Any]) -> tuple[LangGraphRuntime, Any]:
    workflow = normalize_frontend_workflow_payload(plan_json)
    plan = compile_workflow_dsl(workflow)
    runtime = LangGraphRuntime(checkpoint_store=DatabaseRuntimeCheckpointStore())
    return runtime, plan
