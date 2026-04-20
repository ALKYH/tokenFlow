from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

PROTOCOL_VERSION = '1.0.0'
SUPPORTED_PROTOCOL_MAJOR = 1


class RuntimeResource(BaseModel):
    """Transport-friendly resource payload for model runtime nodes."""

    model_config = ConfigDict(extra='forbid')

    name: str = Field(min_length=1, max_length=255)
    kind: Literal['text', 'base64_data']
    text: str | None = None
    base64_data: str | None = None
    mime_type: str = Field(default='text/plain', max_length=120)
    encoding: str = Field(default='utf-8', max_length=32)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode='after')
    def validate_payload(self):
        if self.kind == 'text' and self.text is None:
            raise ValueError('text is required when kind=text')
        if self.kind == 'base64_data' and self.base64_data is None:
            raise ValueError('base64_data is required when kind=base64_data')
        return self


class RuntimeModuleSpec(BaseModel):
    model_config = ConfigDict(extra='forbid')

    source: str = Field(min_length=1, max_length=200000)
    function_name: str = Field(min_length=1, max_length=120)
    args: list[Any] = Field(default_factory=list)
    kwargs: dict[str, Any] = Field(default_factory=dict)


class RuntimeExecutionOptions(BaseModel):
    model_config = ConfigDict(extra='forbid')

    timeout_ms: int | None = Field(default=None, ge=1, le=120000)
    max_output_bytes: int | None = Field(default=None, ge=1024, le=5242880)


class NodeExecutionRequest(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        json_schema_extra={
            'examples': [
                {
                    'protocol_version': '1.0.0',
                    'request_id': 'req_week2_001',
                    'node_id': 'python_snippet_1',
                    'node_type': 'python_snippet',
                    'execution_mode': 'python-module',
                    'module': {
                        'source': (
                            'def __tokenflow_node_entry(value, context, resources):\n'
                            '    print("runtime log:", value)\n'
                            '    return {"upper": str(value).upper()}'
                        ),
                        'function_name': '__tokenflow_node_entry',
                        'args': ['week2'],
                        'kwargs': {}
                    },
                    'inputs': ['week2'],
                    'resources': [],
                    'env': {'WORKSPACE_ID': 'ws_local_001'},
                    'runtime': {'timeout_ms': 8000}
                }
            ]
        }
    )

    protocol_version: str = Field(default=PROTOCOL_VERSION, pattern=r'^[0-9]+\.[0-9]+\.[0-9]+$')
    request_id: str | None = Field(default=None, min_length=1, max_length=120)
    node_id: str = Field(min_length=1, max_length=120)
    node_type: str = Field(min_length=1, max_length=80)
    execution_mode: Literal['python-module', 'builtin', 'auto']
    module: RuntimeModuleSpec
    inputs: list[Any] = Field(default_factory=list)
    resources: list[RuntimeResource] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    runtime: RuntimeExecutionOptions | None = None


class ExecutionError(BaseModel):
    code: str
    message: str
    detail: Any = None
    traceback: str | None = None


class RuntimeMetrics(BaseModel):
    duration_ms: float = 0
    cpu_ms: float | None = None
    memory_peak_mb: float | None = None
    timeout_seconds: float | None = None


class RuntimeTraceEntry(BaseModel):
    node_id: str
    phase: str
    status: str
    detail: str | None = None


class NodeExecutionResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            'examples': [
                {
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
            ]
        }
    )

    protocol_version: str = PROTOCOL_VERSION
    request_id: str | None = None
    status: Literal['ok', 'failed']
    output: Any = None
    logs: list[str] = Field(default_factory=list)
    error: ExecutionError | None = None
    metrics: RuntimeMetrics = Field(default_factory=RuntimeMetrics)
    trace: list[RuntimeTraceEntry] = Field(default_factory=list)


class NodeCapability(BaseModel):
    node_type: str
    execution_mode: str
    description: str
    outputs: list[str] = Field(default_factory=list)
    default_attributes: dict[str, Any] = Field(default_factory=dict)
    supports_python_module: bool = True


class RuntimeHealth(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            'examples': [
                {
                    'status': 'ok',
                    'model_backend': 'llama-cpp-python',
                    'default_model': '',
                    'models': ['qwen2.5-7b-instruct.Q4_K_M.gguf'],
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
                        'llama_cpp_available': True
                    }
                }
            ]
        }
    )

    status: Literal['ok', 'degraded']
    model_backend: str
    default_model: str
    models: list[str] = Field(default_factory=list)
    limits: dict[str, Any] = Field(default_factory=dict)
    dependencies: dict[str, Any] = Field(default_factory=dict)
