from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.schemas.rag import RagDocumentIngestRequest
from backend.app.services.rag_service import ingest_document


SAMPLE_DOCS = [
    {
        "title": "TokenFlow Runtime",
        "source_uri": "seed://runtime",
        "content": (
            "TokenFlow runtime executes Python snippets in a constrained sandbox. "
            "It exposes run_local_model for local GGUF or vLLM inference and records structured metrics."
        ),
    },
    {
        "title": "TokenFlow RAG",
        "source_uri": "seed://rag",
        "content": (
            "Week6 introduces PostgreSQL plus pgvector for RAG. "
            "The pipeline includes ingestion, chunking, embedding, retrieval, optional rerank, cache, and metrics."
        ),
    },
]


async def main() -> None:
    for item in SAMPLE_DOCS:
        payload = RagDocumentIngestRequest(
            workspace_id="week6_seed",
            title=item["title"],
            source_uri=item["source_uri"],
            content=item["content"],
            metadata={"source": "week6_init"},
        )
        result = await ingest_document(payload)
        print(
            f"Ingested document_id={result.document_id} "
            f"title={item['title']} chunk_count={result.chunk_count}"
        )
    print("Week6 initialization complete.")


if __name__ == "__main__":
    asyncio.run(main())

