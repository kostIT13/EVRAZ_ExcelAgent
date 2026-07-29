from src.services.db_tables.query_log_service.repository import SQLAlchemyQueryLogRepository
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
from src.core.db.models import QueryLog
from src.core.db.database import async_session_maker
from fastapi import HTTPException, status
from src.core.logging_settings import logger


class TraceService:
    """Service for query log (trace) operations."""

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

    async def list_all(self, skip: int = 0, limit: int = 20) -> List[QueryLog]:
        async def _list(session):
            repo = SQLAlchemyQueryLogRepository(session)
            return await repo.list_all(skip=skip, limit=limit)
        return await self._run(_list, commit=False)

    async def get_by_request_id(self, request_id: str) -> QueryLog:
        async def _get(session):
            repo = SQLAlchemyQueryLogRepository(session)
            record = await repo.get_by_request_id(request_id)
            if not record:
                raise HTTPException(
                    status_code=404,
                    detail=f"Trace not found for request_id: {request_id}",
                )
            return record
        return await self._run(_get, commit=False)