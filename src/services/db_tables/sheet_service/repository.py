from src.services.db_tables.sheet_service.base import SheetRepository
from src.core.db.models import Sheet
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.orm import selectinload


class SQLAlchemySheetRepository(SheetRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id_and_file(self, sheet_id: int, file_id: int) -> Optional[Sheet]:
        result = await self.session.execute(
            select(Sheet).where(Sheet.id == sheet_id, Sheet.file_id == file_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id_with_columns(self, sheet_id: int, file_id: int) -> Optional[Sheet]:
        result = await self.session.execute(
            select(Sheet)
            .options(selectinload(Sheet.columns))
            .where(Sheet.id == sheet_id, Sheet.file_id == file_id)
        )
        return result.scalar_one_or_none()

    async def list_by_file(self, file_id: int) -> List[Sheet]:
        result = await self.session.execute(
            select(Sheet).where(Sheet.file_id == file_id).order_by(Sheet.sheet_index)
        )
        return list(result.scalars().all())