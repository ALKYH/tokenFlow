import backend.app.services.runtime_service as runtime_service
from backend.app.services.runtime_service import RuntimeExecutionError


def test_run_local_model_dispatches_llama_backend(monkeypatch):
    monkeypatch.setattr(runtime_service, "TOKENFLOW_RUNTIME_MODEL_BACKEND", "llama-cpp-python")
    monkeypatch.setattr(runtime_service, "TOKENFLOW_RUNTIME_DEFAULT_MODEL", "demo.gguf")

    class DummyLlama:
        def create_chat_completion(self, **kwargs):
            return {"choices": [{"message": {"content": "llama-ok"}}]}

    monkeypatch.setattr(runtime_service, "_load_llama_model", lambda _: DummyLlama())

    text = runtime_service._run_local_model("hello")
    assert text == "llama-ok"


def test_run_local_model_dispatches_vllm_backend(monkeypatch):
    monkeypatch.setattr(runtime_service, "TOKENFLOW_RUNTIME_MODEL_BACKEND", "vllm")
    monkeypatch.setattr(runtime_service, "TOKENFLOW_RUNTIME_DEFAULT_MODEL", "demo-vllm")

    captured = {}

    def fake_run_vllm_model(prompt: str, model_name: str | None = None, **kwargs):
        captured["prompt"] = prompt
        captured["model_name"] = model_name
        return "vllm-ok"

    monkeypatch.setattr(runtime_service, "_run_vllm_model", fake_run_vllm_model)

    text = runtime_service._run_local_model("hello")
    assert text == "vllm-ok"
    assert captured["prompt"] == "hello"
    assert captured["model_name"] is None


def test_invalid_runtime_backend_rejected(monkeypatch):
    monkeypatch.setattr(runtime_service, "TOKENFLOW_RUNTIME_MODEL_BACKEND", "bad-backend")

    try:
        runtime_service._run_local_model("hello", model_name="demo")
    except RuntimeExecutionError as exc:
        assert exc.code == "INVALID_REQUEST"
        assert "Unsupported runtime backend" in exc.message
    else:
        raise AssertionError("Expected RuntimeExecutionError for unsupported backend")
