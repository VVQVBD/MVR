"""Асинхронная сессия SQLAlchemy для эндпоинтов /api/v1.

Тот же DATABASE_URL, что и у синхронной части: драйвер подменяется на асинхронный
(sqlite → aiosqlite; postgresql+psycopg работает в async-режиме сам).
"""
from typing import AsyncIterator

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings


def async_url(url: str) -> str:
    u = make_url(url)
    if u.drivername in ("sqlite", "sqlite+pysqlite"):
        u = u.set(drivername="sqlite+aiosqlite")
    elif u.drivername in ("postgresql", "postgresql+psycopg2"):
        u = u.set(drivername="postgresql+psycopg")
    return u.render_as_string(hide_password=False)


def make_async_sessionmaker(url: str, **engine_kwargs) -> async_sessionmaker:
    engine = create_async_engine(async_url(url), pool_pre_ping=True, **engine_kwargs)
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


AsyncSessionLocal = make_async_sessionmaker(settings.database_url)


async def get_async_db() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session
