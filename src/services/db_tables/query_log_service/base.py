from abc import ABC, abstractmethod
from typing import Optional, List
from datetime import datetime
from src.core.db.models import QueryLog


class QueryLogRepository(ABC):

    @abstractmethod
    async def list_all(
        self,
        skip: int = 0,
        limit: int = 20,
        q: Optional[str] = None,
        status: Optional[str] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> List[QueryLog]:
        raise NotImplementedError

    @abstractmethod
    async def count_all(
        self,
        q: Optional[str] = None,
        status: Optional[str] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> int:
        raise NotImplementedError

    @abstractmethod
    async def get_by_request_id(self, request_id: str) -> Optional[QueryLog]:
        raise NotImplementedError
