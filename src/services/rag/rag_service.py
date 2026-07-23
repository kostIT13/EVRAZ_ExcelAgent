"""
RAG service: orchestrates chunking, embedding, BM25 indexing, and hybrid retrieval.
Provides a high-level API for the generation pipeline and file indexing.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from loguru import logger
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.db.database import async_session_maker
from src.core.db.models import Sheet, ColumnMetadata, Cell
from src.core.db.vector_models import ChunkEmbedding, ColumnEmbedding, SheetEmbedding
from src.services.rag.bm25 import BM25Index
from src.services.rag.chunker import make_chunks
from src.services.rag.embedder import Embedder
from src.services.rag.hybrid import HybridRetriever, HybridSearchResult
from src.services.rag.retrieval import DenseRetriever


# ---------------------------------------------------------------------------
# RAG Service
# ---------------------------------------------------------------------------
class RagService:
    """High-level RAG orchestrator.

    Usage
    -----
    rag = RagService()
    await rag.build_index_for_file(file_id=1)
    results = await rag.hybrid_search("какой-то запрос", top_k=5)
    """

    def __init__(self) -> None:
        self._embedder = Embedder()
        self._dense = DenseRetriever(self._embedder)
        # BM25 index is built lazily; can be persisted to disk
        self._bm25: Optional[BM25Index] = None
        self._bm25_path: Path = Path("data/bm25_index.pkl")
        self._bm25_dirty: bool = False

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------
    async def build_index_for_sheet(
        self,
        sheet_id: int,
        text: str,
        session: Optional[AsyncSession] = None,
    ) -> None:
        """Chunk, embed, and store a sheet's text representation.

        Каждый чанк эмбеддится отдельно для точного dense-поиска.
        Также обновляет BM25 индекс.
        """
        chunks = make_chunks(text, strategy="adaptive")
        logger.info("Sheet {}: split into {} chunks", sheet_id, len(chunks))

        async with session or async_session_maker() as s:
            # --- Dense: удаляем старые чанки и создаём новые ---
            await s.execute(
                delete(ChunkEmbedding).where(ChunkEmbedding.sheet_id == sheet_id)
            )

            for chunk_idx, chunk_text in enumerate(chunks):
                vector = await self._embedder.embed(chunk_text)
                chunk_emb = ChunkEmbedding(
                    sheet_id=sheet_id,
                    chunk_index=chunk_idx,
                    source_text=chunk_text[:2000],
                    embedding=vector,
                    model_name=settings.OLLAMA_EMBED_MODEL,
                )
                s.add(chunk_emb)

            # --- Также сохраняем общий эмбеддинг листа (для fallback) ---
            full_vector = await self._embedder.embed(text)
            existing = await s.execute(
                select(SheetEmbedding).where(SheetEmbedding.sheet_id == sheet_id)
            )
            existing_record = existing.scalar_one_or_none()
            if existing_record:
                existing_record.source_text = text[:2000]
                existing_record.embedding = full_vector
                existing_record.model_name = settings.OLLAMA_EMBED_MODEL
            else:
                s.add(SheetEmbedding(
                    sheet_id=sheet_id,
                    source_text=text[:2000],
                    embedding=full_vector,
                    model_name=settings.OLLAMA_EMBED_MODEL,
                ))

            await s.commit()

        # --- Sparse: update BM25 index ---
        self._lazy_init_bm25()
        if self._bm25 is not None and chunks:
            metadata = [{"source_type": "sheet", "source_id": sheet_id}] * len(chunks)
            self._bm25.add_chunks(chunks, metadata=metadata)
            self._bm25.build()
            self._bm25_dirty = True

        logger.info("Sheet {} indexed: {} chunks (dense) + BM25", sheet_id, len(chunks))

    async def build_index_for_column(
        self,
        column_id: int,
        text: str,
        session: Optional[AsyncSession] = None,
    ) -> None:
        """Embed and store a column's text representation."""
        async with session or async_session_maker() as s:
            # Проверяем существующую запись
            existing = await s.execute(
                select(ColumnEmbedding).where(ColumnEmbedding.column_id == column_id)
            )
            existing_record = existing.scalar_one_or_none()
            
            vector = await self._embedder.embed(text)
            
            if existing_record:
                # Обновляем
                existing_record.source_text = text[:2000]
                existing_record.embedding = vector
                existing_record.model_name = settings.OLLAMA_EMBED_MODEL
                logger.debug("Updated embedding for column {}", column_id)
            else:
                # Создаём
                embedding = ColumnEmbedding(
                    column_id=column_id,
                    source_text=text[:2000],
                    embedding=vector,
                    model_name=settings.OLLAMA_EMBED_MODEL,
                )
                s.add(embedding)
                logger.debug("Created embedding for column {}", column_id)
            
            await s.commit()

        logger.info("Column {} indexed (dense)", column_id)

    async def build_index_for_file(
        self,
        file_id: int,
        session: Optional[AsyncSession] = None,
    ) -> None:
        """Build dense + BM25 index for all sheets and columns of a file.

        Called automatically after file upload.
        """
        async with session or async_session_maker() as s:
            sheets_result = await s.execute(
                select(Sheet).where(Sheet.file_id == file_id)
            )
            sheets = list(sheets_result.scalars().all())

            if not sheets:
                logger.warning("No sheets found for file_id={}", file_id)
                return

            for sheet in sheets:
                # Build text representation and index the sheet
                sheet_text = await self._build_sheet_text(sheet, s)
                if sheet_text:
                    await self.build_index_for_sheet(
                        sheet.id, sheet_text, session=s
                    )

                # Index each column
                cols_result = await s.execute(
                    select(ColumnMetadata)
                    .where(ColumnMetadata.sheet_id == sheet.id)
                    .order_by(ColumnMetadata.col_index)
                )
                for col in cols_result.scalars().all():
                    col_parts = [
                        f"Колонка: {col.normalized_name}",
                        f"тип: {col.data_type}",
                    ]
                    if col.sample_values:
                        col_parts.append(
                            f"примеры: {col.sample_values[:5]}"
                        )
                    col_text = ", ".join(col_parts)
                    await self.build_index_for_column(
                        col.id, col_text, session=s
                    )

            logger.info(
                "File {} fully indexed: {} sheets",
                file_id,
                len(sheets),
            )

    @staticmethod
    async def _build_sheet_text(
        sheet: Sheet,
        session: AsyncSession,
        max_rows: int = 500,
    ) -> str:
        """Build a text representation of a sheet for embedding.

        Includes ALL data rows (up to *max_rows*) with ALL columns,
        so that BM25 and dense search can find any product name or value.
        """
        parts = [
            f"Лист: {sheet.normalized_name}",
            f"строк: {sheet.row_count}",
            f"колонок: {sheet.col_count}",
        ]
        if sheet.description:
            parts.append(f"описание: {sheet.description}")

        # Get column names
        cols_result = await session.execute(
            select(ColumnMetadata)
            .where(ColumnMetadata.sheet_id == sheet.id)
            .order_by(ColumnMetadata.col_index)
        )
        columns = list(cols_result.scalars().all())
        
        # Build col_index → normalized_name mapping
        col_names_map = {}
        if columns:
            col_names = [c.normalized_name for c in columns]
            parts.append(f"колонки: {', '.join(col_names)}")
            for c in columns:
                col_names_map[c.col_index] = c.normalized_name

        # Add ALL data rows with ALL columns
        distinct_rows = (
            await session.execute(
                select(Cell.row_num)
                .where(Cell.sheet_id == sheet.id)
                .distinct()
                .order_by(Cell.row_num)
                .limit(max_rows)
            )
        ).scalars().all()

        if distinct_rows:
            parts.append("данные (все колонки):")
            for row_num in distinct_rows:
                row_cells = (
                    await session.execute(
                        select(Cell)
                        .where(
                            Cell.sheet_id == sheet.id,
                            Cell.row_num == row_num,
                        )
                        .order_by(Cell.col_index)
                    )
                ).scalars().all()

                # Collect all column values for this row
                row_values = []
                for c in row_cells:
                    val = c.value_text or str(c.value_number or "")
                    col_name = col_names_map.get(c.col_index, f"col_{c.col_index}")
                    if val:
                        row_values.append(f"{col_name}: {val}")

                if row_values:
                    parts.append(f"  строка {row_num}: " + " | ".join(row_values))

        return "\n".join(parts)

    async def build_full_index(
        self,
        session: Optional[AsyncSession] = None,
    ) -> None:
        """Rebuild the full BM25 index from all chunk embeddings in the DB."""
        async with session or async_session_maker() as s:
            result = await s.execute(select(ChunkEmbedding))
            records = result.scalars().all()

        chunks = [r.source_text for r in records if r.source_text]
        if chunks:
            # Собираем metadata из записей БД (sheet_id уже есть в ChunkEmbedding)
            metadata = [
                {"source_type": "chunk", "source_id": r.sheet_id}
                for r in records
                if r.source_text
            ]
            self._bm25 = BM25Index(chunks)
            self._bm25._metadata = metadata
            self._bm25.build()
            self._bm25_dirty = True
            logger.info("Full BM25 index rebuilt from {} chunks", len(chunks))
        else:
            logger.warning("No chunks found to build full BM25 index")

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------
    async def hybrid_search(
        self,
        query: str,
        top_k: int = 20,
    ) -> List[HybridSearchResult]:
        """Run hybrid BM25 + Dense search.

        If BM25 index is not built, falls back to dense-only.
        """
        self._lazy_init_bm25()

        if self._bm25 is None or self._bm25.size == 0 or not self._bm25.is_built:
            logger.warning(
                "BM25 index is empty or not built; falling back to dense-only search"
            )
            dense_results = await self._dense.search(query, top_k=top_k)
            return [
                HybridSearchResult(
                    chunk=r.chunk,
                    score=r.score,
                    bm25_score=0.0,
                    dense_score=r.score,
                    rank=r.rank,
                    source_type=r.source_type,
                    source_id=r.source_id,
                )
                for r in dense_results
            ]

        hybrid = HybridRetriever(
            bm25_index=self._bm25,
            dense_retriever=self._dense,
            fusion="rrf",
        )
        return await hybrid.search(query, top_k=top_k)

    async def dense_search(
        self,
        query: str,
        top_k: int = 20,
    ) -> list:
        """Run dense-only search."""
        return await self._dense.search(query, top_k=top_k)

    # ------------------------------------------------------------------
    # BM25 persistence
    # ------------------------------------------------------------------
    def persist_bm25(self) -> None:
        """Save BM25 index to disk if dirty."""
        if self._bm25 is not None and self._bm25_dirty and self._bm25.is_built:
            self._bm25_path.parent.mkdir(parents=True, exist_ok=True)
            self._bm25.save(self._bm25_path)
            self._bm25_dirty = False
            logger.info("BM25 index persisted to disk")
        elif self._bm25_dirty:
            logger.warning("BM25 index is dirty but not built, skipping save")

    def load_bm25(self) -> None:
        """Load BM25 index from disk if available."""
        if self._bm25_path.exists():
            self._bm25 = BM25Index()
            self._bm25.load(self._bm25_path)
            self._bm25_dirty = False
            logger.info(
                "BM25 index loaded from disk ({} chunks)", self._bm25.size
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _lazy_init_bm25(self) -> None:
        """Инициализирует BM25 индекс при первом использовании."""
        if self._bm25 is None:
            self.load_bm25()
        if self._bm25 is None:
            self._bm25 = BM25Index([])
            logger.info("BM25 index initialized empty (no chunks)")


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
rag_service: RagService = RagService()