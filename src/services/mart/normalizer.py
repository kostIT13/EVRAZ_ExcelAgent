from __future__ import annotations
import time
from typing import Any, Dict, List, Optional
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.db.database import async_session_maker
from src.core.db.models import (
    Cell,
    ColumnMetadata,
    Metric,
    PriceFact,
    Sheet,
    SheetTemplate,
    SupplierAlias,
)
from src.core.excel.schemas import ParsedSheet
from src.core.excel.schema_inference import ColumnInference, SheetSchema
from src.core.excel.sheet_kind_detector import SheetKind, detect_sheet_kind
from src.core.logging_settings import logger

INTERNAL_SOURCES = {"среднерыночная", "аукцион_старт", "аукцион_победитель"}

DEFAULT_UNIT = "тн"
DEFAULT_CURRENCY = "RUB"


async def normalize_file_to_mart(
    file_id: int,
    session: Optional[AsyncSession] = None,
) -> Dict[str, int]:
    start = time.monotonic()
    own_session = session is None
    s = session or async_session_maker()
    try:
        # 1. Удаляем старые факты файла (идемпотентность при перезаливе).
        result = await s.execute(delete(PriceFact).where(PriceFact.file_id == file_id))
        deleted = result.rowcount or 0
        # Чистим также metrics и aliases файла/листов.
        sheets_for_cleanup = list((await s.execute(
            select(Sheet).where(Sheet.file_id == file_id)
        )).scalars().all())
        sheet_ids = [sh.id for sh in sheets_for_cleanup]
        if sheet_ids:
            await s.execute(delete(Metric).where(Metric.file_id == file_id))
            await s.execute(delete(SupplierAlias).where(SupplierAlias.source_sheet_id.in_(sheet_ids)))

        # 2. Определяем sheet_kind для каждого листа и собираем факты.
        fact_rows: List[PriceFact] = []
        metric_rows: List[Metric] = []
        alias_rows: List[SupplierAlias] = []
        seen_aliases_global: set = set((await s.execute(
            select(SupplierAlias.alias)
        )).scalars().all())
        for sheet in sheets_for_cleanup:
            await _assign_sheet_kind(s, sheet)
            fact_rows.extend(await _fact_rows_for_sheet(s, sheet, file_id))
            metric_rows.extend(await _metric_rows_for_sheet(s, sheet, file_id))
            sheet_aliases = await _supplier_alias_rows_for_sheet(s, sheet, file_id)
            deduped = []
            for a in sheet_aliases:
                if a.alias.lower() not in seen_aliases_global:
                    seen_aliases_global.add(a.alias.lower())
                    deduped.append(a)
            alias_rows.extend(deduped)

        if fact_rows:
            s.add_all(fact_rows)
        if metric_rows:
            s.add_all(metric_rows)
        if alias_rows:
            s.add_all(alias_rows)
        await s.commit()

        elapsed_ms = int((time.monotonic() - start) * 1000)
        logger.info(
            "normalize_file_to_mart: file_id={}, deleted={}, inserted={} (facts), "
            "metrics={}, aliases={}, elapsed={}ms",
            file_id,
            deleted,
            len(fact_rows),
            len(metric_rows),
            len(alias_rows),
            elapsed_ms,
        )
        return {
            "deleted": deleted,
            "inserted": len(fact_rows),
            "metrics": len(metric_rows),
            "aliases": len(alias_rows),
            "elapsed_ms": elapsed_ms,
        }
    except Exception:
        await s.rollback()
        raise
    finally:
        if own_session:
            await s.close()


async def _assign_sheet_kind(s: AsyncSession, sheet: Sheet) -> None:
    headers = list((await s.execute(
        select(ColumnMetadata)
        .where(ColumnMetadata.sheet_id == sheet.id)
        .order_by(ColumnMetadata.col_index)
    )).scalars().all())
    header_names = [h.normalized_name for h in headers]

    sample_values: List[Optional[str]] = []
    if headers:
        sample_result = await s.execute(
            select(Cell)
            .where(Cell.sheet_id == sheet.id, Cell.row_num >= 2)
            .order_by(Cell.row_num)
            .limit(100)
        )
        sample_values = [
            (c.value_text or (str(c.value_number) if c.value_number is not None else None))
            for c in sample_result.scalars().all()
        ]

    kind = detect_sheet_kind(sheet.original_name, header_names, sample_values)
    if sheet.sheet_kind != kind:
        sheet.sheet_kind = kind
        sheet.sheet_kind_auto = True
        await s.flush()


