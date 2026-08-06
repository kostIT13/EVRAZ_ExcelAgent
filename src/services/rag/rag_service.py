"""
RAG service: orchestrates chunking, embedding, and hybrid retrieval via Qdrant.

Обеспечивает высокоуровневый API для пайплайна генерации и индексации файлов.
Вектора (dense + sparse) хранятся в Qdrant, PostgreSQL — только реляционные данные.
"""
from __future__ import annotations

from typing import List, Optional
from uuid import NAMESPACE_URL, uuid5

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.db.database import async_session_maker
from src.core.db.models import Sheet, ColumnMetadata, Cell, ExcelComment
from src.core.qdrant.client import QdrantVectorStore, qdrant_client
from src.services.rag.chunker import make_chunks
from src.services.rag.embedder import MAX_EMBED_CHARS, Embedder
from src.services.rag.hybrid import HybridRetriever, HybridSearchResult
from src.services.rag.sparse import SparseEmbedder, sparse_embedder


def _point_id(source_type: str, source_id: int, chunk_index: int = 0) -> str:
    """Формирует стабильный id точки в Qdrant (детерминированный UUID).

    Qdrant принимает в качестве point ID только unsigned int или UUID.
    Используем UUIDv5 от строкового представления, чтобы сохранить
    детерминизм: один и тот же (source_type, source_id, chunk_index) всегда
    даёт один и тот же UUID — это позволяет корректно перезаписывать
    точки при повторной индексации.
    """
    raw = f"{source_type}:{source_id}:{chunk_index}"
    return str(uuid5(NAMESPACE_URL, raw))


