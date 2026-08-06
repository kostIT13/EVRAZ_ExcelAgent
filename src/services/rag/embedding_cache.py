"""Абстрактный кэш эмбеддингов.

Embedder не должен знать про конкретное хранилище (Postgres, Redis, память).
Он работает через этот интерфейс, что позволяет подменять реализацию.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List, Optional


class EmbeddingCache(ABC):
    """Интерфейс кэша эмбеддингов."""

    @abstractmethod
    async def get(self, text_hash: str) -> Optional[List[float]]:
        """Возвращает эмбеддинг по хэшу текста или None."""

    @abstractmethod
    async def set(self, text_hash: str, text: str, vector: List[float], model_name: str) -> None:
        """Сохраняет эмбеддинг в кэш."""


class InMemoryEmbeddingCache(EmbeddingCache):
    """Простой in-memory кэш (для тестов и локальной разработки)."""

    def __init__(self, max_entries: int = 10000) -> None:
        self._store: Dict[str, List[float]] = {}
        self._max_entries = max_entries

    async def get(self, text_hash: str) -> Optional[List[float]]:
        return self._store.get(text_hash)

    async def set(self, text_hash: str, text: str, vector: List[float], model_name: str) -> None:
        if len(self._store) >= self._max_entries:
            # Простая эвакуация: очищаем половину
            keys = list(self._store.keys())
            for k in keys[: len(keys) // 2]:
                del self._store[k]
        self._store[text_hash] = vector