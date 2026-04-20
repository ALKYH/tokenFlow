# Week 3 Security Baseline Report

Date: 2026-04-20

## Scope
- Runtime model access policy (`models/` whitelist and path safety).
- Runtime isolation controls (timeout, queue length, memory limit, dangerous import/call restrictions).
- Runtime data protection controls (log and error redaction).
- Security regression tests for import abuse, timeout loop, and path traversal.

## Implemented Controls
1. Model whitelist policy:
- `TOKENFLOW_RUNTIME_ALLOWED_MODELS` controls explicit allowed model names.
- If not configured, only discovered local `*.gguf` files are accepted.

2. Model path safety:
- Rejects names containing `/`, `\`, `..`, invalid characters, or non-`.gguf` suffix.
- Resolves candidate path under `TOKENFLOW_MODELS_DIR` and rejects symlink model files.
- Rejects any path escaping `models/` root after path resolution.

3. Runtime execution isolation:
- Hard timeout via `asyncio.wait_for`.
- Graceful cancellation signal via runtime cancellation token (`runtime_checkpoint`, `runtime_cancelled`).
- Concurrency limit via semaphore.
- Queue length limit via `TOKENFLOW_RUNTIME_MAX_QUEUE_LENGTH`.
- Memory peak limit via `TOKENFLOW_RUNTIME_MAX_MEMORY_MB` (tracked by `tracemalloc`).

4. Dangerous code restrictions:
- Non-whitelist imports blocked in AST validation.
- Forbidden calls blocked (`eval`, `exec`, `compile`, `open`, `input`, `__import__`).
- Forbidden dunder/introspection attributes blocked in AST validation.
- Runtime scope exposes minimal builtins only.

5. Sensitive data redaction:
- Redacts secret-like tokens (`api_key/token/secret/password` patterns).
- Redacts user-identifying patterns (`user/email` key-values, email addresses).
- Redacts filesystem paths in logs/errors/traceback.

6. Audit logging:
- JSON-line audit file at `TOKENFLOW_RUNTIME_AUDIT_LOG_PATH`.
- Records timestamp, requestor, node id, model, status, error code, and duration.

## Security Test Results
Test file: `backend/tests/test_runtime_security.py`

Covered cases:
1. Malicious import (`import os`) is rejected with `UNSAFE_CODE`.
2. Loop execution with timeout returns `TIMEOUT`.
3. Model path traversal (`../escape.gguf`) is rejected with `MODEL_NOT_ALLOWED`.
4. Runtime logs redact secrets/email/paths as expected.

## Residual Risks
1. Hard timeout currently returns API timeout immediately, but non-cooperative user code may still consume worker thread briefly.
2. Memory enforcement is peak-measurement based; it does not preemptively terminate allocation-heavy code before peak check.
3. Further sandboxing (process isolation, seccomp/job objects, per-process kill) should be considered for production hardening.
