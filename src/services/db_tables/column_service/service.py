from src.services.db_tables.column_service.repository import SQLAlchemyColumnRepository
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
from src.core.db.models import ColumnMetadata
from src.core.db.database import async_session_maker
from fastapi import HTTPException, status
from src.core.logging_settings import logger


class ColumnService:
    def __init__(self, session: Optional[AsyncSession] = None) -> None:
        self._session = session
        self.repository = SQLAlchemyColumnRepository(session)

    async def _run(self, action, *, commit: bool = True):
        if self._session:
            return await action(self._session)
        async with async_session_maker() as session:
            result = await action(session)
            if commit:
                await session.commit()
            return result

    async def list_by_sheet(self, file_id: int, sheet_id: int) -> List[ColumnMetadata]:
        """List columns for a sheet. Validates sheet exists."""
        async def _list(session):
            from src.services.db_tables.sheet_service.repository import SQLAlchemySheetRepository
            sheet_repo = SQLAlchemySheetRepository(session)
            sheet = await sheet_repo.get_by_id_and_file(sheet_id, file_id)
            if not sheet:
                raise HTTPException(
                    status_code=404,
                    detail=f"Sheet with id={sheet_id} not found for file_id={file_id}",
                )
            repo = SQLAlchemyColumnRepository(session)
            return await repo.list_by_sheet(sheet_id)
        return await self._run(_list, commit=False)