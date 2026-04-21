from backend.app.schemas.rag import RagChunkHit
from backend.app.services.rag_service import (
    build_context_from_hits,
    chunk_text,
    hash_embedding,
    rerank_hits,
)


def test_chunk_text_with_overlap():
    content = "TokenFlow RAG pipelines need chunking and overlap for robust retrieval quality."
    chunks = chunk_text(content * 8, chunk_size=80, chunk_overlap=16)
    assert len(chunks) >= 3
    assert all(len(chunk) <= 80 for chunk in chunks)


def test_hash_embedding_is_deterministic():
    first = hash_embedding("tokenflow", vector_dim=32)
    second = hash_embedding("tokenflow", vector_dim=32)
    assert first == second
    assert len(first) == 32
    norm = sum(value * value for value in first) ** 0.5
    assert 0.999 <= norm <= 1.001


def test_rerank_hits_boosts_keyword_overlap():
    hits = [
        RagChunkHit(
            chunk_id=1,
            document_id=1,
            chunk_index=0,
            score=0.70,
            text="PostgreSQL extension setup details.",
            metadata={},
        ),
        RagChunkHit(
            chunk_id=2,
            document_id=1,
            chunk_index=1,
            score=0.69,
            text="How pgvector improves vector retrieval in PostgreSQL.",
            metadata={},
        ),
    ]
    reranked = rerank_hits("pgvector retrieval", hits)
    assert reranked[0].chunk_id == 2


def test_context_builder_respects_limit():
    hits = [
        RagChunkHit(
            chunk_id=1,
            document_id=9,
            chunk_index=0,
            score=0.91,
            text="A" * 400,
            metadata={},
        )
    ]
    context = build_context_from_hits(hits, max_context_chars=256)
    assert len(context) <= 256
    assert context.startswith("[doc:9 chunk:0")

