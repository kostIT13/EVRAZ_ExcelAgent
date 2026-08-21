from __future__ import annotations
import asyncio
from typing import Optional
from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from src.core.config import settings
from src.core.logging_settings import logger


def build_psycopg_dsn() -> str:
    return (
        f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}"
        f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
    )


class CheckpointerManager:

    _pool: Optional[AsyncConnectionPool] = None
    _saver: Optional[AsyncPostgresSaver] = None
    _setup_lock: "asyncio.Lock" = asyncio.Lock()

    @classmethod
    async def get(cls) -> AsyncPostgresSaver:
        if cls._saver is None:
            async with cls._setup_lock:
                if cls._saver is None:
                    await cls._init()
        return cls._saver

    @classmethod
    async def _init(cls) -> None:
        dsn = build_psycopg_dsn()
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
        if cls._pool is not None:
            await cls._pool.close()
            cls._pool = None
        cls._saver = None
        logger.info("LangGraph Postgres checkpointer closed")


checkpointer_manager = CheckpointerManager