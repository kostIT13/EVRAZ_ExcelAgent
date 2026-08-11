"""Асинхронный ingestion через лёгкую in-process очередь.

Выносит парсинг + нормализацию + entity-resolution из синхронного /files/upload
в фоновую задачу. Клиент сразу получает file_id и опрашивает статус через
GET /files/{file_id}.

Статусы обработки: uploaded → processing → ready | failed.
(При использовании schema inference дополнительно появляется
schema_pending_confirmation, но базовый поток остаётся upload → ready.)

Для прод-развёртывания замените INGESTION_QUEUE_MODE на "celery"/"arq" —
интерфейс enqueue()/get_status() сохраняется, под капотом меняется только
брокер задач.
"""
from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Dict, Optional

from src.core.config import settings
from src.core.logging_settings import logger
from src.services.excel.ingestion_service import ExcelIngestionService


class IngestionQueue:
    """In-process очередь фоновой обработки файлов."""

    def __init__(self) -> None:
        self._queue: "asyncio.Queue[int]" = asyncio.Queue()
        self._status: Dict[int, Dict[str, object]] = {}
        self._worker: Optional[asyncio.Task] = None

    async def start(self) -> None:
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._run_worker())

    async def stop(self) -> None:
        if self._worker:
            self._worker.cancel()
            try:
                await self._worker
            except asyncio.CancelledError:
                pass

    async def enqueue(self, file_path: Path) -> int:
        """Ставит файл в очередь, возвращает file_id-маркер для опроса.

        Примечание: чтобы вернуть реальный file_id, сначала создаём запись File
        (status=uploaded) через ingestion_service, затем обрабатываем в фоне.
        """
        service = ExcelIngestionService()
        file_record = await service.create_pending_file(file_path)
        file_id = file_record.id
        self._status[file_id] = {"status": "uploaded", "path": str(file_path)}

        # Гарантируем, что фоновый воркер запущен (lifespan мог не стартовать его
        # при определённых путях запуска, напр. uvicorn без lifespan или reload).
        await self.start()
        await self._queue.put(file_id)
        return file_id

    def get_status(self, file_id: int) -> Dict[str, object]:
        return dict(self._status.get(file_id, {"status": "unknown"}))

    async def _run_worker(self) -> None:
        while True:
            file_id = await self._queue.get()
            try:
                await self._process(file_id)
            except Exception as exc:
                logger.error("Ingestion worker failed for file {}: {}", file_id, exc)
                self._status[file_id] = {
                    "status": "failed",
                    "error": str(exc),
                    "finished_at": time.time(),
                }
            finally:
                self._queue.task_done()

    async def _process(self, file_id: int) -> None:
        # Сохраняем путь ДО перезаписи словаря статуса, иначе ключ "path"
        # теряется и обработка уходит в process_existing (без реального парсинга).
        path = self._status[file_id].get("path")
        self._status[file_id] = {"status": "processing", "started_at": time.time()}

        service = ExcelIngestionService()
        if path:
            file_record = await service.process_file(Path(str(path)))
        else:
            file_record = await service.process_existing(file_id)

        self._status[file_id] = {
            "status": file_record.status,
            "file_id": file_record.id,
            "finished_at": time.time(),
        }


ingestion_queue: IngestionQueue = IngestionQueue()