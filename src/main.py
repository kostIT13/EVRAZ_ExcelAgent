from fastapi import FastAPI, Request
from src.core.logging_settings import logger
from contextlib import asynccontextmanager
from sqlalchemy import text
from src.core.db.database import engine
from src.api.router import router as files_router
from src.api.agent_router import router as agent_router
from src.api.trace_router import router as trace_router
from src.api.schema_router import router as schema_router
from src.api.errors import register_exception_handlers
from src.core.ratelimit import get_limiter
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting EVRAZ service (entity-resolution + mart)...")

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            logger.info("Database connection OK")
    except Exception as e:
        logger.error(f"Database connection error: {e}")

    # Стартуем фоновый воркер асинхронного ingestion.
    try:
        from src.services.excel.ingestion_queue import ingestion_queue
        await ingestion_queue.start()
        logger.info("Ingestion queue worker started")
    except Exception as e:
        logger.error(f"Ingestion queue start error: {e}")

    yield

    try:
        from src.services.excel.ingestion_queue import ingestion_queue
        await ingestion_queue.stop()
    except Exception:
        pass
    await engine.dispose()
    logger.info("Engine disposed, shutdown complete")


app = FastAPI(
    title="EVRAZ Agent Service",
    description="AI-агент для работы с Excel-файлами (ЕВРАЗ). "
    "Загрузка, нормализация в mart, entity-resolution и ответы на вопросы.",
    version="0.2.0",
    lifespan=lifespan,
)

register_exception_handlers(app)

# Rate limiting (slowapi).
_limiter = get_limiter()
app.state.limiter = _limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.include_router(files_router)
app.include_router(agent_router)
app.include_router(trace_router)
app.include_router(schema_router)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/metrics")
async def metrics():
    """Prometheus-метрики: латентность, доля failed/low_confidence, RPS, token usage."""
    from src.core.metrics import metrics_response
    return metrics_response()


@app.get("/metrics/summary")
async def metrics_summary_endpoint():
    """Агрегированные метрики (JSON) для фронтенд-страницы 'Метрики'."""
    from src.core.metrics import metrics_summary
    return metrics_summary()