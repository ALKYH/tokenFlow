# Week 8 Router + RAG Dynamic Routing Report

Date: 2026-05-09

## Scope
- Upgrade routing from keyword-only matching to hybrid retrieval + rule fallback.
- Decouple RAG candidate recall from router scoring and selection.
- Add TopK candidates and explainability output to routing responses.

## Implemented Items
1. Hybrid routing candidate pipeline in `backend/app/services/routing_service.py`:
- Rule lexical matching remains available as deterministic fallback.
- Added synthetic RAG-style candidate recall stage.
- Added blended candidate scoring with lexical and vector score fields.
- Added TopK candidate output.

2. Router / RAG responsibility split:
- RAG recall now produces candidate context and recall scores.
- Router scoring and final path selection now happen in separate functions:
  - `retrieve_rag_candidates(...)`
  - `score_rule_candidates(...)`

3. Explainability schema:
- Added `RoutingCandidateRead`
- Added `RoutingExplainability`
- Added `top_candidates` and `explainability` to `RoutingClassifyResponse`

## Validation
- Service tests:
  - `backend/tests/test_routing_service.py`
  - `backend/tests/test_routing_queue_service.py`
- Command:

```bash
python -m pytest backend/tests/test_routing_service.py backend/tests/test_routing_queue_service.py -q -p no:cacheprovider
```

- Result:
  - `8 passed`

## Risks / Residual Gaps
1. Current RAG recall is a lightweight synthetic recall layer over rule context, not a full persistent vector-backed route index.
2. Route target types are still represented through existing `target` payloads; dedicated `workflow / agent / toolchain` enums can be tightened later.
3. Explainability is stable enough for API use, but ranking thresholds and blending weights may still need tuning with real traffic.

## References
- `backend/app/services/routing_service.py`
- `backend/app/schemas/routing.py`
- `backend/tests/test_routing_service.py`
- `backend/tests/test_routing_queue_service.py`
