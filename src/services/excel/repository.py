import re
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import insert, select
from loguru import logger
from typing import Any, Dict, List, Optional
from src.core.db.models import File, Sheet, ColumnMetadata, Cell, FactPrice, EntityDictionary, ExcelComment
from src.core.excel.schemas import ParsedFile
from src.core.excel.table_structurer import FactPriceRow, TableStructurer
from src.core.excel.comment_extractor import ParsedComment
from src.services.rag.entity_resolver import EntityResolver, normalize_name
from src.services.excel.base import ExcelRepository


class SQLAlchemyExcelRepository(ExcelRepository):
    def __init__(self, session: AsyncSession):
        self.session = session
        self._entity_resolver = EntityResolver()

    async def process_file(self, file_path: Path) -> File:
        """Полный цикл обработки Excel-файла: парсинг, нормализация, сохранение."""
        from src.core.excel.parser import ExcelParser
        from src.core.excel.normalize import ExcelNormalizer
        from src.core.excel.comment_extractor import extract_comments
        from src.services.rag.rag_service import rag_service

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
        for sheet in parsed.sheets:
            sheet.headers = [ExcelNormalizer.normalize_header(h) for h in sheet.headers]
            for header in sheet.headers:
                sample_values = ExcelNormalizer.extract_sample_values(sheet.data, header.col_name)
                col_type = ExcelNormalizer.infer_column_type(header, sample_values)
                logger.debug("Column '{}' → type={}, samples={}", header.col_name, col_type, sample_values[:3])

        # 3. Сохраняем в БД
        file_record = await self.save_parsed_file(parsed)

        # 4. Извлекаем и сохраняем Excel-комментарии
        try:
            comments = extract_comments(file_path)
            if comments:
                sheet_result = await self.session.execute(
                    select(Sheet).where(
                        Sheet.file_id == file_record.id,
                        Sheet.sheet_index == 0,
                    )
                )
                sheet_record = sheet_result.scalar_one_or_none()
                if sheet_record:
                    await self.save_comments(sheet_record.id, comments)
        except Exception as exc:
            logger.warning("Comment extraction failed (non-fatal): {}", exc)

        # 5. Индексация в векторной БД
        logger.info("Indexing file {} in vector database...", file_record.id)
        await rag_service.build_index_for_file(file_record.id, session=self.session)

        logger.info("Ingestion complete: file_id={}, filename={}", file_record.id, file_record.filename)
        return file_record

    async def get_file(self, file_id: int) -> Optional[File]:
        result = await self.session.execute(
            select(File).where(File.id == file_id)
        )
        return result.scalar_one_or_none()

    async def list_files(self, skip: int = 0, limit: int = 100) -> List[File]:
        result = await self.session.execute(
            select(File).order_by(File.uploaded_at.desc()).offset(skip).limit(limit)
        )
        return list(result.scalars().all())

    async def delete_file(self, file_id: int) -> bool:
        result = await self.session.execute(
            select(File).where(File.id == file_id)
        )
        file_record = result.scalar_one_or_none()
        if not file_record:
            return False
        await self.session.delete(file_record)
        await self.session.commit()
        logger.info("Deleted file id={}", file_id)
        return True

    async def save_parsed_file(self, parsed: ParsedFile) -> File:
        file_record = File(
            filename=parsed.filename,
            file_hash=parsed.file_hash,
            total_sheets=len(parsed.sheets),
            status="processed",
        )
        self.session.add(file_record)
        await self.session.flush()

        for sheet in parsed.sheets:
            period = TableStructurer(sheet).period

            sheet_record = Sheet(
                file_id=file_record.id,
                sheet_index=sheet.sheet_index,
                original_name=sheet.sheet_name,
                normalized_name=self._normalize_name(sheet.sheet_name),
                period=period,
                row_count=len(sheet.data),
                col_count=len(sheet.headers),
            )
            self.session.add(sheet_record)
            await self.session.flush()

            # Предзагружаем маппинг "нормализованное имя колонки → ColumnMetadata".
            # Раньше для каждой ячейки выполнялся отдельный SELECT (_get_column_by_name),
            # что давало N+1 запросов к БД при большом количестве ячеек.
            col_by_name: Dict[str, ColumnMetadata] = {}
            for header in sheet.headers:
                col_record = ColumnMetadata(
                    sheet_id=sheet_record.id,
                    col_index=header.col_index,
                    original_name=header.full_name,
                    normalized_name=header.col_name,
                    data_type="text",
                )
                self.session.add(col_record)
                col_by_name[header.col_name] = col_record
            await self.session.flush()

            # Bulk-insert ячеек: раньше каждая ячейка добавлялась через session.add(),
            # что при тысячах ячеек давало тысячи отдельных ORM-операций. Теперь
            # собираем все ячейки листа и вставляем одним insert-запросом.
            cell_rows = []
            for row_idx, row_data in enumerate(sheet.data):
                for col_name, value in row_data.items():
                    if value is not None and value != "":
                        col_record = col_by_name.get(col_name)
                        if col_record:
                            cell_rows.append({
                                "sheet_id": sheet_record.id,
                                "row_num": row_idx + 1,
                                "col_index": col_record.col_index,
                                "value_text": str(value) if not isinstance(value, (int, float)) else None,
                                "value_number": value if isinstance(value, (int, float)) else None,
                                "original_value": str(value),
                            })
            if cell_rows:
                await self.session.execute(insert(Cell), cell_rows)

            await self._save_fact_prices(sheet_record, sheet)

        await self.session.commit()
        await self.session.refresh(file_record)

        logger.info(
            "Saved file id={}, sheets={}, fact_prices=auto",
            file_record.id,
            file_record.total_sheets,
        )
        return file_record

    async def save_comments(
        self,
        sheet_id: int,
        comments: List[ParsedComment],
    ) -> None:
        for comment in comments:
            record = ExcelComment(
                sheet_id=sheet_id,
                cell_ref=comment.cell_ref,
                row_num=comment.row_num,
                col_index=comment.col_index,
                author=comment.author,
                text=comment.text,
            )
            self.session.add(record)

        if comments:
            await self.session.commit()
            logger.info("Saved {} comments for sheet_id={}", len(comments), sheet_id)

    async def _save_fact_prices(
        self,
        sheet_record: Sheet,
        parsed_sheet: Any,
    ) -> None:
        structurer = TableStructurer(parsed_sheet)
        fact_rows: List[FactPriceRow] = structurer.structure()

        if not fact_rows:
            logger.debug("No fact rows for sheet '{}'", parsed_sheet.sheet_name)
            return
        
        unique_names = list(set(r.item_name_raw for r in fact_rows))
        resolved = await self._entity_resolver.resolve_batch(unique_names, session=self.session)

        for fact_row in fact_rows:
            entity_id, canonical_name = resolved.get(
                fact_row.item_name_raw,
                (None, fact_row.item_name_normalized),
            )

            record = FactPrice(
                sheet_id=sheet_record.id,
                item_id=entity_id,
                period=fact_row.period,
                item_name_raw=fact_row.item_name_raw,
                item_name_normalized=canonical_name,
                price_source=fact_row.price_source,
                price_value=fact_row.price_value,
                row_num=fact_row.row_num,
            )
            self.session.add(record)

        logger.info(
            "Saved {} fact prices for sheet '{}' (period={})",
            len(fact_rows),
            parsed_sheet.sheet_name,
            structurer.period,
        )

    async def _get_column_by_name(self, sheet_id: int, col_name: str) -> Optional[ColumnMetadata]:
        result = await self.session.execute(
            select(ColumnMetadata).where(
                ColumnMetadata.sheet_id == sheet_id,
                ColumnMetadata.normalized_name == col_name,
            )
        )
        return result.scalar_one_or_none()

    def _normalize_name(self, name: str) -> str:
        name = re.sub(r'[^\w\s]', '', name)
        name = re.sub(r'\s+', '_', name)
        name = name.lower().strip('_')
        return name or "unknown"