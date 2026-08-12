from typing import Annotated, Any

from pydantic import BeforeValidator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _coerce_bool(v: Any) -> bool:
    """Приводит строку из .env (например 'release'/'true'/'1') к bool."""
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("1", "true", "yes", "on", "release"):
            return True
        if s in ("0", "false", "no", "off", ""):
            return False
    return bool(v)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # Позволяет игнорировать устаревшие ключи (.env), удалённые из схемы
        # (Ollama/Qdrant/embedding), чтобы не ломать старт при неполной чистке .env.
        extra="ignore",
    )
    LOG_LEVEL: str = "INFO"

    # DEBUG ранее принимал bool; в .env присутствует 'release' (устаревшее значение).
    # Приводим к bool безопасно, чтобы не ломать старт.
    DEBUG: Annotated[bool, BeforeValidator(_coerce_bool)] = False

    # Auth: API-ключ для /files/* и /ask/*. Пустой → auth отключён (dev).
    API_KEY: str = ""
    # Rate limiting (slowapi): "N/minute|hour|day" или пусто — отключено.
    RATE_LIMIT_ASK: str = "30/minute"
    RATE_LIMIT_UPLOAD: str = "10/minute"

    LLM_BASE_URL: str
    LLM_API_KEY: str
    LLM_MODEL_PRIMARY: str
    LLM_MODEL_CHEAP: str

    # Векторные эмбеддинги (fastembed), Qdrant и Ollama полностью удалены.
    # Entity-resolution работает через Postgres pg_trgm (similarity()/%) по
    # mart.price_facts.item_name/.supplier — без эмбеддинг-модели.

    LLM_TEMPERATURE: float = 0.1
    LLM_MAX_TOKENS: int = 2048
    REQUEST_TIMEOUT_S: int = 60
    MAX_RETRIES: int = 3

    # Асинхронный ingestion: лёгкая in-process очередь (без внешнего брокера).
    # Для прод-развёртывания замените на Celery/RQ/arq + Redis/Postgres LISTEN.
    INGESTION_QUEUE_MODE: str = "inproc"  # inproc | celery | arq
    INGESTION_STATUS_MAX_AGE_DAYS: int = 7

    POSTGRES_URL: str
    POSTGRES_DB: str
    POSTGRES_HOST: str
    POSTGRES_PASSWORD: str
    POSTGRES_USER: str
    POSTGRES_PORT: int = 5432

    # statement_timeout для SQL, выполняемого Executor-узлом.
    DB_STATEMENT_TIMEOUT_MS: int = 30000

    # Порог pg_trgm similarity для fuzzy-сопоставления сущностей (0..1).
    TRIGRAM_THRESHOLD: float = 0.25


settings = Settings()