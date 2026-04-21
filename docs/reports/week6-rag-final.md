# Week 6 RAG Final Report

Date: 2026-04-21

## Scope (M4.11 + M4.12)
- PostgreSQL + pgvector schema finalized and wired into backend startup.
- End-to-end RAG flow implemented: ingestion, chunking, embedding, retrieval, optional rerank, cache, context injection.
- Retrieval observability implemented: hit rate, average retrieval latency, cache hit rate, failure rate.
- Week6 migration/init/evaluation scripts added.

## Delivered Code
- DB schema bootstrap:
  - `backend/app/db/session.py` (`ensure_rag_schema`)
  - `docker-compose.yml` switched Postgres image to `pgvector/pgvector:pg16`
- RAG schema/service/router:
  - `backend/app/schemas/rag.py`
  - `backend/app/services/rag_service.py`
  - `backend/app/routers/rag.py`
  - `backend/app/main.py` includes `/api/rag` router and startup bootstrap
- Runtime integration:
  - `backend/app/services/runtime_service.py` exposes `rag_search(...)` and `rag_ingest_text(...)` inside runtime Python nodes
- Validation artifacts:
  - `backend/tests/test_rag_service.py`
  - `scripts/week6_rag_migrate.py`
  - `scripts/week6_rag_init.py`
  - `scripts/week6_rag_eval.py`

## Schema Summary
- `rag_documents`: raw source text and metadata.
- `rag_chunks`: chunk text, token count, `VECTOR(dim)` embedding, per-chunk metadata.
- `rag_query_cache`: query-result cache with TTL and hit counter.
- `rag_query_logs`: retrieval telemetry for acceptance metrics.
- Key indexes:
  - workspace/time indexes for documents, cache, logs
  - GIN index on chunk metadata
  - ivfflat vector index (`vector_cosine_ops`) on embeddings

## API Summary
- `POST /api/rag/documents/ingest`
  - Input: workspace, content, metadata, optional chunk params.
  - Output: document id, chunk count, vector dimension, ingest duration.
- `POST /api/rag/retrieve`
  - Input: query, top-k, rerank flag, context length.
  - Output: chunk hits with scores, injected context block, cache hit flag, duration and estimated cost.
- `GET /api/rag/metrics`
  - Output: `hit_rate`, `avg_retrieval_ms`, `cache_hit_rate`, `failure_rate`.

## Week6 Runbook
1. Start services:
```bash
docker compose up -d postgres backend --build
```
2. Run migration:
```bash
python scripts/week6_rag_migrate.py
```
3. Optional initialization:
```bash
python scripts/week6_rag_init.py
```
4. Run evaluation:
```bash
python scripts/week6_rag_eval.py
```
5. Check report:
```bash
output/week6/rag-eval-report.json
```

## Acceptance Mapping
- M4.11
  - PostgreSQL + pgvector: done.
  - Table/index design: done.
  - Migration/init scripts: done.
  - Retrieval evaluation script: done.
- M4.12
  - Retrieval + context injection: done.
  - Ingest/chunk/embed/retrieve/rerank: done.
  - Cache strategy: query cache with TTL + hit count.
  - Observability: query log metrics endpoints and summary query.

## Known Residual Risks
- Embedding is currently deterministic hash embedding for local/offline stability; upgrading to model-based embeddings is recommended for production relevance quality.
- ivfflat list count is fixed (`lists=100`) and should be tuned by corpus scale.
- Query cache invalidation is TTL-based; document-level invalidation hooks can be added for stricter freshness guarantees.

