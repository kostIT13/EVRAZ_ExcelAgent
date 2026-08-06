from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
    LOG_LEVEL: str = "INFO"

    DEBUG: bool = False

    LLM_BASE_URL: str
    LLM_API_KEY: str
    LLM_MODEL_PRIMARY: str
    LLM_MODEL_CHEAP: str

    OLLAMA_BASE_URL: str
    OLLAMA_EMBED_MODEL: str
    EMBED_DIMENSION: int = 1024

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

    # Qdrant (векторное хранилище)
    QDRANT_URL: str = "http://qdrant:6333"
    QDRANT_API_KEY: str = ""
    QDRANT_COLLECTION: str = "evraz_chunks"
    QDRANT_EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"
    QDRANT_SPARSE_MODEL: str = "Qdrant/bm25"

    # Реранкер (flashrank)
    RERANKER_MODEL: str = "ms-marco-MiniLM-L-12-v2"
    RERANKER_ENABLED: bool = True
    RERANKER_TOP_K: int = 5


settings = Settings()