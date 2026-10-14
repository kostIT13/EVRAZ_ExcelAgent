"""Временный скрипт: проверка парсинга Faked-файла текущим ExcelParser."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.excel.parser import ExcelParser

PATH = "data/Faked_List_proportional (2).xlsx"
OUT = "scripts/faked_parse_dump.txt"

parsed = ExcelParser(Path(PATH)).parse()
lines = []
for sheet in parsed.sheets:
    lines.append(f"===== SHEET: {sheet.sheet_name} | header_rows={sheet.header_rows} | "
                 f"rows={sheet.row_count} | cols={len(sheet.headers)} =====")
    for h in sheet.headers[:30]:
        lines.append(f"  col={h.col_index} name='{h.col_name}' full='{h.full_name}'")
    lines.append("  --- первые 5 строк данных ---")
    for row in sheet.data[:5]:
        lines.append(f"  {str(row)[:200]}")
    lines.append("")

with open(OUT, "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines))
print("written", OUT, len(lines), "lines")