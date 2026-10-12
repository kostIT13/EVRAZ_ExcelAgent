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


# Единый event loop для всех тестов: asyncpg-соединения из пула привязаны
# к loop, в котором созданы. Если каждый тест создаёт свой loop через
# asyncio.run()— пул ломается с "Event loop is closed" (Windows и не только).
_LOOP = asyncio.new_event_loop()
asyncio.set_event_loop(_LOOP)


def _run(coro):
    """Синхронный запуск корутины в общем event loop (pytest не настроен на asyncio-режим)."""
    return _LOOP.run_until_complete(coro)

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
            # AsyncEngine не поддерживает create_all напрямую — выполняем DDL
            # через run_sync (SQLAlchemy 2.0).
            await conn.run_sync(Base.metadata.create_all)

    _run(_setup())

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    yield session_factory

    async def _teardown():
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
        finally:
            await engine.dispose()

    _run(_teardown())