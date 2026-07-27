import tempfile
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, UploadFile, HTTPException, Query
from fastapi import File as FastAPIFile
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.db.database import get_db
from src.core.db.models import File as DBFile, Sheet, ColumnMetadata, Cell
from src.core.logging_settings import logger
from src.services.excel.ingestion_service import ExcelIngestionService
from src.services.rag.rag_service import rag_service

from src.api.schemas import (
    FileResponse,
    FileListResponse,
    FileDetailResponse,
    SheetResponse,
    SheetDetailResponse,
    ColumnResponse,
    CellResponse,
    UploadResponse,
)

router = APIRouter(prefix="/files", tags=["files"])

ALLOWED_EXTENSIONS = {".xlsx", ".xls"}
MAX_FILE_SIZE = 50 * 1024 * 1024



@router.post("/upload", response_model=UploadResponse, status_code=201)
async def upload_file(
    file: UploadFile = FastAPIFile(...),
    session: AsyncSession = Depends(get_db),
):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type '{suffix}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large ({len(content)} bytes). Max: {MAX_FILE_SIZE} bytes",
        )

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        service = ExcelIngestionService(session)
        file_record = await service.process_file(tmp_path)

        logger.info("File uploaded successfully: id={}, filename={}", file_record.id, file_record.filename)

        return UploadResponse(
            message="File uploaded and processed successfully",
            file=FileResponse.model_validate(file_record),
        )

    except FileNotFoundError:
        raise HTTPException(status_code=400, detail="File not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Upload failed: {}", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


@router.get("", response_model=FileListResponse)
async def list_files(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    status: str = Query(None, description="Filter by status: uploaded / processed / error"),
    session: AsyncSession = Depends(get_db),
):
    query = select(DBFile)

    if status:
        query = query.where(DBFile.status == status)

    count_query = select(func.count()).select_from(query.subquery())
    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0

    query = query.order_by(DBFile.uploaded_at.desc()).offset(skip).limit(limit)
    result = await session.execute(query)
    files = list(result.scalars().all())

    return FileListResponse(
        files=[FileResponse.model_validate(f) for f in files],
        total=total,
    )



@router.get("/{file_id}", response_model=FileDetailResponse)
async def get_file(
    file_id: int,
    session: AsyncSession = Depends(get_db),
):
    result = await session.execute(
        select(DBFile)
        .options(selectinload(DBFile.sheets).selectinload(Sheet.columns))
        .where(DBFile.id == file_id)
    )
    file_record = result.scalar_one_or_none()

    if not file_record:
        raise HTTPException(status_code=404, detail=f"File with id={file_id} not found")

    return FileDetailResponse.model_validate(file_record)


@router.delete("/{file_id}", status_code=204)
async def delete_file(
    file_id: int,
    session: AsyncSession = Depends(get_db),
):
    result = await session.execute(select(DBFile).where(DBFile.id == file_id))
    file_record = result.scalar_one_or_none()

    if not file_record:
        raise HTTPException(status_code=404, detail=f"File with id={file_id} not found")

    await session.delete(file_record)
    await session.flush()
    logger.info("Deleted file id={}", file_id)



@router.get("/{file_id}/sheets", response_model=List[SheetResponse])
async def get_file_sheets(
    file_id: int,
    session: AsyncSession = Depends(get_db),
):
    file_result = await session.execute(select(DBFile).where(DBFile.id == file_id))
    if not file_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail=f"File with id={file_id} not found")

    result = await session.execute(
        select(Sheet).where(Sheet.file_id == file_id).order_by(Sheet.sheet_index)
    )
    sheets = list(result.scalars().all())

    return [SheetResponse.model_validate(s) for s in sheets]


@router.get("/{file_id}/sheets/{sheet_id}", response_model=SheetDetailResponse)
async def get_sheet_detail(
    file_id: int,
    sheet_id: int,
    session: AsyncSession = Depends(get_db),
):
    result = await session.execute(
        select(Sheet)
        .options(selectinload(Sheet.columns))
        .where(Sheet.id == sheet_id, Sheet.file_id == file_id)
    )
    sheet = result.scalar_one_or_none()

    if not sheet:
        raise HTTPException(status_code=404, detail=f"Sheet with id={sheet_id} not found")

    return SheetDetailResponse.model_validate(sheet)


@router.get("/{file_id}/sheets/{sheet_id}/columns", response_model=List[ColumnResponse])
async def get_sheet_columns(
    file_id: int,
    sheet_id: int,
    session: AsyncSession = Depends(get_db),
):
    sheet_result = await session.execute(
        select(Sheet).where(Sheet.id == sheet_id, Sheet.file_id == file_id)
    )
    if not sheet_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail=f"Sheet with id={sheet_id} not found")

    result = await session.execute(
        select(ColumnMetadata).where(ColumnMetadata.sheet_id == sheet_id).order_by(ColumnMetadata.col_index)
    )
    columns = list(result.scalars().all())

    return [ColumnResponse.model_validate(c) for c in columns]


@router.get("/{file_id}/sheets/{sheet_id}/cells", response_model=List[CellResponse])
async def get_sheet_cells(
    file_id: int,
    sheet_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=10000),
    session: AsyncSession = Depends(get_db),
):
    sheet_result = await session.execute(
        select(Sheet).where(Sheet.id == sheet_id, Sheet.file_id == file_id)
    )
    if not sheet_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail=f"Sheet with id={sheet_id} not found")

    result = await session.execute(
        select(Cell)
        .where(Cell.sheet_id == sheet_id)
        .order_by(Cell.row_num, Cell.col_index)
        .offset(skip)
        .limit(limit)
    )
    cells = list(result.scalars().all())

    return [CellResponse.model_validate(c) for c in cells]


@router.post("/{file_id}/reindex", status_code=200)
async def reindex_file(
    file_id: int,
    session: AsyncSession = Depends(get_db),
):
    file_result = await session.execute(
        select(DBFile).where(DBFile.id == file_id)
    )
    if not file_result.scalar_one_or_none():
        raise HTTPException(
            status_code=404, detail=f"File with id={file_id} not found"
        )

    logger.info("Reindexing file id={}", file_id)
    await rag_service.build_index_for_file(file_id, session=session)
    logger.info("Reindex complete for file id={}", file_id)

    return {"message": f"File {file_id} reindexed successfully"}