"""Postgres checkpointer для LangGraph.

Оборачивает ``AsyncPostgresSaver`` из ``langgraph-checkpoint-postgres`` в синглтон
с общим пулом соединений. Даёт бесплатно:

* полную историю состояний графа по ``thread_id`` (graph.aget_state_history);
* поддержку ``interrupt()`` / ``Command(resume=...)`` для уточняющих вопросов;
* time-travel отладку при разборе неверных ответов агента.

Таблицы ``checkpoints`` / ``checkpoint_blobs`` / ``checkpoint_writes`` /
``checkpoint_migrations`` создаются автоматически методом ``AsyncPostgresSaver.setup()``
при первой инициализации (внутренние миграции пакета).
"""

from __future__ import annotations

import asyncio
from typing import Optional

from psycopg_pool import AsyncConnectionPool

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from src.core.config import settings
from src.core.logging_settings import logger


def build_psycopg_dsn() -> str:
    """Собирает DSN в формате psycopg (не asyncpg) из настроек приложения."""
    return (
        f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}"
        f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
    )


class CheckpointerManager:
    """Синглтон-менеджер Postgres-checkpointer'а LangGraph."""

    _pool: Optional[AsyncConnectionPool] = None
    _saver: Optional[AsyncPostgresSaver] = None
    _setup_lock: "asyncio.Lock" = asyncio.Lock()

    @classmethod
    async def get(cls) -> AsyncPostgresSaver:
        """Возвращает инициализированный checkpointer (лениво создаёт пул и таблицы)."""
        if cls._saver is None:
            async with cls._setup_lock:
                if cls._saver is None:
                    await cls._init()
        return cls._saver

    @classmethod
    async def _init(cls) -> None:
        dsn = build_psycopg_dsn()
        # autocommit=True обязателен: внутренние миграции langgraph-checkpoint-postgres
        # используют CREATE INDEX CONCURRENTLY, который нельзя выполнять в транзакции.
        pool = AsyncConnectionPool(
            conninfo=dsn,
            kwargs={"autocommit": True},
            max_size=10,
            open=False,
        )
        await pool.open()

        saver = AsyncPostgresSaver(pool)
        await saver.setup()

        cls._pool = pool
        cls._saver = saver
        logger.info("LangGraph Postgres checkpointer initialised (pool max_size=10)")

    @classmethod
    async def close(cls) -> None:
        """Закрывает пул соединений (вызывается при завершении приложения)."""
        if cls._pool is not None:
            await cls._pool.close()
            cls._pool = None
        cls._saver = None
        logger.info("LangGraph Postgres checkpointer closed")


# Удобный алиас для быстрого доступа к активному инстансу.
checkpointer_manager = CheckpointerManager