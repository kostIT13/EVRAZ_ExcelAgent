"""Фикстуры интеграционных тестов.

Интеграционные тесты запускаются только когда задана переменная окружения
``TEST_POSTGRES_URL`` (например::

    TEST_POSTGRES_URL=postgresql+asyncpg://evraz:evraz_secret@localhost:5432/evraz_test

    pytest tests/integration -m integration -v

Если переменная не задана — модуль пропускается на этапе сбора
(``pytestmark`` в тестовых модулях). Фикстура ``test_db`` создаёт схему
``mart`` и все таблицы ``Base.metadata`` в тестовой БД.
"""
import asyncio
import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.db.base import Base

# Импорт обязателен: регистрирует все модели в Base.metadata.
import src.core.db.models  # noqa: F401


def _run(coro):
    """Синхронный запуск корутины (pytest не настроен на asyncio-режим)."""
    return asyncio.run(coro)


def _test_db_url() -> str | None:
    return os.environ.get("TEST_POSTGRES_URL")


@pytest.fixture(scope="session")
def test_db():
    url = _test_db_url()
    if not url:
        pytest.skip("TEST_POSTGRES_URL не задан — интеграционные тесты требуют PostgreSQL")

    engine = create_async_engine(
        url,
        pool_pre_ping=True,
        connect_args={"statement_cache_size": 0},
    )

    async def _setup():
        async with engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
            await conn.execute(text("CREATE SCHEMA IF NOT EXISTS mart"))
        await Base.metadata.create_all(engine)

    _run(_setup())

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    yield session_factory

    async def _teardown():
        try:
            await Base.metadata.drop_all(engine)
        finally:
            await engine.dispose()

    _run(_teardown())