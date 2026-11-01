# -*- coding: utf-8 -*-
"""Дополнение к extract_demo_chart_data.py: данные для двух новых демо-карточек.

1) Февраль 2025: значения по всем видам «Лом меди…» в колонках поставщиков
   Ферроком (E), Сплав-21 (F), ЦветМет (G), Шами-сервис (H) — для дельты min/max.
2) Среднерыночная цена (колонка J) на цинковые лома по месяцам 2025 — для MIN за все месяцы.
"""
import json
from pathlib import Path

import openpyxl

XLSX = Path("data/data_proportional_prices.xlsx")

PERIODS = [
    ("янв", "2025-01"), ("фев", "2025-02"), ("март", "2025-03"),
    ("апр", "2025-04"), ("май", "2025-05"), ("июн", "2025-06"),
    ("июл", "2025-07"), ("авг", "2025-08"), ("сент", "2025-09"),
    ("окт", "2025-10"), ("нояб", "2025-11"), ("дек", "2025-12"),
]

COL_B = 2  # B — наименование лома
COL_SR = 10  # J — среднерыночная цена
SUPPLIER_COLS = {"Ферроком": 5, "Сплав-21": 6, "ЦветМет": 7, "Шами-сервис": 8}
FEB = "2025-02"


def cell_str(v) -> str:
    if v is None:
        return ""
    return str(v).strip().replace("\u00a0", " ").lower()


def main() -> None:
    wb = openpyxl.load_workbook(XLSX, data_only=True)

    feb_copper: list[dict] = []   # {item, supplier, value}
    zinc_series: list[dict] = []  # {period, item, value}

    for ws in wb.worksheets:
        title = (ws.title or "").lower()
        period = None
        for frag, code in PERIODS:
            if frag in title:
                period = code
                break
        if period is None:
            continue

        for r_idx in range(4, ws.max_row + 1):
            name = cell_str(ws.cell(row=r_idx, column=COL_B).value)
            if not name:
                continue

            # 1) февраль: все виды медного лома по 4 поставщикам
            if period == FEB and name.startswith("лом меди"):
                for supplier, col in SUPPLIER_COLS.items():
                    val = ws.cell(row=r_idx, column=col).value
                    if isinstance(val, (int, float)):
                        feb_copper.append({
                            "item": ws.cell(row=r_idx, column=COL_B).value.strip(),
                            "supplier": supplier,
                            "value": round(float(val), 2),
                        })

            # 2) цинковые лома — среднерыночная цена по месяцам
            if "цинк" in name:
                val = ws.cell(row=r_idx, column=COL_SR).value
                if isinstance(val, (int, float)):
                    zinc_series.append({
                        "period": period,
                        "item": ws.cell(row=r_idx, column=COL_B).value.strip(),
                        "value": round(float(val), 2),
                    })

    data = {
        "feb_copper_by_supplier": feb_copper,
        "zinc_market_price": zinc_series,
    }
    Path("scripts/demo_chart_data2.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
