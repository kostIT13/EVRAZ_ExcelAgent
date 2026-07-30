from pathlib import Path
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.logging_settings import logger
from src.core.db.models import File
from src.core.db.database import async_session_maker
from src.services.excel.repository import SQLAlchemyExcelRepository


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
            return await repo.process_file(file_path)

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