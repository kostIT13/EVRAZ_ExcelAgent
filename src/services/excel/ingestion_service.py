from pathlib import Path
from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.logging_settings import logger
from src.core.db.models import File, Sheet
from src.core.db.database import async_session_maker
from src.core.excel.parser import ExcelParser
from src.core.excel.schemas import ParsedFile
from src.core.excel.normalize import ExcelNormalizer
from src.core.excel.comment_extractor import extract_comments
from src.services.excel.repository import ExcelRepository
from src.services.rag.rag_service import rag_service


class ExcelIngestionService:
    def __init__(self, session: Optional[AsyncSession] = None):
        self._session = session

    async def _run_with_session(self, action, *, commit: bool = True):
        """Execute an async action with a session, creating one if needed."""
        if self._session:
            return await action(self._session)
        async with async_session_maker() as session:
            result = await action(session)
            if commit:
                await session.commit()
            return result

    async def process_file(self, file_path: Path) -> File:
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        if file_path.suffix.lower() not in ('.xlsx', '.xls'):
            raise ValueError(f"Not an Excel file: {file_path.suffix}")

        logger.info("Starting ingestion for file: {}", file_path)

        # 1. Парсим Excel
        parser = ExcelParser(file_path)
        parsed: ParsedFile = parser.parse()
        logger.info("Parsed {} sheets from {}", len(parsed.sheets), file_path.name)

        # 2. Нормализуем заголовки
        self._normalize_parsed(parsed)

        # 3. Сохраняем в БД (включая нормализованные fact_prices)
        async def _save(session):
            repo = ExcelRepository(session)
            return await repo.save_parsed_file(parsed)

        file_record = await self._run_with_session(_save)

        # 4. Извлекаем и сохраняем Excel-комментарии
        try:
            comments = extract_comments(file_path)
            if comments:
                async with async_session_maker() as session:
                    repo = ExcelRepository(session)
                    sheet_result = await session.execute(
                        select(Sheet).where(
                            Sheet.file_id == file_record.id,
                            Sheet.sheet_index == 0,
                        )
                    )
                    sheet_record = sheet_result.scalar_one_or_none()
                    if sheet_record:
                        await repo.save_comments(sheet_record.id, comments)
        except Exception as exc:
            logger.warning("Comment extraction failed (non-fatal): {}", exc)

        # 5. Индексируем файл в векторную БД + BM25
        try:
            logger.info("Indexing file {} in vector database...", file_record.id)
            await rag_service.build_index_for_file(file_record.id, session=self._session)
        except Exception as exc:
            logger.error(
                "Indexing failed for file_id={}, but file was saved: {}",
                file_record.id,
                exc,
            )

        logger.info("Ingestion complete: file_id={}, filename={}", file_record.id, file_record.filename)
        return file_record

    def _normalize_parsed(self, parsed: ParsedFile) -> None:
        for sheet in parsed.sheets:
            sheet.headers = [ExcelNormalizer.normalize_header(h) for h in sheet.headers]
            for header in sheet.headers:
                sample_values = ExcelNormalizer.extract_sample_values(sheet.data, header.col_name)
                col_type = ExcelNormalizer.infer_column_type(header, sample_values)
                logger.debug("Column '{}' → type={}, samples={}", header.col_name, col_type, sample_values[:3])

    async def get_file(self, file_id: int) -> Optional[File]:
        async def _get(session):
            result = await session.execute(select(File).where(File.id == file_id))
            return result.scalar_one_or_none()

        return await self._run_with_session(_get, commit=False)

    async def list_files(self, skip: int = 0, limit: int = 100) -> List[File]:
        async def _list(session):
            result = await session.execute(
                select(File).order_by(File.uploaded_at.desc()).offset(skip).limit(limit)
            )
            return list(result.scalars().all())

        return await self._run_with_session(_list, commit=False)

    async def delete_file(self, file_id: int) -> bool:
        async def _delete(session):
            result = await session.execute(select(File).where(File.id == file_id))
            file_record = result.scalar_one_or_none()
            if not file_record:
                return False
            await session.delete(file_record)
            await session.commit()
            logger.info("Deleted file id={}", file_id)
            return True

        return await self._run_with_session(_delete)