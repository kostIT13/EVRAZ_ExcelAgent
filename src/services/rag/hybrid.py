from __future__ import annotations
from typing import List, Optional
from loguru import logger
from src.core.qdrant.client import QdrantVectorStore, qdrant_client
from src.services.rag.embedder import Embedder
from src.services.rag.sparse import SparseEmbedder, sparse_embedder
from src.services.rag.reranker import Reranker, reranker


class HybridSearchResult:
    __slots__ = ("chunk", "score", "bm25_score", "dense_score", "rank", "source_type", "source_id")

    def __init__(
        self,
        chunk: str,
        score: float,
        bm25_score: float,
        dense_score: float,
        rank: int,
        source_type: str = "unknown",
        source_id: int = 0,
    ) -> None:
        self.chunk = chunk
        self.score = score
        self.bm25_score = bm25_score
        self.dense_score = dense_score
        self.rank = rank
        self.source_type = source_type
        self.source_id = source_id

    def to_dict(self) -> dict:
        return {
            "chunk": self.chunk,
            "score": self.score,
            "bm25_score": self.bm25_score,
            "dense_score": self.dense_score,
            "rank": self.rank,
            "source_type": self.source_type,
            "source_id": self.source_id,
        }


class HybridRetriever:
    """Гибридный ретривер поверх Qdrant.

    Выполняет dense + sparse поиск одним запросом к Qdrant с RRF-слиянием
    (Reciprocal Rank Fusion), затем опционально реранкит результаты.
    """

    def __init__(
        self,
        embedder: Embedder,
        store: Optional[QdrantVectorStore] = None,
        sparse: Optional[SparseEmbedder] = None,
        rerank: Optional[Reranker] = None,
    ) -> None:
        self._embedder = embedder
        self._store = store or qdrant_client
        self._sparse = sparse or sparse_embedder
        self._reranker = rerank or reranker

    async def search(
        self,
        query: str,
        top_k: int = 10,
    ) -> List[HybridSearchResult]:
        # Dense-вектор запроса
        dense_vector = await self._embedder.embed(query)
        # Sparse-вектор запроса
        sparse_vector = self._sparse.embed(query)

        # Гибридный поиск одним запросом к Qdrant (RRF-слияние)
        hits = await self._store.hybrid_search(
            dense_vector=dense_vector,
            sparse_vector=sparse_vector,
            top_k=top_k,
        )

        results: List[HybridSearchResult] = []
        for rank, hit in enumerate(hits, start=1):
            payload = hit["payload"]
            results.append(
                HybridSearchResult(
                    chunk=payload.get("text", ""),
                    score=hit["score"],
                    bm25_score=payload.get("sparse_score", 0.0),
                    dense_score=payload.get("dense_score", 0.0),
                    rank=rank,
                    source_type=payload.get("source_type", "unknown"),
                    source_id=int(payload.get("source_id", 0)),
                )
            )

        # Реранкинг
        if self._reranker.enabled and results:
            docs = [
                {"text": r.chunk, "result": r}
                for r in results
            ]
            reranked = self._reranker.rerank(query, docs, top_k=top_k)
            results = [d["result"] for d in reranked]
            for rank, r in enumerate(results, start=1):
                r.rank = rank

        logger.debug(
            "Hybrid search returned {} results for query '{}'",
            len(results),
            query[:60],
        )
        return results