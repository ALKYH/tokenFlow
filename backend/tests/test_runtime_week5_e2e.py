import asyncio

import backend.app.services.runtime_service as runtime_service
from backend.app.schemas.model_runtime import NodeExecutionRequest, RuntimeExecutionOptions, RuntimeModuleSpec
from backend.app.services.runtime_service import execute_node


def _build_request(
    source: str,
    *,
    inputs: list | None = None,
    resources: list[dict] | None = None,
    kwargs: dict | None = None,
    timeout_ms: int = 3000,
) -> NodeExecutionRequest:
    return NodeExecutionRequest(
        protocol_version="1.0.0",
        request_id="req_week5_e2e",
        node_id="node_week5",
        node_type="python_snippet",
        execution_mode="python-module",
        module=RuntimeModuleSpec(
            source=source.strip(),
            function_name="__tokenflow_node_entry",
            args=[],
            kwargs=kwargs or {},
        ),
        inputs=inputs or [],
        resources=resources or [],
        runtime=RuntimeExecutionOptions(timeout_ms=timeout_ms),
    )


def test_chain_const_python_print():
    payload = _build_request(
        """
def __tokenflow_node_entry(inputs, context, resources):
    value = inputs[0] if inputs else ""
    print(f"pipeline={value}")
    return str(value).upper()
""",
        inputs=["week5"],
    )
    response = asyncio.run(execute_node(payload))
    assert response.status == "ok"
    assert response.output == "WEEK5"
    assert any("pipeline=week5" in line for line in response.logs)


def test_chain_resource_injection():
    payload = _build_request(
        """
def __tokenflow_node_entry(inputs, context, resources):
    first = resources[0]["text"] if resources else ""
    return {"chars": len(first), "inputs": len(inputs or [])}
""",
        resources=[
            {
                "name": "doc.txt",
                "kind": "text",
                "text": "TokenFlow runtime resource sample",
            }
        ],
    )
    response = asyncio.run(execute_node(payload))
    assert response.status == "ok"
    assert isinstance(response.output, dict)
    assert response.output["chars"] == len("TokenFlow runtime resource sample")


def test_chain_model_inference_with_stub(monkeypatch):
    captured: dict[str, str] = {}

    def _fake_run_local_model(prompt: str, model_name: str | None = None, **kwargs):
        captured["prompt"] = prompt
        captured["model_name"] = model_name or ""
        return "mocked-model-answer"

    monkeypatch.setattr(runtime_service, "_run_local_model", _fake_run_local_model)

    payload = _build_request(
        """
def __tokenflow_node_entry(inputs, context, resources, model="stub-model.gguf"):
    prompt = inputs[0] if inputs else "hello"
    text = run_local_model(prompt, model=model, max_tokens=32)
    return {"text": text, "model": model}
""",
        inputs=["say hello"],
        kwargs={"model": "stub-model.gguf"},
    )
    response = asyncio.run(execute_node(payload))
    assert response.status == "ok"
    assert response.output == {"text": "mocked-model-answer", "model": "stub-model.gguf"}
    assert captured["prompt"] == "say hello"
    assert captured["model_name"] == "stub-model.gguf"


def test_chain_structured_error_return():
    payload = _build_request(
        """
def __tokenflow_node_entry(inputs, context, resources):
    raise ValueError("week5 boom")
"""
    )
    response = asyncio.run(execute_node(payload))
    assert response.status == "failed"
    assert response.error is not None
    assert response.error.code == "RUNTIME_EXCEPTION"
    assert "week5 boom" in response.error.message
    assert any(item.phase == "run" and item.status == "error" for item in response.trace)
