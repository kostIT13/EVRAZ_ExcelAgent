import re
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet
from src.core.logging_settings import logger

from src.core.excel.schemas import ParsedFile, ParsedSheet, ParsedHeader, ParsedCell


class ExcelParser:
    def __init__(self, file_path: Path, header_rows: Optional[int] = None):
        self.file_path = file_path
        self.workbook = None
        self._header_rows = header_rows  

    def parse(self) -> ParsedFile:
        self.workbook = load_workbook(self.file_path, data_only=True)
        sheets = []

        for sheet_name in self.workbook.sheetnames:
            ws = self.workbook[sheet_name]
            logger.info("Parsing sheet: {}", sheet_name)

            self._unmerge_cells(ws)

            header_rows = self._header_rows or self._detect_header_rows(ws)
            logger.debug("Sheet '{}': detected {} header rows", sheet_name, header_rows)

            headers = self._parse_headers(ws, header_rows)

            data = self._parse_data(ws, headers, header_rows)

            cells = self._collect_cells(ws, headers, header_rows)

            sheets.append(ParsedSheet(
                sheet_name=sheet_name,
                sheet_index=self.workbook.sheetnames.index(sheet_name),
                headers=headers,
                data=data,
                cells=cells,
                raw_data=self._get_raw_data(ws),
                header_rows=header_rows,
            ))

        total_rows = sum(s.row_count for s in sheets)
        total_cells = sum(s.col_count * s.row_count for s in sheets)

        return ParsedFile(
            filename=self.file_path.name,
            file_hash=self._get_file_hash(),
            sheets=sheets,
            total_rows=total_rows,
            total_cells=total_cells,
        )

    def _unmerge_cells(self, ws: Worksheet) -> None:
        merged = list(ws.merged_cells.ranges)
        if not merged:
            return

        logger.debug("Sheet '{}': unmerging {} ranges", ws.title, len(merged))

        ranges_with_values = []
        for merged_range in merged:
            top_left = (merged_range.min_row, merged_range.min_col)
            value = ws.cell(row=top_left[0], column=top_left[1]).value
            ranges_with_values.append((merged_range, value))

        for merged_range in merged:
            ws.unmerge_cells(str(merged_range))

        for merged_range, value in ranges_with_values:
            for row in range(merged_range.min_row, merged_range.max_row + 1):
                for col in range(merged_range.min_col, merged_range.max_col + 1):
                    ws.cell(row=row, column=col).value = value

        logger.debug("Sheet '{}': unmerged {} cells", ws.title, len(merged))


    def _detect_header_rows(self, ws: Worksheet) -> int:
        max_col = ws.max_column or 1
        max_row = ws.max_row or 1

        for row in range(1, min(max_row + 1, 10)):
            cell_val = ws.cell(row=row, column=1).value
            if isinstance(cell_val, (int, float)):
                return row - 1 

        for row in range(1, min(max_row + 1, 10)):
            filled = 0
            for col in range(1, min(max_col + 1, 5)):
                if ws.cell(row=row, column=col).value is not None:
                    filled += 1
            if filled >= 3:  
                if row > 1:
                    return row - 1

        return 3 

    def _get_raw_data(self, ws: Worksheet) -> List[List[Any]]:
        return [list(row) for row in ws.iter_rows(values_only=True)]

    def _parse_headers(self, ws: Worksheet, header_rows: int) -> List[ParsedHeader]:
        headers = []
        max_col = ws.max_column or 1

        for col in range(1, max_col + 1):
            raw_levels = []
            for row in range(1, header_rows + 1):
                cell_value = ws.cell(row=row, column=col).value
                if cell_value is not None:
                    cell_value = str(cell_value).strip().replace('\n', ' ')
                    raw_levels.append(cell_value)
                else:
                    raw_levels.append("")

            levels = []
            for lvl in raw_levels:
                if not levels or lvl != levels[-1]:
                    levels.append(lvl)

            full_name = " > ".join(l for l in levels if l) if any(l for l in levels if l) else f"col_{col}"

            col_name = self._normalize_column_name(full_name)

            headers.append(ParsedHeader(
                levels=levels,
                full_name=full_name,
                col_index=col,
                col_name=col_name,
            ))

        return headers

    def _parse_data(self, ws: Worksheet, headers: List[ParsedHeader], header_rows: int) -> List[Dict[str, Any]]:
        data = []
        start_row = header_rows + 1
        max_row = ws.max_row or 0

        for row in range(start_row, max_row + 1):
            row_data: Dict[str, Any] = {}
            has_any_value = False

            for col_idx, header in enumerate(headers):
                col = col_idx + 1
                cell_value = ws.cell(row=row, column=col).value

                if cell_value is not None:
                    has_any_value = True
                    if isinstance(cell_value, (int, float)):
                        row_data[header.col_name] = cell_value
                    else:
                        row_data[header.col_name] = str(cell_value).strip()
                else:
                    row_data[header.col_name] = None

            if has_any_value:
                data.append(row_data)

        return data


    def _collect_cells(self, ws: Worksheet, headers: List[ParsedHeader], header_rows: int) -> List[ParsedCell]:
        cells = []
        start_row = header_rows + 1
        max_row = ws.max_row or 0

        for row in range(start_row, max_row + 1):
            for col_idx, header in enumerate(headers):
                col = col_idx + 1
                cell_value = ws.cell(row=row, column=col).value
                if cell_value is not None:
                    cells.append(ParsedCell(
                        row=row,
                        col=col,
                        value=cell_value,
                        col_name=header.col_name,
                        sheet_name=ws.title,
                    ))

        return cells


    def _normalize_column_name(self, name: str) -> str:
        # Убираем специальные символы
        name = re.sub(r'[^\w\s]', '', name)
        # Заменяем пробелы на _
        name = re.sub(r'\s+', '_', name)
        # Приводим к нижнему регистру
        name = name.lower()
        # Убираем множественные _
        name = re.sub(r'_+', '_', name)
        # Убираем _ в начале и конце
        name = name.strip('_')
        return name or "unknown"


    def _get_file_hash(self) -> str:
        with open(self.file_path, 'rb') as f:
            return hashlib.sha256(f.read()).hexdigest()[:16]