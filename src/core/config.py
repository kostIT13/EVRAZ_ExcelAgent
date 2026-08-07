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

    # Dense-эмбеддинг модель через Ollama (локальный HTTP /v1/embeddings).
    # nomic-embed-text — 768 dim, контекст 8192 токенов, хорошо работает с русским
    # текстом на CPU. Модель запускается в контейнере Ollama и не зависит от
    # HuggingFace Hub (в отличие от fastembed e5-large, который качал ~2.2 ГБ с HF
    # и зависал при недоступности HF).
    # Размерность 768 ОБЯЗАНА совпадать с размерностью коллекции в Qdrant
    # (EMBED_DIMENSION). После смены размерности пересоздайте коллекцию
    # (scripts/recreate_qdrant_collection.py) и заново загрузите файлы.
    # EMBED_MODEL оставлен для обратной совместимости; embedder использует OLLAMA_EMBED_MODEL.
    EMBED_MODEL: str = "nomic-embed-text"
    OLLAMA_EMBED_MODEL: str = "nomic-embed-text"
    EMBED_DIMENSION: int = 768

    # Размер батча эмбеддингов (количество текстов на один HTTP-запрос к Ollama).
    # Значение можно переопределить через .env (EMBED_BATCH_SIZE).
    EMBED_BATCH_SIZE: int = 32

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