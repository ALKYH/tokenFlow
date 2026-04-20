# FastAPI Authentication Service

This service provides endpoints for registration, login (JWT), token refresh and `me` retrieval backed by PostgreSQL.

Environment variables (create `.env` or export):

- `DATABASE_URL` e.g. `postgresql+asyncpg://user:pass@localhost:5432/dbname`
- `SECRET_KEY` strong random string used to sign JWTs
- `ACCESS_TOKEN_EXPIRE_MINUTES` (default 30)
- `FRONTEND_ORIGINS` comma-separated allowed CORS origins (default `http://localhost:5173`)
- `TOKENFLOW_MODELS_DIR` local model directory (default `../models`)
- `TOKENFLOW_RUNTIME_TIMEOUT_SECONDS` runtime execution timeout in seconds
- `TOKENFLOW_RUNTIME_MAX_CONCURRENCY` runtime parallel execution limit

Run locally:

```bash
python -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Optional local model runtime dependency:

```bash
pip install -r requirements.runtime.txt
```

Endpoints (prefix `/api/auth`):
- `POST /api/auth/register` — body: `{email, password}` → creates user
- `POST /api/auth/login` — body: `{email, password}` → returns `{access_token, token_type}`
- `GET /api/auth/me` — requires `Authorization: Bearer <token>` → returns current user

Runtime endpoints:
- `GET /api/runtime/health` — runtime health, limits and discovered model list
- `GET /api/runtime/capabilities` — node capability metadata
- `POST /api/runtime/execute-node` — execute node payload (`NodeExecutionRequest`)

Frontend integration notes are in this README and example request flows are provided in code comments.
