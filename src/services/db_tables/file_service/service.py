from src.services.db_tables.file_service.repository import SQLAlchemyFileRepository
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
from src.core.db.models import File as DBFile
from src.core.db.database import async_session_maker
from fastapi import HTTPException, status
from src.core.logging_settings import logger


class FileService:
    def __init__(self, session: Optional[AsyncSession] = None) -> None:
        self._session = session
        self.repository = SQLAlchemyFileRepository(session)

    async def _run(self, action, *, commit: bool = True):
        if self._session:
            return await action(self._session)
        async with async_session_maker() as session:
            result = await action(session)
            if commit:
                await session.commit()
            return result

    async def get_by_id(self, file_id: int) -> DBFile:
        async def _get(session):
            record = await self.repository.get_by_id_with_sheets_and_columns(file_id)
            if not record:
                raise HTTPException(status_code=404, detail=f"File with id={file_id} not found")
            return record
        return await self._run(_get, commit=False)

    async def list_all(
        self,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[List[DBFile], int]:
        async def _list(session):
            files = await self.repository.list_all(status=status, skip=skip, limit=limit)
            total = await self.repository.count(status=status)
            return files, total
        return await self._run(_list, commit=False)

    async def delete(self, file_id: int) -> None:
        async def _delete(session):
            record = await self.repository.get_by_id(file_id)
            if not record:
                raise HTTPException(status_code=404, detail=f"File with id={file_id} not found")
            await self.repository.delete(record)
            logger.info("Deleted file id={}", file_id)
        return await self._run(_delete)