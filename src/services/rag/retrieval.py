from __future__ import annotations
from typing import List, Optional
from src.core.logging_settings import logger
from src.core.qdrant.client import QdrantVectorStore, qdrant_client
from src.services.rag.embedder import Embedder
from src.services.rag.sparse import SparseEmbedder, sparse_embedder


class DenseSearchResult:
    __slots__ = ("chunk", "score", "source_type", "source_id", "rank")

    def __init__(
        self,
        chunk: str,
        score: float,
        source_type: str,
        source_id: int,
        rank: int,
    ) -> None:
        self.chunk = chunk
        self.score = score
        self.source_type = source_type
        self.source_id = source_id
        self.rank = rank

    def to_dict(self) -> dict:
        return {
            "chunk": self.chunk,
            "score": self.score,
            "source_type": self.source_type,
            "source_id": self.source_id,
            "rank": self.rank,
        }


class DenseRetriever:
    """Dense-ретривер поверх Qdrant.

    Выполняет поиск по dense-векторам в Qdrant. Sparse-поиск и гибридное
    слияние выполняются в Qdrant одним запросом (см. RagService.hybrid_search).
    """

    def __init__(
        self,
        embedder: Embedder,
        store: Optional[QdrantVectorStore] = None,
        sparse: Optional[SparseEmbedder] = None,
    ) -> None:
        self._embedder = embedder
        self._store = store or qdrant_client
        self._sparse = sparse or sparse_embedder

    async def search(
        self,
        query: str,
        top_k: int = 10,
    ) -> List[DenseSearchResult]:
        """Dense-only поиск по всем типам источников."""
        query_vector = await self._embedder.embed(query, is_query=True)

        # Запрашиваем больше результатов из каждого источника,
        # чтобы после дедупликации гарантированно получить top_k уникальных
        inner_limit = max(top_k * 3, 30)

        results: List[DenseSearchResult] = []
        for source_type in ("chunk", "sheet", "column", "comment"):
            try:
                hits = await self._store.dense_search(
                    query_vector,
                    top_k=inner_limit,
                    source_type=source_type,
                )
                for hit in hits:
                    payload = hit["payload"]
                    results.append(
                        DenseSearchResult(
                            chunk=payload.get("text", ""),
                            score=hit["score"],
                            source_type=source_type,
                            source_id=int(payload.get("source_id", 0)),
                            rank=0,
                        )
                    )
            except Exception as exc:
                logger.warning("Dense search failed for source_type={}: {}", source_type, exc)

        # Дедупликация по (source_type, source_id): оставляем запись с макс. score
        seen: dict[tuple[str, int], DenseSearchResult] = {}
        for r in results:
            key = (r.source_type, r.source_id)
            if key not in seen or r.score > seen[key].score:
                seen[key] = r

        merged = list(seen.values())
        merged.sort(key=lambda r: r.score, reverse=True)

        for rank, result in enumerate(merged[:top_k], start=1):
            result.rank = rank

        return merged[:top_k]

    async def search_sheets(
        self,
        query: str,
        top_k: int = 10,
    ) -> List[DenseSearchResult]:
        query_vector = await self._embedder.embed(query, is_query=True)
        return await self._search_source(query_vector, "sheet", top_k)

    async def search_columns(
        self,
        query: str,
        top_k: int = 10,
    ) -> List[DenseSearchResult]:
        query_vector = await self._embedder.embed(query, is_query=True)
        return await self._search_source(query_vector, "column", top_k)

    async def _search_source(
        self,
        query_vector: List[float],
        source_type: str,
        top_k: int,
    ) -> List[DenseSearchResult]:
        try:
            hits = await self._store.dense_search(
                query_vector,
                top_k=top_k,
                source_type=source_type,
            )
        except Exception as exc:
            logger.warning("Dense search failed for source_type={}: {}", source_type, exc)
            return []

        results: List[DenseSearchResult] = []
        for rank, hit in enumerate(hits, start=1):
            payload = hit["payload"]
            results.append(
                DenseSearchResult(
                    chunk=payload.get("text", ""),
                    score=hit["score"],
                    source_type=source_type,
                    source_id=int(payload.get("source_id", 0)),
                    rank=rank,
                )
            )
        return results