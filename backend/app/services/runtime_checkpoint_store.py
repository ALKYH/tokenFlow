from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, select

from agent.runtime_langgraph.checkpoint import RuntimeCheckpoint
from agent.runtime_langgraph.state import ensure_graph_state

from ..db.session import AsyncSessionLocal
from ..models.runtime_execution import RuntimeCheckpointRecord, RuntimeExecutionRecord


class DatabaseRuntimeCheckpointStore:
    def save_sync(self, checkpoint: RuntimeCheckpoint) -> None:
        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            raise RuntimeError("save_sync cannot be called from a running event loop")
        asyncio.run(self.save(checkpoint))

    async def save(self, checkpoint: RuntimeCheckpoint) -> None:
        state = ensure_graph_state(checkpoint.state)
        async with AsyncSessionLocal() as session:
            session.add(
                RuntimeCheckpointRecord(
                    execution_id=checkpoint.execution_id,
                    workflow_id=checkpoint.workflow_id,
                    workflow_version=checkpoint.workflow_version,
                    node_id=checkpoint.node_id,
                    sequence=checkpoint.sequence,
                    state_json=state,
                )
            )

            existing = await session.scalar(
                select(RuntimeExecutionRecord).where(RuntimeExecutionRecord.execution_id == checkpoint.execution_id)
            )
            retry_count = int(state.get("execution", {}).get("retry_counts", {}).get(checkpoint.node_id, 0))
            status = str(state.get("execution", {}).get("status", "running"))
            last_error = ""
            if state.get("error"):
                last_error = str(state["error"].get("message", ""))

            if existing is None:
                session.add(
                    RuntimeExecutionRecord(
                        execution_id=checkpoint.execution_id,
                        workflow_id=checkpoint.workflow_id,
                        workflow_version=checkpoint.workflow_version,
                        node_id=checkpoint.node_id,
                        status=status,
                        retry_count=retry_count,
                        checkpoints_count=checkpoint.sequence,
                        last_error=last_error,
                        state_json=state,
                        completed_at=datetime.now(timezone.utc) if status in {"success", "failed"} else None,
                    )
                )
            else:
                existing.workflow_id = checkpoint.workflow_id
                existing.workflow_version = checkpoint.workflow_version
                existing.node_id = checkpoint.node_id
                existing.status = status
                existing.retry_count = retry_count
                existing.checkpoints_count = checkpoint.sequence
                existing.last_error = last_error
                existing.state_json = state
                if status in {"success", "failed"}:
                    existing.completed_at = datetime.now(timezone.utc)
                session.add(existing)

            await session.commit()

    def load_latest(self, execution_id: str) -> RuntimeCheckpoint | None:
        import asyncio

        return asyncio.run(self.load_latest_async(execution_id))

    async def load_latest_async(self, execution_id: str) -> RuntimeCheckpoint | None:
        async with AsyncSessionLocal() as session:
            row = await session.scalar(
                select(RuntimeCheckpointRecord)
                .where(RuntimeCheckpointRecord.execution_id == execution_id)
                .order_by(RuntimeCheckpointRecord.sequence.desc(), RuntimeCheckpointRecord.id.desc())
            )
            if row is None:
                return None
            return RuntimeCheckpoint(
                execution_id=row.execution_id,
                workflow_id=row.workflow_id,
                workflow_version=row.workflow_version,
                node_id=row.node_id,
                sequence=row.sequence,
                state=ensure_graph_state(row.state_json or {}),
            )

    def list_for_execution(self, execution_id: str) -> list[RuntimeCheckpoint]:
        import asyncio

        return asyncio.run(self.list_for_execution_async(execution_id))

    async def list_for_execution_async(self, execution_id: str) -> list[RuntimeCheckpoint]:
        async with AsyncSessionLocal() as session:
            rows = (
                await session.execute(
                    select(RuntimeCheckpointRecord)
                    .where(RuntimeCheckpointRecord.execution_id == execution_id)
                    .order_by(RuntimeCheckpointRecord.sequence.asc(), RuntimeCheckpointRecord.id.asc())
                )
            ).scalars().all()
            return [
                RuntimeCheckpoint(
                    execution_id=row.execution_id,
                    workflow_id=row.workflow_id,
                    workflow_version=row.workflow_version,
                    node_id=row.node_id,
                    sequence=row.sequence,
                    state=ensure_graph_state(row.state_json or {}),
                )
                for row in rows
            ]

    async def clear_execution(self, execution_id: str) -> None:
        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(RuntimeCheckpointRecord).where(RuntimeCheckpointRecord.execution_id == execution_id)
            )
            await session.execute(
                delete(RuntimeExecutionRecord).where(RuntimeExecutionRecord.execution_id == execution_id)
            )
            await session.commit()
