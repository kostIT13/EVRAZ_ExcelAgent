from pathlib import Path
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.logging_settings import logger
from src.core.db.models import File
from src.core.db.database import async_session_maker
from src.services.excel.repository import SQLAlchemyExcelRepository
from src.services.mart.normalizer import normalize_file_to_mart


class ExcelIngestionService:
    def __init__(self, session: Optional[AsyncSession] = None):
        self._session = session

    async def _run_with_session(self, action, *, commit: bool = True):
        if self._session:
            repo = SQLAlchemyExcelRepository(self._session)
            return await action(repo)
        async with async_session_maker() as session:
            repo = SQLAlchemyExcelRepository(session)
            result = await action(repo)
            if commit:
                await session.commit()
            return result

    async def process_file(self, file_path: Path) -> File:
        async def _process(repo):
            file_record = await repo.process_file(file_path)

            stats = await normalize_file_to_mart(file_record.id, session=repo.session)

            entity_stats = await repo.index_entities(file_record.id)

            logger.info(
                "Ingestion timing: mart={}ms, entities={}, previous=RAG-over-cells (minutes)",
                stats.get("elapsed_ms", 0),
                entity_stats,
            )
            return file_record

        return await self._run_with_session(_process)

    async def create_pending_file(self, file_path: Path) -> File:
        from src.core.excel.parser import ExcelParser

        async def _create(repo):
            parsed = ExcelParser(file_path).parse()
            return await repo.save_pending_file(parsed)

        return await self._run_with_session(_create)

    async def process_existing(self, file_id: int) -> File:
        from src.core.excel.parser import ExcelParser
        from src.core.db.models import File as FileModel
        from sqlalchemy import select

        async def _process(repo):
            result = await repo.session.execute(
                select(FileModel).where(FileModel.id == file_id)
            )
            file_record = result.scalar_one_or_none()
            if not file_record:
                raise FileNotFoundError(f"File id={file_id} not found")
            return file_record

        return await self._run_with_session(_process)

    async def get_file(self, file_id: int) -> Optional[File]:
        async def _get(repo):
            return await repo.get_file(file_id)

        return await self._run_with_session(_get, commit=False)

    async def list_files(self, skip: int = 0, limit: int = 100) -> List[File]:
        async def _list(repo):
            return await repo.list_files(skip=skip, limit=limit)

        return await self._run_with_session(_list, commit=False)

    async def delete_file(self, file_id: int) -> bool:
        async def _delete(repo):
            return await repo.delete_file(file_id)

        return await self._run_with_session(_delete)