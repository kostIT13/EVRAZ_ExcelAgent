from typing import Annotated, Any

from pydantic import BeforeValidator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _coerce_bool(v: Any) -> bool:
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
        extra="ignore",
    )
    LOG_LEVEL: str = "INFO"
    DEBUG: Annotated[bool, BeforeValidator(_coerce_bool)] = False

    API_KEY: str = ""
    RATE_LIMIT_ASK: str = "30/minute"
    RATE_LIMIT_UPLOAD: str = "10/minute"

    LLM_BASE_URL: str
    LLM_API_KEY: str
    LLM_MODEL_PRIMARY: str
    LLM_MODEL_CHEAP: str

    LLM_TEMPERATURE: float = 0.1
    LLM_MAX_TOKENS: int = 2048
    REQUEST_TIMEOUT_S: int = 60
    MAX_RETRIES: int = 3

    INGESTION_QUEUE_MODE: str = "inproc"  
    INGESTION_STATUS_MAX_AGE_DAYS: int = 7

    POSTGRES_URL: str
    POSTGRES_DB: str
    POSTGRES_HOST: str
    POSTGRES_PASSWORD: str
    POSTGRES_USER: str
    POSTGRES_PORT: int = 5432

    DB_STATEMENT_TIMEOUT_MS: int = 30000

    TRIGRAM_THRESHOLD: float = 0.25

settings = Settings()