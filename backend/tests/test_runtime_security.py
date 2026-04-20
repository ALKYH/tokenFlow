import asyncio

import pytest

from backend.app.schemas.model_runtime import NodeExecutionRequest, RuntimeExecutionOptions, RuntimeModuleSpec
import backend.app.services.runtime_service as runtime_service
from backend.app.services.runtime_service import RuntimeExecutionError, execute_node


def _build_request(source: str, timeout_ms: int = 1000) -> NodeExecutionRequest:
    return NodeExecutionRequest(
        protocol_version='1.0.0',
        request_id='req_test_security',
        node_id='node_security',
        node_type='python_snippet',
        execution_mode='python-module',
        module=RuntimeModuleSpec(source=source.strip(), function_name='__tokenflow_node_entry'),
        runtime=RuntimeExecutionOptions(timeout_ms=timeout_ms)
    )


def test_malicious_import_is_blocked():
    payload = _build_request(
        """
def __tokenflow_node_entry(value, context, resources):
    import os
    return os.getcwd()
"""
    )
    response = asyncio.run(execute_node(payload))
    assert response.status == 'failed'
    assert response.error is not None
    assert response.error.code == 'UNSAFE_CODE'


def test_timeout_dead_loop_returns_timeout():
    payload = _build_request(
        """
def __tokenflow_node_entry(value, context, resources):
    while True:
        runtime_checkpoint()
""",
        timeout_ms=50
    )
    response = asyncio.run(execute_node(payload))
    assert response.status == 'failed'
    assert response.error is not None
    assert response.error.code == 'TIMEOUT'


def test_model_path_traversal_is_rejected():
    with pytest.raises(RuntimeExecutionError) as error:
        runtime_service._validate_model_name('../escape.gguf')
    assert error.value.code == 'MODEL_NOT_ALLOWED'


def test_runtime_logs_are_redacted():
    payload = _build_request(
        r"""
def __tokenflow_node_entry(value, context, resources):
    print("api_key=abc123")
    print("email=test@example.com")
    print(r"C:\Users\someone\secret.txt")
    return "ok"
"""
    )
    response = asyncio.run(execute_node(payload))
    assert response.status == 'ok'
    joined = '\n'.join(response.logs)
    assert '[REDACTED]' in joined
    assert '[EMAIL_REDACTED]' in joined or 'email=[REDACTED]' in joined
    assert '[PATH_REDACTED]' in joined
