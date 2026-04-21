from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import backend.app.services.runtime_service as runtime_service
from backend.app.schemas.model_runtime import NodeExecutionRequest, RuntimeExecutionOptions, RuntimeModuleSpec
from backend.app.services.runtime_service import execute_node


def build_request(
    source: str,
    *,
    request_id: str,
    inputs: list[Any] | None = None,
    resources: list[dict[str, Any]] | None = None,
    kwargs: dict[str, Any] | None = None,
    timeout_ms: int = 3000,
) -> NodeExecutionRequest:
    return NodeExecutionRequest(
        protocol_version="1.0.0",
        request_id=request_id,
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


async def main() -> None:
    records: list[dict[str, Any]] = []

    case_1 = build_request(
        """
def __tokenflow_node_entry(inputs, context, resources):
    value = inputs[0] if inputs else ""
    print(f"pipeline={value}")
    return str(value).upper()
""",
        request_id="week5_case_1",
        inputs=["week5"],
    )
    resp_1 = await execute_node(case_1)
    records.append(
        {
            "case": "const->python_snippet->print",
            "expected": {"status": "ok", "output": "WEEK5"},
            "actual": resp_1.model_dump(),
            "passed": resp_1.status == "ok" and resp_1.output == "WEEK5",
        }
    )

    case_2 = build_request(
        """
def __tokenflow_node_entry(inputs, context, resources):
    first = resources[0]["text"] if resources else ""
    return {"chars": len(first)}
""",
        request_id="week5_case_2",
        resources=[
            {
                "name": "doc.txt",
                "kind": "text",
                "text": "TokenFlow runtime resource sample",
            }
        ],
    )
    resp_2 = await execute_node(case_2)
    expected_chars = len("TokenFlow runtime resource sample")
    records.append(
        {
            "case": "resource injection",
            "expected": {"status": "ok", "output.chars": expected_chars},
            "actual": resp_2.model_dump(),
            "passed": resp_2.status == "ok" and isinstance(resp_2.output, dict) and resp_2.output.get("chars") == expected_chars,
        }
    )

    original_model_runner = runtime_service._run_local_model
    captured: dict[str, Any] = {}

    def fake_model_runner(prompt: str, model_name: str | None = None, **kwargs: Any):
        captured["prompt"] = prompt
        captured["model_name"] = model_name
        return "mocked-model-answer"

    runtime_service._run_local_model = fake_model_runner
    try:
        case_3 = build_request(
            """
def __tokenflow_node_entry(inputs, context, resources, model="stub-model.gguf"):
    prompt = inputs[0] if inputs else "hello"
    text = run_local_model(prompt, model=model, max_tokens=32)
    return {"text": text, "model": model}
""",
            request_id="week5_case_3",
            inputs=["say hello"],
            kwargs={"model": "stub-model.gguf"},
        )
        resp_3 = await execute_node(case_3)
    finally:
        runtime_service._run_local_model = original_model_runner
    records.append(
        {
            "case": "model inference chain",
            "expected": {"status": "ok", "output.text": "mocked-model-answer"},
            "actual": resp_3.model_dump(),
            "captured_call": captured,
            "passed": resp_3.status == "ok" and isinstance(resp_3.output, dict) and resp_3.output.get("text") == "mocked-model-answer",
        }
    )

    case_4 = build_request(
        """
def __tokenflow_node_entry(inputs, context, resources):
    raise ValueError("week5 boom")
""",
        request_id="week5_case_4",
    )
    resp_4 = await execute_node(case_4)
    records.append(
        {
            "case": "structured error return",
            "expected": {"status": "failed", "error.code": "RUNTIME_EXCEPTION"},
            "actual": resp_4.model_dump(),
            "passed": resp_4.status == "failed" and resp_4.error is not None and resp_4.error.code == "RUNTIME_EXCEPTION",
        }
    )

    output_dir = Path("output/week5")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "runtime-e2e-results.json"
    output_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")

    passed = sum(1 for item in records if item["passed"])
    print(f"Week5 E2E: {passed}/{len(records)} passed")
    print(f"Saved: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
