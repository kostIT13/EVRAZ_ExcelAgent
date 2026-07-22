from pathlib import Path
from typing import Optional, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.logging_settings import logger
from src.core.db.models import File, Sheet, ColumnMetadata, Cell
from src.core.db.database import async_session_maker
from src.core.excel.parser import ExcelParser
from src.core.excel.schemas import ParsedFile
from src.core.excel.normalize import ExcelNormalizer
from src.services.excel.repository import ExcelRepository


class ExcelIngestionService:
    def __init__(self, session: Optional[AsyncSession] = None):
        self._session = session

    async def process_file(self, file_path: Path) -> File:
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        if file_path.suffix.lower() not in ('.xlsx', '.xls'):
            raise ValueError(f"Not an Excel file: {file_path.suffix}")

        logger.info("Starting ingestion for file: {}", file_path)

        parser = ExcelParser(file_path)
        parsed: ParsedFile = parser.parse()
        logger.info("Parsed {} sheets from {}", len(parsed.sheets), file_path.name)

        self._normalize_parsed(parsed)

        if self._session:
            file_record = await self._save_with_session(parsed)
        else:
            async with async_session_maker() as session:
                repo = ExcelRepository(session)
                file_record = await repo.save_parsed_file(parsed)

        logger.info("Ingestion complete: file_id={}, filename={}", file_record.id, file_record.filename)
        return file_record

    async def _save_with_session(self, parsed: ParsedFile) -> File:
        repo = ExcelRepository(self._session)
        return await repo.save_parsed_file(parsed)

    def _normalize_parsed(self, parsed: ParsedFile) -> None:
        for sheet in parsed.sheets:
            sheet.headers = [ExcelNormalizer.normalize_header(h) for h in sheet.headers]

            for header in sheet.headers:
                sample_values = ExcelNormalizer.extract_sample_values(sheet.data, header.col_name)
                col_type = ExcelNormalizer.infer_column_type(header, sample_values)
                logger.debug("Column '{}' → type={}, samples={}", header.col_name, col_type, sample_values[:3])


    async def get_file(self, file_id: int) -> Optional[File]:
        async with async_session_maker() as session:
            result = await session.execute(select(File).where(File.id == file_id))
            return result.scalar_one_or_none()

    async def list_files(self, skip: int = 0, limit: int = 100) -> List[File]:
        async with async_session_maker() as session:
            result = await session.execute(
                select(File).order_by(File.uploaded_at.desc()).offset(skip).limit(limit)
            )
            return list(result.scalars().all())

    async def delete_file(self, file_id: int) -> bool:
        async with async_session_maker() as session:
            result = await session.execute(select(File).where(File.id == file_id))
            file_record = result.scalar_one_or_none()
            if not file_record:
                return False
            await session.delete(file_record)
            await session.commit()
            logger.info("Deleted file id={}", file_id)
            return True