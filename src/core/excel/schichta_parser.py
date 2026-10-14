"""Парсер шихтовочных листов (план/факт/отклонения по углю и шихте).

Формат листов «2 блок»/«3 блок»:
- Титульный блок (1-10 строк), затем шапка из 2 строк:
  R11: Поставщики | Стоимость | Состав шихты на МАЙ, % | % участия (ф. в.) | ...
  R12:             |           | Утв. План | факт (средн за период) | ...
- Данные: поставщик в колонке B, значения в остальных колонках.
- Строки-продолжения (число в колонке поставщика) пропускаются.

Формат листа «Отклонения от БЮДЖЕТА и ПЛАНА»:
- Шапка: R5 (блоки: 2 блок / 3 блок / Отклонение), R7 (подзаголовки).
  Метки «3 блок»/«Отклонение» в файле отсутствуют — выводятся по позиции
  блоков (7 колонок на блок, начиная с колонки «2 блок»).
- Данные: поставщик в колонке A, значения в остальных колонках.
- Сводные строки (число в колонке A) помечаются измерением «сводная_строка».
"""
from __future__ import annotations

import re
from typing import Any, List, Optional, Tuple

from openpyxl.worksheet.worksheet import Worksheet

from src.core.excel.schemas import ParsedCell, ParsedHeader, ParsedSheet
from src.core.logging_settings import logger


def is_schichta_sheet(sheet_name: str) -> bool:
    """True для листов шихтовочного формата (блоки/отклонения)."""
    name = (sheet_name or "").lower()
    return any(k in name for k in ("блок", "шихт", "отклонени"))


def _is_number(v: Any) -> bool:
    """Число или числовая строка (openpyxl часто возвращает числа строками)."""
    if isinstance(v, bool):
        return False
    if isinstance(v, (int, float)):
        return True
    if isinstance(v, str):
        try:
            float(v.strip().replace(",", ".").replace(" ", ""))
            return True
        except ValueError:
            return False
    return False


def _clean(v: Any) -> str:
    if v is None:
        return ""
    s = str(v).strip().replace("\n", " ")
    return re.sub(r"\s+", " ", s)


