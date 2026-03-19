"""
Compatibility entrypoint.

This module re-exports the refactored FastAPI `app` so existing run commands
like `uvicorn main:app` continue to work.
"""

from app.main import app  # noqa: E402,F401
