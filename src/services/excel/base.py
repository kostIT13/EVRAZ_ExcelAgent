from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional

from src.core.db.models import File


class ExcelService(ABC):
    @abstractmethod
    async def process_file(self, file_path: Path) -> File:
        ...

    @abstractmethod
    async def get_file(self, file_id: int) -> Optional[File]:
        ...

    @abstractmethod
    async def list_files(self, skip: int = 0, limit: int = 100) -> List[File]:
        ...

    @abstractmethod
    async def delete_file(self, file_id: int) -> bool:
        ...