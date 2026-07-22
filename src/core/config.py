from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
    LOG_LEVEL: str = "INFO"

    DEBUG: bool = False

    LLM_BASE_URL: str
    LLM_API_KEY: str
    LLM_MODEL_PRIMARY: str
    LLM_MODEL_CHEAP: str
    OLLAMA_EMBED_MODEL: str
    OLLAMA_BASE_URL: str
    EMBED_DIMENSION: int = 768 

    POSTGRES_URL: str 
    POSTGRES_DB: str 
    POSTGRES_HOST: str 
    POSTGRES_PASSWORD: str 
    POSTGRES_USER: str
    POSTGRES_PORT: int = 5432


settings = Settings()