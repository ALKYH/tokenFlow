# FastAPI Authentication Service

This service provides endpoints for registration, login (JWT), token refresh and `me` retrieval backed by PostgreSQL.

Environment variables (create `.env` or export):

- `DATABASE_URL` e.g. `postgresql+asyncpg://user:pass@localhost:5432/dbname`
- `SECRET_KEY` strong random string used to sign JWTs
- `ACCESS_TOKEN_EXPIRE_MINUTES` (default 30)
- `FRONTEND_ORIGINS` comma-separated allowed CORS origins (default `http://localhost:5173`)

Run locally:

```bash
python -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Endpoints (prefix `/api/auth`):
- `POST /api/auth/register` — body: `{email, password}` → creates user
- `POST /api/auth/login` — body: `{email, password}` → returns `{access_token, token_type}`
- `GET /api/auth/me` — requires `Authorization: Bearer <token>` → returns current user

Frontend integration notes are in this README and example request flows are provided in code comments.
