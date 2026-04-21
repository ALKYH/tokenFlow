# Week 7 Encoding Governance Report

Date: 2026-04-21

## Scope
- Close cross-cutting item M14: Chinese text safety and encoding consistency.
- Enforce UTF-8 defaults in editor and git checkout behavior.
- Add CI gate to detect non-UTF-8 content and common mojibake patterns.

## Delivered Items
1. Repository encoding rules:
- Added `.editorconfig` for UTF-8 + LF + newline consistency.
- Added `.gitattributes` for normalized line endings and binary file handling.

2. Automated audit script:
- Added `scripts/week7_encoding_audit.py`.
- Validates UTF-8 decode for text files.
- Flags replacement characters (`U+FFFD`) and suspicious mojibake signatures.
- Writes machine-readable report to `output/week7/encoding-audit-report.json`.

3. CI integration:
- Added `.github/workflows/encoding-check.yml`.
- Runs encoding audit on `push` and `pull_request` for `main`.
- Uploads audit report artifact even on failure.

## Validation
Run locally:
```bash
python scripts/week7_encoding_audit.py --fail-on-issues
```

Expected artifact:
- `output/week7/encoding-audit-report.json`

## Residual Risks
1. Mojibake detection is heuristic-based; it may need tuning as multilingual content grows.
2. Generated build artifacts are intentionally excluded from source-encoding policy checks.