def _norm(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[^\w\s%]", " ", s)
    s = re.sub(r"\s+", "_", s).strip("_")
    return s or "col"


def _find_header_start(ws: Worksheet) -> int:
    """Строка с заголовком 'Поставщики' (начало шапки блок-листа)."""
    for row in range(1, min(ws.max_row, 30) + 1):
        for col in range(1, min(ws.max_column, 5) + 1):
            v = ws.cell(row=row, column=col).value
            if v and "поставщик" in str(v).lower():
                return row
    return 1


def _find_block_row(ws: Worksheet) -> Optional[int]:
    """Строка с '2 блок' (лист отклонений)."""
    for row in range(1, min(ws.max_row, 20) + 1):
        for col in range(1, min(ws.max_column, 30) + 1):
            v = ws.cell(row=row, column=col).value
            if v and "2 блок" in str(v).lower():
                return row
    return None


def _find_subheader_row(ws: Worksheet, start: int) -> int:
    """Строка подзаголовков после start (плотно заполненная текстом)."""
    for row in range(start + 1, min(ws.max_row, start + 6) + 1):
        text_count = 0
        for col in range(1, min(ws.max_column, 30) + 1):
            v = ws.cell(row=row, column=col).value
            if v is not None and not _is_number(v) and str(v).strip():
                text_count += 1
        if text_count >= 3:
            return row
    return start


def _deviation_blocks(ws: Worksheet, block_row: int) -> List[Tuple[int, int, str]]:
    """Определяет блоки листа отклонений: [(start_col, end_col, name), ...].

    Метка «2 блок» есть в файле; «3 блок» и «Отклонение» выводятся по позиции
    (ширина блока — расстояние до следующей непустой ячейки в строке блоков).
    """
    start_col = None
    for col in range(1, min(ws.max_column, 30) + 1):
        v = ws.cell(row=block_row, column=col).value
        if v and "2 блок" in str(v).lower():
            start_col = col
            break
    if start_col is None:
        return []

    # После unmerge все ячейки объединённого диапазона содержат метку блока
    # («2 блок»/«3 блок»/«Отклонение») — пропускаем их при поиске границы.
    next_col = None
    for col in range(start_col + 1, min(ws.max_column, 30) + 1):
        v = ws.cell(row=block_row, column=col).value
        s = str(v).strip() if v is not None else ""
        if s and not any(k in s.lower() for k in ("блок", "отклонен")):
            next_col = col
            break
    width = (next_col - start_col) if next_col else 7

    blocks: List[Tuple[int, int, str]] = []
    col = start_col
    for name in ("2 блок", "3 блок", "отклонение"):
        blocks.append((col, col + width - 1, name))
        col += width
    return blocks


def _build_headers(
    ws: Worksheet,
    row1: int,
    row2: int,
    dim_col_index: Optional[int] = None,
) -> List[ParsedHeader]:
    """Собирает заголовки блок-листа из двух строк шапки.

    Числовые заголовки (веса колонок) пропускаются; колонка-измерение
    получает имя «поставщик».
    """
    headers: List[ParsedHeader] = []
    used: set = set()
    for col in range(1, ws.max_column + 1):
        if col == dim_col_index:
            headers.append(ParsedHeader(
                levels=["Поставщик"],
                full_name="Поставщик",
                col_index=col,
                col_name="поставщик",
            ))
            used.add("поставщик")
            continue

        v1 = ws.cell(row=row1, column=col).value
        v2 = ws.cell(row=row2, column=col).value
        h1 = _clean(v1)
        h2 = _clean(v2)

        if _is_number(v1) and _is_number(v2):
            name = f"col_{col}"
        elif _is_number(v1):
            name = h2 or f"col_{col}"          # числовой вес в основной шапке
        elif _is_number(v2):
            name = h1 or f"col_{col}"          # числовой вес в подшапке
        elif h2 and h1 and h1 != h2:
            name = f"{h1} > {h2}"
        else:
            name = h1 or h2 or f"col_{col}"

        col_name = _norm(name)
        if col_name in used:
            col_name = f"{col_name}_{col}"
        used.add(col_name)

        levels: List[str] = []
        if h1 and not _is_number(v1):
            levels.append(h1)
        if h2 and not _is_number(v2) and h2 != h1:
            levels.append(h2)
        headers.append(ParsedHeader(
            levels=levels,
            full_name=name,
            col_index=col,
            col_name=col_name,
        ))
    return headers


def _build_deviation_headers(
    ws: Worksheet,
    block_row: int,
    sub_row: int,
    blocks: List[Tuple[int, int, str]],
) -> List[ParsedHeader]:
    """Собирает заголовки листа отклонений: блок + подзаголовок."""
    headers: List[ParsedHeader] = []
    used: set = set()
    for col in range(1, ws.max_column + 1):
        if col == 1:
            headers.append(ParsedHeader(
                levels=["Поставщик"],
                full_name="Поставщик",
                col_index=col,
                col_name="поставщик",
            ))
            used.add("поставщик")
            continue

        block_name = next((b[2] for b in blocks if b[0] <= col <= b[1]), "")
        sub_v = ws.cell(row=sub_row, column=col).value
        sub_h = _clean(sub_v)

        if _is_number(sub_v):
            name = block_name or f"col_{col}"
        elif block_name and sub_h:
            name = f"{block_name} > {sub_h}"
        else:
            name = block_name or sub_h or f"col_{col}"

        col_name = _norm(name)
        if col_name in used:
            col_name = f"{col_name}_{col}"
        used.add(col_name)

        levels: List[str] = []
        if block_name:
            levels.append(block_name)
        if sub_h and not _is_number(sub_v) and sub_h != block_name:
            levels.append(sub_h)
        headers.append(ParsedHeader(
            levels=levels,
            full_name=name,
            col_index=col,
            col_name=col_name,
        ))
    return headers


def _collect_data(
    ws: Worksheet,
    headers: List[ParsedHeader],
    data_start: int,
    sheet_name: str,
    dim_col_index: int,
    numeric_dim: str,
) -> Tuple[List[dict], List[ParsedCell]]:
    """Собирает строки данных.

    numeric_dim:
      - 'skip'  — строки с числовым значением измерения пропускаются
                  (строки-продолжения в блок-листах);
      - 'label' — числовое значение измерения заменяется на «сводная_строка»
                  (сводные строки в листе отклонений).
    """
    dim_header = next((h for h in headers if h.col_index == dim_col_index), None)
    data: List[dict] = []
    cells: List[ParsedCell] = []

    for row in range(data_start, ws.max_row + 1):
        row_data: dict = {}
        for header in headers:
            v = ws.cell(row=row, column=header.col_index).value
            if v is not None and str(v).strip() != "":
                row_data[header.col_name] = v
        if not row_data:
            continue

        if dim_header:
            dv = row_data.get(dim_header.col_name)
            if dv is not None and _is_number(dv):
                if numeric_dim == "skip":
                    continue
                row_data[dim_header.col_name] = "сводная_строка"

        for header in headers:
            v = row_data.get(header.col_name)
            if v is not None:
                cells.append(ParsedCell(
                    row=row,
                    col=header.col_index,
                    value=v,
                    col_name=header.col_name,
                    sheet_name=sheet_name,
                ))
        data.append(row_data)

    return data, cells


def parse_schichta_sheet(
    ws: Worksheet,
    sheet_name: str,
    sheet_index: int,
) -> ParsedSheet:
    """Разбирает шихтовочный лист в ParsedSheet с чистыми заголовками.

    Путь выбирается по имени листа: «Отклонения…» — лист отклонений
    (блоки 2/3/отклонение по колонкам), «2 блок»/«3 блок» — блок-листы
    (поставщик в колонке B).
    """
    name_lower = (sheet_name or "").lower()
    if "отклонени" in name_lower:
        # Лист «Отклонения от БЮДЖЕТА и ПЛАНА»
        block_row = _find_block_row(ws) or 1
        sub_row = _find_subheader_row(ws, block_row)
        blocks = _deviation_blocks(ws, block_row)
        headers = _build_deviation_headers(ws, block_row, sub_row, blocks)
        data, cells = _collect_data(ws, headers, sub_row + 1, sheet_name, 1, "label")
        header_rows = sub_row - block_row + 1
    else:
        # Лист «2 блок» / «3 блок»
        header_start = _find_header_start(ws)
        sub_row = _find_subheader_row(ws, header_start)
        headers = _build_headers(ws, header_start, sub_row, dim_col_index=2)
        data, cells = _collect_data(ws, headers, sub_row + 1, sheet_name, 2, "skip")
        header_rows = sub_row - header_start + 1

    logger.info(
        "Schichta parser: sheet='{}', headers={}, data_rows={}",
        sheet_name,
        len(headers),
        len(data),
    )
    return ParsedSheet(
        sheet_name=sheet_name,
        sheet_index=sheet_index,
        headers=headers,
        data=data,
        cells=cells,
        header_rows=header_rows,
    )