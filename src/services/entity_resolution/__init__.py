"""
Entity-resolution module (бывший RAG).

RAG, dense-эмбеддинги, Qdrant, Ollama и fastembed полностью удалены. Агент
работает по нормализованной факт-таблице mart.price_facts. Сущности
(item_name/supplier/sheet_period) сопоставляются с вопросом через pg_trgm
(similarity()/%) — без векторного поиска, без BM25-индекса на диске, без
RU-лемматизации.

Components
----------
- ``entity_resolver`` — pg_trgm-резолюция сущностей + список для промпта.
- ``query_cache`` — кэш «вопрос → SQL → результат».
"""

from src.services.entity_resolution.entity_resolver import (
    EntityCandidate,
    EntityResolver,
    entity_resolver,
)
from src.services.entity_resolution.query_cache import (
    QueryCacheService,
    query_cache_service,
)

__all__ = [
    "EntityCandidate",
    "EntityResolver",
    "entity_resolver",
    "QueryCacheService",
    "query_cache_service",
]