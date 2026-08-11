"""Нормализация raw.cells -> mart.price_facts (итеративный, идемпотентный).

Вместо генерации SQL по EAV cells агент работает по нормализованной long-таблице
``mart.price_facts``. Нормализация использует подтверждённую LLM-схему листа
(``mart.sheet_templates``) для интерпретации многострочных/вложенных заголовков,
сдвинутых шапок и слитых ячеек (см. src/core/excel/schema_inference.py).

Идемпотентность: перезалив файла (тот же file_id) удаляет существующие факты
файла и пересоздаёт их — без дублирования.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db.database import async_session_maker
from src.core.db.models import Cell, ColumnMetadata, FactPrice, PriceFact, Sheet, SheetTemplate
from src.core.excel.schemas import ParsedSheet
from src.core.excel.schema_inference import ColumnInference, SheetSchema
from src.core.logging_settings import logger

# Специальные price_source, распознаваемые табличным структуратором.
INTERNAL_SOURCES = {"среднерыночная", "аукцион_старт", "аукцион_победитель"}

DEFAULT_UNIT = "тн"
DEFAULT_CURRENCY = "RUB"


async def normalize_file_to_mart(
    file_id: int,
    session: Optional[AsyncSession] = None,
) -> Dict[str, int]:
    """Идемпотентно заполняет mart.price_facts для данного file_id.

    Сначала удаляет существующие факты файла, затем пересчитывает их из raw.
    Returns:
        Словарь со статистикой: {"deleted": int, "inserted": int, "elapsed_ms": int}.
    """
    start = time.monotonic()
    own_session = session is None
    s = session or async_session_maker()
    try:
        # 1. Удаляем старые факты файла (идемпотентность при перезаливе).
        result = await s.execute(delete(PriceFact).where(PriceFact.file_id == file_id))
        deleted = result.rowcount or 0

        # 2. Собираем факты из raw.
        fact_rows: List[PriceFact] = []
        sheets_result = await s.execute(
            select(Sheet).where(Sheet.file_id == file_id)
        )
        for sheet in list(sheets_result.scalars().all()):
            fact_rows.extend(await _fact_rows_for_sheet(s, sheet, file_id))

        if fact_rows:
            s.add_all(fact_rows)
            await s.commit()

        elapsed_ms = int((time.monotonic() - start) * 1000)
        logger.info(
            "normalize_file_to_mart: file_id={}, deleted={}, inserted={}, elapsed={}ms",
            file_id,
            deleted,
            len(fact_rows),
            elapsed_ms,
        )
        return {"deleted": deleted, "inserted": len(fact_rows), "elapsed_ms": elapsed_ms}
    except Exception:
        await s.rollback()
        raise
    finally:
        if own_session:
            await s.close()


async def _fact_rows_for_sheet(
    s: AsyncSession,
    sheet: Sheet,
    file_id: int,
) -> List[PriceFact]:
    """Строит список mart.price_facts для одного листа из raw."""
    # Пытаемся использовать табличный структуратор из уже сохранённых FactPrice
    # (fact_prices) как источник фактов — он уже учитывает merged cells и шапку.
    fact_result = await s.execute(
        select(FactPrice).where(FactPrice.sheet_id == sheet.id)
    )
    legacy = list(fact_result.scalars().all())

    rows: List[PriceFact] = []
    if legacy:
        for fp in legacy:
            price_type, supplier = _split_source(fp.price_source)
            rows.append(PriceFact(
                file_id=file_id,
                sheet_id=sheet.id,
                source_row_ref=f"sheet:{sheet.id}:row:{fp.row_num}",
                sheet_period=fp.period,
                item_name=fp.item_name_normalized,
                supplier=supplier,
                price_type=price_type,
                value=fp.price_value,
                currency=DEFAULT_CURRENCY,
                unit=DEFAULT_UNIT,
            ))
        return rows

    # Schema-driven нормализация: если для листа есть подтверждённый шаблон
    # (mart.sheet_templates), используем его для интерпретации колонок.
    schema_rows = await _fact_rows_from_schema(s, sheet, file_id)
    if schema_rows:
        return schema_rows

    # Fallback: если факты не сохранены, парсим из cells.
    return await _fact_rows_from_cells(s, sheet, file_id)


async def _find_confirmed_template(
    s: AsyncSession,
    sheet: Sheet,
) -> Optional[SheetSchema]:
    """Ищет подтверждённый шаблон листа в mart.sheet_templates."""
    from src.core.excel.template_fingerprint import compute_sheet_fingerprint

    # Собираем координаты непустых ячеек листа (первые 30 строк) для fingerprint.
    cells_result = await s.execute(
        select(Cell)
        .where(Cell.sheet_id == sheet.id)
        .order_by(Cell.row_num, Cell.col_index)
        .limit(30 * 64)
    )
    grid: Dict[str, Any] = {}
    for cell in cells_result.scalars().all():
        if cell.row_num <= 30:
            coord = _coord(cell.row_num, cell.col_index)
            val = cell.value_text if cell.value_text is not None else cell.value_number
            if val is not None:
                grid[coord] = val

    if not grid:
        return None

    fingerprint = compute_sheet_fingerprint(grid)
    result = await s.execute(
        select(SheetTemplate).where(
            SheetTemplate.fingerprint == fingerprint,
            SheetTemplate.status == "confirmed",
        )
    )
    template = result.scalar_one_or_none()
    if template and template.schema_json:
        try:
            return SheetSchema.model_validate(template.schema_json)
        except Exception:
            return None
    return None


def _coord(row_num: int, col_index: int) -> str:
    letters = ""
    idx = col_index
    while idx >= 0:
        letters = chr(65 + (idx % 26)) + letters
        idx = idx // 26 - 1
    return f"{letters}{row_num}"


async def _fact_rows_from_schema(
    s: AsyncSession,
    sheet: Sheet,
    file_id: int,
) -> List[PriceFact]:
    """Нормализует raw.cells -> mart.price_facts по подтверждённой LLM-схеме.

    Использует header_rows/data_start_row/columns из SheetSchema для корректной
    интерпретации многострочных/вложенных заголовков и сдвинутой шапки.
    Возвращает [] если шаблон не найден или не применим (тогда используется
    эвристический fallback).
    """
    schema = await _find_confirmed_template(s, sheet)
    if schema is None:
        return []

    # Строим маппинг col_index -> (name, path). Для колонок цен определяем
    # price_type/supplier из последнего уровня path (вложенный заголовок).
    col_map: Dict[int, Dict[str, Any]] = {}
    for col in schema.columns:
        col_map[col.col_index] = {
            "name": col.name,
            "path": col.path or [col.name],
        }

    # Ищем колонку item_name (обычно колонка с 'наименован'/'материал'/'лом' в path).
    item_cols = [
        c.col_index
        for c in schema.columns
        if _is_item_column(c)
    ]
    item_col = item_cols[0] if item_cols else None

    # Загружаем все ячейки листа.
    cells_result = await s.execute(
        select(Cell)
        .where(Cell.sheet_id == sheet.id)
        .order_by(Cell.row_num, Cell.col_index)
    )
    rows_by_num: Dict[int, Dict[int, Any]] = {}
    for cell in cells_result.scalars().all():
        if cell.row_num < (schema.data_start_row or 1):
            continue
        rows_by_num.setdefault(cell.row_num, {})[cell.col_index] = (
            cell.value_text if cell.value_text is not None else cell.value_number
        )

    out: List[PriceFact] = []
    for row_num, row_cells in sorted(rows_by_num.items()):
        # Определяем item_name. Если явной колонки нет — пробуем первую колонку.
        item_name = None
        if item_col is not None:
            item_name = row_cells.get(item_col)
        else:
            for cidx in sorted(row_cells):
                if cidx in col_map:
                    item_name = row_cells[cidx]
                    break
        if item_name is None or str(item_name).strip() in ("", "0", "итого", "итог", "всего", "сумма"):
            continue

        for col_index, value in row_cells.items():
            col_def = col_map.get(col_index)
            if col_def is None:
                continue
            if not isinstance(value, (int, float)):
                continue
            # Определяем тип цены и поставщика из пути вложенного заголовка.
            price_type, supplier = _price_from_path(col_def["path"])
            if price_type is None:
                continue
            out.append(PriceFact(
                file_id=file_id,
                sheet_id=sheet.id,
                source_row_ref=f"sheet:{sheet.id}:row:{row_num}:col:{col_index}",
                sheet_period=sheet.period,
                item_name=str(item_name).strip(),
                supplier=supplier,
                price_type=price_type,
                value=float(value),
                currency=DEFAULT_CURRENCY,
                unit=DEFAULT_UNIT,
            ))
    return out


def _is_item_column(col: ColumnInference) -> bool:
    """Определяет, является ли колонка колонкой наименования материала."""
    tokens = " ".join([col.name] + col.path).lower()
    return any(k in tokens for k in ("наименован", "материал", "лом", "вид", "товар", "продукц"))


def _price_from_path(path: List[str]) -> tuple[Optional[str], Optional[str]]:
    """Определяет (price_type, supplier) по пути вложенного заголовка колонки.

    Для внутренних типов ('среднерыночная', 'аукцион_старт', 'аукцион_победитель')
    возвращает price_type без supplier. Всё остальное — колонка поставщика.
    """
    if not path:
        return None, None
    leaf = " ".join(path).strip().lower()
    # Проверяем вложенные заголовки (например, ['Состав шихты на МАЙ, %', 'Утв. План']).
    last = (path[-1] or "").strip()
    key = last.lower()

    if "среднерыночн" in key or "средн" in key and "рыночн" in key:
        return "среднерыночная", None
    if "старт" in key or "стартов" in key:
        return "аукцион_старт", None
    if "победител" in key or "итог" in key or "результат" in key:
        return "аукцион_победитель", None
    if any(k in leaf for k in ("цена", "план", "факт", "руб", "поставщ")):
        return "поставщик", last or None
    if key and "увал" not in key:
        return "поставщик", last
    return None, None


async def _fact_rows_from_cells(
    s: AsyncSession,
    sheet: Sheet,
    file_id: int,
) -> List[PriceFact]:
    """Прямой парсинг raw.cells в mart.price_facts (без табличного структуратора)."""
    cols_result = await s.execute(
        select(ColumnMetadata)
        .where(ColumnMetadata.sheet_id == sheet.id)
        .order_by(ColumnMetadata.col_index)
    )
    columns = list(cols_result.scalars().all())
    if not columns:
        return []

    col_index_to_name = {c.col_index: c.normalized_name for c in columns}
    max_price_col = max((c.col_index for c in columns), default=2)

    cells_result = await s.execute(
        select(Cell)
        .where(Cell.sheet_id == sheet.id)
        .order_by(Cell.row_num, Cell.col_index)
    )
    rows_by_num: Dict[int, Dict[int, Any]] = {}
    for cell in cells_result.scalars().all():
        rows_by_num.setdefault(cell.row_num, {})[cell.col_index] = (
            cell.value_text if cell.value_text is not None else cell.value_number
        )

    out: List[PriceFact] = []
    for row_num, row_cells in sorted(rows_by_num.items()):
        item_name = row_cells.get(2)
        if item_name is None or str(item_name).strip() in ("", "0", "итого", "итог", "всего", "сумма"):
            continue

        for col_index in sorted(row_cells):
            if col_index <= 4 or col_index > max_price_col:
                continue
            value = row_cells[col_index]
            if not isinstance(value, (int, float)):
                continue
            supplier_raw = col_index_to_name.get(col_index, f"поставщик_{col_index}")
            price_type, supplier = _split_source(supplier_raw)
            out.append(PriceFact(
                file_id=file_id,
                sheet_id=sheet.id,
                source_row_ref=f"sheet:{sheet.id}:row:{row_num}:col:{col_index}",
                sheet_period=sheet.period,
                item_name=str(item_name).strip(),
                supplier=supplier,
                price_type=price_type,
                value=float(value),
                currency=DEFAULT_CURRENCY,
                unit=DEFAULT_UNIT,
            ))
    return out


def _split_source(source: str) -> tuple[Optional[str], Optional[str]]:
    """Разделяет price_source на (price_type, supplier).

    Внутренние источники ('среднерыночная', 'аукцион_старт', 'аукцион_победитель')
    относятся к price_type, supplier остаётся None. Всё остальное — это имя
    поставщика (колонка цены), price_type= 'поставщик'.
    """
    key = (source or "").strip().lower()
    if key in INTERNAL_SOURCES:
        return source.strip(), None
    if source and source.strip():
        return "поставщик", source.strip()
    return None, None