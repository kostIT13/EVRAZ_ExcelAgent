from fastapi import FastAPI
from src.core.logging_settings import logger 
from contextlib import asynccontextmanager
from sqlalchemy import text
from src.core.db.database import engine
from src.core.logging_settings import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("The application is running")
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as e:
        logger.error(f"Database connection error:{e}")
    yield 
    await engine.dispose()
    logger.info("Ready")


app = FastAPI(title="production-RAG-service", lifespan=lifespan)