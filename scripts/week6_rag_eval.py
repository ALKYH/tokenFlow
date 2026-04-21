from __future__ import annotations

import asyncio
import json
import statistics
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.db.session import ensure_rag_schema
from backend.app.schemas.rag import RagDocumentIngestRequest, RagRetrieveRequest
from backend.app.services.rag_service import get_retrieval_metrics, ingest_document, retrieve_chunks


EVAL_WORKSPACE_ID = "week6_eval"

DOCUMENTS = [
    {
        "title": "PostgreSQL pgvector Basics",
        "source_uri": "eval://pgvector",
        "content": (
            "pgvector adds a vector data type and distance operators for PostgreSQL. "
            "It supports cosine distance search with ivfflat indexes for fast approximate retrieval."
        ),
    },
    {
        "title": "RAG Pipeline Design",
        "source_uri": "eval://pipeline",
        "content": (
            "A complete RAG pipeline includes ingestion, chunking, embedding, retrieval, rerank, "
            "and context injection before LLM response generation."
        ),
    },
    {
        "title": "Observability and Caching",
        "source_uri": "eval://metrics",
        "content": (
            "Retrieval systems should track hit rate, failure rate, average latency, and cache hit rate. "
            "Query cache and embedding cache reduce repeated work and stabilize latency."
        ),
    },
]

QUERY_CASES = [
    {"query": "How does pgvector support retrieval in PostgreSQL?", "expected_keywords": ["pgvector", "cosine", "ivfflat"]},
    {"query": "What steps are required in a complete RAG pipeline?", "expected_keywords": ["chunking", "embedding", "rerank"]},
    {"query": "Which metrics should we monitor for retrieval quality?", "expected_keywords": ["hit rate", "latency", "failure rate"]},
]


def _hit_contains_expected(hits: list[dict[str, Any]], expected_keywords: list[str]) -> bool:
    joined = " ".join(str(hit.get("text", "")) for hit in hits).lower()
    return any(keyword.lower() in joined for keyword in expected_keywords)


async def main() -> None:
    output_dir = ROOT / "output" / "week6"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "rag-eval-report.json"

    report: dict[str, Any] = {
        "workspace_id": EVAL_WORKSPACE_ID,
        "documents": [],
        "queries": [],
    }

    try:
        await ensure_rag_schema()

        for document in DOCUMENTS:
            ingest_payload = RagDocumentIngestRequest(
                workspace_id=EVAL_WORKSPACE_ID,
                title=document["title"],
                source_uri=document["source_uri"],
                content=document["content"],
                metadata={"stage": "week6_eval"},
            )
            ingest_result = await ingest_document(ingest_payload)
            report["documents"].append(ingest_result.model_dump())

        cold_latencies: list[float] = []
        warm_latencies: list[float] = []
        recalls: list[float] = []
        estimated_costs: list[float] = []

        for case in QUERY_CASES:
            cold = await retrieve_chunks(
                RagRetrieveRequest(
                    workspace_id=EVAL_WORKSPACE_ID,
                    query=case["query"],
                    top_k=5,
                    rerank=True,
                    max_context_chars=2400,
                )
            )
            warm = await retrieve_chunks(
                RagRetrieveRequest(
                    workspace_id=EVAL_WORKSPACE_ID,
                    query=case["query"],
                    top_k=5,
                    rerank=True,
                    max_context_chars=2400,
                )
            )

            cold_dump = cold.model_dump()
            warm_dump = warm.model_dump()
            recall = 1.0 if _hit_contains_expected(cold_dump["hits"], case["expected_keywords"]) else 0.0

            cold_latencies.append(cold.duration_ms)
            warm_latencies.append(warm.duration_ms)
            recalls.append(recall)
            estimated_costs.append(cold.estimated_cost_usd)

            report["queries"].append(
                {
                    "query": case["query"],
                    "expected_keywords": case["expected_keywords"],
                    "cold": cold_dump,
                    "warm": warm_dump,
                    "recall_hit": bool(recall),
                }
            )

        metrics = await get_retrieval_metrics(workspace_id=EVAL_WORKSPACE_ID, window_hours=24)
        report["summary"] = {
            "recall_at_5": round(sum(recalls) / max(1, len(recalls)), 4),
            "avg_cold_latency_ms": round(statistics.mean(cold_latencies), 3),
            "avg_warm_latency_ms": round(statistics.mean(warm_latencies), 3),
            "avg_estimated_cost_usd": round(statistics.mean(estimated_costs), 8),
            "metrics_window_24h": metrics.model_dump(mode="json"),
        }
        report["status"] = "ok"
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = str(exc)

    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved: {output_path}")
    if report["status"] != "ok":
        raise RuntimeError(report.get("error", "week6 eval failed"))


if __name__ == "__main__":
    asyncio.run(main())

