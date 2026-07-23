from __future__ import annotations
from typing import List, Optional, Literal
from loguru import logger
from src.services.rag.bm25 import BM25Index
from src.services.rag.retrieval import DenseRetriever, DenseSearchResult


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


def _rrf_score(rank: int, k: int = 60) -> float:
    return 1.0 / (k + rank)


def _linear_score(
    bm25_score: float,
    dense_score: float,
    alpha: float = 0.3,
) -> float:
    return alpha * bm25_score + (1.0 - alpha) * dense_score


class HybridRetriever:
    def __init__(
        self,
        bm25_index: BM25Index,
        dense_retriever: DenseRetriever,
        fusion: Literal["rrf", "linear"] = "rrf",
        alpha: float = 0.3,
        rrf_k: int = 60,
    ) -> None:
        self._bm25 = bm25_index
        self._dense = dense_retriever
        self._fusion = fusion
        self._alpha = alpha
        self._rrf_k = rrf_k

    async def search(
        self,
        query: str,
        top_k: int = 10,
    ) -> List[HybridSearchResult]:
        bm25_results = self._bm25.search(query, top_k=top_k)
        logger.debug(
            "BM25 returned {} results for query '{}'",
            len(bm25_results),
            query[:60],
        )

        dense_results: List[DenseSearchResult] = await self._dense.search(
            query, top_k=top_k
        )
        logger.debug(
            "Dense returned {} results for query '{}'",
            len(dense_results),
            query[:60],
        )

        if self._fusion == "rrf":
            fused = self._fuse_rrf(bm25_results, dense_results)
        else:
            fused = self._fuse_linear(bm25_results, dense_results)

        fused.sort(key=lambda r: r.score, reverse=True)
        for rank, result in enumerate(fused[:top_k], start=1):
            result.rank = rank

        logger.debug(
            "Hybrid search returned {} results for query '{}'",
            len(fused[:top_k]),
            query[:60],
        )
        return fused[:top_k]

    def _fuse_rrf(
        self,
        bm25_results: List[dict],
        dense_results: List[DenseSearchResult],
    ) -> List[HybridSearchResult]:
        # Строим lookup для dense-результатов по тексту чанка,
        # чтобы нормализовать source_type/source_id из BM25
        dense_by_text: dict[str, DenseSearchResult] = {}
        for r in dense_results:
            dense_by_text[r.chunk] = r

        # Dedup key: используем (source_type, source_id) из dense если доступно,
        # иначе fallback на текст чанка.
        score_map: dict[tuple, dict] = {}

        for rank, item in enumerate(bm25_results, start=1):
            text = item["chunk"]
            rrf = _rrf_score(rank, self._rrf_k)

            # Пытаемся найти соответствующий dense-результат по тексту
            dense_match = dense_by_text.get(text)
            if dense_match is not None:
                stype = dense_match.source_type
                sid = dense_match.source_id
            else:
                stype = item.get("source_type", "unknown")
                sid = item.get("source_id", 0)

            key = (stype, sid) if sid else ("__bm25_text__", hash(text))
            if key not in score_map:
                score_map[key] = {
                    "chunk": text,
                    "score": 0.0,
                    "bm25_score": 0.0,
                    "dense_score": 0.0,
                    "source_type": stype,
                    "source_id": sid,
                }
            score_map[key]["score"] += rrf
            score_map[key]["bm25_score"] = item["score"]

        for rank, item in enumerate(dense_results, start=1):
            text = item.chunk
            rrf = _rrf_score(rank, self._rrf_k)
            key = (item.source_type, item.source_id)
            if key not in score_map:
                score_map[key] = {
                    "chunk": text,
                    "score": 0.0,
                    "bm25_score": 0.0,
                    "dense_score": 0.0,
                    "source_type": item.source_type,
                    "source_id": item.source_id,
                }
            score_map[key]["score"] += rrf
            score_map[key]["dense_score"] = item.score
            # Keep the dense chunk text (richer) when both sources exist
            score_map[key]["chunk"] = text

        return [
            HybridSearchResult(**v, rank=0) for v in score_map.values()
        ]

    def _fuse_linear(
        self,
        bm25_results: List[dict],
        dense_results: List[DenseSearchResult],
    ) -> List[HybridSearchResult]:
        bm25_scores = [r["score"] for r in bm25_results]
        bm25_norm = _min_max_normalise(bm25_scores) if bm25_scores else []

        dense_scores = [r.score for r in dense_results]
        dense_norm = _min_max_normalise(dense_scores) if dense_scores else []

        dense_lookup: dict[str, float] = {}
        dense_meta: dict[str, tuple[str, int]] = {}
        for item, norm_score in zip(dense_results, dense_norm):
            dense_lookup[item.chunk] = norm_score
            dense_meta[item.chunk] = (item.source_type, item.source_id)

        fused: list[HybridSearchResult] = []
        seen: set[str] = set()

        for item, norm_bm25 in zip(bm25_results, bm25_norm):
            text = item["chunk"]
            norm_dense = dense_lookup.get(text, 0.0)
            combined = _linear_score(norm_bm25, norm_dense, self._alpha)
            st, sid = dense_meta.get(text, ("unknown", 0))
            fused.append(
                HybridSearchResult(
                    chunk=text,
                    score=combined,
                    bm25_score=item["score"],
                    dense_score=dense_lookup.get(text, 0.0),
                    rank=0,
                    source_type=st,
                    source_id=sid,
                )
            )
            seen.add(text)

        for item, norm_dense in zip(dense_results, dense_norm):
            if item.chunk not in seen:
                combined = _linear_score(0.0, norm_dense, self._alpha)
                fused.append(
                    HybridSearchResult(
                        chunk=item.chunk,
                        score=combined,
                        bm25_score=0.0,
                        dense_score=item.score,
                        rank=0,
                        source_type=item.source_type,
                        source_id=item.source_id,
                    )
                )

        return fused


def _min_max_normalise(values: List[float]) -> List[float]:
    if not values:
        return []
    mn, mx = min(values), max(values)
    if mx == mn:
        return [0.5] * len(values)
    return [(v - mn) / (mx - mn) for v in values]