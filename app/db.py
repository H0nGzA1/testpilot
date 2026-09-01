"""Async engine + session factory. create_all for MVP (Alembic added in Phase 2)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings
from app.models import Base

_engine = None
_Session: async_sessionmaker[AsyncSession] | None = None


def _ensure() -> async_sessionmaker[AsyncSession]:
    global _engine, _Session
    if _Session is None:
        # NullPool: never reuse a connection across event loops. Celery tasks each spin a
        # fresh loop via asyncio.run(), and pooled asyncpg connections bound to a prior
        # loop raise "another operation is in progress". A fresh connection per session is
        # cheap enough for this internal tool and kills that whole bug class.
        _engine = create_async_engine(get_settings().database_url, future=True, poolclass=NullPool)
        _Session = async_sessionmaker(_engine, expire_on_commit=False)
    return _Session


async def init_db() -> None:
    _ensure()
    assert _engine is not None
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@asynccontextmanager
async def db_session() -> AsyncIterator[AsyncSession]:
    session = _ensure()()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
