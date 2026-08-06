"""Sparse-векторный генератор на базе fastembed (BM25 / SPLADE).

Qdrant умеет хранить sparse-вектора и выполнять по ним поиск.
Это заменяет собственную реализацию BM25-индекса (rank-bm25 + pickle).
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

from loguru import logger

from src.core.config import settings


def _tokenize(text: str) -> List[str]:
    """Токенизация для BM25-подобного sparse-вектора."""
    text = text.lower()
    tokens = re.findall(r"\w+", text, re.UNICODE)
    return [t for t in tokens if len(t) > 1]


def build_sparse_vector(text: str) -> Dict[str, List[float]]:
    """Строит sparse-вектор (BM25-подобный) из текста.

    Возвращает {"indices": [...], "values": [...]} — формат Qdrant SparseVector.
    Используем TF (term frequency) как значение, индекс — хэш токена.
    """
    tokens = _tokenize(text)
    if not tokens:
        return {"indices": [], "values": []}

    # Считаем частоту терминов
    freq: Dict[str, int] = {}
    for tok in tokens:
        freq[tok] = freq.get(tok, 0) + 1

    # Хэшируем токены в стабильные индексы (0..2^31-1)
    indices: List[int] = []
    values: List[float] = []
    for tok, count in freq.items():
        idx = _stable_hash(tok)
        indices.append(idx)
        # Нормализованная частота (логарифмическая) — устойчивее к длинным текстам
        values.append(1.0 + (count - 1) * 0.5)

    return {"indices": indices, "values": values}


def _stable_hash(token: str) -> int:
    """Стабильный хэш токена в диапазоне [0, 2^31)."""
    h = 0
    for ch in token:
        h = (h * 31 + ord(ch)) & 0x7FFFFFFF
    return h


class SparseEmbedder:
    """Генератор sparse-векторов.

    В реальном продакшене здесь можно использовать SPLADE (через fastembed),
    но для локального запуска без скачивания больших моделей используем
    лёгкий BM25-подобный подход на основе TF.
    """

    def __init__(self, model_name: Optional[str] = None) -> None:
        self._model_name = model_name or settings.QDRANT_SPARSE_MODEL
        self._fastembed = None

    def _lazy_init_fastembed(self) -> None:
        """Лениво инициализирует fastembed SPLADE-модель (если доступна)."""
        if self._fastembed is not None:
            return
        try:
            from fastembed import SparseTextEmbedding

            self._fastembed = SparseTextEmbedding(self._model_name)
            logger.info("SparseTextEmbedding '{}' loaded", self._model_name)
        except Exception as exc:
            logger.warning(
                "fastembed SparseTextEmbedding unavailable ({}); "
                "falling back to TF-based sparse vectors",
                exc,
            )
            self._fastembed = None

    def embed(self, text: str) -> Dict[str, List[float]]:
        """Возвращает sparse-вектор для текста."""
        self._lazy_init_fastembed()
        if self._fastembed is not None:
            try:
                result = list(self._fastembed.embed([text]))[0]
                return {
                    "indices": [int(i) for i in result.indices],
                    "values": [float(v) for v in result.values],
                }
            except Exception as exc:
                logger.warning("fastembed sparse embed failed ({}); using TF fallback", exc)

        return build_sparse_vector(text)

    def embed_batch(self, texts: List[str]) -> List[Dict[str, List[float]]]:
        return [self.embed(t) for t in texts]


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
sparse_embedder: SparseEmbedder = SparseEmbedder()