from fastapi import FastAPI
from src.core.logging_settings import logger
from contextlib import asynccontextmanager
from sqlalchemy import text
from src.core.db.database import engine
from src.api.router import router as files_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting EVRAZ RAG service...")
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            logger.info("Database connection OK")
    except Exception as e:
        logger.error(f"Database connection error: {e}")
    yield
    await engine.dispose()
    logger.info("Engine disposed, shutdown complete")


app = FastAPI(title="EVRAZ RAG Service", description="AI-агент для работы с Excel-файлами (ЕВРАЗ). "
                "Загрузка, парсинг, поиск и ответы на вопросы по данным.", version="0.1.0", lifespan=lifespan,)

app.include_router(files_router)


@app.get("/health")
async def health():
    return {"status": "ok"}