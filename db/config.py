from __future__ import annotations

import os

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

load_dotenv()


def _get_database_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    # Railway provides postgres:// but asyncpg needs postgresql+asyncpg://
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


DATABASE_URL: str = _get_database_url()

engine = create_async_engine(DATABASE_URL, echo=False) if DATABASE_URL else None

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
