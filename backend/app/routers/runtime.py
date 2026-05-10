from fastapi import APIRouter, Depends
from fastapi import HTTPException

from ..deps import get_optional_user
from ..schemas.model_runtime import NodeCapability, NodeExecutionRequest, NodeExecutionResponse, RuntimeHealth
from ..schemas.observability import WorkflowCancelRequest, WorkflowResumeRequest
from ..schemas.routing import QueueDeadLetterRead, QueueMetricAggregateRead, QueueMetricRecordRead
from ..services.queue_metrics_service import (
    aggregate_runtime_metrics,
    list_runtime_dead_letters,
    list_runtime_metrics,
)
from ..services.runtime_observability_service import (
    build_runtime_from_plan_json,
    cancel_workflow_execution,
    get_workflow_runs,
    get_workflow_timeline,
    persist_runtime_state,
    register_runtime_execution,
    resume_workflow_execution,
    retry_workflow_node,
)
from ..services.runtime_service import execute_node, get_runtime_capabilities, get_runtime_health
from ..services.runtime_queue_service import runtime_queue_service

router = APIRouter(prefix='/api/runtime', tags=['runtime'])


@router.get(
    '/health',
    response_model=RuntimeHealth,
    summary='Runtime health',
    description='Returns runtime dependency status, model discovery result, and execution limits.',
    responses={
        200: {
            'description': 'Runtime health information',
            'content': {
                'application/json': {
                    'example': {
                        'status': 'ok',
                        'model_backend': 'llama-cpp-python',
                        'default_model': '',
                        'models': [],
                        'limits': {
                            'timeout_seconds': 20,
                            'max_concurrency': 2,
                            'max_queue_length': 16,
                            'max_memory_mb': 512,
                            'max_source_chars': 20000,
                            'max_resource_bytes': 5242880,
                            'max_output_chars': 200000
                        },
                        'dependencies': {
                            'llama_cpp_available': True,
                            'vllm_available': False
                        }
                    }
                }
            }
        }
    }
)
async def runtime_health(_user=Depends(get_optional_user)):
    health = get_runtime_health()
    queue_health = await runtime_queue_service.get_health()
    health.limits["queue"] = queue_health
    return health


@router.get(
    '/capabilities',
    response_model=list[NodeCapability],
    summary='Runtime capabilities',
    description='Returns node-level capability metadata that frontend can use for runtime mode mapping.',
    responses={
        200: {
            'description': 'Runtime capability list',
            'content': {
                'application/json': {
                    'example': [
                        {
                            'node_type': 'runtime',
                            'execution_mode': 'python-module',
                            'description': 'Execute Python function snippet sent from frontend nodes.',
                            'outputs': ['output', 'logs', 'error', 'metrics'],
                            'default_attributes': {'timeout_seconds': 20},
                            'supports_python_module': True
                        }
                    ]
                }
            }
        }
    }
)
async def runtime_capabilities(_user=Depends(get_optional_user)):
    return get_runtime_capabilities()


@router.get('/queue/dead-letters', response_model=list[QueueDeadLetterRead])
async def get_runtime_dead_letters(limit: int = 20, _user=Depends(get_optional_user)):
    rows = await list_runtime_dead_letters(limit=limit)
    return [
        QueueDeadLetterRead(
            request_id=row.request_id,
            queue_backend=row.queue_backend,
            error_code=row.error_code,
            error_message=row.error_message,
            attempts=row.attempts,
            created_at=row.created_at,
            last_attempt_at=row.last_attempt_at,
            wait_time_ms=row.wait_time_ms,
        )
        for row in rows
    ]


