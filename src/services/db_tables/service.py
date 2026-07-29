"""Service layer for core DB tables — orchestrates repositories and business logic.

Endpoints should only interact with services, never with repositories or SQLAlchemy directly.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db.database import async_session_maker
from src.core.db.models import (
    File as DBFile,
    Sheet,
    ColumnMetadata,
    Cell,
    QueryLog,
)
from src.core.logging_settings import logger
from src.services.db_tables.repository import (
    FileRepository,
    SheetRepository,
    ColumnRepository,
    CellRepository,
    QueryLogRepository,
)


# ======================================================================
# FileService
# ======================================================================

class FileService:
    """Service for file-related operations."""

    def __init__(self, session: Optional[AsyncSession] = None) -> None:
        self._session = session

    async def _run(self, action, *, commit: bool = True):
        """Execute an action with a session, creating one if needed."""
        if self._session:
            return await action(self._session)
        async with async_session_maker() as session:
            result = await action(session)
            if commit:
                await session.commit()
            return result

    async def get_by_id(self, file_id: int) -> DBFile:
        """Get file by ID or raise 404."""
        async def _get(session):
            repo = FileRepository(session)
            record = await repo.get_by_id_with_sheets_and_columns(file_id)
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
        """List files with optional status filter. Returns (files, total_count)."""
        async def _list(session):
            repo = FileRepository(session)
            files = await repo.list_all(status=status, skip=skip, limit=limit)
            total = await repo.count(status=status)
            return files, total
        return await self._run(_list, commit=False)

    async def delete(self, file_id: int) -> None:
        """Delete file by ID or raise 404."""
        async def _delete(session):
            repo = FileRepository(session)
            record = await repo.get_by_id(file_id)
            if not record:
                raise HTTPException(status_code=404, detail=f"File with id={file_id} not found")
            await repo.delete(record)
            logger.info("Deleted file id={}", file_id)
        return await self._run(_delete)


# ======================================================================
# SheetService
# ======================================================================

class SheetService:
    """Service for sheet-related operations."""

    def __init__(self, session: Optional[AsyncSession] = None) -> None:
        self._session = session

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
            # Verify file exists first
            file_repo = FileRepository(session)
            file_record = await file_repo.get_by_id(file_id)
            if not file_record:
                raise HTTPException(status_code=404, detail=f"File with id={file_id} not found")

            repo = SheetRepository(session)
            return await repo.list_by_file(file_id)
        return await self._run(_list, commit=False)

    async def get_detail(self, file_id: int, sheet_id: int) -> Sheet:
        """Get sheet with columns. Validates file+sheet exist."""
        async def _get(session):
            repo = SheetRepository(session)
            sheet = await repo.get_by_id_with_columns(sheet_id, file_id)
            if not sheet:
                raise HTTPException(
                    status_code=404,
                    detail=f"Sheet with id={sheet_id} not found for file_id={file_id}",
                )
            return sheet
        return await self._run(_get, commit=False)


# ======================================================================
# ColumnService
# ======================================================================

class ColumnService:
    """Service for column-related operations."""

    def __init__(self, session: Optional[AsyncSession] = None) -> None:
        self._session = session

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
            # Verify sheet exists
            sheet_repo = SheetRepository(session)
            sheet = await sheet_repo.get_by_id_and_file(sheet_id, file_id)
            if not sheet:
                raise HTTPException(
                    status_code=404,
                    detail=f"Sheet with id={sheet_id} not found for file_id={file_id}",
                )

            repo = ColumnRepository(session)
            return await repo.list_by_sheet(sheet_id)
        return await self._run(_list, commit=False)


# ======================================================================
# CellService
# ======================================================================

class CellService:
    """Service for cell-related operations."""

    def __init__(self, session: Optional[AsyncSession] = None) -> None:
        self._session = session

    async def _run(self, action, *, commit: bool = True):
        if self._session:
            return await action(self._session)
        async with async_session_maker() as session:
            result = await action(session)
            if commit:
                await session.commit()
            return result

    async def list_by_sheet(
        self,
        file_id: int,
        sheet_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Cell]:
        """List cells for a sheet with pagination. Validates sheet exists."""
        async def _list(session):
            # Verify sheet exists
            sheet_repo = SheetRepository(session)
            sheet = await sheet_repo.get_by_id_and_file(sheet_id, file_id)
            if not sheet:
                raise HTTPException(
                    status_code=404,
                    detail=f"Sheet with id={sheet_id} not found for file_id={file_id}",
                )

            repo = CellRepository(session)
            return await repo.list_by_sheet(sheet_id, skip=skip, limit=limit)
        return await self._run(_list, commit=False)


# ======================================================================
# TraceService
# ======================================================================

class TraceService:
    """Service for query log (trace) operations."""

    @staticmethod
    async def list_all(skip: int = 0, limit: int = 20) -> List[QueryLog]:
        async with async_session_maker() as session:
            repo = QueryLogRepository(session)
            return await repo.list_all(skip=skip, limit=limit)

    @staticmethod
    async def get_by_request_id(request_id: str) -> QueryLog:
        async with async_session_maker() as session:
            repo = QueryLogRepository(session)
            record = await repo.get_by_request_id(request_id)
            if not record:
                raise HTTPException(
                    status_code=404,
                    detail=f"Trace not found for request_id: {request_id}",
                )
            return record