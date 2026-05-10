from sqlalchemy import JSON, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db.session import Base


class RuntimeExecutionRecord(Base):
    __tablename__ = 'runtime_execution_records'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    execution_id: Mapped[str] = mapped_column(String(120), index=True)
    workflow_id: Mapped[str] = mapped_column(String(120), default='', index=True)
    workflow_version: Mapped[str] = mapped_column(String(32), default='')
    node_id: Mapped[str] = mapped_column(String(120), default='')
    status: Mapped[str] = mapped_column(String(32), default='running', index=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    checkpoints_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str] = mapped_column(Text, default='')
    state_json: Mapped[dict] = mapped_column(JSON, default=dict)
    started_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    completed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RuntimeCheckpointRecord(Base):
    __tablename__ = 'runtime_checkpoint_records'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    execution_id: Mapped[str] = mapped_column(String(120), index=True)
    workflow_id: Mapped[str] = mapped_column(String(120), default='', index=True)
    workflow_version: Mapped[str] = mapped_column(String(32), default='')
    node_id: Mapped[str] = mapped_column(String(120), index=True)
    sequence: Mapped[int] = mapped_column(Integer, default=1)
    state_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WorkflowRunRecord(Base):
    __tablename__ = 'workflow_runs'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    execution_id: Mapped[str] = mapped_column(String(120), index=True)
    workflow_id: Mapped[str] = mapped_column(String(120), index=True)
    workflow_version: Mapped[str] = mapped_column(String(32), default='')
    status: Mapped[str] = mapped_column(String(32), default='running', index=True)
    input_summary: Mapped[str] = mapped_column(Text, default='')
    output_summary: Mapped[str] = mapped_column(Text, default='')
    trace_summary_json: Mapped[dict] = mapped_column(JSON, default=dict)
    state_json: Mapped[dict] = mapped_column(JSON, default=dict)
    started_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    completed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)


class NodeRunRecord(Base):
    __tablename__ = 'node_runs'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    execution_id: Mapped[str] = mapped_column(String(120), index=True)
    workflow_id: Mapped[str] = mapped_column(String(120), index=True)
    node_id: Mapped[str] = mapped_column(String(120), index=True)
    node_type: Mapped[str] = mapped_column(String(80), default='')
    status: Mapped[str] = mapped_column(String(32), default='pending', index=True)
    input_summary: Mapped[str] = mapped_column(Text, default='')
    output_summary: Mapped[str] = mapped_column(Text, default='')
    trace_json: Mapped[dict] = mapped_column(JSON, default=dict)
    started_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    completed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentRunRecord(Base):
    __tablename__ = 'agent_runs'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    execution_id: Mapped[str] = mapped_column(String(120), index=True)
    workflow_id: Mapped[str] = mapped_column(String(120), index=True)
    node_id: Mapped[str] = mapped_column(String(120), index=True)
    agent_name: Mapped[str] = mapped_column(String(120), default='')
    status: Mapped[str] = mapped_column(String(32), default='running', index=True)
    input_summary: Mapped[str] = mapped_column(Text, default='')
    output_summary: Mapped[str] = mapped_column(Text, default='')
    trace_json: Mapped[dict] = mapped_column(JSON, default=dict)
    started_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    completed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RetryRecord(Base):
    __tablename__ = 'retry_records'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    execution_id: Mapped[str] = mapped_column(String(120), index=True)
    workflow_id: Mapped[str] = mapped_column(String(120), index=True)
    node_id: Mapped[str] = mapped_column(String(120), index=True)
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    reason: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RuntimeQueueDeadLetterRecord(Base):
    __tablename__ = 'runtime_queue_dead_letters'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(120), index=True)
    node_id: Mapped[str] = mapped_column(String(120), default='', index=True)
    queue_backend: Mapped[str] = mapped_column(String(32), default='memory')
    error_code: Mapped[str] = mapped_column(String(64), default='')
    error_message: Mapped[str] = mapped_column(Text, default='')
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_attempt_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    wait_time_ms: Mapped[float] = mapped_column(Float, default=0)


class RoutingQueueDeadLetterRecord(Base):
    __tablename__ = 'routing_queue_dead_letters'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(120), index=True)
    queue_backend: Mapped[str] = mapped_column(String(32), default='memory')
    error_code: Mapped[str] = mapped_column(String(64), default='')
    error_message: Mapped[str] = mapped_column(Text, default='')
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_attempt_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    wait_time_ms: Mapped[float] = mapped_column(Float, default=0)


class RoutingQueueMetricRecord(Base):
    __tablename__ = 'routing_queue_metrics'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(120), index=True)
    queue_backend: Mapped[str] = mapped_column(String(32), default='memory')
    status: Mapped[str] = mapped_column(String(32), default='ok')
    duration_ms: Mapped[float] = mapped_column(Float, default=0)
    wait_time_ms: Mapped[float] = mapped_column(Float, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RuntimeQueueMetricRecord(Base):
    __tablename__ = 'runtime_queue_metrics'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(120), index=True)
    queue_backend: Mapped[str] = mapped_column(String(32), default='memory')
    status: Mapped[str] = mapped_column(String(32), default='ok')
    duration_ms: Mapped[float] = mapped_column(Float, default=0)
    wait_time_ms: Mapped[float] = mapped_column(Float, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
