from abc import ABC, abstractmethod
from typing import Optional, List
from src.core.db.models import Sheet


class SheetRepository(ABC):

    @abstractmethod
    async def get_by_id_and_file(self, sheet_id: int, file_id: int) -> Optional[Sheet]:
        raise NotImplementedError

    @abstractmethod
    async def get_by_id_with_columns(self, sheet_id: int, file_id: int) -> Optional[Sheet]:
        raise NotImplementedError

    @abstractmethod
    async def list_by_file(self, file_id: int) -> List[Sheet]:
        raise NotImplementedError