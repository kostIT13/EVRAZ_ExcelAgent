import re
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from loguru import logger
from typing import Any, Dict, List, Optional
from src.core.db.models import File, Sheet, ColumnMetadata, Cell, FactPrice, EntityDictionary, ExcelComment
from src.core.excel.schemas import ParsedFile
from src.core.excel.table_structurer import FactPriceRow, TableStructurer
from src.core.excel.comment_extractor import ParsedComment
from src.services.rag.entity_resolver import EntityResolver, normalize_name


class ExcelRepository:
    def __init__(self, session: AsyncSession):
        self.session = session
        self._entity_resolver = EntityResolver()

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
            # Определяем период из названия листа
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

            # Сохраняем колонки
            for header in sheet.headers:
                col_record = ColumnMetadata(
                    sheet_id=sheet_record.id,
                    col_index=header.col_index,
                    original_name=header.full_name,
                    normalized_name=header.col_name,
                    data_type="text",
                )
                self.session.add(col_record)
            await self.session.flush()

            # Сохраняем ячейки (original cells grid — для обратной совместимости)
            for row_idx, row_data in enumerate(sheet.data):
                for col_name, value in row_data.items():
                    if value is not None and value != "":
                        col_record = await self._get_column_by_name(sheet_record.id, col_name)
                        if col_record:
                            cell_record = Cell(
                                sheet_id=sheet_record.id,
                                row_num=row_idx + 1,
                                col_index=col_record.col_index,
                                value_text=str(value) if not isinstance(value, (int, float)) else None,
                                value_number=value if isinstance(value, (int, float)) else None,
                                original_value=str(value),
                            )
                            self.session.add(cell_record)

            # Сохраняем нормализованные факт-записи (FactPrice)
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
        """Сохраняет Excel-комментарии для листа."""
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
        """Структурирует лист в факт-таблицу и сохраняет."""
        structurer = TableStructurer(parsed_sheet)
        fact_rows: List[FactPriceRow] = structurer.structure()

        if not fact_rows:
            logger.debug("No fact rows for sheet '{}'", parsed_sheet.sheet_name)
            return

        # Собираем уникальные названия для entity resolution
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