@router.get('/queue/metrics', response_model=list[QueueMetricRecordRead])
async def get_runtime_metrics(limit: int = 50, _user=Depends(get_optional_user)):
    rows = await list_runtime_metrics(limit=limit)
    return [
        QueueMetricRecordRead(
            request_id=row.request_id,
            queue_backend=row.queue_backend,
            status=row.status,
            duration_ms=row.duration_ms,
            wait_time_ms=row.wait_time_ms,
            attempts=row.attempts,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.get('/queue/metrics/aggregate', response_model=list[QueueMetricAggregateRead])
async def get_runtime_metrics_aggregate(limit: int = 200, _user=Depends(get_optional_user)):
    rows = await aggregate_runtime_metrics(limit=limit)
    return [QueueMetricAggregateRead(**row) for row in rows]


@router.get('/runs')
async def list_workflow_runs(limit: int = 50, _user=Depends(get_optional_user)):
    rows = await get_workflow_runs(limit=limit)
    return [
        {
            "execution_id": row.execution_id,
            "workflow_id": row.workflow_id,
            "workflow_version": row.workflow_version,
            "status": row.status,
            "input_summary": row.input_summary,
            "output_summary": row.output_summary,
            "started_at": row.started_at,
            "updated_at": row.updated_at,
            "completed_at": row.completed_at,
        }
        for row in rows
    ]


@router.get('/runs/{execution_id}/timeline')
async def get_runtime_timeline(execution_id: str, _user=Depends(get_optional_user)):
    timeline = await get_workflow_timeline(execution_id)
    if timeline is None:
        raise HTTPException(status_code=404, detail='Execution not found')
    return timeline


@router.post('/runs/{execution_id}/retry/{node_id}')
async def retry_runtime_node(execution_id: str, node_id: str, _user=Depends(get_optional_user)):
    try:
        return await retry_workflow_node(execution_id, node_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post('/runs/{execution_id}/resume')
async def resume_runtime_execution(execution_id: str, _user=Depends(get_optional_user)):
    try:
        return await resume_workflow_execution(execution_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post('/runs/{execution_id}/cancel')
async def cancel_runtime_execution(execution_id: str, _user=Depends(get_optional_user)):
    try:
        return await cancel_workflow_execution(execution_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post('/runs/register')
async def register_runtime_plan(payload: WorkflowResumeRequest, _user=Depends(get_optional_user)):
    runtime, plan = build_runtime_from_plan_json(payload.plan_json)
    state = {
        "workflow_id": payload.workflow_id,
        "workflow_version": payload.workflow_version,
        "execution": {"execution_id": payload.execution_id, "status": "pending"},
        "trace": [],
        "spans": [],
        "context": {},
        "input": {},
        "resources": {},
    }
    register_runtime_execution(payload.execution_id, runtime, plan, state)
    await persist_runtime_state(state)
    return {"registered": True, "execution_id": payload.execution_id}


@router.post(
    '/execute-node',
    response_model=NodeExecutionResponse,
    summary='Execute runtime node',
    description='Execute a single node in runtime mode with structured output/logs/error/metrics.',
    responses={
        200: {
            'description': 'Execution result (ok or failed)',
            'content': {
                'application/json': {
                    'examples': {
                        'success': {
                            'summary': 'Successful execution',
                            'value': {
                                'protocol_version': '1.0.0',
                                'request_id': 'req_week2_001',
                                'status': 'ok',
                                'output': {'upper': 'WEEK2'},
                                'logs': ['runtime log: week2'],
                                'error': None,
                                'metrics': {'duration_ms': 12.4, 'timeout_seconds': 8},
                                'trace': [
                                    {'node_id': 'python_snippet_1', 'phase': 'prepare', 'status': 'ok'},
                                    {'node_id': 'python_snippet_1', 'phase': 'run', 'status': 'ok'},
                                    {'node_id': 'python_snippet_1', 'phase': 'postprocess', 'status': 'ok'}
                                ]
                            }
                        },
                        'failure': {
                            'summary': 'Failed execution',
                            'value': {
                                'protocol_version': '1.0.0',
                                'request_id': 'req_week2_002',
                                'status': 'failed',
                                'output': None,
                                'logs': [],
                                'error': {
                                    'code': 'RUNTIME_EXCEPTION',
                                    'message': 'division by zero',
                                    'detail': None
                                },
                                'metrics': {'duration_ms': 6.7, 'timeout_seconds': 20},
                                'trace': [
                                    {'node_id': 'python_snippet_2', 'phase': 'prepare', 'status': 'ok'},
                                    {'node_id': 'python_snippet_2', 'phase': 'run', 'status': 'error', 'detail': 'ZeroDivisionError'}
                                ]
                            }
                        }
                    }
                }
            }
        }
    }
)
async def runtime_execute_node(payload: NodeExecutionRequest, _user=Depends(get_optional_user)):
    requestor = None
    if _user:
        requestor = str(getattr(_user, 'email', None) or getattr(_user, 'id', None) or '')
    if not runtime_queue_service.config.execute_through_queue:
        return await execute_node(payload, requestor=requestor)
    queued_payload = payload.model_copy(
        update={
            'env': {
                **payload.env,
                'TOKENFLOW_RUNTIME_REQUESTOR': requestor or payload.env.get('TOKENFLOW_RUNTIME_REQUESTOR', ''),
            }
        }
    )
    return await runtime_queue_service.execute(queued_payload)
