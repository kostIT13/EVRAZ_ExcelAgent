from src.services.db_tables.sheet_service.repository import SQLAlchemySheetRepository
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
from src.core.db.models import Sheet
from src.core.db.database import async_session_maker
from fastapi import HTTPException, status
from src.core.logging_settings import logger


class SheetService:
    def __init__(self, session: Optional[AsyncSession] = None) -> None:
        self._session = session
        self.repository = SQLAlchemySheetRepository(session)

    async def _run(self, action, *, commit: bool = True):
        if self._session:
            return await action(self._session)
        async with async_session_maker() as session:
            result = await action(session)
            if commit:
                await session.commit()
            return result

    async def list_by_file(self, file_id: int) -> List[Sheet]:
        """List all sheets for a file. Validates file exists."""
        async def _list(session):
            repo = SQLAlchemySheetRepository(session)
            return await repo.list_by_file(file_id)
        return await self._run(_list, commit=False)

    async def get_detail(self, file_id: int, sheet_id: int) -> Sheet:
        """Get sheet with columns. Validates file+sheet exist."""
        async def _get(session):
            repo = SQLAlchemySheetRepository(session)
            sheet = await repo.get_by_id_with_columns(sheet_id, file_id)
            if not sheet:
                raise HTTPException(
                    status_code=404,
                    detail=f"Sheet with id={sheet_id} not found for file_id={file_id}",
                )
            return sheet
        return await self._run(_get, commit=False)