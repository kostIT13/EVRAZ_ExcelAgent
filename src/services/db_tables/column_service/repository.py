from src.services.db_tables.column_service.base import ColumnRepository
from src.core.db.models import ColumnMetadata
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from sqlalchemy import select


class SQLAlchemyColumnRepository(ColumnRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_by_sheet(self, sheet_id: int) -> List[ColumnMetadata]:
        result = await self.session.execute(
            select(ColumnMetadata)
            .where(ColumnMetadata.sheet_id == sheet_id)
            .order_by(ColumnMetadata.col_index)
        )
        return list(result.scalars().all())