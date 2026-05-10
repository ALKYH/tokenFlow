# FastAPI Backend Service

This service provides auth APIs, runtime node execution APIs, routing APIs, queue/scheduler APIs, and RAG APIs backed by PostgreSQL.

## Deployment Shape

Recommended containerized topology:
- `postgres`
- `redis`
- `backend-api`
- `runtime-worker`

Notes:
- `backend-api` serves FastAPI routes and initializes schema/seed data.
- `runtime-worker` uses the runtime-enabled image target and keeps runtime dependencies (`llama-cpp-python`, optional `vllm`) isolated from the lighter API container path.
- `redis` is used for runtime/routing queue backends in containerized mode.

## Environment Variables
- `DATABASE_URL` e.g. `postgresql+asyncpg://user:pass@localhost:5432/dbname`
- `SECRET_KEY` strong random string used to sign JWTs
- `ACCESS_TOKEN_EXPIRE_MINUTES` default `30`
- `FRONTEND_ORIGINS` comma-separated CORS origins, default `http://localhost:5173`
- `TOKENFLOW_MODELS_DIR` local model directory, default `../models`
- `TOKENFLOW_STORAGE_DIR` runtime storage path, default `./storage`
- `TOKENFLOW_REDIS_URL` Redis connection string, default `redis://localhost:6379/0`

Runtime:
- `TOKENFLOW_RUNTIME_TIMEOUT_SECONDS`
- `TOKENFLOW_RUNTIME_MAX_CONCURRENCY`
- `TOKENFLOW_RUNTIME_MODEL_BACKEND` `llama-cpp-python` (default) or `vllm`
- `TOKENFLOW_RUNTIME_DEFAULT_MODEL`
- `TOKENFLOW_RUNTIME_VLLM_TENSOR_PARALLEL_SIZE`
- `TOKENFLOW_RUNTIME_VLLM_GPU_MEMORY_UTILIZATION`
- `TOKENFLOW_RUNTIME_VLLM_TRUST_REMOTE_CODE`

Routing queue:
- `TOKENFLOW_ROUTING_QUEUE_BACKEND` `inline` (default), `memory`, or `redis`
- `TOKENFLOW_ROUTING_QUEUE_INSTANCE_ID`
- `TOKENFLOW_ROUTING_QUEUE_MAX_LENGTH`
- `TOKENFLOW_ROUTING_QUEUE_WAIT_TIMEOUT_MS`
- `TOKENFLOW_ROUTING_QUEUE_RETRY_DELAY_MS`
- `TOKENFLOW_ROUTING_PROCESSING_TIMEOUT_MS`
- `TOKENFLOW_ROUTING_RECLAIM_INTERVAL_MS`
- `TOKENFLOW_ROUTING_QUEUE_INLINE_FALLBACK`
- `TOKENFLOW_ROUTING_QUEUE_NAME`

Runtime queue:
- `TOKENFLOW_RUNTIME_QUEUE_BACKEND` `inline`, `memory`, or `redis`
- `TOKENFLOW_RUNTIME_QUEUE_INSTANCE_ID`
- `TOKENFLOW_RUNTIME_QUEUE_MAX_LENGTH`
- `TOKENFLOW_RUNTIME_QUEUE_WAIT_TIMEOUT_MS`
- `TOKENFLOW_RUNTIME_QUEUE_MAX_ATTEMPTS`
- `TOKENFLOW_RUNTIME_QUEUE_RETRY_DELAY_MS`
- `TOKENFLOW_RUNTIME_PROCESSING_TIMEOUT_MS`
- `TOKENFLOW_RUNTIME_RECLAIM_INTERVAL_MS`
- `TOKENFLOW_RUNTIME_QUEUE_INLINE_FALLBACK`
- `TOKENFLOW_RUNTIME_QUEUE_NAME`
- `TOKENFLOW_RUNTIME_LOCK_PREFIX`
- `TOKENFLOW_RUNTIME_LOCK_TTL_SECONDS`

RAG:
- `TOKENFLOW_RAG_VECTOR_DIM` pgvector dimension, default `256`
- `TOKENFLOW_RAG_CHUNK_SIZE` chunk size for ingestion, default `700`
- `TOKENFLOW_RAG_CHUNK_OVERLAP` chunk overlap chars, default `120`
- `TOKENFLOW_RAG_DEFAULT_TOP_K` retrieval top-k default, default `5`
- `TOKENFLOW_RAG_CACHE_TTL_SECONDS` retrieval cache TTL in seconds, default `900`

## Local Run
```bash
python -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt -r requirements.runtime.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## Containerized Run

From repository root:

```bash
docker compose up --build
```

Services:
- API: `http://localhost:8000`
- Runtime worker: `http://localhost:8010`
- PostgreSQL: `localhost:5432`
- Redis: `localhost:6379`

## Endpoints
Auth (prefix `/api/auth`):
- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/auth/me`

Runtime:
- `GET /api/runtime/health`
- `GET /api/runtime/capabilities`
- `GET /api/runtime/runs`
- `GET /api/runtime/runs/{execution_id}/timeline`
- `POST /api/runtime/execute-node`
- `POST /api/runtime/runs/{execution_id}/retry/{node_id}`
- `POST /api/runtime/runs/{execution_id}/resume`
- `POST /api/runtime/runs/{execution_id}/cancel`

Routing:
- `GET /api/routing/queue/health`
- `POST /api/routing/resolve`
- `POST /api/routing/classify`

RAG:
- `POST /api/rag/documents/ingest`
- `POST /api/rag/retrieve`
- `GET /api/rag/metrics`

## Runtime RAG Helpers
Inside runtime node Python snippets, you can call:
- `rag_ingest_text(content, workspace_id="default", title="", source_uri="", metadata={})`
- `rag_search(query, workspace_id="default", top_k=5, rerank=True, max_context_chars=2400)`
