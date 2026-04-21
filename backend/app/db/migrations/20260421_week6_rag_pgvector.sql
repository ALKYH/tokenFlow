-- Week6 RAG migration (PostgreSQL + pgvector)
-- Default embedding dimension: 256

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS rag_documents (
    id BIGSERIAL PRIMARY KEY,
    workspace_id VARCHAR(120) NOT NULL DEFAULT 'default',
    source_uri VARCHAR(500) NOT NULL DEFAULT '',
    title VARCHAR(255) NOT NULL DEFAULT '',
    content TEXT NOT NULL,
    content_hash CHAR(64) NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    ingest_status VARCHAR(32) NOT NULL DEFAULT 'ready',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (workspace_id, content_hash)
);

CREATE TABLE IF NOT EXISTS rag_chunks (
    id BIGSERIAL PRIMARY KEY,
    document_id BIGINT NOT NULL REFERENCES rag_documents(id) ON DELETE CASCADE,
    workspace_id VARCHAR(120) NOT NULL,
    chunk_index INTEGER NOT NULL,
    chunk_text TEXT NOT NULL,
    token_count INTEGER NOT NULL DEFAULT 0,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    embedding VECTOR(256) NOT NULL,
    embedding_model VARCHAR(120) NOT NULL DEFAULT 'hash-v1',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (document_id, chunk_index)
);

CREATE TABLE IF NOT EXISTS rag_query_cache (
    cache_key VARCHAR(128) PRIMARY KEY,
    workspace_id VARCHAR(120) NOT NULL,
    query_text TEXT NOT NULL,
    query_hash CHAR(64) NOT NULL,
    top_k INTEGER NOT NULL DEFAULT 5,
    result JSONB NOT NULL DEFAULT '[]'::jsonb,
    hit_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS rag_query_logs (
    id BIGSERIAL PRIMARY KEY,
    workspace_id VARCHAR(120) NOT NULL,
    query_text TEXT NOT NULL,
    top_k INTEGER NOT NULL DEFAULT 5,
    hit_count INTEGER NOT NULL DEFAULT 0,
    duration_ms DOUBLE PRECISION NOT NULL DEFAULT 0,
    rerank_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    cache_hit BOOLEAN NOT NULL DEFAULT FALSE,
    success BOOLEAN NOT NULL DEFAULT TRUE,
    error_code VARCHAR(64) NOT NULL DEFAULT '',
    estimated_cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_rag_documents_workspace_created ON rag_documents(workspace_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_rag_chunks_workspace ON rag_chunks(workspace_id);
CREATE INDEX IF NOT EXISTS ix_rag_chunks_metadata ON rag_chunks USING GIN (metadata);
CREATE INDEX IF NOT EXISTS ix_rag_query_cache_workspace_expires ON rag_query_cache(workspace_id, expires_at DESC);
CREATE INDEX IF NOT EXISTS ix_rag_query_logs_workspace_created ON rag_query_logs(workspace_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_rag_chunks_embedding_ivfflat ON rag_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

