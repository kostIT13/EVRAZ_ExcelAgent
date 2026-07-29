from abc import ABC, abstractmethod
from typing import Optional, List
from src.core.db.models import ColumnMetadata


class ColumnRepository(ABC):

    @abstractmethod
    async def list_by_sheet(self, sheet_id: int) -> List[ColumnMetadata]:
        raise NotImplementedError