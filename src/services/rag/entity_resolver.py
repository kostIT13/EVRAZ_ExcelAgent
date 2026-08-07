"""Entity Resolution Service — резолвит названия лома в канонические сущности.

Использует:
1. Точное совпадение (после нормализации)
2. Нечёткое совпадение (Levenshtein distance)
3. Embedding similarity (для семантически похожих названий)
4. LLM-подтверждение для новых сущностей (при заливке, не в рантайме)
"""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional, Tuple

from rapidfuzz import fuzz, process as rapidfuzz_process
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db.database import async_session_maker
from src.core.db.models import EntityDictionary
from src.core.logging_settings import logger
from src.services.llm.llm_client import LLMClient
from src.services.rag.embedder import Embedder, cosine_similarity


# Порог для fuzzy matching
FUZZY_THRESHOLD = 0.85


def normalize_name(name: str) -> str:
    """Максимально нормализует название для сравнения."""
    if not name:
        return ""
    name = name.lower().strip()
    name = re.sub(r'\s+', ' ', name)
    name = re.sub(r'[^\w\sа-яёa-z]', '', name)
    name = name.strip()
    return name


def levenshtein_similarity(a: str, b: str) -> float:
    """Вычисляет схожесть строк через Levenshtein distance (нормализованную)."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0

    a, b = a.lower(), b.lower()
    n, m = len(a), len(b)
    if n > m:
        a, b = b, a
        n, m = m, n

    current = list(range(n + 1))
    for i in range(1, m + 1):
        previous, current = current, [i] + [0] * n
        for j in range(1, n + 1):
            add = previous[j] + 1
            delete = current[j - 1] + 1
            change = previous[j - 1]
            if a[j - 1] != b[i - 1]:
                change += 1
            current[j] = min(add, delete, change)

    distance = current[n]
    max_len = max(n, m)
    if max_len == 0:
        return 1.0
    return 1.0 - (distance / max_len)


class EntityResolver:
    """Резолвит названия лома в канонические сущности."""

    # TTL кэша списка сущностей справочника. Внутри одного resolve_batch справочник
    # загружается один раз и не перезапрашивается при каждом имени.
    DICT_CACHE_TTL_SECONDS = 300.0

    def __init__(self, llm: Optional[LLMClient] = None):
        self._llm = llm or LLMClient()
        self._embedder = Embedder()
        self._cache: Dict[str, Optional[int]] = {}  # normalized_name → entity_id
        self._all_entities: List[EntityDictionary] = []
        self._all_entities_loaded_at: float = 0.0

    async def _load_all_entities(
        self,
        session: AsyncSession,
    ) -> List[EntityDictionary]:
        """Загружает весь справочник в память (с TTL-кэшем).

        Это устраняет главное узкое место: раньше для каждого уникального названия
        выполнялось по два полных `SELECT * FROM entity_dictionary` (поиск по алиасам
        и fuzzy-match), что при сотнях названий и растущем справочнике давало
        O(N × M) запросов и времени. Теперь справочник читается один раз и
        переиспользуется внутри batch (и между batch в пределах TTL).
        """
        now = time.monotonic()
        if self._all_entities and (now - self._all_entities_loaded_at) < self.DICT_CACHE_TTL_SECONDS:
            return self._all_entities

        result = await session.execute(select(EntityDictionary))
        self._all_entities = list(result.scalars().all())
        self._all_entities_loaded_at = now
        return self._all_entities

    async def resolve(
        self,
        item_name: str,
        session: Optional[AsyncSession] = None,
    ) -> Tuple[Optional[int], str]:
        """Резолвит название лома в ID сущности.

        Args:
            item_name: Сырое название лома.
            session: Опциональная сессия БД.

        Returns:
            (entity_id, canonical_name) — ID сущности и каноническое имя.
            Если сущность не найдена, возвращает (None, нормализованное_имя).
        """
        normalized = normalize_name(item_name)
        if not normalized:
            return None, item_name

        # 1. Проверяем кэш
        if normalized in self._cache:
            cached_id = self._cache[normalized]
            if cached_id is not None:
                # Берём каноническое имя из уже загруженного справочника,
                # не делая отдельный SELECT по ID.
                own_session = session is None
                s = session or async_session_maker()
                try:
                    all_entities = await self._load_all_entities(s)
                    entity = self._entity_by_id(all_entities, cached_id)
                    return cached_id, (entity.canonical_name if entity else normalized)
                finally:
                    if own_session:
                        await s.close()
            return None, normalized

        # 2. Ищем в БД. Справочник загружается один раз и кэшируется,
        # поэтому повторные вызовы resolve() не делают полные SELECT *.
        own_session = session is None
        s = session or async_session_maker()
        try:
            all_entities = await self._load_all_entities(s)
            entity = self._find_entity(all_entities, normalized)
            if entity is not None:
                self._cache[normalized] = entity.id
                return entity.id, entity.canonical_name

            # 3. Не найдено — кэшируем как None
            self._cache[normalized] = None
            return None, normalized
        finally:
            # Закрываем только если создали свою сессию
            if own_session:
                await s.close()

    async def resolve_batch(
        self,
        names: List[str],
        session: Optional[AsyncSession] = None,
    ) -> Dict[str, Tuple[Optional[int], str]]:
        """Резолвит список названий лома.

        Справочник загружается в память один раз на весь батч, а не на каждое
        имя (раньше каждое имя делало до двух полных `SELECT * FROM entity_dictionary`).

        Returns:
            Dict[исходное_имя → (entity_id, canonical_name)]
        """
        own_session = session is None
        s = session or async_session_maker()
        try:
            all_entities = await self._load_all_entities(s)
            result = {}
            for name in names:
                normalized = normalize_name(name)
                if not normalized:
                    result[name] = (None, name)
                    continue

                # 1. Проверяем кэш резолва
                if normalized in self._cache:
                    cached_id = self._cache[normalized]
                    if cached_id is not None:
                        entity = self._entity_by_id(all_entities, cached_id)
                        result[name] = (cached_id, entity.canonical_name if entity else normalized)
                    else:
                        result[name] = (None, normalized)
                    continue

                # 2. Ищем в памяти (точное → алиасы → fuzzy)
                entity = self._find_entity(all_entities, normalized)
                if entity is not None:
                    self._cache[normalized] = entity.id
                    result[name] = (entity.id, entity.canonical_name)
                else:
                    self._cache[normalized] = None
                    result[name] = (None, normalized)
            return result
        finally:
            if own_session:
                await s.close()

    async def add_entity(
        self,
        canonical_name: str,
        aliases: Optional[List[str]] = None,
        category: Optional[str] = None,
        description: Optional[str] = None,
        session: Optional[AsyncSession] = None,
    ) -> EntityDictionary:
        """Добавляет новую сущность в справочник.

        Args:
            canonical_name: Каноническое название.
            aliases: Список алиасов (синонимов).
            category: Категория (например, 'цветной_лом', 'черный_лом').
            description: Описание.

        Returns:
            Созданная EntityDictionary.
        """
        normalized_canonical = normalize_name(canonical_name)

        own_session = session is None
        s = session or async_session_maker()
        try:
            # Проверяем, не существует ли уже
            existing = await s.execute(
                select(EntityDictionary).where(
                    EntityDictionary.canonical_name == normalized_canonical
                )
            )
            existing_record = existing.scalar_one_or_none()
            if existing_record:
                # Обновляем алиасы
                if aliases:
                    current_aliases = set(existing_record.aliases or [])
                    current_aliases.update(aliases)
                    existing_record.aliases = list(current_aliases)
                    await s.commit()
                    await s.refresh(existing_record)
                return existing_record

            # Создаём эмбеддинг для канонического имени
            embed_text = f"{canonical_name} {' '.join(aliases or [])}"
            embedding = await self._embedder.embed(embed_text)

            entity = EntityDictionary(
                canonical_name=normalized_canonical,
                aliases=[normalize_name(a) for a in (aliases or [])],
                category=category,
                description=description,
                embedding=embedding,
            )
            s.add(entity)
            await s.commit()
            await s.refresh(entity)

            # Очищаем кэш для всех алиасов
            self._cache[normalized_canonical] = entity.id
            for alias in (aliases or []):
                self._cache[normalize_name(alias)] = entity.id

            logger.info(
                "Added entity: '{}' (id={}, aliases={})",
                canonical_name,
                entity.id,
                aliases,
            )
            return entity
        finally:
            if own_session:
                await s.close()

    async def suggest_entities(
        self,
        names: List[str],
        session: Optional[AsyncSession] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Для списка ненайденных названий предлагает кандидатов из справочника.

        Использует embedding similarity для поиска похожих сущностей.

        Returns:
            Dict[исходное_имя → [{"entity_id": ..., "canonical_name": ..., "score": ...}]]
        """
        suggestions: Dict[str, List[Dict[str, Any]]] = {}

        own_session = session is None
        s = session or async_session_maker()
        try:
            # Получаем все сущности
            result = await s.execute(select(EntityDictionary))
            all_entities = list(result.scalars().all())

            if not all_entities:
                return {name: [] for name in names}

            for name in names:
                normalized = normalize_name(name)
                if not normalized:
                    suggestions[name] = []
                    continue

                # Сначала fuzzy match
                fuzzy_matches = []
                for entity in all_entities:
                    sim = levenshtein_similarity(normalized, entity.canonical_name)
                    if sim >= FUZZY_THRESHOLD:
                        fuzzy_matches.append({
                            "entity_id": entity.id,
                            "canonical_name": entity.canonical_name,
                            "score": sim,
                            "method": "fuzzy",
                        })
                    else:
                        # Проверяем алиасы
                        for alias in (entity.aliases or []):
                            sim = levenshtein_similarity(normalized, alias)
                            if sim >= FUZZY_THRESHOLD:
                                fuzzy_matches.append({
                                    "entity_id": entity.id,
                                    "canonical_name": entity.canonical_name,
                                    "score": sim,
                                    "method": "alias_fuzzy",
                                })
                                break

                # Если есть fuzzy-совпадения — используем их
                if fuzzy_matches:
                    fuzzy_matches.sort(key=lambda x: x["score"], reverse=True)
                    suggestions[name] = fuzzy_matches[:3]
                    continue

                # Иначе — embedding similarity
                name_embedding = await self._embedder.embed(normalized)
                scored = []
                for entity in all_entities:
                    if entity.embedding:
                        sim = cosine_similarity(name_embedding, entity.embedding)
                        if sim >= 0.7:
                            scored.append({
                                "entity_id": entity.id,
                                "canonical_name": entity.canonical_name,
                                "score": sim,
                                "method": "embedding",
                            })

                scored.sort(key=lambda x: x["score"], reverse=True)
                suggestions[name] = scored[:3]

            return suggestions
        finally:
            if own_session:
                await s.close()

    def _entity_by_id(
        self,
        all_entities: List[EntityDictionary],
        entity_id: int,
    ) -> Optional[EntityDictionary]:
        """Возвращает сущность по ID из уже загруженного в память справочника."""
        for entity in all_entities:
            if entity.id == entity_id:
                return entity
        return None

    @staticmethod
    def _fuzzy_best(
        candidates: List[Tuple[str, EntityDictionary]],
        normalized_name: str,
    ) -> Optional[EntityDictionary]:
        """Ищет лучшее fuzzy-совпадение через rapidfuzz (на порядки быстрее Python).

        Использует C-реализацию rapidfuzz вместо чистого Python-Levenshtein,
        который ранее выполнял сравнение для каждой сущности и каждого алиаса.
        """
        if not candidates:
            return None

        # extractOne ожидает плоский список строк. Кандидаты у нас — кортежи
        # (строка, entity), поэтому передаём только строки, а entity достаём
        # по индексу из исходного списка.
        strings = [c[0] for c in candidates]
        best, score, index = rapidfuzz_process.extractOne(
            normalized_name,
            strings,
            scorer=fuzz.ratio,
            processor=None,
        )
        if score / 100.0 >= FUZZY_THRESHOLD:
            return candidates[index][1]
        return None

    def _find_entity(
        self,
        all_entities: List[EntityDictionary],
        normalized_name: str,
    ) -> Optional[EntityDictionary]:
        """Ищет сущность в уже загруженном справочнике по нормализованному имени.

        Все операции выполняются в памяти над одним списком сущностей (без
        повторных SELECT * в БД на каждое имя):
        1. Точное совпадение по canonical_name.
        2. Точное совпадение по алиасам.
        3. Fuzzy-match по canonical_name и алиасам через rapidfuzz.
        """
        # 1. Точное совпадение по canonical_name
        for entity in all_entities:
            if entity.canonical_name == normalized_name:
                return entity

        # 2. Точное совпадение по алиасам
        alias_hits = []
        for entity in all_entities:
            if entity.aliases and normalized_name in entity.aliases:
                return entity
            if entity.aliases:
                alias_hits.extend((alias, entity) for alias in entity.aliases)

        # 3. Fuzzy match (canonical_name, затем алиасы)
        canonical_candidates = [
            (entity.canonical_name, entity) for entity in all_entities
        ]
        best = self._fuzzy_best(canonical_candidates, normalized_name)
        if best is not None:
            return best

        if alias_hits:
            best = self._fuzzy_best(alias_hits, normalized_name)
            if best is not None:
                return best

        return None

    async def _get_canonical_name(
        self,
        entity_id: int,
        session: Optional[AsyncSession] = None,
    ) -> str:
        """Получает каноническое имя по ID сущности."""
        own_session = session is None
        s = session or async_session_maker()
        try:
            result = await s.execute(
                select(EntityDictionary).where(EntityDictionary.id == entity_id)
            )
            entity = result.scalar_one_or_none()
            return entity.canonical_name if entity else "unknown"
        finally:
            if own_session:
                await s.close()


# Singleton
entity_resolver: EntityResolver = EntityResolver()