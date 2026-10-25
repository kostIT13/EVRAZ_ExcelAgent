from src.services.db_tables.query_log_service.base import QueryLogRepository
from src.core.db.models import QueryLog
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
from typing import Optional, List, Tuple
from sqlalchemy import func, select, desc


def _apply_filters(
    stmt,
    q: Optional[str],
    status: Optional[str],
    since: Optional[datetime],
    until: Optional[datetime],
):
    if status:
        stmt = stmt.where(QueryLog.status == status)
    if q:
        # Подстрока пользователя: % и _ экранируем, чтобы они не стали джокерами LIKE.
        escaped = q.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
        stmt = stmt.where(QueryLog.question.ilike(f"%{escaped}%", escape="\\"))
    if since is not None:
        stmt = stmt.where(QueryLog.created_at >= since)
    if until is not None:
        stmt = stmt.where(QueryLog.created_at <= until)
    return stmt


class SQLAlchemyQueryLogRepository(QueryLogRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_all(
        self,
        skip: int = 0,
        limit: int = 20,
        q: Optional[str] = None,
        status: Optional[str] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> List[QueryLog]:
        stmt = _apply_filters(select(QueryLog), q, status, since, until)
        result = await self.session.execute(
            stmt.order_by(desc(QueryLog.created_at)).offset(skip).limit(limit)
        )
        return list(result.scalars().all())

    async def count_all(
        self,
        q: Optional[str] = None,
        status: Optional[str] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> int:
        stmt = _apply_filters(
            select(func.count()).select_from(QueryLog), q, status, since, until
        )
        return int((await self.session.execute(stmt)).scalar_one())

    async def get_by_request_id(self, request_id: str) -> Optional[QueryLog]:
        result = await self.session.execute(
            select(QueryLog).where(QueryLog.request_id == request_id)
        )
        return result.scalar_one_or_none()
