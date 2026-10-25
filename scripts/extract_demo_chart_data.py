# -*- coding: utf-8 -*-
"""Извлекает данные для демо-графиков из data_proportional_prices.xlsx.

1) Среднерыночная цена (колонка J) на «Лом твердых сплавов (без припоя)» по месяцам 2025.
2) «Предлож. победителя» (колонка L) на «Лом латуни ЛАЖМц» по месяцам 2025.
3) Значения колонки «Ферроком» (E) по всем видам «Лом меди…» на февральском листе.
"""
import json
from pathlib import Path

import openpyxl

XLSX = Path("data/data_proportional_prices.xlsx")
OUT = Path("scripts/demo_chart_data.json")

MONTH_LABELS = [
    "янв25", "фев25", "март25", "апр25", "май25",
    "июнь25", "июль25", "авг25", "сент25", "окт25", "нояб25", "дек25",
]
# Соответствие листа периоду: имя листа содержит русское сокращение месяца
PERIODS = [
    ("янв", "2025-01"), ("фев", "2025-02"), ("март", "2025-03"),
    ("апр", "2025-04"), ("май", "2025-05"), ("июн", "2025-06"),
    ("июл", "2025-07"), ("авг", "2025-08"), ("сент", "2025-09"),
    ("окт", "2025-10"), ("нояб", "2025-11"), ("дек", "2025-12"),
]

# Ключевые материалы и колонки
ITEM_HARD_ALLOY = "Лом твердых сплавов (без припоя)"  # колонка J — среднерыночная
ITEM_BRASS_LAZH = "Лом латуни ЛАЖМц"                    # колонка L — предлож. победителя
ITEM_ALUMINIUM = "Лом алюминия"                          # колонка J — среднерыночная
FEB_PERIOD = "2025-02"
COL_SR = 10   # J — среднерыночная цена
COL_L = 12    # L — предлож. победителя
COL_E = 5     # E — Ферроком
COL_B = 2     # B — наименование лома


def cell_str(v) -> str:
    if v is None:
        return ""
    s = str(v).strip().lower()
    return s.replace("\u00a0", " ")


def main() -> None:
    wb = openpyxl.load_workbook(XLSX, data_only=True)

    hard_alloy_series = []
    brass_series = []
    aluminium_series = []
    ferrokkom_feb = []

    for ws in wb.worksheets:
        title = ws.title or ""
        period = None
        for frag, code in PERIODS:
            if frag in title.lower():
                period = code
                break
        if period is None:
            continue

        # Строки листа
        for r_idx in range(4, ws.max_row + 1):
            name = cell_str(ws.cell(row=r_idx, column=COL_B).value)
            if not name:
                continue

            # 1) Лом твердых сплавов (без припоя) — среднерыночная цена
            if name == ITEM_HARD_ALLOY.lower():
                val = ws.cell(row=r_idx, column=COL_SR).value
                hard_alloy_series.append({
                    "period": period,
                    "value": round(float(val), 2) if isinstance(val, (int, float)) else None,
                })

            # 2) Лом латуни ЛАЖМц — предлож. победителя
            if name == ITEM_BRASS_LAZH.lower():
                val = ws.cell(row=r_idx, column=COL_L).value
                brass_series.append({
                    "period": period,
                    "value": round(float(val), 2) if isinstance(val, (int, float)) else None,
                })

            # 3) «Лом алюминия» — среднерыночная цена по месяцам (для примера с уточнением)
            if name == ITEM_ALUMINIUM.lower():
                val = ws.cell(row=r_idx, column=COL_SR).value
                aluminium_series.append({
                    "period": period,
                    "value": round(float(val), 2) if isinstance(val, (int, float)) else None,
                })

            # 4) Февраль: все виды меди по Ферроком
            if period == FEB_PERIOD and name.startswith("лом меди"):
                val = ws.cell(row=r_idx, column=COL_E).value
                ferrokkom_feb.append({
                    "item": ws.cell(row=r_idx, column=COL_B).value.strip(),
                    "value": round(float(val), 2) if isinstance(val, (int, float)) else None,
                })

    data = {
        "hard_alloy_market_price": hard_alloy_series,
        "brass_lazhm_winner_price": brass_series,
        "aluminium_market_price": aluminium_series,
        "ferrokkom_feb_copper_items": ferrokkom_feb,
    }
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()