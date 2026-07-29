from abc import ABC, abstractmethod
from typing import Optional, List
from src.core.db.models import QueryLog


class QueryLogRepository(ABC):

    @abstractmethod
    async def list_all(
        self,
        skip: int = 0,
        limit: int = 20,
    ) -> List[QueryLog]:
        raise NotImplementedError

    @abstractmethod
    async def get_by_request_id(self, request_id: str) -> Optional[QueryLog]:
        raise NotImplementedError