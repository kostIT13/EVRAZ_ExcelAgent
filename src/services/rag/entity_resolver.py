"""Entity Resolution Service — резолвит названия лома в канонические сущности.

Использует:
1. Точное совпадение (после нормализации)
2. Нечёткое совпадение (Levenshtein distance)
3. Embedding similarity (для семантически похожих названий)
4. LLM-подтверждение для новых сущностей (при заливке, не в рантайме)
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db.database import async_session_maker
from src.core.db.models import EntityDictionary
from src.core.logging_settings import logger
from src.services.llm.llm_client import LLMClient
from src.services.rag.embedder import Embedder


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

    def __init__(self, llm: Optional[LLMClient] = None):
        self._llm = llm or LLMClient()
        self._embedder = Embedder(self._llm)
        self._cache: Dict[str, Optional[int]] = {}  # normalized_name → entity_id

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
                return cached_id, await self._get_canonical_name(cached_id, session)
            return None, normalized

        # 2. Ищем в БД
        # ВАЖНО: используем session напрямую без async with,
        # чтобы не закрыть переданную извне сессию (SQLAlchemy 2.0 asyncio
        # закрывает сессию при выходе из async with).
        if session is not None:
            s = session
        else:
            s = async_session_maker()
        try:
            entity = await self._find_entity(s, normalized)
            if entity is not None:
                self._cache[normalized] = entity.id
                return entity.id, entity.canonical_name

            # 3. Не найдено — кэшируем как None
            self._cache[normalized] = None
            return None, normalized
        finally:
            # Закрываем только если создали свою сессию
            if session is None:
                await s.close()

    async def resolve_batch(
        self,
        names: List[str],
        session: Optional[AsyncSession] = None,
    ) -> Dict[str, Tuple[Optional[int], str]]:
        """Резолвит список названий лома.

        Returns:
            Dict[исходное_имя → (entity_id, canonical_name)]
        """
        result = {}
        for name in names:
            entity_id, canonical = await self.resolve(name, session)
            result[name] = (entity_id, canonical)
        return result

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

        # ВАЖНО: используем session напрямую без async with,
        # чтобы не закрыть переданную извне сессию.
        if session is not None:
            s = session
        else:
            s = async_session_maker()
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
            if session is None:
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

        # ВАЖНО: используем session напрямую без async with,
        # чтобы не закрыть переданную извне сессию.
        if session is not None:
            s = session
        else:
            s = async_session_maker()
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
                        from src.services.rag.embedder import cosine_similarity
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
            if session is None:
                await s.close()

    async def _find_entity(
        self,
        session: AsyncSession,
        normalized_name: str,
    ) -> Optional[EntityDictionary]:
        """Ищет сущность в БД по нормализованному имени."""
        # 1. Точное совпадение по canonical_name
        result = await session.execute(
            select(EntityDictionary).where(
                EntityDictionary.canonical_name == normalized_name
            )
        )
        entity = result.scalar_one_or_none()
        if entity is not None:
            return entity

        # 2. Поиск по алиасам (JSON содержит список)
        all_entities = await session.execute(select(EntityDictionary))
        for entity in all_entities.scalars().all():
            if entity.aliases and normalized_name in entity.aliases:
                return entity

        # 3. Fuzzy match по canonical_name
        all_entities = await session.execute(select(EntityDictionary))
        best_match = None
        best_score = 0.0
        for entity in all_entities.scalars().all():
            sim = levenshtein_similarity(normalized_name, entity.canonical_name)
            if sim > best_score:
                best_score = sim
                best_match = entity
            # Проверяем алиасы
            for alias in (entity.aliases or []):
                sim = levenshtein_similarity(normalized_name, alias)
                if sim > best_score:
                    best_score = sim
                    best_match = entity

        if best_score >= FUZZY_THRESHOLD:
            return best_match

        return None

    async def _get_canonical_name(
        self,
        entity_id: int,
        session: Optional[AsyncSession] = None,
    ) -> str:
        """Получает каноническое имя по ID сущности."""
        if session is not None:
            s = session
        else:
            s = async_session_maker()
        try:
            result = await s.execute(
                select(EntityDictionary).where(EntityDictionary.id == entity_id)
            )
            entity = result.scalar_one_or_none()
            return entity.canonical_name if entity else "unknown"
        finally:
            if session is None:
                await s.close()


# Singleton
entity_resolver: EntityResolver = EntityResolver()