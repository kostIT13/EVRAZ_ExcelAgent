"""Repository layer for core DB tables — encapsulates all direct SQLAlchemy queries.

Each repository class is responsible for a single table/ model.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.db.models import (
    File as DBFile,
    Sheet,
    ColumnMetadata,
    Cell,
    QueryLog,
)


# ======================================================================
# FileRepository
# ======================================================================

class FileRepository:
    """Repository for the `files` table."""

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


# ======================================================================
# SheetRepository
# ======================================================================

class SheetRepository:
    """Repository for the `sheets` table."""

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


# ======================================================================
# ColumnRepository
# ======================================================================

class ColumnRepository:
    """Repository for the `column_metadata` table."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_by_sheet(self, sheet_id: int) -> List[ColumnMetadata]:
        result = await self.session.execute(
            select(ColumnMetadata)
            .where(ColumnMetadata.sheet_id == sheet_id)
            .order_by(ColumnMetadata.col_index)
        )
        return list(result.scalars().all())


# ======================================================================
# CellRepository
# ======================================================================

class CellRepository:
    """Repository for the `cells` table."""

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


# ======================================================================
# QueryLogRepository
# ======================================================================

class QueryLogRepository:
    """Repository for the `query_logs` table."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_all(
        self,
        skip: int = 0,
        limit: int = 20,
    ) -> List[QueryLog]:
        result = await self.session.execute(
            select(QueryLog)
            .order_by(desc(QueryLog.created_at))
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_request_id(self, request_id: str) -> Optional[QueryLog]:
        result = await self.session.execute(
            select(QueryLog).where(QueryLog.request_id == request_id)
        )
        return result.scalar_one_or_none()