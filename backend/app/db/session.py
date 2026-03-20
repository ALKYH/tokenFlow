from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from ..core.config import DATABASE_URL

engine = create_async_engine(DATABASE_URL, future=True, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
Base = declarative_base()


async def ensure_runtime_schema():
    async with engine.begin() as conn:
        dialect = conn.dialect.name
        plugin_route_info_statement = (
            "ALTER TABLE plugins ADD COLUMN IF NOT EXISTS route_info JSON NOT NULL DEFAULT '{}'"
            if dialect == 'sqlite'
            else "ALTER TABLE plugins ADD COLUMN IF NOT EXISTS route_info JSON NOT NULL DEFAULT '{}'::json"
        )
        statements = [
            "ALTER TABLE user_secrets ADD COLUMN IF NOT EXISTS secret_name VARCHAR(120) NOT NULL DEFAULT 'default'",
            "ALTER TABLE user_secrets ADD COLUMN IF NOT EXISTS request_prefix VARCHAR(500) NOT NULL DEFAULT ''",
            "ALTER TABLE user_secrets ADD COLUMN IF NOT EXISTS priority INTEGER NOT NULL DEFAULT 100",
            plugin_route_info_statement
        ]
        for statement in statements:
            try:
                await conn.execute(text(statement))
            except Exception:
                continue

async def create_db_and_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
