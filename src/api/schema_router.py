"""API для Schema Inference / Template Fingerprint: подтверждение LLM-схем листов.

Реализует:
- POST /files/{file_id}/sheets/{sheet_id}/infer-schema — вызвать LLM-распознавание.
- POST /files/{file_id}/sheets/{sheet_id}/confirm-schema — подтвердить схему
  (пользователь принял/исправил распознанную структуру), сохранить в
  mart.sheet_templates как confirmed и переиспользовать для похожих файлов.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db.database import get_db
from src.core.db.models import Sheet, SheetTemplate
from src.core.excel.schema_inference import (
    SheetSchema,
    schema_inference_service,
    serialize_cells_grid,
)
from src.core.excel.template_fingerprint import compute_sheet_fingerprint
from src.core.logging_settings import logger
from src.core.db.models import Cell, ColumnMetadata


router = APIRouter(prefix="/files", tags=["schema"])


class ConfirmSchemaRequest(BaseModel):
    sheet_schema: Dict[str, Any]
    confirmed_by: Optional[str] = "user"


async def _load_sheet_context(session: AsyncSession, file_id: int, sheet_id: int) -> Dict[str, Any]:
    """Загружает сырую сетку ячеек листа и merged cells для fingerprint/inference."""
    sheet_result = await session.execute(
        select(Sheet).where(Sheet.id == sheet_id, Sheet.file_id == file_id)
    )
    sheet = sheet_result.scalar_one_or_none()
    if not sheet:
        raise HTTPException(status_code=404, detail="Sheet not found")

    cells_result = await session.execute(
        select(Cell).where(Cell.sheet_id == sheet_id)
    )
    grid: Dict[str, Any] = {}
    for cell in cells_result.scalars().all():
        coord = _coord(cell.row_num, cell.col_index)
        val = cell.value_text if cell.value_text is not None else cell.value_number
        if val is not None:
            grid[coord] = val

    return {"sheet": sheet, "grid": grid}


def _coord(row_num: int, col_index: int) -> str:
    col_letter = _col_letter(col_index)
    return f"{col_letter}{row_num}"


def _col_letter(index: int) -> str:
    letters = ""
    while index >= 0:
        letters = chr(65 + (index % 26)) + letters
        index = index // 26 - 1
    return letters


@router.post("/{file_id}/sheets/{sheet_id}/infer-schema")
async def infer_schema(
    file_id: int,
    sheet_id: int,
    session: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    ctx = await _load_sheet_context(session, file_id, sheet_id)
    sheet = ctx["sheet"]
    grid = ctx["grid"]

    fingerprint = compute_sheet_fingerprint(grid)
    existing = await session.execute(
        select(SheetTemplate).where(SheetTemplate.fingerprint == fingerprint)
    )
    template = existing.scalar_one_or_none()
    if template and template.status == "confirmed" and template.schema_json:
        logger.info(
            "infer_schema: confirmed template cache hit for sheet {}",
            sheet_id,
        )
        return {
            "fingerprint": fingerprint,
            "from_cache": True,
            "status": template.status,
            "schema_json": template.schema_json,
        }

    grid_text = serialize_cells_grid(grid)
    inferred: SheetSchema = await schema_inference_service.infer(
        cells_grid=grid_text,
        sheet_name=sheet.original_name,
    )

    # Сохраняем результат со статусом pending_confirmation, не пишем в mart.price_facts.
    if template is None:
        session.add(SheetTemplate(
            fingerprint=fingerprint,
            schema_json=inferred.model_dump(),
            sheet_name_pattern=sheet.original_name,
            status="pending_confirmation",
            confidence=inferred.confidence,
        ))
        await session.commit()

    return {
        "fingerprint": fingerprint,
        "from_cache": False,
        "status": "pending_confirmation",
        "schema_json": inferred.model_dump(),
        "confidence": inferred.confidence,
        "notes": inferred.notes,
    }


@router.post("/{file_id}/sheets/{sheet_id}/confirm-schema")
async def confirm_schema(
    file_id: int,
    sheet_id: int,
    request: ConfirmSchemaRequest,
    session: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    from datetime import datetime, timezone

    ctx = await _load_sheet_context(session, file_id, sheet_id)
    fingerprint = compute_sheet_fingerprint(ctx["grid"])

    result = await session.execute(
        select(SheetTemplate).where(SheetTemplate.fingerprint == fingerprint)
    )
    template = result.scalar_one_or_none()
    if template is None:
        template = SheetTemplate(
            fingerprint=fingerprint,
            sheet_name_pattern=ctx["sheet"].original_name,
        )
        session.add(template)

    template.schema_json = request.sheet_schema
    template.status = "confirmed"
    template.confirmed_by = request.confirmed_by
    template.confidence = float(request.sheet_schema.get("confidence", 0.0))
    template.confirmed_at = datetime.now(timezone.utc)
    await session.commit()

    logger.info(
        "confirm_schema: confirmed template for sheet {} (file {}), fingerprint={}",
        sheet_id,
        file_id,
        fingerprint[:12],
    )
    return {
        "fingerprint": fingerprint,
        "status": "confirmed",
        "schema_json": template.schema_json,
    }