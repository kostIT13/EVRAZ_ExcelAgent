from fastapi import FastAPI
from src.core.logging_settings import logger
from contextlib import asynccontextmanager
from sqlalchemy import text
from src.core.db.database import engine
from src.core.qdrant.client import qdrant_client, ensure_collections
from src.api.router import router as files_router
from src.api.agent_router import router as agent_router
from src.api.trace_router import router as trace_router
from src.api.errors import register_exception_handlers


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting EVRAZ RAG service...")

    # Инициализация Qdrant-коллекции
    try:
        await ensure_collections()
        logger.info("Qdrant collections ready")
    except Exception as e:
        logger.error(f"Qdrant initialization error: {e}")

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            logger.info("Database connection OK")
    except Exception as e:
        logger.error(f"Database connection error: {e}")

    yield

    await qdrant_client.close()
    await engine.dispose()
    logger.info("Engine disposed, shutdown complete")


app = FastAPI(
    title="EVRAZ RAG Service",
    description="AI-агент для работы с Excel-файлами (ЕВРАЗ). "
    "Загрузка, парсинг, поиск и ответы на вопросы по данным.",
    version="0.1.0",
    lifespan=lifespan,
)

register_exception_handlers(app)

app.include_router(files_router)
app.include_router(agent_router)
app.include_router(trace_router)


@app.get("/health")
async def health():
    return {"status": "ok"}