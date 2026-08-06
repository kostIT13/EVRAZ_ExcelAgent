"""Qdrant vector store client.

Обеспечивает хранение dense- и sparse-векторов в Qdrant и гибридный поиск
(Reciprocal Rank Fusion) одним запросом. Заменяет pgvector + BM25.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qm
from qdrant_client.models import Distance, VectorParams

from src.core.config import settings
from src.core.logging_settings import logger


# Типы источников, которые хранятся в коллекции
SOURCE_TYPES = ("chunk", "sheet", "column", "comment")


class QdrantVectorStore:
    """Тонкая обёртка над AsyncQdrantClient с гибридным поиском."""

    def __init__(
        self,
        url: Optional[str] = None,
        api_key: Optional[str] = None,
        collection: Optional[str] = None,
        dense_dim: Optional[int] = None,
    ) -> None:
        self._url = url or settings.QDRANT_URL
        self._api_key = api_key if api_key is not None else settings.QDRANT_API_KEY
        self._collection = collection or settings.QDRANT_COLLECTION
        self._dense_dim = dense_dim or settings.EMBED_DIMENSION

        self._client = AsyncQdrantClient(
            url=self._url,
            api_key=self._api_key or None,
            timeout=30,
        )

    # ------------------------------------------------------------------
    # Lifecycle / collections
    # ------------------------------------------------------------------
    async def ensure_collection(self) -> None:
        """Создаёт коллекцию с dense + sparse векторами, если её нет."""
        try:
            exists = await self._client.collection_exists(self._collection)
        except Exception as exc:
            logger.error("Qdrant collection_exists failed: {}", exc)
            raise

        if exists:
            logger.debug("Qdrant collection '{}' already exists", self._collection)
            return

        await self._client.create_collection(
            collection_name=self._collection,
            vectors_config={
                "dense": VectorParams(
                    size=self._dense_dim,
                    distance=Distance.COSINE,
                ),
            },
            sparse_vectors_config={
                "sparse": qm.SparseVectorParams(
                    index=qm.SparseIndexParams(
                        on_disk=True,
                    ),
                ),
            },
        )
        logger.info("Qdrant collection '{}' created (dense={}, sparse)", self._collection, self._dense_dim)

    async def delete_collection(self) -> None:
        """Удаляет коллекцию (для полной переиндексации)."""
        await self._client.delete_collection(self._collection)
        logger.info("Qdrant collection '{}' deleted", self._collection)

    async def close(self) -> None:
        await self._client.close()

    # ------------------------------------------------------------------
    # Upsert
    # ------------------------------------------------------------------
    async def upsert(
        self,
        points: List[Dict[str, Any]],
    ) -> None:
        """Вставляет/обновляет точки.

        Каждая точка:
            {
                "id": str,            # уникальный id (например "chunk:1:0")
                "dense": List[float], # dense-вектор
                "sparse": {           # sparse-вектор (опционально)
                    "indices": List[int],
                    "values": List[float],
                },
                "payload": {...},     # source_type, source_id, text, ...
            }
        """
        if not points:
            return

        qdrant_points = []
        for p in points:
            vectors: Dict[str, Any] = {"dense": p["dense"]}
            if p.get("sparse"):
                vectors["sparse"] = qm.SparseVector(
                    indices=p["sparse"]["indices"],
                    values=p["sparse"]["values"],
                )
            qdrant_points.append(
                qm.PointStruct(
                    id=p["id"],
                    vector=vectors,
                    payload=p.get("payload", {}),
                )
            )

        await self._client.upsert(
            collection_name=self._collection,
            points=qdrant_points,
        )

    async def delete_by_filter(self, **payload_filter: Any) -> None:
        """Удаляет точки по точному совпадению payload-полей."""
        conditions = [
            qm.FieldCondition(
                key=k,
                match=qm.MatchValue(value=v),
            )
            for k, v in payload_filter.items()
        ]
        await self._client.delete(
            collection_name=self._collection,
            points_selector=qm.FilterSelector(
                filter=qm.Filter(must=conditions),
            ),
        )

    async def delete_by_ids(self, ids: List[str]) -> None:
        if not ids:
            return
        await self._client.delete(
            collection_name=self._collection,
            points_selector=qm.PointIdsList(point_ids=ids),
        )

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------
    async def hybrid_search(
        self,
        dense_vector: List[float],
        sparse_vector: Optional[Dict[str, List[float]]],
        top_k: int = 10,
        *,
        source_type: Optional[str] = None,
        source_id: Optional[int] = None,
        prefetch_k: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Гибридный поиск (dense + sparse) с RRF-слиянием одним запросом.

        Args:
            dense_vector: Dense-вектор запроса.
            sparse_vector: Sparse-вектор запроса {"indices": [...], "values": [...]}.
            top_k: Сколько результатов вернуть.
            source_type: Фильтр по типу источника (chunk/sheet/column/comment).
            source_id: Фильтр по id источника.
            prefetch_k: Сколько кандидатов запрашивать до слияния (по умолчанию top_k*4).

        Returns:
            Список dict: {"id", "score", "payload"}.
        """
        prefetch_k = prefetch_k or max(top_k * 4, 40)

        prefetch: List[qm.Prefetch] = []
        if dense_vector:
            prefetch.append(
                qm.Prefetch(
                    query=dense_vector,
                    using="dense",
                    limit=prefetch_k,
                )
            )
        if sparse_vector:
            prefetch.append(
                qm.Prefetch(
                    query=qm.SparseVector(
                        indices=sparse_vector["indices"],
                        values=sparse_vector["values"],
                    ),
                    using="sparse",
                    limit=prefetch_k,
                )
            )

        if not prefetch:
            return []

        query_filter = self._build_filter(source_type=source_type, source_id=source_id)

        response = await self._client.query_points(
            collection_name=self._collection,
            prefetch=prefetch,
            query=qm.FusionQuery(fusion=qm.Fusion.RRF),
            limit=top_k,
            with_payload=True,
            query_filter=query_filter,
        )

        results = []
        for point in response.points:
            results.append(
                {
                    "id": point.id,
                    "score": point.score,
                    "payload": point.payload or {},
                }
            )
        return results

    async def dense_search(
        self,
        dense_vector: List[float],
        top_k: int = 10,
        *,
        source_type: Optional[str] = None,
        source_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Только dense-поиск."""
        query_filter = self._build_filter(source_type=source_type, source_id=source_id)
        response = await self._client.query_points(
            collection_name=self._collection,
            query=dense_vector,
            using="dense",
            limit=top_k,
            with_payload=True,
            query_filter=query_filter,
        )
        return [
            {"id": p.id, "score": p.score, "payload": p.payload or {}}
            for p in response.points
        ]

    @staticmethod
    def _build_filter(
        source_type: Optional[str] = None,
        source_id: Optional[int] = None,
    ) -> Optional[qm.Filter]:
        conditions = []
        if source_type:
            conditions.append(
                qm.FieldCondition(key="source_type", match=qm.MatchValue(value=source_type))
            )
        if source_id is not None:
            conditions.append(
                qm.FieldCondition(key="source_id", match=qm.MatchValue(value=source_id))
            )
        if not conditions:
            return None
        return qm.Filter(must=conditions)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
qdrant_client: QdrantVectorStore = QdrantVectorStore()


async def ensure_collections() -> None:
    """Гарантирует наличие коллекции при старте приложения."""
    await qdrant_client.ensure_collection()