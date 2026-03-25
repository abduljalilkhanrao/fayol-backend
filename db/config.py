from __future__ import annotations

import os

from dotenv import load_dotenv
import ssl

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

load_dotenv()


def _get_database_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    # Strip ?pgbouncer=true — asyncpg doesn't understand it
    url = url.split("?")[0]
    # Railway provides postgres:// but asyncpg needs postgresql+asyncpg://
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


DATABASE_URL: str = _get_database_url()

# Supabase requires SSL; create a permissive SSL context for asyncpg
_ssl_context = ssl.create_default_context()
_ssl_context.check_hostname = False
_ssl_context.verify_mode = ssl.CERT_NONE

# prepared_statement_cache_size=0 is required when connecting through PgBouncer
engine = (
    create_async_engine(
        DATABASE_URL,
        echo=False,
        connect_args={"ssl": _ssl_context, "prepared_statement_cache_size": 0},
        pool_pre_ping=True,
    )
    if DATABASE_URL
    else None
)

async_session = (
    async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    if engine
    else None
)


async def get_session():
    """FastAPI dependency that yields an async database session."""
    if async_session is None:
        raise RuntimeError("DATABASE_URL is not configured")
    async with async_session() as session:
        yield session
