from src.services.db_tables.file_service.base import FileRepository
from src.core.db.models import File as DBFile 
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from src.core.db.models import Sheet


class SQLAlchemyFileRepository(FileRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, file_id: int) -> Optional[DBFile]:
        result = await self.session.execute(
            select(DBFile).where(DBFile.id == file_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id_with_sheets_and_columns(self, file_id: int) -> Optional[DBFile]:
        result = await self.session.execute(
            select(DBFile)
            .options(selectinload(DBFile.sheets).selectinload(Sheet.columns))
            .where(DBFile.id == file_id)
        )
        return result.scalar_one_or_none()

    async def list_all(
        self,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[DBFile]:
        query = select(DBFile)
        if status:
            query = query.where(DBFile.status == status)
        query = query.order_by(DBFile.uploaded_at.desc()).offset(skip).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count(self, status: Optional[str] = None) -> int:
        query = select(func.count()).select_from(DBFile)
        if status:
            query = query.where(DBFile.status == status)
        result = await self.session.execute(query)
        return result.scalar() or 0

    async def delete(self, file_record: DBFile) -> None:
        await self.session.delete(file_record)
        await self.session.flush()