from src.core.logging_settings import logger
from src.core.config import settings
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from typing import AsyncGenerator, Optional


engine = create_async_engine(
    settings.POSTGRES_URL,
    echo=settings.DEBUG,
    pool_pre_ping=True,
    connect_args={
        "statement_cache_size": 0,
    },
)


async_session_maker = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
            logger.debug("Transaction committed")
        except Exception:
            await session.rollback()
            logger.exception("Transaction error")
            raise


def make_readonly_url() -> str:
    """DSN для read-only роли app_readonly (GRANT SELECT на mart.*).

    Executor-узел подключается через эту роль, чтобы защита SQL была на уровне
    БД (read-only), а не только на уровне keyword-blacklist в промпте.
    """
    from urllib.parse import quote

    base = settings.POSTGRES_URL
    if "://" in base:
        scheme, rest = base.split("://", 1)
        host_part = rest.split("@", 1)
        user = quote(settings.READONLY_DB_USER, safe="")
        pwd = quote(settings.READONLY_DB_PASSWORD or "", safe="")
        new_auth = f"{user}:{pwd}" if settings.READONLY_DB_PASSWORD else user
        new_rest = f"{new_auth}@{host_part[1]}" if len(host_part) == 2 else rest
        return f"{scheme}://{new_rest}"
    return base


# Read-only engine для Executor-узла (отдельная сессия под app_readonly).
readonly_engine = create_async_engine(
    make_readonly_url(),
    echo=settings.DEBUG,
    pool_pre_ping=True,
    connect_args={"statement_cache_size": 0},
)
readonly_session_maker = async_sessionmaker(
    bind=readonly_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)