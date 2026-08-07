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

    # Dense-эмбеддинг модель (локальный инференс через fastembed, без HTTP к Ollama).
    # intfloat/multilingual-e5-large — мультиязычная модель (~100 языков, включая
    # русский), контекст 512 токенов (~1000 символов русского текста), что позволяет
    # эмбеддить чанки без агрессивной обрезки (в отличие от прежней MiniLM-L12-v2
    # с контекстом 128 токенов, терявшей ~80% содержания чанка).
    # ВАЖНО: fastembed 0.8.0 не поддерживает e5-small, поэтому используем e5-large.
    # Размерность 1024 ОБЯЗАНА совпадать с размерностью коллекции в Qdrant
    # (EMBED_DIMENSION). После смены размерности пересоздайте коллекцию
    # (scripts/recreate_qdrant_collection.py) и заново загрузите файлы.
    EMBED_MODEL: str = "intfloat/multilingual-e5-large"
    # Legacy-параметр (модель эмбеддинга в Ollama), оставлен для обратной
    # совместимости при деплое, но fastembed-embedder его не использует.
    OLLAMA_EMBED_MODEL: str = "intfloat/multilingual-e5-large"
    EMBED_DIMENSION: int = 1024

    # Размер батча эмбеддингов (количество текстов на один проход fastembed).
    # fastembed инференсит локально на CPU батчами — это сильно быстрее
    # последовательных HTTP-запросов к Ollama. Значение можно переопределить
    # через .env (EMBED_BATCH_SIZE).
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