class RagService:
    """Высокоуровневый RAG-оркестратор поверх Qdrant.

    Usage
    -----
    rag = RagService()
    await rag.build_index_for_file(file_id=1)
    results = await rag.hybrid_search("какой-то запрос", top_k=5)
    """

    def __init__(
        self,
        embedder: Optional[Embedder] = None,
        store: Optional[QdrantVectorStore] = None,
        sparse: Optional[SparseEmbedder] = None,
    ) -> None:
        self._embedder = embedder or Embedder()
        self._store = store or qdrant_client
        self._sparse = sparse or sparse_embedder
        self._hybrid = HybridRetriever(
            embedder=self._embedder,
            store=self._store,
            sparse=self._sparse,
        )

    # ------------------------------------------------------------------
    # Session helpers
    # ------------------------------------------------------------------
    @staticmethod
    async def _with_session(
        session: Optional[AsyncSession],
        action,
        *,
        commit: bool = True,
    ):
        """Execute an action with a session, creating one if needed."""
        own_session = session is None
        s = session or async_session_maker()
        try:
            result = await action(s)
            if commit:
                await s.commit()
            return result
        except Exception:
            await s.rollback()
            raise
        finally:
            if own_session:
                await s.close()

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------
    async def build_index_for_sheet(
        self,
        sheet_id: int,
        text: str,
        session: Optional[AsyncSession] = None,
    ) -> None:
        """Чанкует, эмбеддит и сохраняет лист в Qdrant (dense + sparse)."""
        chunks = make_chunks(text, strategy="adaptive")
        logger.info("Sheet {}: split into {} chunks", sheet_id, len(chunks))

        # Удаляем старые точки листа
        await self._store.delete_by_filter(source_type="chunk", source_id=sheet_id)
        await self._store.delete_by_filter(source_type="sheet", source_id=sheet_id)

        points = []
        # Сначала эмбеддим все чанки батчами (один HTTP-запрос на порцию вместо
        # одного запроса на каждый чанк). Спарс-вектора считаются локально и быстро.
        chunk_dense = await self._embedder.embed_batch(chunks)
        for chunk_idx, (chunk_text, dense) in enumerate(zip(chunks, chunk_dense)):
            sparse = self._sparse.embed(chunk_text)
            points.append(
                {
                    "id": _point_id("chunk", sheet_id, chunk_idx),
                    "dense": dense,
                    "sparse": sparse,
                    "payload": {
                        "source_type": "chunk",
                        "source_id": sheet_id,
                        "text": chunk_text[:10000],
                        "chunk_index": chunk_idx,
                        "model_name": settings.OLLAMA_EMBED_MODEL,
                    },
                }
            )

        # Для full_vector используем компактное представление листа.
        # Лимит берём из MAX_EMBED_CHARS, чтобы не превысить контекст модели эмбеддинга
        # (bge-m3 = 8192 токена). Прежнее значение 18000 символов могло превышать контекст.
        full_text = text[:MAX_EMBED_CHARS]
        last_material_end = full_text.rfind("\n\n")
        if last_material_end > 100:
            full_text = text[:last_material_end]

        full_dense = await self._embedder.embed(full_text)
        full_sparse = self._sparse.embed(full_text)
        points.append(
            {
                "id": _point_id("sheet", sheet_id, 0),
                "dense": full_dense,
                "sparse": full_sparse,
                "payload": {
                    "source_type": "sheet",
                    "source_id": sheet_id,
                    "text": full_text[:10000],
                    "model_name": settings.OLLAMA_EMBED_MODEL,
                },
            }
        )

        await self._store.upsert(points)
        logger.info("Sheet {} indexed: {} chunks (dense + sparse)", sheet_id, len(chunks))

    async def build_index_for_column(
        self,
        column_id: int,
        text: str,
        session: Optional[AsyncSession] = None,
    ) -> None:
        """Эмбеддит и сохраняет колонку в Qdrant."""
        await self._store.delete_by_filter(source_type="column", source_id=column_id)

        dense = await self._embedder.embed(text)
        sparse = self._sparse.embed(text)
        await self._store.upsert(
            [
                {
                    "id": _point_id("column", column_id, 0),
                    "dense": dense,
                    "sparse": sparse,
                    "payload": {
                        "source_type": "column",
                        "source_id": column_id,
                        "text": text[:5000],
                        "model_name": settings.OLLAMA_EMBED_MODEL,
                    },
                }
            ]
        )
        logger.info("Column {} indexed (dense + sparse)", column_id)

    async def _build_index_for_columns(
        self,
        columns: List[ColumnMetadata],
    ) -> None:
        """Эмбеддит все колонки листа батчами (вместо одного HTTP-запроса на колонку)."""
        if not columns:
            return

        col_texts = []
        for col in columns:
            col_parts = [
                f"Колонка: {col.normalized_name}",
                f"тип: {col.data_type}",
            ]
            if col.sample_values:
                col_parts.append(f"примеры: {col.sample_values[:5]}")
            col_texts.append(", ".join(col_parts))

        col_dense = await self._embedder.embed_batch(col_texts)

        points = []
        for col, text, dense in zip(columns, col_texts, col_dense):
            points.append(
                {
                    "id": _point_id("column", col.id, 0),
                    "dense": dense,
                    "sparse": self._sparse.embed(text),
                    "payload": {
                        "source_type": "column",
                        "source_id": col.id,
                        "text": text[:5000],
                        "model_name": settings.OLLAMA_EMBED_MODEL,
                    },
                }
            )
            logger.debug("Column {} prepared for indexing", col.id)

        await self._store.upsert(points)
        logger.info("Indexed {} columns in batch", len(columns))

    async def build_index_for_file(
        self,
        file_id: int,
        session: Optional[AsyncSession] = None,
    ) -> None:
        """Строит dense + sparse индекс для всех листов и колонок файла."""
        own_session = session is None
        s = session or async_session_maker()
        try:
            sheets_result = await s.execute(
                select(Sheet).where(Sheet.file_id == file_id)
            )
            sheets = list(sheets_result.scalars().all())

            if not sheets:
                logger.warning("No sheets found for file_id={}", file_id)
                return

            for sheet in sheets:
                sheet_text = await self._build_sheet_text(sheet, s)
                if sheet_text:
                    await self.build_index_for_sheet(sheet.id, sheet_text, session=s)

                cols_result = await s.execute(
                    select(ColumnMetadata)
                    .where(ColumnMetadata.sheet_id == sheet.id)
                    .order_by(ColumnMetadata.col_index)
                )
                await self._build_index_for_columns(list(cols_result.scalars().all()))

                await self._index_comments(sheet.id, s)

            await s.commit()
            logger.info("File {} fully indexed: {} sheets", file_id, len(sheets))
        except Exception:
            await s.rollback()
            raise
        finally:
            if own_session:
                await s.close()

    async def _index_comments(
        self,
        sheet_id: int,
        session: AsyncSession,
    ) -> None:
        """Индексирует Excel-комментарии для листа."""
        result = await session.execute(
            select(ExcelComment).where(ExcelComment.sheet_id == sheet_id)
        )
        comments = list(result.scalars().all())

        if not comments:
            return

        comment_texts = [
            f"Комментарий к ячейке {c.cell_ref} (автор: {c.author or 'неизвестен'}): {c.text}"
            for c in comments
        ]

        full_text = "\n".join(comment_texts)
        chunks = make_chunks(full_text, strategy="adaptive")

        await self._store.delete_by_filter(source_type="comment", source_id=sheet_id)

        points = []
        chunk_dense = await self._embedder.embed_batch(chunks)
        for chunk_idx, (chunk_text, dense) in enumerate(zip(chunks, chunk_dense)):
            sparse = self._sparse.embed(chunk_text)
            points.append(
                {
                    "id": _point_id("comment", sheet_id, chunk_idx),
                    "dense": dense,
                    "sparse": sparse,
                    "payload": {
                        "source_type": "comment",
                        "source_id": sheet_id,
                        "text": chunk_text[:5000],
                        "model_name": settings.OLLAMA_EMBED_MODEL,
                    },
                }
            )

        await self._store.upsert(points)
        logger.info("Indexed {} comments for sheet_id={}", len(comments), sheet_id)

    @staticmethod
    async def _build_sheet_text(
        sheet: Sheet,
        session: AsyncSession,
        max_rows: int = 500,
    ) -> str:
        """Строит текстовое представление листа для эмбеддинга.

        Формат: структурированный текст, где каждый материал — отдельный блок.
        """
        parts = [
            f"Лист: {sheet.normalized_name}",
            f"период: {sheet.period or 'unknown'}",
        ]

        cols_result = await session.execute(
            select(ColumnMetadata)
            .where(ColumnMetadata.sheet_id == sheet.id)
            .order_by(ColumnMetadata.col_index)
        )
        columns = list(cols_result.scalars().all())
        if columns:
            col_names = [c.normalized_name for c in columns]
            parts.append(f"колонки: {', '.join(col_names)}")

        from src.core.db.models import FactPrice
        fact_result = await session.execute(
            select(FactPrice)
            .where(FactPrice.sheet_id == sheet.id)
            .order_by(FactPrice.item_name_normalized, FactPrice.price_source)
            .limit(500)
        )
        fact_rows = list(fact_result.scalars().all())

        if fact_rows:
            current_item = None
            item_lines = []
            for fp in fact_rows:
                if fp.item_name_normalized != current_item:
                    if item_lines:
                        parts.append("\n".join(item_lines))
                        parts.append("")
                    current_item = fp.item_name_normalized
                    item_lines = [f"{current_item}:"]
                item_lines.append(f"  {fp.price_source}: {fp.price_value} руб/тн")
            if item_lines:
                parts.append("\n".join(item_lines))
        else:
            parts.append("данные (все колонки):")
            col_names_map = {c.col_index: c.normalized_name for c in columns}
            distinct_rows = (
                await session.execute(
                    select(Cell.row_num)
                    .where(Cell.sheet_id == sheet.id)
                    .distinct()
                    .order_by(Cell.row_num)
                    .limit(max_rows)
                )
            ).scalars().all()
            for row_num in distinct_rows:
                row_cells = (
                    await session.execute(
                        select(Cell)
                        .where(Cell.sheet_id == sheet.id, Cell.row_num == row_num)
                        .order_by(Cell.col_index)
                    )
                ).scalars().all()
                row_values = []
                for c in row_cells:
                    val = c.value_text or str(c.value_number or "")
                    col_name = col_names_map.get(c.col_index, f"col_{c.col_index}")
                    if val:
                        row_values.append(f"{col_name}: {val}")
                if row_values:
                    parts.append(f"  строка {row_num}: " + " | ".join(row_values))

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------
    async def hybrid_search(
        self,
        query: str,
        top_k: int = 20,
    ) -> List[HybridSearchResult]:
        """Гибридный поиск (dense + sparse) через Qdrant с реранкингом."""
        try:
            return await self._hybrid.search(query, top_k=top_k)
        except Exception as exc:
            logger.error("Hybrid search failed: {}", exc)
            return []

    async def dense_search(self, query: str, top_k: int = 20) -> list:
        """Dense-only поиск."""
        from src.services.rag.retrieval import DenseRetriever
        retriever = DenseRetriever(self._embedder, self._store, self._sparse)
        return await retriever.search(query, top_k=top_k)

    async def clear_index(self) -> None:
        """Полностью очищает векторный индекс (для переиндексации)."""
        await self._store.delete_collection()
        await self._store.ensure_collection()
        logger.info("Vector index cleared and recreated")


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
rag_service: RagService = RagService()