from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from loguru import logger
from typing import Optional
from src.core.db.models import File, Sheet, ColumnMetadata, Cell
from src.core.excel.schemas import ParsedFile


class ExcelRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

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
            sheet_record = Sheet(
                file_id=file_record.id,
                sheet_index=sheet.sheet_index,
                original_name=sheet.sheet_name,
                normalized_name=self._normalize_name(sheet.sheet_name),
                row_count=len(sheet.data),
                col_count=len(sheet.headers),
            )
            self.session.add(sheet_record)
            await self.session.flush()

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

        await self.session.commit()
        await self.session.refresh(file_record)

        logger.info("Saved file id={}, sheets={}", file_record.id, file_record.total_sheets)
        return file_record

    async def _get_column_by_name(self, sheet_id: int, col_name: str) -> Optional[ColumnMetadata]:
        result = await self.session.execute(
            select(ColumnMetadata).where(
                ColumnMetadata.sheet_id == sheet_id,
                ColumnMetadata.normalized_name == col_name,
            )
        )
        return result.scalar_one_or_none()

    def _normalize_name(self, name: str) -> str:
        import re
        name = re.sub(r'[^\w\s]', '', name)
        name = re.sub(r'\s+', '_', name)
        name = name.lower().strip('_')
        return name or "unknown"