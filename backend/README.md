# FastAPI Backend Service

This service provides auth APIs, runtime node execution APIs, and Week6 RAG APIs backed by PostgreSQL.

## Environment Variables
- `DATABASE_URL` e.g. `postgresql+asyncpg://user:pass@localhost:5432/dbname`
- `SECRET_KEY` strong random string used to sign JWTs
- `ACCESS_TOKEN_EXPIRE_MINUTES` default `30`
- `FRONTEND_ORIGINS` comma-separated CORS origins, default `http://localhost:5173`
- `TOKENFLOW_MODELS_DIR` local model directory, default `../models`
- `TOKENFLOW_RUNTIME_TIMEOUT_SECONDS` runtime execution timeout in seconds
- `TOKENFLOW_RUNTIME_MAX_CONCURRENCY` runtime parallel execution limit
- `TOKENFLOW_RUNTIME_MODEL_BACKEND` `llama-cpp-python` (default) or `vllm`
- `TOKENFLOW_RUNTIME_DEFAULT_MODEL` default model for `run_local_model(...)`
- `TOKENFLOW_RUNTIME_VLLM_TENSOR_PARALLEL_SIZE` vLLM tensor parallel size
- `TOKENFLOW_RUNTIME_VLLM_GPU_MEMORY_UTILIZATION` vLLM GPU memory utilization (0-1)
- `TOKENFLOW_RUNTIME_VLLM_TRUST_REMOTE_CODE` vLLM trust remote code flag
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

## Endpoints
Auth (prefix `/api/auth`):
- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/auth/me`

Runtime:
- `GET /api/runtime/health`
- `GET /api/runtime/capabilities`
- `POST /api/runtime/execute-node`

RAG (Week6):
- `POST /api/rag/documents/ingest` ingest raw text and create chunk embeddings
- `POST /api/rag/retrieve` vector retrieve with optional rerank + context injection
- `GET /api/rag/metrics` retrieval metrics summary

## Runtime RAG Helpers
Inside runtime node Python snippets, you can call:
- `rag_ingest_text(content, workspace_id="default", title="", source_uri="", metadata={})`
- `rag_search(query, workspace_id="default", top_k=5, rerank=True, max_context_chars=2400)`

