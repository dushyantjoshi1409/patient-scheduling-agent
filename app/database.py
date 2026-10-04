"""Database engine, session factory, and base model for async SQLAlchemy.

Handles Railway's DATABASE_URL format automatically — Railway provides
postgresql:// but asyncpg needs postgresql+asyncpg://.
"""
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


def _get_async_url(url: str) -> str:
    """Convert a standard postgres URL to async-compatible format."""
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


engine = create_async_engine(_get_async_url(settings.database_url), echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""
    pass


async def get_db() -> AsyncSession:
    """Dependency that yields an async database session."""
    async with async_session() as session:
        yield session


async def init_db():
    """Create all tables from ORM model metadata."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
