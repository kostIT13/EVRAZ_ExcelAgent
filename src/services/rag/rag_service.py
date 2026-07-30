"""
RAG service: orchestrates chunking, embedding, BM25 indexing, and hybrid retrieval.
Provides a high-level API for the generation pipeline and file indexing.
"""

from __future__ import annotations

import pickle
from pathlib import Path
from typing import List, Optional

from loguru import logger
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.db.database import async_session_maker
from src.core.db.models import Sheet, ColumnMetadata, Cell, ExcelComment
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
        self._bm25: Optional[BM25Index] = None
        self._bm25_path: Path = Path("data/bm25_index.pkl")
        self._bm25_dirty: bool = False

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
    # BM25 helpers (DRY)
    # ------------------------------------------------------------------
    def _update_bm25(self, chunks: List[str], metadata: List[dict]) -> None:
        """Add chunks to BM25 index and rebuild."""
        self._lazy_init_bm25()
        if self._bm25 is not None and chunks:
            self._bm25.add_chunks(chunks, metadata=metadata)
            self._bm25.build()
            self._bm25_dirty = True

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------
    async def build_index_for_sheet(
        self,
        sheet_id: int,
        text: str,
        session: Optional[AsyncSession] = None,
    ) -> None:
        """Chunk, embed, and store a sheet's text representation."""
        chunks = make_chunks(text, strategy="adaptive")
        logger.info("Sheet {}: split into {} chunks", sheet_id, len(chunks))

        async def _do_index(s):
            await s.execute(delete(ChunkEmbedding).where(ChunkEmbedding.sheet_id == sheet_id))

            for chunk_idx, chunk_text in enumerate(chunks):
                vector = await self._embedder.embed(chunk_text)
                s.add(ChunkEmbedding(
                    sheet_id=sheet_id,
                    chunk_index=chunk_idx,
                    source_text=chunk_text[:10000],
                    embedding=vector,
                    model_name=settings.OLLAMA_EMBED_MODEL,
                ))

            # Для full_vector используем компактное представление:
            # только названия материалов (без цен), чтобы эмбеддинг листа был лёгким для поиска
            # и не обрезался. Берём первые 18000 символов текста (безопасный лимит модели BAAI/bge-m3).
            full_text = text[:18000]
            # Обрезаем по границе последнего полного названия материала
            last_material_end = full_text.rfind("\n\n")
            if last_material_end > 100:
                full_text = text[:last_material_end]
            
            full_vector = await self._embedder.embed(full_text)
            existing = await s.execute(
                select(SheetEmbedding).where(SheetEmbedding.sheet_id == sheet_id)
            )
            existing_record = existing.scalar_one_or_none()
            if existing_record:
                existing_record.source_text = full_text[:10000]
                existing_record.embedding = full_vector
                existing_record.model_name = settings.OLLAMA_EMBED_MODEL
            else:
                s.add(SheetEmbedding(
                    sheet_id=sheet_id,
                    source_text=full_text[:10000],
                    embedding=full_vector,
                    model_name=settings.OLLAMA_EMBED_MODEL,
                ))

        await self._with_session(session, _do_index)

        self._update_bm25(
            chunks,
            [{"source_type": "sheet", "source_id": sheet_id}] * len(chunks),
        )
        logger.info("Sheet {} indexed: {} chunks (dense) + BM25", sheet_id, len(chunks))

    async def build_index_for_column(
        self,
        column_id: int,
        text: str,
        session: Optional[AsyncSession] = None,
    ) -> None:
        """Embed and store a column's text representation."""
        async def _do_index(s):
            existing = await s.execute(
                select(ColumnEmbedding).where(ColumnEmbedding.column_id == column_id)
            )
            existing_record = existing.scalar_one_or_none()
            vector = await self._embedder.embed(text)

            if existing_record:
                existing_record.source_text = text[:5000]
                existing_record.embedding = vector
                existing_record.model_name = settings.OLLAMA_EMBED_MODEL
            else:
                s.add(ColumnEmbedding(
                    column_id=column_id,
                    source_text=text[:5000],
                    embedding=vector,
                    model_name=settings.OLLAMA_EMBED_MODEL,
                ))

        await self._with_session(session, _do_index)

        self._update_bm25(
            [text],
            [{"source_type": "column", "source_id": column_id}],
        )
        logger.info("Column {} indexed (dense + BM25)", column_id)

    async def build_index_for_file(
        self,
        file_id: int,
        session: Optional[AsyncSession] = None,
    ) -> None:
        """Build dense + BM25 index for all sheets and columns of a file."""
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
                for col in cols_result.scalars().all():
                    col_parts = [
                        f"Колонка: {col.normalized_name}",
                        f"тип: {col.data_type}",
                    ]
                    if col.sample_values:
                        col_parts.append(f"примеры: {col.sample_values[:5]}")
                    col_text = ", ".join(col_parts)
                    await self.build_index_for_column(col.id, col_text, session=s)

                await self._index_comments(sheet.id, s)

            # Коммитим все оставшиеся изменения (включая _index_comments для последнего sheet)
            await s.commit()

            logger.info("File {} fully indexed: {} sheets", file_id, len(sheets))
        except Exception:
            await s.rollback()
            raise
        finally:
            if own_session:
                await s.close()

        # Сохраняем BM25 индекс после полной индексации файла
        self.persist_bm25()

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

        for chunk_idx, chunk_text in enumerate(chunks):
            vector = await self._embedder.embed(chunk_text)
            session.add(ChunkEmbedding(
                sheet_id=sheet_id,
                chunk_index=chunk_idx,
                source_text=chunk_text[:5000],
                embedding=vector,
                model_name=settings.OLLAMA_EMBED_MODEL,
            ))

        self._update_bm25(
            chunks,
            [{"source_type": "comment", "source_id": sheet_id}] * len(chunks),
        )
        logger.info("Indexed {} comments for sheet_id={}", len(comments), sheet_id)

    @staticmethod
    async def _build_sheet_text(
        sheet: Sheet,
        session: AsyncSession,
        max_rows: int = 500,
    ) -> str:
        """Build a text representation of a sheet for embedding.
        
        Формат: структурированный текст, где каждый материал — отдельный блок.
        Это улучшает качество chunking и поиска.
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
            # Группируем по материалам — каждый материал отдельный блок
            current_item = None
            item_lines = []
            for fp in fact_rows:
                if fp.item_name_normalized != current_item:
                    if item_lines:
                        parts.append("\n".join(item_lines))
                        parts.append("")  # пустая строка между материалами
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

    async def build_full_index(
        self,
        session: Optional[AsyncSession] = None,
    ) -> None:
        """Rebuild the full BM25 index from all chunk embeddings in the DB."""
        async def _do_fetch(s):
            result = await s.execute(select(ChunkEmbedding))
            return result.scalars().all()

        records = await self._with_session(session, _do_fetch, commit=False)

        chunks = [r.source_text for r in records if r.source_text]
        if chunks:
            metadata = [
                {"source_type": "chunk", "source_id": r.sheet_id}
                for r in records if r.source_text
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
        
        Если dense search не дал результатов (эмбеддинги не загружены или модель не работает),
        делает fallback на прямой SQL-поиск через ILIKE по fact_prices.
        """
        self._lazy_init_bm25()

        # Пробуем dense search
        dense_results = await self._dense.search(query, top_k=top_k)

        # Если dense search не дал результатов — делаем fallback на SQL
        if not dense_results:
            logger.warning(
                "Dense search returned no results for '{}'. "
                "Falling back to SQL ILIKE search.",
                query[:60],
            )
            return await self._sql_fallback_search(query, top_k=top_k)

        # Если BM25 пуст — используем только dense
        if self._bm25 is None or self._bm25.size == 0 or not self._bm25.is_built:
            logger.warning("BM25 index is empty or not built; using dense-only results")
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

        # Полноценный hybrid search
        hybrid = HybridRetriever(bm25_index=self._bm25, dense_retriever=self._dense, fusion="rrf")
        return await hybrid.search(query, top_k=top_k)

    async def _sql_fallback_search(
        self,
        query: str,
        top_k: int = 20,
    ) -> List[HybridSearchResult]:
        """Fallback: прямой SQL-поиск через ILIKE по fact_prices.
        
        Используется когда dense search не дал результатов (например,
        эмбеддинги не загружены или модель эмбеддингов не работает).
        """
        from sqlalchemy import text
        from src.core.db.database import async_session_maker

        # Извлекаем ключевые слова из запроса
        import re
        keywords = re.findall(r'\w+', query.lower())
        # Фильтруем стоп-слова
        stop_words = {'какова', 'сколько', 'какая', 'какой', 'какие', 'каких', 'цена', 'цены',
                      'цену', 'стоимость', 'была', 'составила', 'составил', 'составило',
                      'за', 'на', 'в', 'по', 'с', 'о', 'об', 'от', 'для', 'и', 'или',
                      'не', 'ни', 'да', 'нет', 'это', 'то', 'что', 'как', 'так', 'все',
                      'весь', 'вся', 'всего', 'всей', 'всех', 'всем', 'всеми',
                      'январь', 'февраль', 'март', 'апрель', 'май', 'июнь',
                      'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь',
                      'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
                      'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря',
                      'месяц', 'месяце', 'месяца', 'месяцев', 'год', 'года', 'году',
                      'лет', '2025', '2024', '2026'}
        keywords = [k for k in keywords if k not in stop_words and len(k) > 2]

        if not keywords:
            logger.warning("No meaningful keywords extracted from '{}'", query[:60])
            return []

        # Строим ILIKE условия
        like_conditions = " OR ".join(
            f"fp.item_name_normalized ILIKE '%{kw}%'" for kw in keywords
        )

        sql = f"""
        SELECT DISTINCT fp.item_name_normalized, fp.period, fp.price_source, fp.price_value,
               fp.sheet_id
        FROM fact_prices fp
        WHERE {like_conditions}
        ORDER BY fp.item_name_normalized, fp.period
        LIMIT {top_k * 3}
        """

        logger.info(
            "SQL fallback search: keywords={}, sql={}",
            keywords,
            sql[:200],
        )

        try:
            async with async_session_maker() as s:
                result = await s.execute(text(sql))
                rows = result.fetchall()

            if not rows:
                logger.warning("SQL fallback search returned no results for keywords={}", keywords)
                return []

            # Группируем по материалу и формируем чанки
            from collections import defaultdict
            by_item = defaultdict(list)
            for row in rows:
                by_item[row[0]].append(row)

            results = []
            for rank, (item_name, item_rows) in enumerate(sorted(by_item.items())[:top_k]):
                chunk_parts = [f"{item_name}:"]
                for row in item_rows[:5]:  # макс 5 строк на материал
                    chunk_parts.append(f"  {row[2]}: {row[3]} руб/тн (период: {row[1]})")
                chunk_text = "\n".join(chunk_parts)

                results.append(HybridSearchResult(
                    chunk=chunk_text,
                    score=1.0 - (rank * 0.05),  # убывающий score
                    bm25_score=0.0,
                    dense_score=0.0,
                    rank=rank + 1,
                    source_type="sql_fallback",
                    source_id=item_rows[0][4] if item_rows else 0,
                ))

            logger.info(
                "SQL fallback search: found {} items for keywords={}",
                len(results),
                keywords,
            )
            return results

        except Exception as exc:
            logger.error("SQL fallback search failed: {}", exc)
            return []

    async def dense_search(self, query: str, top_k: int = 20) -> list:
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
            try:
                self._bm25.load(self._bm25_path)
                self._bm25_dirty = False
                logger.info("BM25 index loaded from disk ({} chunks)", self._bm25.size)
            except (EOFError, pickle.UnpicklingError, ValueError) as exc:
                logger.warning("BM25 index file corrupted ({}), rebuilding from scratch", exc)
                self._bm25_path.unlink(missing_ok=True)
                self._bm25 = BM25Index([])
                self._bm25_dirty = True

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