"""Entity Resolution без векторных эмбеддингов (чистый pg_trgm).

RAG, dense-эмбеддинги, Qdrant, Ollama и fastembed полностью удалены. Список
уникальных сущностей (item_name, supplier, sheet_period) извлекается из
mart.price_facts напрямую (entity_embeddings удалена):

1. На этапе ingestion — список сущностей кладётся в Redis/in-memory-кэш (или
   читается из БД), а не эмбеддится.
2. В рантайме вопрос сопоставляется с кандидатами через Postgres pg_trgm
   (similarity() / % оператор) по item_name/supplier — быстро, без
   RU-лемматизации, без отдельного BM25-индекса на диске.
3. Если pg_trgm не дал кандидатов — полный список сущностей передаётся в
   промпт Classifier/Planner, и LLM сам сопоставляет вопрос с сущностями.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db.database import async_session_maker
from src.core.logging_settings import logger

# Верхний предел кандидатов, отдаваемых в Planner/CodeGen
DEFAULT_TOP_N = 10

# Порог pg_trgm similarity (0..1). Снижен для устойчивости к опечаткам.
TRIGRAM_THRESHOLD = 0.25

# Сколько уникальных сущностей отдавать в промпт, если pg_trgm не помог.
MAX_ENTITIES_FOR_PROMPT = 200


@dataclass
class EntityCandidate:
    entity_type: str          # item | supplier | period
    entity_value: str
    score: float
    method: str               # trigram

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_type": self.entity_type,
            "entity_value": self.entity_value,
            "score": round(self.score, 4),
            "method": self.method,
        }


class EntityResolver:
    """Резолвит вопрос к списку сущностей mart.price_facts через pg_trgm."""

    def __init__(self) -> None:
        self._entity_cache: Dict[str, List[str]] = {}
        self._cache_loaded = False

    # ------------------------------------------------------------------
    # Ingestion: извлечение списка сущностей (без эмбеддинга)
    # ------------------------------------------------------------------
    async def index_entities(
        self,
        items: List[str],
        suppliers: List[str],
        periods: List[str],
        session: Optional[AsyncSession] = None,
    ) -> Dict[str, int]:
        """Сохраняет уникальные сущности в in-memory-кэш.

        Ничего не эмбеддит. Вместо этого список сущностей читается на рантайме
        из mart.price_facts (см. resolve_candidates), а здесь только заполняем
        кэш уникальными значениями, чтобы отдавать их в промпт.
        """
        self._entity_cache["item"] = _unique(items)
        self._entity_cache["supplier"] = _unique(suppliers)
        self._entity_cache["period"] = _unique(periods)
        self._cache_loaded = True

        counts = {k: len(v) for k, v in self._entity_cache.items()}
        logger.info(
            "Entity catalog indexed (no embeddings): item={}, supplier={}, period={}",
            counts.get("item", 0),
            counts.get("supplier", 0),
            counts.get("period", 0),
        )
        return counts

    # ------------------------------------------------------------------
    # Runtime: поиск кандидатов через pg_trgm
    # ------------------------------------------------------------------
    async def resolve_candidates(
        self,
        query: str,
        top_n: int = DEFAULT_TOP_N,
        session: Optional[AsyncSession] = None,
    ) -> List[EntityCandidate]:
        """Находит top-N похожих item_name/supplier через pg_trgm.

        Выполняет SQL с similarity() по mart.price_facts.item_name и .supplier.
        Это быстрее векторного поиска и не требует эмбеддинг-модели.
        """
        if not query.strip():
            return []

        own_session = session is None
        s = session or async_session_maker()
        try:
            sql = text(
                """
                SELECT 'item' AS entity_type, item_name AS entity_value,
                       similarity(item_name, :q) AS score
                FROM mart.price_facts
                WHERE item_name % :q
                GROUP BY item_name
                UNION ALL
                SELECT 'supplier', supplier,
                       similarity(supplier, :q)
                FROM mart.price_facts
                WHERE supplier % :q
                  AND supplier IS NOT NULL
                GROUP BY supplier
                ORDER BY score DESC
                LIMIT :top_n
                """
            )
            result = await s.execute(sql, {"q": query, "top_n": top_n})
            rows = result.all()
        finally:
            if own_session:
                await s.close()

        candidates = [
            EntityCandidate(
                entity_type=r.entity_type,
                entity_value=r.entity_value,
                score=float(r.score or 0.0),
                method="trigram",
            )
            for r in rows
        ]
        return candidates[:top_n]

    # ------------------------------------------------------------------
    # Список сущностей для промпта (fallback, если pg_trgm пуст)
    # ------------------------------------------------------------------
    def entities_for_prompt(self) -> Dict[str, List[str]]:
        """Возвращает сущности для передачи в системный промпт Classifier/Planner."""
        if not self._cache_loaded:
            return {}
        return {
            "item_name": self._entity_cache.get("item", [])[:MAX_ENTITIES_FOR_PROMPT],
            "supplier": self._entity_cache.get("supplier", [])[:MAX_ENTITIES_FOR_PROMPT],
            "sheet_period": self._entity_cache.get("period", [])[:MAX_ENTITIES_FOR_PROMPT],
        }


def _unique(values: List[str]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for v in values:
        key = str(v).strip()
        if key and key not in seen:
            seen.add(key)
            out.append(key)
    return out


# Singleton
entity_resolver: EntityResolver = EntityResolver()