async def _fact_rows_for_sheet(
    s: AsyncSession,
    sheet: Sheet,
    file_id: int,
) -> List[PriceFact]:
    if sheet.sheet_kind == SheetKind.MATRIX:
        return []
    schema_rows = await _fact_rows_from_schema(s, sheet, file_id)
    if schema_rows:
        return schema_rows
    return await _fact_rows_from_cells(s, sheet, file_id)


async def _metric_rows_for_sheet(
    s: AsyncSession,
    sheet: Sheet,
    file_id: int,
) -> List[Metric]:
    if sheet.sheet_kind != SheetKind.MATRIX:
        return []

    cols_result = await s.execute(
        select(ColumnMetadata)
        .where(ColumnMetadata.sheet_id == sheet.id)
        .order_by(ColumnMetadata.col_index)
    )
    columns = list(cols_result.scalars().all())
    if not columns:
        return []

    # Первая колонка — измерение (наименование/шихта).
    dimension_col = min(c.col_index for c in columns)
    metric_cols = [c for c in columns if c.col_index != dimension_col]

    cells_result = await s.execute(
        select(Cell)
        .where(Cell.sheet_id == sheet.id)
        .order_by(Cell.row_num, Cell.col_index)
    )
    rows_by_num: Dict[int, Dict[int, Any]] = {}
    for cell in cells_result.scalars().all():
        rows_by_num.setdefault(cell.row_num, {})[cell.col_index] = cell

    out: List[Metric] = []
    for row_num, row_cells in sorted(rows_by_num.items()):
        dim_cell = row_cells.get(dimension_col)
        if dim_cell is None:
            continue
        dim_value = dim_cell.value_text if dim_cell.value_text is not None else (
            str(dim_cell.value_number) if dim_cell.value_number is not None else None
        )
        if not dim_value or dim_value.strip().lower() in ("итого", "итог", "всего", "сумма", ""):
            continue

        for col in metric_cols:
            cell = row_cells.get(col.col_index)
            if cell is None:
                continue
            number = cell.value_number if cell.value_number is not None else _to_number(cell.value_text)
            is_blank = number is None
            if not is_blank:
                metric_type = _metric_type_from_name(col.normalized_name)
                out.append(Metric(
                    file_id=file_id,
                    sheet_id=sheet.id,
                    source_row_ref=f"sheet:{sheet.id}:row:{row_num}:col:{col.col_index}",
                    dimension_type="item",
                    dimension=str(dim_value).strip(),
                    period=sheet.period,
                    metric_type=metric_type,
                    metric=col.normalized_name,
                    value=float(number),
                    unit="%",
                    is_blank=False,
                ))
            else:
                # Сохраняем признак пустой ячейки явно.
                metric_type = _metric_type_from_name(col.normalized_name)
                out.append(Metric(
                    file_id=file_id,
                    sheet_id=sheet.id,
                    source_row_ref=f"sheet:{sheet.id}:row:{row_num}:col:{col.col_index}",
                    dimension_type="item",
                    dimension=str(dim_value).strip(),
                    period=sheet.period,
                    metric_type=metric_type,
                    metric=col.normalized_name,
                    value=None,
                    unit="%",
                    is_blank=True,
                ))
    return out


async def _supplier_alias_rows_for_sheet(
    s: AsyncSession,
    sheet: Sheet,
    file_id: int,
) -> List[SupplierAlias]:
    if sheet.sheet_kind != SheetKind.PRICES:
        return []

    # Загружаем существующие alias (глобальный unique-констрейнт).
    existing = set((await s.execute(
        select(SupplierAlias.alias)
    )).scalars().all())

    cols_result = await s.execute(
        select(ColumnMetadata)
        .where(ColumnMetadata.sheet_id == sheet.id)
        .order_by(ColumnMetadata.col_index)
    )
    columns = list(cols_result.scalars().all())
    if not columns:
        return []

    out: List[SupplierAlias] = []
    seen_aliases: set = set()
    for col in columns:
        name = col.normalized_name or col.original_name
        if not name or name.strip().lower() in ("", "наименование", "наименован"):
            continue
        canonical = _canonical_supplier(name)
        if not canonical:
            continue
        alias_key = name.strip().lower()
        if alias_key in existing or alias_key in seen_aliases:
            continue
        seen_aliases.add(alias_key)
        out.append(SupplierAlias(
            canonical_name=canonical,
            alias=name.strip(),
            source_sheet_id=sheet.id,
        ))
    return out


