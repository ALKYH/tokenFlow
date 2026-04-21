# Week 5 Compatibility & E2E Report

Date: 2026-04-21

## Scope
- M3.10 dual-mode compatibility (`pyodide` + `runtime`) in workspace editor.
- Runtime failure fallback UX (single action to switch to `pyodide`).
- M4.13 first-round E2E validation for 4 required runtime chains.

## Implemented Items
1. Global and node-level mode control:
- Global execution mode toggle remains in the top toolbar.
- Added node-level execution mode override in the right sidebar:
  - `Inherit Workspace`
  - `Runtime`
  - `Pyodide`
- Node override is persisted in workspace snapshots (`execution_mode_override`).

2. Output schema alignment for regression comparison:
- Normalized runtime and pyodide node results to the same frontend shape:
  - `mode`
  - `status`
  - `output`
  - `logs`
  - `error`
  - `metrics`
  - `durationMs`
  - `trace`
- Upstream node value extraction now reads unified `output`.

3. One-click fallback strategy:
- When a node is manually executed in runtime mode and fails:
  - Prompt user to switch this node to `pyodide`.
  - On confirm, auto-update node override and retry immediately.

## E2E Validation Coverage
Automated validation files:
- `backend/tests/test_runtime_week5_e2e.py`
- `scripts/week5_runtime_e2e.py`

Validated chains:
1. `const -> python snippet -> print`
2. Resource injection (`resources` transport and read)
3. Model inference path (`run_local_model`) with stubbed local model runner
4. Structured error propagation (`RUNTIME_EXCEPTION`)

Output artifact:
- `output/week5/runtime-e2e-results.json`

## Known Gaps / Residual Risks
1. Real GGUF inference validation still depends on local model availability and environment setup; current E2E uses a stub for deterministic CI-like execution.
2. Fallback prompt is intentionally limited to manual node run (not automatic graph batch execution) to avoid repeated modal interruptions.
3. Legacy nodes with raw `lastResult` remain readable, but unified result shape should be preferred for new regressions.
