"""Пересоздание Qdrant-коллекции с новой размерностью dense-векторов.

Используется после смены эмбеддинг-модели (например, с fastembed
intfloat/multilingual-e5-large dim=1024, переходя с MiniLM dim=384): существующая
коллекция создана под старую размерность и несовместима с новыми векторами.

Qdrant работает в docker и опубликован на порту 6333. URL берётся из
переменной окружения QDRANT_URL (по умолчанию http://qdrant:6333 — имя хоста
внутри docker-сети).

Запуск с хоста (рекомендуется) — указываем localhost, т.к. внутри docker-сети
имя 'qdrant' не резолвится на хосте:
    set "QDRANT_URL=http://localhost:6333" && uv run python scripts/recreate_qdrant_collection.py

Запуск внутри контейнера service (docker compose run):
    docker compose run --rm -T service uv run python scripts/recreate_qdrant_collection.py

После пересоздания коллекции заново загрузите файлы через 'pload file'.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Добавляем корень проекта в sys.path, чтобы импорты src.* работали
# независимо от того, откуда запущен скрипт.
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