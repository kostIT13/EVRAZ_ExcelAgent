from src.services.db_tables.query_log_service.base import QueryLogRepository
from src.core.db.models import QueryLog
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
from sqlalchemy import select, desc


class SQLAlchemyQueryLogRepository(QueryLogRepository):
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