from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.db.session import ensure_rag_schema


async def main() -> None:
    await ensure_rag_schema()
    print("Week6 migration complete: pgvector extension and RAG tables are ensured.")


if __name__ == "__main__":
    asyncio.run(main())

