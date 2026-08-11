import tempfile
from pathlib import Path
from typing import List
from fastapi import APIRouter, Depends, UploadFile, Query, Request
from fastapi import File as FastAPIFile
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.db.database import get_db
from src.core.logging_settings import logger
from src.api.errors import AppError, FileTooLargeError, ValidationError
from src.api.security import verify_api_key
from src.core.ratelimit import get_limiter, upload_limit

_limiter = get_limiter()
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
from src.api.dependencies import (
    CellServiceDependency,
    FileServiceDependency,
    SheetServiceDependency,
    ColumnServiceDependency,
    ExcelIngestionServiceDependency,
)


router = APIRouter(prefix="/files", tags=["files"])

ALLOWED_EXTENSIONS = {".xlsx", ".xls"}
MAX_FILE_SIZE = 50 * 1024 * 1024


@router.post("/upload", response_model=UploadResponse, status_code=201)
@_limiter.limit(upload_limit)
async def upload_file(
    request: Request,
    service: ExcelIngestionServiceDependency,
    file: UploadFile = FastAPIFile(...),
    _key: str = Depends(verify_api_key),
):
    request = request  # noqa: F841
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValidationError(
            f"Invalid file type '{suffix}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    # Читаем только MAX_FILE_SIZE + 1 байт, чтобы не загружать огромный файл в память.
    # Если файл больше лимита — сразу отклоняем, не читая его целиком.
    content = await file.read(MAX_FILE_SIZE + 1)
    if len(content) > MAX_FILE_SIZE:
        raise FileTooLargeError(
            f"File too large. Max: {MAX_FILE_SIZE} bytes"
        )

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        # Асинхронный ingestion: парсинг+нормализация уходят в фоновую очередь.
        # Клиент сразу получает file_id и опрашивает статус через GET /files/{id}.
        from src.services.excel.ingestion_queue import ingestion_queue
        file_id = await ingestion_queue.enqueue(tmp_path)
        file_record = await service.get_file(file_id)
        logger.info("File queued for processing: id={}, filename={}", file_id, file.filename)
        return UploadResponse(
            message="File uploaded, processing started asynchronously",
            file=FileResponse.model_validate(file_record),
        )
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


@router.get("/{file_id}/status", response_model=FileDetailResponse)
async def get_ingestion_status(
    file_id: int,
    service: FileServiceDependency,
):
    """Опрос статуса асинхронной обработки файла (uploaded/processing/ready/failed)."""
    from src.services.excel.ingestion_queue import ingestion_queue
    file_record = await service.get_by_id(file_id)
    status = ingestion_queue.get_status(file_id)
    if file_record and file_record.status == "ready":
        return FileDetailResponse.model_validate(file_record)
    if file_record:
        # Возвращаем текущий статус обработки.
        data = FileDetailResponse.model_validate(file_record).model_dump()
        data["status"] = status.get("status", file_record.status)
        return FileDetailResponse(**data)
    raise FileNotFoundError(f"File id={file_id} not found")


@router.get("", response_model=FileListResponse)
async def list_files(
    service: FileServiceDependency,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    status: str = Query(None, description="Filter by status: uploaded / processed / error"),
):
    files, total = await service.list_all(status=status, skip=skip, limit=limit)

    return FileListResponse(
        files=[FileResponse.model_validate(f) for f in files],
        total=total,
    )


@router.get("/{file_id}", response_model=FileDetailResponse)
async def get_file(
    file_id: int,
    service: FileServiceDependency,
):
    file_record = await service.get_by_id(file_id)
    return FileDetailResponse.model_validate(file_record)


@router.delete("/{file_id}", status_code=204)
async def delete_file(
    file_id: int,
    service: FileServiceDependency
):
    await service.delete(file_id)


@router.get("/{file_id}/sheets", response_model=List[SheetResponse])
async def get_file_sheets(
    file_id: int,
    service: SheetServiceDependency
):
    sheets = await service.list_by_file(file_id)
    return [SheetResponse.model_validate(s) for s in sheets]


@router.get("/{file_id}/sheets/{sheet_id}", response_model=SheetDetailResponse)
async def get_sheet_detail(
    file_id: int,
    sheet_id: int,
    service: SheetServiceDependency
):
    sheet = await service.get_detail(file_id, sheet_id)
    return SheetDetailResponse.model_validate(sheet)


@router.get("/{file_id}/sheets/{sheet_id}/columns", response_model=List[ColumnResponse])
async def get_sheet_columns(
    file_id: int,
    sheet_id: int,
    service: ColumnServiceDependency
):
    columns = await service.list_by_sheet(file_id, sheet_id)
    return [ColumnResponse.model_validate(c) for c in columns]


@router.get("/{file_id}/sheets/{sheet_id}/cells", response_model=List[CellResponse])
async def get_sheet_cells(
    file_id: int,
    sheet_id: int,
    service: CellServiceDependency,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=10000)
):
    cells = await service.list_by_sheet(file_id, sheet_id, skip=skip, limit=limit)
    return [CellResponse.model_validate(c) for c in cells]


@router.post("/{file_id}/reindex", status_code=200)
async def reindex_file(
    file_id: int,
    service: FileServiceDependency,
):
    """Пересоздаёт mart.price_facts и справочники сущностей для файла.

    Векторный RAG-индекс (Qdrant) удалён из архитектуры, поэтому переиндексация
    означает повторную нормализацию raw.cells -> mart.price_facts и пересборку
    списка сущностей для pg_trgm-сопоставления.
    """
    await service.get_by_id(file_id)

    from src.services.mart.normalizer import normalize_file_to_mart
    from src.services.excel.repository import SQLAlchemyExcelRepository

    logger.info("Reindexing file id={}", file_id)
    async with get_db() as session:
        repo = SQLAlchemyExcelRepository(session)
        stats = await normalize_file_to_mart(file_id, session=session)
        entity_stats = await repo.index_entities(file_id)
    logger.info(
        "Reindex complete for file id={}: mart={}, entities={}",
        file_id,
        stats,
        entity_stats,
    )
    return {"message": f"File {file_id} reindexed successfully"}
