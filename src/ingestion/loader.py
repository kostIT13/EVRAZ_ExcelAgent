"""
Загрузка нормализованных данных в PostgreSQL через SQLAlchemy.
"""
import hashlib
import re
from datetime import datetime, timezone

import pandas as pd

from src.core.db.models import File, Sheet, ColumnMetadata, Cell
from src.core.db.database import async_session_maker
from src.core.logging_settings import logger


async def load_file(
    filename: str,
    parsed_data: dict,
    normalized_df,
    file_hash: str = None
) -> int:
    if file_hash is None:
        file_hash = hashlib.sha256(filename.encode()).hexdigest()
    
    async with async_session_maker() as session:
        db_file = File(
            filename=filename,
            file_hash=file_hash,
            total_sheets=len(parsed_data),
            total_rows=len(normalized_df),
            total_cells=len(normalized_df),
            status="processing",
            uploaded_at=datetime.now(timezone.utc)
        )
        session.add(db_file)
        await session.flush()
        
        total_cells = 0
        
        # Для каждого листа из сырых данных (нужны для структуры)
        for sheet_idx, (sheet_name, raw_df) in enumerate(parsed_data.items()):
            month = _extract_month(sheet_name)
            normalized_name = month or f"sheet_{sheet_idx}"
            
            db_sheet = Sheet(
                file_id=db_file.id,
                sheet_index=sheet_idx,
                original_name=sheet_name,
                normalized_name=normalized_name,
                description=f"Цены на лом цветных металлов за {month}",
                row_count=len(raw_df),
                col_count=len(raw_df.columns)
            )
            session.add(db_sheet)
            await session.flush()
            
            # Создаём колонки для нормализованных данных
            norm_columns = {
                'месяц': ColumnMetadata(sheet_id=db_sheet.id, col_index=0, original_name='месяц', normalized_name='mesyac', data_type='text'),
                'наименование': ColumnMetadata(sheet_id=db_sheet.id, col_index=1, original_name='наименование', normalized_name='naimenovanie', data_type='text'),
                'поставщик': ColumnMetadata(sheet_id=db_sheet.id, col_index=2, original_name='поставщик', normalized_name='postavshchik', data_type='text'),
                'цена': ColumnMetadata(sheet_id=db_sheet.id, col_index=3, original_name='цена', normalized_name='cena', data_type='number'),
                'тип_цены': ColumnMetadata(sheet_id=db_sheet.id, col_index=4, original_name='тип_цены', normalized_name='tip_ceny', data_type='text'),
            }
            for col in norm_columns.values():
                session.add(col)
            await session.flush()
            
            # Грузим нормализованные данные
            sheet_data = normalized_df[normalized_df['месяц'] == month]
            for row_idx, (_, row) in enumerate(sheet_data.iterrows()):
                for col_name, db_col in norm_columns.items():
                    value = row.get(col_name)
                    if value is None or (isinstance(value, float) and pd.isna(value)):
                        continue
                    
                    value_text = str(value) if not isinstance(value, (int, float)) else None
                    value_number = float(value) if isinstance(value, (int, float)) else None
                    
                    db_cell = Cell(
                        sheet_id=db_sheet.id,
                        row_num=row_idx + 1,
                        col_index=db_col.col_index,
                        value_text=value_text,
                        value_number=value_number,
                        original_value=str(value)
                    )
                    session.add(db_cell)
                    total_cells += 1
        
        db_file.total_cells = total_cells
        db_file.status = "processed"
        db_file.processed_at = datetime.now(timezone.utc)
        
        await session.commit()
        logger.info(f"File {filename} loaded: {db_file.total_sheets} sheets, {total_cells} cells")
        return db_file.id



def _extract_month(sheet_name: str) -> str:
    match = re.search(r'\(на\s+(\w+\d+)\)', sheet_name)
    return match.group(1) if match else sheet_name


def _normalize_name(name: str) -> str:
    name = name.lower()
    name = re.sub(r'[^a-zа-яё0-9\s]', '', name)
    name = re.sub(r'\s+', '_', name)
    return name.strip('_') or 'unknown'


def _detect_data_type(df, col_name: str) -> str:
    non_null = df[col_name].dropna()
    if len(non_null) == 0:
        return 'text'
    numeric_count = sum(1 for v in non_null if isinstance(v, (int, float)))
    return 'number' if numeric_count == len(non_null) else 'text'


if __name__ == '__main__':
    import asyncio
    from src.ingestion.parser import parse_excel
    from src.ingestion.normalizer import normalize_all
    
    async def test():
        parsed = parse_excel('data/data_proportional_prices.xlsx')
        normalized = normalize_all(parsed)
        file_id = await load_file(
            filename='data_proportional_prices.xlsx',
            parsed_data=parsed,
            normalized_df=normalized
        )
        print(f'File loaded with ID: {file_id}')
    
    asyncio.run(test())
