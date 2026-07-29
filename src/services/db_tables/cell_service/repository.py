from src.services.db_tables.cell_service.base import CellRepository
from src.core.db.models import Cell
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from sqlalchemy import select


class SQLAlchemyCellRepository(CellRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_by_sheet(
        self,
        sheet_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Cell]:
        result = await self.session.execute(
            select(Cell)
            .where(Cell.sheet_id == sheet_id)
            .order_by(Cell.row_num, Cell.col_index)
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())