from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
    LOG_LEVEL: str = "INFO"

    DEBUG: bool = False

    LLM_BASE_URL: str
    LLM_API_KEY: str
    LLM_MODEL_PRIMARY: str
    LLM_MODEL_CHEAP: str

    OLLAMA_BASE_URL: str = "http://ollama:11434/v1"
    OLLAMA_EMBED_MODEL: str = "nomic-embed-text"
    EMBED_DIMENSION: int = 768

    LLM_TEMPERATURE: float = 0.1
    LLM_MAX_TOKENS: int = 2048
    REQUEST_TIMEOUT_S: int = 60
    MAX_RETRIES: int = 3

    POSTGRES_URL: str
    POSTGRES_DB: str
    POSTGRES_HOST: str
    POSTGRES_PASSWORD: str
    POSTGRES_USER: str
    POSTGRES_PORT: int = 5432


settings = Settings()