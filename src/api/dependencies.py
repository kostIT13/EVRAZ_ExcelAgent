from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Annotated

from src.core.db.database import get_db
from src.services.excel.ingestion_service import ExcelIngestionService
from src.services.db_tables.file_service.service import FileService
from src.services.db_tables.cell_service.service import CellService
from src.services.db_tables.column_service.service import ColumnService
from src.services.db_tables.query_log_service.service import TraceService
from src.services.db_tables.sheet_service.service import SheetService


async def get_excel_service(session: AsyncSession = Depends(get_db)):
    return ExcelIngestionService(session)


async def get_file_service(session: AsyncSession = Depends(get_db)):
    return FileService(session)


async def get_cell_service(session: AsyncSession = Depends(get_db)):
    return CellService(session)


async def get_column_service(session: AsyncSession = Depends(get_db)):
    return ColumnService(session)


async def get_trace_service(session: AsyncSession = Depends(get_db)):
    return TraceService(session)


async def get_sheet_service(session: AsyncSession = Depends(get_db)):
    return SheetService(session)


ExcelIngestionServiceDependency =  Annotated[ExcelIngestionService, Depends(get_excel_service)]
FileServiceDependency = Annotated[FileService, Depends(get_file_service)]
CellServiceDependency = Annotated[CellService, Depends(get_cell_service)]
ColumnServiceDependency = Annotated[ColumnService, Depends(get_column_service)]
TraceServiceDependency = Annotated[TraceService, Depends(get_trace_service)]
SheetServiceDependency = Annotated[SheetService, Depends(get_sheet_service)]

