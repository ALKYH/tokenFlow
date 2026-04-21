from fastapi import APIRouter, Depends

from ..deps import get_optional_user
from ..schemas.model_runtime import NodeCapability, NodeExecutionRequest, NodeExecutionResponse, RuntimeHealth
from ..services.runtime_service import execute_node, get_runtime_capabilities, get_runtime_health

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
    return get_runtime_health()


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
    return await execute_node(payload, requestor=requestor)
