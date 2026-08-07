from __future__ import annotations
import asyncio
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.config import settings
from src.core.logging_settings import logger
from src.core.qdrant.client import QdrantVectorStore


async def main() -> None:
    logger.info(
        "Qdrant: url={} collection='{}' dense_dim={}",
        settings.QDRANT_URL,
        settings.QDRANT_COLLECTION,
        settings.EMBED_DIMENSION,
    )

    store = QdrantVectorStore()

    logger.info("Удаляю коллекцию '{}'...", settings.QDRANT_COLLECTION)
    await store.delete_collection()

    logger.info(
        "Создаю коллекцию '{}' заново (dense={}, sparse)...",
        settings.QDRANT_COLLECTION,
        settings.EMBED_DIMENSION,
    )
    await store.ensure_collection()

    await store.close()
    logger.info(
        "Готово. Коллекция '{}' пересоздана. Заново загрузите файлы через 'pload file'.",
        settings.QDRANT_COLLECTION,
    )


if __name__ == "__main__":
    asyncio.run(main())