def _to_number(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value.replace(",", ".").replace(" ", "").replace("%", ""))
    except (ValueError, TypeError):
        return None


def _metric_type_from_name(name: str) -> str:
    key = (name or "").lower()
    if "отклон" in key:
        return "отклонение"
    if "факт" in key:
        return "факт"
    if "план" in key:
        return "план"
    if "%" in key or "процент" in key or "доля" in key:
        return "percent"
    return "value"


def _canonical_supplier(name: str) -> str:
    import re
    cleaned = re.sub(r"[*()]", " ", name)
    cleaned = re.sub(r"\+?\(?\d[\d\s\-().]{4,}\)?", " ", cleaned)  # телефоны
    cleaned = re.sub(r"\([^)]*\)", " ", cleaned)  # всё в скобках
    tokens = [t for t in cleaned.split() if len(t) > 1]
    if not tokens:
        return ""
    # Каноническое имя — первые 1-2 значимых слова.
    return " ".join(tokens[:2]).strip().lower()


async def _find_confirmed_template(
    s: AsyncSession,
    sheet: Sheet,
) -> Optional[SheetSchema]:
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
    schema = await _find_confirmed_template(s, sheet)
    if schema is None:
        return []

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
            # Пустая ячейка (NULL) — сохраняем признак is_blank, не превращаем в 0.
            if not isinstance(value, (int, float)):
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
                    value=None,
                    currency=DEFAULT_CURRENCY,
                    unit=DEFAULT_UNIT,
                    is_blank=True,
                ))
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
                is_blank=False,
            ))
    return out


def _is_item_column(col: ColumnInference) -> bool:
    tokens = " ".join([col.name] + col.path).lower()
    return any(k in tokens for k in ("наименован", "материал", "лом", "вид", "товар", "продукц"))


def _price_from_path(path: List[str]) -> tuple[Optional[str], Optional[str]]:
    if not path:
        return None, None
    leaf = " ".join(path).strip().lower()
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
            if col_index == 1 or col_index == 2 or col_index > max_price_col:
                continue
            value = row_cells[col_index]
            supplier_raw = col_index_to_name.get(col_index, f"поставщик_{col_index}")
            price_type, supplier = _split_source(supplier_raw)
            if price_type is None:
                continue
            # Пустая ячейка (NULL) сохраняется явно через is_blank, не как 0.
            if not isinstance(value, (int, float)):
                out.append(PriceFact(
                    file_id=file_id,
                    sheet_id=sheet.id,
                    source_row_ref=f"sheet:{sheet.id}:row:{row_num}:col:{col_index}",
                    sheet_period=sheet.period,
                    item_name=str(item_name).strip(),
                    supplier=supplier,
                    price_type=price_type,
                    value=None,
                    currency=DEFAULT_CURRENCY,
                    unit=DEFAULT_UNIT,
                    is_blank=True,
                ))
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
                is_blank=False,
            ))
    return out


def _split_source(source: str) -> tuple[Optional[str], Optional[str]]:
    key = (source or "").strip().lower()
    if not key:
        return None, None
    # Подстрока-детекция внутренних типов (аналог _price_from_path).
    if "среднерыночн" in key or ("средн" in key and "рыночн" in key):
        return "среднерыночная", None
    if "предлож_победител" in key or "победител" in key:
        return "аукцион_победитель", None
    if "стартовая" in key or "старт" in key or "стартов" in key:
        return "аукцион_старт", None
    if key in INTERNAL_SOURCES:
        return source.strip(), None
    # Всё остальное — колонка поставщика.
    return "поставщик", source.strip()