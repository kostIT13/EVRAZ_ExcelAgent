from src.core.logging_settings import logger 
from src.core.config import settings
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from typing import AsyncGenerator
from sqlalchemy import event
import asyncpg


engine = create_async_engine(
    settings.POSTGRES_URL, 
    echo=settings.DEBUG, 
    pool_pre_ping=True
)


@event.listens_for(engine.sync_engine, "connect")
def register_vector(dbapi_connection, connection_record):
    if isinstance(dbapi_connection, asyncpg.Connection):
        dbapi_connection.set_type_codec(
            'vector',
            encoder=lambda x: '[' + ','.join(map(str, x)) + ']' if x else None,
            decoder=lambda x: [float(v) for v in x[1:-1].split(',')] if x else None,
            format='text'
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
        except Exception as e:
            await session.rollback()
            logger.error(f"Transaction error {e}", exc_info=True)
            raise