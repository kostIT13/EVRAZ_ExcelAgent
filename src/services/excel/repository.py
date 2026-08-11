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
from src.services.entity_resolution.entity_resolver import EntityResolver, entity_resolver
from src.services.excel.base import ExcelRepository


class SQLAlchemyExcelRepository(ExcelRepository):
    def __init__(self, session: AsyncSession):
        self.session = session
        self._entity_resolver = EntityResolver()

    async def process_file(self, file_path: Path) -> File:
        """Полный цикл обработки Excel-файла: парсинг raw, нормализация в mart.

        Тяжёлый RAG-over-cells (chunk/sheet/column эмбеддинги) НЕ строится.
        Вместо него на этапе ingestion заполняется mart.price_facts и собираются
        уникальные сущности (item/supplier/period) для pg_trgm-сопоставления.
        Это делает индексацию секундами вместо минут.
        """
        from src.core.excel.parser import ExcelParser
        from src.core.excel.normalize import ExcelNormalizer
        from src.core.excel.comment_extractor import extract_comments

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

        # 3. Сохраняем в БД (raw + fact_prices)
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

        # 5. Нормализация в mart.price_facts и entity-resolution выполняются в
        #    ingestion_service.process_file (после возврата file_record), чтобы
        #    держать raw-парсинг и mart-нормализацию как отдельные идемпотентные шаги.

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

    async def save_pending_file(self, parsed: ParsedFile) -> File:
        """Создаёт запись File со статусом 'uploaded' до фоновой обработки.

        Если файл с таким file_hash уже существует (например, повторная загрузка
        одного и того же файла), не пытаемся вставить дубликат — возвращаем уже
        существующую запись. Иначе повторная загрузка упадёт с unique constraint
        ix_files_file_hash.
        """
        result = await self.session.execute(
            select(File).where(File.file_hash == parsed.file_hash)
        )
        file_record = result.scalar_one_or_none()
        if file_record is not None:
            file_record.filename = parsed.filename
            file_record.total_sheets = len(parsed.sheets)
            file_record.status = "uploaded"
            file_record.error_message = None
            await self.session.commit()
            return file_record

        file_record = File(
            filename=parsed.filename,
            file_hash=parsed.file_hash,
            total_sheets=len(parsed.sheets),
            status="uploaded",
        )
        self.session.add(file_record)
        await self.session.commit()
        await self.session.refresh(file_record)
        return file_record

    async def save_parsed_file(self, parsed: ParsedFile) -> File:
        # В асинхронном пайплайне запись File уже создана на этапе create_pending_file()
        # (статус "uploaded"), и повторная вставка по тому же file_hash упрётся в
        # unique constraint ix_files_file_hash. Поэтому переиспользуем существующую
        # запись, обновляя её поля, либо создаём новую, если её ещё нет.
        result = await self.session.execute(
            select(File).where(File.file_hash == parsed.file_hash)
        )
        file_record = result.scalar_one_or_none()
        if file_record is None:
            file_record = File(
                filename=parsed.filename,
                file_hash=parsed.file_hash,
                total_sheets=len(parsed.sheets),
                status="processed",
            )
            self.session.add(file_record)
        else:
            file_record.filename = parsed.filename
            file_record.total_sheets = len(parsed.sheets)
            file_record.status = "processed"
            file_record.error_message = None
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
        
        for fact_row in fact_rows:
            # Entity-resolution (item_id в entity_dictionary) выполняется отдельно
            # на этапе index_entities() после сохранения mart.price_facts, а поиск
            # сущностей в рантайме — через pg_trgm (resolve_candidates). Поэтому
            # здесь item_id не проставляем (None), а item_name_normalized используем
            # как каноническое имя для pg_trgm-сопоставления.
            record = FactPrice(
                sheet_id=sheet_record.id,
                item_id=None,
                period=fact_row.period,
                item_name_raw=fact_row.item_name_raw,
                item_name_normalized=fact_row.item_name_normalized,
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

    async def index_entities(self, file_id: int) -> Dict[str, int]:
        """Собирает уникальные значения сущностей (item/supplier/period) из mart.price_facts.

        Без эмбеддингов: уникальные значения трёх справочников (десятки–сотни
        записей) кэшируются в памяти для pg_trgm-резолюции и передачи в промпт.
        """
        items: List[str] = []
        suppliers: List[str] = []
        periods: List[str] = []

        sheets_result = await self.session.execute(
            select(Sheet).where(Sheet.file_id == file_id)
        )
        sheets = list(sheets_result.scalars().all())

        for sheet in sheets:
            if sheet.period:
                periods.append(sheet.period)

            facts_result = await self.session.execute(
                select(FactPrice).where(FactPrice.sheet_id == sheet.id)
            )
            for fp in facts_result.scalars().all():
                if fp.item_name_normalized:
                    items.append(fp.item_name_normalized)
                if fp.price_source:
                    suppliers.append(fp.price_source)

        # Fallback: если fact_prices пусты, берём item-колонку из cells.
        if not items:
            for sheet in sheets:
                cols_result = await self.session.execute(
                    select(ColumnMetadata)
                    .where(ColumnMetadata.sheet_id == sheet.id)
                    .order_by(ColumnMetadata.col_index)
                )
                item_col = next((c for c in cols_result.scalars().all() if c.col_index == 2), None)
                if item_col:
                    cells_result = await self.session.execute(
                        select(Cell)
                        .where(Cell.sheet_id == sheet.id, Cell.col_index == item_col.col_index)
                    )
                    for cell in cells_result.scalars().all():
                        val = cell.value_text or str(cell.value_number or "")
                        if val.strip():
                            items.append(val.strip())

        return await entity_resolver.index_entities(
            items=items,
            suppliers=suppliers,
            periods=periods,
            session=self.session,
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