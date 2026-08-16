from __future__ import annotations
import asyncio
import time
from pathlib import Path
from typing import Dict, Optional
from src.core.config import settings
from src.core.logging_settings import logger
from src.services.excel.ingestion_service import ExcelIngestionService


class IngestionQueue:

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
        service = ExcelIngestionService()
        file_record = await service.create_pending_file(file_path)
        file_id = file_record.id
        self._status[file_id] = {"status": "uploaded", "path": str(file_path)}
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