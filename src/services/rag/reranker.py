"""Реранкер на базе flashrank.

Переупорядочивает результаты гибридного поиска по релевантности
с помощью кросс-энкодерной модели (ms-marco-MiniLM-L-12-v2).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from loguru import logger

from src.core.config import settings


class Reranker:
    """Обёртка над flashrank.RerankRequest."""

    def __init__(
        self,
        model_name: Optional[str] = None,
        enabled: Optional[bool] = None,
    ) -> None:
        self._model_name = model_name or settings.RERANKER_MODEL
        self._enabled = enabled if enabled is not None else settings.RERANKER_ENABLED
        self._ranker = None

    def _lazy_init(self) -> None:
        if self._ranker is not None:
            return
        try:
            from flashrank import Ranker

            self._ranker = Ranker(model_name=self._model_name)
            logger.info("Reranker '{}' loaded", self._model_name)
        except Exception as exc:
            logger.warning(
                "flashrank Ranker unavailable ({}); reranking disabled", exc
            )
            self._ranker = None

    @property
    def enabled(self) -> bool:
        return self._enabled and self._ranker is not None

    def rerank(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        top_k: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Переупорядочивает документы по релевантности к запросу.

        Args:
            query: Запрос пользователя.
            documents: Список dict с ключом "text" (и любыми метаданными).
            top_k: Сколько результатов вернуть после реранкинга.

        Returns:
            Тот же список документов, но переупорядоченный, с добавленным
            полем "rerank_score".
        """
        if not documents:
            return []

        self._lazy_init()
        if self._ranker is None:
            # Реранкер недоступен — возвращаем как есть
            return documents

        top_k = top_k or settings.RERANKER_TOP_K

        try:
            from flashrank import RerankRequest

            passages = [
                {"id": str(i), "text": doc.get("text", "")}
                for i, doc in enumerate(documents)
            ]
            request = RerankRequest(query=query, passages=passages)
            ranked = self._ranker.rerank(request)

            # Сопоставляем обратно с исходными документами
            result: List[Dict[str, Any]] = []
            for item in ranked[:top_k]:
                idx = int(item["id"])
                doc = dict(documents[idx])
                doc["rerank_score"] = float(item["score"])
                result.append(doc)
            return result
        except Exception as exc:
            logger.warning("Reranking failed ({}); returning original order", exc)
            return documents


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
reranker: Reranker = Reranker()