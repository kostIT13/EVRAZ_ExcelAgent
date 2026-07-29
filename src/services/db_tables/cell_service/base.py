from abc import ABC, abstractmethod
from typing import Optional, List
from src.core.db.models import Cell


class CellRepository(ABC):

    @abstractmethod
    async def list_by_sheet(
        self,
        sheet_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Cell]:
        raise NotImplementedError