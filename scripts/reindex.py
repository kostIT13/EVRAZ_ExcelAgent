"""
Скрипт переиндексации: удаляет старые эмбеддинги и перестраивает
BM25 + dense (pgvector) индексы для всех файлов в БД.

Запуск:
    cd C:\Users\frejz\OneDrive\Рабочий стол\Evraz_Agent
    .venv\Scripts\python scripts\reindex.py
"""

import asyncio
import sys
from pathlib import Path

# Добавляем корень проекта в путь
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loguru import logger
from sqlalchemy import select, delete

from src.core.config import settings
from src.core.db.database import async_session_maker
from src.core.db.models import File, Sheet, ColumnMetadata
from src.core.db.vector_models import SheetEmbedding, ColumnEmbedding, QueryEmbeddingCache
from src.services.rag.rag_service import rag_service


async def reindex_all():
    logger.info("=" * 60)
    logger.info("НАЧАЛО ПЕРЕИНДЕКСАЦИИ")
    logger.info(f"Ollama URL: {settings.OLLAMA_BASE_URL}")
    logger.info(f"Embed model: {settings.OLLAMA_EMBED_MODEL}")
    logger.info(f"Postgres URL: {settings.POSTGRES_URL}")
    logger.info("=" * 60)

    # Шаг 1: Получаем все файлы
    async with async_session_maker() as session:
        result = await session.execute(select(File).order_by(File.id))
        files = list(result.scalars().all())

        if not files:
            logger.warning("В БД нет файлов! Сначала загрузи Excel через API /upload")
            return

        logger.info("Найдено файлов: {}", len(files))
        for f in files:
            logger.info("  File #{}: {} (created: {})", f.id, f.filename, f.created_at)

    # Шаг 2: Удаляем старые эмбеддинги
    logger.info("Удаляем старые эмбеддинги...")
    async with async_session_maker() as session:
        await session.execute(delete(SheetEmbedding))
        await session.execute(delete(ColumnEmbedding))
        await session.execute(delete(QueryEmbeddingCache))
        await session.commit()
    logger.info("Старые эмбеддинги удалены")

    # Шаг 3: Сбрасываем BM25 индекс
    rag_service._bm25 = None
    rag_service._bm25_dirty = False
    logger.info("BM25 индекс сброшен")

    # Шаг 4: Индексируем каждый файл
    for f in files:
        logger.info("--- Индексирую файл #{}: {} ---", f.id, f.filename)
        try:
            await rag_service.build_index_for_file(f.id)
            logger.info("Файл #{} успешно проиндексирован", f.id)
        except Exception as e:
            logger.error("Ошибка при индексации файла #{}: {}", f.id, e)
            import traceback
            logger.error(traceback.format_exc())

    # Шаг 5: Сохраняем BM25 индекс на диск
    rag_service.persist_bm25()

    # Шаг 6: Проверяем результат
    async with async_session_maker() as session:
        sheet_count = (await session.execute(select(SheetEmbedding))).scalars().all()
        col_count = (await session.execute(select(ColumnEmbedding))).scalars().all()
        logger.info("=" * 60)
        logger.info("ИТОГО:")
        logger.info("  SheetEmbedding: {} записей", len(sheet_count))
        logger.info("  ColumnEmbedding: {} записей", len(col_count))
        logger.info("  BM25 chunks: {}", rag_service._bm25.size if rag_service._bm25 else 0)
        logger.info("=" * 60)

    logger.info("ПЕРЕИНДЕКСАЦИЯ ЗАВЕРШЕНА!")


if __name__ == "__main__":
    asyncio.run(reindex_all())