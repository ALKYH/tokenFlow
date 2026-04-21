import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from ..core.config import DATABASE_URL

engine = create_async_engine(DATABASE_URL, future=True, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
Base = declarative_base()


def _rag_vector_dim() -> int:
    raw = os.environ.get('TOKENFLOW_RAG_VECTOR_DIM', '256').strip()
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = 256
    return max(8, min(4096, value))


async def ensure_runtime_schema():
    async with engine.begin() as conn:
        dialect = conn.dialect.name
        plugin_route_info_statement = (
            "ALTER TABLE plugins ADD COLUMN IF NOT EXISTS route_info JSON NOT NULL DEFAULT '{}'"
            if dialect == 'sqlite'
            else "ALTER TABLE plugins ADD COLUMN IF NOT EXISTS route_info JSON NOT NULL DEFAULT '{}'::json"
        )
        plugin_library_kind_statement = "ALTER TABLE plugins ADD COLUMN IF NOT EXISTS library_kind VARCHAR(80) NOT NULL DEFAULT 'personal'"
        inbox_source_statement = "ALTER TABLE inbox_messages ADD COLUMN IF NOT EXISTS source VARCHAR(120) NOT NULL DEFAULT 'system'"
        inbox_attachments_statement = (
            "ALTER TABLE inbox_messages ADD COLUMN IF NOT EXISTS attachments JSON NOT NULL DEFAULT '[]'"
            if dialect == 'sqlite'
            else "ALTER TABLE inbox_messages ADD COLUMN IF NOT EXISTS attachments JSON NOT NULL DEFAULT '[]'::json"
        )
        statements = [
            "ALTER TABLE user_secrets ADD COLUMN IF NOT EXISTS secret_name VARCHAR(120) NOT NULL DEFAULT 'default'",
            "ALTER TABLE user_secrets ADD COLUMN IF NOT EXISTS request_prefix VARCHAR(500) NOT NULL DEFAULT ''",
            "ALTER TABLE user_secrets ADD COLUMN IF NOT EXISTS priority INTEGER NOT NULL DEFAULT 100",
            plugin_route_info_statement,
            plugin_library_kind_statement,
            inbox_source_statement,
            inbox_attachments_statement
        ]
        for statement in statements:
            try:
                await conn.execute(text(statement))
            except Exception:
                continue


async def ensure_rag_schema():
    async with engine.begin() as conn:
        if conn.dialect.name != 'postgresql':
            return
        vector_dim = _rag_vector_dim()
        ddl_statements = [
            "CREATE EXTENSION IF NOT EXISTS vector",
            """
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
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS rag_chunks (
                id BIGSERIAL PRIMARY KEY,
                document_id BIGINT NOT NULL REFERENCES rag_documents(id) ON DELETE CASCADE,
                workspace_id VARCHAR(120) NOT NULL,
                chunk_index INTEGER NOT NULL,
                chunk_text TEXT NOT NULL,
                token_count INTEGER NOT NULL DEFAULT 0,
                metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                embedding VECTOR({vector_dim}) NOT NULL,
                embedding_model VARCHAR(120) NOT NULL DEFAULT 'hash-v1',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (document_id, chunk_index)
            )
            """,
            """
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
            )
            """,
            """
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
            )
            """,
            "CREATE INDEX IF NOT EXISTS ix_rag_documents_workspace_created ON rag_documents(workspace_id, created_at DESC)",
            "CREATE INDEX IF NOT EXISTS ix_rag_chunks_workspace ON rag_chunks(workspace_id)",
            "CREATE INDEX IF NOT EXISTS ix_rag_chunks_metadata ON rag_chunks USING GIN (metadata)",
            "CREATE INDEX IF NOT EXISTS ix_rag_query_cache_workspace_expires ON rag_query_cache(workspace_id, expires_at DESC)",
            "CREATE INDEX IF NOT EXISTS ix_rag_query_logs_workspace_created ON rag_query_logs(workspace_id, created_at DESC)",
            "CREATE INDEX IF NOT EXISTS ix_rag_chunks_embedding_ivfflat ON rag_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)",
            "ALTER TABLE rag_documents ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()",
            f"ALTER TABLE rag_chunks ALTER COLUMN embedding TYPE VECTOR({vector_dim}) USING embedding::VECTOR({vector_dim})",
        ]
        for statement in ddl_statements:
            await conn.execute(text(statement))


async def create_db_and_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
