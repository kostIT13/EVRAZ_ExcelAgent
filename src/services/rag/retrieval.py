from __future__ import annotations
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.db.database import async_session_maker
from src.core.db.vector_models import ChunkEmbedding, ColumnEmbedding, SheetEmbedding
from src.core.logging_settings import logger
from src.services.rag.embedder import Embedder


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
    def __init__(self, embedder: Embedder) -> None:
        self._embedder = embedder

    async def search(
        self,
        query: str,
        top_k: int = 10,
        session: Optional[AsyncSession] = None,
    ) -> List[DenseSearchResult]:
        query_vector = await self._embedder.embed(query)

        # Запрашиваем больше результатов из каждого источника,
        # чтобы после слияния и дедупликации гарантированно получить top_k уникальных
        inner_limit = max(top_k * 3, 30)

        # Ищем сначала по чанкам (наиболее точный поиск по строкам данных)
        chunk_results = await self._search_chunk_embeddings(
            query_vector, inner_limit, session
        )
        # Затем по листам (fallback — общий контекст листа)
        sheet_results = await self._search_sheet_embeddings(
            query_vector, inner_limit, session
        )
        column_results = await self._search_column_embeddings(
            query_vector, inner_limit, session
        )

        # Дедупликация по (source_type, source_id): оставляем запись с макс. score
        seen: dict[tuple[str, int], DenseSearchResult] = {}
        for r in chunk_results + sheet_results + column_results:
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
        session: Optional[AsyncSession] = None,
    ) -> List[DenseSearchResult]:
        query_vector = await self._embedder.embed(query)
        return await self._search_sheet_embeddings(query_vector, top_k, session)

    async def search_columns(
        self,
        query: str,
        top_k: int = 10,
        session: Optional[AsyncSession] = None,
    ) -> List[DenseSearchResult]:
        query_vector = await self._embedder.embed(query)
        return await self._search_column_embeddings(query_vector, top_k, session)

    async def _search_chunk_embeddings(
        self,
        query_vector: List[float],
        top_k: int,
        session: Optional[AsyncSession],
    ) -> List[DenseSearchResult]:
        """Поиск по отдельным чанкам (строкам данных) — наиболее точный."""
        async with session or async_session_maker() as s:
            stmt = (
                select(
                    ChunkEmbedding.source_text,
                    ChunkEmbedding.sheet_id,
                    (1 - ChunkEmbedding.embedding.cosine_distance(query_vector)).label(
                        "score"
                    ),
                )
                .order_by(
                    ChunkEmbedding.embedding.cosine_distance(query_vector).asc()
                )
                .limit(top_k)
            )
            rows = await s.execute(stmt)
            results: List[DenseSearchResult] = []
            for rank, row in enumerate(rows, start=1):
                results.append(
                    DenseSearchResult(
                        chunk=row.source_text,
                        score=float(row.score),
                        source_type="chunk",
                        source_id=row.sheet_id,
                        rank=rank,
                    )
                )
            return results

    async def _search_sheet_embeddings(
        self,
        query_vector: List[float],
        top_k: int,
        session: Optional[AsyncSession],
    ) -> List[DenseSearchResult]:
        async with session or async_session_maker() as s:
            stmt = (
                select(
                    SheetEmbedding.source_text,
                    SheetEmbedding.sheet_id,
                    (1 - SheetEmbedding.embedding.cosine_distance(query_vector)).label(
                        "score"
                    ),
                )
                .order_by(
                    SheetEmbedding.embedding.cosine_distance(query_vector).asc()
                )
                .limit(top_k)
            )
            rows = await s.execute(stmt)
            results: List[DenseSearchResult] = []
            for rank, row in enumerate(rows, start=1):
                results.append(
                    DenseSearchResult(
                        chunk=row.source_text,
                        score=float(row.score),
                        source_type="sheet",
                        source_id=row.sheet_id,
                        rank=rank,
                    )
                )
            return results

    async def _search_column_embeddings(
        self,
        query_vector: List[float],
        top_k: int,
        session: Optional[AsyncSession],
    ) -> List[DenseSearchResult]:
        async with session or async_session_maker() as s:
            stmt = (
                select(
                    ColumnEmbedding.source_text,
                    ColumnEmbedding.column_id,
                    (1 - ColumnEmbedding.embedding.cosine_distance(query_vector)).label(
                        "score"
                    ),
                )
                .order_by(
                    ColumnEmbedding.embedding.cosine_distance(query_vector).asc()
                )
                .limit(top_k)
            )
            rows = await s.execute(stmt)
            results: List[DenseSearchResult] = []
            for rank, row in enumerate(rows, start=1):
                results.append(
                    DenseSearchResult(
                        chunk=row.source_text,
                        score=float(row.score),
                        source_type="column",
                        source_id=row.column_id,
                        rank=rank,
                    )
                )
            return results