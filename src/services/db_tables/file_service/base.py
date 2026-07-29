from abc import ABC, abstractmethod
from src.core.db.models import File as DBFile
from typing import Optional, List


class FileRepository(ABC):
    
    @abstractmethod
    async def get_by_id(self, file_id: int) -> Optional[DBFile]:
        raise NotImplementedError

    @abstractmethod
    async def get_by_id_with_sheets_and_columns(self, file_id: int) -> Optional[DBFile]:
        raise NotImplementedError

    @abstractmethod
    async def list_all(self, status: Optional[str] = None, skip: int = 0, limit: int = 100) -> List[DBFile]:
        raise NotImplementedError

    @abstractmethod
    async def count(self, status: Optional[str] = None) -> int:
        raise NotImplementedError

    